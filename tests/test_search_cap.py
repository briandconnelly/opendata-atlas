"""Search paging at the Discovery API's 10,000-result cap (#24)."""

from __future__ import annotations

from typing import Any

import httpx

from opendata_atlas.constants import CATALOG_RESULT_CAP
from opendata_atlas.core import catalog
from opendata_atlas.core import cursor as cursors
from opendata_atlas.core.budget import wire_size
from opendata_atlas.core.http import SodaClient, set_client
from opendata_atlas.core.models import SearchResult
from tests.conftest import wire
from tests.test_budget import wire_measure
from tests.test_search_evidence import body, item, search


def _serve(total: int, sent: list[dict[str, str]]) -> None:
    """A catalog of `total` entries that, like upstream, rejects offset + limit over the cap."""

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params.multi_items())
        sent.append(params)
        offset, limit = int(params["offset"]), int(params["limit"])
        if offset + limit > CATALOG_RESULT_CAP:
            return httpx.Response(400, json={"error": "Sum of `offset` and `limit` cannot exceed"})
        page = [
            item(f"a{i // 10_000:03d}-{i % 10_000:04d}", f"Dataset {i}")
            for i in range(offset, min(offset + limit, total))
        ]
        return httpx.Response(200, json=body(page, min(total, CATALOG_RESULT_CAP)))

    set_client(SodaClient(transport=httpx.MockTransport(handler)))


def _cursor_at(offset: int, page_size: int) -> str:
    state = {"q": None, "scope": "tabular", "cat": None, "off": offset, "ps": page_size}
    return cursors.encode("search", {**state, "seen": []}, portal_id="data.seattle.gov")


async def test_the_last_page_at_the_cap_says_more_may_exist(client, tools_list):
    sent: list[dict[str, str]] = []
    _serve(25_000, sent)
    args: dict[str, Any] = {"portal": "seattle", "cursor": _cursor_at(9_950, 50)}
    out = await search(client, tools_list, args)
    assert len(out["datasets"]) == 50
    assert out["has_more"] is False
    assert out["truncated"] is True
    assert "10,000" in out["truncation_hint"]


async def test_a_catalog_under_the_cap_is_not_truncated(client, tools_list):
    sent: list[dict[str, str]] = []
    _serve(120, sent)
    out = await search(client, tools_list, {"portal": "seattle", "cursor": _cursor_at(100, 50)})
    assert len(out["datasets"]) == 20
    assert out["has_more"] is False
    assert "truncated" not in out


async def test_a_resumed_page_never_asks_past_the_cap(client, tools_list):
    """A page the byte budget cut short can resume at an offset page_size does not divide."""
    sent: list[dict[str, str]] = []
    _serve(25_000, sent)
    out = await search(client, tools_list, {"portal": "seattle", "cursor": _cursor_at(9_993, 10)})
    assert sent[-1]["limit"] == "7"
    assert len(out["datasets"]) == 7
    assert out["truncated"] is True


async def test_the_cap_fields_count_toward_the_budget(client, monkeypatch):
    """Copilot on #45: a last page that fits only without the cap fields is cut short, and the
    page that then ends the listing carries them within the limit."""
    sent: list[dict[str, str]] = []
    _serve(25_000, sent)
    args: dict[str, Any] = {"portal": "seattle", "cursor": _cursor_at(9_990, 10)}
    unlimited = wire(await client.call_tool_mcp("atlas_search_datasets", args))["structuredContent"]
    assert unlimited["truncated"] is True and len(unlimited["datasets"]) == 10
    bare = {k: v for k, v in unlimited.items() if k not in ("truncated", "truncation_hint")}
    limit = wire_size(SearchResult.model_validate(bare)) + 10
    monkeypatch.setattr(catalog, "RESULT_LIMIT", limit)

    page = wire(await client.call_tool_mcp("atlas_search_datasets", args))
    out = page["structuredContent"]
    assert page["isError"] is False, out
    assert wire_measure(page) <= limit
    assert out["has_more"] is True and "truncated" not in out
    seen = len(out["datasets"])
    while out["has_more"]:
        page = wire(
            await client.call_tool_mcp(
                "atlas_search_datasets", {"portal": "seattle", "cursor": out["next_cursor"]}
            )
        )
        assert wire_measure(page) <= limit
        out = page["structuredContent"]
        seen += len(out["datasets"])
    assert out["truncated"] is True
    assert seen == 10
