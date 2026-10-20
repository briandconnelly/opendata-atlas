"""The atlas-profile draft-pack profiler, offline against a synthetic portal."""

from __future__ import annotations

import json
import tomllib
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

import anyio
import httpx
import pytest

from opendata_atlas.core.http import SodaClient
from opendata_atlas.portals.checkers import run_check
from opendata_atlas.portals.loader import load_portal
from opendata_atlas.portals.model import PortalIdentity, SoqlProbe
from opendata_atlas.portals.registry import Registry, RegistryEntry
from opendata_atlas.portals.validation import ValidationFile
from opendata_atlas.profiler import cli
from opendata_atlas.profiler.emit import pack_files, render_claims
from opendata_atlas.profiler.profile import (
    flagships,
    gap_hour,
    identity_verified,
    observe_text,
    profile_portal,
    spring_forward,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from opendata_atlas.portals.model import Claim

TODAY = date(2026, 10, 18)
HOST = "data.example.gov"
DATASET = "abcd-1234"
EMPTY = "zzzz-0000"
REGION_COL = ":@computed_region_ab12_cd34"
LAYER = "ab12-cd34"
DISCOVERY = "api.us.socrata.com"


def _entry(timezone: str | None = "America/Los_Angeles") -> RegistryEntry:
    return RegistryEntry(
        identity=PortalIdentity(
            id=HOST,
            public_host=HOST,
            catalog_query={"domains": HOST},
            catalog_region="us",
            name="Example City",
            timezone=timezone,
            platform="socrata",
            status="active",
            tier="generic",
        )
    )


def _hours(counts: dict[int, int]) -> list[dict[str, str]]:
    return [{"h": str(h), "n": str(n)} for h, n in sorted(counts.items())]


#: Hourly counts on 2026-03-08: hour 2 is empty, as on a wall-clock spring-forward day.
GAP_DAY = _hours({h: 5 for h in range(24) if h != 2})
#: A year of hourly counts peaking at 17.
YEAR = _hours({h: (100 if h == 17 else 10) for h in range(24)})


class SyntheticPortal:
    """Serves one portal: a dataset with every observable feature, and an empty dataset."""

    def __init__(
        self,
        *,
        domain: str = HOST,
        datasets: tuple[str, ...] = (DATASET, EMPTY),
        tz_rows: bool = True,
        gap_rows: list[dict[str, str]] | None = None,
        year_rows: list[dict[str, str]] | None = None,
        fail_on: str | None = None,
        extra_columns: tuple[dict[str, Any], ...] = (),
        area_values: tuple[str, ...] = ("Hollywood   ", "Central"),
        layer_columns: list[dict[str, Any]] | None = None,
        hi: str = "2026-06-30T23:00:00.000",
        midnight: int = 0,
        filtered_rows: list[dict[str, str]] | None = None,
    ) -> None:
        self.hi = hi
        self.gap_day = date(2026, 3, 8)
        self.midnight = midnight
        self.filtered_rows = YEAR if filtered_rows is None else filtered_rows
        self.fail_on = fail_on
        self.layer_columns = layer_columns
        self.extra_columns = extra_columns
        self.area_values = area_values
        self.gap_rows = GAP_DAY if gap_rows is None else gap_rows
        self.year_rows = YEAR if year_rows is None else year_rows
        self.domain = domain
        self.datasets = datasets
        self.tz_rows = tz_rows
        self.in_flight = 0
        self.max_in_flight = 0
        self.requests: list[str] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await anyio.sleep(0)
            self.requests.append(str(request.url))
            if self.fail_on and self.fail_on in str(request.url):
                return httpx.Response(500, json={"message": "synthetic failure"})
            # json.dumps escapes a lone surrogate, as upstream JSON can; httpx's json= cannot.
            body = json.dumps(self._route(request)).encode()
            return httpx.Response(200, content=body, headers={"content-type": "application/json"})
        finally:
            self.in_flight -= 1

    def _result(self, dataset: str, views: int | None) -> dict[str, Any]:
        resource: dict[str, Any] = {"id": dataset, "name": f"Dataset {dataset}"}
        if views is not None:
            resource["page_views"] = {"page_views_total": views}
        return {"resource": resource, "metadata": {"domain": self.domain}}

    def _route(self, request: httpx.Request) -> Any:  # noqa: PLR0911, PLR0912
        url, params = request.url, dict(request.url.params)
        if url.host == DISCOVERY:
            if url.path.endswith("/facets"):
                return [
                    {"facet": "categories", "values": [{"value": "Safety", "count": 2}]},
                    {
                        "facet": "datatypes",
                        "count": 3,
                        "values": [{"value": "dataset", "count": 2}, {"value": "map", "count": 1}],
                    },
                ]
            views = {DATASET: 50, EMPTY: None}
            ids = request.url.params.get_list("ids")
            results = [self._result(d, views.get(d)) for d in self.datasets if not ids or d in ids]
            return {"results": results, "resultSetSize": len(results)}
        path = url.path
        if path == f"/api/views/{LAYER}.json":
            return {
                "id": LAYER,
                "columns": self.layer_columns
                or [
                    {"fieldName": "_feature_id", "dataTypeName": "number"},
                    {"fieldName": "_feature_id_string", "dataTypeName": "text"},
                    {"fieldName": "name", "dataTypeName": "text"},
                ],
            }
        if path.startswith("/api/views/"):
            dataset = path.removeprefix("/api/views/").removesuffix(".json")
            return {"id": dataset, "columns": self._columns()}
        q = params["$query"]
        if path == f"/resource/{EMPTY}.json":
            return [{"n": "0"}]
        if q == "SELECT count(*) AS n":
            return [{"n": "1000"}]
        if q.startswith(f"SELECT count({REGION_COL})"):
            return [{"filled": "900", "n": "1000"}]
        if q.startswith("SELECT area_name AS v"):
            first, second = self.area_values
            return [{"v": first, "n": "600"}, {"v": second, "n": "400"}]
        if q.startswith("SELECT zone AS v"):
            return [{"v": "A", "n": "700"}, {"v": "-", "n": "300"}]
        if q.startswith("SELECT notes AS v"):
            return [{"v": f"note {i}", "n": "1"} for i in range(101)]
        if q.startswith("SELECT min(occurred)"):
            return [{"lo": "2024-01-01T00:00:00.000", "hi": self.hi}]
        if "AS midnight" in q:
            return [{"n": "1000", "midnight": str(self.midnight)}]
        if "date_extract_mm(occurred) != 0" in q:
            return self.filtered_rows
        if f"{self.gap_day.isoformat()}T00:00:00" in q:
            return self.gap_rows if self.tz_rows else []
        if "date_extract_hh(occurred)" in q:
            return self.year_rows if self.tz_rows else []
        raise AssertionError(f"unexpected request {url}")

    def _columns(self) -> list[dict[str, Any]]:
        return [
            {"fieldName": "area_name", "dataTypeName": "text"},
            {"fieldName": "zone", "dataTypeName": "text"},
            {"fieldName": "notes", "dataTypeName": "text"},
            {"fieldName": "count", "dataTypeName": "number"},
            {
                "fieldName": REGION_COL,
                "dataTypeName": "number",
                "computationStrategy": {
                    "type": "georegion_match_on_point",
                    "parameters": {"region": f"_{LAYER}", "primary_key": "_feature_id"},
                },
            },
            {"fieldName": "occurred", "dataTypeName": "floating_timestamp"},
            *self.extra_columns,
        ]


async def _profile(
    portal: SyntheticPortal,
    entry: RegistryEntry | None = None,
    datasets=10,
    dataset_ids: list[str] | None = None,
):
    client = SodaClient(transport=httpx.MockTransport(portal))
    try:
        return await profile_portal(
            client, entry or _entry(), datasets=datasets, dataset_ids=dataset_ids, today=TODAY
        )
    finally:
        await client.aclose()


def _soql(claim: Claim) -> list[SoqlProbe]:
    probes = claim.probes
    assert all(isinstance(p, SoqlProbe) for p in probes)
    return [p for p in probes if isinstance(p, SoqlProbe)]


def _by_id(claims: list[Claim]) -> dict[str, Claim]:
    return {c.id: c for c in claims}


async def test_profile_emits_observations_only():
    report, claims = await _profile(SyntheticPortal())
    assert report.identity_verified
    assert {c.id for c in claims} == {
        f"{DATASET}-{REGION_COL}-fill",
        f"{DATASET}-zone-placeholders",
        f"{DATASET}-area_name-padded",
        f"{DATASET}-occurred-timezone",
    }
    for c in claims:
        assert c.interpretation is None
        assert c.placeholders is None
        assert c.reviewed_by is None
        assert c.reviewed_at is None
        assert not c.reviewed


async def test_profile_report_shape():
    report, _ = await _profile(SyntheticPortal())
    assert report.portal_id == HOST
    assert report.asset_mix == {"dataset": 2, "map": 1}
    assert report.profiled_at == TODAY
    assert [d.dataset_id for d in report.datasets] == [DATASET, EMPTY]
    assert report.datasets[0].page_views == 50
    assert report.datasets[1].page_views is None
    assert "page_views_total" in report.flagship_basis


async def test_profile_never_writes_a_tier():
    entry = _entry()
    _, claims = await _profile(SyntheticPortal(), entry)
    files = pack_files(entry.identity, claims)
    assert tomllib.loads(files["portal.toml"])["tier"] == entry.identity.tier == "generic"
    assert PortalIdentity.model_validate(tomllib.loads(files["portal.toml"])) == entry.identity


async def test_emitted_assertions_pass_on_their_own_probe():
    portal = SyntheticPortal()
    _, claims = await _profile(portal)
    asserted = [c for c in claims if c.assertion]
    assert {c.id for c in asserted} == {c.id for c in claims}
    handler = portal._route
    for c in asserted:
        for a in c.assertion:
            probe = _soql(c)[a.probe]
            dataset = c.scope.dataset
            request = httpx.Request(
                "GET", f"https://{HOST}/resource/{dataset}.json", params={"$query": probe.query}
            )
            result = run_check(a.checker, a.typed_params, handler(request))
            assert result.outcome == "passed", (c.id, a.checker, result.detail)


async def test_padded_values_claim():
    _, claims = await _profile(SyntheticPortal())
    padded = _by_id(claims)[f"{DATASET}-area_name-padded"]
    assert padded.kind == "padded_values"
    assert len(padded.assertion) == 1
    (a,) = padded.assertion
    assert a.checker == "value_present"
    assert a.params["value"] == "Hollywood   "
    assert a.params["column"] == "v"
    assert "0.600" in _soql(padded)[0].observation


async def test_placeholder_claim_has_no_declaration():
    _, claims = await _profile(SyntheticPortal())
    ph = _by_id(claims)[f"{DATASET}-zone-placeholders"]
    assert ph.kind == "placeholder_share"
    assert ph.placeholders is None
    assert [(a.checker, a.params) for a in ph.assertion] == [
        ("value_present", {"column": "v", "value": "-", "count": "n"})
    ]


async def test_place_field_claim():
    _, claims = await _profile(SyntheticPortal())
    fill = _by_id(claims)[f"{DATASET}-{REGION_COL}-fill"]
    assert fill.kind == "place_field"
    assert _soql(fill)[0].query == f"SELECT count({REGION_COL}) AS filled, count(*) AS n"
    (a,) = fill.assertion
    assert a.checker == "share_by_group"
    assert a.params == {"numerator": "filled", "denominator": "n", "min": 0.85}
    assert LAYER in _soql(fill)[0].observation
    assert "`name`" in _soql(fill)[0].observation


#: Layer schemas probed live (`docs/evidence/standards-m4-2026-10-19/view-*.json`: field
#: name, type and cached cardinality only) and the label column the profiler should name.
#: It equals the pack's reviewed `label_column` except where noted.
_LAYER_EVIDENCE = Path(__file__).resolve().parent.parent / "docs/evidence/standards-m4-2026-10-19"
_LAYER_LABELS = {
    "chicago-8hcu-yrd4": "ward",  # was `globalid`, a GUID (Task 5 m2); `ward` is a number
    "chicago-43wa-7qmu": "ward",
    "chicago-awaf-s7ux": "ward",
    "chicago-vrxf-vc4k": "area_numbe",  # pack: `community`; both name the area, one by number
    "chicago-rpca-8um6": "zip",
    "chicago-6mkv-f3dw": "zcta5ce10",
    "chicago-bdys-3d7i": "name10",  # was `statefp10`, one value for every tract (Task 5 m2)
    "chicago-d9mm-jgwp": "dist_label",  # pack: `dist_num`; both name the district
    "chicago-d3ds-rm58": "beat_num",  # was `district`, 23 values over 277 beats
    "seattle-ru88-fbhk": "name",  # was `precinct`, 5 values over 61 areas
    "seattle-kuhn-3gp2": "name",
    "seattle-q256-3sug": "zcta5ce10",
    "seattle-cyqu-gs94": "c_district",  # was none: the label is a number
    "seattle-2day-rhn5": "name10",  # was `tractce10`
}


#: Probed layers where the profiler's candidate differs from the pack's reviewed label.
_PACK_DIFFERS = {"chicago-vrxf-vc4k": "community", "chicago-d9mm-jgwp": "dist_num"}
_PACKS = Path(__file__).resolve().parent.parent / "src/opendata_atlas/portals"


@pytest.mark.parametrize("layer", sorted(_LAYER_LABELS))
def test_expected_label_is_the_packs_unless_noted(layer):
    """The expectations above are the reviewed packs' label columns, but for two."""
    pack = {"chicago": "data.cityofchicago.org", "seattle": "seattle"}[layer.split("-")[0]]
    claim = load_portal(_PACKS / pack).pack.region_layer(layer.split("-", 1)[1])
    assert claim is not None and claim.interpretation is not None
    expected = _PACK_DIFFERS.get(layer, _LAYER_LABELS[layer])
    assert claim.interpretation.label_column == expected


@pytest.mark.parametrize("layer", sorted(_LAYER_LABELS))
async def test_candidate_label_column_names_each_feature(layer):
    """Ruling 87: the candidate label column tells the features apart and is not an id."""
    probed = json.loads((_LAYER_EVIDENCE / f"view-{layer}.json").read_text())
    _, claims = await _profile(SyntheticPortal(layer_columns=probed["columns"]))
    (probe,) = _soql(_by_id(claims)[f"{DATASET}-{REGION_COL}-fill"])
    assert f"candidate label column `{_LAYER_LABELS[layer]}`" in probe.observation


async def test_layer_with_only_bookkeeping_columns_has_no_candidate_label():
    columns = [
        {"fieldName": "_feature_id", "dataTypeName": "number"},
        {"fieldName": "objectid", "dataTypeName": "number"},
        {"fieldName": "globalid", "dataTypeName": "text"},
        {"fieldName": "the_geom", "dataTypeName": "multipolygon"},
    ]
    _, claims = await _profile(SyntheticPortal(layer_columns=columns))
    (probe,) = _soql(_by_id(claims)[f"{DATASET}-{REGION_COL}-fill"])
    assert "candidate label column none found" in probe.observation


async def test_dst_claim_on_spring_forward_day():
    _, claims = await _profile(SyntheticPortal())
    tz = _by_id(claims)[f"{DATASET}-occurred-timezone"]
    assert tz.kind == "column_timezone"
    assert tz.interpretation is None
    gap, day = _soql(tz)
    assert "'2026-03-08T00:00:00'" in gap.query
    assert "'2026-03-09T00:00:00'" in gap.query
    assert "'2025-06-30T00:00:00'" in day.query
    assert "'2026-07-01T00:00:00'" in day.query
    checks = [(a.checker, a.probe, a.params) for a in tz.assertion]
    assert checks == [
        ("dst_gap", 0, {"gap_hour": 2}),
        ("diurnal_peak", 1, {"peak_from": 15, "peak_to": 19}),
    ]


async def test_time_probes_with_no_rows_give_no_claim():
    report, claims = await _profile(SyntheticPortal(tz_rows=False))
    assert f"{DATASET}-occurred-timezone" not in _by_id(claims)
    assert any(n.startswith("occurred:") for n in report.datasets[0].notes)


async def test_failed_assertion_keeps_evidence_without_it():
    """Rows at the gap hour (a UTC-stored column) contradict dst_gap: no dst_gap assertion."""
    portal = SyntheticPortal(gap_rows=_hours(dict.fromkeys(range(24), 5)))
    _, claims = await _profile(portal)
    tz = _by_id(claims)[f"{DATASET}-occurred-timezone"]
    assert len(_soql(tz)) == 2
    assert [a.checker for a in tz.assertion] == ["diurnal_peak"]
    assert "hour 2 has 5 rows" in _soql(tz)[0].observation


async def test_date_only_column_gets_no_timezone_claim():
    """Every probed row at hour 0 is a date-only column: a note, no claim, no extra request."""
    portal = SyntheticPortal(gap_rows=_hours({0: 40}), year_rows=_hours({0: 9000}))
    report, claims = await _profile(portal)
    assert not any(c.kind == "column_timezone" for c in claims)
    assert "occurred: date-only; no timezone test applies." in report.datasets[0].notes
    assert len([r for r in portal.requests if "occurred" in r]) == 3


async def test_null_timezone_portal_skips_timezone_probes():
    portal = SyntheticPortal()
    report, claims = await _profile(portal, _entry(timezone=None))
    assert not any(c.kind == "column_timezone" for c in claims)
    assert not any("min(occurred)" in r or "date_extract_hh" in r for r in portal.requests)
    notes = report.datasets[0].notes
    assert any("occurred" in n and "timezone" in n for n in notes), notes


async def test_no_dst_zone_gets_a_diurnal_only_claim():
    """A zone with no spring-forward day still gets the by-hour probe, with no dst_gap."""
    portal = SyntheticPortal()
    report, claims = await _profile(portal, _entry(timezone="Pacific/Honolulu"))
    tz = _by_id(claims)[f"{DATASET}-occurred-timezone"]
    (day,) = _soql(tz)
    assert "'2025-06-30T00:00:00'" in day.query
    assert [(a.checker, a.probe) for a in tz.assertion] == [("diurnal_peak", 0)]
    assert not any("2026-03-08" in r for r in portal.requests)
    notes = report.datasets[0].notes
    assert any("Pacific/Honolulu" in n and "by-hour probe only" in n for n in notes), notes


async def test_midnight_defaults_are_left_out_of_the_diurnal_probe():
    """Many rows at exactly 00:00:00 (an unknown-time default) would fake an hour-0 peak."""
    portal = SyntheticPortal(
        year_rows=_hours({h: (500 if h == 0 else 100 if h == 17 else 10) for h in range(24)}),
        midnight=400,
    )
    _, claims = await _profile(portal)
    tz = _by_id(claims)[f"{DATASET}-occurred-timezone"]
    _, day, midnight = _soql(tz)
    assert "date_extract_mm(occurred) != 0" in day.query
    assert "AS midnight" in midnight.query
    assert "400 of 1,000" in midnight.observation
    assert "left out" in day.observation
    peak = next(a for a in tz.assertion if a.checker == "diurnal_peak")
    assert (peak.probe, peak.params) == (1, {"peak_from": 15, "peak_to": 19})


async def test_few_midnight_rows_keep_the_raw_diurnal_probe():
    portal = SyntheticPortal(midnight=5)
    _, claims = await _profile(portal)
    tz = _by_id(claims)[f"{DATASET}-occurred-timezone"]
    assert len(_soql(tz)) == 2
    assert not any("date_extract_mm(occurred) != 0" in r for r in portal.requests)


async def test_future_max_ends_the_window_today():
    """A row dated after today must not move the window past the data (Everett, row 165)."""
    portal = SyntheticPortal(hi="2026-12-20T00:00:00.000")
    report, claims = await _profile(portal)
    _, day = _soql(_by_id(claims)[f"{DATASET}-occurred-timezone"])
    assert "'2025-10-18T00:00:00'" in day.query
    assert "'2026-10-19T00:00:00'" in day.query
    assert any("2026-12-20" in n and "after today" in n for n in report.datasets[0].notes)


async def test_dataset_ids_profile_only_the_named_datasets():
    portal = SyntheticPortal()
    report, _ = await _profile(portal, dataset_ids=[EMPTY])
    assert [d.dataset_id for d in report.datasets] == [EMPTY]
    assert report.error is None
    assert EMPTY in report.flagship_basis and "--dataset" in report.flagship_basis


async def test_repeated_dataset_id_is_profiled_once():
    """A repeated id would emit duplicate claim ids, which the loader rejects (exit 5)."""
    report, claims = await _profile(SyntheticPortal(), dataset_ids=[DATASET, DATASET])
    assert [d.dataset_id for d in report.datasets] == [DATASET]
    ids = [c.id for c in claims]
    assert len(ids) == len(set(ids))


async def test_midnight_spring_forward_keeps_gap_hour_0():
    """A zone that springs forward at midnight skips hour 0; it must not become hour 2."""
    zone = ZoneInfo("America/Santiago")
    day = spring_forward(zone, date(2024, 1, 1), date(2026, 6, 30))
    assert day is not None and gap_hour(zone, day) == 0  # known positive: such zones exist
    portal = SyntheticPortal(gap_rows=_hours({h: 5 for h in range(1, 24)}))
    portal.gap_day = day
    _, claims = await _profile(portal, _entry(timezone="America/Santiago"))
    tz = _by_id(claims)[f"{DATASET}-occurred-timezone"]
    gap = next(a for a in tz.assertion if a.checker == "dst_gap")
    assert gap.params == {"gap_hour": 0}


async def test_unknown_dataset_id_stops_before_any_dataset():
    portal = SyntheticPortal()
    report, claims = await _profile(portal, dataset_ids=[DATASET, "nope-0000"])
    assert report.error == "datasets: not on this portal: nope-0000"
    assert report.datasets == []
    assert claims == []


async def test_zero_row_dataset_is_noted():
    portal = SyntheticPortal()
    report, claims = await _profile(portal)
    empty = report.datasets[1]
    assert empty.dataset_id == EMPTY
    assert empty.claims == []
    assert any("0 rows" in n for n in empty.notes), empty.notes
    assert not any(c.scope.dataset == EMPTY for c in claims)
    assert len([r for r in portal.requests if f"/resource/{EMPTY}" in r]) == 1


async def test_noncategorical_text_column_is_skipped():
    report, claims = await _profile(SyntheticPortal())
    assert not any(c.scope.column == "notes" for c in claims)
    assert any(n.startswith("notes:") and "100" in n for n in report.datasets[0].notes)


def test_observe_text_ignores_more_than_100_groups():
    rows = [{"v": "-", "n": "5"}] + [{"v": f"x{i}", "n": "1"} for i in range(100)]
    assert observe_text(DATASET, "c", "SELECT c AS v", rows, TODAY) == []


def test_observe_text_skips_null_group():
    rows = [{"n": "10"}, {"v": "A", "n": "5"}]
    assert observe_text(DATASET, "c", "SELECT c AS v", rows, TODAY) == []


async def test_requests_are_sequential():
    portal = SyntheticPortal()
    await _profile(portal)
    assert len(portal.requests) > 10
    assert portal.max_in_flight == 1


async def test_datasets_caps_flagships():
    report, _ = await _profile(SyntheticPortal(), datasets=1)
    assert [d.dataset_id for d in report.datasets] == [DATASET]


async def test_unverified_identity_stops_after_identity():
    portal = SyntheticPortal(domain="other.example.gov")
    report, claims = await _profile(portal)
    assert not report.identity_verified
    assert "other.example.gov" in report.identity_detail
    assert claims == []
    assert report.datasets == []
    assert all(DISCOVERY in r and "facets" not in r for r in portal.requests)


def test_identity_verified():
    page = [{"metadata": {"domain": HOST}}]
    assert identity_verified([page, page], HOST)
    assert not identity_verified([], HOST)
    assert not identity_verified([[]], HOST)
    assert not identity_verified([page, [{"metadata": {"domain": "x.gov"}}]], HOST)
    assert not identity_verified([[{"metadata": {}}]], HOST)


def test_flagships_order():
    def r(i: str, views: int | None) -> dict[str, Any]:
        res: dict[str, Any] = {"id": i}
        if views is not None:
            res["page_views"] = {"page_views_total": views}
        return {"resource": res}

    results = [r("bbbb-0000", 5), r("aaaa-0000", None), r("cccc-0000", 9), r("aaaa-1111", 5)]
    assert [x["resource"]["id"] for x in flagships(results, 3)] == [
        "cccc-0000",
        "aaaa-1111",
        "bbbb-0000",
    ]
    assert [x["resource"]["id"] for x in flagships(results, 10)][-1] == "aaaa-0000"


def test_spring_forward():
    la = ZoneInfo("America/Los_Angeles")
    assert spring_forward(la, date(2025, 1, 1), date(2026, 6, 30)) == date(2026, 3, 8)
    assert spring_forward(la, date(2026, 3, 8), date(2026, 3, 8)) == date(2026, 3, 8)
    assert spring_forward(la, date(2026, 3, 9), date(2026, 10, 1)) is None
    assert spring_forward(la, date(2026, 11, 1), date(2026, 11, 1)) is None
    honolulu = ZoneInfo("Pacific/Honolulu")
    assert spring_forward(honolulu, date(2020, 1, 1), date(2026, 10, 18)) is None


def test_render_claims_escapes_strings():
    from opendata_atlas.portals.model import Claim, Scope

    claim = Claim(
        id="x-y-padded",
        kind="padded_values",
        scope=Scope(dataset="abcd-1234", column="y"),
        evidence=[
            SoqlProbe(
                kind="soql_probe",
                query="SELECT y AS v WHERE y = 'a\"b\\c'",
                observed_at=TODAY,
                observation="tab\there, del\x7f, é, emoji \U0001f600, newline\n",
            )
        ],
    )
    text = render_claims([claim])
    assert text.isascii()
    parsed = tomllib.loads(text)["claim"][0]
    assert Claim.model_validate(parsed) == claim
    assert "observed_at = 2026-10-18" in text


@pytest.mark.parametrize(
    "bad",
    [
        "a\ud800b",
        "x\udc00",
        "\udc00\ud800",
        "\ud83d\ude00 ok \ud800",
        "lit \\ud83d\\ude00 \\ud800 \ud800",
    ],
)
def test_render_claims_replaces_lone_surrogates(bad):
    from opendata_atlas.portals.model import Claim, Scope

    claim = Claim(
        id="x-y-padded",
        kind="padded_values",
        scope=Scope(dataset="abcd-1234", column="y"),
        evidence=[
            SoqlProbe(kind="soql_probe", query="SELECT 1", observed_at=TODAY, observation=bad)
        ],
    )
    parsed = tomllib.loads(render_claims([claim]))["claim"][0]
    observation = parsed["evidence"][0]["observation"]
    assert "\ufffd" in observation
    assert observation == "".join(
        "\ufffd" if 0xD800 <= ord(ch) <= 0xDFFF else ch
        for ch in bad.encode("utf-16", "surrogatepass").decode("utf-16", "replace")
    )


def test_lone_surrogate_upstream_value_gives_a_loadable_pack(run_cli, tmp_path):
    out = tmp_path / "draft"
    portal = SyntheticPortal(area_values=("a\ud800b  ", "\udc00\ud800 "))
    report = tmp_path / "report.json"
    argv = [HOST, "--out", str(out), "--report", str(report), "--datasets", "1"]
    assert run_cli(argv, portal) == 0
    loaded = load_portal(out, validation=ValidationFile())
    assert not any(c.scope.column == "area_name" for c in loaded.pack.claims)
    notes = json.loads(report.read_text())["datasets"][0]["notes"]
    assert "area_name: values that are not valid Unicode; skipped." in notes


async def test_emitted_pack_round_trips(tmp_path):
    entry = _entry()
    _, claims = await _profile(SyntheticPortal(), entry)
    files = pack_files(entry.identity, claims)
    assert set(files) == {"portal.toml", f"facts/{DATASET}.toml"}
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)
    loaded = load_portal(tmp_path, validation=ValidationFile())
    assert loaded.identity == entry.identity
    assert loaded.pack.claims == claims


def test_pack_files_puts_layer_claims_in_regions():
    from opendata_atlas.portals.model import Claim, ManualObservation, Scope

    layer = Claim(
        id="region-ab12-cd34",
        kind="region_layer",
        scope=Scope(layer=LAYER),
        evidence=[ManualObservation(kind="manual_observation", note="n", observed_at=TODAY)],
    )
    files = pack_files(_entry().identity, [layer])
    assert set(files) == {"portal.toml", "regions.toml"}


# CLI


@pytest.fixture
def run_cli(monkeypatch, tmp_path) -> Callable[..., int]:
    def run(argv: list[str], portal: SyntheticPortal, entry: RegistryEntry | None = None) -> int:
        e = entry or _entry()
        registry = Registry(version="test", entries={e.identity.id: e})
        monkeypatch.setattr(cli, "load_registry", lambda: registry)
        monkeypatch.setattr(
            cli, "SodaClient", lambda: SodaClient(transport=httpx.MockTransport(portal))
        )
        monkeypatch.setattr(cli.freshness, "today", lambda: TODAY)
        monkeypatch.chdir(tmp_path)
        return cli.main(argv)

    return run


def test_cli_writes_pack_and_report(run_cli, tmp_path):
    out, report = tmp_path / "draft", tmp_path / "report.json"
    code = run_cli([HOST, "--out", str(out), "--report", str(report)], SyntheticPortal())
    assert code == 0
    assert (out / "portal.toml").is_file()
    assert (out / "facts" / f"{DATASET}.toml").is_file()
    data = json.loads(report.read_text())
    assert data["identity_verified"] is True
    assert len(data["datasets"]) == 2
    load_portal(out, validation=ValidationFile())


def test_cli_report_defaults_to_stdout(run_cli, tmp_path, capsys):
    assert run_cli([HOST, "--out", str(tmp_path / "d"), "--datasets", "1"], SyntheticPortal()) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["portal_id"] == HOST
    assert len(data["datasets"]) == 1


def test_null_timezone_portal_exits_0(run_cli, tmp_path):
    out = tmp_path / "d"
    assert run_cli([HOST, "--out", str(out)], SyntheticPortal(), _entry(timezone=None)) == 0
    assert not any("timezone" in p.read_text() for p in (out / "facts").glob("*.toml"))


def test_unverified_identity_exits_3(run_cli, tmp_path):
    out, report = tmp_path / "draft", tmp_path / "report.json"
    portal = SyntheticPortal(domain="other.example.gov")
    assert run_cli([HOST, "--out", str(out), "--report", str(report)], portal) == 3
    assert json.loads(report.read_text())["identity_verified"] is False
    assert not out.exists()


def test_existing_out_dir_exits_2(run_cli, tmp_path):
    out = tmp_path / "draft"
    out.mkdir()
    portal = SyntheticPortal()
    assert run_cli([HOST, "--out", str(out)], portal) == 2
    assert portal.requests == []


def test_cli_dataset_option_profiles_named_datasets(run_cli, tmp_path):
    out, report = tmp_path / "d", tmp_path / "r.json"
    argv = [HOST, "--dataset", DATASET, "--out", str(out), "--report", str(report)]
    assert run_cli(argv, SyntheticPortal()) == 0
    assert [d["dataset_id"] for d in json.loads(report.read_text())["datasets"]] == [DATASET]


def test_cli_unknown_dataset_exits_6(run_cli, tmp_path, capsys):
    out, report = tmp_path / "d", tmp_path / "r.json"
    argv = [HOST, "--dataset", "nope-0000", "--out", str(out), "--report", str(report)]
    assert run_cli(argv, SyntheticPortal()) == 6
    assert not out.exists()
    assert json.loads(report.read_text())["error"] == "datasets: not on this portal: nope-0000"
    assert "nope-0000" in capsys.readouterr().err


def test_cli_dataset_and_datasets_are_exclusive(run_cli, tmp_path):
    portal = SyntheticPortal()
    argv = [HOST, "--dataset", DATASET, "--datasets", "3", "--out", str(tmp_path / "d")]
    with pytest.raises(SystemExit) as e:
        run_cli(argv, portal)
    assert e.value.code == 2
    assert portal.requests == []


def test_unknown_host_exits_2(run_cli, tmp_path):
    portal = SyntheticPortal()
    assert run_cli(["nowhere.example.org", "--out", str(tmp_path / "d")], portal) == 2
    assert portal.requests == []


def test_out_defaults_to_portals_dir(run_cli, tmp_path):
    (tmp_path / "src" / "opendata_atlas" / "portals").mkdir(parents=True)
    assert run_cli([HOST, "--datasets", "1"], SyntheticPortal()) == 0
    assert (tmp_path / "src" / "opendata_atlas" / "portals" / HOST / "portal.toml").is_file()


def test_out_required_without_portals_dir(run_cli):
    portal = SyntheticPortal()
    assert run_cli([HOST], portal) == 2
    assert portal.requests == []


def test_cli_refuses_a_pack_that_does_not_load(run_cli, tmp_path, monkeypatch, capsys):
    real = cli.pack_files

    def broken(identity, claims):
        files = real(identity, claims)
        files[f"facts/{DATASET}.toml"] = "[[claim]]\nid = \n"
        return files

    monkeypatch.setattr(cli, "pack_files", broken)
    out = tmp_path / "draft"
    assert run_cli([HOST, "--out", str(out)], SyntheticPortal()) == cli.EXIT_INVALID_PACK
    err = capsys.readouterr().err
    assert f"facts/{DATASET}.toml" in err.replace("\\", "/")  # `\` on Windows
    assert not out.exists()
    assert list(tmp_path.iterdir()) == [], "no temporary directory is left behind"


def test_cli_lists_values_to_review(run_cli, tmp_path, capsys):
    report = tmp_path / "report.json"
    assert (
        run_cli([HOST, "--out", str(tmp_path / "d"), "--report", str(report)], SyntheticPortal())
        == 0
    )
    err = capsys.readouterr().err
    heading = "Review these values before committing; drop any that identify a person"
    assert heading in err
    after = err.split(heading, 1)[1]
    assert f"{DATASET}-area_name-padded" in after
    assert '"Hollywood   "' in after
    assert '"-"' not in after
    listed = json.loads(report.read_text())["review_values"]
    assert listed == [{"claim_id": f"{DATASET}-area_name-padded", "value": "Hollywood   "}]


@pytest.mark.parametrize("stage", ["catalog/v1?", "/facets", "only=dataset"])
def test_upstream_failure_before_datasets_writes_report(run_cli, tmp_path, stage, capsys):
    out, report = tmp_path / "draft", tmp_path / "report.json"
    portal = SyntheticPortal(fail_on=stage)
    assert run_cli([HOST, "--out", str(out), "--report", str(report)], portal) == cli.EXIT_UPSTREAM
    data = json.loads(report.read_text())
    assert data["error"].endswith("upstream_unavailable")
    assert data["datasets"] == []
    assert not out.exists()
    assert "Traceback" not in capsys.readouterr().err


async def test_column_without_field_name_is_skipped():
    portal = SyntheticPortal(extra_columns=({"dataTypeName": "text"}, {"fieldName": 7}))
    report, claims = await _profile(portal)
    assert {c.id for c in claims} >= {f"{DATASET}-zone-placeholders"}
    assert any("2 columns without a field name" in n for n in report.datasets[0].notes)
