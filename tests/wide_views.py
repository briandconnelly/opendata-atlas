"""Synthetic wide views for describe paging and budget tests: a mock portal serving them."""

from __future__ import annotations

from typing import Any

import httpx

from opendata_atlas.core.http import SodaClient, set_client

WIDE = "wide-0001"
#: Long names, as on real wide portals, so 300 columns exceed the budget.
PAD = "of_a_deliberately_verbose_naming_scheme"
WIDE_ARGS = {"portal": "seattle", "dataset_id": WIDE}


def wide_column(index: int, type_: str = "text") -> dict[str, Any]:
    name = f"measurement_column_{index:03d}_{PAD}"
    return {
        "fieldName": name,
        "name": name,
        "dataTypeName": type_,
        "description": f"Synthetic column number {index} with a sentence of description. " * 2,
    }


def serve_columns(columns: list[dict[str, Any]]) -> None:
    """Install a mock portal whose view has `columns` and whose count query returns 42."""
    view = {
        "id": WIDE,
        "name": "Wide synthetic dataset",
        "viewType": "tabular",
        "assetType": "dataset",
        "columns": columns,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if "/api/views/" in request.url.path:
            return httpx.Response(200, json=view)
        return httpx.Response(200, json=[{"n": "42"}])

    set_client(SodaClient(transport=httpx.MockTransport(handler)))


def serve_wide(count: int = 300) -> None:
    """Install a mock portal with `count` long-named text columns."""
    serve_columns([wide_column(i) for i in range(count)])
