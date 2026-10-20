"""Ruling 62: a reviewed place_field claim on a computed-region column replaces that column's
structural entry in `place_fields`; it never adds a second one (design: computed-region
columns take their layer label and kind from claims when present)."""

from __future__ import annotations

from datetime import date

from opendata_atlas.core.describe import place_specs
from tests.conftest import SEATTLE_CONTEXT, with_extra_claim

TODAY = date(2026, 10, 18)
COLUMN = ":@computed_region_ru88_fbhk"


def _region_column(layer: str) -> dict:
    return {"fieldName": COLUMN, "computationStrategy": {"parameters": {"region": f"_{layer}"}}}


def test_layer_claim_alone_gives_one_entry():
    """Known baseline: Seattle's reviewed ru88-fbhk layer, no column claim."""
    specs = place_specs(SEATTLE_CONTEXT, "kzjm-xkqj", [_region_column("ru88-fbhk")], today=TODAY)
    assert [(s["column"], s["source"]) for s in specs] == [(COLUMN, "computed_region")]


def test_column_claim_on_a_computed_region_replaces_the_entry():
    ctx = with_extra_claim(
        SEATTLE_CONTEXT, dataset="kzjm-xkqj", column=COLUMN, reliability="partial"
    )
    specs = place_specs(ctx, "kzjm-xkqj", [_region_column("ru88-fbhk")], today=TODAY)
    assert len(specs) == 1, specs
    (spec,) = specs
    assert spec["source"] == "computed_region"
    assert spec["layer_id"] == "ru88-fbhk"
    # The dataset's own claim decides kind and reliability; the layer keeps its label column.
    assert (spec["kind"], spec["reliability"]) == ("neighborhood", "partial")
    assert spec["label_column"] == "name"


def test_column_claim_on_an_unreviewed_layer_replaces_the_default():
    ctx = with_extra_claim(SEATTLE_CONTEXT, dataset="kzjm-xkqj", column=COLUMN, reliability="ok")
    specs = place_specs(ctx, "kzjm-xkqj", [_region_column("zzzz-zzzz")], today=TODAY)
    assert len(specs) == 1, specs
    (spec,) = specs
    assert (spec["source"], spec["layer_id"]) == ("computed_region", "zzzz-zzzz")
    assert (spec["kind"], spec["reliability"]) == ("neighborhood", "ok")
    assert spec["reason"] != "Region layer not reviewed; check assigned_fraction."
    assert spec["label_column"] is None
