"""Every failure leaves as the error envelope (docs/design.md: Errors), on the wire."""

from __future__ import annotations

import json
from typing import Any

import jsonschema
import pytest
from fastmcp import Client
from fastmcp.exceptions import McpError

from opendata_atlas.core.errors import ErrorEnvelope
from opendata_atlas.mcp.server import build_server
from tests.conftest import wire

ENVELOPE_SCHEMA = ErrorEnvelope.model_json_schema()
REQUIRED = {"code", "message", "temporary", "retry_after_ms"}


def assert_tool_envelope(result: dict[str, Any], input_schema: dict[str, Any]) -> dict[str, Any]:
    assert result["isError"] is True
    envelope = result["structuredContent"]
    assert envelope.keys() >= REQUIRED
    jsonschema.validate(envelope, ENVELOPE_SCHEMA)
    assert json.loads(result["content"][0]["text"]) == envelope
    assert envelope["request_id"]
    if not envelope["temporary"]:
        assert envelope["retry_after_ms"] is None
    details = envelope.get("details") or {}
    published = set(input_schema["properties"])
    for path in [details.get("field"), *list(details.get("fields") or [])]:
        if path:
            assert path.split(".")[0] in published, f"{path} is not a published parameter"
    return envelope


# One forced framework-validation failure per tool: the case that bypasses handlers.
VALIDATION_CASES = [
    ("atlas_search_datasets", {"portal": "seattle", "page_size": 0}, "page_size"),
    ("atlas_search_datasets", {"portal": "seattle", "asset_scope": "maps"}, "asset_scope"),
    ("atlas_describe_dataset", {"portal": "seattle"}, "dataset_id"),
    ("atlas_describe_dataset", {"portal": "seattle", "dataset_id": "Fire 911"}, "dataset_id"),
    (
        "atlas_query_dataset",
        {"portal": "seattle", "dataset_id": "kzjm-xkqj", "page_size": 501},
        "page_size",
    ),
    (
        "atlas_query_dataset",
        {"portal": "seattle", "dataset_id": "kzjm-xkqj", "select": []},
        "select",
    ),
    ("atlas_query_dataset", {"portal": "seattle", "dataset_id": "kzjm-xkqj", "where": ""}, "where"),
    (
        "atlas_query_dataset",
        {
            "portal": "seattle",
            "dataset_id": "kzjm-xkqj",
            "near": {"column": "report_location", "latitude": 91, "longitude": 0, "radius_m": 10},
        },
        "near.latitude",
    ),
    ("atlas_get_reference", {"topic": "faq"}, "topic"),
]


@pytest.mark.parametrize(("tool", "args", "field"), VALIDATION_CASES)
async def test_validation_failure_is_enveloped(client, input_schemas, tool, args, field):
    envelope = assert_tool_envelope(
        wire(await client.call_tool_mcp(tool, args)), input_schemas[tool]
    )
    assert envelope["code"] == "invalid_argument"
    assert envelope["details"]["field"] == field
    assert "value" not in envelope["details"], "received values are never echoed"


MALFORMED_PORTAL_CASES = [
    ("atlas_search_datasets", {"portal": "Chicago, IL", "query": "permits"}),
    ("atlas_describe_dataset", {"portal": "Chicago, IL", "dataset_id": "kzjm-xkqj"}),
    ("atlas_query_dataset", {"portal": "Chicago, IL", "dataset_id": "kzjm-xkqj"}),
]


@pytest.mark.parametrize(("tool", "args"), MALFORMED_PORTAL_CASES)
async def test_malformed_portal_repairs_to_find_portals(client, input_schemas, tool, args):
    """A place name in `portal` fails the pattern; the repair finds the portal id."""
    envelope = assert_tool_envelope(
        wire(await client.call_tool_mcp(tool, args)), input_schemas[tool]
    )
    assert envelope["code"] == "invalid_argument"
    assert envelope["details"]["field"] == "portal"
    assert envelope["repair"]["next_step"] == "find_portal"
    assert envelope["repair"]["tool"] == "atlas_find_portals"
    assert envelope["repair"]["arguments"] == {}
    assert "Chicago" not in json.dumps(envelope), "received values are never echoed"


async def test_unknown_argument_is_named(client):
    """The one case where details.field is not a published parameter: it names the stray key."""
    result = wire(
        await client.call_tool_mcp(
            "atlas_query_dataset", {"portal": "seattle", "dataset_id": "kzjm-xkqj", "limit": 5}
        )
    )
    envelope = result["structuredContent"]
    assert result["isError"] is True
    assert envelope["code"] == "invalid_argument"
    assert envelope["details"]["field"] == "limit"
    jsonschema.validate(envelope, ENVELOPE_SCHEMA)


@pytest.mark.parametrize("mode", ["modern", "legacy"])
async def test_unknown_tool_is_a_malformed_call(input_schemas, caplog, mode):
    """A `tools/call` naming no tool of this server is the caller's malformed call, not a
    server defect: `invalid_argument` on `name`, the tool names as candidates, and a repair
    to the full contract (milestone 6 standards review)."""
    kw = {"mode": "legacy"} if mode == "legacy" else {}
    async with Client(build_server(), **kw) as client:
        result = wire(await client.call_tool_mcp("atlas_get_dataset_metadata", {"x": 1}))
    envelope = result["structuredContent"]
    assert result["isError"] is True
    jsonschema.validate(envelope, ENVELOPE_SCHEMA)
    assert json.loads(result["content"][0]["text"]) == envelope
    assert envelope["code"] == "invalid_argument"
    assert envelope["temporary"] is False and envelope["retry_after_ms"] is None
    assert envelope["request_id"]
    assert envelope["details"]["field"] == "name"
    assert envelope["details"]["candidates"] == list(input_schemas)
    assert "value" not in envelope["details"]
    assert "atlas_get_dataset_metadata" not in json.dumps(envelope), "never echoed"
    assert envelope["repair"] == {
        "next_step": "read_capabilities",
        "tool": "atlas_get_reference",
        "arguments": {"topic": "capabilities"},
    }
    assert not [r for r in caplog.records if r.exc_info], "not logged as a server failure"


COMBINATION_CASES = [
    (
        "atlas_query_dataset",
        {"portal": "seattle", "dataset_id": "kzjm-xkqj", "mode": "soql"},
        ["soql"],
    ),
    (
        "atlas_query_dataset",
        {
            "portal": "seattle",
            "dataset_id": "kzjm-xkqj",
            "mode": "soql",
            "soql": "SELECT count(*)",
            "where": "a = 1",
        },
        ["where"],
    ),
    (
        "atlas_query_dataset",
        {"portal": "seattle", "dataset_id": "kzjm-xkqj", "soql": "SELECT 1"},
        ["soql"],
    ),
    (
        "atlas_query_dataset",
        {"portal": "seattle", "dataset_id": "kzjm-xkqj", "cursor": "abc", "where": "a = 1"},
        ["where"],
    ),
    (
        "atlas_query_dataset",
        {"portal": "seattle", "dataset_id": "kzjm-xkqj", "where": "x" * 2100, "having": "y" * 2100},
        ["where", "having"],
    ),
    ("atlas_search_datasets", {"portal": "seattle", "cursor": "abc", "query": "fire"}, ["query"]),
    ("atlas_get_reference", {"item_id": "dates"}, ["topic", "item_id"]),
]


@pytest.mark.parametrize(("tool", "args", "fields"), COMBINATION_CASES)
async def test_combination_failure_is_enveloped(client, input_schemas, tool, args, fields):
    envelope = assert_tool_envelope(
        wire(await client.call_tool_mcp(tool, args)), input_schemas[tool]
    )
    assert envelope["code"] == "invalid_argument"
    details = envelope["details"]
    assert ([details["field"]] if "field" in details else details["fields"]) == fields


async def test_reference_domain_error(client, input_schemas):
    result = wire(
        await client.call_tool_mcp("atlas_get_reference", {"topic": "soql", "item_id": "joins"})
    )
    envelope = assert_tool_envelope(result, input_schemas["atlas_get_reference"])
    assert envelope["code"] == "reference_not_found"
    assert "syntax" in envelope["details"]["candidates"]


async def test_request_ids_differ_per_call(client):
    ids = set()
    for _ in range(3):
        result = wire(
            await client.call_tool_mcp("atlas_get_reference", {"topic": "soql", "item_id": "joins"})
        )
        ids.add(result["structuredContent"]["request_id"])
    assert len(ids) == 3


@pytest.mark.parametrize(
    ("uri", "code"),
    [
        ("opendata-atlas://guides/no-such-guide", "reference_not_found"),
        ("opendata-atlas://soql/joins", "reference_not_found"),
        ("opendata-atlas://nowhere", "reference_not_found"),
    ],
)
async def test_resource_failure_uses_jsonrpc_carrier(client, uri, code):
    with pytest.raises(McpError) as caught:
        await client.read_resource(uri)
    error = caught.value.error
    assert error.code == -32602
    data = error.data
    assert data["machine_code"] == code
    assert "human_message" in data and "code" not in data and "message" not in data
    assert data["temporary"] is False and data["retry_after_ms"] is None
    assert data["resource_uri"] == uri
    assert data["request_id"]
