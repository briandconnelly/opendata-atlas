"""Curated guides: every example is a valid call, and every guide is reachable."""

from __future__ import annotations

import json
import re

import jsonschema
import pytest

from opendata_atlas.core import arguments
from opendata_atlas.core.describe import served_evidence
from opendata_atlas.portals.resolve import _pack_dirs, resolve_portal
from tests.conftest import SEATTLE_CONTEXT, wire

GUIDES = SEATTLE_CONTEXT.guides
#: The pack's timezone claims, keyed as the fork's TIME_EVIDENCE was.
TIME_EVIDENCE: dict[str, dict[str, dict[str, str | None]]] = {}
for _claim in SEATTLE_CONTEXT.pack.claims:
    if _claim.kind == "column_timezone" and _claim.interpretation and _claim.scope.dataset:
        TIME_EVIDENCE.setdefault(_claim.scope.dataset, {})[str(_claim.scope.column)] = {
            "timezone": _claim.interpretation.timezone,
            "evidence": served_evidence(_claim.evidence),
        }

EXAMPLES = [(g.guide_id, e) for g in GUIDES for e in g.examples]
#: Words a guide may use to assert a column's timezone, and the zone each one means.
TIMEZONE_WORDS = {
    "Pacific": "America/Los_Angeles",
    "America/Los_Angeles": "America/Los_Angeles",
    "UTC": "UTC",
}
TIMEZONE_PATTERN = r"\b(Pacific|America/Los_Angeles|UTC)\b"


@pytest.mark.parametrize(
    ("guide_id", "example"), EXAMPLES, ids=[f"{g}-{i}" for i, (g, _) in enumerate(EXAMPLES)]
)
def test_example_is_a_valid_query_call(input_schemas, guide_id, example):
    jsonschema.validate(example.arguments, input_schemas["atlas_query_dataset"])
    arguments.check_query({"mode": None, "soql": None, "cursor": None, **example.arguments})


#: Every shipped pack's guide examples, with the id of the pack that ships them.
PACK_EXAMPLES = [
    (pack_id, guide.guide_id, example)
    for pack_id in _pack_dirs()
    for guide in resolve_portal(pack_id).guides
    for example in guide.examples
]


@pytest.mark.parametrize(
    ("pack_id", "guide_id", "example"),
    PACK_EXAMPLES,
    ids=[f"{p}-{g}-{i}" for i, (p, g, _) in enumerate(PACK_EXAMPLES)],
)
def test_example_portal_resolves_to_its_pack(pack_id, guide_id, example):
    """An example that names another portal would run a guide's query on the wrong portal."""
    assert resolve_portal(example.arguments["portal"]).identity.id == pack_id, guide_id


def test_every_pack_example_is_checked():
    assert len(PACK_EXAMPLES) >= len(EXAMPLES) > 0


def test_examples_use_their_guide_dataset():
    for guide in GUIDES:
        assert all(e.arguments["dataset_id"] == guide.dataset_id for e in guide.examples)


@pytest.mark.parametrize("guide", GUIDES, ids=[g.guide_id for g in GUIDES])
def test_guide_timezone_claims_have_evidence(guide):
    for line in guide.render().splitlines():
        claimed = {TIMEZONE_WORDS[w] for w in re.findall(TIMEZONE_PATTERN, line)}
        if not claimed:
            continue
        field = re.match(r"- `([^`]+)`:", line)
        assert field is not None, f"Timezone claim needs a column: {line}"
        evidence = TIME_EVIDENCE.get(guide.dataset_id, {}).get(field[1], {})
        assert claimed == {evidence.get("timezone")}, (guide.guide_id, field[1], claimed)
        assert evidence.get("evidence"), (guide.guide_id, field[1])


@pytest.mark.parametrize("guide", GUIDES, ids=[g.guide_id for g in GUIDES])
async def test_guide_reachable_by_tool_and_resource(client, guide):
    tool = wire(
        await client.call_tool_mcp(
            "atlas_get_reference",
            {"topic": "guides", "portal": "seattle", "item_id": guide.guide_id},
        )
    )
    resource = await client.read_resource(
        f"opendata-atlas://portals/seattle/guides/{guide.guide_id}"
    )
    assert tool["structuredContent"]["body"] == resource[0].text == guide.render()
    assert guide.dataset_id in resource[0].text


async def test_guide_index_entries_carry_dataset_id(client):
    tool = wire(
        await client.call_tool_mcp("atlas_get_reference", {"topic": "guides", "portal": "seattle"})
    )
    resource = json.loads(
        (await client.read_resource("opendata-atlas://portals/seattle/guides"))[0].text
    )
    expected = {g.guide_id: g.dataset_id for g in GUIDES}
    for index in (tool["structuredContent"], resource):
        assert {e["item_id"]: e["dataset_id"] for e in index["entries"]} == expected


async def test_non_guide_index_entries_omit_dataset_id(client):
    tool = wire(await client.call_tool_mcp("atlas_get_reference", {"topic": "soql"}))
    assert all("dataset_id" not in e for e in tool["structuredContent"]["entries"])


@pytest.mark.soda_fixture("describe_fire_summary")
async def test_describe_links_guide_and_examples(client, soda):
    out = wire(
        await client.call_tool_mcp(
            "atlas_describe_dataset", {"portal": "seattle", "dataset_id": "kzjm-xkqj"}
        )
    )["structuredContent"]
    assert out["guide_uri"] == "opendata-atlas://portals/data.seattle.gov/guides/fire-911"
    assert out["example_queries"][0]["arguments"]["dataset_id"] == "kzjm-xkqj"


@pytest.mark.soda_fixture("describe_filter_view")
async def test_filter_view_links_parent_guide_without_examples(client, soda):
    out = wire(
        await client.call_tool_mcp(
            "atlas_describe_dataset",
            {"portal": "seattle", "dataset_id": "8tqq-u7ib", "sample_rows": 1},
        )
    )["structuredContent"]
    assert out["guide_uri"] == "opendata-atlas://portals/data.seattle.gov/guides/building-permits"
    assert "example_queries" not in out


@pytest.mark.soda_fixture("search_fire")
async def test_search_links_guide(client, soda):
    out = wire(
        await client.call_tool_mcp(
            "atlas_search_datasets", {"portal": "seattle", "query": "fire 911", "page_size": 3}
        )
    )["structuredContent"]
    fire = next(d for d in out["datasets"] if d["dataset_id"] == "kzjm-xkqj")
    assert fire["guide_uri"] == "opendata-atlas://portals/data.seattle.gov/guides/fire-911"
