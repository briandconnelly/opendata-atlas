"""Typed checkers over literal rows (docs/design.md: Fact model)."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from opendata_atlas.portals.checkers import (
    CHECKERS,
    DiurnalPeak,
    DstGap,
    MetadataBefore,
    MetadataEquals,
    ShareByGroup,
    ValueAbsent,
    ValuePresent,
    run_check,
)

YEARS = [{"y": str(y), "ph": "98", "n": "100"} for y in range(2008, 2017)]
SHARE = ShareByGroup(
    group="y", numerator="ph", denominator="n", where="y <= 2016", min=0.9, min_groups=9
)


def test_share_passed():
    assert run_check("share_by_group", SHARE, YEARS).outcome == "passed"


def test_share_too_few_groups_is_inconclusive():
    assert run_check("share_by_group", SHARE, YEARS[:8]).outcome == "inconclusive"


def test_share_contradicted_names_the_group():
    rows = [dict(r) for r in YEARS]
    rows[3]["ph"] = "50"
    result = run_check("share_by_group", SHARE, rows)
    assert result.outcome == "contradicted"
    assert "2011" in result.detail


def test_share_where_filters_rows():
    rows = [*YEARS, {"y": "2020", "ph": "1", "n": "100"}]
    assert run_check("share_by_group", SHARE, rows).outcome == "passed"


def test_share_max_bound():
    p = ShareByGroup(numerator="ph", denominator="n", max=0.05)
    assert run_check("share_by_group", p, [{"ph": "1", "n": "100"}]).outcome == "passed"
    assert run_check("share_by_group", p, [{"ph": "9", "n": "100"}]).outcome == "contradicted"


def test_missing_fields_are_not_groups():
    p = ShareByGroup(group="y", numerator="ph", denominator="n", min=0.5)
    rows = [{"y": "2008", "n": "100"}, {"y": "2009", "ph": "x", "n": "100"}]
    assert run_check("share_by_group", p, rows).outcome == "inconclusive"
    zero = [{"y": "2008", "ph": "0", "n": "0"}]
    assert run_check("share_by_group", p, zero).outcome == "inconclusive"


def test_share_needs_a_bound():
    with pytest.raises(ValidationError):
        ShareByGroup(numerator="ph", denominator="n")


def test_empty_result_is_inconclusive_for_every_soql_checker():
    params = {
        "share_by_group": SHARE,
        "value_present": ValuePresent(column="c", value="v"),
        "value_absent": ValueAbsent(column="c", value="v"),
        "dst_gap": DstGap(),
        "diurnal_peak": DiurnalPeak(peak_from=9, peak_to=17),
    }
    soql = [name for name, (_, kind) in CHECKERS.items() if kind == "soql_probe"]
    assert set(soql) == set(params)
    for name in soql:
        assert run_check(name, params[name], []).outcome == "inconclusive", name


def test_value_present_and_absent():
    rows = [{"c": "-", "n": "3"}, {"c": "x", "n": "0"}]
    present = ValuePresent(column="c", value="-")
    assert run_check("value_present", present, rows).outcome == "passed"
    missing = ValuePresent(column="c", value="zz")
    assert run_check("value_present", missing, rows).outcome == "contradicted"
    counted = ValuePresent(column="c", value="x", count="n", min_count=1)
    assert run_check("value_present", counted, rows).outcome == "contradicted"
    assert run_check("value_absent", ValueAbsent(column="c", value="zz"), rows).outcome == "passed"
    hit = run_check("value_absent", ValueAbsent(column="c", value="x"), rows)
    assert hit.outcome == "contradicted"
    assert "x" in hit.detail


def _hours(counts: dict[int, int]) -> list[dict[str, str]]:
    return [{"h": str(h), "n": str(n)} for h, n in counts.items()]


def test_dst_gap():
    p = DstGap()
    assert run_check("dst_gap", p, _hours({1: 50, 3: 50})).outcome == "passed"
    assert run_check("dst_gap", p, _hours({1: 50, 2: 5, 3: 50})).outcome == "contradicted"
    assert run_check("dst_gap", p, _hours({2: 0, 3: 50})).outcome == "inconclusive"
    assert run_check("dst_gap", DstGap(max_gap_rows=5), _hours({1: 9, 2: 5, 3: 9})).outcome == (
        "passed"
    )


def test_diurnal_peak_ties_take_the_earliest_hour():
    rows = _hours({h: 10 for h in range(24)})
    early = DiurnalPeak(peak_from=0, peak_to=0)
    assert run_check("diurnal_peak", early, rows).outcome == "passed"
    late = DiurnalPeak(peak_from=1, peak_to=23)
    assert run_check("diurnal_peak", late, rows).outcome == "contradicted"


def test_diurnal_peak_inconclusive_when_thin():
    p = DiurnalPeak(peak_from=9, peak_to=17)
    assert run_check("diurnal_peak", p, _hours({12: 500})).outcome == "inconclusive"
    assert run_check("diurnal_peak", p, _hours({h: 1 for h in range(24)})).outcome == (
        "inconclusive"
    )


def test_diurnal_peak_params_order():
    with pytest.raises(ValidationError):
        DiurnalPeak(peak_from=9, peak_to=3)


def test_metadata_before_reads_epoch_and_iso():
    p = MetadataBefore(field="rowsUpdatedAt", before=date(2016, 1, 1))
    assert run_check("metadata_before", p, {"rowsUpdatedAt": 1437350400}).outcome == "passed"
    iso = {"rowsUpdatedAt": "2015-07-20T00:00:00Z"}
    assert run_check("metadata_before", p, iso).outcome == "passed"
    assert run_check("metadata_before", p, {"rowsUpdatedAt": "2016-02-01"}).outcome == (
        "contradicted"
    )
    assert run_check("metadata_before", p, {"rowsUpdatedAt": "soon"}).outcome == "inconclusive"
    assert run_check("metadata_before", p, {}).outcome == "inconclusive"


def test_metadata_equals_dotted_path():
    p = MetadataEquals(field="a.b", value="x")
    assert run_check("metadata_equals", p, {"a": {"b": "x"}}).outcome == "passed"
    assert run_check("metadata_equals", p, {"a": {"b": "y"}}).outcome == "contradicted"
    assert run_check("metadata_equals", p, {"a": 1}).outcome == "inconclusive"
    flag = MetadataEquals(field="f", value=True)
    assert run_check("metadata_equals", flag, {"f": 1}).outcome == "contradicted"


def test_wrong_data_type_is_inconclusive():
    assert run_check("share_by_group", SHARE, {"a": 1}).outcome == "inconclusive"
    meta = MetadataEquals(field="f", value=1)
    assert run_check("metadata_equals", meta, [{"f": 1}]).outcome == "inconclusive"


def test_params_reject_unknown_keys():
    with pytest.raises(ValidationError):
        ShareByGroup(numerator="a", denominator="b", min=0.5, foo=1)  # ty: ignore[unknown-argument]


def test_where_rejects_soql():
    with pytest.raises(ValidationError):
        ShareByGroup(numerator="a", denominator="b", min=0.5, where="y <= 2016 OR 1=1")


def test_unparseable_counts_are_inconclusive_not_decisive():
    gap = DstGap()
    rows = [{"h": "1", "n": "50"}, {"h": "2", "n": "x"}, {"h": "3", "n": "50"}]
    assert run_check("dst_gap", gap, rows).outcome == "inconclusive"
    counted = ValuePresent(column="c", value="x", count="n")
    assert run_check("value_present", counted, [{"c": "x", "n": "?"}]).outcome == "inconclusive"


def test_metadata_before_date_strings_and_offsets():
    p = MetadataBefore(field="d", before=date(2016, 1, 1))
    early = MetadataBefore(field="d", before=date(2015, 1, 1))
    # "20151020" is an ISO basic date (2015-10-20), not epoch seconds in 1970.
    assert run_check("metadata_before", early, {"d": "20151020"}).outcome == "contradicted"
    assert run_check("metadata_before", p, {"d": "1437350400"}).outcome == "passed"
    # 2015-12-31T20:00-08:00 is 2016-01-01T04:00Z: not before 2016-01-01 in UTC.
    late = {"d": "2015-12-31T20:00:00-08:00"}
    assert run_check("metadata_before", p, late).outcome == "contradicted"


@pytest.mark.parametrize(
    ("model", "kwargs"),
    [
        (ValuePresent, {"column": "c", "value": "v", "min_count": 0}),
        (DstGap, {"min_neighbor_rows": -1}),
        (DstGap, {"max_gap_rows": -1}),
        (DiurnalPeak, {"peak_from": 1, "peak_to": 2, "min_hours": 0}),
        (DiurnalPeak, {"peak_from": 1, "peak_to": 2, "min_hours": 25}),
        (DiurnalPeak, {"peak_from": 1, "peak_to": 2, "min_rows": 0}),
    ],
)
def test_count_bounds_rejected(model, kwargs):
    with pytest.raises(ValidationError):
        model(**kwargs)
