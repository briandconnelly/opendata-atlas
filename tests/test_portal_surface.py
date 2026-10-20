"""Milestone 2 Task 5: `portal` is required on every data tool and resolved per call."""

from __future__ import annotations

import json

import pytest
from fastmcp.exceptions import McpError

from opendata_atlas.core.reference import topics
from tests.conftest import SEATTLE_CONTEXT, wire

DATA_TOOLS = ("atlas_search_datasets", "atlas_describe_dataset", "atlas_query_dataset")
FIRE = "kzjm-xkqj"
SEPT = "datetime between '2026-09-01T00:00:00' and '2026-09-30T23:59:59'"
GUIDE_IDS = [d.item_id for d in topics(SEATTLE_CONTEXT)["guides"].documents]


def test_data_tools_require_portal(input_schemas):
    for tool in DATA_TOOLS:
        schema = input_schemas[tool]
        assert "portal" in schema["required"], tool
        assert next(iter(schema["properties"])) == "portal", f"{tool}: portal comes first"
        assert schema["properties"]["portal"]["pattern"]
    reference = input_schemas["atlas_get_reference"]
    assert "portal" in reference["properties"]
    assert "portal" not in reference.get("required", [])


@pytest.mark.parametrize("tool", DATA_TOOLS)
async def test_missing_portal_is_invalid_argument(client, tool):
    args = {"dataset_id": FIRE} if tool != "atlas_search_datasets" else {"query": "fire"}
    envelope = wire(await client.call_tool_mcp(tool, args))["structuredContent"]
    assert envelope["code"] == "invalid_argument"
    assert envelope["details"]["field"] == "portal"


PORTAL_NOT_FOUND_CASES = [
    ("atlas_search_datasets", {"query": "fire"}),
    ("atlas_describe_dataset", {"dataset_id": FIRE}),
    ("atlas_query_dataset", {"dataset_id": FIRE}),
    ("atlas_get_reference", {"topic": "guides"}),
]


@pytest.mark.parametrize(("tool", "args"), PORTAL_NOT_FOUND_CASES)
async def test_unknown_portal_is_enveloped_on_the_wire(client, tool, args):
    result = wire(await client.call_tool_mcp(tool, {"portal": "nowhere-portal-zz", **args}))
    assert result["isError"] is True
    envelope = result["structuredContent"]
    assert envelope["code"] == "portal_not_found"
    assert envelope["request_id"]
    assert envelope["repair"]["tool"] == "atlas_find_portals"
    assert "nowhere-portal-zz" not in json.dumps(result), "the value is never echoed"


@pytest.mark.parametrize(
    ("first", "second"), [("seattle", SEATTLE_CONTEXT.id), (SEATTLE_CONTEXT.id, "Seattle")]
)
@pytest.mark.soda_fixture("query_keyset_pages")
async def test_continuation_accepts_alias_or_canonical_id(client, soda, first, second):
    args = {"select": ["incident_number", "datetime"], "where": SEPT, "page_size": 3}
    page1 = wire(
        await client.call_tool_mcp(
            "atlas_query_dataset", {"portal": first, "dataset_id": FIRE, **args}
        )
    )["structuredContent"]
    assert page1["has_more"] is True
    page2 = wire(
        await client.call_tool_mcp(
            "atlas_query_dataset",
            {"portal": second, "dataset_id": FIRE, "cursor": page1["next_cursor"]},
        )
    )
    assert page2["isError"] is False, page2["structuredContent"]
    assert page2["structuredContent"]["source"]["portal"]["id"] == SEATTLE_CONTEXT.id


@pytest.mark.parametrize(
    ("first", "second"), [("seattle", SEATTLE_CONTEXT.id), (SEATTLE_CONTEXT.id, "seattle")]
)
@pytest.mark.soda_fixture("search_all_pages")
async def test_search_continuation_accepts_alias_or_canonical_id(client, soda, first, second):
    args = {"query": "neighborhood", "asset_scope": "all", "page_size": 4}
    page1 = wire(await client.call_tool_mcp("atlas_search_datasets", {"portal": first, **args}))[
        "structuredContent"
    ]
    page2 = wire(
        await client.call_tool_mcp(
            "atlas_search_datasets", {"portal": second, "cursor": page1["next_cursor"]}
        )
    )
    assert page2["isError"] is False, page2["structuredContent"]


@pytest.mark.soda_fixture("query_keyset_pages")
async def test_wrong_portal_cursor_rejected(client, soda):
    args = {"select": ["incident_number", "datetime"], "where": SEPT, "page_size": 3}
    page1 = wire(
        await client.call_tool_mcp(
            "atlas_query_dataset", {"portal": "seattle", "dataset_id": FIRE, **args}
        )
    )["structuredContent"]
    page2 = wire(
        await client.call_tool_mcp(
            "atlas_query_dataset",
            {"portal": "chicago", "dataset_id": FIRE, "cursor": page1["next_cursor"]},
        )
    )["structuredContent"]
    assert page2["code"] == "invalid_cursor"
    assert "portal" not in page2["repair"]["arguments"], "a paging-reference repair"


@pytest.mark.soda_fixture("search_all_pages")
async def test_wrong_portal_search_cursor_rejected(client, soda):
    args = {"query": "neighborhood", "asset_scope": "all", "page_size": 4}
    page1 = wire(
        await client.call_tool_mcp("atlas_search_datasets", {"portal": "seattle", **args})
    )["structuredContent"]
    page2 = wire(
        await client.call_tool_mcp(
            "atlas_search_datasets", {"portal": "chicago", "cursor": page1["next_cursor"]}
        )
    )["structuredContent"]
    assert page2["code"] == "invalid_cursor"


@pytest.mark.parametrize("portal", ["seattle", SEATTLE_CONTEXT.id])
async def test_guide_resources_live_under_the_portal(client, portal):
    index = json.loads(
        (await client.read_resource(f"opendata-atlas://portals/{portal}/guides"))[0].text
    )
    tool = wire(
        await client.call_tool_mcp("atlas_get_reference", {"topic": "guides", "portal": portal})
    )["structuredContent"]
    tool.pop("source")
    assert index == tool
    for entry in index["entries"]:
        assert (
            entry["uri"]
            == f"opendata-atlas://portals/{SEATTLE_CONTEXT.id}/guides/{entry['item_id']}"
        )
    guide_id = GUIDE_IDS[0]
    body = (await client.read_resource(f"opendata-atlas://portals/{portal}/guides/{guide_id}"))[
        0
    ].text
    item = wire(
        await client.call_tool_mcp(
            "atlas_get_reference", {"topic": "guides", "portal": portal, "item_id": guide_id}
        )
    )["structuredContent"]
    assert item["body"] == body
    assert item["uri"] == f"opendata-atlas://portals/{SEATTLE_CONTEXT.id}/guides/{guide_id}"


async def test_old_guide_resources_are_gone(client):
    for uri in ("opendata-atlas://guides", f"opendata-atlas://guides/{GUIDE_IDS[0]}"):
        with pytest.raises(McpError):
            await client.read_resource(uri)


async def test_guide_resource_with_unknown_portal_is_enveloped(client):
    uri = "opendata-atlas://portals/nowhere-portal-zz/guides"
    with pytest.raises(McpError) as caught:
        await client.read_resource(uri)
    assert caught.value.error.code == -32602
    data = caught.value.error.data
    assert data["machine_code"] == "portal_not_found"
    assert data["resource_uri"] == "opendata-atlas://portals/{portal}/guides"


def test_single_portal_binding_is_gone():
    from opendata_atlas.mcp import server, tools

    assert not hasattr(server, "SEATTLE_CONTEXT")
    assert not hasattr(tools, "_current_portal")
    assert not hasattr(tools, "_portal")


@pytest.mark.soda_fixture("describe_missing")
async def test_dataset_not_found_names_the_portal(client, soda):
    envelope = wire(
        await client.call_tool_mcp(
            "atlas_describe_dataset", {"portal": "seattle", "dataset_id": "abcd-1234"}
        )
    )["structuredContent"]
    assert envelope["code"] == "dataset_not_found"
    assert envelope["message"] == "No public dataset on City of Seattle has this id."
    assert "City of Seattle" in envelope["repair"]["alternative"]
    assert "another portal" in envelope["repair"]["alternative"]
    assert envelope["repair"]["arguments"] == {"portal": SEATTLE_CONTEXT.id}
