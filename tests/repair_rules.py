"""The repair-scope rule (Task 5): which repairs carry `portal`, and with which value."""

from __future__ import annotations

from typing import Any

import jsonschema

#: Tools whose calls read one portal's data; their repairs carry the canonical portal id.
DATA_TOOLS = frozenset({"atlas_search_datasets", "atlas_describe_dataset", "atlas_query_dataset"})


def assert_repair_scope(repair: dict[str, Any], portal_id: str) -> None:
    """A data-tool repair carries `portal` as the canonical id; a reference repair carries it
    only for topic guides; a find_portals repair never does."""
    tool, arguments = repair["tool"], repair["arguments"]
    if tool in DATA_TOOLS:
        assert arguments.get("portal") == portal_id, (
            f"{tool} repair must carry portal={portal_id!r}: {arguments}"
        )
    elif tool == "atlas_get_reference":
        if arguments.get("topic") == "guides":
            assert arguments.get("portal") == portal_id, arguments
        else:
            assert "portal" not in arguments, arguments
    elif tool == "atlas_find_portals":
        assert "portal" not in arguments, arguments


def assert_repair_callable(repair: dict, input_schemas: dict) -> None:
    """A repair names a published tool, and its arguments are literal and valid for it."""
    assert repair["tool"] in input_schemas, f"repair names unknown tool {repair['tool']}"
    jsonschema.validate(repair["arguments"], input_schemas[repair["tool"]])
    for value in repair["arguments"].values():
        assert "<" not in str(value), "repair arguments must be literal, not placeholders"
