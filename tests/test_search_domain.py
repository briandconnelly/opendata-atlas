"""Search keeps only entries from the portal's own catalog domain (docs/design.md: tool 1)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from opendata_atlas.core.http import SodaClient, set_client
from opendata_atlas.portals.model import PortalIdentity
from opendata_atlas.portals.registry import load_registry
from tests.conftest import SEATTLE_IDENTITY_DICT
from tests.test_search_evidence import Catalog, install, item, search

EVIDENCE = Path(__file__).parents[1] / "docs/evidence/registry-2026-10-18/probes.jsonl"


def entry(dataset_id: str, name: str, domain: str | None, **kw: Any) -> dict[str, Any]:
    out = item(dataset_id, name, **kw)
    if domain is not None:
        out["metadata"]["domain"] = domain
    return out


SEATTLE = "data.seattle.gov"


async def test_foreign_domain_results_are_dropped_and_counted(client, tools_list):
    install(
        Catalog(
            [entry("aaaa-aaaa", "Trees", SEATTLE), entry("bbbb-bbbb", "Trees", "data.other.gov")],
            external=[
                entry("cccc-cccc", "Link", "data.other.gov", kind="href"),
                entry("dddd-dddd", "Link", SEATTLE, kind="href"),
            ],
        )
    )
    out = await search(client, tools_list, {"portal": "seattle", "query": "trees"})
    assert [d["dataset_id"] for d in out["datasets"]] == ["aaaa-aaaa"]
    assert [d["dataset_id"] for d in out["external_matches"]] == ["dddd-dddd"]
    assert [e["dataset_id"] for e in out["match_evidence"]] == ["aaaa-aaaa"]
    assert out["foreign_results_dropped"] == 2


async def test_no_foreign_results_omits_the_count(client, tools_list):
    install(Catalog([entry("aaaa-aaaa", "Trees", SEATTLE), entry("bbbb-bbbb", "Trees", None)]))
    out = await search(client, tools_list, {"portal": "seattle", "query": "trees"})
    assert [d["dataset_id"] for d in out["datasets"]] == ["aaaa-aaaa", "bbbb-bbbb"]
    assert "foreign_results_dropped" not in out


async def test_a_foreign_entry_mid_page_still_advances_the_offset(client, tools_list):
    pages = {
        "0": [
            entry("aaaa-aaaa", "Trees", SEATTLE),
            entry("bbbb-bbbb", "Trees", "data.other.gov"),
            entry("cccc-cccc", "Trees", SEATTLE),
        ],
        "3": [entry("dddd-dddd", "Trees", SEATTLE)],
    }
    offsets: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params.multi_items())
        if params.get("only") == "federated_href,href":
            return httpx.Response(200, json={"results": [], "resultSetSize": 0})
        offsets.append(params["offset"])
        return httpx.Response(200, json={"results": pages[params["offset"]], "resultSetSize": 4})

    set_client(SodaClient(transport=httpx.MockTransport(handler)))
    first = await search(
        client, tools_list, {"portal": "seattle", "query": "trees", "page_size": 3}
    )
    assert [d["dataset_id"] for d in first["datasets"]] == ["aaaa-aaaa", "cccc-cccc"]
    assert first["foreign_results_dropped"] == 1
    assert first["has_more"] is True
    second = await search(client, tools_list, {"portal": "seattle", "cursor": first["next_cursor"]})
    assert offsets == ["0", "3"], "the dropped entry still counts toward the upstream offset"
    assert [d["dataset_id"] for d in second["datasets"]] == ["dddd-dddd"]
    assert second["has_more"] is False
    assert "foreign_results_dropped" not in second


async def test_a_page_of_only_foreign_entries_still_pages_on(client, tools_list):
    install(Catalog([entry("aaaa-aaaa", "Trees", "data.other.gov")], total=5))
    out = await search(client, tools_list, {"portal": "seattle", "query": "trees"})
    assert out["datasets"] == []
    assert out["foreign_results_dropped"] == 1
    assert out["has_more"] is True
    assert out["next_cursor"]


async def test_search_context_portal_expects_its_search_context(client, tools_list):
    install(
        Catalog(
            [
                entry("aaaa-aaaa", "Trees", "data.sf.gov"),
                entry("bbbb-bbbb", "Trees", "data.sfgov.org"),
            ]
        )
    )
    out = await search(client, tools_list, {"portal": "data.sf.gov", "query": "trees"})
    assert [d["dataset_id"] for d in out["datasets"]] == ["aaaa-aaaa"]
    assert out["foreign_results_dropped"] == 1


# --- the expected domain ------------------------------------------------------------


def test_result_domain_prefers_search_context():
    base = SEATTLE_IDENTITY_DICT
    both = {"domains": "cos.x.gov", "search_context": "x.gov"}
    assert PortalIdentity.model_validate(base | {"catalog_query": both}).result_domain == "x.gov"
    only = {"search_context": "y.gov"}
    assert PortalIdentity.model_validate(base | {"catalog_query": only}).result_domain == "y.gov"
    dom = {"domains": "z.gov"}
    assert PortalIdentity.model_validate(base | {"catalog_query": dom}).result_domain == "z.gov"


def test_result_domain_matches_probed_evidence_for_every_registry_entry():
    """Pins Task 2's identity rule against probe evidence, for every shipped registry entry.

    Each entry's `result_domain` must be the only domain its `catalog_query` returned when the
    registry was built, so a wrong rule would fail here rather than empty a portal's search.
    """
    probes = {}
    for line in EVIDENCE.read_text().splitlines():
        rec = json.loads(line)
        probes[rec.get("domain") or rec["id"]] = rec
    entries = load_registry().entries
    checked = 0
    for ident in (e.identity for e in entries.values()):
        assert ident.id in probes, f"no probe record for {ident.id}"
        rec = probes[ident.id]
        if rec["kind"] == "pack":
            if "identity" in rec:  # a probed pack query (Chicago): the domains it returned
                assert set(rec["identity"]["domains_seen"]) == {ident.result_domain}, ident.id
            else:
                assert ident.result_domain == "data.seattle.gov"  # fixtures: metadata.domain
            checked += 1
            continue
        cand = next((c for c in rec["candidates"] if c["params"] == ident.catalog_query), None)
        assert cand, f"{ident.id}: no probed candidate for {ident.catalog_query}"
        assert cand["matches"], ident.id
        assert set(cand["domains_seen"]) == {ident.result_domain}, ident.id
        checked += 1
    assert checked == len(entries) > 0


@pytest.mark.parametrize("fixture", ["search_fire", "search_all_pages"])
def test_seattle_fixtures_carry_only_the_expected_domain(fixture):
    path = Path(__file__).parent / "fixtures/http" / f"{fixture}.json"
    domains = {
        r["metadata"]["domain"]
        for rec in json.loads(path.read_text()).values()
        for r in rec["body"]["results"]
    }
    assert domains == {"data.seattle.gov"}


def test_catalog_query_must_name_a_domain():
    with pytest.raises(ValidationError, match=r"`domains` or `search_context`"):
        PortalIdentity.model_validate(SEATTLE_IDENTITY_DICT | {"catalog_query": {}})
    with pytest.raises(ValidationError):
        PortalIdentity.model_validate(SEATTLE_IDENTITY_DICT | {"catalog_query": {"x": "y"}})


async def test_a_malformed_metadata_is_kept_not_a_crash(client, tools_list):
    odd = entry("aaaa-aaaa", "Trees", None)
    odd["metadata"] = "oops"
    install(Catalog([odd]))
    out = await search(client, tools_list, {"portal": "seattle", "query": "trees"})
    assert [d["dataset_id"] for d in out["datasets"]] == ["aaaa-aaaa"]
    assert "foreign_results_dropped" not in out


async def test_a_map_view_of_a_foreign_parent_is_dropped_with_it(client, tools_list):
    """The view is a window onto its parent; with the parent foreign it has nothing to show."""
    install(
        Catalog(
            [
                entry("aaaa-aaaa", "Trees", SEATTLE),
                entry("mmmm-mmmm", "Trees map", SEATTLE, kind="map", parent="pppp-pppp"),
            ],
            parents=[entry("pppp-pppp", "Trees", "data.other.gov")],
        )
    )
    out = await search(client, tools_list, {"portal": "seattle", "query": "trees"})
    assert [d["dataset_id"] for d in out["datasets"]] == ["aaaa-aaaa"]
    assert out["foreign_results_dropped"] == 1
