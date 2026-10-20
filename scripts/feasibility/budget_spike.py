"""Measure the hypothetical five-tool `tools/list` against the 24 KiB budget (dev-only).

Usage: uv run python scripts/feasibility/budget_spike.py [OUT.json]

Loads today's `tools/list` from the in-process server, adds a required `portal` string
property to the four tools' input schemas, prepends `atlas_find_portals` (docs/design.md,
Tools 1), and prints both serialized sizes. The size is counted as `tests/test_contract.py`
counts it: compact JSON of the wire `tools/list` result, UTF-8 bytes. The served surface and
`tests/snapshots/tools_list.json` are not touched.
"""

from __future__ import annotations

import asyncio
import copy
import json
import sys
from pathlib import Path
from typing import Annotated, Any, Literal

from fastmcp import Client, FastMCP
from fastmcp.tools import ToolResult  # noqa: TC002 (FastMCP resolves annotations at runtime)
from fastmcp.tools.function_tool import FunctionTool
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from opendata_atlas.constants import TOOLS_LIST_BYTE_BUDGET
from opendata_atlas.core.models import Source  # noqa: TC001 (pydantic resolves field types)
from opendata_atlas.mcp.schema import compact_schema
from opendata_atlas.mcp.server import build_server


def wire(model: Any) -> dict[str, Any]:
    """Same as tests/conftest.py `wire`."""
    return model.model_dump(mode="json", by_alias=True, exclude_none=True)


def compact_json(data: Any) -> str:
    """Same as tests/conftest.py `compact_json`."""
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


PORTAL_PROPERTY: dict[str, Any] = {
    "type": "string",
    "pattern": "^[A-Za-z0-9][A-Za-z0-9.-]{1,99}$",
    "description": "Portal id or alias from atlas_find_portals, e.g. data.seattle.gov.",
}


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Jurisdiction(_Closed):
    level: Literal["city", "county", "region", "state", "national", "other"]
    country: str
    region: str | None = None


class PortalCandidate(_Closed):
    id: str
    aliases: list[str]
    name: str
    public_host: str
    jurisdiction: _Jurisdiction | None = None
    tier: Literal["generic", "profiled", "curated"]
    match: Literal["alias", "name", "place_name", "host"]


class FindPortalsResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    portals: list[PortalCandidate]
    has_more: bool
    next_cursor: str | None = None
    source: Source


async def atlas_find_portals(
    query: Annotated[
        str | None,
        Field(
            min_length=1,
            max_length=200,
            description='Place name, e.g. "Chicago"; omit to list curated, then profiled, portals.',
        ),
    ] = None,
    level: Annotated[
        Literal["city", "county", "region", "state", "national", "other"] | None,
        Field(description="Only portals whose jurisdiction has this level."),
    ] = None,
    country: Annotated[
        str | None,
        Field(min_length=2, max_length=2, description="Two-letter country code, e.g. US."),
    ] = None,
    tier: Annotated[
        Literal["generic", "profiled", "curated"] | None,
        Field(description="Only portals at this tier."),
    ] = None,
    page_size: Annotated[int | None, Field(ge=1, le=50, description="Default 10.")] = None,
    cursor: Annotated[
        str | None,
        Field(min_length=1, description="next_cursor from the previous page; omit for page one."),
    ] = None,
) -> ToolResult:
    """Resolve a place to portal ids. Call first when you do not know the portal id.

    Returns candidates and never picks one: "Chicago" returns the city and the county,
    told apart by jurisdiction.level. Ask the user when candidates differ in level.
    Example: {"query": "Chicago"}. Reads only the shipped registry; instant.
    """
    raise NotImplementedError


async def _find_portals_entry() -> dict[str, Any]:
    server = FastMCP("spike")
    tool = FunctionTool.from_function(
        atlas_find_portals,
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
        output_schema=compact_schema(FindPortalsResult.model_json_schema()),
    )
    tool.parameters = compact_schema(tool.parameters)
    server.add_tool(tool)
    async with Client(server) as client:
        listed = wire(await client.list_tools_mcp())
    return listed["tools"][0]


async def measure() -> dict[str, Any]:
    async with Client(build_server()) as client:
        current = wire(await client.list_tools_mcp())
    current_bytes = len(compact_json(current).encode())

    hypothetical = copy.deepcopy(current)
    for tool in hypothetical["tools"]:
        schema = tool["inputSchema"]
        schema["properties"]["portal"] = dict(PORTAL_PROPERTY)
        schema["required"] = ["portal", *schema.get("required", [])]
    find = await _find_portals_entry()
    find_bytes = len(compact_json(find).encode())
    hypothetical["tools"].insert(0, find)
    five_bytes = len(compact_json(hypothetical).encode())

    return {
        "measured_as": "len(compact_json(wire(list_tools_mcp())).encode()), as test_contract.py",
        "budget_bytes": TOOLS_LIST_BYTE_BUDGET,
        "current_four_tool_bytes": current_bytes,
        "portal_description_bytes": len(PORTAL_PROPERTY["description"].encode()),
        "atlas_find_portals_entry_bytes": find_bytes,
        "five_tool_bytes": five_bytes,
        "headroom_bytes": TOOLS_LIST_BYTE_BUDGET - five_bytes,
        "within_budget": five_bytes <= TOOLS_LIST_BYTE_BUDGET,
        "tools": [t["name"] for t in hypothetical["tools"]],
    }


def main() -> None:
    result = asyncio.run(measure())
    text = json.dumps(result, indent=2)
    print(text)
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(text + "\n")


if __name__ == "__main__":
    main()
