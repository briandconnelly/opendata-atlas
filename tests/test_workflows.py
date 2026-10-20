"""Workflow shape. The weekly drift workflow cannot run without a GitHub remote, so this file is
its only check: it parses the YAML strictly and runs the issue loop against a stub `gh`."""

from __future__ import annotations

import copy
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOWS = Path(__file__).parent.parent / ".github" / "workflows"
PYTEST_CMD = (
    "uv run pytest --run-integration -m integration tests/test_drift.py "
    "--drift-report drift-report.json"
)
ISSUES_CMD = (
    "uv run python scripts/drift_issues.py drift-report.json --out drift-issues "
    '--run-url "${{ github.server_url }}/${{ github.repository }}'
    '/actions/runs/${{ github.run_id }}"'
)


def _load(name: str) -> dict[str, Any]:
    doc = yaml.safe_load((WORKFLOWS / name).read_text())
    # YAML 1.1 reads the key `on` as the boolean True.
    doc["on"] = doc.pop(True) if True in doc else doc["on"]
    return doc


def _steps(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return doc["jobs"]["drift"]["steps"]


def shape_problems(doc: dict[str, Any], live: dict[str, Any]) -> list[str]:  # noqa: PLR0912
    """Everything wrong with a drift workflow document; empty when it has the intended shape."""
    problems: list[str] = []
    if doc.get("on", {}).get("schedule") != [{"cron": "41 15 * * 1"}]:
        problems.append("schedule is not the single weekly cron")
    if "workflow_dispatch" not in doc.get("on", {}):
        problems.append("no workflow_dispatch")
    if doc.get("permissions") != {"contents": "read", "issues": "write"}:
        problems.append("permissions are not contents: read, issues: write")
    if list(doc.get("jobs", {})) != ["drift"]:
        problems.append("jobs are not exactly `drift`")
        return problems
    steps = _steps(doc)
    live_steps = live["jobs"]["live"]["steps"]
    for index, label in ((0, "checkout"), (1, "setup-uv")):
        if steps[index].get("uses") != live_steps[index].get("uses"):
            problems.append(f"{label} is not pinned to the SHA live.yml uses")
    runs = [s.get("run") for s in steps]
    if runs[2:5] != ["uv sync --locked", PYTEST_CMD, ISSUES_CMD]:
        problems.append("the sync, pytest and issue-body steps are not exactly as specified")
        return problems
    if len(steps) != 6:
        problems.append("expected six steps: checkout, uv, sync, pytest, bodies, issue loop")
        return problems
    if steps[3].get("continue-on-error") is not True:
        problems.append("the pytest step lacks continue-on-error: true")
    if "if" in steps[3]:
        problems.append("the pytest step must run unconditionally")
    for step in steps[4:]:
        if step.get("if") != "always()":
            problems.append(f"step {step.get('name')!r} lacks `if: always()`")
    loop = steps[5]
    if loop.get("env", {}).get("GH_TOKEN") != "${{ github.token }}":
        problems.append("the issue loop lacks GH_TOKEN: ${{ github.token }}")
    if loop.get("shell") != "bash":
        problems.append(
            "the issue loop lacks `shell: bash` (pipefail), so a failed list opens a duplicate"
        )
    script = loop.get("run", "")
    for needle in (
        'gh issue list --label drift --state open --search "$title in:title"',
        "gh issue comment",
        "gh issue create --label drift",
        "drift-issues/titles.tsv",
    ):
        if needle not in script:
            problems.append(f"the issue loop lacks `{needle}`")
    return problems


@pytest.fixture
def drift() -> dict[str, Any]:
    return _load("drift.yml")


@pytest.fixture
def live() -> dict[str, Any]:
    return _load("live.yml")


def test_drift_workflow_shape(drift, live):
    assert shape_problems(drift, live) == []
    assert "UNEXERCISED" in (WORKFLOWS / "drift.yml").read_text()


def _mutate_cron(d):
    d["on"]["schedule"][0]["cron"] = "41 15 * * *"


def _drop_issues_permission(d):
    d["permissions"].pop("issues")


def _unpin_checkout(d):
    _steps(d)[0]["uses"] = "actions/checkout@v7"


def _change_pytest(d):
    _steps(d)[3]["run"] = "uv run pytest --run-integration -m integration"


def _drop_continue(d):
    _steps(d)[3].pop("continue-on-error")


def _drop_always_on_bodies(d):
    _steps(d)[4].pop("if")


def _drop_always_on_loop(d):
    _steps(d)[5]["if"] = "success()"


def _drop_token(d):
    _steps(d)[5]["env"].pop("GH_TOKEN")


def _drop_create(d):
    step = _steps(d)[5]
    step["run"] = step["run"].replace("gh issue create --label drift", "gh issue create")


def _drop_pipefail_shell(d):
    _steps(d)[5].pop("shell")


def _drop_dispatch(d):
    d["on"].pop("workflow_dispatch")


@pytest.mark.parametrize(
    "mutate",
    [
        _mutate_cron,
        _drop_issues_permission,
        _unpin_checkout,
        _change_pytest,
        _drop_continue,
        _drop_always_on_bodies,
        _drop_always_on_loop,
        _drop_token,
        _drop_create,
        _drop_pipefail_shell,
        _drop_dispatch,
    ],
)
def test_shape_check_catches(mutate, drift, live):
    """Known positives: the shape check must fail on each way the workflow could be wrong."""
    broken = copy.deepcopy(drift)
    mutate(broken)
    assert shape_problems(broken, live) != []


def test_live_workflow_unchanged(live):
    runs = [s.get("run") for s in live["jobs"]["live"]["steps"]]
    assert "uv run pytest --run-integration -m integration" in runs


STUB_GH = """#!/bin/sh
echo "$@" >> "$GH_LOG"
case "$1 $2" in
  "issue list") [ -n "$GH_LIST_FAIL" ] && exit 1; cat "$GH_LIST" ;;
esac
"""


def _run_loop(drift, tmp_path, listing: str, *, list_fails: bool = False, work=None):
    """Run the issue loop's shell with a stub `gh`; return the stub's calls.

    Without `work`, the loop reads two synthetic portals' issue files; with it, the files
    already in `work/drift-issues`.
    """
    if work is None:
        work = tmp_path / "work"
        (work / "drift-issues").mkdir(parents=True)
        (work / "drift-issues" / "titles.tsv").write_text(
            "a.example\tDrift: a.example\nb.example\tDrift: b.example\n"
        )
        for portal in ("a.example", "b.example"):
            (work / "drift-issues" / f"{portal}.md").write_text(f"body {portal}\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(STUB_GH)
    gh.chmod(0o755)
    (tmp_path / "list.json").write_text(listing)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "GH_LOG": str(tmp_path / "calls.log"),
        "GH_LIST": str(tmp_path / "list.json"),
        "GH_LIST_FAIL": "1" if list_fails else "",
    }
    step = _steps(drift)[5]
    # What Actions runs: `shell: bash` is `bash -eo pipefail`, the default is `bash -e`.
    flags = "-eo pipefail" if step.get("shell") == "bash" else "-e"
    proc = subprocess.run(
        ["bash", *flags.split(), "-c", step["run"]], cwd=work, env=env, check=False
    )
    log = tmp_path / "calls.log"
    return proc.returncode, (log.read_text().splitlines() if log.exists() else [])


def test_issue_loop_comments_on_a_match_and_creates_otherwise(drift, tmp_path):
    listing = (
        '[{"number": 7, "title": "Drift: a.example"},'
        ' {"number": 9, "title": "Drift: a.example extra"}]'
    )
    returncode, calls = _run_loop(drift, tmp_path, listing)
    assert returncode == 0
    assert "issue comment 7 --body-file drift-issues/a.example.md" in calls
    assert (
        "issue create --label drift --title Drift: b.example --body-file drift-issues/b.example.md"
        in calls
    )
    # An issue whose title only contains ours is not a match.
    assert not any(c.startswith("issue comment 9") for c in calls)
    assert sum(c.startswith("issue create") for c in calls) == 1


def test_issue_loop_fails_closed_when_listing_fails(drift, tmp_path):
    """A failed `gh issue list` must stop the step, not open a duplicate issue."""
    returncode, calls = _run_loop(drift, tmp_path, "[]", list_fails=True)
    assert returncode != 0
    assert any(c.startswith("issue list") for c in calls)  # the stub did see the failing call
    assert not any(c.startswith("issue create") for c in calls)
    assert not any(c.startswith("issue comment") for c in calls)


def test_a_run_that_fails_before_any_claim_opens_an_issue(drift, tmp_path):
    """Final review M-8, offline: no drift report (a collection-time PackError) still ends in
    a `Drift: run failed` issue, through the workflow's own body and loop steps."""
    import importlib.util
    import shlex

    spec = importlib.util.spec_from_file_location(
        "drift_issues", Path(__file__).parent.parent / "scripts" / "drift_issues.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    work = tmp_path / "work"
    work.mkdir()
    argv = shlex.split(_steps(drift)[4]["run"].replace("${{ github.run_id }}", "1"))
    assert argv[:4] == ["uv", "run", "python", "scripts/drift_issues.py"]
    cwd = Path.cwd()
    os.chdir(work)
    try:
        assert module.main(argv[4:]) == 0
    finally:
        os.chdir(cwd)
    returncode, calls = _run_loop(drift, tmp_path, "[]", work=work)
    assert returncode == 0
    created = [c for c in calls if c.startswith("issue create")]
    assert len(created) == 1 and "--title Drift: run failed" in created[0], calls
