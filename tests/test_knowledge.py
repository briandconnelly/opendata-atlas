"""Milestone 2 Task 9: knowledge levels and notices, place kinds, candidate placeholders.

`docs/design.md` Knowledge levels and Place fields are the spec. Re-record the query fixture
with `RECORD_FIXTURES=1 uv run pytest tests/test_knowledge.py`.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from typing import Any, get_args

import httpx
import jsonschema
import pytest

from opendata_atlas.core import cache, describe, query
from opendata_atlas.core.http import SodaClient, set_client
from opendata_atlas.portals.knowledge import (
    SHARED_PLACEHOLDERS,
    column_knowledge,
    dataset_knowledge,
    knowledge_notice,
)
from opendata_atlas.portals.model import Claim, Pack, PlaceKind, PortalContext
from tests.conftest import SEATTLE_CONTEXT, wire

TOOL = "atlas_query_dataset"
SPD = "33kz-ixgy"
ROAD_WEATHER = "egc4-d24i"  # a Seattle dataset the pack has no claim on
_EVIDENCE = [
    {"kind": "manual_observation", "note": "test fixture", "observed_at": date(2026, 10, 18)}
]
#: The conftest's pinned clock.
TODAY = date(2026, 10, 18)
# The notice's closing sentence, pinned literally (ruling 68).
GAP_OFFER = (
    "When you caveat a gap named here, also offer the user a knowledge-gap issue "
    "(capabilities ## Knowledge gaps); never file one unasked."
)


def ctx(pack: Pack) -> PortalContext:
    """A Seattle-identity context holding only `pack`, with no checks."""
    return replace(SEATTLE_CONTEXT, pack=pack, checks={})


def claim(
    claim_kind: str, /, *, column: str | None = None, reviewed: bool = True, **interp: Any
) -> Claim:
    data: dict[str, Any] = {
        "id": f"t.{claim_kind}.{column}.{reviewed}",
        "kind": claim_kind,
        "scope": {"dataset": "d1", "column": column} if column else {"dataset": "d1"},
        "evidence": _EVIDENCE,
    }
    if reviewed:
        data |= {"interpretation": interp, "reviewed_by": "test", "reviewed_at": date(2026, 10, 18)}
    return Claim.model_validate(data)


@pytest.fixture
def unit_place_time() -> tuple[Claim, Claim, Claim]:
    return (
        claim("unit_of_observation", unit="dispatch"),
        claim("place_field", column="hood", kind="neighborhood", reliability="ok"),
        claim("column_timezone", column="when", timezone="America/Los_Angeles"),
    )


def level(*claims: Claim, primary: str | None = "when") -> str:
    return dataset_knowledge(
        ctx(Pack(claims=list(claims))), "d1", ["hood"], primary, today=TODAY
    ).level


async def q(client, tools_list, args):
    result = wire(await client.call_tool_mcp(TOOL, args))
    assert result["isError"] is False, result["structuredContent"]
    schema = next(t["outputSchema"] for t in tools_list["tools"] if t["name"] == TOOL)
    jsonschema.validate(result["structuredContent"], schema)
    return result["structuredContent"]


def test_reviewed_requires_unit_place_and_time(unit_place_time):
    UNIT, PLACE, TIME = unit_place_time
    assert level(UNIT, PLACE, TIME) == "reviewed"
    for missing in (UNIT, PLACE, TIME):
        assert level(*[c for c in (UNIT, PLACE, TIME) if c is not missing]) != "reviewed"
    # No time column at all: nothing to review for it.
    assert level(UNIT, PLACE, primary=None) == "reviewed"
    knowledge = dataset_knowledge(
        ctx(Pack(claims=[UNIT, PLACE, TIME])), "d1", ["hood"], "when", today=TODAY
    )
    assert knowledge.validation == "unchecked", "these claims carry no assertions"
    # Seattle: SPD Call Data has a recorded unit, four reviewed place fields and a reviewed
    # primary time column; SPD Crime has a unit but no reviewed time column.
    spd = ["dispatch_neighborhood", "dispatch_precinct", "dispatch_sector", "dispatch_beat"]
    seattle = SEATTLE_CONTEXT
    primary = "cad_event_original_time_queued"
    assert dataset_knowledge(seattle, SPD, spd, primary, today=TODAY).level == "reviewed"
    crime = ["neighborhood", "precinct", "sector", "beat"]
    assert (
        dataset_knowledge(seattle, "tazs-3rd5", crime, "report_date_time", today=TODAY).level
        == "none"
    )


def test_partial_claims_are_profiled_or_none(unit_place_time):
    UNIT, PLACE, TIME = unit_place_time
    # Reviewed claims short of the rule, and nothing unreviewed: none.
    assert level(PLACE, TIME) == "none"
    assert level() == "none"
    # A profiler observation (no interpretation) makes it profiled.
    observed = claim("place_field", column="hood", reviewed=False)
    assert level(UNIT, observed, TIME) == "profiled"
    pack = ctx(Pack(claims=[observed, TIME]))
    hood = column_knowledge(pack, "d1", "hood", today=TODAY)
    when = column_knowledge(pack, "d1", "when", today=TODAY)
    assert hood is not None and hood.level == "profiled"
    assert when is not None and when.level == "reviewed"
    assert column_knowledge(pack, "d1", "other", today=TODAY) is None, (
        "set only when a claim covers it"
    )
    # A reviewed placeholder declaration is a reviewed claim, not an observation.
    declared = Claim.model_validate(
        {
            "id": "t.ph",
            "kind": "placeholder_share",
            "scope": {"dataset": "d1", "column": "hood"},
            "placeholders": ["-"],
            "reviewed_by": "test",
            "reviewed_at": date(2026, 10, 18),
            "evidence": _EVIDENCE,
        }
    )
    assert level(PLACE, declared, TIME) == "none"


@pytest.mark.soda_fixture("query_knowledge")
async def test_notice_on_unreviewed_dataset_even_on_curated_portal(client, tools_list, soda):
    assert not [c for c in SEATTLE_CONTEXT.pack.claims if c.scope.dataset == ROAD_WEATHER]
    out = await q(
        client,
        tools_list,
        {
            "portal": "seattle",
            "dataset_id": ROAD_WEATHER,
            "select": ["stationname"],
            "where": "recordid = 1",
            "page_size": 1,
        },
    )
    assert out["source"]["portal"]["tier"] == "curated"
    notice = out["knowledge_notice"]
    assert notice["level"] == "none"
    assert "unit of observation" in notice["message"] and "datetime" in notice["message"]
    caveat = notice["message"].removesuffix(" " + GAP_OFFER)
    assert caveat != notice["message"], "ends with the gap offer (ruling 68)"
    assert caveat.endswith(".") and ". " not in caveat, "one sentence"


@pytest.mark.soda_fixture("query_knowledge")
async def test_no_notice_for_plain_columns_on_reviewed_dataset(client, tools_list, soda):
    out = await q(
        client,
        tools_list,
        {
            "portal": "seattle",
            "dataset_id": SPD,
            "select": ["cad_event_number", "initial_call_type"],
            "where": "cad_event_number = '2026000000001'",
            "page_size": 1,
        },
    )
    assert out.get("knowledge_notice") is None
    # A reviewed place field and the reviewed primary time column carry none either.
    seattle, places = SEATTLE_CONTEXT, {"dispatch_neighborhood": None}
    times = ["cad_event_original_time_queued", "cad_event_arrived_time"]
    used = {"dispatch_neighborhood", "cad_event_original_time_queued"}
    notice = knowledge_notice(
        seattle, SPD, places=places, time_columns=times, referenced=used, today=TODAY
    )
    assert notice is None


@pytest.mark.soda_fixture("query_knowledge")
async def test_notice_for_unreviewed_time_column(client, tools_list, soda):
    out = await q(
        client,
        tools_list,
        {
            "portal": "seattle",
            "dataset_id": SPD,
            "select": ["count(*) AS n"],
            "where": "cad_event_arrived_time > '2026-10-01T00:00:00'",
        },
    )
    notice = out["knowledge_notice"]
    assert notice["level"] == "reviewed", "the dataset is reviewed; the column is not"
    assert "cad_event_arrived_time" in notice["message"]
    assert "cad_event_original_time_queued" not in notice["message"]
    # With no knowledge-bearing column referenced, a reviewed dataset carries no notice.
    times = ["cad_event_original_time_queued", "call_sign_at_scene_time"]
    notice = knowledge_notice(
        SEATTLE_CONTEXT, SPD, places={}, time_columns=times, referenced=set(), today=TODAY
    )
    assert notice is None


def test_candidate_placeholders_exclude_declared_values():
    assert {"-", "UNKNOWN", "NULL", "OOJ", "FK ERROR", "X", "0", ""} == SHARED_PLACEHOLDERS
    groups = describe._Outcome()
    groups.status = "ok"
    groups.value = [
        {"v": "A", "n": "10"},
        {"v": "-", "n": "5"},
        {"v": "UNKNOWN", "n": "3"},
        {"v": "", "n": "1"},
        {"n": "2"},
    ]
    spec = {"column": "hood", "source": "column", "kind": "neighborhood", "reliability": "ok"}
    field = describe._place_field(
        spec, groups, {}, placeholder_values=frozenset({"-"}), stale_placeholders=frozenset()
    )
    assert [(p.value, p.rows) for p in field.candidate_placeholders or []] == [
        ("UNKNOWN", 3),
        ("", 1),
    ]
    # Only the declared value leaves `values` and `assigned_fraction`.
    assert [(p.value, p.rows) for p in field.placeholder_values or []] == [("-", 5), ("null", 2)]
    assert {v.value for v in field.values or []} == {"A", "UNKNOWN", ""}
    assert field.assigned_fraction == round(1 - 7 / 21, 4)
    assert (field.null_rows, field.non_null_rows) == (2, 19)
    # Seattle declares the whole vocabulary on its text place fields: no candidates left.
    seattle = SEATTLE_CONTEXT.pack.placeholders("tazs-3rd5", "neighborhood")
    field = describe._place_field(
        spec, groups, {}, placeholder_values=seattle, stale_placeholders=frozenset()
    )
    assert field.candidate_placeholders is None


def test_new_place_kinds_load():
    new = {"ward", "community_area", "borough", "community_district", "county"}
    new |= {"police_district", "school_district"}
    assert new <= set(get_args(PlaceKind))
    ward = claim(
        "place_field", column="ward", kind="ward", kind_label="City ward", reliability="ok"
    )
    ctx_pack = Pack(claims=[ward])
    specs = describe.place_specs(
        SEATTLE_CONTEXT.__class__(identity=SEATTLE_CONTEXT.identity, pack=ctx_pack),
        "d1",
        [{"fieldName": "ward"}],
        today=TODAY,
    )
    assert specs[0]["kind"] == "ward" and specs[0]["kind_label"] == "City ward"
    field = describe._place_field(
        specs[0], None, {}, placeholder_values=frozenset(), stale_placeholders=frozenset()
    )
    assert (field.kind, field.kind_label) == ("ward", "City ward")


@pytest.mark.parametrize(
    ("clauses", "fires"),
    [
        ({"where": "cad_event_arrived_time > '2026-10-01T00:00:00'"}, True),
        ({"order_by": ["cad_event_arrived_time DESC"]}, True),
        ({"where": "initial_call_type = 'cad_event_arrived_time'"}, False),
        ({"select": ["count(*) AS cad_event_arrived_time"]}, False),
        ({"select": ["initial_call_type"]}, False),
        ({}, False),  # the default select is not scanned
    ],
)
def test_notice_scan_follows_the_coverage_scan(clauses, fires):
    from opendata_atlas.core import query

    where = [f"({clauses['where']})"] if "where" in clauses else []
    used = query._referenced(*query._written(clauses, where))
    times = ["cad_event_original_time_queued", "cad_event_arrived_time"]
    notice = knowledge_notice(
        SEATTLE_CONTEXT, SPD, places={}, time_columns=times, referenced=used, today=TODAY
    )
    assert (notice is not None) is fires


@pytest.mark.soda_fixture("describe_fire_summary")
async def test_describe_reports_dataset_and_column_knowledge(client, tools_list, soda):
    result = wire(
        await client.call_tool_mcp(
            "atlas_describe_dataset", {"portal": "seattle", "dataset_id": "kzjm-xkqj"}
        )
    )
    out = result["structuredContent"]
    schema = next(t for t in tools_list["tools"] if t["name"] == "atlas_describe_dataset")
    jsonschema.validate(out, schema["outputSchema"])
    # Fire 911: reviewed unit of observation, time and region layers (milestone 3 Task 5).
    assert out["knowledge"] == {"level": "reviewed", "validation": "unchecked"}
    by_name = {c["name"]: c.get("knowledge") for c in out["columns"]}
    assert by_name["datetime"] == {"level": "reviewed", "validation": "passed"}
    assert by_name["type"] is None, "no claim covers a plain column"


@pytest.mark.soda_fixture("describe_crime_full")
async def test_describe_full_reports_raw_null_counts(client, tools_list, soda):
    result = wire(
        await client.call_tool_mcp(
            "atlas_describe_dataset",
            {
                "portal": "seattle",
                "dataset_id": "tazs-3rd5",
                "detail": "full",
                "column_query": "zzz",
            },
        )
    )
    hood = next(
        p for p in result["structuredContent"]["place_fields"] if p["column"] == "neighborhood"
    )
    assert "candidate_placeholders" not in hood, "Seattle declares the whole vocabulary"
    assert hood["non_null_rows"] > 1_000_000 and hood["null_rows"] >= 0


# --- Task 9 review, fix round 1 ------------------------------------------------


def _declaration(column: str, *, reviewed: bool) -> Claim:
    data: dict[str, Any] = {
        "id": f"t.ph.{column}.{reviewed}",
        "kind": "placeholder_share",
        "scope": {"dataset": "d1", "column": column},
        "placeholders": ["-"],
        "evidence": _EVIDENCE,
    }
    if reviewed:
        data |= {"reviewed_by": "test", "reviewed_at": date(2026, 10, 18)}
    return Claim.model_validate(data)


def test_unreviewed_declaration_only_flags_candidates():
    pack = Pack(claims=[_declaration("hood", reviewed=False)])
    assert pack.placeholders("d1", "hood") == frozenset()
    groups = describe._Outcome()
    groups.status = "ok"
    groups.value = [{"v": "A", "n": "10"}, {"v": "-", "n": "5"}]
    spec = {"column": "hood", "source": "column", "kind": "neighborhood", "reliability": "ok"}
    field = describe._place_field(
        spec,
        groups,
        {},
        placeholder_values=pack.placeholders("d1", "hood"),
        stale_placeholders=frozenset(),
    )
    assert {v.value for v in field.values or []} == {"A", "-"}
    assert field.assigned_fraction == 1.0
    assert field.placeholder_values is None
    assert [(p.value, p.rows) for p in field.candidate_placeholders or []] == [("-", 5)]


def test_time_column_needs_a_reviewed_timezone_claim(unit_place_time):
    unit, place, time = unit_place_time
    pack = ctx(Pack(claims=[unit, place, time, _declaration("later", reviewed=True)]))
    notice = knowledge_notice(
        pack,
        "d1",
        places={"hood": None},
        time_columns=["when", "later"],
        referenced={"later"},
        today=TODAY,
    )
    assert notice is not None and "`later`" in notice.message
    # Nor does a placeholder declaration make the primary time column reviewed.
    pack = ctx(Pack(claims=[unit, place, _declaration("when", reviewed=True)]))
    assert dataset_knowledge(pack, "d1", ["hood"], "when", today=TODAY).level != "reviewed"


def test_notice_names_what_each_row_counts():
    notice = knowledge_notice(
        ctx(Pack()), "d1", places={}, time_columns=[], referenced=set(), today=TODAY
    )
    assert notice is not None
    assert "what each row counts is unverified" in notice.message
    assert "that row counts" not in notice.message


def test_computed_region_columns_need_their_layers():
    with pytest.raises(ValueError, match="layers"):
        dataset_knowledge(ctx(Pack()), "d1", [":@computed_region_aaaa_bbbb"], None, today=TODAY)


def _layer(*, reviewed: bool) -> Claim:
    data: dict[str, Any] = {
        "id": f"t.layer.{reviewed}",
        "kind": "region_layer",
        "scope": {"layer": "aaaa-bbbb"},
        "evidence": _EVIDENCE,
    }
    if reviewed:
        data |= {
            "interpretation": {"kind": "ward", "reliability": "ok", "label_column": "name"},
            "reviewed_by": "test",
            "reviewed_at": date(2026, 10, 18),
        }
    return Claim.model_validate(data)


def test_dataset_with_computed_regions_only(unit_place_time):
    unit = unit_place_time[0]
    region = ":@computed_region_aaaa_bbbb"
    layers = {region: "aaaa-bbbb"}

    def level_of(*claims: Claim) -> str:
        pack = ctx(Pack(claims=list(claims)))
        return dataset_knowledge(pack, "d1", [region], None, layers=layers, today=TODAY).level

    assert level_of(unit, _layer(reviewed=True)) == "reviewed"
    assert level_of(unit) == "none", "an unreviewed layer has no claim to count"
    assert level_of(unit, _layer(reviewed=False)) == "profiled"


def test_dataset_with_no_place_or_time_columns(unit_place_time):
    unit = unit_place_time[0]
    assert dataset_knowledge(ctx(Pack(claims=[unit])), "d1", [], None, today=TODAY).level == (
        "reviewed"
    )
    assert dataset_knowledge(ctx(Pack()), "d1", [], None, today=TODAY).level == "none"


async def test_filter_view_inherits_its_parents_level():
    from dataclasses import replace

    from opendata_atlas.core.http import SodaClient
    from tests.http_fixtures import Replay

    def reviewed_claim(kind: str, column: str | None, **interp: Any) -> Claim:
        scope = {"dataset": "76t5-zqzr"} | ({"column": column} if column else {})
        return Claim.model_validate(
            {
                "id": f"t.permits.{kind}",
                "kind": kind,
                "scope": scope,
                "interpretation": interp,
                "reviewed_by": "test",
                "reviewed_at": date(2026, 10, 18),
                "evidence": _EVIDENCE,
            }
        )

    extra = [
        reviewed_claim("unit_of_observation", None, unit="permit"),
        reviewed_claim("column_timezone", "applieddate", timezone="America/Los_Angeles"),
    ]
    pack = SEATTLE_CONTEXT.pack.model_copy(
        update={"claims": [*SEATTLE_CONTEXT.pack.claims, *extra]}
    )
    ctx = replace(SEATTLE_CONTEXT, pack=pack)
    client = SodaClient(transport=Replay("describe_filter_view"))
    result = await describe.describe(
        client, ctx, dataset_id="8tqq-u7ib", column_query=None, sample_rows=1, detail="summary"
    )
    assert result.knowledge.level == "reviewed", "the view reads its parent's claims"
    base = await describe.describe(
        SodaClient(transport=Replay("describe_filter_view")),
        SEATTLE_CONTEXT,
        dataset_id="8tqq-u7ib",
        column_query=None,
        sample_rows=1,
        detail="summary",
    )
    assert base.knowledge.level == "none"


@pytest.mark.soda_fixture("describe_fire_summary")
async def test_summary_describe_omits_full_only_place_counts(client, tools_list, soda):
    result = wire(
        await client.call_tool_mcp(
            "atlas_describe_dataset", {"portal": "seattle", "dataset_id": "kzjm-xkqj"}
        )
    )
    fields = result["structuredContent"]["place_fields"]
    assert fields
    for field in fields:
        assert not {"candidate_placeholders", "null_rows", "non_null_rows"} & set(field)


# --- Milestone 3 Task 6: text columns a query filtered on -----------------------

_TEXT_COLUMNS: list[dict[str, Any]] = [
    {"fieldName": "area_name", "dataTypeName": "text"},
    {"fieldName": "crime_type", "dataTypeName": "text"},
    {"fieldName": "date_rptd", "dataTypeName": "floating_timestamp"},
]


def _install_view(columns: list[dict[str, Any]], dataset_id: str) -> None:
    """A fake portal serving `columns` as the dataset's view and one row for any query."""
    view = {"id": dataset_id, "assetType": "dataset", "viewType": "tabular", "columns": columns}

    def handler(request: httpx.Request) -> httpx.Response:
        if "/api/views/" in request.url.path:
            return httpx.Response(200, json=view)
        headers = {
            "X-SODA2-Fields": json.dumps(["n"]),
            "X-SODA2-Types": json.dumps(["number"]),
        }
        return httpx.Response(200, headers=headers, content=b'[{"n":"1",":id":"row-1"}]')

    cache.clear()
    set_client(SodaClient(transport=httpx.MockTransport(handler)))


async def _text_call(client: Any, dataset_id: str, **args: Any) -> dict[str, Any]:
    result = wire(
        await client.call_tool_mcp(
            TOOL, {"portal": "seattle", "dataset_id": dataset_id, "page_size": 1, **args}
        )
    )
    assert result["isError"] is False, result["structuredContent"]
    return result["structuredContent"]


async def test_notice_names_filtered_text_column(client):
    _install_view(_TEXT_COLUMNS, "aaaa-bbbb")
    out = await _text_call(
        client, "aaaa-bbbb", select=["count(*) AS n"], where="area_name = 'Hollywood'"
    )
    message = out["knowledge_notice"]["message"]
    assert "`area_name`" in message and "not a reviewed place field" in message
    assert "`crime_type`" not in message


async def test_notice_names_grouped_only_text_column(client):
    """Ruling 69: grouping a text column to read its values is the exploratory path."""
    _install_view(_TEXT_COLUMNS, "aaaa-bbbb")
    out = await _text_call(
        client, "aaaa-bbbb", select=["area_name", "count(*) AS n"], group_by=["area_name"]
    )
    message = out["knowledge_notice"]["message"]
    assert "`area_name`" in message and "not a reviewed place field" in message
    assert "filtered or grouped here" in message
    assert "`crime_type`" not in message, "neither filtered nor grouped"


async def test_grouped_alias_of_a_text_column_names_the_column(client):
    """Ruling 70: `area_name AS a`, then `group_by ["a"]`, groups area_name."""
    _install_view(_TEXT_COLUMNS, "aaaa-bbbb")
    out = await _text_call(
        client, "aaaa-bbbb", select=["area_name AS a", "count(*) AS n"], group_by=["a"]
    )
    message = out["knowledge_notice"]["message"]
    assert "`area_name`" in message and "filtered or grouped here" in message
    assert "`a`" not in message, "the alias itself is never named"


async def test_grouped_alias_is_not_a_text_column(client):
    _install_view(_TEXT_COLUMNS, "aaaa-bbbb")
    out = await _text_call(
        client,
        "aaaa-bbbb",
        select=["upper(crime_type) AS area_name", "count(*) AS n"],
        group_by=["area_name"],
    )
    message = out["knowledge_notice"]["message"]
    assert "`area_name`" not in message, "the alias, not the column"


async def test_raw_soql_where_text_column_is_named(client):
    _install_view(_TEXT_COLUMNS, "aaaa-bbbb")
    out = await _text_call(
        client,
        "aaaa-bbbb",
        mode="soql",
        soql="SELECT crime_type, count(*) AS n WHERE area_name = 'Hollywood' GROUP BY crime_type",
    )
    message = out["knowledge_notice"]["message"]
    assert "`area_name`" in message and "not reviewed place fields" in message
    assert "`area_name`, `crime_type`" in message, "raw GROUP BY names its text column too"


async def test_no_extra_sentence_with_a_reviewed_place_field(client):
    columns = [
        {"fieldName": "offense_category", "dataTypeName": "text"},
        {"fieldName": "neighborhood", "dataTypeName": "text"},
        {"fieldName": "report_date_time", "dataTypeName": "floating_timestamp"},
    ]
    _install_view(columns, "tazs-3rd5")
    out = await _text_call(
        client, "tazs-3rd5", select=["count(*) AS n"], where="offense_category = 'X'"
    )
    notice = out.get("knowledge_notice")
    assert notice is None or "filtered or grouped here" not in notice["message"]


async def test_no_extra_sentence_for_a_grouped_reviewed_place_field(client):
    columns = [
        {"fieldName": "offense_category", "dataTypeName": "text"},
        {"fieldName": "neighborhood", "dataTypeName": "text"},
        {"fieldName": "report_date_time", "dataTypeName": "floating_timestamp"},
    ]
    _install_view(columns, "tazs-3rd5")
    out = await _text_call(
        client,
        "tazs-3rd5",
        select=["neighborhood", "offense_category", "count(*) AS n"],
        group_by=["neighborhood", "offense_category"],
    )
    notice = out.get("knowledge_notice")
    assert notice is None or "filtered or grouped here" not in notice["message"]


def test_text_sentence_fires_on_reviewed_dataset_and_lists_overflow():
    names = ["a", "b", "c", "d", "e"]
    notice = knowledge_notice(
        SEATTLE_CONTEXT,
        SPD,
        places={},
        time_columns=[],
        referenced=set(),
        today=TODAY,
        text_filters=names,
    )
    assert notice is not None and notice.level == "reviewed"
    assert "`a`, `b`, `c` (+2 more)" in notice.message
    assert notice.message.endswith(f"unverified. {GAP_OFFER}")


def test_text_sentence_absent_when_a_reviewed_place_backs_the_dataset():
    notice = knowledge_notice(
        SEATTLE_CONTEXT,
        SPD,
        places={"dispatch_neighborhood": None},
        time_columns=["cad_event_original_time_queued"],
        referenced=set(),
        today=TODAY,
        text_filters=["initial_call_type"],
    )
    assert notice is None


def test_text_filters_are_sorted_text_columns_in_where():
    columns = [*_TEXT_COLUMNS, {"fieldName": "n", "dataTypeName": "number"}]
    assert query._text_filters("crime_type = 'x' AND area_name = 'y' AND n > 1", columns) == [
        "area_name",
        "crime_type",
    ]
    assert query._soql_where("SELECT a WHERE b = 'WHERE c' GROUP BY d") == " b =   "
    grouped = query._text_filters(
        "n > 1", columns, group_by="area_name, upper(crime_type)", select="n AS x"
    )
    assert grouped == ["area_name", "crime_type"]

    # Ruling 70: a grouped select alias resolves to the column(s) its expression reads.
    def by_alias(select: str) -> list[str]:
        return query._text_filters("", columns, group_by="a", select=select)

    assert by_alias("area_name AS a") == ["area_name"], "alias of a bare text column"
    assert by_alias("upper(crime_type) AS a, count(*) AS n") == ["crime_type"]
    assert by_alias("count(*) AS a") == [], "an expression reading no column names none"
    assert by_alias("n AS a") == [], "a number column is not a text column"
    assert query._text_filters(
        "", columns, group_by="area_name", select="crime_type AS area_name"
    ) == ["crime_type"], "the alias, resolved, not the like-named column"
    assert (
        query._soql_clause("SELECT a WHERE b = 1 GROUP BY c, d ORDER BY c", "group by") == " c, d "
    )


def test_fired_notice_ends_with_the_gap_offer_once():
    """Ruling 68: a fired notice points at the knowledge-gap offer, once, after its caveats."""
    gap_only = knowledge_notice(
        SEATTLE_CONTEXT,
        ROAD_WEATHER,
        places={},
        time_columns=["datetime"],
        referenced=set(),
        today=TODAY,
    )
    text_only = knowledge_notice(
        SEATTLE_CONTEXT,
        SPD,
        places={},
        time_columns=[],
        referenced=set(),
        today=TODAY,
        text_filters=["a"],
    )
    both = knowledge_notice(
        SEATTLE_CONTEXT,
        ROAD_WEATHER,
        places={},
        time_columns=["datetime"],
        referenced=set(),
        today=TODAY,
        text_filters=["stationname"],
    )
    for notice in (gap_only, text_only, both):
        assert notice is not None
        assert notice.message.endswith(" " + GAP_OFFER)
        assert notice.message.count(GAP_OFFER) == 1
    assert len(GAP_OFFER) <= 140


@pytest.mark.soda_fixture("query_knowledge")
async def test_gap_offer_absent_when_no_notice_fires(client, tools_list, soda):
    out = await q(
        client,
        tools_list,
        {
            "portal": "seattle",
            "dataset_id": SPD,
            "select": ["cad_event_number", "initial_call_type"],
            "where": "cad_event_number = '2026000000001'",
            "page_size": 1,
        },
    )
    assert out.get("knowledge_notice") is None
    assert "knowledge-gap issue" not in json.dumps(out)
