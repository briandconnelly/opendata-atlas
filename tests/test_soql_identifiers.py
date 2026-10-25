"""Engine-written SoQL quotes keyword column names, such as LAPD's `group` (#18)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from opendata_atlas.core import cache
from opendata_atlas.core.http import SodaClient, set_client
from opendata_atlas.core.soql import identifier
from tests.conftest import wire

#: A synthetic view whose text column is named like a SoQL keyword.
VIEW = {
    "id": "aaaa-bbbb",
    "assetType": "dataset",
    "viewType": "tabular",
    "columns": [
        {"fieldName": "group", "dataTypeName": "text"},
        {"fieldName": "caseno", "dataTypeName": "text"},
        {"fieldName": "order", "dataTypeName": "floating_timestamp"},
    ],
}


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("caseno", "caseno"),
        ("date_rptd", "date_rptd"),
        ("group", "`group`"),
        ("order", "`order`"),
        ("select", "`select`"),
        (":id", ":id"),
        (":@computed_region_abcd_1234", ":@computed_region_abcd_1234"),
        ("Mixed Case", "`Mixed Case`"),
    ],
)
def test_identifier(name: str, expected: str):
    assert identifier(name) == expected


def _serve(sent: list[dict[str, Any]]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/api/views/" in request.url.path:
            return httpx.Response(200, json=VIEW)
        params = dict(request.url.params.multi_items())
        sent.append(params)
        select = params.get("$select", "")
        if select.startswith("count(*)"):
            return httpx.Response(200, json=[{"n": "2"}])
        if select.startswith("min("):
            return httpx.Response(200, json=[{"lo": "2026-01-01T00:00:00.000"}])
        headers = {
            "X-SODA2-Fields": '["group","caseno","order",":id"]',
            "X-SODA2-Types": '["text","text","floating_timestamp","text"]',
        }
        row = {"group": "A", "caseno": "1", "order": "2026-01-01T00:00:00.000", ":id": "row-1"}
        return httpx.Response(200, headers=headers, json=[row])

    cache.clear()
    set_client(SodaClient(transport=httpx.MockTransport(handler)))


async def test_default_projection_quotes_keyword_columns(client):
    sent: list[dict[str, Any]] = []
    _serve(sent)
    args = {"portal": "los-angeles", "dataset_id": "aaaa-bbbb", "page_size": 1}
    result = wire(await client.call_tool_mcp("atlas_query_dataset", args))
    assert result["isError"] is False, result["structuredContent"]
    assert sent[-1]["$select"] == "`group`, caseno, `order`, :id"
    assert result["structuredContent"]["rows"][0]["group"] == "A"


async def test_describe_probes_quote_keyword_columns(client):
    sent: list[dict[str, Any]] = []
    _serve(sent)
    args = {"portal": "los-angeles", "dataset_id": "aaaa-bbbb", "sample_rows": 1}
    result = wire(await client.call_tool_mcp("atlas_describe_dataset", args))
    assert result["isError"] is False, result["structuredContent"]
    selects = {p["$select"] for p in sent}
    assert "min(`order`) AS lo, max(`order`) AS hi" in selects
    assert "`group`,caseno,`order`" in selects
