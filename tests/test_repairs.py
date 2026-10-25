"""Milestone 1 exit test (e): every documented or emitted repair is a literal, valid call."""

from __future__ import annotations

import jsonschema
import pytest

from opendata_atlas.core import catalog, describe, query
from opendata_atlas.core.errors import AtlasError, ErrorCode, ErrorEnvelope, map_upstream_error
from opendata_atlas.core.reference import ERROR_CODES_BY_TOOL, ERROR_EXAMPLES
from tests.conftest import SEATTLE_CONTEXT, wire
from tests.repair_rules import DATA_TOOLS, assert_repair_callable, assert_repair_scope

SEATTLE_ID = SEATTLE_CONTEXT.id
#: Worked examples use illustrative values; they validate against the schemas but never resolve.
EXAMPLE_PORTAL = "example-city"


def test_every_documented_code_has_a_worked_example():
    documented = {code for codes in ERROR_CODES_BY_TOOL.values() for code in codes}
    assert documented <= ERROR_EXAMPLES.keys()
    assert set(ErrorCode) == documented, "every code is reachable from some tool"


@pytest.mark.parametrize("code", list(ERROR_EXAMPLES))
def test_worked_example_is_a_valid_envelope_with_callable_repair(code, input_schemas):
    example = ERROR_EXAMPLES[code]
    ErrorEnvelope.model_validate(example)
    assert example["code"] == code.value
    assert "retry_after_ms" in example
    if example["temporary"] is False:
        assert example["retry_after_ms"] is None
    if "repair" in example:
        assert_repair_callable(example["repair"], input_schemas)


def test_exemption_does_not_weaken_published_tools(input_schemas):
    published = next(iter(input_schemas))
    with pytest.raises(jsonschema.ValidationError):
        assert_repair_callable(
            {"tool": published, "arguments": {"no_such_argument_9": 1}}, input_schemas
        )
    with pytest.raises(AssertionError):
        assert_repair_callable({"tool": "atlas_not_a_tool", "arguments": {}}, input_schemas)


UPSTREAM_CASES = [
    (400, {"code": "query.soql.no-such-column"}),
    (400, {"code": "query.soql.type-mismatch"}),
    (403, {"message": "Invalid app_token specified"}),
    (404, {}),
]


@pytest.mark.parametrize(("status", "body"), UPSTREAM_CASES)
def test_upstream_mapping_repairs_are_callable(status, body, input_schemas):
    repair = map_upstream_error(
        status,
        body,
        dataset_id="kzjm-xkqj",
        token_configured=True,
        portal_id=SEATTLE_ID,
        portal_name=SEATTLE_CONTEXT.identity.name,
    ).envelope.repair
    assert repair is not None
    assert_repair_callable(repair.model_dump(exclude_none=True), input_schemas)
    assert_repair_scope(repair.model_dump(exclude_none=True), SEATTLE_ID)


def _reference_cursor(topic: str, portal_id: str | None) -> str:
    """A server-minted reference cursor at offset 1 (same process key as the server)."""
    from opendata_atlas.core import cursor as cursors
    from opendata_atlas.core import reference_service

    context = SEATTLE_CONTEXT if topic == "guides" else None
    entries = reference_service.read(context, topic, None, paged=False).entries or []
    state = {"t": topic, "p": portal_id, "o": 1, "f": reference_service._fingerprint(entries)}
    return cursors.encode("reference", state, portal_id="*")


GUIDES_CURSOR = _reference_cursor("guides", SEATTLE_ID)
SOQL_CURSOR = _reference_cursor("soql", None)

EMITTED_CASES = [
    ("atlas_get_reference", {"topic": "soql", "item_id": "joins"}),
    ("atlas_get_reference", {"item_id": "dates"}),
    ("atlas_get_reference", {"topic": "guides", "portal": "seattle", "item_id": "nope"}),
    (
        "atlas_query_dataset",
        {"portal": "seattle", "dataset_id": "kzjm-xkqj", "cursor": "not-a-cursor"},
    ),
    (
        "atlas_query_dataset",
        {"portal": "seattle", "dataset_id": "kzjm-xkqj", "cursor": "eyJ4IjoxfQ.AAAA"},
    ),
    ("atlas_search_datasets", {"portal": "seattle", "cursor": "not-a-cursor"}),
    ("atlas_search_datasets", {"portal": "seattle", "cursor": "eyJ4IjoxfQ.AAAA"}),
    ("atlas_search_datasets", {"portal": "nowhere-portal-zz"}),
    ("atlas_search_datasets", {"portal": "Chicago, IL"}),
    ("atlas_describe_dataset", {"portal": "Chicago, IL", "dataset_id": "kzjm-xkqj"}),
    ("atlas_query_dataset", {"portal": "Chicago, IL", "dataset_id": "kzjm-xkqj"}),
    ("atlas_find_portals", {"cursor": "not-a-cursor"}),
    ("atlas_find_portals", {"cursor": "eyJ4IjoxfQ.AAAA"}),
    ("atlas_get_reference", {"topic": "guides", "portal": "seattle", "cursor": "not-a-cursor"}),
    ("atlas_get_reference", {"topic": "guides", "portal": "seattle", "cursor": "eyJ4IjoxfQ.AAAA"}),
    ("atlas_get_reference", {"topic": "soql", "cursor": "not-a-cursor"}),
    (
        "atlas_get_reference",
        {"topic": "guides", "portal": "seattle", "item_id": "nope", "cursor": "not-a-cursor"},
    ),
    # Ruling 50: a server-minted cursor's repair continues its own walk.
    ("atlas_get_reference", {"cursor": GUIDES_CURSOR}),
    ("atlas_get_reference", {"topic": "soql", "cursor": GUIDES_CURSOR}),
    ("atlas_get_reference", {"topic": "guides", "portal": "seattle", "cursor": SOQL_CURSOR}),
    ("atlas_get_reference", {"topic": "soql", "item_id": "dates", "cursor": SOQL_CURSOR}),
    # Argument combinations (#19): each repair reads the reference section with the rule.
    (
        "atlas_query_dataset",
        {"portal": "seattle", "dataset_id": "kzjm-xkqj", "cursor": "x", "where": "a = 1"},
    ),
    ("atlas_query_dataset", {"portal": "seattle", "dataset_id": "kzjm-xkqj", "soql": "SELECT *"}),
    ("atlas_query_dataset", {"portal": "seattle", "dataset_id": "kzjm-xkqj", "mode": "soql"}),
    (
        "atlas_query_dataset",
        {
            "portal": "seattle",
            "dataset_id": "kzjm-xkqj",
            "mode": "soql",
            "soql": "SELECT *",
            "where": "a = 1",
        },
    ),
    (
        "atlas_query_dataset",
        {
            "portal": "seattle",
            "dataset_id": "kzjm-xkqj",
            "where": " OR ".join(["a = 1"] * 300),
            "having": " OR ".join(["n = 1"] * 300),
        },
    ),
    (
        "atlas_describe_dataset",
        {"portal": "seattle", "dataset_id": "kzjm-xkqj", "column_cursor": "x", "sample_rows": 1},
    ),
    ("atlas_search_datasets", {"portal": "seattle", "cursor": "x", "query": "fire"}),
    ("atlas_find_portals", {"cursor": "x", "query": "Seattle"}),
    # A tool name this server does not have (milestone 6 standards review).
    ("atlas_get_dataset_metadata", {"dataset_id": "kzjm-xkqj"}),
]


def test_reference_portal_mismatch_repair_is_callable(input_schemas):
    """Its repair names the cursor's portal, not the call's, so it is checked here, not in
    EMITTED_CASES (whose scope rule wants the call's portal)."""
    from dataclasses import replace

    from opendata_atlas.core import reference_service

    other = replace(
        SEATTLE_CONTEXT,
        identity=SEATTLE_CONTEXT.identity.model_copy(update={"id": "data.example.gov"}),
    )
    with pytest.raises(AtlasError) as caught:
        reference_service.read(other, "guides", None, cursor=GUIDES_CURSOR)
    envelope = caught.value.envelope
    assert envelope.code == ErrorCode.INVALID_CURSOR
    assert envelope.repair is not None
    repair = envelope.repair.model_dump(exclude_none=True)
    assert_repair_callable(repair, input_schemas)
    assert repair["arguments"] == {"topic": "guides", "portal": SEATTLE_ID, "cursor": GUIDES_CURSOR}
    assert reference_service.read(SEATTLE_CONTEXT, "guides", None, cursor=GUIDES_CURSOR).entries


#: A repair that returns rows reads as an answer; one that drops the failed call's
#: arguments then answers a different question (#16).
ROW_TOOLS = {"atlas_query_dataset", "atlas_search_datasets"}


@pytest.mark.parametrize(
    "code", [ErrorCode.QUERY_TIMEOUT, ErrorCode.CURSOR_EXPIRED, ErrorCode.INVALID_CURSOR]
)
def test_documented_repairs_for_lost_queries_return_no_rows(code):
    assert ERROR_EXAMPLES[code]["repair"]["tool"] not in ROW_TOOLS


@pytest.mark.parametrize(("tool", "args"), EMITTED_CASES)
async def test_emitted_repairs_are_callable(client, input_schemas, tool, args):
    envelope = wire(await client.call_tool_mcp(tool, args))["structuredContent"]
    assert "repair" in envelope
    assert_repair_callable(envelope["repair"], input_schemas)
    assert_repair_scope(envelope["repair"], SEATTLE_ID)
    assert envelope["repair"]["tool"] not in ROW_TOOLS
    followed = wire(
        await client.call_tool_mcp(envelope["repair"]["tool"], envelope["repair"]["arguments"])
    )
    assert followed["structuredContent"].get("code") != "invalid_argument", (
        "following a repair must not be a usage error"
    )


#: Success results whose `hints[].repair` must be callable: (fake view pages, row fields, call).
HINT_CASES = [
    (
        [[]],
        ["area_name"],
        {
            "portal": "seattle",
            "dataset_id": "aaaa-bbbb",
            "select": ["area_name"],
            "where": "date_rptd >= '2026-09-01' AND area_name = 'O''Brien_%'",
        },
    ),
]


@pytest.mark.parametrize(("pages", "fields", "args"), HINT_CASES)
async def test_emitted_hint_repairs_are_callable(client, input_schemas, pages, fields, args):
    """A hint is not an error, so it is not in EMITTED_CASES (ruling 47); it is an inspection
    that keeps every other filter, so a row tool is allowed (unlike lost-query repairs)."""
    from tests.test_query import install_hint_view

    install_hint_view(pages, fields)
    content = wire(await client.call_tool_mcp("atlas_query_dataset", args))["structuredContent"]
    assert content["hints"], content
    for hint in content["hints"]:
        assert_repair_callable(hint, input_schemas)
        assert_repair_scope(hint, SEATTLE_ID)
        followed = wire(await client.call_tool_mcp(hint["tool"], hint["arguments"]))
        assert followed["isError"] is False, followed["structuredContent"]


def _engine_repairs() -> list[dict]:
    """Every repair and suggestion the engine builds outside the HTTP mapping."""
    out = []
    for category in ("Public Safety", None):
        for scope in ("tabular", "all"):
            out.append(
                catalog._suggest(SEATTLE_ID, SEATTLE_CONTEXT.identity.name, "fire", scope, category)
            )
    out.append(query._narrow(SEATTLE_ID, "kzjm-xkqj"))
    views = [
        {
            "id": "aaaa-bbbb",
            "viewType": "tabular",
            "assetType": "map",
            "modifyingViewUid": "cccc-dddd",
        },
        {"id": "aaaa-bbbb", "viewType": "href", "assetType": "href"},
    ]
    for view in views:
        with pytest.raises(AtlasError) as caught:
            describe.require_queryable(view, "aaaa-bbbb", SEATTLE_ID)
        out.append(caught.value.envelope.repair)
    with pytest.raises(AtlasError) as caught:
        query._within_circle(
            SEATTLE_ID,
            "kzjm-xkqj",
            {"column": "x", "latitude": 0, "longitude": 0, "radius_m": 1},
            {"x": "text"},
            [],
        )
    out.append(caught.value.envelope.repair)
    return [r.model_dump(exclude_none=True) for r in out if r is not None]


def test_every_emitted_repair_carries_portal(input_schemas):
    """The repair-scope rule over documented, mapped and engine-built repairs.

    Wire-emitted repairs are checked by the `client` fixture on every call in the suite."""
    documented = [e["repair"] for e in ERROR_EXAMPLES.values() if "repair" in e]
    for repair in documented:
        assert_repair_scope(repair, EXAMPLE_PORTAL)
    mapped = [
        map_upstream_error(
            status,
            body,
            dataset_id="kzjm-xkqj",
            token_configured=True,
            portal_id=SEATTLE_ID,
            portal_name=SEATTLE_CONTEXT.identity.name,
        ).envelope.repair
        for status, body in UPSTREAM_CASES
    ]
    engine = _engine_repairs()
    emitted = [*(r.model_dump(exclude_none=True) for r in mapped if r), *engine]
    data_tool_repairs = [r for r in [*documented, *emitted] if r["tool"] in DATA_TOOLS]
    assert len(data_tool_repairs) >= 12, "the sample reaches the migrated sites"
    for repair in emitted:
        assert_repair_scope(repair, SEATTLE_ID)
    for repair in [*documented, *emitted]:
        assert_repair_callable(repair, input_schemas)


def test_repair_scope_rule_can_fail():
    with pytest.raises(AssertionError):
        assert_repair_scope({"tool": "atlas_describe_dataset", "arguments": {}}, SEATTLE_ID)
    with pytest.raises(AssertionError):
        assert_repair_scope(
            {"tool": "atlas_search_datasets", "arguments": {"portal": "seattle"}}, SEATTLE_ID
        )
    with pytest.raises(AssertionError):
        assert_repair_scope(
            {"tool": "atlas_get_reference", "arguments": {"topic": "soql", "portal": SEATTLE_ID}},
            SEATTLE_ID,
        )


async def test_client_guard_rejects_a_wire_repair_that_fails_its_schema(client, monkeypatch):
    """Final review M-5: every repair a tool call emits is schema-checked, not only scoped."""
    from opendata_atlas.core.errors import Repair
    from opendata_atlas.mcp import tools

    def bad(portal: str):
        raise AtlasError(
            ErrorCode.PORTAL_NOT_FOUND,
            "No such portal.",
            repair=Repair(
                next_step="find_portal", tool="atlas_find_portals", arguments={"bogus": 1}
            ),
        )

    monkeypatch.setattr(tools, "resolve_portal", bad)
    with pytest.raises(jsonschema.ValidationError):
        await client.call_tool_mcp("atlas_search_datasets", {"portal": "seattle", "query": "x"})
