"""Offline checks of the paid curation test's setup (tests/test_curation_skill.py)."""

from __future__ import annotations

import json
from pathlib import Path

from tests.test_curation_skill import (
    ALLOWED_TOOLS,
    CLAUDE_HOME,
    EVAL_RUNS,
    RUN_VAR,
    SERVED_CHECK,
    changed_reviewed,
    child_env,
    claude_command,
    codex_command,
    no_change_failures,
    outcome_failures,
    path_violations,
    tier_failure,
    uncommitted_failure,
)

PACK = "data.example.gov"
DIGEST = "sha256:aaaa"
TASKS = ["01-a", "02-b"]
REVIEWED = ["a", "b"]


def _entry(claim_id: str, matches: bool = True) -> dict:
    return {"claim_id": claim_id, "expected": "x", "served": "x", "matches": matches}


def _healthy(wt: Path, runs=EVAL_RUNS, tasks=TASKS) -> None:
    for run in runs:
        (wt / run).mkdir(parents=True, exist_ok=True)
        for tid in tasks:
            event = {"type": "result", "subtype": "success", "result": "an answer"}
            (wt / run / f"{tid}.transcript.jsonl").write_text(json.dumps(event) + "\n")
    (wt / SERVED_CHECK).write_text(json.dumps([_entry(i) for i in REVIEWED]))


def _completed(**over) -> dict:
    return {"outcome": "completed", "pack": PACK, "pack_digest": DIGEST, **over}


def _check(outcome, wt: Path) -> list[str]:
    return outcome_failures(
        outcome, pack=PACK, digest_now=DIGEST, wt=wt, task_ids=TASKS, reviewed=REVIEWED
    )


def test_completed_outcome_with_its_evidence_passes(tmp_path):
    _healthy(tmp_path)
    assert _check(_completed(), tmp_path) == []


def test_pack_changed_after_step_11_3_is_flagged(tmp_path):
    """Rule 13: King County run 2's formatter wrap would have shown here."""
    _healthy(tmp_path)
    (failure,) = _check(_completed(pack_digest="sha256:bbbb"), tmp_path)
    assert "changed after the eval runs began" in failure


def test_completed_without_a_full_eval_run_is_flagged(tmp_path):
    _healthy(tmp_path, runs=EVAL_RUNS[:2])
    (failure,) = _check(_completed(), tmp_path)
    assert failure.startswith(EVAL_RUNS[2])


def test_completed_with_a_missing_transcript_is_flagged(tmp_path):
    _healthy(tmp_path)
    (tmp_path / EVAL_RUNS[0] / "02-b.transcript.jsonl").unlink()
    (failure,) = _check(_completed(), tmp_path)
    assert EVAL_RUNS[0] in failure and "02-b" in failure


def test_an_unhealthy_transcript_is_a_grade_not_a_failure(tmp_path):
    """A session over its budget grades FAIL (skill step 11.3); the run itself is complete."""
    _healthy(tmp_path)
    bad = {"type": "result", "subtype": "error_max_budget_usd"}
    (tmp_path / EVAL_RUNS[0] / "02-b.transcript.jsonl").write_text(json.dumps(bad) + "\n")
    assert _check(_completed(), tmp_path) == []


def test_completed_without_the_served_check_is_flagged(tmp_path):
    _healthy(tmp_path)
    (tmp_path / SERVED_CHECK).unlink()
    (failure,) = _check(_completed(), tmp_path)
    assert SERVED_CHECK in failure


def test_served_check_with_an_unmatched_claim_is_flagged(tmp_path):
    _healthy(tmp_path)
    served = [_entry("a"), _entry("b", matches=False)]
    (tmp_path / SERVED_CHECK).write_text(json.dumps(served))
    (failure,) = _check(_completed(), tmp_path)
    assert "not served as reviewed" in failure and "'b'" in failure


def test_no_change_that_made_eval_runs_is_flagged(tmp_path):
    no_change = {"outcome": "no_change", "pack": PACK, "reason": "no new dataset in the bound"}
    assert _check(no_change, tmp_path) == []
    _healthy(tmp_path, runs=EVAL_RUNS[:1])
    (failure,) = _check(no_change, tmp_path)
    assert "eval runs were made" in failure


def test_uncommitted_pack_changes_are_flagged():
    assert uncommitted_failure("") is None
    problem = uncommitted_failure(
        " M src/opendata_atlas/portals/x/guides.py\n?? evals/portals/x.json\n"
    )
    assert problem is not None and "guides.py" in problem and "x.json" in problem


def test_blocked_run_that_made_eval_runs_is_flagged(tmp_path):
    """Rule 12: a stopped run skips step 11.3, so no paid eval run exists."""
    blocked = {"outcome": "blocked_engine", "pack": PACK, "reason": "engine gap: bundle list"}
    assert _check(blocked, tmp_path) == []
    _healthy(tmp_path, runs=EVAL_RUNS[:1])
    (failure,) = _check(blocked, tmp_path)
    assert "eval runs were made" in failure


def test_outcome_states_and_reason_are_required(tmp_path):
    assert _check(None, tmp_path) == ["outcome.json: missing or not an object"]
    assert "not one of" in _check({"outcome": "done", "pack": PACK}, tmp_path)[0]
    no_reason = {"outcome": "profiled_without_review", "pack": PACK}
    assert _check(no_reason, tmp_path) == ["outcome.json: profiled_without_review needs a reason"]
    other = {"outcome": "profiled_without_review", "pack": "x.gov", "reason": "none found"}
    assert "the branch adds" in _check(other, tmp_path)[0]


def test_codex_command_confines_writes_and_allows_network(tmp_path):
    git_dir, last = tmp_path / "repo" / ".git", tmp_path / "last.txt"
    command = codex_command("data.honolulu.gov", tmp_path / "wt", git_dir, last)
    assert command[:2] == ["codex", "exec"]
    assert command[-1] == "Curate data.honolulu.gov by following skills/curate-portal/SKILL.md."
    assert command[command.index("-C") + 1] == str(tmp_path / "wt")
    assert command[command.index("-s") + 1] == "workspace-write"
    assert "--dangerously-bypass-approvals-and-sandbox" not in command
    configs = [command[i + 1] for i, v in enumerate(command) if v == "-c"]
    assert 'approval_policy="never"' in configs
    assert "sandbox_workspace_write.network_access=true" in configs
    roots = [c for c in configs if c.startswith("sandbox_workspace_write.writable_roots=")]
    assert len(roots) == 1
    assert json.loads(roots[0].split("=", 1)[1]) == [str(git_dir), str(CLAUDE_HOME)]
    assert command[command.index("-o") + 1] == str(last)


def test_child_env_drops_the_opt_in_variable():
    """Nothing the curating agent runs can start a nested, paid curation run."""
    base = {RUN_VAR: "1", "PATH": "/usr/bin", "ATLAS_CURATION_PORTAL": "x.example.gov"}
    assert RUN_VAR in base  # known positive: the variable is there to drop
    env = child_env(base)
    assert RUN_VAR not in env
    assert env == {"PATH": "/usr/bin", "ATLAS_CURATION_PORTAL": "x.example.gov"}


def test_claude_command_is_the_documented_one():
    command = claude_command("data.honolulu.gov")
    assert command[:3] == [
        "claude",
        "-p",
        "Curate data.honolulu.gov by following skills/curate-portal/SKILL.md.",
    ]
    assert command[command.index("--allowedTools") + 1] == ALLOWED_TOOLS
    assert command[command.index("--max-turns") + 1] == "200"
    assert command[command.index("--permission-mode") + 1] == "acceptEdits"
    assert "Bash(git push:*)" not in ALLOWED_TOOLS


def test_claude_command_caps_spend():
    """Ruling 74: the curation session is capped at $12 by the CLI itself."""
    command = claude_command("data.honolulu.gov")
    assert command.count("--max-budget-usd") == 1
    assert command[command.index("--max-budget-usd") + 1] == "12"


def test_claude_command_loads_no_mcp_servers():
    """Ruling 61: `--strict-mcp-config` with no `--mcp-config` restricts MCP servers only: the
    child loads no MCP server from another configuration, and the skill calls the server
    in-process. Plugins, skills, hooks, the user's CLAUDE.md and memory still load (ruling 65);
    whether claude.ai connectors are dropped is not yet probed."""
    command = claude_command("data.honolulu.gov")
    assert "--strict-mcp-config" in command
    assert "--mcp-config" not in command


def test_path_rule_allows_the_pack_paths_and_flags_others():
    pack = "data.honolulu.gov"
    allowed = [
        f"src/opendata_atlas/portals/{pack}/portal.toml",
        f"src/opendata_atlas/portals/{pack}/facts/6hui-dvrh.toml",
        f"evals/portals/{pack}.json",
        "src/opendata_atlas/portals/registry_overrides.toml",
        "src/opendata_atlas/portals/validation.json",
        "docs/decisions.md",
    ]
    assert path_violations(allowed, pack) == []
    foreign = [
        "src/opendata_atlas/portals/seattle/guides.py",
        "evals/portals/seattle.json",
        "src/opendata_atlas/portals/tiers.py",
        f"src/opendata_atlas/portals/{pack}x/portal.toml",
    ]
    assert path_violations(allowed + foreign, pack) == foreign


def test_tier_check_allows_at_most_profiled():
    """Ruling 64: the curating agent never promotes its own pack."""
    assert tier_failure("profiled") is None
    assert tier_failure("generic") is None
    assert tier_failure("curated") is not None  # known positive: run 2 declared this
    assert tier_failure("curated", "profiled") is not None


def test_tier_check_lets_an_existing_pack_keep_its_tier():
    """Re-curating a curated pack (King County, 2026-10-20) neither raises nor lowers it."""
    assert tier_failure("curated", "curated") is None


def test_tier_check_rejects_lowering_an_existing_pack():
    """The tier is the reviewer's to change (skill step 12)."""
    assert tier_failure("profiled", "curated") is not None
    assert tier_failure("profiled", "profiled") is None


def test_served_check_of_bare_matches_is_flagged(tmp_path):
    """#28: `[{"matches": true}]` used to pass."""
    _healthy(tmp_path)
    (tmp_path / SERVED_CHECK).write_text(json.dumps([{"matches": True}]))
    failures = _check(_completed(), tmp_path)
    assert any("entries without" in f for f in failures)
    assert any("reviewed claims with no entry: ['a', 'b']" in f for f in failures)


def test_served_check_missing_a_reviewed_claim_is_flagged(tmp_path):
    _healthy(tmp_path)
    (tmp_path / SERVED_CHECK).write_text(json.dumps([_entry("a")]))
    (failure,) = _check(_completed(), tmp_path)
    assert failure.endswith("reviewed claims with no entry: ['b']")


def _claims(*claims: str) -> str:
    return "".join(f'[[claim]]\nid = "{c}"\n{body}\n' for c, body in (x.split("|") for x in claims))


def test_changed_reviewed_lists_only_added_or_changed_reviewed_claims():
    base = [_claims("old|interpretation = {kind = 'a'}", "draft|kind = 'x'")]
    now = [
        _claims(
            "old|interpretation = {kind = 'a'}",
            "draft|interpretation = {kind = 'b'}",
            "new|placeholders = ['-']",
            "observed|kind = 'y'",
        )
    ]
    assert changed_reviewed(now, base) == ["draft", "new"]


def test_no_change_with_a_clean_worktree_passes():
    outcome = {"outcome": "no_change", "pack": "seattle"}
    assert (
        no_change_failures(
            outcome, commits=0, porcelain="", pack_id="data.seattle.gov", portal="seattle"
        )
        == []
    )


def test_no_change_with_worktree_changes_is_flagged():
    """#29: tracked edits with no commit used to pass."""
    outcome = {"outcome": "no_change", "pack": "seattle"}
    (failure,) = no_change_failures(
        outcome,
        commits=0,
        porcelain=" M src/opendata_atlas/core/query.py\n",
        pack_id="data.seattle.gov",
        portal="seattle",
    )
    assert "worktree has changes" in failure and "query.py" in failure


def test_no_change_for_another_portals_pack_is_flagged():
    outcome = {"outcome": "no_change", "pack": "seattle"}
    failures = no_change_failures(
        outcome, commits=1, porcelain="", pack_id="data.seattle.gov", portal="chicago"
    )
    assert any("1 commit" in f for f in failures)
    assert any("'chicago' is 'data.cityofchicago.org'" in f for f in failures)
