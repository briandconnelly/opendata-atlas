"""Headless run of the curate-portal skill (docs/design.md, Curation runbook). Paid and opt-in.

Runs only with `ATLAS_RUN_CURATION=1` and `--run-integration -m integration`, so neither the weekly
live run nor the drift run starts it. `ATLAS_CURATION_PORTAL` picks the portal (default
`data.honolulu.gov`); `ATLAS_CURATION_HOST` the curating agent, `claude` (default) or `codex`;
`ATLAS_CURATION_EVIDENCE` names a directory for `summary.json`.

The run starts one curation session (`claude -p`, up to 200 turns and $12; or `codex exec`,
which has no budget option and is bounded only by the 3-hour timeout). The agent writes
`.curation/outcome.json` (skill, Ending). On `completed`, the agent made 3 eval runs, the test
checks them and the full offline gate, and makes one more eval run. On `profiled_without_review`
or `blocked_engine`, the test checks that no eval run was made and makes none. Eval answers are
graded by hand from `summary.json`.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tomllib
from collections import Counter
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from opendata_atlas.portals.tiers import COVERS

if TYPE_CHECKING:
    from collections.abc import Mapping

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parent.parent
PORTAL = os.environ.get("ATLAS_CURATION_PORTAL", "data.honolulu.gov")
HOST = os.environ.get("ATLAS_CURATION_HOST", "claude")
RUN_VAR = "ATLAS_RUN_CURATION"
TIMEOUT_S = 3 * 60 * 60
ALLOWED_TOOLS = (
    "Read,Edit,Write,Glob,Grep,Bash(uv run:*),Bash(git add:*),Bash(git commit:*),"
    "Bash(git status:*),Bash(git diff:*),Bash(git log:*),Bash(ls:*),Bash(mkdir:*)"
)
PORTALS = "src/opendata_atlas/portals"
PROMPT = "Curate {portal} by following skills/curate-portal/SKILL.md."
#: The agent's ending states (skill, Ending): only `completed` makes eval runs.
OUTCOMES = ("completed", "profiled_without_review", "blocked_engine", "no_change")
EVAL_RUNS = (".curation/evals-1", ".curation/evals-2", ".curation/evals-3")
SERVED_CHECK = ".curation/served-check.json"
CLAUDE_HOME = Path.home() / ".claude"

_spec = importlib.util.spec_from_file_location("pack_digest", ROOT / "scripts" / "pack_digest.py")
assert _spec is not None and _spec.loader is not None
_digest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_digest)
pack_digest = _digest.pack_digest

#: Run in the worktree: every guide example of the pack through the in-process client.
GUIDE_CHECK = """
import asyncio, json, sys
from pathlib import Path
from fastmcp import Client
from opendata_atlas.mcp.server import build_server
from opendata_atlas.portals.loader import load_portal

async def main(pack):
    out = []
    async with Client(build_server()) as client:
        for guide in load_portal(Path(pack)).guides:
            for example in guide.examples:
                result = await client.call_tool_mcp("atlas_query_dataset", example.arguments)
                wire = result.model_dump(mode="json", by_alias=True, exclude_none=True)
                failed = bool(wire.get("isError"))
                out.append({
                    "guide": guide.guide_id,
                    "question": example.question,
                    "is_error": failed,
                    "code": (wire.get("structuredContent") or {}).get("code") if failed else None,
                })
    print(json.dumps(out))

asyncio.run(main(sys.argv[1]))
"""


def child_env(base: Mapping[str, str]) -> dict[str, str]:
    """`base` without `ATLAS_RUN_CURATION`, so nothing the curating agent runs (its own
    `uv run pytest`, the drift run, the evals) can start a nested curation run."""
    return {k: v for k, v in base.items() if k != RUN_VAR}


# Ruling 74: the CLI enforces this per-session cap; the milestone's cost gate relies on it.
CURATION_BUDGET_USD = 12


def claude_command(portal: str) -> list[str]:
    return [
        "claude",
        "-p",
        PROMPT.format(portal=portal),
        "--allowedTools",
        ALLOWED_TOOLS,
        "--strict-mcp-config",
        "--permission-mode",
        "acceptEdits",
        "--max-turns",
        "200",
        "--max-budget-usd",
        str(CURATION_BUDGET_USD),
        "--output-format",
        "stream-json",
        "--verbose",
    ]


def codex_command(portal: str, wt: Path, git_dir: Path, last_message: Path) -> list[str]:
    """`codex exec` in the worktree: writes confined to it and to the repository's git directory
    (a worktree's commits land there), network on for the profiler and the drift run, and no
    approval prompts. `~/.claude` is writable too, for the Claude Code eval sessions the agent
    starts (step 11.3). `codex exec` has no budget option (docs/decisions.md, ruling 74)."""
    return [
        "codex",
        "exec",
        "-C",
        str(wt),
        "-s",
        "workspace-write",
        "-c",
        'approval_policy="never"',
        "-c",
        "sandbox_workspace_write.network_access=true",
        "-c",
        f"sandbox_workspace_write.writable_roots={json.dumps([str(git_dir), str(CLAUDE_HOME)])}",
        "--json",
        "-o",
        str(last_message),
        PROMPT.format(portal=portal),
    ]


def outcome_failures(
    outcome: object, *, pack: str, digest_now: str, wt: Path, task_ids: list[str]
) -> list[str]:
    """What `.curation/outcome.json` gets wrong against the branch and the worktree.

    `completed` must record the digest the committed pack still has (rule 13), all 3 eval runs
    with a transcript per task (an unhealthy one is a FAIL grade, not a skill failure), and the
    served check; the other outcomes a `reason` and no eval run (rule 12)."""
    if not isinstance(outcome, dict):
        return ["outcome.json: missing or not an object"]
    state = outcome.get("outcome")
    if state not in OUTCOMES:
        return [f"outcome.json: outcome {state!r} is not one of {list(OUTCOMES)}"]
    out = []
    if outcome.get("pack") != pack:
        out.append(f"outcome.json: pack {outcome.get('pack')!r}, but the branch adds {pack!r}")
    made = [d for d in EVAL_RUNS if (wt / d).exists()]
    if state != "completed":
        if not (isinstance(outcome.get("reason"), str) and outcome["reason"].strip()):
            out.append(f"outcome.json: {state} needs a reason")
        if made:
            out.append(f"outcome.json: {state}, but eval runs were made: {made}")
        return out
    if outcome.get("pack_digest") != digest_now:
        out.append(
            f"outcome.json: pack_digest {outcome.get('pack_digest')!r} recorded at step 11.3, "
            f"but the committed pack is {digest_now}: the pack changed after the eval runs began"
        )
    for run in EVAL_RUNS:
        missing = [tid for tid in task_ids if not (wt / run / f"{tid}.transcript.jsonl").is_file()]
        if missing:
            out.append(f"{run}: no transcript for {missing}")
    try:
        served = json.loads((wt / SERVED_CHECK).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        served = None
    if not (isinstance(served, list) and served):
        out.append(f"{SERVED_CHECK}: missing or not a non-empty list (skill step 6)")
    return out


def path_violations(paths: list[str], pack: str) -> list[str]:
    """Changed paths outside the path rule (CONTRIBUTING-portals.md, Rules) plus
    `docs/decisions.md`, where the skill logs every engine defect it finds (its rule 7)."""
    allowed = {
        f"evals/portals/{pack}.json",
        f"{PORTALS}/registry_overrides.toml",
        f"{PORTALS}/validation.json",
        "docs/decisions.md",
    }
    return [p for p in paths if p not in allowed and not p.startswith(f"{PORTALS}/{pack}/")]


def tier_failure(tier: object, base_tier: object = None) -> str | None:
    """The curating agent never raises a tier to `curated` (ruling 64, skill rule 3); a
    reviewer promotes. An existing pack keeps the tier it had at `base_tier`."""
    if tier in ("generic", "profiled") or tier == base_tier:
        return None
    return f"declared tier {tier!r} (base {base_tier!r}); the curating agent never raises it"


def result_event(transcript: Path) -> dict[str, Any]:
    """The last `result` event of a stream-json transcript, or {} when there is none."""
    events = []
    for line in transcript.read_text(encoding="utf-8").splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    results = [e for e in events if isinstance(e, dict) and e.get("type") == "result"]
    return results[-1] if results else {}


def claim_summary(pack_dir: Path) -> dict[str, Any]:
    """Claim counts by kind; reviewed claims; those with a reason and probe evidence."""
    kinds: Counter[str] = Counter()
    reviewed = with_reason_and_probe = 0
    for path in [*sorted((pack_dir / "facts").glob("*.toml")), pack_dir / "regions.toml"]:
        if not path.is_file():
            continue
        for claim in tomllib.loads(path.read_text(encoding="utf-8")).get("claim", []):
            kinds[claim.get("kind", "?")] += 1
            interpretation = claim.get("interpretation")
            if interpretation or claim.get("placeholders"):
                reviewed += 1
            kinds_of_evidence = {e.get("kind") for e in claim.get("evidence", [])}
            probed = kinds_of_evidence & {"soql_probe", "metadata_probe"}
            if interpretation and interpretation.get("reason") and probed:
                with_reason_and_probe += 1
    return {
        "by_kind": dict(sorted(kinds.items())),
        "reviewed": reviewed,
        "with_interpretation_reason_and_probe": with_reason_and_probe,
    }


def _run(args: list[str], cwd: Path, env: dict[str, str], **kw: Any) -> subprocess.CompletedProcess:
    print(f"$ {' '.join(args)}", flush=True)
    return subprocess.run(args, check=False, cwd=cwd, env=env, text=True, capture_output=True, **kw)


def _git(*args: str, cwd: Path = ROOT) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, text=True, capture_output=True
    ).stdout


def _curate(wt: Path, env: dict[str, str], transcript: Path) -> dict[str, Any]:
    """Step 2: the headless curation session; its exit code and final `result` event (for
    Codex, its last message, and `success` when it exits 0 with one)."""
    if HOST == "codex":
        last = transcript.with_suffix(".last-message.txt")
        git_dir = Path(_git("rev-parse", "--git-common-dir", cwd=wt).strip()).resolve()
        with transcript.open("w") as out:
            session = subprocess.run(
                codex_command(PORTAL, wt, git_dir, last),
                check=False,
                cwd=wt,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=subprocess.STDOUT,
                timeout=TIMEOUT_S,
            )
        message = last.read_text(encoding="utf-8") if last.is_file() else ""
        return {
            "host": "codex",
            "exit_code": session.returncode,
            "subtype": "success" if session.returncode == 0 and message.strip() else "error",
            "total_cost_usd": None,
            "final_message": message,
            "transcript": str(transcript),
        }
    with transcript.open("w") as out:
        session = subprocess.run(
            claude_command(PORTAL),
            check=False,
            cwd=wt,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=subprocess.STDOUT,
            timeout=TIMEOUT_S,
        )
    final = result_event(transcript)
    return {
        "host": "claude",
        "exit_code": session.returncode,
        "subtype": final.get("subtype"),
        "is_error": final.get("is_error"),
        "num_turns": final.get("num_turns"),
        "duration_ms": final.get("duration_ms"),
        "total_cost_usd": final.get("total_cost_usd"),
        "final_message": final.get("result"),
        "transcript": str(transcript),
    }


def _branch(wt: Path, base: str, branch: str, summary: dict, failures: list[str]) -> str | None:
    """Step 4: the branch's commits, the pack they add, and the path rule. Returns the pack."""
    commits = int(_git("rev-list", "--count", f"{base}..{branch}").strip())
    changed = (
        _git("diff", "--name-only", f"HEAD~{commits}", "HEAD", cwd=wt).split() if commits else []
    )
    evals = "evals/portals/"
    packs = sorted(
        {p.split("/")[3] for p in changed if p.startswith(f"{PORTALS}/") and p.count("/") >= 4}
        | {p.removeprefix(evals).removesuffix(".json") for p in changed if p.startswith(evals)}
    )
    pack = packs[0] if len(packs) == 1 else None
    summary.update(commits=commits, changed_paths=changed, pack=pack)
    if commits < 1:
        failures.append("the branch has no commit")
        return None
    if pack is None:
        failures.append(f"expected one pack directory among the changed paths, found {packs}")
        return None
    summary["path_violations"] = violations = path_violations(changed, pack)
    if violations:
        failures.append(f"paths outside the path rule: {violations}")
    return pack


def _gates(
    wt: Path,
    pack_dir: Path,
    portal_id: str,
    env: dict,
    summary: dict,
    failures: list,
    *,
    full: bool,
):
    """Step 5: the offline gate, the scoped drift run and every guide example. `full` (a
    `completed` run) is the whole suite and the read-only lint, format and type checks, which
    read untracked files too; otherwise the pack's own tests, since a blocked run may stop on a
    failing engine test."""
    tests = (
        ["--ignore=tests/test_curation_skill.py"]
        if full
        else ["tests/test_packs.py", "tests/test_tiers.py", "tests/test_release_gate.py"]
    )
    drift = ["--run-integration", "-m", "integration", "tests/test_drift.py", "-k", portal_id]
    commands = {
        "offline_gate": ["uv", "run", "pytest", "-q", *tests],
        "drift": ["uv", "run", "pytest", *drift],
    }
    if full:
        commands |= {
            "ruff_check": ["uv", "run", "ruff", "check"],
            "ruff_format": ["uv", "run", "ruff", "format", "--check"],
            "ty": ["uv", "run", "ty", "check"],
        }
    for name, args in commands.items():
        done = _run(args, wt, env)
        summary["checks"][name] = {"exit_code": done.returncode, "tail": done.stdout[-1500:]}
        if done.returncode != 0:
            failures.append(f"{name} exited {done.returncode}")
    guides = _run(["uv", "run", "python", "-c", GUIDE_CHECK, str(pack_dir)], wt, env)
    examples = json.loads(guides.stdout) if guides.returncode == 0 else []
    summary["checks"]["guide_examples"] = {
        "exit_code": guides.returncode,
        "examples": examples,
        "stderr_tail": guides.stderr[-1500:] if guides.returncode else "",
    }
    if guides.returncode != 0 or any(e["is_error"] for e in examples):
        failures.append(f"guide examples: exit {guides.returncode}, {examples}")


def _evals(wt: Path, pack: str, out: Path, env: dict, summary: dict, failures: list[str]):
    """Step 5: the eval file covers all four kinds, and one eval run ends every task healthy."""
    eval_file = wt / "evals" / "portals" / f"{pack}.json"
    tasks = json.loads(eval_file.read_text()) if eval_file.is_file() else []
    covered = {c for t in tasks for c in t.get("covers", [])}
    missing = [c for c in COVERS if c not in covered]
    summary["eval_covers_missing"] = missing
    if missing or not tasks:
        failures.append(f"eval file {eval_file.name}: {len(tasks)} tasks, missing {missing}")
    if not tasks:
        return
    args = ["uv", "run", "python", "evals/run.py", "--portal", pack, str(out)]
    code = _run(args, wt, env, timeout=TIMEOUT_S).returncode
    answers = [_answer(task, out / f"{task['id']}.transcript.jsonl") for task in tasks]
    summary["checks"]["evals"] = {"exit_code": code, "out": str(out)}
    summary["eval_answers"] = answers
    unhealthy = [a["id"] for a in answers if a["subtype"] != "success"]
    if code != 0 or unhealthy:
        failures.append(f"evals: exit {code}, unhealthy transcripts {unhealthy}")


def _answer(task: dict[str, Any], transcript: Path) -> dict[str, Any]:
    event = result_event(transcript) if transcript.is_file() else {}
    return {
        "id": task["id"],
        "covers": task.get("covers", []),
        "prompt": task["prompt"],
        "expect": task["expect"],
        "subtype": event.get("subtype"),
        "total_cost_usd": event.get("total_cost_usd"),
        "answer": event.get("result"),
    }


@pytest.mark.skipif(os.environ.get(RUN_VAR) != "1", reason=f"paid; set {RUN_VAR}=1 to run")
def test_curation_skill_produces_a_passing_pack(tmp_path):
    env = child_env(os.environ)
    branch = f"curate/test-{date.today().isoformat()}"
    wt = tmp_path / "wt"
    base = _git("rev-parse", "HEAD").strip()
    _git("worktree", "add", str(wt), "-b", branch, "HEAD")  # 1.
    print(f"worktree {wt} on {branch} at {base}", flush=True)

    curation = _curate(wt, env, tmp_path / "curation.transcript.jsonl")  # 2.
    summary: dict[str, Any] = {
        "portal": PORTAL,
        "branch": branch,
        "base": base,
        "curation": curation,
        "checks": {},
    }
    failures: list[str] = []
    if curation["subtype"] != "success":  # 3.
        failures.append(f"curation transcript ends {curation['subtype']!r}")

    try:
        outcome = json.loads((wt / ".curation" / "outcome.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        outcome = None
    summary["outcome"] = outcome
    no_change = isinstance(outcome, dict) and outcome.get("outcome") == "no_change"
    if no_change:  # 4. An existing pack, nothing new to review: no commit (skill step 5).
        commits = int(_git("rev-list", "--count", f"{base}..{branch}").strip())
        has_pack = (ROOT / PORTALS / str(outcome.get("pack")) / "portal.toml").is_file()
        if commits or not has_pack or not str(outcome.get("reason") or "").strip():
            failures.append(f"no_change needs no commit, an existing pack and a reason: {outcome}")
        pack = None
    else:
        pack = _branch(wt, base, branch, summary, failures)  # 4.
    if pack is not None:  # 5.
        pack_dir = wt / PORTALS / pack
        identity = tomllib.loads((pack_dir / "portal.toml").read_text(encoding="utf-8"))
        summary.update(
            pack_dir=f"{PORTALS}/{pack}",
            portal_id=identity["id"],
            declared_tier=identity.get("tier"),
            jurisdiction=identity.get("jurisdiction"),
            timezone=identity.get("timezone"),
            claims=claim_summary(pack_dir),
        )
        try:
            base_toml = _git("show", f"{base}:{PORTALS}/{pack}/portal.toml")
            base_tier = tomllib.loads(base_toml).get("tier")
        except subprocess.CalledProcessError:
            base_tier = None  # a new pack
        if (problem := tier_failure(identity.get("tier"), base_tier)) is not None:
            failures.append(problem)
        eval_file = wt / "evals" / "portals" / f"{pack}.json"
        tasks = json.loads(eval_file.read_text()) if eval_file.is_file() else []
        failures += outcome_failures(
            outcome,
            pack=pack,
            digest_now=pack_digest(wt, pack),
            wt=wt,
            task_ids=[t["id"] for t in tasks],
        )
        completed = isinstance(outcome, dict) and outcome.get("outcome") == "completed"
        _gates(wt, pack_dir, identity["id"], env, summary, failures, full=completed)
        if completed:
            _evals(wt, pack, tmp_path / "evals", env, summary, failures)

    summary["failures"] = failures  # 6. Written whether or not the run passed.
    evidence = os.environ.get("ATLAS_CURATION_EVIDENCE")
    if evidence:
        Path(evidence).mkdir(parents=True, exist_ok=True)
        (Path(evidence) / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps({k: summary.get(k) for k in ("pack", "declared_tier", "failures")}))
    assert failures == [], failures
