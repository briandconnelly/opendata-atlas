"""Milestone 2: catalog search and describe against recorded data.seattle.gov responses.

Re-record with `RECORD_FIXTURES=1 uv run pytest tests/test_search_describe.py`.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import jsonschema
import pytest

from opendata_atlas.constants import TIME_TYPES
from opendata_atlas.core import describe
from tests.conftest import SEATTLE_CONTEXT, wire


async def call(client, tool, args):
    return wire(await client.call_tool_mcp(tool, args))


def ok(result, tools_list, tool):
    assert result["isError"] is False, result["structuredContent"]
    schema = next(t["outputSchema"] for t in tools_list["tools"] if t["name"] == tool)
    jsonschema.validate(result["structuredContent"], schema)
    return result["structuredContent"]


# --- search ------------------------------------------------------------------


@pytest.mark.soda_fixture("search_fire")
async def test_search_uses_catalog_alias_and_tabular_scope(client, tools_list, soda):
    out = ok(
        await call(
            client,
            "atlas_search_datasets",
            {"portal": "seattle", "query": "fire 911", "page_size": 3},
        ),
        tools_list,
        "atlas_search_datasets",
    )
    fire = next(d for d in out["datasets"] if d["dataset_id"] == "kzjm-xkqj")
    assert fire["queryability"] == "supported"
    assert fire["portal_url"].startswith("https://data.seattle.gov/")
    assert "description" not in fire, "descriptions are full-detail only"
    if hasattr(soda, "requests"):
        # The external-asset lookup runs concurrently, so the primary request is not always first.
        primary = [r for r in soda.requests if "dataset,filter" in r]
        assert len(primary) == 1 and "cos-data.seattle.gov" in primary[0]


@pytest.mark.soda_fixture("search_all_pages")
async def test_search_all_scope_pages_and_marks_external(client, tools_list, soda):
    tool = "atlas_search_datasets"
    first = ok(
        await call(
            client,
            tool,
            {"portal": "seattle", "query": "neighborhood", "asset_scope": "all", "page_size": 4},
        ),
        tools_list,
        tool,
    )
    external = [d for d in first["datasets"] if d["queryability"] == "external"]
    assert external, "federated ArcGIS entries appear in scope=all"
    assert all(d["external_url"].startswith("https://") for d in external)
    assert all(d["asset_type"] not in ("map", "chart") for d in first["datasets"])
    assert first["has_more"] is True and first["next_cursor"]

    second = ok(
        await call(client, tool, {"portal": "seattle", "cursor": first["next_cursor"]}),
        tools_list,
        tool,
    )
    assert {d["dataset_id"] for d in second["datasets"]}.isdisjoint(
        d["dataset_id"] for d in first["datasets"]
    )


async def test_search_rejects_tampered_cursor(client):
    result = await call(
        client, "atlas_search_datasets", {"portal": "seattle", "cursor": "eyJ4IjoxfQ.AAAA"}
    )
    envelope = result["structuredContent"]
    assert result["isError"] is True
    assert envelope["code"] == "cursor_expired"
    assert envelope["repair"]["next_step"] == "read_paging"
    assert envelope["repair"]["tool"] == "atlas_get_reference"
    assert envelope["repair"]["arguments"] == {"topic": "soql", "item_id": "paging"}


async def test_search_rejects_malformed_cursor(client):
    result = await call(
        client, "atlas_search_datasets", {"portal": "seattle", "cursor": "not-a-cursor"}
    )
    assert result["structuredContent"]["code"] == "invalid_cursor"


# --- describe ----------------------------------------------------------------


def test_spd_time_semantics_and_coverage_use_primary_time_column():
    fixture = Path(__file__).parent / "fixtures/http/query_spd_view.json"
    view = json.loads(fixture.read_text())["data.seattle.gov/api/views/33kz-ixgy.json?[]"]["body"]
    time_columns = [c for c in view["columns"] if c["dataTypeName"] in TIME_TYPES]
    column = time_columns[0]
    assert column["fieldName"] == "cad_event_original_time_queued"
    semantics = describe._time(SEATTLE_CONTEXT, "33kz-ixgy", column, date(2026, 10, 18))
    assert semantics.timezone == "America/Los_Angeles" and semantics.evidence
    assert describe._coverage_columns(
        SEATTLE_CONTEXT, "33kz-ixgy", time_columns, date(2026, 10, 18)
    ) == [column]


@pytest.mark.soda_fixture("describe_fire_summary")
async def test_describe_summary(client, tools_list, soda):
    out = ok(
        await call(
            client, "atlas_describe_dataset", {"portal": "seattle", "dataset_id": "kzjm-xkqj"}
        ),
        tools_list,
        "atlas_describe_dataset",
    )
    assert out["row_count"]["origin"] == "live_query" and out["row_count"]["value"] > 2_000_000
    coverage = out["data_coverage"][0]
    assert coverage["column"] == "datetime" and coverage["max"] > coverage["min"]
    assert {"name": "report_location", "type": "point"} in out["columns"]
    assert all(set(c) - {"knowledge"} == {"name", "type"} for c in out["columns"]), (
        "summary columns are name+type, plus knowledge where a claim covers the column"
    )
    assert {"column": "report_location", "type": "point"} in out["geo_columns"]
    kinds = {p["column"]: (p["kind"], p["reliability"]) for p in out["place_fields"]}
    assert kinds[":@computed_region_ru88_fbhk"] == ("neighborhood", "ok")
    assert kinds[":@computed_region_cyqu_gs94"] == ("council_district", "unreliable")
    assert all("values" not in p for p in out["place_fields"]), "values are full-detail only"
    tz = next(t for t in out["time_semantics"] if t["column"] == "datetime")
    assert tz["timezone"] == "America/Los_Angeles" and tz["evidence"]
    assert out["source"]["now_local"]


@pytest.mark.soda_fixture("describe_fire_full")
async def test_describe_full_resolves_region_labels(client, tools_list, soda):
    out = ok(
        await call(
            client,
            "atlas_describe_dataset",
            {
                "portal": "seattle",
                "dataset_id": "kzjm-xkqj",
                "detail": "full",
                "column_query": "type",
            },
        ),
        tools_list,
        "atlas_describe_dataset",
    )
    assert [c["name"] for c in out["columns"]] == ["type"]
    stats = out["columns"][0]["stats"]
    assert stats["top"][0] == "Aid Response" and stats["origin"] == "cached_metadata"
    assert "cardinality" not in stats

    mcpp = next(p for p in out["place_fields"] if p["column"] == ":@computed_region_ru88_fbhk")
    labels = {v["label"]: v["value"] for v in mcpp["values"]}
    assert labels["CAPITOL HILL"] == "8" and labels["NORTH CAPITOL HILL"] == "44"
    assert mcpp["assigned_fraction"] > 0.99
    assert mcpp["label_column"] == "name" and mcpp["boundary_vintage"]

    council = next(p for p in out["place_fields"] if p["column"] == ":@computed_region_cyqu_gs94")
    assert council["assigned_fraction"] < 0.2
    assert council["reliability"] == "unreliable"


@pytest.mark.soda_fixture("describe_crime_full")
async def test_describe_reports_placeholder_share(client, tools_list, soda):
    out = ok(
        await call(
            client,
            "atlas_describe_dataset",
            {
                "portal": "seattle",
                "dataset_id": "tazs-3rd5",
                "detail": "full",
                "column_query": "zzz",
            },
        ),
        tools_list,
        "atlas_describe_dataset",
    )
    assert out["columns"] == []
    hood = next(p for p in out["place_fields"] if p["column"] == "neighborhood")
    assert hood["reliability"] == "partial"
    dash = next(v for v in hood["placeholder_values"] if v["value"] == "-")
    assert dash["rows"] > 500_000
    assert 0.4 < hood["assigned_fraction"] < 0.65
    assert all(v["label"] not in ("-", "UNKNOWN") for v in hood["values"])


@pytest.mark.soda_fixture(
    "describe_fire_summary", overrides={"count%28%2A%29": "timeout", "count(*)": "timeout"}
)
async def test_describe_row_count_timeout_falls_back_to_cache(client, tools_list, soda):
    out = ok(
        await call(
            client, "atlas_describe_dataset", {"portal": "seattle", "dataset_id": "kzjm-xkqj"}
        ),
        tools_list,
        "atlas_describe_dataset",
    )
    assert out["row_count"]["status"] == "timeout"
    assert out["row_count"]["origin"] == "cached_metadata"
    assert out["row_count"]["value"] > 0


@pytest.mark.soda_fixture("describe_fire_full")
async def test_fire_describe_serves_medical_unit(client, tools_list, soda):
    out = ok(
        await call(
            client,
            "atlas_describe_dataset",
            {
                "portal": "seattle",
                "dataset_id": "kzjm-xkqj",
                "detail": "full",
                "column_query": "type",
            },
        ),
        tools_list,
        "atlas_describe_dataset",
    )
    unit = out["unit_of_observation"]
    assert unit["unit"] == "dispatch" and "medical" in unit["reason"]
    assert "lower bound" in unit["reason"], "five named types do not cover every medical type"
    assert out["knowledge"]["level"] == "reviewed"


@pytest.mark.soda_fixture("query_three_rows")
async def test_fire_query_loses_unit_notice(client, tools_list, soda):
    args = {"portal": "seattle", "dataset_id": "kzjm-xkqj", "select": ["incident_number"]}
    args |= {"where": "incident_number in ('F260124133', 'F260124199', 'F260124257')"}
    out = ok(
        await call(client, "atlas_query_dataset", {**args, "page_size": 1}),
        tools_list,
        "atlas_query_dataset",
    )
    assert out["returned_rows"] == 1
    assert "knowledge_notice" not in out, "Fire 911 is reviewed, unit of observation included"


# Every upstream data request times out: the view alone decides the unit.
@pytest.mark.soda_fixture("query_knowledge", overrides={"/resource/egc4-d24i": "timeout"})
async def test_unit_absent_without_reviewed_claim(client, tools_list, soda):
    out = ok(
        await call(
            client, "atlas_describe_dataset", {"portal": "seattle", "dataset_id": "egc4-d24i"}
        ),
        tools_list,
        "atlas_describe_dataset",
    )
    assert "unit_of_observation" not in out
    assert out["knowledge"]["level"] == "none"


@pytest.mark.soda_fixture("describe_crime_full")
async def test_crime_describe_serves_offense_unit(client, tools_list, soda):
    out = ok(
        await call(
            client,
            "atlas_describe_dataset",
            {
                "portal": "seattle",
                "dataset_id": "tazs-3rd5",
                "detail": "full",
                "column_query": "zzz",
            },
        ),
        tools_list,
        "atlas_describe_dataset",
    )
    assert out["unit_of_observation"] == {"unit": "offense"}, "a claim without a reason omits it"


@pytest.mark.soda_fixture("describe_filter_view")
async def test_describe_filter_view_inherits_parent_facts(client, tools_list, soda):
    out = ok(
        await call(
            client,
            "atlas_describe_dataset",
            {"portal": "seattle", "dataset_id": "8tqq-u7ib", "sample_rows": 1},
        ),
        tools_list,
        "atlas_describe_dataset",
    )
    assert [p["column"] for p in out["place_fields"]] == ["originalzip"]
    assert {"column": "location1", "type": "point"} in out["geo_columns"]
    row = out["sample_rows"][0]
    assert set(row) == {c["name"] for c in out["columns"]}, (
        "sample rows carry every column, nulls included"
    )


async def test_filter_view_inherits_parent_unit():
    from opendata_atlas.core.http import SodaClient
    from tests.conftest import with_unit
    from tests.http_fixtures import Replay

    async def unit_of(ctx):
        client = SodaClient(transport=Replay("describe_filter_view"))
        try:
            out = await describe.describe(
                client, ctx, dataset_id="8tqq-u7ib", column_query=None, sample_rows=0, detail=None
            )
        finally:
            await client.aclose()
        return out.unit_of_observation

    # 8tqq-u7ib is a filter view of 76t5-zqzr; only the parent carries the claim.
    unit = await unit_of(with_unit(SEATTLE_CONTEXT, dataset="76t5-zqzr", unit="permit"))
    assert unit is not None and unit.unit == "permit"
    assert await unit_of(SEATTLE_CONTEXT) is None, "the shipped parent has no unit claim"


@pytest.mark.soda_fixture("describe_not_queryable")
async def test_describe_federated_and_map_views(client, soda):
    federated = (
        await call(
            client, "atlas_describe_dataset", {"portal": "seattle", "dataset_id": "w3qt-9btr"}
        )
    )["structuredContent"]
    assert federated["code"] == "dataset_not_queryable"
    assert "arcgis.com" in federated["repair"]["alternative"]

    view = (
        await call(
            client, "atlas_describe_dataset", {"portal": "seattle", "dataset_id": "5rc4-5s78"}
        )
    )["structuredContent"]
    assert view["code"] == "dataset_not_queryable"
    assert view["repair"]["arguments"] == {"portal": "data.seattle.gov", "dataset_id": "76t5-zqzr"}


@pytest.mark.soda_fixture("describe_missing")
async def test_describe_missing_dataset(client, soda):
    result = await call(
        client, "atlas_describe_dataset", {"portal": "seattle", "dataset_id": "abcd-1234"}
    )
    envelope = result["structuredContent"]
    assert result["isError"] is True
    assert envelope["code"] == "dataset_not_found"
    assert envelope["repair"]["tool"] == "atlas_search_datasets"


@pytest.mark.soda_fixture("describe_missing", overrides={"abcd-1234": (503, {"message": "down"})})
async def test_describe_upstream_outage_is_temporary(client, soda):
    envelope = (
        await call(
            client, "atlas_describe_dataset", {"portal": "seattle", "dataset_id": "abcd-1234"}
        )
    )["structuredContent"]
    assert envelope["code"] == "upstream_unavailable"
    assert envelope["temporary"] is True
