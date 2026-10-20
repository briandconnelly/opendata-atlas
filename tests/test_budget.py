"""Every tool's largest result fits its measure, and the reserve covers the modern envelope.

Query, reference entry pages and `atlas_find_portals` are measured by `wire_size` (text copy
plus `structuredContent`, ruling 72); describe and reference bodies by `payload_size` (ruling 35,
carry-over F6).
"""

from __future__ import annotations

import re
from typing import Any

import httpx
import pytest

from opendata_atlas.constants import RESULT_BYTE_BUDGET
from opendata_atlas.core import budget, cache
from opendata_atlas.core.budget import ENVELOPE_RESERVE, RESULT_LIMIT, fit
from opendata_atlas.core.http import SodaClient, set_client
from opendata_atlas.core.portals import find_portals
from opendata_atlas.core.reference import topics
from opendata_atlas.portals.registry import load_registry
from tests.conftest import JSONRPC_FRAME, SEATTLE_CONTEXT, compact_json, framed_size, wire
from tests.wide_views import WIDE_ARGS, serve_wide

WIDE_QUERY = {"portal": "seattle", "dataset_id": "76t5-zqzr", "page_size": 200}
SEATTLE = SEATTLE_CONTEXT.id
#: A synthetic view with one text column, for the trimmed-paging walk.
NAME_VIEW = {
    "id": "aaaa-bbbb",
    "assetType": "dataset",
    "viewType": "tabular",
    "columns": [{"fieldName": "name", "dataTypeName": "text"}],
}


def wire_measure(result: dict[str, Any]) -> int:
    """`budget.wire_size` over a received result: its text copy and `structuredContent`."""
    keys = ("content", "structuredContent", "isError")
    return len(compact_json({k: result[k] for k in keys}).encode())


def payload_measure(result: dict[str, Any]) -> int:
    """`budget.payload_size` over a received result: `structuredContent` alone."""
    return len(compact_json(result["structuredContent"]).encode())


def reference_measure(result: dict[str, Any]) -> int:
    """Ruling 72: an entry page by `wire_size`; a body, never paged, by `payload_size`."""
    if "entries" in result["structuredContent"]:
        return wire_measure(result)
    return payload_measure(result)


async def call(client, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    result = wire(await client.call_tool_mcp(tool, args))
    assert result["isError"] is False, result["structuredContent"]
    return result


async def test_envelope_reserve_covers_modern_overhead(client):
    result = wire(await client.call_tool_mcp("atlas_get_reference", {"topic": "index"}))
    rest = {k: v for k, v in result.items() if k not in ("structuredContent", "content")}
    overhead = len(compact_json(rest).encode()) + len(JSONRPC_FRAME)
    assert overhead > 600, "the modern _meta stamp is present (known positive)"
    assert overhead <= ENVELOPE_RESERVE


@pytest.mark.soda_fixture("query_wide_rows")
async def test_query_page_fits_modern_wire(client, soda):
    result = await call(client, "atlas_query_dataset", WIDE_QUERY)
    assert result["structuredContent"]["returned_rows"] >= 1
    assert framed_size(result) <= RESULT_BYTE_BUDGET


def _reference_calls() -> list[dict[str, Any]]:
    """Every static topic and item, the Seattle portal item, and the Seattle guides index."""
    calls: list[dict[str, Any]] = [{"topic": "index"}, {"topic": "portals"}]
    for name, topic in topics(None).items():
        if name in ("portals", "guides"):
            continue
        calls.append({"topic": name})
        calls += [{"topic": name, "item_id": d.item_id} for d in topic.documents]
    calls.append({"topic": "portals", "item_id": SEATTLE})
    calls.append({"topic": "guides", "portal": SEATTLE})
    calls += [
        {"topic": "guides", "portal": SEATTLE, "item_id": g.guide_id}
        for g in SEATTLE_CONTEXT.guides
    ]
    return calls


def _case_id(args: dict[str, Any]) -> str:
    return "reference:" + "/".join(str(v) for v in args.values())


CASES = [
    pytest.param(
        "atlas_query_dataset",
        WIDE_QUERY,
        "query_wide_rows",
        None,
        wire_measure,
        id="query:wide_rows",
    ),
    *(
        pytest.param(
            "atlas_describe_dataset",
            {**WIDE_ARGS, "detail": detail},
            None,
            serve_wide,
            payload_measure,
            id=f"describe:300_columns_{detail}",
        )
        for detail in ("summary", "full")
    ),
    pytest.param(
        "atlas_describe_dataset",
        {"portal": "seattle", "dataset_id": "kzjm-xkqj", "detail": "full"},
        "describe_fire_full",
        None,
        payload_measure,
        id="describe:seattle_fire_full",
    ),
    *(
        pytest.param("atlas_get_reference", args, None, None, reference_measure, id=_case_id(args))
        for args in _reference_calls()
    ),
    pytest.param(
        "atlas_find_portals",
        {"page_size": 50},
        None,
        None,
        wire_measure,
        id="find_portals:page_size_50",
    ),
]


@pytest.mark.parametrize(("tool", "args", "fixture", "serve", "measure"), CASES)
async def test_largest_result_per_tool_fits(client, request, tool, args, fixture, serve, measure):
    if fixture is not None:
        request.node.add_marker(pytest.mark.soda_fixture(fixture))
        request.getfixturevalue("soda")
    if serve is not None:
        serve()
    result = await call(client, tool, args)
    assert measure(result) <= RESULT_LIMIT


async def test_trimmed_query_pages_deliver_every_row(client):
    """A page the larger reserve trims still continues; walking the cursor reaches every row."""
    total = 40
    rows = [{"name": f"{i:03d}" + "x" * 2_500, ":id": f"row-{i:03d}"} for i in range(total)]

    def handler(request: httpx.Request) -> httpx.Response:
        if "/api/views/" in request.url.path:
            return httpx.Response(200, json=NAME_VIEW)
        params = dict(request.url.params.multi_items())
        after = re.search(r":id > '([^']*)'", params.get("$where", ""))
        page = [r for r in rows if after is None or r[":id"] > after.group(1)]
        headers = {"X-SODA2-Fields": '["name",":id"]', "X-SODA2-Types": '["text","text"]'}
        return httpx.Response(200, headers=headers, json=page[: int(params["$limit"])])

    cache.clear()
    set_client(SodaClient(transport=httpx.MockTransport(handler)))
    args: dict[str, Any] = {
        "portal": "seattle",
        "dataset_id": "aaaa-bbbb",
        "select": ["name"],
        "page_size": 200,
    }
    seen: list[str] = []
    pages = 0
    while True:
        result = await call(client, "atlas_query_dataset", args)
        out = result["structuredContent"]
        assert framed_size(result) <= RESULT_BYTE_BUDGET
        assert out["returned_rows"] >= 1
        seen += [r["name"][:3] for r in out["rows"]]
        pages += 1
        if not out["has_more"]:
            break
        assert out["returned_rows"] < total, "the byte budget, not page_size, ended this page"
        args = {"portal": "seattle", "dataset_id": "aaaa-bbbb", "cursor": out["next_cursor"]}
    assert pages > 1
    assert seen == [f"{i:03d}" for i in range(total)], "every row exactly once, in order"


def _walk(registry, page_size: int) -> tuple[list[str], int]:
    """Every candidate id across all pages, and the page count."""
    page = find_portals(
        registry, query=None, level=None, country=None, tier=None, page_size=page_size, cursor=None
    )
    seen, pages = [c.id for c in page.candidates], 1
    while page.has_more:
        assert page.next_cursor
        page = find_portals(
            registry,
            query=None,
            level=None,
            country=None,
            tier=None,
            page_size=None,
            cursor=page.next_cursor,
        )
        assert page.candidates, "a continuation page is never empty"
        seen += [c.id for c in page.candidates]
        pages += 1
    assert page.next_cursor is None
    return seen, pages


def test_find_portals_packing_continues(monkeypatch: pytest.MonkeyPatch):
    registry = load_registry()
    expected, full_pages = _walk(registry, 50)
    monkeypatch.setattr(budget, "RESULT_LIMIT", 2_000)
    seen, pages = _walk(registry, 50)
    assert pages > full_pages, "the low limit packed fewer candidates per page"
    assert seen == expected
    assert len(seen) == len(set(seen))


def test_fit_settles_on_the_largest_count_that_fits():
    sizes = {"n": -1}

    def settle(n: int) -> None:
        sizes["n"] = n

    assert fit(10, settle, lambda: 100 * sizes["n"], limit=450) == 4
    assert sizes["n"] == 4, "the result is left settled at the returned count"
    assert fit(10, settle, lambda: 100 * sizes["n"], limit=5_000) == 10
    assert sizes["n"] == 10
    assert fit(10, settle, lambda: 100 + 100 * sizes["n"], limit=50) == 0
    assert sizes["n"] == 0


async def test_candidate_over_the_limit_is_internal_error(client, monkeypatch: pytest.MonkeyPatch):
    """A page that cannot hold one candidate fails loudly, never as an empty page with a cursor."""
    monkeypatch.setattr(budget, "RESULT_LIMIT", 1)
    result = wire(await client.call_tool_mcp("atlas_find_portals", {}))
    assert result["isError"] is True
    envelope = result["structuredContent"]
    assert envelope["code"] == "internal_error"
    assert envelope["message"] == "A single portal candidate exceeds the result budget."
