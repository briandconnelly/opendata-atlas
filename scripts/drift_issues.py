"""Turn a drift report into one GitHub issue body per portal with a failing claim.

    uv run python scripts/drift_issues.py drift-report.json --out drift-issues

Writes `<out>/<portal id>.md` for each portal with a `contradicted` or `inconclusive` claim, and
`<out>/titles.tsv` (`portal id<TAB>title`). A report that is missing or unreadable means the run
failed before any claim ran (a pack that fails to load at collection, say): then the one issue
is `Drift: run failed`, in `<out>/drift-run.md`, linking `--run-url` when given.
`.github/workflows/drift.yml` opens or updates the issues from those files. docs/design.md:
Drift checks.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

FAILING = ("contradicted", "inconclusive")
FOOTER = "Re-probe, then correct or remove the claim (docs/design.md: Release gate)."
#: The issue file key for a run that produced no readable report; no portal id lacks a dot.
RUN_FAILED = "drift-run"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _request_cell(request: str) -> str:
    """The request as a code span; an em dash when the failure had no request."""
    return _cell(f"`{request}`") if request else "\u2014"


def _rows(result: dict[str, Any]) -> list[str]:
    """One row per assertion that did not pass; the claim's own row when none is listed."""
    claim = _cell(f"`{result['claim']}`")
    failed = [a for a in result["assertions"] if a["outcome"] != "passed"]
    if not failed:
        return [f"| {claim} | {result['outcome']} |  |  |  |"]
    return [
        f"| {claim} | {a['outcome']} | {a['checker']} | {_request_cell(a['request'])} "
        f"| {_cell(a['detail'])} |"
        for a in failed
    ]


def issue_bodies(report: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """Portal id to (title, Markdown body), for portals with a failing claim only."""
    by_portal: dict[str, list[dict[str, Any]]] = {}
    for result in report["results"]:
        if result["outcome"] in FAILING:
            by_portal.setdefault(result["portal"], []).append(result)
    bodies: dict[str, tuple[str, str]] = {}
    for portal_id in sorted(by_portal):
        lines = [
            f"The drift run of {report['generated_at']} found claims that no longer hold, "
            f"or that it could not check, on {portal_id}.",
            "",
            "| claim | outcome | checker | request | detail |",
            "| --- | --- | --- | --- | --- |",
        ]
        for result in by_portal[portal_id]:
            lines.extend(_rows(result))
        lines += ["", FOOTER, ""]
        bodies[portal_id] = (f"Drift: {portal_id}", "\n".join(lines))
    return bodies


def run_failed_body(report: Path, problem: str, run_url: str | None) -> tuple[str, str]:
    """The issue for a drift run that left no readable report: no claim's outcome is known."""
    log = f"See the job log: {run_url}" if run_url else "See the workflow's job log."
    lines = [
        f"The drift run failed before any claim was checked: it left no report "
        f"(`{report}`: {problem}). No claim's outcome is known from this run.",
        "",
        log,
        "",
        "A collection error, such as a pack that fails to load, is the usual cause.",
        "",
    ]
    return "Drift: run failed", "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])  # ty: ignore[possibly-missing-attribute]
    parser.add_argument("report", type=Path, help="the --drift-report JSON")
    parser.add_argument("--out", type=Path, required=True, help="directory for the issue files")
    parser.add_argument("--run-url", help="the workflow run, linked from a run-failed issue")
    args = parser.parse_args(argv)
    try:
        bodies = issue_bodies(json.loads(args.report.read_text()))
    except FileNotFoundError:
        bodies = {RUN_FAILED: run_failed_body(args.report, "file not found", args.run_url)}
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        problem = f"unreadable report, {type(e).__name__}"
        bodies = {RUN_FAILED: run_failed_body(args.report, problem, args.run_url)}
    args.out.mkdir(parents=True, exist_ok=True)
    for portal_id, (_, body) in bodies.items():
        (args.out / f"{portal_id}.md").write_text(body)
    titles = "".join(f"{portal_id}\t{title}\n" for portal_id, (title, _) in bodies.items())
    (args.out / "titles.tsv").write_text(titles)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
