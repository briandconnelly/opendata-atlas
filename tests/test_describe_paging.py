"""Describe column paging and `describe_too_large` (milestone 2, Task 10).

The wide views are synthetic: a mock transport serves a generated view and a row count.
Seattle's recorded fixtures prove the common case is unchanged.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import jsonschema
import pytest

from opendata_atlas.core import cursor as cursors
from opendata_atlas.core.budget import RESULT_LIMIT
from opendata_atlas.core.errors import Repair
from opendata_atlas.core.http import SodaClient, set_client
from tests.conftest import wire
from tests.wide_views import PAD, WIDE, WIDE_ARGS, serve_columns, serve_wide, wide_column

TOOL = "atlas_describe_dataset"


def _too_large(*, place: bool) -> None:
    """Geo columns alone exceed the budget; they are never paged."""
    columns = [wide_column(i) for i in range(5)]
    columns += [
        {
            "fieldName": f"a_remarkably_long_geographic_column_name_for_padding_{i:03d}",
            "name": f"geo {i}",
            "dataTypeName": "point",
        }
        for i in range(300)
    ]
    if place:
        columns.insert(
            2,
            {
                "fieldName": ":@computed_region_abcd_efgh",
                "name": "Region",
                "dataTypeName": "number",
                "computationStrategy": {"parameters": {"region": "_abcd-efgh"}},
            },
        )
    serve_columns(columns)


async def describe(client, **extra: Any) -> dict[str, Any]:
    return wire(await client.call_tool_mcp(TOOL, {**WIDE_ARGS, **extra}))


def size(result: dict[str, Any]) -> int:
    """Bytes of structuredContent, the measure describe packs against."""
    return len(
        json.dumps(result["structuredContent"], separators=(",", ":"), ensure_ascii=False).encode()
    )


def names(out: dict[str, Any]) -> list[str]:
    return [c["name"] for c in out["columns"]]


@pytest.mark.parametrize(("detail", "cap"), [("summary", 100), ("full", 25)])
async def test_wide_schema_pages_columns_within_budget(client, tools_list, detail, cap):
    serve_wide()
    result = await describe(client, detail=detail)
    assert result["isError"] is False, result["structuredContent"]
    out = result["structuredContent"]
    schema = next(t["outputSchema"] for t in tools_list["tools"] if t["name"] == TOOL)
    jsonschema.validate(out, schema)
    assert out["columns_total"] == 300
    assert out["has_more_columns"] is True and out["next_column_cursor"]
    assert 0 < len(out["columns"]) <= cap
    assert size(result) <= RESULT_LIMIT


async def walk(client, **extra: Any) -> tuple[list[str], int]:
    """Every column name across all pages, and the page count."""
    page = await describe(client, **extra)
    seen: list[str] = []
    pages = 0
    while True:
        out = page["structuredContent"]
        assert page["isError"] is False, out
        assert size(page) <= RESULT_LIMIT
        seen += names(out)
        pages += 1
        if not out["has_more_columns"]:
            assert "next_column_cursor" not in out
            return seen, pages
        page = await describe(
            client,
            column_cursor=out["next_column_cursor"],
            **{k: v for k, v in extra.items() if k in ("column_query", "detail")},
        )


@pytest.mark.parametrize("detail", ["summary", "full"])
async def test_pages_together_list_every_column_exactly_once(client, detail):
    serve_wide()
    seen, pages = await walk(client, detail=detail)
    assert pages > 1
    assert seen == [f"measurement_column_{i:03d}_{PAD}" for i in range(300)]


async def test_column_query_subset_pages_every_match_once(client):
    serve_wide(900)
    # Matches the descriptions "number 1", "number 10".."number 19", "number 100".."number 199".
    matching = [1, *range(10, 20), *range(100, 200)]
    seen, pages = await walk(client, column_query="number 1", detail="full")
    expected = [f"measurement_column_{i:03d}_{PAD}" for i in matching]
    assert pages > 1 and seen == expected


async def test_never_paged_sections_repeat_on_every_page(client):
    serve_columns(
        [wide_column(i) for i in range(280)] + [wide_column(i, "point") for i in range(280, 300)]
    )
    first = (await describe(client))["structuredContent"]
    second = (await describe(client, column_cursor=first["next_column_cursor"]))[
        "structuredContent"
    ]
    for key in ("place_fields", "geo_columns", "time_semantics", "knowledge"):
        assert second[key] == first[key]
    assert first["geo_columns"], "the fixture has geo columns to repeat"


async def test_narrow_schema_is_not_paged(client):
    serve_wide(5)
    out = (await describe(client))["structuredContent"]
    assert out["columns_total"] == 5 and len(out["columns"]) == 5
    assert out["has_more_columns"] is False and "next_column_cursor" not in out


@pytest.mark.soda_fixture("describe_fire_summary")
async def test_seattle_summary_is_unpaged(client, soda):
    out = (await describe(client, dataset_id="kzjm-xkqj"))["structuredContent"]
    assert out["has_more_columns"] is False and "next_column_cursor" not in out
    assert out["columns_total"] == len(out["columns"]) == 7


@pytest.mark.soda_fixture("describe_fire_full")
async def test_seattle_full_is_unpaged(client, soda):
    out = (await describe(client, dataset_id="kzjm-xkqj", detail="full", column_query="type"))[
        "structuredContent"
    ]
    assert out["has_more_columns"] is False and "next_column_cursor" not in out
    assert out["columns_total"] == len(out["columns"])


async def test_unit_of_observation_repeats_on_every_page():
    from opendata_atlas.core import describe as describe_module
    from opendata_atlas.core.http import get_client
    from tests.conftest import SEATTLE_CONTEXT, with_unit

    serve_wide()
    ctx, client = with_unit(SEATTLE_CONTEXT, dataset=WIDE, unit="reading"), get_client()
    args = {"dataset_id": WIDE, "column_query": None, "sample_rows": 0, "detail": None}
    first = await describe_module.describe(client, ctx, **args)
    assert first.has_more_columns and first.next_column_cursor
    second = await describe_module.describe(
        client, ctx, **args, column_cursor=first.next_column_cursor
    )
    assert second.columns and second.columns[0].name not in {c.name for c in first.columns}
    for page in (first, second):
        assert page.unit_of_observation is not None
        assert page.unit_of_observation.unit == "reading"


async def test_column_query_counts_only_matches(client):
    serve_wide()
    out = (await describe(client, column_query="column_29"))["structuredContent"]
    assert out["columns_total"] == 10 and len(out["columns"]) == 10
    assert out["has_more_columns"] is False


async def test_column_cursor_continuation_rules(client):
    serve_wide()
    cursor = (await describe(client))["structuredContent"]["next_column_cursor"]

    # Repeating the bound arguments is allowed, by alias or canonical id.
    repeated = await describe(
        client, portal="data.seattle.gov", detail="summary", column_cursor=cursor
    )
    assert repeated["isError"] is False
    assert names(repeated["structuredContent"])[0] != f"measurement_column_000_{PAD}"

    # Anything else is invalid_argument.
    extra = await describe(client, column_cursor=cursor, sample_rows=1)
    assert extra["isError"] is True
    assert extra["structuredContent"]["code"] == "invalid_argument"
    assert extra["structuredContent"]["details"]["field"] == "sample_rows"

    # A mismatched repeat is invalid_cursor with the paging repair.
    for mismatch in ({"detail": "full"}, {"column_query": "column"}, {"dataset_id": "wide-0002"}):
        bad = await describe(client, column_cursor=cursor, **mismatch)
        envelope = bad["structuredContent"]
        assert envelope["code"] == "invalid_cursor", mismatch
        assert envelope["repair"]["next_step"] == "read_paging"

    # Another tool's cursor is refused the same way.
    foreign = cursors.encode("query", {"ds": WIDE}, portal_id="data.seattle.gov")
    bad = await describe(client, column_cursor=foreign)
    assert bad["structuredContent"]["code"] == "invalid_cursor"


async def test_column_cursor_binds_column_query_and_detail(client):
    serve_wide()
    first = (await describe(client, column_query="column", detail="full"))["structuredContent"]
    cursor = first["next_column_cursor"]
    # Omitted arguments continue from the cursor's own.
    page = (await describe(client, column_cursor=cursor))["structuredContent"]
    assert "description" in page["columns"][0], "detail=full was inherited"
    assert page["columns_total"] == 300
    matched = await describe(client, column_cursor=cursor, column_query="column", detail="full")
    assert matched["isError"] is False


def _full_only_too_large() -> None:
    """Place values make full detail overflow; summary fits."""
    columns = [wide_column(i) for i in range(5)]
    columns += [
        {
            "fieldName": f":@computed_region_aaaa_{i:04d}",
            "name": f"Region {i}",
            "dataTypeName": "number",
            "computationStrategy": {"parameters": {"region": f"_aaaa-{i:04d}"}},
        }
        for i in range(10)
    ]
    view = {
        "id": WIDE,
        "name": "Regions",
        "viewType": "tabular",
        "assetType": "dataset",
        "columns": columns,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if "/api/views/" in request.url.path:
            return httpx.Response(200, json=view)
        if "$group" in request.url.params:
            return httpx.Response(200, json=[{"v": str(v), "n": "5"} for v in range(100)])
        return httpx.Response(200, json=[{"n": "42"}])

    set_client(SodaClient(transport=httpx.MockTransport(handler)))


async def follow(client, input_schemas, first: dict[str, Any]) -> list[dict[str, Any]]:
    """The envelopes met by following each repair once, ending at the first without one."""
    seen: list[dict[str, Any]] = []
    call = first
    for _ in range(5):
        result = await client.call_tool_mcp(TOOL, call)
        envelope = wire(result)["structuredContent"]
        seen.append(envelope)
        if "repair" not in envelope:
            return seen
        repair = envelope["repair"]
        assert repair["tool"] == TOOL
        jsonschema.validate(repair["arguments"], input_schemas[TOOL])
        assert repair["arguments"] != call, "a repair is never the call that failed"
        call = repair["arguments"]
    raise AssertionError("repair chain did not end")


async def test_describe_too_large_repair_is_callable(client, input_schemas):
    _full_only_too_large()
    full = await describe(client, detail="full", column_query="Region")
    envelope = full["structuredContent"]
    assert full["isError"] is True and envelope["code"] == "describe_too_large"
    assert envelope["temporary"] is False
    assert envelope["details"]["field"] == "detail" and "knowledge" in envelope["details"]["reason"]
    repair = envelope["repair"]
    assert repair["next_step"] == "use_summary" and repair["tool"] == TOOL
    assert repair["arguments"] == {
        "portal": "data.seattle.gov",
        "dataset_id": WIDE,
        "column_query": "Region",
        "detail": "summary",
    }
    jsonschema.validate(repair["arguments"], input_schemas[TOOL])
    # Following it once succeeds: summary fits.
    followed = wire(await client.call_tool_mcp(TOOL, repair["arguments"]))
    assert followed["isError"] is False


async def test_describe_too_large_repair_chain_shrinks_until_none(client, input_schemas):
    _too_large(place=True)
    first = {**WIDE_ARGS, "detail": "full", "sample_rows": 1, "column_query": "Region"}
    steps = await follow(client, input_schemas, first)
    assert [e["repair"]["next_step"] for e in steps[:-1]] == ["use_summary", "drop_samples"]
    assert [e["details"]["field"] for e in steps] == ["detail", "sample_rows", "dataset_id"]
    # Each repair keeps the other arguments of the failed call.
    assert steps[0]["repair"]["arguments"] == {
        "portal": "data.seattle.gov",
        "dataset_id": WIDE,
        "column_query": "Region",
        "detail": "summary",
        "sample_rows": 1,
    }
    assert steps[1]["repair"]["arguments"]["sample_rows"] == 0
    assert steps[1]["repair"]["arguments"]["column_query"] == "Region"
    last = steps[-1]
    assert "repair" not in last and "query the dataset directly" in last["details"]["reason"]
    assert all(e["code"] == "describe_too_large" for e in steps)


async def test_describe_too_large_never_offers_column_narrowing(client):
    _too_large(place=True)
    for extra in ({}, {"detail": "full"}, {"sample_rows": 2}):
        envelope = (await describe(client, **extra))["structuredContent"]
        assert envelope["code"] == "describe_too_large"
        assert envelope.get("repair", {}).get("next_step") != "narrow_columns"
        assert "column_query" not in envelope.get("repair", {}).get("arguments", {})


async def test_column_cursor_expires_when_the_schema_changes(client):
    serve_wide()
    cursor = (await describe(client))["structuredContent"]["next_column_cursor"]
    serve_columns([*[wide_column(i) for i in range(299)], wide_column(999)])
    stale = await describe(client, column_cursor=cursor)
    envelope = stale["structuredContent"]
    assert stale["isError"] is True and envelope["code"] == "cursor_expired"
    assert envelope["repair"]["next_step"] == "read_paging"


async def test_message_matches_the_path(client):
    _too_large(place=True)
    # No column matches, so the sections alone overflow: no column is placed.
    alone = (await describe(client, column_query="zzz_no_such_column"))["structuredContent"]
    assert alone["code"] == "describe_too_large"
    assert "one column" not in alone["message"]
    assert alone["message"].startswith("The sections returned on every page exceed")


async def test_message_names_the_one_column_path(client):
    """Grow a padding column until the sections fit with no column but not beside one."""

    def serve(pad: int) -> None:
        geo = [
            {"fieldName": f"{'g' * 80}_{i:03d}", "name": "g", "dataTypeName": "point"}
            for i in range(200)
        ]
        padding = {"fieldName": f"p{'p' * pad}", "name": "p", "dataTypeName": "point"}
        serve_columns([wide_column(0), *geo, padding])

    for pad in range(0, 2000, 5):
        serve(pad)
        alone = (await describe(client, column_query="zzz_no_such_column"))["structuredContent"]
        if alone.get("code") == "describe_too_large":
            break
        beside = (await describe(client, column_query="measurement"))["structuredContent"]
        if beside.get("code") == "describe_too_large":
            assert beside["message"].endswith("with even one column.")
            return
    pytest.fail("no padding put the sections between the two limits")


async def test_example_message_is_one_the_engine_produces():
    from opendata_atlas.core.describe import _too_large
    from opendata_atlas.core.errors import ErrorCode
    from opendata_atlas.core.reference import ERROR_EXAMPLES

    produced = _too_large(
        "p",
        "aaaa-bbbb",
        column_query=None,
        detail="full",
        sample_rows=0,
        even_one=True,
        continued=False,
    ).envelope.message
    assert ERROR_EXAMPLES[ErrorCode.DESCRIBE_TOO_LARGE]["message"] == produced


async def test_columns_cursor_without_fingerprint_is_invalid_cursor(client):
    serve_wide()
    bare = cursors.encode(
        "columns",
        {"ds": WIDE, "q": None, "d": "summary", "o": 10},
        portal_id="data.seattle.gov",
    )
    result = await describe(client, column_cursor=bare)
    envelope = result["structuredContent"]
    assert result["isError"] is True and envelope["code"] == "invalid_cursor"
    assert envelope["repair"]["next_step"] == "read_paging"


async def test_continuation_repair_says_it_restarts(client):
    serve_wide()
    first = await describe(client, column_query="measurement", detail="full")
    cursor = first["structuredContent"]["next_column_cursor"]
    # Same matching columns, now beside geo columns that overflow the unpaged sections.
    serve_columns(
        [wide_column(i) for i in range(300)]
        + [
            {"fieldName": f"{'g' * 70}_{i:03d}", "name": "g", "dataTypeName": "point"}
            for i in range(300)
        ]
    )
    failed = await describe(client, column_cursor=cursor)
    envelope = failed["structuredContent"]
    assert envelope["code"] == "describe_too_large"
    repair = envelope["repair"]
    assert "column_cursor" not in repair["arguments"]
    assert "first page" in repair["alternative"]
    # A first-page failure carries no such note.
    fresh = (await describe(client, detail="full"))["structuredContent"]
    assert "alternative" not in fresh["repair"]


def test_restart_repair_is_the_paging_reference():
    from opendata_atlas.core.describe import _RESTART

    assert isinstance(_RESTART, Repair) and _RESTART.next_step == "read_paging"
