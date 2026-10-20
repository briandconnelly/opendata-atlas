from __future__ import annotations

import json
import tomllib
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from opendata_atlas.portals.loader import PORTALS_DIR, SEATTLE, PackError
from opendata_atlas.portals.model import Pack, PortalIdentity
from opendata_atlas.portals.registry import (
    Registry,
    RegistryEntry,
    _check_unique,
    context_for,
    load_registry,
)
from tests.conftest import seattle_only_packs

FIXTURE = Path(__file__).parent / "fixtures" / "registry" / "registry.json"


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


def _write(path: Path, identities: list[dict[str, Any]]) -> Path:
    entries = [{"identity": i, "dataset_count": None, "catalog_size": None} for i in identities]
    path.write_text(json.dumps({"version": "t", "entries": entries}))
    return path


@pytest.fixture
def empty_packs(tmp_path: Path) -> Path:
    d = tmp_path / "packs"
    d.mkdir()
    return d


def test_load_registry_reads_entries_and_version(empty_packs: Path):
    reg = load_registry(FIXTURE, empty_packs)
    assert reg.version == "2026-10-18-fixture00000"
    assert set(reg.entries) == {"a.example.gov", "b.example.gov", "data.seattle.gov"}
    assert isinstance(reg.entries["b.example.gov"], RegistryEntry)
    assert reg.entries["b.example.gov"].dataset_count == 12
    assert reg.entries["a.example.gov"].catalog_size is None


def test_pack_identity_overrides_registry_entry():
    reg = load_registry(FIXTURE, SEATTLE.parent)
    entry = reg.entries["data.seattle.gov"]
    assert entry.identity.name == "City of Seattle"
    assert entry.identity.tier == "curated"
    assert (entry.dataset_count, entry.catalog_size) == (5000, 7000)


def test_pack_without_registry_entry_is_reachable(tmp_path: Path):
    path = _write(tmp_path / "r.json", [_identity("a.example.gov")])
    reg = load_registry(path, PORTALS_DIR)
    found = reg.by_alias("seattle")
    assert found is not None
    assert found.identity.id == "data.seattle.gov"


def test_by_alias_is_case_insensitive(empty_packs: Path):
    reg = load_registry(FIXTURE, empty_packs)
    assert reg.by_alias("ALPHA") is not None
    assert reg.by_alias("A.Example.GOV") is not None
    assert reg.by_alias("alpha").identity.id == "a.example.gov"  # ty: ignore[unresolved-attribute]
    assert reg.by_alias("nope") is None


def test_ordered_puts_curated_first(tmp_path: Path):
    path = _write(
        tmp_path / "r.json",
        [
            _identity("z.example.gov"),
            _identity("m.example.gov", tier="profiled"),
            _identity("b.example.gov"),
        ],
    )
    reg = load_registry(path, seattle_only_packs(tmp_path))
    assert isinstance(reg, Registry)
    assert [e.identity.id for e in reg.ordered] == [
        "data.seattle.gov",
        "m.example.gov",
        "b.example.gov",
        "z.example.gov",
    ]


def test_context_for_without_pack_has_empty_pack(empty_packs: Path):
    ident = load_registry(FIXTURE, empty_packs).entries["a.example.gov"].identity
    ctx = context_for(ident, None)
    assert ctx.identity == ident
    assert ctx.pack == Pack(claims=[])
    assert ctx.guides == ()


def test_context_for_with_pack_loads_it():
    ctx = context_for(
        load_registry(FIXTURE, SEATTLE.parent).entries["data.seattle.gov"].identity, SEATTLE
    )
    assert ctx.pack.claims


def test_context_for_rejects_pack_with_other_identity(empty_packs: Path):
    ident = load_registry(FIXTURE, empty_packs).entries["a.example.gov"].identity
    with pytest.raises(PackError, match=r"(?=.*a\.example\.gov)(?=.*data\.seattle\.gov)"):
        context_for(ident, SEATTLE)


def test_invalid_json_raises_pack_error(tmp_path: Path, empty_packs: Path):
    path = tmp_path / "r.json"
    path.write_text("{not json")
    with pytest.raises(PackError, match=r"r\.json"):
        load_registry(path, empty_packs)


def test_missing_entries_key_raises_pack_error(tmp_path: Path, empty_packs: Path):
    path = tmp_path / "r.json"
    path.write_text(json.dumps({"version": "t"}))
    with pytest.raises(PackError, match=r"r\.json"):
        load_registry(path, empty_packs)


def test_invalid_identity_raises_pack_error(tmp_path: Path, empty_packs: Path):
    path = _write(tmp_path / "r.json", [_identity("a.example.gov", catalog_region="mars")])
    with pytest.raises(PackError, match=r"r\.json"):
        load_registry(path, empty_packs)


def test_duplicate_ids_in_registry_raise(tmp_path: Path, empty_packs: Path):
    path = _write(tmp_path / "r.json", [_identity("a.example.gov"), _identity("a.example.gov")])
    with pytest.raises(PackError, match=r"a\.example\.gov"):
        load_registry(path, empty_packs)


def test_duplicate_aliases_raise(tmp_path: Path, empty_packs: Path):
    path = _write(
        tmp_path / "r.json",
        [
            _identity("a.example.gov", aliases=["shared"]),
            _identity("b.example.gov", aliases=["shared"]),
        ],
    )
    with pytest.raises(
        PackError, match=r"a\.example\.gov.*b\.example\.gov|b\.example\.gov.*a\.example\.gov"
    ):
        load_registry(path, empty_packs)


def test_alias_colliding_with_other_portals_id_raises(tmp_path: Path, empty_packs: Path):
    path = _write(
        tmp_path / "r.json",
        [_identity("a.example.gov", aliases=["taken-name"]), _identity("taken-name")],
    )
    with pytest.raises(PackError, match=r"(?=.*a\.example\.gov)(?=.*taken-name)"):
        load_registry(path, empty_packs)


def test_by_alias_resolves_id_case_insensitively(empty_packs: Path):
    reg = load_registry(FIXTURE, empty_packs)
    found = reg.by_alias("DATA.SEATTLE.GOV")
    assert found is not None
    assert found.identity.name == "x"
    assert found.identity.id == "data.seattle.gov"


def _raw_entry(id_: str, aliases: list[str] | None = None) -> RegistryEntry:
    # model_construct skips the lowercase-only id/alias patterns, so the casefold
    # in _check_unique is tested on its own.
    ident = PortalIdentity.model_construct(id=id_, aliases=aliases or [])
    return RegistryEntry.model_construct(identity=ident, dataset_count=None, catalog_size=None)


def _unique(*entries: RegistryEntry) -> None:
    _check_unique({e.identity.id: e for e in entries})


def test_ids_differing_only_in_case_collide():
    with pytest.raises(PackError, match=r"(?=.*Data\.Example\.gov)(?=.*data\.example\.gov)"):
        _unique(_raw_entry("Data.Example.gov"), _raw_entry("data.example.gov"))


def test_aliases_differing_only_in_case_collide():
    with pytest.raises(PackError, match=r"(?=.*chicago-a)(?=.*chicago-b)"):
        _unique(_raw_entry("chicago-a", ["Chicago"]), _raw_entry("chicago-b", ["chicago"]))


def test_alias_and_other_id_differing_only_in_case_collide():
    with pytest.raises(PackError, match=r"(?=.*a\.example\.gov)(?=.*taken-name)"):
        _unique(_raw_entry("a.example.gov", ["Taken-Name"]), _raw_entry("taken-name"))


# --- scripts/build_registry.py (pure functions, offline) ---

_BUILD = Path(__file__).resolve().parent.parent / "scripts" / "build_registry.py"


def _load_builder():
    import importlib.util

    spec = importlib.util.spec_from_file_location("build_registry", _BUILD)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


br = _load_builder()


def _entry(id_: str, aliases: list[str] | None = None, size: int | None = None) -> RegistryEntry:
    ident = PortalIdentity.model_validate(_identity(id_, aliases=aliases or []))
    return RegistryEntry(identity=ident, dataset_count=size, catalog_size=size)


def test_choose_catalog_query_prefers_largest_matching():
    chosen = br.choose_catalog_query(
        [
            ({"domains": "data.sf.gov"}, 5, True),
            ({"search_context": "data.sf.gov"}, 1225, True),
        ]
    )
    assert chosen == {"search_context": "data.sf.gov"}


def test_choose_catalog_query_ignores_larger_unmatched_and_ties_prefer_domains():
    chosen = br.choose_catalog_query(
        [
            ({"search_context": "data.lacity.org"}, 1274, False),
            ({"search_context": "data.lacity.org"}, 927, True),
            ({"domains": "data.lacity.org"}, 927, True),
        ]
    )
    assert chosen == {"domains": "data.lacity.org"}


def test_choose_catalog_query_none_when_no_match():
    assert br.choose_catalog_query([({"domains": "x.example.gov"}, 10, False)]) is None
    assert br.choose_catalog_query([]) is None


def test_alias_collision_exits_naming_both():
    entries = {
        "a.example.gov": _entry("a.example.gov", ["shared"]),
        "b.example.gov": _entry("b.example.gov", ["shared"]),
    }
    with pytest.raises(SystemExit, match=r"(?=.*a\.example\.gov)(?=.*b\.example\.gov)"):
        br.check_aliases(entries)


def test_alias_colliding_with_id_exits_naming_both():
    entries = {
        "a.example.gov": _entry("a.example.gov", ["b-example"]),
        "b-example": _entry("b-example"),
    }
    with pytest.raises(SystemExit, match=r"(?=.*a\.example\.gov)(?=.*b-example)"):
        br.check_aliases(entries)


def test_check_aliases_accepts_distinct_names():
    br.check_aliases(
        {
            "a.example.gov": _entry("a.example.gov", ["alpha"]),
            "b.example.gov": _entry("b.example.gov", ["beta"]),
        }
    )


def test_collision_writes_no_registry(tmp_path: Path):
    out = tmp_path / "registry.json"
    entries = {
        "a.example.gov": _entry("a.example.gov", ["shared"]),
        "b.example.gov": _entry("b.example.gov", ["shared"]),
    }
    with pytest.raises(SystemExit):
        br.write_registry(entries, out, date(2026, 10, 18))
    assert not out.exists()


def test_write_registry_round_trips_through_load_registry(tmp_path: Path, empty_packs: Path):
    out = tmp_path / "registry.json"
    entries = {"a.example.gov": _entry("a.example.gov", ["alpha"], size=3)}
    br.write_registry(entries, out, date(2026, 10, 18))
    reg = load_registry(out, empty_packs)
    assert reg.by_alias("alpha").identity.id == "a.example.gov"  # ty: ignore[unresolved-attribute]
    assert reg.entries["a.example.gov"].catalog_size == 3
    assert reg.version.startswith("2026-10-18-")


def test_override_adds_manual_entry():
    entries = {"a.example.gov": _entry("a.example.gov")}
    merged = br.merge_overrides(
        entries,
        {
            "m.example.gov": {
                "name": "Manual Portal",
                "catalog_query": {"search_context": "m.example.gov"},
            }
        },
    )
    assert set(merged) == {"a.example.gov", "m.example.gov"}
    manual = merged["m.example.gov"].identity
    assert manual.name == "Manual Portal"
    assert manual.public_host == "m.example.gov"
    assert manual.catalog_query == {"search_context": "m.example.gov"}
    assert manual.tier == "generic"
    assert entries["a.example.gov"].identity.name == "a.example.gov"  # input untouched


def test_override_updates_enumerated_entry_and_keeps_counts():
    entries = {"a.example.gov": _entry("a.example.gov", size=9)}
    merged = br.merge_overrides(
        entries,
        {
            "a.example.gov": {
                "name": "City of A",
                "aliases": ["a-city"],
                "place_names": ["A"],
                "jurisdiction": {"level": "city", "country": "US", "region": "WA"},
                "timezone": "America/Los_Angeles",
            }
        },
    )
    ident = merged["a.example.gov"].identity
    assert (ident.name, ident.aliases, ident.timezone) == (
        "City of A",
        ["a-city"],
        "America/Los_Angeles",
    )
    assert ident.jurisdiction is not None
    assert ident.jurisdiction.level == "city"
    assert merged["a.example.gov"].catalog_size == 9


def test_override_rejects_unknown_field():
    with pytest.raises(SystemExit, match=r"(?=.*a\.example\.gov)(?=.*tier)"):
        br.merge_overrides(
            {"a.example.gov": _entry("a.example.gov")}, {"a.example.gov": {"tier": "curated"}}
        )


def test_registry_version_is_deterministic():
    a = {"a.example.gov": _entry("a.example.gov"), "b.example.gov": _entry("b.example.gov")}
    b = {"b.example.gov": _entry("b.example.gov"), "a.example.gov": _entry("a.example.gov")}
    v1 = br.registry_version(a, date(2026, 10, 18))
    assert v1 == br.registry_version(b, date(2026, 10, 18))
    assert v1.startswith("2026-10-18-")
    assert len(v1) == len("2026-10-18-") + 12
    changed = {"a.example.gov": _entry("a.example.gov", size=1)}
    assert br.registry_version(changed, date(2026, 10, 18)) != v1


def test_choose_public_host_follows_links_or_matched_value():
    host, _ = br.choose_public_host("data.sfgov.org", {"search_context": "data.sf.gov"}, {})
    assert host == "data.sf.gov"
    host, _ = br.choose_public_host(
        "cos-data.example.gov", {"domains": "cos-data.example.gov"}, {"data.example.gov": 40}
    )
    assert host == "data.example.gov"
    host, _ = br.choose_public_host(
        "x.example.gov", {"domains": "x.example.gov"}, {"x.example.gov": 30, "y.example.gov": 2}
    )
    assert host == "x.example.gov"


def test_shipped_registry_loads_with_required_portals():
    reg = load_registry()
    # 242 on 2026-10-18 after the fix-round-1 eligibility rules and the `integration` token
    # (docs/upstream-facts.md).
    assert len(reg.entries) >= 240
    assert "performance.seattle.gov" not in reg.entries  # 2xx, but not JSON: ineligible
    assert "al-amcc-uat.data.socrata.com" not in reg.entries  # non-production token
    assert "integration-kcmo.data.socrata.com" not in reg.entries  # non-production token
    chicago = reg.by_alias("chicago")
    assert chicago is not None
    assert chicago.identity.id == "data.cityofchicago.org"
    assert chicago.identity.timezone == "America/Chicago"
    seattle = reg.by_alias("seattle")
    assert seattle is not None
    assert seattle.identity.tier == "curated"
    assert "cos-data.seattle.gov" not in reg.entries  # folded into the Seattle pack
    assert reg.entries["data.sf.gov"].identity.catalog_query == {"search_context": "data.sf.gov"}
    cook = reg.entries["datacatalog.cookcountyil.gov"].identity
    assert cook.jurisdiction is not None
    assert (cook.jurisdiction.level, cook.jurisdiction.region) == ("county", "IL")
    assert {"Cook County", "Cook County, IL"} <= set(cook.place_names)
    assert cook.timezone == "America/Chicago"


# --- fix round 1: eligibility rules, manual identity, pack overrides ---


@pytest.mark.parametrize(
    "host",
    [
        "al-amcc-uat.data.socrata.com",
        "newjerseysp-uat.data.socrata.com",
        "va-cca-uat.data.socrata.com",
        "vtmbl-reporting-uat.data.socrata.com",
        "newjerseysp-dev.data.socrata.com",
        "budget-qa-reporting.data.socrata.com",
        "lafayettecsdgovla-train.data.socrata.com",
        "dot-edpsandbox.data.socrata.com",
        "test.example.gov",
        "STAGING-x.example.gov",
        "integration-kcmo.data.socrata.com",
    ],
)
def test_non_production_hosts_are_ineligible(host: str):
    assert not br.is_production(host)


@pytest.mark.parametrize(
    "host",
    [
        "data.texas.gov",
        "datacatalog.cookcountyil.gov",
        "testament.data.socrata.com",
        "devon-county.example.gov",
        "data.qa-county.example.gov",  # only the first label decides
    ],
)
def test_production_hosts_stay_eligible(host: str):
    assert br.is_production(host)


def _v(status: int, json_ok: bool = True, error: str | None = None, timeout: bool = False):
    return {"status": status, "json": json_ok, "error": error, "timeout": timeout}


def test_views_verdict_keeps_2xx_json_5xx_and_timeouts():
    assert br.views_verdict(_v(200))[0]
    assert br.views_verdict(_v(500, json_ok=False))[0]
    assert br.views_verdict(_v(503, json_ok=False))[0]
    assert br.views_verdict(_v(0, False, "ReadTimeout", timeout=True))[0]
    assert br.views_verdict(_v(0, False, "ConnectTimeout", timeout=True))[0]


def test_views_verdict_drops_4xx_non_json_2xx_and_connection_failures():
    assert not br.views_verdict(_v(404, json_ok=False))[0]
    assert not br.views_verdict(_v(200, json_ok=False))[0]
    assert not br.views_verdict(_v(0, False, "ConnectError"))[0]
    assert not br.views_verdict(_v(0, False, "RemoteProtocolError"))[0]


def test_views_verdict_without_failure_class_asks_for_a_reprobe():
    with pytest.raises(SystemExit, match="re-probe"):
        br.views_verdict({"status": 0, "json": False})


def test_manual_entry_failing_identity_exits():
    rec = {
        "errors": 0,
        "views": _v(200),
        "identity": {"matches": False, "complete_read": True},
    }
    with pytest.raises(SystemExit, match=r"m\.example\.gov"):
        br.check_manual("m.example.gov", rec)


def test_manual_entry_without_identity_result_exits():
    with pytest.raises(SystemExit, match=r"m\.example\.gov"):
        br.check_manual("m.example.gov", {"errors": 0, "views": _v(200)})


def test_manual_entry_passing_identity_and_views_is_accepted():
    rec = {"errors": 0, "views": _v(200), "identity": {"matches": True, "complete_read": True}}
    br.check_manual("m.example.gov", rec)


def test_expected_domain_prefers_search_context():
    assert br.expected_domain({"domains": "x.gov"}) == "x.gov"
    assert br.expected_domain({"search_context": "y.gov"}) == "y.gov"
    assert (
        br.expected_domain(
            {"domains": "cos-data.seattle.gov", "search_context": "data.seattle.gov"}
        )
        == "data.seattle.gov"
    )


def test_override_for_a_pack_id_exits_naming_it():
    with pytest.raises(SystemExit, match=r"data\.seattle\.gov"):
        br.reject_pack_overrides({"data.seattle.gov": {"name": "x"}}, {"data.seattle.gov"})
    br.reject_pack_overrides({"a.example.gov": {}}, {"data.seattle.gov"})


def test_chicago_alias_survives_the_pack():
    """The Chicago pack (milestone 4) took over the registry override; its alias and
    timezone must come through `portal.toml`."""
    entry = load_registry().by_alias("chicago")
    assert entry is not None
    assert entry.identity.id == "data.cityofchicago.org"
    assert entry.identity.timezone == "America/Chicago"


def test_everett_alias_survives_the_pack():
    """The Everett pack (milestone 6) took over registry override 58; its alias and
    timezone must come through `portal.toml`."""
    entry = load_registry().by_alias("everett")
    assert entry is not None
    assert entry.identity.id == "data.everettwa.gov"
    assert entry.identity.timezone == "America/Los_Angeles"


def test_king_county_alias_survives_the_pack():
    """The King County pack (milestone 6) took over registry override 59; its alias and
    timezone must come through `portal.toml`."""
    entry = load_registry().by_alias("king-county")
    assert entry is not None
    assert entry.identity.id == "data.kingcounty.gov"
    assert entry.identity.timezone == "America/Los_Angeles"


# --- generated names from site titles (records copied from live titles, 2026-10-19) ---

EVERETT = {
    "site_title": "Tyler Data & Insights",
    "site_company": "Tyler Data & Insights",
    "html_title": "City of Everett Open Data",
}
KING = {
    "site_title": "King County | Open Data",
    "site_company": "King County",
    "html_title": "King County | Open Data",
}
NOLA = {
    "site_title": "Data.NOLA.gov | Enabling New Orleans",
    "site_company": "Data.NOLA.gov",
    "html_title": "Home - DataDriven - City of New Orleans",
}
MO = {
    "site_title": "data.mo.gov | State of Missouri Data Portal",
    "site_company": "data.mo.gov",
    "html_title": "Catalog | data.mo.gov | State of Missouri Data Portal",
}
VENDOR = {
    "site_title": "Tyler Data & Insights",
    "site_company": "Tyler Data & Insights",
    "html_title": "Catalog | Tyler Data & Insights",
}
MOVED = {"site_title": None, "site_company": None, "html_title": "This site has moved"}
ALBANY = {
    "site_title": "Tyler Data & Insights",
    "site_company": "Tyler Data & Insights",
    "html_title": "Catalog | City of Albany",
}


def test_title_name_takes_the_sites_own_name():
    assert br.title_name(EVERETT, "data.everettwa.gov") == "City of Everett Open Data"
    assert br.title_name(KING, "data.kingcounty.gov") == "King County"
    assert br.title_name(ALBANY, "albany.data.socrata.com") == "City of Albany"


def test_title_name_prefers_a_government_name():
    assert br.title_name(NOLA, "data.nola.gov") == "City of New Orleans"


def test_generated_names_skip_generic_parts():
    assert br.title_name(MO, "data.mo.gov") == "State of Missouri Data Portal"
    assert br.title_name(VENDOR, "kirklandwa.data.socrata.com") is None
    assert br.title_name(MOVED, "opendata.fcgov.com") is None
    assert br.title_name({}, "x.data.socrata.com") is None


def test_override_name_beats_title_name():
    id_ = "data.everettwa.gov"
    entries = {id_: _entry(id_, size=7)}
    titled = br.apply_title_names(entries, {id_: EVERETT})
    merged = br.merge_overrides(titled, {id_: {"name": "Everett"}})
    assert merged[id_].identity.name == "Everett"
    # without the override, the title name stands, and counts are kept
    assert titled[id_].identity.name == "City of Everett Open Data"
    assert titled[id_].catalog_size == 7
    # a portal without a usable title keeps its name
    other = br.apply_title_names(
        {"x.example.gov": _entry("x.example.gov")}, {"x.example.gov": MOVED}
    )
    assert other["x.example.gov"].identity.name == "x.example.gov"


def test_titles_all_is_accepted():
    parse = br.build_parser().parse_args
    base = ["--out", "o", "--evidence", "e"]
    assert parse([*base, "--titles", "all"]).titles == "all"
    assert parse([*base, "--titles", "5"]).titles == 5
    assert parse(base).titles == 0
    for bad in ("0", "x"):
        with pytest.raises(SystemExit) as exc:
            parse([*base, "--titles", bad])
        assert exc.value.code == 2


_TITLES = Path(__file__).resolve().parent.parent / "docs/evidence/registry-2026-10-18/titles.json"


def _name_problems(registry: Registry) -> list[str]:
    """Shipped names that are generic, or that fall back to the host although the title names
    the portal and no override or pack identity set it (Review Focus 3)."""
    titles = json.loads(_TITLES.read_text())
    overrides = tomllib.loads(br.OVERRIDES_PATH.read_text())
    set_by_hand = {i for i, o in overrides.items() if "name" in o} | set(br._packs())
    problems = []
    for id_, entry in registry.entries.items():
        ident = entry.identity
        if ident.name.casefold() in br.GENERIC_TITLES:
            problems.append(f"{id_}: generic name {ident.name!r}")
        if ident.name == ident.public_host and id_ not in set_by_hand:
            generated = br.title_name(titles.get(id_, {}), ident.public_host)
            if generated is not None:
                problems.append(f"{id_}: host as name, but the title gives {generated!r}")
    return problems


def test_shipped_names_are_not_generic():
    assert _name_problems(load_registry()) == []
