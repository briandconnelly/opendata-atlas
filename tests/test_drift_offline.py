"""The drift run offline: merge and prune rules, probe failures, and a recorded replay."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import pytest

from opendata_atlas.core.describe import served_evidence
from opendata_atlas.core.errors import AtlasError, ErrorCode
from opendata_atlas.core.http import SodaClient, get_client
from opendata_atlas.portals.drift import (
    AssertionResult,
    ClaimResult,
    asserted_claims,
    check_claim,
    merge_results,
    record_claim,
    report_json,
)
from opendata_atlas.portals.loader import PackError
from opendata_atlas.portals.model import (
    Claim,
    Document,
    ManualObservation,
    SoqlProbe,
)
from opendata_atlas.portals.validation import (
    ClaimCheck,
    ValidationFile,
    assertion_digest,
    load_validation,
    write_validation,
)
from tests.conftest import (
    _DRIFT_RESULTS,
    SEATTLE_CONTEXT,
    pytest_sessionfinish,
    write_drift_outputs,
    write_drift_report,
)

if TYPE_CHECKING:
    from opendata_atlas.portals.checkers import Outcome

TODAY = date(2026, 10, 18)
EARLIER = date(2026, 4, 1)


def _result(portal: str, claim: str, outcome: Outcome) -> ClaimResult:
    return ClaimResult(
        portal_id=portal,
        claim_id=claim,
        outcome=outcome,
        assertions=[
            AssertionResult(
                checker="dst_gap", probe=0, outcome=outcome, detail="d", request="SELECT 1"
            )
        ],
    )


def _old(**claims: str) -> ValidationFile:
    return ValidationFile(
        portals={
            "p.example": {
                cid: ClaimCheck(checked_at=EARLIER, outcome=o)  # ty: ignore[invalid-argument-type]
                for cid, o in claims.items()
            }
        }
    )


def test_merge_moves_outcome_to_previous(tmp_path):
    old = _old(a="passed", b="inconclusive")
    results = [_result("p.example", "a", "contradicted"), _result("p.example", "b", "passed")]
    merged = merge_results(old, results, TODAY, {"p.example": {"a", "b"}})
    a, b = merged.portals["p.example"]["a"], merged.portals["p.example"]["b"]
    assert (a.checked_at, a.outcome, a.previous_outcome) == (TODAY, "contradicted", "passed")
    assert (b.outcome, b.previous_outcome) == ("passed", "inconclusive")
    # The writer surfaces a failure: the contradicted outcome survives the round trip.
    path = tmp_path / "validation.json"
    write_validation(merged, path)
    text = path.read_text()
    assert text.endswith("}\n")
    assert json.loads(text)["portals"]["p.example"]["a"]["outcome"] == "contradicted"
    assert load_validation(path) == merged


def test_merge_records_the_checked_assertion_digest():
    """Final review M-3: the gate compares this digest with the pack's current assertion."""
    result = _result("p.example", "a", "passed")
    result.digest = "0123456789ab"
    old = ValidationFile(
        portals={
            "p.example": {
                "a": ClaimCheck(checked_at=EARLIER, outcome="passed", assertion_digest="old"),
                "b": ClaimCheck(checked_at=EARLIER, outcome="passed", assertion_digest="kept"),
            }
        }
    )
    merged = merge_results(old, [result], TODAY, {"p.example": {"a", "b"}})
    assert merged.portals["p.example"]["a"].assertion_digest == "0123456789ab"
    assert merged.portals["p.example"]["b"].assertion_digest == "kept", "unchecked keeps its own"


def test_merge_gives_a_new_claim_no_previous_outcome():
    merged = merge_results(ValidationFile(), [_result("p.example", "a", "passed")], TODAY, {})
    assert merged.portals["p.example"]["a"].previous_outcome is None


def test_merge_keeps_unrun_live_claims():
    old = _old(a="passed", b="inconclusive")
    merged = merge_results(
        old, [_result("p.example", "a", "passed")], TODAY, {"p.example": {"a", "b"}}
    )
    assert merged.portals["p.example"]["b"] == old.portals["p.example"]["b"]


def test_merge_drops_claims_no_longer_in_packs():
    """Review Focus 3: a removed or renamed claim's old entry goes at the next merge of its
    portal."""
    old = _old(a="passed", b="passed", renamed="passed")
    merged = merge_results(
        old, [_result("p.example", "a", "passed")], TODAY, {"p.example": {"a", "b"}}
    )
    assert set(merged.portals["p.example"]) == {"a", "b"}


def test_scoped_run_leaves_other_portals_byte_identical(tmp_path):
    """Final review M-6: a run with results for one portal (a curator's `-k` run) never edits
    another portal's entries, not even to prune its orphans."""
    other = {
        "x": ClaimCheck(checked_at=EARLIER, outcome="passed", assertion_digest="0123456789ab"),
        "orphan": ClaimCheck(checked_at=EARLIER, outcome="inconclusive"),
    }
    old = ValidationFile(portals={**_old(a="passed", gone="passed").portals, "q.example": other})
    live = {"p.example": {"a"}, "q.example": {"x"}}
    merged = merge_results(old, [_result("p.example", "a", "contradicted")], TODAY, live)
    assert set(merged.portals["p.example"]) == {"a"}, "the run's own portal is still pruned"
    before, after = tmp_path / "before.json", tmp_path / "after.json"
    write_validation(ValidationFile(portals={"q.example": old.portals["q.example"]}), before)
    write_validation(ValidationFile(portals={"q.example": merged.portals["q.example"]}), after)
    assert after.read_bytes() == before.read_bytes()


def test_session_writer_records_a_contradicted_result(tmp_path):
    """The conftest hook's writer, on a synthetic failure: it lands in both files."""
    validation, report = tmp_path / "validation.json", tmp_path / "report.json"
    results = [_result("p.example", "a", "contradicted")]
    write_drift_report(results, report)
    write_drift_outputs(results, validation, live={}, today=TODAY)
    entry = json.loads(validation.read_text())["portals"]["p.example"]["a"]
    assert entry == {
        "checked_at": TODAY.isoformat(),
        "outcome": "contradicted",
        "previous_outcome": None,
        "assertion_digest": None,
    }
    body = json.loads(report.read_text())
    assert body["results"][0]["outcome"] == "contradicted"
    assert body["results"][0]["assertions"][0]["request"] == "SELECT 1"


def _probe_claim() -> Claim:
    return Claim.model_validate(
        {
            "id": "test-tz",
            "kind": "column_timezone",
            "scope": {"dataset": "abcd-1234", "column": "t"},
            "evidence": [
                {
                    "kind": "soql_probe",
                    "query": "SELECT 1",
                    "observed_at": TODAY,
                    "observation": "o",
                },
                {
                    "kind": "metadata_probe",
                    "path": "/api/views/abcd-1234.json",
                    "observed_at": TODAY,
                    "observation": "o",
                },
            ],
            "assertion": [
                {"checker": "dst_gap", "probe": 0},
                {"checker": "diurnal_peak", "probe": 0, "params": {"peak_from": 1, "peak_to": 3}},
                {
                    "checker": "metadata_equals",
                    "probe": 1,
                    "params": {"field": "id", "value": "abcd-1234"},
                },
            ],
        }
    )


async def test_probe_failure_is_inconclusive():
    """Review Focus 1: a 503 makes that probe's assertions inconclusive, never passed."""
    seen: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if "/resource/" in request.url.path:
            return httpx.Response(503, json={"message": "down"})
        return httpx.Response(200, json={"id": "abcd-1234"})

    client = SodaClient(transport=httpx.MockTransport(answer))
    try:
        result = await check_claim(client, SEATTLE_CONTEXT, _probe_claim())
    finally:
        await client.aclose()
    assert result.outcome == "inconclusive"
    soql = [a for a in result.assertions if a.probe == 0]
    assert [a.outcome for a in soql] == ["inconclusive", "inconclusive"]
    assert all("upstream_unavailable" in a.detail for a in soql)
    assert soql[0].request == "SELECT 1"
    meta = next(a for a in result.assertions if a.probe == 1)
    assert (meta.outcome, meta.request) == ("passed", "/api/views/abcd-1234.json")
    # Each named probe ran once, on the portal's public host.
    assert len(seen) == 2
    assert seen[0].startswith("https://data.seattle.gov/resource/abcd-1234.json?")
    assert seen[1] == "https://data.seattle.gov/api/views/abcd-1234.json"


@pytest.mark.parametrize("metadata", [False, True])
@pytest.mark.parametrize(
    ("failures", "attempts", "outcome", "detail"),
    [
        ([(ErrorCode.QUERY_TIMEOUT, True)], 2, "passed", None),
        ([(ErrorCode.QUERY_TIMEOUT, True)] * 2, 2, "inconclusive", "query_timeout"),
        ([(ErrorCode.QUERY_TIMEOUT, False)], 1, "inconclusive", "query_timeout"),
        ([(ErrorCode.UPSTREAM_UNAVAILABLE, True)], 1, "inconclusive", "upstream_unavailable"),
        ([(ErrorCode.RATE_LIMITED, True)], 1, "inconclusive", "rate_limited"),
        (
            [(ErrorCode.QUERY_TIMEOUT, True), (ErrorCode.DATASET_NOT_FOUND, False)],
            2,
            "inconclusive",
            "dataset_not_found",
        ),
    ],
)
async def test_probe_retries_only_temporary_query_timeout(
    metadata, failures, attempts, outcome, detail
):
    seen = []

    def answer(request: httpx.Request) -> httpx.Response:
        is_metadata = "/api/views/" in request.url.path
        if is_metadata == metadata:
            seen.append(str(request.url))
            if len(seen) <= len(failures):
                code, temporary = failures[len(seen) - 1]
                raise AtlasError(code, "synthetic failure", temporary=temporary)
        body = (
            {"id": "abcd-1234"}
            if is_metadata
            else [{"h": str(h), "n": "200" if h == 1 else "10"} for h in range(24) if h != 2]
        )
        return httpx.Response(200, json=body)

    client = SodaClient(transport=httpx.MockTransport(answer))
    try:
        result = await check_claim(client, SEATTLE_CONTEXT, _probe_claim())
    finally:
        await client.aclose()
    assert len(seen) == attempts
    assert len(set(seen)) == 1, "retry must replay the same probe, shared by its assertions"
    assert result.outcome == outcome
    affected = [a for a in result.assertions if a.probe == int(metadata)]
    assert all(a.outcome == outcome for a in affected)
    if detail:
        assert all(a.detail == detail for a in affected)


def test_report_json_shape():
    body = report_json([_result("p.example", "a", "passed")])
    assert set(body) == {"generated_at", "results"}
    assert body["results"] == [
        {
            "portal": "p.example",
            "claim": "a",
            "outcome": "passed",
            "assertions": [
                {
                    "checker": "dst_gap",
                    "probe": 0,
                    "outcome": "passed",
                    "detail": "d",
                    "request": "SELECT 1",
                }
            ],
        }
    ]


def test_missing_validation_file_is_empty(tmp_path, caplog):
    with caplog.at_level("WARNING"):
        assert load_validation(tmp_path / "absent.json") == ValidationFile()
    assert caplog.records == [], "an explicit path keeps its silent empty read"


def test_missing_shipped_validation_file_warns(tmp_path, monkeypatch, caplog):
    """Final review M-2: a missing shipped file disables freshness, so it is logged."""
    from opendata_atlas.portals import validation

    monkeypatch.setattr(validation, "VALIDATION_PATH", tmp_path / "validation.json")
    validation._default.cache_clear()
    with caplog.at_level("WARNING"):
        assert load_validation() == ValidationFile()
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    assert "validation.json" in warnings[0].getMessage()
    assert "freshness" in warnings[0].getMessage()


@pytest.mark.parametrize("body", ["{not json", '{"portals": {"p": {"c": {"outcome": "ok"}}}}'])
def test_malformed_validation_file_names_it(tmp_path, body):
    path = tmp_path / "validation.json"
    path.write_text(body)
    with pytest.raises(PackError, match=r"validation\.json"):
        load_validation(path)


def test_served_evidence_prefers_the_manual_note():
    probe = SoqlProbe(kind="soql_probe", query="q", observed_at=TODAY, observation="probed")
    note = ManualObservation(kind="manual_observation", note="noted", observed_at=TODAY)
    doc = Document(kind="document", url="https://example.org", quote="quoted", observed_at=TODAY)
    assert served_evidence([probe, doc, note]) == "noted"
    assert served_evidence([doc, probe]) == "probed"
    assert served_evidence([doc]) == "quoted"


def test_asserted_claims_skips_directories_without_a_portal(tmp_path):
    (tmp_path / "no-portal").mkdir()
    assert asserted_claims(tmp_path) == []


SEATTLE_ASSERTED = [c for p, c in asserted_claims() if p.id == "data.seattle.gov"]


@pytest.mark.soda_fixture("drift_seattle")
async def test_check_claim_replays_recorded_probes(soda):
    # Count-independent: a claim whose probe the fixture lacks fails as an unrecorded request.
    assert SEATTLE_ASSERTED, "the Seattle pack has asserted claims"
    client = get_client()
    results = [await check_claim(client, SEATTLE_CONTEXT, c) for c in SEATTLE_ASSERTED]
    assert {r.claim_id: r.outcome for r in results} == {c.id: "passed" for c in SEATTLE_ASSERTED}
    # Final review M-3: each result carries the digest of the assertions it checked.
    assert [r.digest for r in results] == [assertion_digest(c) for c in SEATTLE_ASSERTED]


async def test_a_raising_case_is_recorded_inconclusive(monkeypatch):
    """Ruling 41 (1): an unexpected error still leaves an inconclusive result for the merge."""

    async def boom(client, portal, claim):
        raise TypeError("checker bug")

    monkeypatch.setattr("opendata_atlas.portals.drift.check_claim", boom)
    results: list[ClaimResult] = []
    claim = _probe_claim()
    with pytest.raises(TypeError, match="checker bug"):
        await record_claim(object(), SEATTLE_CONTEXT, claim, results)  # ty: ignore[invalid-argument-type]
    assert [(r.portal_id, r.claim_id, r.outcome) for r in results] == [
        (SEATTLE_CONTEXT.id, claim.id, "inconclusive")
    ]
    assert "TypeError" in results[0].assertions[0].detail
    # The recorded result is not a pass, so the merge cannot keep an old `passed` as current.
    old = ValidationFile(
        portals={SEATTLE_CONTEXT.id: {claim.id: ClaimCheck(checked_at=EARLIER, outcome="passed")}}
    )
    merged = merge_results(old, results, TODAY, {SEATTLE_CONTEXT.id: {claim.id}})
    entry = merged.portals[SEATTLE_CONTEXT.id][claim.id]
    assert (entry.outcome, entry.previous_outcome) == ("inconclusive", "passed")
    assert entry.assertion_digest == assertion_digest(claim)


async def test_a_clean_case_is_recorded_as_checked(monkeypatch):
    sentinel = _result("p.example", "a", "passed")

    async def fine(client, portal, claim):
        return sentinel

    monkeypatch.setattr("opendata_atlas.portals.drift.check_claim", fine)
    results: list[ClaimResult] = []
    await record_claim(object(), SEATTLE_CONTEXT, _probe_claim(), results)  # ty: ignore[invalid-argument-type]
    assert results == [sentinel]


def test_a_malformed_validation_file_keeps_the_report(tmp_path):
    """Ruling 41 (2): the report does not depend on the old file, so it is written regardless."""
    validation, report = tmp_path / "validation.json", tmp_path / "report.json"
    validation.write_text("{not json")
    results = [_result("p.example", "a", "contradicted")]
    write_drift_report(results, report)
    with pytest.raises(PackError, match=r"validation\.json"):
        write_drift_outputs(results, validation, live={}, today=TODAY)
    assert json.loads(report.read_text())["results"][0]["outcome"] == "contradicted"
    assert validation.read_text() == "{not json"


def _session(report, results):
    from types import SimpleNamespace

    stash = {_DRIFT_RESULTS: results}
    config = SimpleNamespace(stash=stash, getoption=lambda name: str(report))
    return SimpleNamespace(config=config)


def test_session_finish_writes_the_report_when_the_file_is_bad(tmp_path, monkeypatch):
    validation, report = tmp_path / "validation.json", tmp_path / "report.json"
    validation.write_text("{not json")
    monkeypatch.setattr("tests.conftest.VALIDATION_PATH", validation)
    monkeypatch.setattr("tests.conftest.asserted_claims", list)
    session = _session(report, [_result("p.example", "a", "passed")])
    with pytest.raises(PackError, match=r"validation\.json"):
        pytest_sessionfinish(session, 1)
    assert json.loads(report.read_text())["results"][0]["claim"] == "a"


def test_session_finish_writes_the_report_when_a_pack_fails(tmp_path, monkeypatch):
    report = tmp_path / "report.json"

    def broken():
        raise PackError("portals/x/portal.toml: <toml>: bad")

    monkeypatch.setattr("tests.conftest.asserted_claims", broken)
    monkeypatch.setattr("tests.conftest.VALIDATION_PATH", tmp_path / "validation.json")
    session = _session(report, [_result("p.example", "a", "passed")])
    with pytest.raises(PackError, match=r"portal\.toml"):
        pytest_sessionfinish(session, 1)
    assert json.loads(report.read_text())["results"][0]["claim"] == "a"
    assert not (tmp_path / "validation.json").exists()


def test_write_validation_goes_through_a_sibling_temp_file(tmp_path, monkeypatch):
    """Ruling 41 (3): the target is replaced whole, never half-written."""
    path = tmp_path / "validation.json"
    write_validation(_old(a="passed"), path)
    before = path.read_text()
    replaced: list[tuple[Path, str]] = []
    real_replace = Path.replace

    def spy(self, target):
        replaced.append((self, self.read_text()))
        assert path.read_text() == before  # the target is untouched until the swap
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", spy)
    write_validation(_old(a="contradicted"), path)
    [(temp, body)] = replaced
    assert temp.parent == path.parent and temp != path
    assert json.loads(body)["portals"]["p.example"]["a"]["outcome"] == "contradicted"
    assert not temp.exists()
    assert json.loads(path.read_text())["portals"]["p.example"]["a"]["outcome"] == "contradicted"


def test_a_failed_swap_leaves_the_old_file_and_no_temp(tmp_path, monkeypatch):
    path = tmp_path / "validation.json"
    write_validation(_old(a="passed"), path)
    before = path.read_text()

    def fail(self, target):
        raise OSError("disk gone")

    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(OSError, match="disk gone"):
        write_validation(_old(a="contradicted"), path)
    assert path.read_text() == before
    assert [p.name for p in tmp_path.iterdir()] == ["validation.json"]
