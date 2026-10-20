"""Reference content: tool and resources serve one copy; instructions keep their binding prefix."""

from __future__ import annotations

import json

import pytest

from opendata_atlas.constants import INSTRUCTIONS_SENTINEL
from opendata_atlas.core.reference import CAPABILITIES, INSTRUCTIONS, topics
from tests.conftest import SEATTLE_CONTEXT, wire

TOPICS = topics(SEATTLE_CONTEXT)

DOCUMENTS = [(topic, doc.item_id) for topic, t in TOPICS.items() for doc in t.documents]


@pytest.mark.parametrize(("topic", "item_id"), DOCUMENTS)
async def test_tool_and_resource_serve_the_same_body(client, topic, item_id):
    args = {"topic": topic, "item_id": item_id}
    uri = f"opendata-atlas://{topic}/{item_id}"
    if topic == "guides":
        args["portal"] = "seattle"
        uri = f"opendata-atlas://portals/{SEATTLE_CONTEXT.id}/guides/{item_id}"
    tool = wire(await client.call_tool_mcp("atlas_get_reference", args))
    resource = await client.read_resource(uri)
    assert tool["isError"] is False
    assert tool["structuredContent"]["body"] == resource[0].text
    assert tool["structuredContent"]["uri"] == uri


async def test_index_entries_resolve_as_resources(client):
    index = wire(await client.call_tool_mcp("atlas_get_reference", {}))["structuredContent"]
    # Guides live under a portal: the portals topic lists each portal's guide index.
    assert {e["item_id"] for e in index["entries"]} == set(TOPICS) - {"guides"}
    for entry in index["entries"]:
        assert await client.read_resource(entry["uri"])
    reference = json.loads((await client.read_resource(index["uri"]))[0].text)
    assert reference["entries"] == index["entries"]


async def test_capabilities_resource(client):
    assert (await client.read_resource("opendata-atlas://capabilities"))[0].text == CAPABILITIES


def test_instructions_end_with_sentinel():
    assert INSTRUCTIONS.splitlines()[-1] == INSTRUCTIONS_SENTINEL


def test_instructions_lead_with_negative_scope():
    head = INSTRUCTIONS[:400]
    assert "Does NOT" in head
    assert "ArcGIS" in head


async def test_instructions_reach_the_client(client):
    assert client.instructions == INSTRUCTIONS


def test_capabilities_names_only_real_tools():
    import re

    named = set(re.findall(r"atlas_[a-z_]+", CAPABILITIES + INSTRUCTIONS))
    assert named <= {
        "atlas_find_portals",
        "atlas_search_datasets",
        "atlas_describe_dataset",
        "atlas_query_dataset",
        "atlas_get_reference",
    }


def test_query_description_states_the_real_cap():
    from opendata_atlas.constants import QUERY_LOGICAL_CAP
    from opendata_atlas.mcp.tools import atlas_query_dataset

    assert f"{QUERY_LOGICAL_CAP:,} rows" in (atlas_query_dataset.__doc__ or "")


def test_error_catalog_discloses_the_dataset_id_echo():
    """dataset_not_found and dataset_not_queryable put the caller's dataset_id in details.value."""
    from opendata_atlas.core import reference_service
    from tests.conftest import SEATTLE_CONTEXT

    body = reference_service.read(SEATTLE_CONTEXT, "errors", "envelope").body
    assert body is not None
    policy = next(line for line in body.splitlines() if line.startswith("Value policy:"))
    assert "caller's `dataset_id`" in policy


@pytest.mark.parametrize(
    ("args", "has_portal"),
    [
        ({"topic": "index"}, False),
        ({"topic": "capabilities"}, False),
        ({"topic": "soql"}, False),
        ({"topic": "soql", "item_id": "syntax"}, False),
        ({"topic": "errors"}, False),
        ({"topic": "errors", "item_id": "codes"}, False),
        ({"topic": "contributing"}, False),
        ({"topic": "portals"}, False),
        ({"topic": "portals", "item_id": "seattle"}, True),
        ({"topic": "guides", "portal": "seattle"}, True),
        ({"topic": "guides", "portal": "seattle", "item_id": "fire-911"}, True),
    ],
)
async def test_reference_source_names_a_portal_only_for_portal_topics(client, args, has_portal):
    source = wire(await client.call_tool_mcp("atlas_get_reference", args))["structuredContent"][
        "source"
    ]
    assert ("portal" in source) is has_portal
    assert ("now_local" in source) is has_portal
    assert ("now_weekday" in source) is has_portal
    if has_portal:
        assert source["portal"]["id"] == SEATTLE_CONTEXT.id
