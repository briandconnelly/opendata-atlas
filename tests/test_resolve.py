"""Portal resolution: pattern, lookup, operator allowlist, retirement."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from opendata_atlas.core.errors import AtlasError, ErrorCode
from opendata_atlas.portals import resolve
from opendata_atlas.portals.registry import Registry, RegistryEntry, load_registry
from opendata_atlas.portals.resolve import resolve_portal

ALLOWLIST_ENV = "OPENDATA_ATLAS_PORTALS"
CHICAGO = "data.cityofchicago.org"


@pytest.fixture(autouse=True)
def _no_allowlist(monkeypatch):
    monkeypatch.delenv(ALLOWLIST_ENV, raising=False)


def fail(value: str) -> AtlasError:
    with pytest.raises(AtlasError) as e:
        resolve_portal(value)
    return e.value


def with_retired(monkeypatch, portal_id: str = CHICAGO) -> None:
    reg = load_registry()
    entries = dict(reg.entries)
    old = entries[portal_id]
    entries[portal_id] = RegistryEntry(
        identity=old.identity.model_copy(update={"status": "retired"}),
        dataset_count=old.dataset_count,
        catalog_size=old.catalog_size,
    )
    monkeypatch.setattr(resolve, "load_registry", lambda: replace(reg, entries=entries))


def assert_no_echo(err: AtlasError, raw: str) -> None:
    assert raw not in json.dumps(err.envelope.to_wire())


def test_resolves_alias_and_id_case_insensitively():
    seattle = resolve_portal("Seattle")
    assert seattle.id == "data.seattle.gov"
    assert resolve_portal("DATA.SEATTLE.GOV") is seattle
    assert resolve_portal("chicago").id == CHICAGO


def test_unknown_portal_is_not_found_without_echo():
    raw = "zz-distinctive-portal-9431"
    err = fail(raw)
    env = err.envelope
    assert env.code is ErrorCode.PORTAL_NOT_FOUND
    assert env.temporary is False
    assert env.repair is not None
    assert (env.repair.tool, env.repair.arguments) == ("atlas_find_portals", {})
    assert env.details is not None
    assert env.details.value is None
    assert_no_echo(err, raw)


def test_allowlist_blocks_other_portals(monkeypatch):
    monkeypatch.setenv(ALLOWLIST_ENV, "seattle")
    assert resolve_portal("data.seattle.gov").id == "data.seattle.gov"
    err = fail("chicago")
    assert err.envelope.code is ErrorCode.PORTAL_NOT_ENABLED
    assert err.envelope.temporary is False
    assert_no_echo(err, "chicago")


def test_allowlist_is_read_per_call_and_tolerates_case_and_space(monkeypatch):
    monkeypatch.setenv(ALLOWLIST_ENV, " SEATTLE , Data.CityOfChicago.org ,")
    assert resolve_portal("chicago").id == CHICAGO
    monkeypatch.setenv(ALLOWLIST_ENV, "   ")
    assert resolve_portal("chicago").id == CHICAGO
    monkeypatch.setenv(ALLOWLIST_ENV, "seattle")
    assert fail("chicago").envelope.code is ErrorCode.PORTAL_NOT_ENABLED


def test_retired_portal_fails(monkeypatch):
    with_retired(monkeypatch)
    err = fail("chicago")
    assert err.envelope.code is ErrorCode.PORTAL_RETIRED
    assert err.envelope.temporary is False
    assert_no_echo(err, "chicago")


@pytest.mark.parametrize("raw", [" seattle", "seattle ", "seattle\n", "a", "-seattle", "sea ttle"])
def test_whitespace_portal_is_invalid_argument(raw):
    err = fail(raw)
    assert err.envelope.code is ErrorCode.INVALID_ARGUMENT
    assert err.envelope.details is not None
    assert err.envelope.details.field == "portal"


def test_invalid_portal_is_not_echoed():
    raw = "zq distinctive 7731!"
    assert_no_echo(fail(raw), raw)
    assert_no_echo(fail(" zq7731"), "zq7731")


def test_resolution_precedence(monkeypatch):
    with_retired(monkeypatch)
    monkeypatch.setenv(ALLOWLIST_ENV, "seattle")
    # invalid pattern beats unknown and blocked
    assert fail("bad value!").envelope.code is ErrorCode.INVALID_ARGUMENT
    # unknown beats blocked
    assert fail("nowhere-ville").envelope.code is ErrorCode.PORTAL_NOT_FOUND
    # known, retired and outside the allowlist: not enabled wins over retired
    assert fail("chicago").envelope.code is ErrorCode.PORTAL_NOT_ENABLED
    # known, retired and allowed: retired
    monkeypatch.setenv(ALLOWLIST_ENV, "chicago")
    assert fail("chicago").envelope.code is ErrorCode.PORTAL_RETIRED


def test_contexts_are_cached_per_canonical_id():
    assert resolve_portal("seattle") is resolve_portal("data.seattle.gov")
    assert resolve_portal("chicago") is resolve_portal(CHICAGO)
    assert isinstance(load_registry(), Registry)


def test_unknown_allowlist_entries_are_logged_once_and_fail_closed(monkeypatch, caplog):
    monkeypatch.setenv(ALLOWLIST_ENV, "seattle, typo-portal-4417")
    with caplog.at_level("WARNING", logger=resolve.log.name):
        assert resolve_portal("seattle").id == "data.seattle.gov"
        err = fail("chicago")
        resolve_portal("seattle")
    assert err.envelope.code is ErrorCode.PORTAL_NOT_ENABLED
    assert_no_echo(err, "typo-portal-4417")
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    assert "typo-portal-4417" in warnings[0].getMessage()
    assert not [r for r in caplog.records if r.levelname == "ERROR"]


def test_allowlist_with_no_resolvable_entry_logs_an_error(monkeypatch, caplog):
    monkeypatch.setenv(ALLOWLIST_ENV, "typo-portal-4417")
    with caplog.at_level("WARNING", logger=resolve.log.name):
        assert fail("seattle").envelope.code is ErrorCode.PORTAL_NOT_ENABLED
    assert [r.levelname for r in caplog.records] == ["WARNING", "ERROR"]


@pytest.mark.parametrize(
    "code", [ErrorCode.PORTAL_NOT_FOUND, ErrorCode.PORTAL_NOT_ENABLED, ErrorCode.PORTAL_RETIRED]
)
def test_emitted_text_matches_the_documented_example(monkeypatch, code):
    from opendata_atlas.core.reference import ERROR_EXAMPLES

    with_retired(monkeypatch)
    raw = {
        ErrorCode.PORTAL_NOT_FOUND: "nowhere-ville",
        ErrorCode.PORTAL_NOT_ENABLED: "seattle",
        ErrorCode.PORTAL_RETIRED: "chicago",
    }[code]
    if code is ErrorCode.PORTAL_NOT_ENABLED:
        monkeypatch.setenv(ALLOWLIST_ENV, "chicago")
    wire = fail(raw).envelope.to_wire()
    example = ERROR_EXAMPLES[code]
    assert wire["message"] == example["message"]
    assert wire["repair"]["alternative"] == example["repair"]["alternative"]
    assert wire["details"]["reason"] == example["details"]["reason"]
