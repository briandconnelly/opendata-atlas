"""scripts/drift_issues.py: one issue body per portal with a failing claim."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

SCRIPT = Path(__file__).parent.parent / "scripts" / "drift_issues.py"
_spec = importlib.util.spec_from_file_location("drift_issues", SCRIPT)
assert _spec and _spec.loader
drift_issues = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(drift_issues)


def _assertion(outcome: str, detail: str = "d", request: str = "SELECT 1") -> dict[str, Any]:
    return {
        "checker": "dst_gap",
        "probe": 0,
        "outcome": outcome,
        "detail": detail,
        "request": request,
    }


def _claim(portal: str, claim: str, outcome: str, *assertions: dict[str, Any]) -> dict[str, Any]:
    return {"portal": portal, "claim": claim, "outcome": outcome, "assertions": list(assertions)}


REPORT = {
    "generated_at": "2026-10-18T00:00:00+00:00",
    "results": [
        _claim("ok.example", "fine", "passed", _assertion("passed")),
        _claim(
            "bad.example",
            "wrong",
            "contradicted",
            _assertion("passed", "fine here", "SELECT fine"),
            _assertion("contradicted", "2 rows at hour 2 | expected 0", "SELECT count(*) AS n"),
        ),
        _claim(
            "bad.example",
            "unsure",
            "inconclusive",
            _assertion("inconclusive", "upstream_unavailable"),
        ),
        _claim("also-ok.example", "fine", "passed", _assertion("passed")),
    ],
}


def test_only_failing_portals_get_issues():
    bodies = drift_issues.issue_bodies(REPORT)
    assert list(bodies) == ["bad.example"]
    title, _ = bodies["bad.example"]
    assert title == "Drift: bad.example"


def test_body_lists_query_and_observed_result():
    _, body = drift_issues.issue_bodies(REPORT)["bad.example"]
    assert "| claim | outcome | checker | request | detail |" in body
    assert "SELECT count(*) AS n" in body
    # A pipe in a cell would split the row.
    assert "2 rows at hour 2 \\| expected 0" in body
    assert "upstream_unavailable" in body
    assert "wrong" in body and "unsure" in body
    # An assertion that held is not the problem.
    assert "SELECT fine" not in body
    assert body.rstrip().endswith(
        "Re-probe, then correct or remove the claim (docs/design.md: Release gate)."
    )
    for line in body.splitlines():
        if line.startswith("|"):
            assert line.count("|") - line.count("\\|") == 6, line


def test_passing_report_gives_no_issues():
    report = {"generated_at": "x", "results": [_claim("a", "b", "passed", _assertion("passed"))]}
    assert drift_issues.issue_bodies(report) == {}


def test_titles_tsv_written(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(json.dumps(REPORT))
    out = tmp_path / "out"
    assert drift_issues.main([str(report), "--out", str(out)]) == 0
    assert (out / "titles.tsv").read_text() == "bad.example\tDrift: bad.example\n"
    assert "wrong" in (out / "bad.example.md").read_text()
    assert sorted(p.name for p in out.iterdir()) == ["bad.example.md", "titles.tsv"]


def test_clean_report_writes_an_empty_titles_file(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"generated_at": "x", "results": []}))
    assert drift_issues.main([str(report), "--out", str(tmp_path / "out")]) == 0
    assert (tmp_path / "out" / "titles.tsv").read_text() == ""


def test_a_failure_without_a_request_renders_a_dash():
    """`record_claim`'s synthetic result has no request; an empty code span would look broken."""
    report = {
        "generated_at": "x",
        "results": [
            _claim("p.example", "c", "inconclusive", _assertion("inconclusive", "TypeError: x", ""))
        ],
    }
    _, body = drift_issues.issue_bodies(report)["p.example"]
    assert "``" not in body
    assert "| \u2014 | TypeError: x |" in body


RUN_URL = "https://github.com/o/r/actions/runs/1"


def test_a_missing_report_opens_a_run_failed_issue(tmp_path):
    """Final review M-8: a run that fails before any claim (no report) still reports."""
    out = tmp_path / "out"
    args = [str(tmp_path / "absent.json"), "--out", str(out), "--run-url", RUN_URL]
    assert drift_issues.main(args) == 0
    key, title = (out / "titles.tsv").read_text().rstrip("\n").split("\t")
    assert title == "Drift: run failed"
    body = (out / f"{key}.md").read_text()
    assert "failed before" in body and "no report" in body
    assert RUN_URL in body


def test_an_unreadable_report_opens_a_run_failed_issue(tmp_path):
    report = tmp_path / "report.json"
    report.write_text("{truncated")
    out = tmp_path / "out"
    assert drift_issues.main([str(report), "--out", str(out)]) == 0
    assert (out / "titles.tsv").read_text().endswith("\tDrift: run failed\n")
