"""Run eval tasks headless in Claude Code or Codex against the capture server.

Usage: python evals/run.py [--host claude|codex] [--portal NAME] <out_dir> [task_id ...]
       python evals/run.py --help
Each task is one paid headless agent session. `--help` (or `-h`) prints this and runs nothing;
an unknown option or a missing <out_dir> exits 2 and runs nothing.
`--portal NAME` runs `evals/portals/NAME.json` (NAME is the pack directory name, e.g. `seattle`);
without it, the cross-portal tasks in `evals/tasks.json` run.
A task's optional `server_args` are appended to the capture server's arguments.
Claude runs with `--tools ""`, which removes every built-in tool so the agent can only call the
server's MCP tools (`--allowedTools` alone pre-approves tools but does not restrict the agent).
Codex runs with a clean CODEX_HOME that turns off apps, web search, the shell tool, browser,
computer use and image viewing, in an empty working directory. `unified_exec` stays on whatever
the config says (`codex features list`, codex-cli 0.164.0), so Codex can still run commands:
`evals/report.py` flags any call that is not one of the server's tools, and such a run is not
evidence.
Claude sessions are capped at $1 each with `--max-budget-usd`. Codex sessions are not capped:
`codex exec` has no budget option.
Writes <id>.transcript.jsonl (the host's JSON event stream), <id>.capture.jsonl (server view),
and <id>.stderr.txt. Exits 1 when any session exits nonzero. Exits 2, before any session, when
<out_dir> already holds a transcript for a task it would run: each run needs a new <out_dir>.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ",".join(
    f"mcp__opendata-atlas__atlas_{name}"
    for name in (
        "find_portals",
        "search_datasets",
        "describe_dataset",
        "query_dataset",
        "get_reference",
    )
)


#: Built-in Codex tools a session must not use. `unified_exec` is listed although
#: codex-cli 0.164.0 keeps it on, so a later CLI that honors it closes the gap.
CODEX_FEATURES_OFF = (
    "apps",
    "shell_tool",
    "unified_exec",
    "browser_use",
    "in_app_browser",
    "computer_use",
    "view_image",
)


# Ruling 74: the CLI enforces this per-session cap; the milestone's cost gate relies on it.
EVAL_BUDGET_USD = 1


def load_tasks(portal: str | None) -> list[dict]:
    """The tasks in `evals/portals/<portal>.json`, or in `evals/tasks.json` when None."""
    path = ROOT / "evals" / ("tasks.json" if portal is None else f"portals/{portal}.json")
    if not path.is_file():
        sys.exit(f"no eval task file for portal {portal!r}: {path.relative_to(ROOT)}")
    return json.loads(path.read_text())


def capture_args(task: dict, capture: Path) -> list[str]:
    """`uv` arguments that run the capture server, with the task's `server_args` appended.

    `uv run --directory ROOT` runs from ROOT, so relative paths in `server_args` are
    repository paths.
    """
    return [
        "run",
        "--directory",
        str(ROOT),
        "python",
        "scripts/capture_server.py",
        str(capture),
        *task.get("server_args", []),
    ]


def run(task: dict, out: Path, host: str) -> int:
    """One session; returns the host's exit code."""
    capture = out / f"{task['id']}.capture.jsonl"
    capture.unlink(missing_ok=True)
    args = capture_args(task, capture)
    command = codex_command(task, args) if host == "codex" else claude_command(task, args, out)
    env = {**os.environ, "CODEX_HOME": str(codex_home(out))} if host == "codex" else os.environ
    with (
        (out / f"{task['id']}.transcript.jsonl").open("w") as stdout,
        (out / f"{task['id']}.stderr.txt").open("w") as stderr,
    ):
        code = subprocess.call(
            command,
            cwd=session_dir(out, task) if host == "codex" else out,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            env=env,
        )
    print(f"{task['id']}: exit {code}", flush=True)
    return code


def session_dir(out: Path, task: dict) -> Path:
    """An empty working directory, so a session that can run commands has no pointer to the
    other tasks' transcripts in `out`."""
    path = out / "sessions" / task["id"]
    path.mkdir(parents=True, exist_ok=True)
    return path


def claude_command(task: dict, args: list[str], out: Path) -> list[str]:
    config = out / f"{task['id']}.mcp.json"
    server = {"command": "uv", "args": args, "env": task.get("env", {})}
    config.write_text(json.dumps({"mcpServers": {"opendata-atlas": server}}))
    return [
        "claude",
        "-p",
        task["prompt"],
        "--mcp-config",
        str(config),
        "--strict-mcp-config",
        "--tools",
        "",
        "--allowedTools",
        TOOLS,
        "--max-turns",
        "20",
        "--max-budget-usd",
        str(EVAL_BUDGET_USD),
        "--output-format",
        "stream-json",
        "--verbose",
    ]


def codex_home(out: Path) -> Path:
    """A clean CODEX_HOME: the user's login and model, but none of their MCP servers, apps,
    hooks or web search, and the built-in tools that config can turn off turned off."""
    home = out / "codex-home"
    home.mkdir(exist_ok=True)
    user = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    auth = home / "auth.json"
    if not auth.is_symlink():
        auth.symlink_to(user / "auth.json")
    settings = (
        tomllib.loads((user / "config.toml").read_text()) if (user / "config.toml").exists() else {}
    )
    lines = [
        f"{key} = {json.dumps(settings[key])}"
        for key in ("model", "model_reasoning_effort")
        if key in settings
    ]
    lines += ['web_search = "disabled"', "", "[features]"]
    lines += [f"{feature} = false" for feature in CODEX_FEATURES_OFF]
    (home / "config.toml").write_text("\n".join(lines) + "\n")
    return home


def codex_command(task: dict, args: list[str]) -> list[str]:
    # Codex takes MCP servers as TOML config overrides; JSON strings and arrays are valid TOML.
    overrides = [
        'mcp_servers.opendata_atlas.command="uv"',
        f"mcp_servers.opendata_atlas.args={json.dumps(args)}",
    ]
    for key, value in task.get("env", {}).items():
        overrides.append(f"mcp_servers.opendata_atlas.env.{key}={json.dumps(value)}")
    command = [
        "codex",
        "exec",
        "--skip-git-repo-check",
        "-s",
        "read-only",
        "-c",
        'approval_policy="never"',
    ]
    for override in overrides:
        command += ["-c", override]
    return [*command, "--json", task["prompt"]]


def usage_error(message: str) -> None:
    """Print `message` and the usage to stderr and exit 2; never launches a session."""
    print(f"evals/run.py: {message}\n{__doc__}", file=sys.stderr)
    sys.exit(2)


def parse_args(argv: list[str]) -> tuple[str, str | None, Path, list[str]]:
    """(host, portal, out_dir, task ids). `--help`/`-h` anywhere prints usage and exits 0;
    any other flag, a flag out of its documented position, or no `<out_dir>` exits 2."""
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        sys.exit(0)
    host, portal = "claude", None
    for flag in ("--host", "--portal"):
        if argv[:1] == [flag]:
            if len(argv) < 2 or argv[1].startswith("-"):
                usage_error(f"{flag} needs a value")
            value, argv = argv[1], argv[2:]
            if flag == "--host":
                host = value
            else:
                portal = value
    stray = [a for a in argv if a.startswith("-")]
    if stray:
        usage_error(f"unknown or misplaced option {stray[0]!r}")
    if host not in ("claude", "codex"):
        usage_error(f"unknown host {host!r}; use claude or codex")
    if not argv:
        usage_error("missing <out_dir>")
    return host, portal, Path(argv[0]).resolve(), argv[1:]


def main() -> None:
    host, portal, out, ids = parse_args(sys.argv[1:])
    tasks = load_tasks(portal)
    wanted = set(ids)
    unknown = sorted(wanted - {task["id"] for task in tasks})
    if unknown:
        sys.exit(f"unknown task ids for this file: {unknown}")
    selected = [task for task in tasks if not wanted or task["id"] in wanted]
    existing = [t["id"] for t in selected if (out / f"{t['id']}.transcript.jsonl").exists()]
    if existing:
        print(
            f"evals/run.py: {out} already holds transcripts for {', '.join(existing)}; "
            "use a new <out_dir> so an earlier run's evidence is kept",
            file=sys.stderr,
        )
        sys.exit(2)
    out.mkdir(parents=True, exist_ok=True)
    failed = [task["id"] for task in selected if run(task, out, host) != 0]
    if failed:
        sys.exit(f"sessions exited nonzero: {', '.join(failed)}")


if __name__ == "__main__":
    main()
