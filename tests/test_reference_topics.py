"""Milestone 2 Task 11: portal-aware reference topics, resources and served text."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest
from fastmcp.exceptions import McpError

from opendata_atlas.core.reference import CAPABILITIES, HEAD_RULES, INSTRUCTIONS, topics
from opendata_atlas.portals.loader import load_portal
from opendata_atlas.portals.packfile import PORTALS_DIR
from opendata_atlas.portals.registry import REGISTRY_PATH
from tests.conftest import SEATTLE_CONTEXT, wire

ROOT = Path(__file__).resolve().parent.parent
SEATTLE = SEATTLE_CONTEXT.id
GUIDE_IDS = [g.guide_id for g in SEATTLE_CONTEXT.guides]
ALLOWLIST_ENV = "OPENDATA_ATLAS_PORTALS"


async def ref(client, **args):
    return wire(await client.call_tool_mcp("atlas_get_reference", args))


def _section(markdown: str, heading: str) -> str:
    match = re.search(rf"^## {heading}\n(.*?)(?=^## |\Z)", markdown, re.MULTILINE | re.DOTALL)
    assert match, f"no ## {heading} section"
    return match.group(1)


# --- topic portals ----------------------------------------------------------------


async def test_portals_topic_lists_curated_portals(client):
    result = await ref(client, topic="portals")
    assert result["isError"] is False
    index = result["structuredContent"]
    assert index["uri"] == "opendata-atlas://portals"
    assert "portal" not in index["source"], "the index names no portal"
    ids = [e["item_id"] for e in index["entries"]]
    assert SEATTLE in ids
    from opendata_atlas.portals.registry import load_registry

    registry = load_registry()
    for entry in index["entries"]:
        assert registry.entries[entry["item_id"]].identity.tier in ("curated", "profiled")
        assert entry["uri"] == f"opendata-atlas://portals/{entry['item_id']}"
    resource = json.loads((await client.read_resource("opendata-atlas://portals"))[0].text)
    index.pop("source")
    assert resource == index


@pytest.mark.parametrize("item_id", ["seattle", SEATTLE, "Seattle"])
async def test_portals_topic_item_reports_knowledge_summary(client, item_id):
    result = (await ref(client, topic="portals", item_id=item_id))["structuredContent"]
    assert result["uri"] == f"opendata-atlas://portals/{SEATTLE}"
    assert result["source"]["portal"]["id"] == SEATTLE, "the item names its portal"
    body = result["body"]
    for heading in ("Identity", "Knowledge", "Guides"):
        assert f"## {heading}" in body
    identity = _section(body, "Identity")
    assert SEATTLE in identity and "curated" in identity
    knowledge = _section(body, "Knowledge")
    from opendata_atlas.portals.knowledge import pack_levels

    levels = pack_levels(SEATTLE_CONTEXT, today=date(2026, 10, 18))
    assert levels, "the Seattle pack records knowledge"
    for dataset_id, level in levels.items():
        line = next(line for line in knowledge.splitlines() if dataset_id in line)
        assert line.startswith(f"- {level}:"), line
    for guide in SEATTLE_CONTEXT.guides:
        if guide.dataset_id in levels:
            assert f"`{guide.dataset_id}` ({guide.title})" in knowledge, "id and title"
    guides = _section(body, "Guides")
    for guide_id in GUIDE_IDS:
        assert f"opendata-atlas://portals/{SEATTLE}/guides/{guide_id}" in guides
    resource = (await client.read_resource(f"opendata-atlas://portals/{SEATTLE}"))[0].text
    assert resource == body


async def test_portal_index_stays_well_inside_the_result_budget():
    """Fails at 80% of the budget, so the index gains its cursor before it is cut."""
    from opendata_atlas.constants import RESULT_BYTE_BUDGET
    from opendata_atlas.core import reference_service
    from opendata_atlas.core.budget import payload_size

    index = reference_service.read(None, "portals", None)
    assert index.entries
    assert payload_size(index) <= 0.8 * RESULT_BYTE_BUDGET


async def test_malformed_item_id_gets_the_find_portal_repair(client):
    raw = "Seattle WA"
    result = await ref(client, topic="portals", item_id=raw)
    envelope = result["structuredContent"]
    assert envelope["code"] == "invalid_argument"
    assert envelope["details"]["field"] == "item_id"
    assert envelope["repair"]["next_step"] == "find_portal"
    assert envelope["repair"]["tool"] == "atlas_find_portals"
    assert raw not in json.dumps(result)


async def test_malformed_resource_segment_names_the_segment(client):
    with pytest.raises(McpError) as caught:
        await client.read_resource("opendata-atlas://portals/Seattle%20WA/guides")
    data = caught.value.error.data
    assert caught.value.error.code == -32602
    assert data["machine_code"] == "invalid_argument"
    assert data["details"]["field"] == "uri"
    assert "the {portal} segment must be a portal id or alias" in data["details"]["reason"]
    assert data["resource_uri"] == "opendata-atlas://portals/{portal}/guides"
    assert data["repair"]["tool"] == "atlas_find_portals"
    assert "Seattle" not in json.dumps(data)


def test_item_id_accepts_any_portal_id_length(input_schemas):
    from opendata_atlas.constants import PORTAL_PATTERN

    item_id = input_schemas["atlas_get_reference"]["properties"]["item_id"]
    assert "99}" in PORTAL_PATTERN, "PORTAL_PATTERN allows 100 characters"
    assert item_id["maxLength"] == 100


def _registry_only_portal() -> str:
    """A portal in `registry.json` that no pack defines. Chosen from the files, not named,
    so a new pack never turns it into a portal with one (Chicago did, ruling 85)."""
    packed = {load_portal(p.parent).identity.id for p in PORTALS_DIR.glob("*/portal.toml")}
    listed = json.loads(REGISTRY_PATH.read_text())["entries"]
    return min(e["identity"]["id"] for e in listed if e["identity"]["id"] not in packed)


async def test_portals_item_for_a_portal_without_a_pack(client):
    portal = _registry_only_portal()
    body = (await ref(client, topic="portals", item_id=portal))["structuredContent"]["body"]
    assert f"`{portal}`" in _section(body, "Identity"), "the item is the chosen portal"
    assert "generic" in _section(body, "Identity")
    assert "none" in _section(body, "Knowledge")
    assert "No guides" in _section(body, "Guides")


async def test_portals_item_unknown_portal_names_item_id_and_never_echoes(client):
    raw = "nowhere-portal-zz"
    result = await ref(client, topic="portals", item_id=raw)
    envelope = result["structuredContent"]
    assert envelope["code"] == "portal_not_found"
    assert envelope["details"]["field"] == "item_id"
    assert envelope["repair"]["tool"] == "atlas_find_portals"
    assert raw not in json.dumps(result)


@pytest.mark.parametrize(
    "dataset_id",
    [
        pytest.param("kzjm-xkqj", marks=pytest.mark.soda_fixture("describe_fire_full")),
        pytest.param("tazs-3rd5", marks=pytest.mark.soda_fixture("describe_crime_full")),
        # The reviewed dataset: its recorded view only, with row aggregates timed out;
        # describe computes knowledge from the schema, not from the aggregates.
        pytest.param(
            "33kz-ixgy",
            marks=pytest.mark.soda_fixture(
                "query_knowledge", overrides={"/resource/33kz-ixgy": "timeout"}
            ),
        ),
    ],
)
async def test_pack_levels_agree_with_describe_on_recorded_datasets(client, soda, dataset_id):
    """The summary's level is computed offline; on recorded datasets describe agrees."""
    from opendata_atlas.portals.knowledge import pack_levels

    levels = pack_levels(SEATTLE_CONTEXT, today=date(2026, 10, 18))
    out = wire(
        await client.call_tool_mcp(
            "atlas_describe_dataset",
            {
                "portal": "seattle",
                "dataset_id": dataset_id,
                "detail": "summary" if dataset_id == "33kz-ixgy" else "full",
            },
        )
    )["structuredContent"]
    assert out["knowledge"]["level"] == levels[dataset_id]
    if dataset_id == "33kz-ixgy":
        assert levels[dataset_id] == "reviewed", "the agreement covers a reviewed dataset"


# --- topic guides, contributing, and the portal argument -------------------------


async def test_guides_topic_requires_portal(client):
    for args in ({"topic": "guides"}, {"topic": "guides", "item_id": GUIDE_IDS[0]}):
        envelope = (await ref(client, **args))["structuredContent"]
        assert envelope["code"] == "invalid_argument"
        assert envelope["details"]["field"] == "portal"
        assert envelope["repair"] == {
            "next_step": "list_topics",
            "tool": "atlas_get_reference",
            "arguments": {},
        }


@pytest.mark.parametrize(
    "args",
    [
        {},
        {"topic": "index"},
        {"topic": "capabilities"},
        {"topic": "soql"},
        {"topic": "soql", "item_id": "dates"},
        {"topic": "errors"},
        {"topic": "contributing"},
        {"topic": "portals"},
        {"topic": "portals", "item_id": "seattle"},
    ],
)
async def test_portal_is_rejected_on_every_other_topic(client, args):
    raw = "secret-looking-portal-value"
    result = await ref(client, **args, portal=raw)
    envelope = result["structuredContent"]
    assert envelope["code"] == "invalid_argument"
    assert envelope["details"]["field"] == "portal"
    assert envelope["repair"]["arguments"] == {}
    assert raw not in json.dumps(result)
    if args.get("topic") == "portals":
        assert "item_id" in envelope["details"]["reason"]


async def test_contributing_topic_defines_tiers_and_levels(client):
    result = (await ref(client, topic="contributing"))["structuredContent"]
    assert result["uri"] == "opendata-atlas://contributing"
    assert "portal" not in result["source"]
    body = result["body"]
    for word in ("generic", "profiled", "curated", "none", "reviewed"):
        assert f"`{word}`" in body
    assert '"unchecked"' in body
    assert "uv run atlas-profile <host>" in body, "the contribution path (Task 13)"
    assert (await client.read_resource("opendata-atlas://contributing"))[0].text == body


async def test_contributing_has_no_items(client):
    envelope = (await ref(client, topic="contributing", item_id="x"))["structuredContent"]
    assert envelope["code"] == "invalid_argument"
    assert envelope["repair"]["arguments"] == {}


def test_reference_portal_parameter_description(input_schemas):
    portal = input_schemas["atlas_get_reference"]["properties"]["portal"]
    assert portal["description"] == (
        "Portal id or alias. Required for topic guides; rejected on other topics."
    )
    topic = input_schemas["atlas_get_reference"]["properties"]["topic"]
    assert set(topic["enum"]) == {
        "index",
        "capabilities",
        "portals",
        "guides",
        "soql",
        "errors",
        "contributing",
    }


@pytest.mark.parametrize(
    ("args", "portal"),
    [
        ({"topic": "portals"}, None),
        ({"topic": "portals", "item_id": "seattle"}, SEATTLE),
        ({"topic": "guides", "portal": "seattle"}, SEATTLE),
        ({"topic": "contributing"}, None),
    ],
)
async def test_source_portal_per_topic(client, args, portal):
    source = (await ref(client, **args))["structuredContent"]["source"]
    assert (source.get("portal") or {}).get("id") == portal


# --- index: only readable URIs ---------------------------------------------------


async def test_index_lists_only_readable_uris(client):
    index = (await ref(client))["structuredContent"]
    names = {e["item_id"] for e in index["entries"]}
    assert names == {"capabilities", "portals", "soql", "errors", "contributing"}
    for entry in index["entries"]:
        assert "{" not in entry["uri"], entry
        assert await client.read_resource(entry["uri"])
    assert "portals" in index["summary"] and "guides" in index["summary"]


# --- resources and their tool fallbacks (docs/design.md table) -------------------

#: (resource URI template, tool fallback arguments). Placeholders are filled per row.
FALLBACKS = [
    ("opendata-atlas://reference", {}),
    ("opendata-atlas://capabilities", {"topic": "capabilities"}),
    ("opendata-atlas://soql", {"topic": "soql"}),
    ("opendata-atlas://soql/{section_id}", {"topic": "soql", "item_id": "dates"}),
    ("opendata-atlas://errors", {"topic": "errors"}),
    ("opendata-atlas://errors/{section_id}", {"topic": "errors", "item_id": "envelope"}),
    ("opendata-atlas://portals", {"topic": "portals"}),
    ("opendata-atlas://portals/{portal}", {"topic": "portals", "item_id": SEATTLE}),
    ("opendata-atlas://portals/{portal}/guides", {"topic": "guides", "portal": SEATTLE}),
    (
        "opendata-atlas://portals/{portal}/guides/{guide_id}",
        {"topic": "guides", "portal": SEATTLE, "item_id": GUIDE_IDS[0]},
    ),
    ("opendata-atlas://contributing", {"topic": "contributing"}),
]


def _shape(uri: str) -> str:
    return re.sub(r"\{[a-z_]+\}", "{}", uri)


def _design_resources() -> set[str]:
    text = (ROOT / "docs/design.md").read_text()
    table = text.split("### Resources and their tool fallbacks", 1)[1].split("\n### ", 1)[0]
    return {_shape(u) for u in re.findall(r"`(opendata-atlas://[^`]+)`", table)}


async def test_every_resource_has_a_tool_fallback(client):
    served = {str(r.uri) for r in await client.list_resources()}
    served |= {t.uri_template for t in await client.list_resource_templates()}
    table = {_shape(uri) for uri, _ in FALLBACKS}
    assert {_shape(u) for u in served} == table, "every served resource is in the table"
    assert _design_resources() == table, "the table matches docs/design.md"
    for template, args in FALLBACKS:
        uri = (
            template.replace("{section_id}", args.get("item_id", ""))
            .replace("{portal}", SEATTLE)
            .replace("{guide_id}", args.get("item_id", ""))
        )
        text = (await client.read_resource(uri))[0].text
        tool = (await ref(client, **args))["structuredContent"]
        if "item_id" in args or args.get("topic") in ("capabilities", "contributing"):
            assert text == tool["body"], uri
        else:
            tool.pop("source")
            assert json.loads(text) == tool, uri


# --- resource-path portal errors (carried item 4) --------------------------------

RESOURCE_TEMPLATES = [
    "opendata-atlas://portals/{portal}",
    "opendata-atlas://portals/{portal}/guides",
    "opendata-atlas://portals/{portal}/guides/fire-911",
]


def _retire_chicago(monkeypatch):
    from tests.test_resolve import with_retired

    with_retired(monkeypatch)


@pytest.mark.parametrize("template", RESOURCE_TEMPLATES)
@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ("nowhere-portal-zz", "portal_not_found"),
        ("seattle", "portal_not_enabled"),
        ("chicago", "portal_retired"),
    ],
)
async def test_resource_portal_errors_use_invalid_params_and_never_echo(
    client, monkeypatch, template, raw, code
):
    if code == "portal_not_enabled":
        monkeypatch.setenv(ALLOWLIST_ENV, "chicago")
    else:
        monkeypatch.delenv(ALLOWLIST_ENV, raising=False)
    if code == "portal_retired":
        _retire_chicago(monkeypatch)
    with pytest.raises(McpError) as caught:
        await client.read_resource(template.replace("{portal}", raw))
    error = caught.value.error
    assert error.code == -32602
    data = error.data
    assert data["machine_code"] == code
    assert data["details"]["field"] == "uri"
    assert data["resource_uri"] == template.replace("guides/fire-911", "guides/{guide_id}")
    assert data["repair"]["tool"] == "atlas_find_portals"
    assert raw not in json.dumps(data) and raw not in error.message


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ("nowhere-portal-zz", "portal_not_found"),
        ("seattle", "portal_not_enabled"),
        ("chicago", "portal_retired"),
    ],
)
async def test_tool_portal_errors_name_the_portal_field(client, monkeypatch, raw, code):
    if code == "portal_not_enabled":
        monkeypatch.setenv(ALLOWLIST_ENV, "chicago")
    else:
        monkeypatch.delenv(ALLOWLIST_ENV, raising=False)
    if code == "portal_retired":
        _retire_chicago(monkeypatch)
    result = wire(
        await client.call_tool_mcp("atlas_search_datasets", {"portal": raw, "query": "fire"})
    )
    envelope = result["structuredContent"]
    assert envelope["code"] == code
    assert envelope["details"]["field"] == "portal"
    assert raw not in json.dumps(result)


# --- served text (carried items 5-7) ----------------------------------------------


def test_instructions_describe_a_multi_portal_server():
    first = INSTRUCTIONS.splitlines()[0]
    assert "Socrata" in first and "portal" in first
    does_not = next(line for line in INSTRUCTIONS.splitlines() if line.startswith("Does NOT"))
    for exclusion in ("write", "private", "ArcGIS", "geocode", "export"):
        assert exclusion in does_not
    for local in ("performance.", "King County", "data.wa.gov"):
        assert local not in INSTRUCTIONS + CAPABILITIES


MILESTONE_2_RULES = [
    ("atlas_find_portals", "unless the request names the level"),
    ("no reviewed place field", "unverified"),
    ("now_local", "never silently assume a zone; state the zone"),
]


@pytest.mark.parametrize(("marker", "obligation"), MILESTONE_2_RULES)
def test_milestone_2_head_rules_are_served(marker, obligation):
    rule = next((r for r in HEAD_RULES if marker in r and obligation in r), None)
    assert rule is not None, f"no head rule with {marker!r} and {obligation!r}"
    assert f"- {rule}" in INSTRUCTIONS.splitlines()
    assert f"- {rule}" in _section(CAPABILITIES, "Rules").splitlines()


def test_knowledge_rule_is_served_in_rules_only():
    """Ruling 23: knowledge_notice.message carries its own caveat, so the rule leaves the head."""
    from opendata_atlas.core.reference import CAPABILITY_RULES

    rule = next(r for r in CAPABILITY_RULES if "knowledge_notice" in r and "say so" in r)
    assert f"- {rule}" in _section(CAPABILITIES, "Rules").splitlines()
    assert "knowledge_notice" not in INSTRUCTIONS


def test_every_rule_is_restated_under_rules():
    from opendata_atlas.core.reference import CAPABILITY_RULES

    rules = _section(CAPABILITIES, "Rules").splitlines()
    for rule in (*HEAD_RULES, *CAPABILITY_RULES):
        assert f"- {rule}" in rules


#: Ruling 23: the instructions fit the shortest prefix on record (2,048 characters) with room.
INSTRUCTIONS_MAX_CHARS = 1_800


def test_instructions_fit_the_ruling_23_limit():
    assert len(INSTRUCTIONS) <= INSTRUCTIONS_MAX_CHARS, len(INSTRUCTIONS)


RULE = (
    "Offer the user a defect or knowledge-gap issue (capabilities ## Defects, ## Knowledge gaps)."
)


def test_defect_head_rule_is_short_and_details_stay_in_defects():
    rule = next(r for r in HEAD_RULES if "## Defects" in r)
    assert rule == RULE
    assert "Never file an issue unasked." in HEAD_RULES
    defects = _section(CAPABILITIES, "Defects")
    from opendata_atlas.constants import ISSUES_URL

    for item in (ISSUES_URL, "error code", "`request_id`", "server version"):
        assert item in defects


def test_knowledge_gap_head_rule_and_section():
    assert RULE in HEAD_RULES
    assert "Never file an issue unasked." in HEAD_RULES
    headings = [line for line in CAPABILITIES.splitlines() if line.startswith("## ")]
    assert headings.index("## Knowledge gaps") == headings.index("## Defects") + 1
    gaps = _section(CAPABILITIES, "Knowledge gaps")
    for item in ("knowledge-gap", "portal id", "dataset id", "column"):
        assert item in gaps


def test_defect_report_tool_call_rule_is_in_rules():
    """S-M2: the review obligation is a rule, not a trailing clause of ## Defects."""
    rules = _section(CAPABILITIES, "Rules").splitlines()
    assert "- In a defect report, include the tool call, once the user has reviewed it." in rules
    assert "tool call" not in _section(CAPABILITIES, "Defects")


def test_examples_are_illustrative():
    from opendata_atlas.core.reference import ERROR_EXAMPLES
    from tests.repair_rules import DATA_TOOLS

    for example in ERROR_EXAMPLES.values():
        repair = example.get("repair")
        if repair and repair["tool"] in DATA_TOOLS:
            assert repair["arguments"]["portal"] == "example-city"
            if "dataset_id" in repair["arguments"]:
                assert repair["arguments"]["dataset_id"] == "abcd-1234"
    from opendata_atlas.core.errors import AtlasError
    from opendata_atlas.portals.resolve import resolve_portal

    with pytest.raises(AtlasError):
        resolve_portal("example-city")  # illustrative: it never resolves
    codes = topics(None)["errors"].documents[1].body
    assert "illustrative" in codes.split("```", 1)[0]
    from opendata_atlas.mcp import tools

    for fn in (
        tools.atlas_search_datasets,
        tools.atlas_describe_dataset,
        tools.atlas_query_dataset,
    ):
        doc = fn.__doc__ or ""
        assert '"portal": "example-city"' in doc
        assert "illustrative" in doc.lower()


def test_browse_suggestion_names_the_portal():
    from opendata_atlas.core import catalog

    alternative = catalog._suggest(SEATTLE, "City of Seattle", "x", "tabular", None).alternative
    assert alternative is not None
    assert alternative.endswith("say City of Seattle may not publish this data.")


# --- weekdays (ruling 92) ---------------------------------------------------------


def test_weekday_rule_is_a_capability_rule_naming_date_extract_dow():
    rules = [line for line in _section(CAPABILITIES, "Rules").splitlines() if "weekday" in line]
    assert len(rules) == 1, rules
    assert "`date_extract_dow`" in rules[0]
    assert "`source.now_weekday`" in rules[0]
    assert rules[0].startswith("- Name a weekday only from the data")


def test_weekday_rule_gives_date_extract_dow_numbering():
    """M5 standards F1: the rule sends agents to a number, so it gives the numbering.

    `date_extract_dow` returns "0" for Sunday (probed live 2026-10-19,
    docs/evidence/standards-m5-2026-10-19/dow-probe.json); Python's `weekday()` returns
    0 for Monday, so an agent mapping the number itself can be a day off.
    """
    rule = next(line for line in _section(CAPABILITIES, "Rules").splitlines() if "weekday" in line)
    assert "`date_extract_dow` on the date column, 0 = Sunday" in rule


def test_weekday_semantics_states_only_the_fact():
    semantics = _section(CAPABILITIES, "Semantics")
    assert (
        "`source.now_weekday` is today's weekday in the portal's zone, "
        "present exactly when `now_local` is." in semantics
    )
    assert "never" not in next(line for line in semantics.splitlines() if "now_weekday" in line)


def test_dates_topic_points_to_now_weekday_and_date_extract_dow():
    dates = next(d for d in topics(None)["soql"].documents if d.item_id == "dates").body
    line = next(line for line in dates.splitlines() if "`source.now_weekday`" in line)
    assert "date_extract_dow" in line


# --- resource size (milestone 5 Task 3) -------------------------------------------

STATIC_RESOURCES = [
    "opendata-atlas://capabilities",
    "opendata-atlas://contributing",
    "opendata-atlas://reference",
    "opendata-atlas://portals",
    "opendata-atlas://soql",
    "opendata-atlas://errors",
]


async def _sizes_and_bodies(client) -> dict[str, tuple[int | None, int]]:
    listed = {str(r.uri): r.size for r in await client.list_resources()}
    return {
        uri: (listed.get(uri), len((await client.read_resource(uri))[0].text.encode("utf-8")))
        for uri in STATIC_RESOURCES
    }


async def test_static_resources_declare_their_byte_size(client):
    sizes = await _sizes_and_bodies(client)
    assert set(sizes) == set(STATIC_RESOURCES)
    for uri, (declared, actual) in sizes.items():
        assert declared == actual, uri


async def test_resource_size_matches_read_under_allowlist(client, monkeypatch):
    uri = "opendata-atlas://portals"
    full = (await _sizes_and_bodies(client))[uri]
    monkeypatch.setenv(ALLOWLIST_ENV, "seattle")
    from opendata_atlas.portals import registry, resolve, validation

    registry._default.cache_clear()
    validation._default.cache_clear()
    resolve._context.cache_clear()
    resolve._pack_dirs.cache_clear()
    resolve._parse_allowlist.cache_clear()
    declared, actual = (await _sizes_and_bodies(client))[uri]
    assert declared == actual
    assert actual < full[1], "the allowlist changes the body, so a stale size would show"


async def test_size_counts_utf8_bytes(client, monkeypatch):
    from opendata_atlas.mcp import resources

    monkeypatch.setattr(resources, "CAPABILITIES", "é")
    listed = {str(r.uri): r.size for r in await client.list_resources()}
    assert listed["opendata-atlas://capabilities"] == 2
