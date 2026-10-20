"""Milestone 2 standards review (docs/reviews/2026-10-18-m2-standards.md): behavior fixes."""

from __future__ import annotations

import pytest
from fastmcp import Client
from fastmcp.exceptions import McpError
from mcp.types import ResourceTemplateReference

from opendata_atlas.constants import PORTALS_ENV
from opendata_atlas.core import cursor as cursors
from opendata_atlas.mcp.server import build_server
from opendata_atlas.portals.registry import load_registry
from tests.conftest import SEATTLE_CONTEXT, wire

ERAS = [{"mode": "legacy"}, {}]
ERA_IDS = ["legacy", "modern"]


# --- [6.details-field]: on a resource, `details.field` is the method's parameter, `uri` ---


@pytest.mark.parametrize(
    "uri",
    [
        "opendata-atlas://soql/nope",
        "opendata-atlas://errors/nope",
        "opendata-atlas://portals/seattle/guides/nope",
    ],
)
async def test_reference_not_found_on_a_resource_names_uri(client, uri):
    with pytest.raises(McpError) as caught:
        await client.read_resource_mcp(uri)
    data = caught.value.error.data
    assert data["machine_code"] == "reference_not_found"
    assert data["details"]["field"] == "uri"
    assert data["details"]["candidates"], "the candidates still help the agent build a URI"


async def test_reference_not_found_on_the_tool_still_names_item_id(client):
    result = wire(
        await client.call_tool_mcp("atlas_get_reference", {"topic": "soql", "item_id": "x"})
    )
    assert result["structuredContent"]["details"]["field"] == "item_id"


# --- [6.details-field]: describe's cursor parameter is `column_cursor`, not `cursor` ---


@pytest.mark.parametrize(
    "column_cursor",
    [
        "garbage",  # malformed
        cursors.encode("search", {}, portal_id=SEATTLE_CONTEXT.id),  # another tool's cursor
        cursors.encode("columns", {}, portal_id="data.cityofchicago.org"),  # another portal's
    ],
    ids=["malformed", "other-tool", "other-portal"],
)
async def test_describe_cursor_errors_name_column_cursor(client, column_cursor):
    args = {"portal": "seattle", "dataset_id": "kzjm-xkqj", "column_cursor": column_cursor}
    envelope = wire(await client.call_tool_mcp("atlas_describe_dataset", args))["structuredContent"]
    assert envelope["code"] == "invalid_cursor"
    assert envelope["details"]["field"] == "column_cursor"


# --- [1.negotiated-caps]: advertise only what is served; logging is never sent ---


@pytest.mark.parametrize("kwargs", ERAS, ids=ERA_IDS)
async def test_logging_is_not_advertised(kwargs):
    async with Client(build_server(), **kwargs) as client:
        capabilities = client.server_capabilities.model_dump(exclude_none=True)
    assert "logging" not in capabilities


# --- [4.template-completion] [2.completion]: completion for the URI template variables ---

PORTAL_TEMPLATE = ResourceTemplateReference(uri="opendata-atlas://portals/{portal}")
GUIDE_TEMPLATE = ResourceTemplateReference(
    uri="opendata-atlas://portals/{portal}/guides/{guide_id}"
)


@pytest.mark.parametrize("kwargs", ERAS, ids=ERA_IDS)
async def test_completions_are_advertised_and_answer_on_both_eras(kwargs):
    async with Client(build_server(), **kwargs) as client:
        assert client.server_capabilities.completions is not None
        result = await client.complete_mcp(PORTAL_TEMPLATE, {"name": "portal", "value": "seat"})
    assert result.completion.values == ["seattle"]


@pytest.mark.parametrize(
    "template",
    [
        "opendata-atlas://portals/{portal}",
        "opendata-atlas://portals/{portal}/guides",
        "opendata-atlas://portals/{portal}/guides/{guide_id}",
    ],
)
async def test_portal_completion_matches_ids_and_aliases_by_prefix(client, template):
    ref = ResourceTemplateReference(uri=template)
    by_alias = await client.complete_mcp(ref, {"name": "portal", "value": "CHIC"})
    assert "chicago" in by_alias.completion.values
    by_id = await client.complete_mcp(ref, {"name": "portal", "value": "data.cityofch"})
    assert by_id.completion.values == ["data.cityofchicago.org"]


async def test_portal_completion_is_capped_and_says_so(client):
    result = (
        await client.complete_mcp(PORTAL_TEMPLATE, {"name": "portal", "value": ""})
    ).completion
    registry = load_registry()
    names = {e.identity.id for e in registry.entries.values() if e.identity.status == "active"}
    aliases = sorted(a for e in registry.entries.values() for a in e.identity.aliases)
    assert len(result.values) == 100
    assert result.total == len(names) + len(aliases)
    assert result.has_more is True
    assert result.values[: len(aliases)] == aliases, "aliases first, then ids, each sorted"
    assert result.values[len(aliases)] == min(names)


async def test_portal_completion_respects_the_allowlist(monkeypatch):
    monkeypatch.setenv(PORTALS_ENV, "seattle")
    async with Client(build_server()) as client:
        result = await client.complete_mcp(PORTAL_TEMPLATE, {"name": "portal", "value": ""})
    assert result.completion.values == ["seattle", "data.seattle.gov"]


async def test_guide_completion_uses_the_portal_in_context(client):
    result = await client.complete_mcp(
        GUIDE_TEMPLATE, {"name": "guide_id", "value": "spd"}, {"portal": "seattle"}
    )
    assert result.completion.values == ["spd-calls", "spd-crime"]
    no_portal = await client.complete_mcp(GUIDE_TEMPLATE, {"name": "guide_id", "value": "spd"})
    assert no_portal.completion.values == []
    bad_portal = await client.complete_mcp(
        GUIDE_TEMPLATE, {"name": "guide_id", "value": ""}, {"portal": "nope.example"}
    )
    assert bad_portal.completion.values == []


@pytest.mark.parametrize(
    ("template", "value", "expected"),
    [
        ("opendata-atlas://soql/{section_id}", "pa", ["paging"]),
        ("opendata-atlas://errors/{section_id}", "", ["envelope", "codes", "authentication"]),
    ],
)
async def test_section_completion(client, template, value, expected):
    ref = ResourceTemplateReference(uri=template)
    result = await client.complete_mcp(ref, {"name": "section_id", "value": value})
    assert result.completion.values == expected


async def test_completion_of_an_unknown_reference_is_empty(client):
    ref = ResourceTemplateReference(uri="opendata-atlas://nope/{x}")
    result = await client.complete_mcp(ref, {"name": "x", "value": ""})
    assert result.completion.values == []
