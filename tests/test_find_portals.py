"""Milestone 2 Task 6: `atlas_find_portals` matching, ordering, paging and the tool surface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from opendata_atlas.core import cursor as cursors
from opendata_atlas.core.errors import AtlasError, ErrorCode
from opendata_atlas.core.portals import find_portals
from opendata_atlas.portals.registry import Registry, load_registry
from tests.conftest import seattle_only_packs, wire

CITY = {"level": "city", "country": "US", "region": "IL"}
COUNTY = {"level": "county", "country": "US", "region": "IL"}


def _identity(id_: str, tier: str = "generic", **over: Any) -> dict[str, Any]:
    return {
        "id": id_,
        "aliases": [],
        "public_host": id_,
        "catalog_query": {"domains": id_},
        "catalog_region": "us",
        "name": id_,
        "platform": "socrata",
        "status": "active",
        "tier": tier,
    } | over


def _registry(tmp_path: Path, identities: list[dict[str, Any]], *, version: str = "v1") -> Registry:
    entries = [{"identity": i, "dataset_count": 7, "catalog_size": 9} for i in identities]
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"version": version, "entries": entries}))
    packs = tmp_path / "packs"
    packs.mkdir(exist_ok=True)
    return load_registry(path, packs)


def _ids(result) -> list[str]:
    return [c.id for c in result.candidates]


def _find(registry: Registry, **kw: Any):
    args: dict[str, Any] = dict(
        query=None, level=None, country=None, tier=None, page_size=None, cursor=None
    )
    return find_portals(registry, **(args | kw))


@pytest.fixture
def places(tmp_path: Path) -> Registry:
    return _registry(
        tmp_path,
        [
            _identity(
                "data.cityofspringfield.org",
                name="City of Springfield",
                place_names=["Springfield", "Springfield, IL"],
                jurisdiction=CITY,
            ),
            _identity(
                "data.springfieldcounty.gov",
                "profiled",
                name="Springfield County",
                place_names=["Springfield", "Springfield County, IL"],
                jurisdiction=COUNTY,
            ),
            _identity(
                "data.kingcounty.gov",
                "profiled",
                aliases=["king"],
                name="King County",
                place_names=["King County, WA"],
                jurisdiction={"level": "county", "country": "US", "region": "WA"},
            ),
            _identity("data.alphacounty.gov", name="Alpha County", jurisdiction=COUNTY),
            _identity("data.nowhere.example", name="No Place", jurisdiction=None),
            _identity("zzz.example.gov", name="Zed"),
        ],
    )


def test_alias_match_ranks_first(tmp_path: Path):
    reg = _registry(
        tmp_path,
        [
            _identity("a.chicagoland.example", "profiled", name="Chicago Metro Planning"),
            _identity(
                "data.cityofchicago.org",
                aliases=["chicago"],
                name="City of Chicago",
                place_names=["Chicago"],
            ),
        ],
    )
    result = _find(reg, query="CHICAGO")
    assert result.candidates[0].id == "data.cityofchicago.org"
    assert result.candidates[0].match == "alias"


def test_matching_is_whole_token_and_case_insensitive(places: Registry):
    result = _find(places, query="king county wa")
    assert _ids(result) == ["data.kingcounty.gov"]
    assert result.candidates[0].match == "place_name"
    assert _find(places, query="King County, WA").candidates[0].id == "data.kingcounty.gov"
    assert _find(places, query="KING").candidates[0].match == "alias"


def test_name_match_needs_whole_tokens(tmp_path: Path):
    reg = _registry(
        tmp_path, [_identity("x.example.gov", name="Springfield", place_names=["Springfield"])]
    )
    assert _find(reg, query="spring").candidates == []  # a fragment of a token, not a token
    assert _find(reg, query="springfield").candidates[0].match == "name"


def test_match_strength_then_tier_then_id(places: Registry):
    # Springfield matches both by name; the profiled portal outranks the generic one.
    result = _find(places, query="springfield")
    kinds = [(c.id, c.match) for c in result.candidates]
    assert kinds == [
        ("data.springfieldcounty.gov", "name"),
        ("data.cityofspringfield.org", "name"),
    ]
    host = _find(places, query="nowhere.example")
    assert [(c.id, c.match) for c in host.candidates] == [("data.nowhere.example", "host")]


def test_no_query_lists_every_tier_curated_first(tmp_path: Path):
    """Ruling 32: the no-argument listing pages through curated, profiled, then generic."""
    _registry(tmp_path, [_identity("z.example.gov"), _identity("m.example.gov", "profiled")])
    reg = load_registry(tmp_path / "registry.json", seattle_only_packs(tmp_path))
    result = _find(reg)
    assert _ids(result) == ["data.seattle.gov", "m.example.gov", "z.example.gov"]
    assert all(c.match is None for c in result.candidates)
    assert _ids(_find(reg, tier="generic")) == ["z.example.gov"]


def test_no_match_is_empty_success(places: Registry):
    result = _find(places, query="atlantis")
    assert result.candidates == []
    assert result.has_more is False
    assert result.next_cursor is None
    assert result.registry_version == "v1"


async def test_no_match_is_empty_success_over_the_wire(client):
    result = wire(await client.call_tool_mcp("atlas_find_portals", {"query": "atlantis"}))
    assert not result.get("isError")
    assert result["structuredContent"]["candidates"] == []
    assert result["structuredContent"]["has_more"] is False


def test_find_portals_never_picks_one(places: Registry):
    result = _find(places, query="Springfield")
    assert set(_ids(result)) == {"data.cityofspringfield.org", "data.springfieldcounty.gov"}
    assert {c.jurisdiction.level for c in result.candidates if c.jurisdiction} == {
        "city",
        "county",
    }


def test_country_and_level_filters_exclude_null_jurisdiction(places: Registry):
    everything = _find(places, country="us")
    assert "data.nowhere.example" not in _ids(everything)
    assert "zzz.example.gov" not in _ids(everything)
    # A filter alone searches every tier, profiled before generic, then by id.
    assert _ids(_find(places, level="county")) == [
        "data.kingcounty.gov",
        "data.springfieldcounty.gov",
        "data.alphacounty.gov",
    ]
    assert _find(places, country="FR").candidates == []
    assert _ids(_find(places, query="springfield", level="city")) == ["data.cityofspringfield.org"]


def test_filter_without_query_includes_generic_tier_first(places: Registry):
    assert _ids(_find(places, country="US")) == [
        "data.kingcounty.gov",
        "data.springfieldcounty.gov",
        "data.alphacounty.gov",
        "data.cityofspringfield.org",
    ]
    assert _ids(_find(places, level="city")) == ["data.cityofspringfield.org"]
    assert _ids(_find(places)) == [
        "data.kingcounty.gov",
        "data.springfieldcounty.gov",
        "data.alphacounty.gov",
        "data.cityofspringfield.org",
        "data.nowhere.example",
        "zzz.example.gov",
    ]


def test_punctuation_only_query_is_invalid_argument(places: Registry):
    for bad in (".", "-", " ,; "):
        with pytest.raises(AtlasError) as caught:
            _find(places, query=bad)
        envelope = caught.value.envelope
        assert envelope.code == ErrorCode.INVALID_ARGUMENT
        assert envelope.details is not None
        assert envelope.details.field == "query"
        assert envelope.repair is not None
        assert (envelope.repair.next_step, envelope.repair.tool, envelope.repair.arguments) == (
            "find_portal",
            "atlas_find_portals",
            {},
        )


def test_host_match_needs_whole_dns_labels(tmp_path: Path):
    reg = _registry(
        tmp_path,
        [
            _identity("data.sf.gov", name="Bay"),
            _identity("data.cityofchicago.org", name="Windy"),
        ],
    )
    assert [(c.id, c.match) for c in _find(reg, query="sf").candidates] == [("data.sf.gov", "host")]
    assert _ids(_find(reg, query="sf.gov")) == ["data.sf.gov"]
    assert _ids(_find(reg, query="CityOfChicago")) == ["data.cityofchicago.org"]
    for fragment in ("ata.s", "cityof", "f.g"):
        assert _find(reg, query=fragment).candidates == [], fragment


def test_place_name_outranks_host_then_id_breaks_ties(tmp_path: Path):
    reg = _registry(
        tmp_path,
        [
            _identity("b.example.gov", name="Bee"),
            _identity("a.example.gov", name="Ay", place_names=["Example"]),
            _identity("c.example.gov", name="Sea"),
            _identity("d.example.gov", name="Dee", place_names=["Example"]),
        ],
    )
    got = [(c.id, c.match) for c in _find(reg, query="example").candidates]
    assert got == [
        ("a.example.gov", "place_name"),
        ("d.example.gov", "place_name"),
        ("b.example.gov", "host"),
        ("c.example.gov", "host"),
    ]


def test_allowlist_limits_candidates(monkeypatch: pytest.MonkeyPatch):
    full = _ids(_find(load_registry(), query="chicago"))
    assert full == ["data.cityofchicago.org"]
    monkeypatch.setenv("OPENDATA_ATLAS_PORTALS", "seattle")
    assert _find(load_registry(), query="chicago").candidates == []
    assert _ids(_find(load_registry(), query="seattle")) == ["data.seattle.gov"]
    monkeypatch.setenv("OPENDATA_ATLAS_PORTALS", "chicago")
    assert _ids(_find(load_registry(), query="chicago")) == ["data.cityofchicago.org"]


def test_wrong_shape_cursor_is_invalid_not_internal(places: Registry):
    for state in ({}, {"rv": "v1"}):
        forged = cursors.encode("portals", state, portal_id="*")
        with pytest.raises(AtlasError) as caught:
            _find(places, cursor=forged)
        assert caught.value.envelope.code == ErrorCode.INVALID_CURSOR


def test_paging_walks_every_match_once(places: Registry):
    seen: list[str] = []
    page = _find(places, tier=None, page_size=1)
    while True:
        seen += _ids(page)
        if not page.has_more:
            break
        assert page.next_cursor
        page = _find(places, page_size=1, cursor=page.next_cursor)
    assert seen == _ids(_find(places, page_size=50))
    assert len(seen) == len(set(seen)) == 6  # every tier (ruling 32)


def test_cursor_expires_on_registry_change(places: Registry, tmp_path: Path):
    page = _find(places, page_size=1)
    assert page.next_cursor
    newer = _registry(tmp_path, [_identity("data.kingcounty.gov", "profiled")], version="v2")
    with pytest.raises(AtlasError) as caught:
        _find(newer, cursor=page.next_cursor)
    envelope = caught.value.envelope
    assert envelope.code == ErrorCode.CURSOR_EXPIRED
    assert envelope.repair is not None
    assert envelope.repair.next_step == "read_paging"


def test_other_tools_cursor_is_invalid(places: Registry):
    foreign = cursors.encode("search", {}, portal_id="*")
    with pytest.raises(AtlasError) as caught:
        _find(places, cursor=foreign)
    assert caught.value.envelope.code == ErrorCode.INVALID_CURSOR


def test_shipped_registry_alias_and_county():
    chicago = find_portals(
        load_registry(),
        query="Chicago",
        level=None,
        country=None,
        tier=None,
        page_size=None,
        cursor=None,
    )
    assert chicago.candidates[0].id == "data.cityofchicago.org"
    assert chicago.candidates[0].match == "alias"
    cook = find_portals(
        load_registry(),
        query="Cook County",
        level=None,
        country=None,
        tier=None,
        page_size=None,
        cursor=None,
    )
    assert "datacatalog.cookcountyil.gov" in [c.id for c in cook.candidates]
    assert cook.candidates[0].id == "datacatalog.cookcountyil.gov"


def test_shipped_registry_no_argument_listing_pages_past_seattle():
    """Ruling 32: the `portal_not_found` repair lists every portal, not only Seattle."""
    result = _find(load_registry())
    assert result.candidates[0].tier == "curated"  # curated first, by canonical id within a tier
    assert "data.seattle.gov" in {c.id for c in result.candidates}
    assert result.has_more
    assert result.next_cursor is not None
    assert {c.tier for c in result.candidates} > {"curated"}


def test_shipped_registry_new_york_city_and_state():
    """The query "New York" finds the city and the state; "New York City" finds the city."""
    new_york = _ids(_find(load_registry(), query="New York"))
    assert "data.cityofnewyork.us" in new_york
    assert "data.ny.gov" in new_york
    assert "data.cityofnewyork.us" in _ids(_find(load_registry(), query="New York City"))


PLACE_QUERIES = {
    "data.everettwa.gov": ["Everett", "Everett, WA", "everett"],
    "data.kingcounty.gov": ["King County", "King County, WA", "king-county"],
}


def _first_for_place(registry: Registry) -> dict[str, str | None]:
    """Each Review Focus 1 query, and the id it returns first."""
    return {
        q: next(iter(_ids(_find(registry, query=q))), None)
        for qs in PLACE_QUERIES.values()
        for q in qs
    }


def test_shipped_registry_finds_everett_and_king_county():
    """Review Focus 1: each new portal comes first for its place names and its alias."""
    expected = {q: id_ for id_, qs in PLACE_QUERIES.items() for q in qs}
    assert _first_for_place(load_registry()) == expected


def _every_candidate(registry: Registry, query: str) -> list[str]:
    """Every candidate id for `query`, in order, across all pages."""
    seen: list[str] = []
    page = _find(registry, query=query)
    while True:
        seen += _ids(page)
        if not page.has_more:
            return seen
        assert page.next_cursor
        page = _find(registry, cursor=page.next_cursor)


def _cross_matches(registry: Registry) -> list[str]:
    """Review Focus 2 violations: Seattle and King County must stay apart."""
    seattle = _every_candidate(registry, "Seattle")
    king = _every_candidate(registry, "King County")
    problems = []
    if seattle[:1] != ["data.seattle.gov"]:
        problems.append(f"Seattle first is {seattle[:1]}")
    if "data.kingcounty.gov" in seattle:
        problems.append("Seattle finds data.kingcounty.gov")
    if "data.seattle.gov" in king:
        problems.append("King County finds data.seattle.gov")
    return problems


def test_seattle_and_king_county_do_not_cross_match():
    """Review Focus 2: Seattle and King County stay apart, on every page."""
    assert _cross_matches(load_registry()) == []


# --- the tool ---------------------------------------------------------------


async def test_tool_is_first_closed_world_and_portal_free(tools_list):
    first = tools_list["tools"][0]
    assert first["name"] == "atlas_find_portals"
    assert first["annotations"]["openWorldHint"] is False
    assert "portal" not in first["inputSchema"]["properties"]
    assert first["inputSchema"]["properties"]["country"]["pattern"] == "^[A-Za-z]{2}$"


async def test_tool_returns_candidates_without_source_portal(client):
    result = wire(
        await client.call_tool_mcp("atlas_find_portals", {"query": "seattle", "country": "us"})
    )
    content = result["structuredContent"]
    assert content["candidates"][0]["id"] == "data.seattle.gov"
    assert content["candidates"][0]["match"] == "alias"
    assert "portal" not in content["source"]
    assert content["registry_version"]


async def test_continuation_may_repeat_only_page_size(client):
    first = wire(
        await client.call_tool_mcp("atlas_find_portals", {"tier": "generic", "page_size": 1})
    )
    content = first["structuredContent"]
    assert content["has_more"]
    bad = wire(
        await client.call_tool_mcp(
            "atlas_find_portals", {"cursor": content["next_cursor"], "country": "US"}
        )
    )["structuredContent"]
    assert bad["code"] == "invalid_argument"
    assert bad["details"]["field"] == "country"
    ok = wire(
        await client.call_tool_mcp(
            "atlas_find_portals", {"cursor": content["next_cursor"], "page_size": 1}
        )
    )
    assert not ok.get("isError")


async def test_bad_cursor_gets_restart_repair(client):
    envelope = wire(await client.call_tool_mcp("atlas_find_portals", {"cursor": "nope"}))[
        "structuredContent"
    ]
    assert envelope["code"] == "invalid_cursor"
    assert envelope["repair"]["next_step"] == "read_paging"


async def test_invalid_country_is_invalid_argument(client):
    envelope = wire(await client.call_tool_mcp("atlas_find_portals", {"country": "USA"}))[
        "structuredContent"
    ]
    assert envelope["code"] == "invalid_argument"


@pytest.mark.parametrize("limit", [None, 4_000])
def test_two_thousand_portals_page_within_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, limit: int | None
):
    """Task 9 fixture: the no-argument walk over a 2,000-entry registry stays in budget.

    50 generic candidates (7,041 bytes) fit RESULT_LIMIT whole, so the lowered limit is the
    known positive: there `fit` must trim pages and the walk must still cover every id once.
    """
    from opendata_atlas.core import budget
    from opendata_atlas.core.budget import wire_size

    if limit is not None:
        monkeypatch.setattr(budget, "RESULT_LIMIT", limit)
    identities = [
        _identity(f"data.portal{i:04d}.example.gov", name=f"Generic portal {i:04d} ".ljust(40, "n"))
        for i in range(2000)
    ]
    entries = [{"identity": i, "dataset_count": 7, "catalog_size": 9} for i in identities]
    (tmp_path / "registry.json").write_text(json.dumps({"version": "v1", "entries": entries}))
    reg = load_registry(tmp_path / "registry.json", packs_dir=tmp_path)

    seen: list[str] = []
    sizes: list[int] = []
    page = _find(reg, page_size=50)
    while True:
        # Ruling 72: pages are measured by wire_size, what the client receives.
        assert wire_size(page) <= budget.RESULT_LIMIT
        seen += _ids(page)
        sizes.append(len(page.candidates))
        if not page.has_more:
            break
        page = _find(reg, page_size=50, cursor=page.next_cursor)
    assert len(seen) == len(set(seen)) == 2000
    assert set(seen) == {i["id"] for i in identities}
    if limit is None:
        assert len(sizes) == 2000 // 50  # whole pages of 50
    else:
        assert max(sizes) < 50, "fit trimmed every page under the lowered limit"


@pytest.mark.parametrize("limit", [None, 4_000])
async def test_two_thousand_portals_fit_the_modern_wire(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, limit: int | None
):
    """Ruling 72: every page of the 2,000-portal walk, as received with its frame, fits.

    At the default limit each page is within 24 KiB framed; under the lowered limit (the known
    positive, where `fit` trims) each received page is within that limit by wire_size.
    """
    from opendata_atlas.constants import RESULT_BYTE_BUDGET
    from opendata_atlas.core import budget
    from opendata_atlas.mcp import tools
    from tests.conftest import framed_size

    if limit is not None:
        monkeypatch.setattr(budget, "RESULT_LIMIT", limit)
    identities = [
        _identity(f"data.portal{i:04d}.example.gov", name=f"Generic portal {i:04d} ".ljust(40, "n"))
        for i in range(2000)
    ]
    entries = [{"identity": i, "dataset_count": 7, "catalog_size": 9} for i in identities]
    (tmp_path / "registry.json").write_text(json.dumps({"version": "v1", "entries": entries}))
    reg = load_registry(tmp_path / "registry.json", packs_dir=tmp_path)
    monkeypatch.setattr(tools, "load_registry", lambda: reg)

    args: dict[str, Any] = {"page_size": 50}
    seen: list[str] = []
    while True:
        result = wire(await client.call_tool_mcp("atlas_find_portals", args))
        assert result["isError"] is False, result["structuredContent"]
        assert framed_size(result) <= RESULT_BYTE_BUDGET
        received = {k: result[k] for k in ("content", "structuredContent", "isError")}
        assert len(json.dumps(received, separators=(",", ":")).encode()) <= budget.RESULT_LIMIT
        out = result["structuredContent"]
        seen += [c["id"] for c in out["candidates"]]
        if not out["has_more"]:
            break
        args = {"cursor": out["next_cursor"], "page_size": 50}
    assert len(seen) == len(set(seen)) == 2000
