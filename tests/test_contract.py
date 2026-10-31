"""Milestone 1 exit tests (a) schema snapshot and (c) tools/list byte budget."""

from __future__ import annotations

import json
import os
from pathlib import Path

from opendata_atlas.constants import TOOL_PREFIX, TOOLS_LIST_BYTE_BUDGET
from tests.conftest import JSONRPC_FRAME, compact_json, framed_size, wire

SNAPSHOT = Path(__file__).parent / "snapshots" / "tools_list.json"
EXPECTED_TOOLS = [
    "atlas_find_portals",
    "atlas_search_datasets",
    "atlas_describe_dataset",
    "atlas_query_dataset",
    "atlas_get_reference",
]


def _surface(tools_list):
    """The agent-visible tool surface, minus per-response envelope metadata."""
    return {"tools": tools_list["tools"]}


def test_tools_list_matches_snapshot(tools_list):
    current = json.dumps(_surface(tools_list), indent=2, sort_keys=True) + "\n"
    if os.environ.get("UPDATE_SNAPSHOTS"):
        SNAPSHOT.write_text(current)
    assert SNAPSHOT.exists(), "no snapshot; create it with UPDATE_SNAPSHOTS=1"
    assert current == SNAPSHOT.read_text(), (
        "tool surface changed; rerun with UPDATE_SNAPSHOTS=1 if intended"
    )


def _listing_size(listing: dict) -> int:
    """Bytes of the `tools/list` result as the client receives it, JSON-RPC frame included."""
    return framed_size(listing)


def test_tools_list_within_byte_budget(tools_list):
    size = _listing_size(tools_list)
    print(f"tools/list serialized size: {size} bytes (budget {TOOLS_LIST_BYTE_BUDGET})")
    assert size <= TOOLS_LIST_BYTE_BUDGET


def test_listing_size_counts_the_jsonrpc_frame():
    """Final review M-4: a listing 10 bytes under the budget unframed is over it framed."""
    listing = {"tools": [{"name": ""}]}
    pad = TOOLS_LIST_BYTE_BUDGET - 10 - len(compact_json(listing).encode())
    listing = {"tools": [{"name": "x" * pad}]}
    assert len(compact_json(listing).encode()) == TOOLS_LIST_BYTE_BUDGET - 10
    assert _listing_size(listing) == TOOLS_LIST_BYTE_BUDGET - 10 + len(JSONRPC_FRAME)


def test_tool_names_and_order_are_stable(tools_list):
    assert [t["name"] for t in tools_list["tools"]] == EXPECTED_TOOLS
    assert all(name.startswith(TOOL_PREFIX) for name in EXPECTED_TOOLS)


async def test_listing_is_deterministic(client, tools_list):
    again = wire(await client.list_tools_mcp())
    assert compact_json(_surface(again)) == compact_json(_surface(tools_list))


def test_cache_hints_are_public_one_hour(tools_list):
    assert tools_list["ttlMs"] == 3_600_000
    assert tools_list["cacheScope"] == "public"


def test_every_tool_is_read_only_with_explicit_open_world(tools_list):
    for tool in tools_list["tools"]:
        hints = tool["annotations"]
        assert hints["readOnlyHint"] is True
        assert "openWorldHint" in hints
        assert "destructiveHint" not in hints and "idempotentHint" not in hints


def _walk(schema):
    if isinstance(schema, dict):
        yield schema
        for value in schema.values():
            yield from _walk(value)
    elif isinstance(schema, list):
        for item in schema:
            yield from _walk(item)


def test_input_schemas_are_closed_and_union_free(tools_list):
    for tool in tools_list["tools"]:
        for node in _walk(tool["inputSchema"]):
            assert "anyOf" not in node and "oneOf" not in node, tool["name"]
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False, tool["name"]


def test_output_schemas_open_at_top_closed_below(tools_list):
    for tool in tools_list["tools"]:
        schema = tool["outputSchema"]
        assert schema["additionalProperties"] is True, tool["name"]
        assert "source" in schema["required"], tool["name"]
        source = schema["properties"]["source"]
        assert source.get("additionalProperties") is False, tool["name"]


def test_every_parameter_is_described_or_self_evident(tools_list):
    self_evident = {"group_by", "having"}
    for tool in tools_list["tools"]:
        assert len(tool["description"]) > 40
        for name, prop in tool["inputSchema"]["properties"].items():
            assert prop.get("description") or name in self_evident, f"{tool['name']}.{name}"


def _refs(schema) -> list[str]:
    return [n["$ref"] for n in _walk(schema) if isinstance(n.get("$ref"), str)]


def test_input_schemas_are_fully_inlined(tools_list):
    """Planners write arguments from the input schema, so it has no `$ref` [3.portable-schema]."""
    for tool in tools_list["tools"]:
        assert "$defs" not in tool["inputSchema"], tool["name"]
        assert _refs(tool["inputSchema"]) == [], tool["name"]


def test_output_schemas_share_only_repeated_objects(tools_list):
    """#66: a `$defs` entry exists only for an object the schema uses more than once, every
    `$ref` names one, and no definition refers to itself or another (no recursion)."""
    shared = 0
    for tool in tools_list["tools"]:
        schema = tool["outputSchema"]
        defs = schema.get("$defs", {})
        refs = _refs({k: v for k, v in schema.items() if k != "$defs"})
        assert set(refs) <= {f"#/$defs/{name}" for name in defs}, tool["name"]
        for name, body in defs.items():
            assert refs.count(f"#/$defs/{name}") >= 2, (tool["name"], name)
            assert _refs(body) == [], (tool["name"], name)
        shared += len(defs)
    assert shared, "known positive: some output object is shared"


def test_shared_output_schemas_expand_to_the_inlined_schema():
    """#66: sharing a repeated object changes bytes, never meaning. Each tool's served output
    schema, expanded, equals its model's schema inlined before compaction."""
    from fastmcp.utilities.json_schema import dereference_refs

    from opendata_atlas.mcp.schema import compact_output_schema
    from opendata_atlas.mcp.tools import _TOOLS

    shared = 0
    for _fn, _title, model, _hints in _TOOLS:
        raw = model.model_json_schema()
        served = compact_output_schema(raw)
        shared += len(served.get("$defs", {}))
        inlined = compact_output_schema(dereference_refs(raw))
        assert "$defs" not in inlined and _refs(inlined) == [], model.__name__
        assert dereference_refs(served) == inlined, model.__name__
    assert shared, "known positive: some model has a repeated object"
