import shutil
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from opendata_atlas.core.context import local_now, make_source
from opendata_atlas.portals.loader import SEATTLE, PackError, load_portal
from opendata_atlas.portals.model import (
    Claim,
    Interpretation,
    ManualObservation,
    PortalIdentity,
    Scope,
)
from tests.conftest import SEATTLE_IDENTITY_DICT, with_extra_claim, with_identity


def test_seattle_identity_loads():
    ctx = load_portal(SEATTLE)
    assert ctx.id == "data.seattle.gov"
    assert ctx.identity.aliases == ["seattle"]
    assert ctx.identity.tier == "curated"
    assert ctx.identity.catalog_query == {
        "domains": "cos-data.seattle.gov",
        "search_context": "data.seattle.gov",
    }
    assert ctx.identity.catalog_domain == "cos-data.seattle.gov"
    assert str(ctx.tz) == "America/Los_Angeles"


def test_interpretation_requires_reviewer():
    with pytest.raises(ValidationError):
        Claim(
            id="x",
            kind="place_field",
            scope=Scope(dataset="aaaa-bbbb", column="c"),
            interpretation=Interpretation(reliability="ok"),
            evidence=[
                ManualObservation(
                    kind="manual_observation", note="n", observed_at=date(2026, 10, 17)
                )
            ],
            assertion=[],
        )


def test_bad_timezone_and_alias_rejected():
    for bad in ({"timezone": "Pacific/Nowhere"}, {"aliases": ["Seattle WA"]}):
        with pytest.raises(ValidationError):
            PortalIdentity.model_validate(SEATTLE_IDENTITY_DICT | bad)


def _claim(evidence, assertion=()):
    return Claim.model_validate(
        {
            "id": "c",
            "kind": "placeholder_share",
            "scope": {"dataset": "aaaa-bbbb", "column": "c"},
            "evidence": evidence,
            "assertion": list(assertion),
        }
    )


_DOC = {"kind": "document", "url": "u", "quote": "q", "observed_at": "2026-10-17"}
_PROBE = {
    "kind": "soql_probe",
    "query": "SELECT 1",
    "observed_at": "2026-10-17",
    "observation": "o",
}
_ASSERT = {"checker": "value_present", "params": {"column": "c", "value": "v"}}


def test_assertions_require_probe_evidence():
    with pytest.raises(ValidationError, match="probe"):
        _claim([_DOC], [_ASSERT])
    assert _claim([_DOC, _PROBE], [_ASSERT]).assertion


def test_interpretation_timezone_validated():
    with pytest.raises(ValidationError):
        Interpretation(timezone="Pacific/Nowhere")
    assert Interpretation(timezone="America/Los_Angeles").timezone


NOW = datetime(2026, 10, 17, 19, 0, tzinfo=UTC)


def test_null_timezone_gives_reason_not_utc():
    ctx = with_identity(load_portal(SEATTLE), timezone=None)
    assert local_now(ctx, NOW) == (None, "unknown")
    state = with_identity(ctx, jurisdiction={"level": "state", "country": "US", "region": "TX"})
    assert local_now(state, NOW) == (None, "multi_zone")


def test_seattle_local_now_is_pacific_wall_clock():
    # Same format as the fork's make_source: isoformat(timespec="seconds") on an aware datetime.
    assert local_now(load_portal(SEATTLE), NOW) == ("2026-10-17T12:00:00-07:00", None)


def test_make_source_uses_the_portal_zone():
    source = make_source(load_portal(SEATTLE))
    assert source.now_local is not None
    assert source.now_local.endswith(("-07:00", "-08:00"))


def test_source_echoes_the_portal():
    source = make_source(load_portal(SEATTLE))
    assert source.portal is not None
    assert source.portal.id == "data.seattle.gov"
    assert source.portal.alias == "seattle"
    assert source.portal.name == "City of Seattle"
    assert source.portal.tier == "curated"
    assert source.portal.timezone == "America/Los_Angeles"
    assert source.now_local_reason is None


def test_null_timezone_portal_gets_null_now_local_with_reason():
    state = with_identity(
        load_portal(SEATTLE),
        timezone=None,
        aliases=[],
        jurisdiction={"level": "state", "country": "US", "region": "TX"},
    )
    source = make_source(state)
    assert source.now_local is None
    assert source.now_local_reason == "multi_zone"
    assert source.portal is not None
    assert source.portal.timezone is None
    assert source.portal.alias is None
    unknown = make_source(with_identity(load_portal(SEATTLE), timezone=None, jurisdiction=None))
    assert unknown.now_local_reason == "unknown"


def test_portal_independent_source_has_no_portal():
    source = make_source(None)
    assert source.portal is None
    assert source.now_local is None
    assert source.now_local_reason is None
    assert set(source.model_dump(exclude_none=True)) == {"request_id"}


def test_seattle_source_carries_the_local_weekday():
    source = make_source(load_portal(SEATTLE), now=NOW)
    assert source.now_local == "2026-10-17T12:00:00-07:00"
    assert source.now_weekday == "Saturday"


def test_weekday_is_the_portal_local_day():
    # Sunday 03:00 UTC is still Saturday evening in Seattle.
    late = datetime(2026, 10, 18, 3, 0, tzinfo=UTC)
    source = make_source(load_portal(SEATTLE), now=late)
    assert source.now_local == "2026-10-17T20:00:00-07:00"
    assert source.now_weekday == "Saturday"


def test_weekday_ahead_of_utc_in_a_positive_offset_zone():
    # Saturday 19:00 UTC is already Sunday morning in Tokyo (UTC+9).
    tokyo = with_identity(load_portal(SEATTLE), timezone="Asia/Tokyo")
    source = make_source(tokyo, now=NOW)
    assert NOW.weekday() == 5
    assert source.now_local == "2026-10-18T04:00:00+09:00"
    assert source.now_weekday == "Sunday"


def test_weekday_absent_without_now_local():
    multi_zone = with_identity(
        load_portal(SEATTLE),
        timezone=None,
        jurisdiction={"level": "state", "country": "US", "region": "TX"},
    )
    unknown = with_identity(load_portal(SEATTLE), timezone=None, jurisdiction=None)
    for portal in (multi_zone, unknown):
        source = make_source(portal, now=NOW)
        assert source.now_local is None
        assert source.now_weekday is None
    assert make_source(None, now=NOW).now_weekday is None


def test_with_extra_claim_adds_a_valid_place_field():
    ctx = with_extra_claim(
        load_portal(SEATTLE), dataset="abcd-1234", column="hood", reliability="partial"
    )
    claim = ctx.pack.place_fields("abcd-1234")["hood"]
    assert claim.interpretation is not None
    assert claim.interpretation.reliability == "partial"
    assert len(ctx.pack.claims) == len(load_portal(SEATTLE).pack.claims) + 1


# Claims the engine cannot serve fail at load, not at first describe (final review, item 4).


def _reviewed(kind, scope, interpretation):
    return {
        "id": "c",
        "kind": kind,
        "scope": scope,
        "interpretation": interpretation,
        "reviewed_by": "test",
        "reviewed_at": "2026-10-17",
        "evidence": [_DOC],
    }


_PLACE = ("place_field", {"dataset": "aaaa-bbbb", "column": "c"})
_REGION = ("region_layer", {"layer": "aaaa-bbbb"})


@pytest.mark.parametrize(("kind", "scope"), [_PLACE, _REGION])
def test_place_claims_require_a_place_kind(kind, scope):
    base = {"reliability": "ok", "label_column": "name"}
    for bad in ({"kind": "planet"}, {}):
        with pytest.raises(ValidationError, match=r"interpretation\.kind"):
            Claim.model_validate(_reviewed(kind, scope, base | bad))
    assert Claim.model_validate(_reviewed(kind, scope, base | {"kind": "beat"}))


@pytest.mark.parametrize(("kind", "scope"), [_PLACE, _REGION])
def test_place_claims_require_reliability(kind, scope):
    with pytest.raises(ValidationError, match=r"interpretation\.reliability"):
        Claim.model_validate(_reviewed(kind, scope, {"kind": "beat", "label_column": "name"}))


def test_region_layer_requires_label_column():
    with pytest.raises(ValidationError, match=r"interpretation\.label_column"):
        Claim.model_validate(_reviewed(*_REGION, {"kind": "beat", "reliability": "ok"}))


def test_column_timezone_requires_timezone():
    scope = {"dataset": "aaaa-bbbb", "column": "c"}
    with pytest.raises(ValidationError, match=r"interpretation\.timezone"):
        Claim.model_validate(_reviewed("column_timezone", scope, {"reason": "r"}))
    tz = {"timezone": "America/Los_Angeles"}
    assert Claim.model_validate(_reviewed("column_timezone", scope, tz))


def test_unservable_claim_fails_load_portal_naming_file_and_field(tmp_path):
    d = tmp_path / "p"
    shutil.copytree(SEATTLE, d)
    (d / "facts" / "aaaa-bbbb.toml").write_text(
        '[[claim]]\nid = "bad-layer"\nkind = "region_layer"\nscope = {layer = "aaaa-bbbb"}\n'
        'interpretation = {kind = "beat", reliability = "ok"}\n'
        'reviewed_by = "test"\nreviewed_at = 2026-10-17\n\n'
        '[[claim.evidence]]\nkind = "manual_observation"\nnote = "n"\nobserved_at = 2026-10-17\n'
    )
    with pytest.raises(PackError, match=r"aaaa-bbbb\.toml.*interpretation\.label_column"):
        load_portal(d)
    assert load_portal(SEATTLE).pack.region_layer("ru88-fbhk") is not None
