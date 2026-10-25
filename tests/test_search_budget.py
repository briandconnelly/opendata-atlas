"""Search pages fit the byte budget, and the cursor still reaches every dataset (#17)."""

from __future__ import annotations

from typing import Any

import httpx

from opendata_atlas.core.budget import RESULT_LIMIT
from opendata_atlas.core.http import SodaClient, set_client
from tests.conftest import wire
from tests.test_budget import wire_measure
from tests.test_search_evidence import TOOL, body, item, search

TOTAL = 60
#: Long enough that 50 full-detail summaries are several times the budget.
DESCRIPTION = "Street trees planted and maintained by the city. " * 40
FOREIGN = 7


def _catalog() -> list[dict[str, Any]]:
    entries = [
        item(f"aaaa-{i:04d}", f"Trees {i:02d}", description=DESCRIPTION) for i in range(TOTAL)
    ]
    entries[FOREIGN]["metadata"]["domain"] = "data.other.gov"
    return entries


def _serve(entries: list[dict[str, Any]]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params.multi_items())
        if params.get("only") == "federated_href,href":
            return httpx.Response(200, json=body([]))
        offset, limit = int(params["offset"]), int(params["limit"])
        return httpx.Response(200, json=body(entries[offset : offset + limit], len(entries)))

    set_client(SodaClient(transport=httpx.MockTransport(handler)))


async def test_full_detail_page_fits_the_budget(client):
    _serve(_catalog())
    args = {"portal": "seattle", "query": "trees", "page_size": 50, "detail": "full"}
    received = wire(await client.call_tool_mcp(TOOL, args))
    assert received["isError"] is False, received["structuredContent"]
    out = received["structuredContent"]
    assert wire_measure(received) <= RESULT_LIMIT
    assert 1 <= len(out["datasets"]) < 50, "the byte budget, not page_size, ended this page"
    assert out["has_more"] is True
    assert len(out["match_evidence"]) == len(out["datasets"])


async def test_trimmed_search_pages_deliver_every_dataset(client, tools_list):
    entries = _catalog()
    _serve(entries)
    args: dict[str, Any] = {
        "portal": "seattle",
        "query": "trees",
        "page_size": 50,
        "detail": "full",
    }
    seen: list[str] = []
    pages = 0
    while True:
        out = await search(client, tools_list, args)
        seen += [d["dataset_id"] for d in out["datasets"]]
        pages += 1
        if not out["has_more"]:
            break
        args = {"portal": "seattle", "cursor": out["next_cursor"]}
    expected = [e["resource"]["id"] for i, e in enumerate(entries) if i != FOREIGN]
    assert pages > 2
    assert seen == expected, "every dataset exactly once, in catalog order"


async def test_summary_page_within_budget_is_untouched(client, tools_list):
    _serve(_catalog())
    out = await search(client, tools_list, {"portal": "seattle", "query": "trees", "page_size": 5})
    assert [d["dataset_id"] for d in out["datasets"]] == [f"aaaa-{i:04d}" for i in range(5)]
    assert out["has_more"] is True
