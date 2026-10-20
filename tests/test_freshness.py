"""Milestone 3 Task 3: runtime freshness and asymmetric degradation of stale claims.

`docs/design.md` Validation state and freshness, Knowledge levels, Place fields and Time are
the spec. The conftest pins `freshness.today()` to 2026-10-18, the clock the shipped checks
were first validated against (a later `checked_at`, such as the 2026-10-19 drift run's, is
fresh).
"""

from __future__ import annotations

import tomllib
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from opendata_atlas.core import describe, query
from opendata_atlas.core.http import SodaClient
from opendata_atlas.portals import freshness
from opendata_atlas.portals.freshness import claim_validation, combine
from opendata_atlas.portals.knowledge import GAP_OFFER, SHARED_PLACEHOLDERS
from opendata_atlas.portals.model import Claim
from opendata_atlas.portals.validation import ClaimCheck
from tests.conftest import SEATTLE_CONTEXT, wire
from tests.http_fixtures import Replay

if TYPE_CHECKING:
    from opendata_atlas.portals.model import PortalContext, Validation

TODAY = date(2026, 10, 18)
CRIME, FIRE = "tazs-3rd5", "kzjm-xkqj"
STALE_REASON = (
    "Reviewed as ok, but its checks last ran on {}, over 180 days ago; "
    "treat its coverage as unknown."
)
_PROBE = {
    "kind": "soql_probe",
    "query": "SELECT count(*) AS n",
    "observed_at": date(2026, 10, 18),
    "observation": "test fixture",
}
_ASSERTION = {
    "checker": "share_by_group",
    "params": {"numerator": "n", "denominator": "n", "min": 0.5},
}


def _claim(claim_id: str) -> Claim:
    return next(c for c in SEATTLE_CONTEXT.pack.claims if c.id == claim_id)


def _checked(ctx: PortalContext, claim_id: str, days_ago: int) -> PortalContext:
    """A copy of `ctx` whose check for `claim_id` ran `days_ago` days before TODAY."""
    check = ClaimCheck(checked_at=TODAY - timedelta(days=days_ago), outcome="passed")
    return replace(ctx, checks={**ctx.checks, claim_id: check})


def _with_claims(ctx: PortalContext, *claims: Claim, drop: tuple[str, ...] = ()) -> PortalContext:
    kept = [c for c in ctx.pack.claims if c.id not in drop]
    return replace(ctx, pack=ctx.pack.model_copy(update={"claims": [*kept, *claims]}))


def _asserted(claim_id: str, kind: str, column: str, **fields: Any) -> Claim:
    return Claim.model_validate(
        {
            "id": claim_id,
            "kind": kind,
            "scope": {"dataset": CRIME, "column": column},
            "reviewed_by": "test",
            "reviewed_at": date(2026, 10, 18),
            "evidence": [_PROBE],
            "assertion": [_ASSERTION],
            **fields,
        }
    )


async def _describe_full(fixture: str, ctx: PortalContext, dataset_id: str):
    return await describe.describe(
        SodaClient(transport=Replay(fixture)),
        ctx,
        dataset_id=dataset_id,
        column_query=None,
        sample_rows=0,
        detail="full",
    )


#: Recorded views for SPD Crime Data; the sector grouping itself is served by an override.
_SECTOR_ROWS = (200, [{"sector": "K", "n": "3"}, {"sector": "B", "n": "2"}])


async def _query_sector(ctx: PortalContext):
    replay = Replay("query_coverage_grouped", overrides={"GROUP BY sector": _SECTOR_ROWS})
    return await query.run(
        SodaClient(transport=replay),
        ctx,
        dataset_id=CRIME,
        mode="soql",
        clauses={},
        soql="SELECT sector, count(*) AS n GROUP BY sector LIMIT 3",
        page_size=None,
        cursor=None,
        detail="summary",
    )


# --- Step 1: the rule ---------------------------------------------------------


def test_fresh_check_reports_its_outcome():
    claim = _claim("kzjm-xkqj-datetime-timezone")
    assert claim_validation(SEATTLE_CONTEXT, claim, TODAY) == "passed"
    assert freshness.today() == TODAY, "the conftest pins the clock"


def test_claim_without_assertions_is_unchecked():
    claim = _claim("region-ru88-fbhk")
    assert not claim.assertion
    # Even an entry does not check a claim that asserts nothing.
    ctx = _checked(SEATTLE_CONTEXT, claim.id, 0)
    assert claim_validation(ctx, claim, TODAY) == "unchecked"


def test_asserted_claim_without_entry_is_unchecked():
    claim = _claim("tazs-3rd5-sector-place")
    assert claim.assertion
    assert claim_validation(replace(SEATTLE_CONTEXT, checks={}), claim, TODAY) == "unchecked"


def test_180_days_is_fresh_181_is_stale():  # Review Focus 2
    claim = _claim("tazs-3rd5-sector-place")
    assert freshness.STALE_AFTER_DAYS == 180
    assert claim_validation(_checked(SEATTLE_CONTEXT, claim.id, 180), claim, TODAY) == "passed"
    assert claim_validation(_checked(SEATTLE_CONTEXT, claim.id, 181), claim, TODAY) == "stale"


def test_future_checked_at_is_fresh():  # Review Focus 2
    claim = _claim("tazs-3rd5-sector-place")
    ctx = _checked(SEATTLE_CONTEXT, claim.id, -30)
    assert claim_validation(ctx, claim, TODAY) == "passed"


def test_combine_order():
    order: list[Validation] = ["contradicted", "stale", "inconclusive", "unchecked", "passed"]
    for i, worst in enumerate(order):
        assert combine(order[i:]) == worst
        assert combine(reversed(order[i:])) == worst
    assert combine([]) == "unchecked"
    assert combine(["passed", "passed"]) == "passed"


# --- Step 2: degradation over recorded fixtures ---------------------------------


async def test_stale_ok_place_field_reads_unknown():
    ctx = _checked(SEATTLE_CONTEXT, "tazs-3rd5-sector-place", 181)
    result = await _describe_full("describe_crime_full", ctx, CRIME)
    sector = next(p for p in result.place_fields if p.column == "sector")
    assert (sector.reliability, sector.validation) == ("unknown", "stale")
    assert sector.reliability_reason == STALE_REASON.format(TODAY - timedelta(days=181))
    precinct = next(p for p in result.place_fields if p.column == "precinct")
    assert (precinct.reliability, precinct.validation) == ("ok", None), "only the stale claim"

    out = await _query_sector(ctx)
    warnings = [wire(w) for w in out.coverage_warnings or []]
    assert [(w["column"], w["reliability"], w["validation"]) for w in warnings] == [
        ("sector", "unknown", "stale")
    ]
    assert out.knowledge_notice is not None
    assert "`sector`" in out.knowledge_notice.message
    assert "stale" in out.knowledge_notice.message
    caveat = out.knowledge_notice.message.removesuffix(" " + GAP_OFFER)
    assert caveat != out.knowledge_notice.message, "ends with the gap offer (ruling 68)"
    assert caveat.endswith(".")
    assert ". " not in caveat, "one sentence"
    # Fresh, the same query has no warning on an ok field.
    fresh = await _query_sector(SEATTLE_CONTEXT)
    assert fresh.coverage_warnings is None


async def test_stale_partial_verdict_is_kept():
    partial = _asserted(
        "test.sector.partial",
        "place_field",
        "sector",
        interpretation={"kind": "sector", "reliability": "partial", "reason": "test gaps"},
    )
    ctx = _checked(
        _with_claims(SEATTLE_CONTEXT, partial, drop=("tazs-3rd5-sector-place",)), partial.id, 181
    )
    result = await _describe_full("describe_crime_full", ctx, CRIME)
    sector = next(p for p in result.place_fields if p.column == "sector")
    assert (sector.reliability, sector.reliability_reason) == ("partial", "test gaps")
    assert sector.validation == "stale"

    out = await _query_sector(ctx)
    assert [wire(w) for w in out.coverage_warnings or []] == [
        {"column": "sector", "reliability": "partial", "reason": "test gaps", "validation": "stale"}
    ]


async def test_stale_timezone_reads_unknown():
    ctx = _checked(SEATTLE_CONTEXT, "kzjm-xkqj-datetime-timezone", 181)
    result = await _describe_full("describe_fire_full", ctx, FIRE)
    entry = wire(next(t for t in result.time_semantics if t.column == "datetime"))
    assert "timezone" not in entry and "evidence" not in entry
    assert entry["validation"] == "stale"
    datetime_column = next(c for c in result.columns if c.name == "datetime")
    assert datetime_column.knowledge is not None
    assert datetime_column.knowledge.validation == "stale"
    fresh = await _describe_full("describe_fire_full", SEATTLE_CONTEXT, FIRE)
    entry = wire(next(t for t in fresh.time_semantics if t.column == "datetime"))
    assert entry["timezone"] == "America/Los_Angeles" and "validation" not in entry


async def test_stale_placeholder_declaration_withholds_assigned_fraction():
    # SLU/CASCADE is a real neighborhood outside the shared vocabulary: only the stale
    # declaration can make it a candidate.
    declared = ["-", "UNKNOWN", "OOJ", "FK ERROR", "SLU/CASCADE"]
    assert "SLU/CASCADE" not in SHARED_PLACEHOLDERS
    claim = _asserted(
        "test.neighborhood.placeholders", "placeholder_share", "neighborhood", placeholders=declared
    )
    base = _with_claims(SEATTLE_CONTEXT, claim, drop=("tazs-3rd5-neighborhood-placeholders",))
    fresh = await _describe_full("describe_crime_full", base, CRIME)
    hood = next(p for p in fresh.place_fields if p.column == "neighborhood")
    assert hood.assigned_fraction is not None and hood.placeholder_values, "fresh: excluded"
    assert "SLU/CASCADE" in {p.value for p in hood.placeholder_values}

    result = await _describe_full("describe_crime_full", _checked(base, claim.id, 181), CRIME)
    hood = next(p for p in result.place_fields if p.column == "neighborhood")
    assert hood.assigned_fraction is None and hood.placeholder_values is None
    candidates = {p.value for p in hood.candidate_placeholders or []}
    present = {v.value for v in hood.values or []}
    assert "SLU/CASCADE" in candidates and "SLU/CASCADE" in present
    assert candidates == present & (set(declared) | SHARED_PLACEHOLDERS)
    knowledge = next(c for c in result.columns if c.name == "neighborhood").knowledge
    assert knowledge is not None and knowledge.validation == "stale"


async def test_mixed_declarations_keep_the_fresh_placeholders():
    fresh_claim = _asserted(
        "test.neighborhood.fresh", "placeholder_share", "neighborhood", placeholders=["-"]
    )
    stale_claim = _asserted(
        "test.neighborhood.stale",
        "placeholder_share",
        "neighborhood",
        placeholders=["SLU/CASCADE"],
    )
    base = _with_claims(
        SEATTLE_CONTEXT, fresh_claim, stale_claim, drop=("tazs-3rd5-neighborhood-placeholders",)
    )
    ctx = _checked(_checked(base, fresh_claim.id, 0), stale_claim.id, 181)
    result = await _describe_full("describe_crime_full", ctx, CRIME)
    hood = next(p for p in result.place_fields if p.column == "neighborhood")
    kept = {p.value: p.rows for p in hood.placeholder_values or []}
    assert kept == {"-": 745994}, "the fresh declaration's placeholders stay"
    values = {v.value for v in hood.values or []}
    candidates = {p.value for p in hood.candidate_placeholders or []}
    assert "-" not in values and "-" not in candidates
    assert "SLU/CASCADE" in values and "SLU/CASCADE" in candidates
    assert hood.assigned_fraction is None


#: Seattle's own claims on `neighborhood`, dropped so a test claim is its only declaration.
_HOOD_CLAIMS = ("tazs-3rd5-neighborhood-place", "tazs-3rd5-neighborhood-placeholders")


def _hood_place_field(placeholders: list[str]) -> Claim:
    """A reviewed `partial` place field that declares placeholders, as
    `docs/pack-examples/place_field.toml` does (engine gap 2, Everett review M1)."""
    return _asserted(
        "test.neighborhood.place",
        "place_field",
        "neighborhood",
        interpretation={"kind": "neighborhood", "reliability": "partial", "reason": "test gaps"},
        placeholders=placeholders,
    )


async def test_reviewed_place_field_placeholders_are_declared():
    claim = _hood_place_field(["-", "SLU/CASCADE"])
    ctx = _with_claims(SEATTLE_CONTEXT, claim, drop=_HOOD_CLAIMS)
    result = await _describe_full("describe_crime_full", ctx, CRIME)
    hood = next(p for p in result.place_fields if p.column == "neighborhood")
    kept = {p.value: p.rows for p in hood.placeholder_values or []}
    assert kept.get("-") == 745994 and "SLU/CASCADE" in kept
    values = {v.value for v in hood.values or []}
    candidates = {p.value for p in hood.candidate_placeholders or []}
    assert not values & {"-", "SLU/CASCADE"} and not candidates & {"-", "SLU/CASCADE"}
    assert hood.assigned_fraction is not None and hood.assigned_fraction < 0.6
    assert ctx.pack.placeholders(CRIME, "neighborhood") == frozenset({"-", "SLU/CASCADE"})


async def test_stale_place_field_placeholders_degrade():
    claim = _hood_place_field(["SLU/CASCADE"])
    ctx = _checked(_with_claims(SEATTLE_CONTEXT, claim, drop=_HOOD_CLAIMS), claim.id, 181)
    result = await _describe_full("describe_crime_full", ctx, CRIME)
    hood = next(p for p in result.place_fields if p.column == "neighborhood")
    assert hood.assigned_fraction is None
    assert "SLU/CASCADE" not in {p.value for p in hood.placeholder_values or []}
    assert "SLU/CASCADE" in {v.value for v in hood.values or []}
    assert "SLU/CASCADE" in {p.value for p in hood.candidate_placeholders or []}
    # Only the declaration degrades: the stale partial verdict is kept.
    assert (hood.reliability, hood.reliability_reason) == ("partial", "test gaps")
    assert hood.validation == "stale"


async def test_stale_ok_region_layer_reads_unknown():
    layer = Claim.model_validate(
        {
            "id": "test.layer.ru88",
            "kind": "region_layer",
            "scope": {"layer": "ru88-fbhk"},
            "interpretation": {"kind": "neighborhood", "label_column": "name", "reliability": "ok"},
            "reviewed_by": "test",
            "reviewed_at": date(2026, 10, 18),
            "evidence": [_PROBE],
            "assertion": [_ASSERTION],
        }
    )
    base = _with_claims(SEATTLE_CONTEXT, layer, drop=("region-ru88-fbhk",))
    column = ":@computed_region_ru88_fbhk"
    fresh = await _describe_full("describe_fire_full", base, FIRE)
    field = next(p for p in fresh.place_fields if p.column == column)
    assert (field.reliability, field.validation) == ("ok", None)
    result = await _describe_full("describe_fire_full", _checked(base, layer.id, 181), FIRE)
    field = next(p for p in result.place_fields if p.column == column)
    assert (field.reliability, field.validation) == ("unknown", "stale")
    assert field.reliability_reason == STALE_REASON.format(TODAY - timedelta(days=181))
    assert field.label_column == "name", "the layer's labels still apply"


async def test_fresh_seattle_output_has_no_validation_fields():
    for fixture, dataset_id in (("describe_crime_full", CRIME), ("describe_fire_full", FIRE)):
        out = wire(await _describe_full(fixture, SEATTLE_CONTEXT, dataset_id))
        assert out["place_fields"] and out["time_semantics"]
        for entry in [*out["place_fields"], *out["time_semantics"]]:
            assert "validation" not in entry, entry
    replay = Replay("query_coverage_grouped")
    out = await query.run(
        SodaClient(transport=replay),
        SEATTLE_CONTEXT,
        dataset_id=CRIME,
        mode="clauses",
        clauses={
            "select": ["neighborhood", "count(*) AS n"],
            "group_by": ["neighborhood"],
            "order_by": ["n DESC"],
        },
        soql=None,
        page_size=3,
        cursor=None,
        detail="summary",
    )
    warnings = wire(out)["coverage_warnings"]
    assert warnings and all("validation" not in w for w in warnings)


@pytest.mark.parametrize("body", ["capabilities", "contributing"])
def test_capability_summary_states_installed_release_rule(body):
    from opendata_atlas.core.reference import CAPABILITIES, CONTRIBUTING

    text = {"capabilities": CAPABILITIES, "contributing": CONTRIBUTING}[body]
    assert (
        "Scheduled drift checks cannot change an installed release; "
        "the runtime freshness rule is what protects old installs."
    ) in text
    assert "In this release every claim reports" not in text
    assert "180 days" in text and '"stale"' in text and "`unknown`" in text


def test_load_portal_fills_checks_for_its_own_portal():
    from opendata_atlas.portals.loader import SEATTLE, load_portal
    from opendata_atlas.portals.registry import context_for
    from opendata_atlas.portals.validation import ValidationFile

    check = ClaimCheck(checked_at=date(2026, 1, 1), outcome="inconclusive")
    file = ValidationFile(portals={"data.seattle.gov": {"x": check}, "other.gov": {"y": check}})
    assert dict(load_portal(SEATTLE, validation=file).checks) == {"x": check}
    shipped = load_portal(SEATTLE).checks
    asserted = {c.id for c in load_portal(SEATTLE).pack.claims if c.assertion}
    assert set(shipped) == asserted and {c.outcome for c in shipped.values()} == {"passed"}
    assert context_for(SEATTLE_CONTEXT.identity, None).checks == {}, "no pack, no checks"


def test_portal_summary_counts_validations():
    from opendata_atlas.core.reference_service import portal_summary

    asserted = sum(1 for c in SEATTLE_CONTEXT.pack.claims if c.assertion)
    fresh = portal_summary(SEATTLE_CONTEXT)
    assert f"{asserted} `passed`" in fresh and "`stale`" not in fresh
    assert '"unchecked"' not in fresh, "no longer claims every claim is unchecked"
    stale = portal_summary(_checked(SEATTLE_CONTEXT, "tazs-3rd5-sector-place", 181))
    assert "1 `stale`" in stale and f"{asserted - 1} `passed`" in stale


_RANK = {"none": 0, "profiled": 1, "reviewed": 2}


def test_staleness_never_raises_a_level():  # Ruling 42
    from opendata_atlas.portals.knowledge import dataset_knowledge, pack_levels

    stale = SEATTLE_CONTEXT
    for c in SEATTLE_CONTEXT.pack.claims:
        if c.assertion:
            stale = _checked(stale, c.id, 181)
    assert any(c.assertion for c in SEATTLE_CONTEXT.pack.claims)
    fresh_levels = pack_levels(SEATTLE_CONTEXT, today=TODAY)
    stale_levels = pack_levels(stale, today=TODAY)
    assert fresh_levels.keys() == stale_levels.keys()
    for dataset_id, fresh_level in fresh_levels.items():
        assert _RANK[stale_levels[dataset_id]] <= _RANK[fresh_level], dataset_id
    crime = ["neighborhood", "precinct", "sector", "beat"]
    for ctx in (SEATTLE_CONTEXT, stale):
        level = dataset_knowledge(ctx, CRIME, crime, "report_date_time", today=TODAY).level
        assert level == "none", "stale sector on SPD Crime reads as fresh SPD Crime does"


def test_served_placeholder_sentence_matches_the_code():
    from opendata_atlas.core.reference import CAPABILITIES

    assert (
        "a stale placeholder declaration no longer removes its values: they stay in `values` "
        "and are listed in `candidate_placeholders`, `assigned_fraction` is omitted, and "
        "`placeholder_values` keeps only what a fresh declaration removes"
    ) in CAPABILITIES
    assert "no longer removes values from `values` or `assigned_fraction`" not in CAPABILITIES


async def test_stale_only_fields_publish_only_stale(tools_list):
    def walk(node: Any, path: str):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "validation" and "knowledge" not in path:
                    yield path, value
                yield from walk(value, f"{path}/{key}")
        elif isinstance(node, list):
            for item in node:
                yield from walk(item, path)

    found = {
        path: schema
        for tool in tools_list["tools"]
        for path, schema in walk(tool.get("outputSchema", {}), tool["name"])
    }
    assert len(found) == 3, found
    for path, schema in found.items():
        assert schema.get("enum") == ["stale"] or schema.get("const") == "stale", (path, schema)


@pytest.mark.soda_fixture("describe_fire_full")
async def test_stale_layer_lowers_the_summary_as_describe(
    client, soda, monkeypatch: pytest.MonkeyPatch
):
    """Final review M-1: a stale `ok` region layer lowers describe; the summary agrees."""
    from opendata_atlas.mcp import tools
    from opendata_atlas.portals.knowledge import pack_levels

    fire = "kzjm-xkqj"
    layer = _claim("region-ru88-fbhk")
    asserted = Claim.model_validate(
        {
            **layer.model_dump(mode="json", exclude_none=True),
            "evidence": [
                {
                    "kind": "metadata_probe",
                    "path": "/api/views/ru88-fbhk.json",
                    "observed_at": "2026-10-18",
                    "observation": "test fixture",
                }
            ],
            "assertion": [
                {
                    "checker": "metadata_before",
                    "probe": 0,
                    "params": {"field": "rowsUpdatedAt", "before": "2017-01-01"},
                }
            ],
        }
    )
    with_layer = _with_claims(SEATTLE_CONTEXT, asserted, drop=(layer.id,))
    stale = _checked(with_layer, layer.id, 181)
    monkeypatch.setattr(tools, "resolve_portal", lambda value: stale)
    out = wire(
        await client.call_tool_mcp(
            "atlas_describe_dataset", {"portal": "seattle", "dataset_id": fire, "detail": "full"}
        )
    )["structuredContent"]
    assert pack_levels(with_layer, today=TODAY)[fire] == "reviewed", "fresh layer (known positive)"
    assert out["knowledge"]["level"] != "reviewed", "the stale layer lowers describe"
    assert pack_levels(stale, today=TODAY)[fire] == out["knowledge"]["level"]


# Milestone 4 Task 1 (carry-over M-1, ruling 73): `pack_levels` maps each dataset to its own
# region layers. Each case builds Seattle plus synthetic claims for dataset `synt-0001`, and
# checks the summary against what describe computes for a schema exposing `A_COL`.
SYNT = "synt-0001"
A_COL, A_LAYER = ":@computed_region_aaaa_1111", "aaaa-1111"
B_COL, B_LAYER = ":@computed_region_bbbb_2222", "bbbb-2222"
_EXAMPLES = Path(__file__).resolve().parent.parent / "docs" / "pack-examples"


def _example(kind: str, claim_id: str, scope: dict[str, str], *, reviewed: bool) -> Claim:
    """The `docs/pack-examples/<kind>.toml` claim, re-scoped. Unreviewed, it is an
    observation: no review and no interpretation."""
    fields = tomllib.loads((_EXAMPLES / f"{kind}.toml").read_text())["claim"][0]
    fields = {**fields, "id": claim_id, "scope": scope}
    if not reviewed:
        fields = {
            k: v
            for k, v in fields.items()
            if k not in ("reviewed_by", "reviewed_at", "interpretation")
        }
    return Claim.model_validate(fields)


def _fill(dataset_id: str, column: str) -> Claim:
    """The profiler's fill observation: a `place_field` with no interpretation."""
    return Claim.model_validate(
        {
            "id": f"{dataset_id}-{column}-fill",
            "kind": "place_field",
            "scope": {"dataset": dataset_id, "column": column},
            "evidence": [_PROBE],
        }
    )


def _layer(layer_id: str, *, reviewed: bool) -> Claim:
    return _example("region_layer", f"region-{layer_id}", {"layer": layer_id}, reviewed=reviewed)


def _synthetic(*claims: Claim) -> PortalContext:
    """Seattle plus `claims` and `synt-0001`'s reviewed unit and `created_date` timezone."""
    unit = _example("unit_of_observation", f"{SYNT}-unit", {"dataset": SYNT}, reviewed=True)
    tz = _example(
        "column_timezone",
        f"{SYNT}-created-tz",
        {"dataset": SYNT, "column": "created_date"},
        reviewed=True,
    )
    return _with_claims(SEATTLE_CONTEXT, unit, tz, *claims)


#: `synt-0001`'s schema: `created_date` and `A_COL`, computed against layer `aaaa-1111`.
_SYNT_VIEW = {
    "id": SYNT,
    "name": "Synthetic",
    "assetType": "dataset",
    "viewType": "tabular",
    "columns": [
        {"fieldName": "created_date", "dataTypeName": "floating_timestamp"},
        {
            "fieldName": A_COL,
            "dataTypeName": "number",
            "computationStrategy": {"parameters": {"region": f"_{A_LAYER}"}},
        },
    ],
}


def _synt_upstream(request: httpx.Request) -> httpx.Response:
    """`synt-0001`'s view, its row count and its `created_date` range; nothing else."""
    path, select = request.url.path, request.url.params.get("$select", "")
    if path == f"/api/views/{SYNT}.json":
        return httpx.Response(200, json=_SYNT_VIEW)
    if path == f"/resource/{SYNT}.json" and select == "count(*) AS n":
        return httpx.Response(200, json=[{"n": "10"}])
    if path == f"/resource/{SYNT}.json" and select.startswith("min(created_date)"):
        span = {"lo": "2026-01-01T00:00:00", "hi": "2026-10-01T00:00:00"}
        return httpx.Response(200, json=[span])
    raise AssertionError(f"unexpected request {request.url}")


async def _describe_level(ctx: PortalContext) -> str:
    """The level describe itself reports for `synt-0001`, from the schema above."""
    result = await describe.describe(
        SodaClient(transport=httpx.MockTransport(_synt_upstream)),
        ctx,
        dataset_id=SYNT,
        column_query=None,
        sample_rows=0,
        detail="summary",
    )
    assert result.knowledge is not None
    return result.knowledge.level


async def test_pack_levels_ignores_layers_a_dataset_does_not_expose():
    """Over-reach: another dataset's unreviewed layer no longer lowers this one."""
    from opendata_atlas.portals.knowledge import pack_levels

    ctx = _synthetic(
        _fill(SYNT, A_COL),
        _layer(A_LAYER, reviewed=True),
        _layer(B_LAYER, reviewed=False),
        _fill("synt-0002", B_COL),
    )
    assert pack_levels(ctx, today=TODAY)[SYNT] == "reviewed" == await _describe_level(ctx)


async def test_pack_levels_counts_a_datasets_own_unreviewed_layer():
    """Under-reach: a layer with no claim keeps the dataset below `reviewed`, as describe."""
    from opendata_atlas.portals.knowledge import pack_levels

    ctx = _synthetic(_fill(SYNT, A_COL))
    assert pack_levels(ctx, today=TODAY)[SYNT] == "profiled" == await _describe_level(ctx)


async def test_pack_levels_lets_a_reviewed_place_field_override_its_layer():
    """Ruling 62: the dataset's own reviewed claim on the column governs over its layer."""
    from opendata_atlas.portals.knowledge import pack_levels

    place = _example(
        "place_field", f"{SYNT}-a-place", {"dataset": SYNT, "column": A_COL}, reviewed=True
    )
    ctx = _synthetic(place, _layer(A_LAYER, reviewed=False))
    assert pack_levels(ctx, today=TODAY)[SYNT] == "reviewed" == await _describe_level(ctx)


async def test_pack_levels_fallback_reads_higher_for_a_layer_the_pack_does_not_claim():
    """Documented caveat (Task 6): a dataset with no computed-region claim of its own falls
    back to the pack's layers, so a schema column on a layer the pack never claims lowers
    describe but not the summary. Describe governs."""
    from opendata_atlas.portals.knowledge import pack_levels

    ctx = _synthetic()
    assert A_LAYER not in {c.scope.layer for c in ctx.pack.claims if c.kind == "region_layer"}
    assert pack_levels(ctx, today=TODAY)[SYNT] == "reviewed"
    assert await _describe_level(ctx) == "none"


def test_pack_levels_seattle_unchanged():
    from opendata_atlas.portals.knowledge import pack_levels

    assert pack_levels(SEATTLE_CONTEXT, today=TODAY) == {
        "33kz-ixgy": "reviewed",
        "65db-xm6k": "none",
        "76t5-zqzr": "none",
        "kzjm-xkqj": "reviewed",
        "ppi5-g2bj": "none",
        "tazs-3rd5": "none",
    }
