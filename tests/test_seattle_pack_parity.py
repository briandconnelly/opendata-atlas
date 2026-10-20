"""Golden parity: the Seattle pack reproduces the fork's four knowledge tables.

The literals below are copied verbatim from `seattle-open-data` 26c6628
`src/seattle_open_data/constants.py` (`git show 26c6628:src/seattle_open_data/constants.py`).
Milestone 2 refactors the pack lookups; this pins what they must still return.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from opendata_atlas.core.describe import place_specs, served_evidence
from opendata_atlas.portals.loader import SEATTLE, load_portal

# --- fork tables, verbatim -------------------------------------------------------

PLACEHOLDER_VALUES = frozenset({"-", "UNKNOWN", "NULL", "OOJ", "FK ERROR", "X", "0", ""})

REGION_LAYERS: dict[str, dict[str, str]] = {
    "ru88-fbhk": {
        "kind": "neighborhood",
        "label_column": "name",
        "vintage": "SPD Micro Community Policing Plan Areas, updated 2016-03-03",
        "reliability": "ok",
    },
    "kuhn-3gp2": {
        "kind": "beat",
        "label_column": "name",
        "vintage": "SPD Beats, updated 2015-07-17 (51 beats; current SPD beats differ)",
        "reliability": "partial",
        "reason": "2015 beat boundaries; current SPD beats differ.",
    },
    "q256-3sug": {
        "kind": "zip",
        "label_column": "zcta5ce10",
        "vintage": "2010 ZIP Code Tabulation Areas (national), updated 2015-02-19",
        "reliability": "ok",
    },
    "cyqu-gs94": {
        "kind": "council_district",
        "label_column": "c_district",
        "vintage": "City Council Districts, updated 2015-07-20 (predates 2022 redistricting)",
        "reliability": "unreliable",
        "reason": "Mostly null, only districts 1-3 appear, and the boundaries predate 2022.",
    },
    "2day-rhn5": {
        "kind": "census_tract",
        "label_column": "name10",
        "vintage": "2010 Census Tracts, updated 2015-05-16",
        "reliability": "unreliable",
        "reason": "Mostly null on Seattle datasets; 2010 tracts.",
    },
}

PLACE_FIELDS: dict[str, dict[str, dict[str, str]]] = {
    "33kz-ixgy": {
        "dispatch_neighborhood": {"kind": "neighborhood", "reliability": "ok"},
        "dispatch_precinct": {"kind": "precinct", "reliability": "ok"},
        "dispatch_sector": {"kind": "sector", "reliability": "ok"},
        "dispatch_beat": {"kind": "beat", "reliability": "ok"},
    },
    "tazs-3rd5": {
        "neighborhood": {
            "kind": "neighborhood",
            "reliability": "partial",
            "reason": "Placeholder ('-') for nearly all offenses before 2017; 1-4% missing since. "
            "Do not use for 2008-2016.",
        },
        "precinct": {"kind": "precinct", "reliability": "ok"},
        "sector": {"kind": "sector", "reliability": "ok"},
        "beat": {"kind": "beat", "reliability": "ok"},
    },
    "ppi5-g2bj": {
        "precinct": {"kind": "precinct", "reliability": "ok"},
        "sector": {"kind": "sector", "reliability": "ok"},
        "beat": {"kind": "beat", "reliability": "ok"},
    },
    "76t5-zqzr": {
        "originalzip": {"kind": "zip", "reliability": "ok"},
    },
}

TIME_EVIDENCE: dict[str, dict[str, dict[str, str]]] = {
    "kzjm-xkqj": {
        "datetime": {
            "timezone": "America/Los_Angeles",
            "evidence": "max(datetime) tracked Pacific wall-clock time when probed 2026-10-15.",
        },
    },
    "33kz-ixgy": {
        "cad_event_original_time_queued": {
            "timezone": "America/Los_Angeles",
            "evidence": (
                "Spring-forward gap and local diurnal profile matched Pacific wall-clock time "
                "when probed 2026-10-16."
            ),
        },
    },
    "65db-xm6k": {
        "date": {
            "timezone": "America/Los_Angeles",
            "evidence": (
                "Empty spring-forward hour and commute peaks matched Pacific wall-clock time "
                "when probed 2026-10-16."
            ),
        },
    },
}

# ----------------------------------------------------------------------------------

PACK = load_portal(SEATTLE)
_ATTRS = ("kind", "label_column", "vintage", "reliability", "reason")


def _interp(claim: Any) -> dict[str, str]:
    assert claim is not None and claim.interpretation is not None
    values = {a: getattr(claim.interpretation, a) for a in _ATTRS}
    return {k: v for k, v in values.items() if v is not None}


@pytest.mark.parametrize("layer_id", sorted(REGION_LAYERS))
def test_region_layers_match_the_fork(layer_id):
    assert _interp(PACK.pack.region_layer(layer_id)) == REGION_LAYERS[layer_id]


def test_place_fields_match_the_fork():
    datasets = {c.scope.dataset for c in PACK.pack.claims if c.kind == "place_field"}
    assert datasets == set(PLACE_FIELDS)
    for dataset_id, fields in PLACE_FIELDS.items():
        found = {col: _interp(c) for col, c in PACK.pack.place_fields(dataset_id).items()}
        assert found == fields, dataset_id


def test_time_evidence_matches_the_fork():
    claims = {
        (c.scope.dataset, c.scope.column) for c in PACK.pack.claims if c.kind == "column_timezone"
    }
    assert claims == {(d, col) for d, cols in TIME_EVIDENCE.items() for col in cols}
    for dataset_id, cols in TIME_EVIDENCE.items():
        for column, fact in cols.items():
            claim = PACK.pack.column_timezone(dataset_id, column)
            assert claim is not None and claim.interpretation is not None
            assert claim.interpretation.timezone == fact["timezone"]
            assert served_evidence(claim.evidence) == fact["evidence"]


def test_placeholders_match_the_fork():
    # The fork applied PLACEHOLDER_VALUES to every text place field (source "column").
    for dataset_id, fields in PLACE_FIELDS.items():
        for column in fields:
            assert PACK.pack.placeholders(dataset_id, column) == PLACEHOLDER_VALUES
    assert PACK.pack.placeholders("33kz-ixgy", "not_a_place_field") == frozenset()


def _fork_place_specs(dataset_id: str, columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The fork's `place_specs` (seattle-open-data 26c6628 core/describe.py) over the tables."""
    names = {c.get("fieldName") for c in columns}
    specs: list[dict[str, Any]] = [
        {"column": name, "source": "column", **facts}
        for name, facts in PLACE_FIELDS.get(dataset_id, {}).items()
        if name in names
    ]
    for c in columns:
        region = ((c.get("computationStrategy") or {}).get("parameters") or {}).get("region")
        if not region:
            continue
        layer_id = str(region).lstrip("_")
        known = REGION_LAYERS.get(layer_id)
        specs.append(
            {
                "column": c["fieldName"],
                "source": "computed_region",
                "layer_id": layer_id,
                "kind": known["kind"] if known else "other",
                "reliability": known["reliability"] if known else "partial",
                "reason": (known or {}).get("reason")
                or (None if known else "Region layer not reviewed; check assigned_fraction."),
                "label_column": known["label_column"] if known else None,
                "vintage": known["vintage"] if known else None,
            }
        )
    return specs


def _schema(dataset_id: str) -> list[dict[str, Any]]:
    """A minimal schema: the dataset's place-field columns, one column per region layer, an
    unreviewed layer, and an unrelated column."""
    columns: list[dict[str, Any]] = [{"fieldName": c} for c in PLACE_FIELDS.get(dataset_id, {})]
    for layer_id in [*REGION_LAYERS, "zzzz-9999"]:
        columns.append(
            {
                "fieldName": f":@computed_region_{layer_id.replace('-', '_')}",
                "computationStrategy": {"parameters": {"region": f"_{layer_id}"}},
            }
        )
    columns.append({"fieldName": "unrelated"})
    return columns


@pytest.mark.parametrize("dataset_id", [*sorted(PLACE_FIELDS), "kzjm-xkqj"])
def test_place_specs_match_the_fork(dataset_id):
    columns = _schema(dataset_id)
    specs = place_specs(PACK, dataset_id, columns, today=date(2026, 10, 18))
    assert specs == _fork_place_specs(dataset_id, columns)
