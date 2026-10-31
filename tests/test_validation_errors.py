"""Bound framework diagnostics independently of the tool surface."""

from opendata_atlas.core.errors import from_validation_errors


def test_validation_fields_are_bounded():
    errors = [{"loc": (f"field_{i}",), "msg": "invalid"} for i in range(25)]
    envelope = from_validation_errors(errors, tool="atlas_query_dataset").envelope
    assert envelope.details is not None
    assert envelope.details.field is None
    assert envelope.details.fields == [f"field_{i}" for i in range(20)]
    assert "5 fields omitted" in envelope.details.reason
    assert len(envelope.details.reason) <= 500


def test_overlong_validation_path_is_omitted():
    errors = [{"loc": ("x" * 1000,), "msg": "invalid"}]
    details = from_validation_errors(errors, tool="atlas_query_dataset").envelope.details
    assert details is not None
    assert details.field is None and details.fields is None
    assert "1 fields omitted" in details.reason
    assert "x" * 129 not in details.reason


def test_dataset_validation_without_portal_has_no_repair():
    errors = [{"loc": ("dataset_id",), "msg": "invalid"}]
    assert from_validation_errors(errors, tool="atlas_query_dataset").envelope.repair is None
