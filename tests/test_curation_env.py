"""Offline checks of the paid curation test's setup (tests/test_curation_skill.py)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.test_curation_skill import (
    ALLOWED_TOOLS,
    CLAUDE_HOME,
    COMPAT_OUTCOMES,
    COMPAT_STEPS,
    OUTCOMES,
    RUN_VAR,
    SERVED_CHECK,
    changed_reviewed,
    child_env,
    claude_command,
    codex_command,
    compat_failures,
    dropped_claims,
    no_change_failures,
    outcome_failures,
    path_violations,
    recorded_runs,
    stopped_failures,
    tier_failure,
    uncommitted_failure,
)

PACK = "data.example.gov"
#: Skill step 11.3's run directory: `.curation/<pack>-<UTC date>-<n>/evals-<k>` (#70).
EVAL_RUNS = tuple(f".curation/{PACK}-2026-10-30-1/evals-{k}" for k in (1, 2, 3))
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
    return {
        "outcome": "completed",
        "pack": PACK,
        "pack_digest": DIGEST,
        "eval_runs": list(EVAL_RUNS),
        **over,
    }


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
        "CHANGELOG.md",
    ]
    assert path_violations(allowed, pack) == []
    foreign = [
        "docs/decisions.md",
        "src/opendata_atlas/portals/data.seattle.gov/guides.py",
        "evals/portals/data.seattle.gov.json",
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


EXAMPLES = Path(__file__).resolve().parents[1] / "docs" / "pack-examples"
PLACE = (EXAMPLES / "place_field.toml").read_text()
PLACEHOLDER = (EXAMPLES / "placeholder_share.toml").read_text()
PLACEHOLDER_ID = "crime-neighborhood-pre2017-placeholder"


def _unreviewed(text: str, claim_id: str) -> str:
    """The claim as the profiler drafts it: no interpretation, no review metadata."""
    drafted = re.sub(r"^(interpretation|reviewed_by|reviewed_at) = .*\n", "", text, flags=re.M)
    return drafted.replace(PLACEHOLDER_ID, claim_id)


def test_changed_reviewed_lists_only_added_or_changed_reviewed_claims():
    changed_place = PLACE.replace('reason = "', 'reason = "Revised. ', 1)
    assert changed_place != PLACE
    now = [changed_place, PLACEHOLDER, _unreviewed(PLACEHOLDER, "drafted-placeholder")]
    assert changed_reviewed(now, [PLACE]) == ["crime-neighborhood-place-field", PLACEHOLDER_ID]
    assert changed_reviewed([PLACE, PLACEHOLDER], [PLACE, PLACEHOLDER]) == []


def test_unreviewed_placeholder_declarations_need_no_served_entry():
    """Copilot on #41: `Claim.reviewed` needs review metadata beside the placeholders."""
    assert changed_reviewed([_unreviewed(PLACEHOLDER, "drafted")], []) == []


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


@pytest.mark.parametrize("portal", ["seattle", "data.seattle.gov", "Seattle", "Seattle, WA"])
def test_no_change_resolves_the_portal_as_step_1_does(portal):
    outcome = {"outcome": "no_change", "pack": "data.seattle.gov"}
    failures = no_change_failures(
        outcome, commits=0, porcelain="", pack_id="data.seattle.gov", portal=portal
    )
    assert failures == []


def test_no_change_for_another_place_names_pack_is_flagged():
    """Copilot on #41: a place name used to skip the identity check."""
    outcome = {"outcome": "no_change", "pack": "data.seattle.gov"}
    (failure,) = no_change_failures(
        outcome, commits=0, porcelain="", pack_id="data.seattle.gov", portal="Chicago, IL"
    )
    assert "['data.cityofchicago.org']" in failure


def test_no_change_for_an_unknown_portal_is_flagged():
    outcome = {"outcome": "no_change", "pack": "data.seattle.gov"}
    (failure,) = no_change_failures(
        outcome, commits=0, porcelain="", pack_id="data.seattle.gov", portal="Atlantis"
    )
    assert "matches no registered portal" in failure


def test_no_change_for_another_portals_pack_is_flagged():
    outcome = {"outcome": "no_change", "pack": "seattle"}
    failures = no_change_failures(
        outcome, commits=1, porcelain="", pack_id="data.seattle.gov", portal="chicago"
    )
    assert any("1 commit" in f for f in failures)
    assert any("'chicago' is ['data.cityofchicago.org']" in f for f in failures)


# --- #67 to #70: compatibility case, merged facts, stop outcomes, eval run directories ---


def test_completed_needs_three_recorded_eval_runs(tmp_path):
    """#70: the runs live where outcome.json says, so a rerun cannot overwrite them."""
    _healthy(tmp_path)
    for bad in (None, EVAL_RUNS[:2], [EVAL_RUNS[0]] * 3, ["/tmp/evals-1", *EVAL_RUNS[1:]]):
        (failure,) = _check(_completed(eval_runs=bad), tmp_path)
        assert "eval_runs" in failure, bad
    assert recorded_runs(_completed()) == list(EVAL_RUNS)
    assert recorded_runs(_completed(eval_runs=[".curation/../x", *EVAL_RUNS[1:]])) is None


def test_eval_runs_anywhere_under_curation_count_as_made(tmp_path):
    blocked = {"outcome": "blocked_engine", "pack": PACK, "reason": "engine gap"}
    (tmp_path / ".curation" / f"{PACK}-2026-10-30-2" / "evals-1").mkdir(parents=True)
    (failure,) = _check(blocked, tmp_path)
    assert "eval runs were made" in failure


def _compat(wt: Path, portal: str, **steps: str) -> None:
    kinds = {s: steps.get(s, "ok") for s in COMPAT_STEPS}
    row = {"portal": portal, "steps": {s: {"outcome": k, "kind": k} for s, k in kinds.items()}}
    (wt / COMPAT_OUTCOMES).parent.mkdir(parents=True, exist_ok=True)
    (wt / COMPAT_OUTCOMES).write_text(json.dumps([row]))


def test_compat_case_must_pass_for_a_completed_run(tmp_path):
    """#67: the compatibility case is a promotion condition, so a completed run records it."""
    _healthy(tmp_path)
    check = {"pack": PACK, "digest_now": DIGEST, "task_ids": TASKS, "reviewed": REVIEWED}
    (failure,) = outcome_failures(_completed(), wt=tmp_path, portal_id=PACK, **check)
    assert "missing or unreadable" in failure
    _compat(tmp_path, PACK)
    assert outcome_failures(_completed(), wt=tmp_path, portal_id=PACK, **check) == []
    _compat(tmp_path, PACK, query_p2="transient")
    assert "query_p2" in compat_failures(tmp_path, PACK)[0]
    assert "no row" in compat_failures(tmp_path, "data.other.gov")[0]


def test_dropped_claims_names_base_claims_the_run_removed():
    """#68: copying a profiler facts file over an existing one drops its reviewed claims."""
    base = ['[[claim]]\nid = "a"\n\n[[claim]]\nid = "b"\n']
    assert (
        dropped_claims(['[[claim]]\nid = "a"\n[[claim]]\nid = "b"\n[[claim]]\nid = "c"\n'], base)
        == []
    )
    assert dropped_claims(['[[claim]]\nid = "a"\n[[claim]]\nid = "c"\n'], base) == ["b"]


@pytest.mark.parametrize(
    "state", ["preflight_failed", "not_registered", "needs_input", "profiler_failed"]
)
def test_stop_outcomes_need_a_reason_no_commit_and_a_clean_worktree(tmp_path, state):
    """#69: every stop goes through the Ending, so each has an outcome."""
    assert state in OUTCOMES
    outcome = {"outcome": state, "pack": None, "reason": "why it stopped"}
    assert _check_stop(outcome, tmp_path) == []
    assert stopped_failures(outcome, commits=0, porcelain="") == []
    assert "commit" in stopped_failures(outcome, commits=1, porcelain="")[0]
    assert "worktree" in stopped_failures(outcome, commits=0, porcelain="?? x\n")[0]
    assert "needs a reason" in _check_stop({"outcome": state, "pack": None}, tmp_path)[0]


def _check_stop(outcome, wt: Path) -> list[str]:
    return outcome_failures(outcome, pack=None, digest_now="", wt=wt, task_ids=[], reviewed=[])


def test_allowlist_permits_the_preflight_and_compat_commands():
    """Skill steps 0 and 11.1 run these as written; the headless session must allow them."""
    for rule in (
        "Bash(uv --version)",
        "Bash(git rev-parse:*)",
        "Bash(claude --version)",
        "Bash(COMPAT_EVIDENCE_DIR=.curation/compat uv run:*)",
    ):
        assert rule in ALLOWED_TOOLS, rule


def test_skill_names_the_compat_command_as_contributing_does():
    root = Path(__file__).resolve().parent.parent
    skill = (root / "skills/curate-portal/SKILL.md").read_text(encoding="utf-8")
    contributing = (root / "CONTRIBUTING-portals.md").read_text(encoding="utf-8")
    command = re.search(r"`(COMPAT_EVIDENCE_DIR=[^`]+)`", contributing)
    assert command is not None
    assert f"`{command.group(1)}`" in skill
    for state in OUTCOMES:
        assert f"`{state}`" in skill, state
