"""Regressions for the Codex review of milestone 1."""

from __future__ import annotations

import os
import subprocess
import sys

from fastmcp import Client

from opendata_atlas.core.errors import map_upstream_error
from opendata_atlas.mcp.server import build_server
from tests.conftest import wire

MARKER = "UNTRUSTED_MARKER"


def test_imports_without_system_tz_database():
    env = {**os.environ, "PYTHONTZPATH": "/nonexistent"}
    probe = (
        "from opendata_atlas.core.context import make_source;"
        "from opendata_atlas.portals.loader import SEATTLE, load_portal;"
        "print(load_portal(SEATTLE).tz, make_source(load_portal(SEATTLE)).now_local)"
    )
    out = subprocess.run(
        [sys.executable, "-c", probe], env=env, capture_output=True, text=True, check=False
    )
    assert out.returncode == 0, out.stderr
    assert "America/Los_Angeles" in out.stdout


async def test_handler_validation_error_is_internal_not_caller_error():
    server = build_server()

    @server.tool
    def broken() -> dict:
        from opendata_atlas.core.models import Source

        Source.model_validate({})
        return {}

    async with Client(server) as client:
        result = wire(await client.call_tool_mcp("broken", {}))
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "internal_error"


def test_upstream_codes_must_be_symbolic():
    err = map_upstream_error(400, {"code": f"query.soql.invalid {MARKER}"}).envelope.to_wire()
    assert MARKER not in str(err)
    err = map_upstream_error(503, {"code": f"oops\x07{MARKER}"}).envelope.to_wire()
    assert "upstream_code" not in err["details"]


def test_non_object_upstream_data_is_tolerated():
    err = map_upstream_error(400, {"code": "query.soql.invalid", "data": "unexpected string"})
    assert err.envelope.code == "soql_syntax_error"


async def test_unknown_reference_ids_are_not_echoed(client):
    result = wire(
        await client.call_tool_mcp("atlas_get_reference", {"topic": "soql", "item_id": MARKER})
    )
    assert MARKER not in str(result["structuredContent"])
    assert result["structuredContent"]["code"] == "reference_not_found"


async def test_capabilities_rejects_item_selectors(client):
    result = wire(
        await client.call_tool_mcp("atlas_get_reference", {"topic": "capabilities", "item_id": "x"})
    )
    assert result["isError"] is True
    assert result["structuredContent"]["details"]["fields"] == ["topic", "item_id"]
