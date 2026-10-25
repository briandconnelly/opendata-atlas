"""Milestone 3 Task 12: per-portal eval task files and the eval runner.

`docs/design.md` Per-portal eval tasks and Evals are the spec. Tasks live in
`evals/portals/<pack dir>.json` (one portal's tasks) and `evals/tasks.json` (cross-portal).
"""

from __future__ import annotations

import importlib.util
import itertools
import json
import tomllib
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from opendata_atlas.portals import validation
from opendata_atlas.portals.freshness import claim_validation
from opendata_atlas.portals.loader import SEATTLE, load_portal

ROOT = Path(__file__).resolve().parent.parent
EVALS = ROOT / "evals"
CROSS = EVALS / "tasks.json"
PORTAL_FILES = sorted((EVALS / "portals").glob("*.json"))
STALE_FIXTURE = EVALS / "fixtures" / "validation-stale.json"

_spec = importlib.util.spec_from_file_location("eval_run", EVALS / "run.py")
assert _spec and _spec.loader
eval_run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eval_run)

REQUIRED = {"id", "prompt", "expect"}
OPTIONAL = {"env", "server_args", "covers", "targets"}
COVERS = {"in_area", "relative_date", "misleading_field", "not_published"}


def _tasks(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text())


def _all_tasks() -> list[tuple[Path, dict[str, Any]]]:
    return [(path, task) for path in [CROSS, *PORTAL_FILES] for task in _tasks(path)]


def _ids(path: Path) -> list[str]:
    return [task["id"] for task in _tasks(path)]


def test_portal_files_are_named_for_pack_directories():
    packs = {p.name for p in SEATTLE.parent.iterdir() if (p / "portal.toml").exists()}
    assert PORTAL_FILES, "no evals/portals/*.json found"
    assert {p.stem for p in PORTAL_FILES} <= packs


def test_task_ids_unique_across_files():
    ids = [task["id"] for _, task in _all_tasks()]
    assert len(ids) == len(set(ids)), sorted({i for i in ids if ids.count(i) > 1})


def test_task_fields_allowed():
    for path, task in _all_tasks():
        keys = set(task)
        assert keys >= REQUIRED, (path.name, task.get("id"), REQUIRED - keys)
        assert keys <= REQUIRED | OPTIONAL, (path.name, task["id"], keys - REQUIRED - OPTIONAL)
        assert all(isinstance(task[k], str) and task[k] for k in REQUIRED), task["id"]
        env = task.get("env", {})
        assert isinstance(env, dict), task["id"]
        assert all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()), task["id"]
        for key in ("server_args", "covers"):
            value = task.get(key, [])
            assert isinstance(value, list), (task["id"], key)
            assert all(isinstance(v, str) for v in value), (task["id"], key)


def test_targets_shape():
    """`targets` names what an `in_area` or `relative_date` task's answer must use; those kinds
    require it (the tier check confirms each target is reviewed)."""
    for path, task in _all_tasks():
        covers = set(task.get("covers", []))
        targets = task.get("targets")
        if covers & {"in_area", "relative_date"}:
            assert isinstance(targets, dict), (path.name, task["id"], "needs targets")
        if targets is None:
            continue
        assert set(targets) <= {"dataset", "place", "time"}, (task["id"], set(targets))
        assert isinstance(targets.get("dataset"), str) and targets["dataset"], task["id"]
        if "in_area" in covers:
            place = targets.get("place")
            assert isinstance(place, list) and place, (task["id"], "in_area needs targets.place")
            assert all(isinstance(c, str) and c for c in place), task["id"]
        if "relative_date" in covers:
            assert isinstance(targets.get("time"), str), (task["id"], "relative_date needs time")


def test_covers_values_known():
    seen = [(task["id"], c) for _, task in _all_tasks() for c in task.get("covers", [])]
    assert seen, "no task declares covers"
    assert [(i, c) for i, c in seen if c not in COVERS] == []
    for _, task in _all_tasks():
        covers = task.get("covers", [])
        assert len(covers) == len(set(covers)), task["id"]


def test_server_args_paths_exist():
    checked = 0
    for _, task in _all_tasks():
        args = task.get("server_args", [])
        for flag, value in itertools.pairwise(args):
            if flag == "--validation":
                assert not Path(value).is_absolute(), task["id"]
                assert (ROOT / value).is_file(), (task["id"], value)
                checked += 1
    assert checked, "no task passes --validation"


def test_seattle_file_holds_the_seattle_tasks():
    ids = _ids(EVALS / "portals" / "data.seattle.gov.json")
    prefixes = [i.split("-", 1)[0] for i in ids]
    assert prefixes == [f"{n:02d}" for n in range(1, 25)] + ["27", "30"]
    assert "27-unreviewed-on-curated" in ids
    assert "30-stale-claim" in ids
    tasks = {
        t["id"].split("-", 1)[0]: t for t in _tasks(EVALS / "portals" / "data.seattle.gov.json")
    }
    covers = {n: t["covers"] for n, t in tasks.items() if "covers" in t}
    assert covers == {
        "03": ["in_area", "relative_date"],
        "04": ["not_published"],
        "14": ["misleading_field"],
        "24": ["not_published"],
    }
    assert tasks["30"]["server_args"] == ["--validation", "evals/fixtures/validation-stale.json"]


def test_cross_portal_file():
    ids = _ids(CROSS)
    assert [i.split("-", 1)[0] for i in ids] == ["25", "26", "28", "29", "31", "32"]
    assert "31-knowledge-gap-offer" in ids


def test_load_tasks_reads_the_portal_file_or_the_cross_portal_file():
    assert [t["id"] for t in eval_run.load_tasks(None)] == _ids(CROSS)
    assert [t["id"] for t in eval_run.load_tasks("data.seattle.gov")] == _ids(
        EVALS / "portals" / "data.seattle.gov.json"
    )
    with pytest.raises(SystemExit, match="no-such-portal"):
        eval_run.load_tasks("no-such-portal")


def _stale_claims() -> set[str]:
    ctx = load_portal(SEATTLE)
    today = date(2026, 10, 18)
    return {c.id for c in ctx.pack.claims if claim_validation(ctx, c, today) == "stale"}


def test_stale_fixture_marks_only_its_claim_stale():
    # Control: the shipped file has no stale claim on the pinned date.
    assert _stale_claims() == set()
    validation.set_override(STALE_FIXTURE)
    try:
        assert _stale_claims() == {"tazs-3rd5-sector-place"}
    finally:
        validation.set_override(None)
    assert _stale_claims() == set()


def test_set_override_replaces_the_cached_default(tmp_path: Path):
    shipped = validation.load_validation()
    empty = tmp_path / "empty.json"
    empty.write_text('{"portals": {}}\n')
    validation.set_override(empty)
    try:
        assert validation.load_validation() == validation.ValidationFile()
        # An explicit path still wins over the override.
        assert validation.load_validation(validation.VALIDATION_PATH) == shipped
    finally:
        validation.set_override(None)
    assert validation.load_validation() == shipped


def test_claude_command_restricts_tools(tmp_path: Path):
    task = next(t for t in eval_run.load_tasks("data.seattle.gov") if t["id"] == "30-stale-claim")
    capture = tmp_path / "30.capture.jsonl"
    args = eval_run.capture_args(task, capture)
    assert args[-len(task["server_args"]) :] == task["server_args"]
    assert str(capture) in args
    command = eval_run.claude_command(task, args, tmp_path)
    i = command.index("--tools")
    assert command[i + 1] == ""
    config = json.loads((tmp_path / f"{task['id']}.mcp.json").read_text())
    assert config["mcpServers"]["opendata-atlas"]["args"] == args
    # Only the eval's own config: no user plugins or connectors (ruling 61).
    assert command[command.index("--mcp-config") + 1] == str(tmp_path / f"{task['id']}.mcp.json")
    assert "--strict-mcp-config" in command
    assert list(config["mcpServers"]) == ["opendata-atlas"]
    # The Codex host gets the same server arguments.
    codex = eval_run.codex_command(task, args)
    assert f"mcp_servers.opendata_atlas.args={json.dumps(args)}" in codex


def test_eval_command_caps_spend(tmp_path: Path):
    """Ruling 74: each eval session is capped at $1 by the CLI itself."""
    task = {"id": "x", "prompt": "p", "expect": "e"}
    command = eval_run.claude_command(task, [], tmp_path)
    assert command.count("--max-budget-usd") == 1
    assert command[command.index("--max-budget-usd") + 1] == "1"


def test_capture_args_without_server_args(tmp_path: Path):
    task = {"id": "x", "prompt": "p", "expect": "e"}
    capture = tmp_path / "x.capture.jsonl"
    assert eval_run.capture_args(task, capture)[-1] == str(capture)


# --- argument parsing never launches a paid session by mistake (ruling 55) ----------


@pytest.fixture
def no_launch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Any session launch fails the test; the working directory is a scratch directory."""

    def launch(*args: Any, **kwargs: Any) -> Any:
        pytest.fail(f"evals/run.py launched a session: {args!r}")

    monkeypatch.setattr(eval_run, "claude_command", launch)
    monkeypatch.setattr(eval_run, "codex_command", launch)
    monkeypatch.setattr(eval_run.subprocess, "call", launch)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _main(monkeypatch: pytest.MonkeyPatch, *argv: str) -> int:
    monkeypatch.setattr(eval_run.sys, "argv", ["evals/run.py", *argv])
    with pytest.raises(SystemExit) as exc:
        eval_run.main()
    code = exc.value.code
    return 0 if code is None else code if isinstance(code, int) else 1


@pytest.mark.parametrize(
    "argv",
    [("--help",), ("-h",), ("--portal", "seattle", "--help"), ("out", "-h"), ("--help", "out")],
)
def test_help_prints_usage_and_exits_0(monkeypatch, capsys, no_launch, argv):
    assert _main(monkeypatch, *argv) == 0
    assert "Usage: python evals/run.py" in capsys.readouterr().out
    assert list(no_launch.iterdir()) == [], "help created no output directory"


@pytest.mark.parametrize(
    "argv",
    [
        ("--bogus", "out"),
        ("--portal", "seattle", "--bogus", "out"),
        ("out", "--bogus"),
        ("--portal", "seattle", "--host", "codex", "out"),
        (),
        ("--portal", "data.seattle.gov"),
        ("--host",),
        ("--host", "claude", "--portal"),
    ],
)
def test_bad_arguments_print_usage_and_exit_2(monkeypatch, capsys, no_launch, argv):
    assert _main(monkeypatch, *argv) == 2
    assert "Usage: python evals/run.py" in capsys.readouterr().err
    assert list(no_launch.iterdir()) == [], "a usage error created no output directory"


# --- session outcomes and tool isolation (#26, #27) ---------------------------------

_rspec = importlib.util.spec_from_file_location("eval_report", EVALS / "report.py")
assert _rspec is not None
assert _rspec.loader is not None
eval_report = importlib.util.module_from_spec(_rspec)
_rspec.loader.exec_module(eval_report)


def _fake_sessions(monkeypatch: pytest.MonkeyPatch, codes: dict[str, int]) -> list[Path]:
    """Every launch returns its task's code from `codes`; records each session's cwd."""
    cwds: list[Path] = []

    def call(command: list[str], **kwargs: Any) -> int:
        cwds.append(Path(kwargs["cwd"]))
        return next(code for task_id, code in codes.items() if f"prompt-{task_id}" in command)

    monkeypatch.setattr(eval_run.subprocess, "call", call)
    tasks = [{"id": i, "prompt": f"prompt-{i}", "expect": "e"} for i in codes]
    monkeypatch.setattr(eval_run, "load_tasks", lambda portal: tasks)
    return cwds


def test_a_failed_session_fails_the_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    _fake_sessions(monkeypatch, {"ok": 0, "bad": 17})
    assert _main(monkeypatch, str(tmp_path)) == 1


def test_all_sessions_ok_exits_0(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    _fake_sessions(monkeypatch, {"a": 0, "b": 0})
    monkeypatch.setattr(eval_run.sys, "argv", ["evals/run.py", str(tmp_path)])
    eval_run.main()


def test_codex_sessions_run_in_empty_directories(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "user-codex"))
    (tmp_path / "user-codex").mkdir()
    cwds = _fake_sessions(monkeypatch, {"a": 0, "b": 0})
    monkeypatch.setattr(eval_run.sys, "argv", ["evals/run.py", "--host", "codex", str(tmp_path)])
    eval_run.main()
    assert len(set(cwds)) == 2
    assert all(c.parent == tmp_path / "sessions" and not any(c.iterdir()) for c in cwds)


def test_codex_home_turns_off_built_in_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "user-codex"))
    (tmp_path / "user-codex").mkdir()
    config = tomllib.loads((eval_run.codex_home(tmp_path) / "config.toml").read_text())
    assert config["web_search"] == "disabled"
    for feature in ("apps", "shell_tool", "unified_exec", "browser_use", "computer_use"):
        assert config["features"][feature] is False


def _transcript(tmp_path: Path, events: list[dict[str, Any]]) -> Path:
    path = tmp_path / "t.transcript.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    return path


def _claude_tool(name: str) -> dict[str, Any]:
    block = {"type": "tool_use", "id": "1", "name": name, "input": {}}
    return {"type": "assistant", "message": {"content": [block]}}


def test_report_flags_a_claude_tool_that_is_not_the_servers(tmp_path: Path):
    events = [_claude_tool("mcp__opendata-atlas__atlas_find_portals"), _claude_tool("Bash")]
    s = eval_report.summarize(_transcript(tmp_path, events))
    assert [c[0] for c in s["calls"]] == ["atlas_find_portals"]
    assert s["foreign"] == ["Bash"]


def test_report_flags_codex_commands_and_other_servers(tmp_path: Path):
    def item(**kw: Any) -> dict[str, Any]:
        return {"type": "item.completed", "item": kw}

    events = [
        {"type": "thread.started"},
        item(type="reasoning", text="..."),
        item(type="mcp_tool_call", server="opendata_atlas", tool="atlas_find_portals"),
        item(type="mcp_tool_call", tool="atlas_query_dataset"),
        item(type="command_execution", command="cat evals/tasks.json"),
        item(type="mcp_tool_call", server="other", tool="x"),
        item(type="agent_message", text="answer"),
    ]
    s = eval_report.summarize(_transcript(tmp_path, events))
    assert [c[0] for c in s["calls"]] == ["atlas_find_portals", "atlas_query_dataset"]
    assert s["foreign"] == ["command_execution", "other"]
    assert s["answer"] == "answer"
