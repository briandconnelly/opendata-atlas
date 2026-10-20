"""Milestone 3 Task 9: reference entry lists page within the result budget.

Fixtures: a portal with 100 guides, and a registry whose portals index lists 300 portals.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import TYPE_CHECKING, Any

import pytest

from opendata_atlas.constants import RESULT_BYTE_BUDGET
from opendata_atlas.core import cursor as cursors
from opendata_atlas.core import reference_service
from opendata_atlas.core.budget import RESULT_LIMIT, payload_size, wire_size
from opendata_atlas.core.errors import AtlasError, ErrorCode
from opendata_atlas.core.guides import Example, Guide
from opendata_atlas.mcp import resources
from opendata_atlas.portals.registry import load_registry
from tests.conftest import SEATTLE_CONTEXT, framed_size, wire

if TYPE_CHECKING:
    from pathlib import Path

    from opendata_atlas.core.models import ReferenceResult
    from opendata_atlas.portals.model import PortalContext

GUIDES = 100


def _guide(i: int) -> Guide:
    return Guide(
        guide_id=f"synthetic-guide-{i:03d}",
        dataset_id=f"gd{i:02d}-abcd",
        title=f"Synthetic guide {i:03d} ".ljust(60, "t"),
        description=f"Guide {i:03d} ".ljust(200, "d"),
        body="Facts. ".ljust(2000, "b"),
        examples=(Example("How many?", {"select": ["count(*) AS n"]}),),
    )


@pytest.fixture
def hundred() -> PortalContext:
    """Seattle's identity and pack with 100 synthetic guides."""
    return replace(SEATTLE_CONTEXT, guides=tuple(_guide(i) for i in range(GUIDES)))


def _walk(portal: PortalContext | None, topic: str) -> list[ReferenceResult]:
    pages = [reference_service.read(portal, topic, None)]
    while pages[-1].has_more:
        assert pages[-1].next_cursor
        pages.append(reference_service.read(portal, topic, None, cursor=pages[-1].next_cursor))
    assert pages[-1].next_cursor is None
    return pages


def _ids(pages: list[ReferenceResult]) -> list[str]:
    return [e.item_id for page in pages for e in page.entries or []]


def test_hundred_guides_index_pages_within_budget(hundred: PortalContext):
    unpaged = reference_service.read(hundred, "guides", None, paged=False)
    assert payload_size(unpaged) > RESULT_LIMIT, "the fixture needs paging (known positive)"
    pages = _walk(hundred, "guides")
    assert pages[0].has_more is True
    assert len(pages) > 1
    for page in pages:
        # Ruling 72: entry pages are measured by wire_size, what the client receives.
        assert wire_size(page) <= RESULT_LIMIT
        assert page.entries
    ids = _ids(pages)
    assert ids == [g.guide_id for g in hundred.guides]
    assert len(set(ids)) == GUIDES


def test_hundred_guides_portal_summary_fits(
    hundred: PortalContext, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(reference_service, "resolve_portal", lambda value, field: hundred)
    result = reference_service.read(None, "portals", hundred.id)
    assert result.body is not None
    for guide in hundred.guides:
        assert f"`{guide.guide_id}`" in result.body
    assert payload_size(result) <= RESULT_LIMIT


async def test_hundred_guides_pages_fit_the_modern_wire(
    client, hundred: PortalContext, monkeypatch: pytest.MonkeyPatch
):
    """Ruling 72: every page, as received with its JSON-RPC frame, is within the 24 KiB limit."""
    from opendata_atlas.mcp import tools

    monkeypatch.setattr(tools, "resolve_portal", lambda value: hundred)
    args: dict[str, Any] = {"topic": "guides", "portal": "seattle"}
    seen: list[str] = []
    while True:
        result = wire(await client.call_tool_mcp("atlas_get_reference", args))
        assert result["isError"] is False, result["structuredContent"]
        assert framed_size(result) <= RESULT_BYTE_BUDGET
        out = result["structuredContent"]
        seen += [e["item_id"] for e in out["entries"]]
        if not out["has_more"]:
            break
        args = {"topic": "guides", "portal": "seattle", "cursor": out["next_cursor"]}
    assert seen == [g.guide_id for g in hundred.guides]


def test_seattle_guides_index_is_not_paged():
    result = reference_service.read(SEATTLE_CONTEXT, "guides", None)
    assert result.has_more is False
    assert result.next_cursor is None
    assert [e.item_id for e in result.entries or []] == [g.guide_id for g in SEATTLE_CONTEXT.guides]
    assert len(SEATTLE_CONTEXT.guides) == 7


def test_bodies_carry_no_paging_fields():
    result = reference_service.read(None, "capabilities", None)
    assert result.body
    assert result.has_more is None
    assert result.next_cursor is None


def _code(call: Any) -> tuple[ErrorCode, dict[str, Any]]:
    with pytest.raises(AtlasError) as caught:
        call()
    envelope = caught.value.envelope
    assert envelope.repair is not None
    return envelope.code, envelope.repair.model_dump(exclude_none=True)


def _mint(topic: str, portal_id: str | None, entries: Any, offset: int = 1) -> str:
    """A server cursor for `topic`, as `_page` mints it (same process key)."""
    state = {"t": topic, "p": portal_id, "o": offset, "f": reference_service._fingerprint(entries)}
    return cursors.encode("reference", state, portal_id="*")


def test_reference_cursor_rules(hundred: PortalContext):
    first = reference_service.read(hundred, "guides", None)
    assert first.next_cursor
    token = first.next_cursor
    continuation = {
        "next_step": "continue_paging",
        "tool": "atlas_get_reference",
        "arguments": {"topic": "guides", "portal": hundred.id, "cursor": token},
    }

    # item_id with cursor is invalid_argument; the repair is the call without item_id.
    with pytest.raises(AtlasError) as caught:
        reference_service.read(hundred, "guides", "x", cursor=token)
    envelope = caught.value.envelope
    assert envelope.code == ErrorCode.INVALID_ARGUMENT
    assert envelope.details is not None
    assert envelope.details.field == "item_id"
    assert envelope.repair is not None
    assert envelope.repair.arguments == continuation["arguments"]
    assert envelope.repair.alternative == "To read the item, omit cursor and keep item_id."

    # Another topic, or none (index): invalid_cursor naming the cursor's topic, repaired by
    # continuing the cursor's own walk (ruling 50).
    for topic in ("soql", "index"):
        envelope = _envelope(lambda t=topic: reference_service.read(None, t, None, cursor=token))
        assert envelope.code == ErrorCode.INVALID_CURSOR
        assert envelope.message == "The cursor belongs to topic `guides`."
        assert envelope.details.field == "topic"
        assert envelope.repair.model_dump(exclude_none=True) == continuation

    # A topic's cursor sent to guides: the topic is named, not the portal.
    soql = reference_service.read(None, "soql", None, paged=False).entries or []
    soql_token = _mint("soql", None, soql)
    envelope = _envelope(lambda: reference_service.read(hundred, "guides", None, cursor=soql_token))
    assert envelope.message == "The cursor belongs to topic `soql`."
    assert envelope.details.field == "topic"
    assert envelope.repair.arguments == {"topic": "soql", "cursor": soql_token}

    # Another portal on the right topic: invalid_cursor naming the cursor's portal.
    other = replace(
        hundred, identity=hundred.identity.model_copy(update={"id": "data.example.gov"})
    )
    envelope = _envelope(lambda: reference_service.read(other, "guides", None, cursor=token))
    assert envelope.code == ErrorCode.INVALID_CURSOR
    assert envelope.message == f"The cursor belongs to portal `{hundred.id}`."
    assert envelope.details.field == "portal"
    assert envelope.repair.model_dump(exclude_none=True) == continuation

    # A changed entry list: cursor_expired, restarting page one.
    fewer = replace(hundred, guides=hundred.guides[:-1])
    envelope = _envelope(lambda: reference_service.read(fewer, "guides", None, cursor=token))
    assert envelope.code == ErrorCode.CURSOR_EXPIRED
    assert envelope.repair.arguments == {"topic": "guides", "portal": hundred.id}

    # A cursor of the right kind with a wrong-shaped state: invalid_cursor, not a crash.
    for state in ({"t": "guides"}, {"t": "guides", "p": None, "o": 1, "f": "x"}):
        forged = cursors.encode("reference", state, portal_id="*")
        envelope = _envelope(
            lambda f=forged: reference_service.read(hundred, "guides", None, cursor=f)
        )
        assert envelope.code == ErrorCode.INVALID_CURSOR
        assert envelope.details.field == "cursor"

    # Following each mismatch repair returns the next page (known positive).
    followed = reference_service.read(hundred, "guides", None, cursor=token)
    assert followed.entries
    assert followed.entries[0].item_id == hundred.guides[len(first.entries or [])].guide_id
    soql_page = reference_service.read(None, "soql", None, cursor=soql_token)
    assert [e.item_id for e in soql_page.entries or []] == [e.item_id for e in soql[1:]]


def _envelope(call: Any) -> Any:
    with pytest.raises(AtlasError) as caught:
        call()
    envelope = caught.value.envelope
    assert envelope.details is not None
    assert envelope.repair is not None
    return envelope


async def test_reference_cursor_mismatches_over_the_wire(
    client, input_schemas, hundred: PortalContext, monkeypatch: pytest.MonkeyPatch
):
    """The reviewer's three cases (task 9 review I1), each repaired by its continuation."""
    import jsonschema

    from opendata_atlas.mcp import tools

    monkeypatch.setattr(tools, "resolve_portal", lambda value: hundred)
    first = wire(
        await client.call_tool_mcp("atlas_get_reference", {"topic": "guides", "portal": "seattle"})
    )["structuredContent"]
    guides_token = first["next_cursor"]
    soql_token = _mint(
        "soql", None, reference_service.read(None, "soql", None, paged=False).entries
    )
    cases = [
        ({"cursor": guides_token}, "topic", "guides"),
        ({"topic": "soql", "cursor": guides_token}, "topic", "guides"),
        ({"topic": "guides", "portal": "seattle", "cursor": soql_token}, "topic", "soql"),
    ]
    for args, field, owner in cases:
        content = wire(await client.call_tool_mcp("atlas_get_reference", args))
        envelope = content["structuredContent"]
        assert content["isError"] is True
        assert envelope["code"] == "invalid_cursor"
        assert envelope["details"]["field"] == field
        assert envelope["message"] == f"The cursor belongs to topic `{owner}`."
        repair = envelope["repair"]
        jsonschema.validate(repair["arguments"], input_schemas[repair["tool"]])
        followed = wire(await client.call_tool_mcp(repair["tool"], repair["arguments"]))
        assert followed["isError"] is False, followed["structuredContent"]
        assert followed["structuredContent"]["entries"]

    content = wire(
        await client.call_tool_mcp(
            "atlas_get_reference", {"topic": "soql", "item_id": "dates", "cursor": soql_token}
        )
    )
    assert content["structuredContent"]["code"] == "invalid_argument"
    assert content["structuredContent"]["repair"]["arguments"] == {
        "topic": "soql",
        "cursor": soql_token,
    }


async def test_guides_resource_is_unpaged(
    client, hundred: PortalContext, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(resources, "resolve_portal", lambda value, field: hundred)
    contents = await client.read_resource(f"opendata-atlas://portals/{hundred.id}/guides")
    index = json.loads(contents[0].text)
    assert [e["item_id"] for e in index["entries"]] == [g.guide_id for g in hundred.guides]
    assert index["has_more"] is False
    assert "next_cursor" not in index


def _profiled(i: int) -> dict[str, Any]:
    id_ = f"data.portal{i:04d}.example.gov"
    return {
        "id": id_,
        "aliases": [],
        "public_host": id_,
        "catalog_query": {"domains": id_},
        "catalog_region": "us",
        "name": f"Profiled portal {i:04d} ".ljust(40, "n"),
        "platform": "socrata",
        "status": "active",
        "tier": "profiled",
        "jurisdiction": {"level": "city", "country": "US", "region": "WA"},
    }


def test_portal_index_with_many_profiled_portals_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    entries = [
        {"identity": _profiled(i), "dataset_count": 7, "catalog_size": 9} for i in range(300)
    ]
    (tmp_path / "registry.json").write_text(json.dumps({"version": "v1", "entries": entries}))
    registry = load_registry(tmp_path / "registry.json", packs_dir=tmp_path)
    monkeypatch.setattr(reference_service, "load_registry", lambda: registry)

    pages = _walk(None, "portals")
    assert pages[0].has_more is True
    for page in pages:
        assert wire_size(page) <= RESULT_LIMIT
    ids = _ids(pages)
    assert ids == [e.identity.id for e in registry.ordered]
    assert len(set(ids)) == 300


def test_item_id_with_cursor_repairs_to_the_cursors_own_walk(hundred: PortalContext):
    """Ruling 51 (N2): the repair comes from the decoded cursor, so recovery is one hop."""
    token = reference_service.read(hundred, "guides", None).next_cursor
    assert token
    envelope = _envelope(lambda: reference_service.read(None, "soql", "dates", cursor=token))
    assert envelope.code == ErrorCode.INVALID_ARGUMENT
    assert envelope.details.field == "item_id"
    assert envelope.repair.arguments == {"topic": "guides", "portal": hundred.id, "cursor": token}
    assert reference_service.read(hundred, "guides", None, cursor=token).entries


def test_item_id_with_undecodable_cursor_is_malformed():
    """A cursor that will not decode gets the malformed-cursor error, not a doomed repair."""
    envelope = _envelope(
        lambda: reference_service.read(None, "soql", "dates", cursor="not-a-cursor")
    )
    assert envelope.code == ErrorCode.INVALID_CURSOR
    assert envelope.details.field == "cursor"
    assert envelope.repair.arguments == {"topic": "soql"}


def test_cursor_repair_guard_binds_the_cursors_own_state(hundred: PortalContext):
    """Ruling 51 (N1): the conftest exemption accepts only the cursor's own continuation."""
    from tests.conftest import _check_repair_scope

    token = reference_service.read(hundred, "guides", None).next_cursor
    assert token
    soql_token = _mint(
        "soql", None, reference_service.read(None, "soql", None, paged=False).entries or []
    )
    call = {"topic": "soql", "cursor": token}

    def content(arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "repair": {
                "next_step": "continue_paging",
                "tool": "atlas_get_reference",
                "arguments": arguments,
            }
        }

    # Known negative: the cursor's own continuation passes.
    _check_repair_scope(
        "atlas_get_reference",
        call,
        content({"topic": "guides", "portal": hundred.id, "cursor": token}),
    )
    bad = [
        # Another canonical portal.
        {"topic": "guides", "portal": "data.cityofchicago.org", "cursor": token},
        # A different cursor.
        {"topic": "soql", "cursor": soql_token},
        # The cursor's portal but not its topic.
        {"topic": "soql", "cursor": token},
    ]
    for arguments in bad:
        with pytest.raises(AssertionError):
            _check_repair_scope("atlas_get_reference", call, content(arguments))
