"""Upstream SODA2 failures map onto the error taxonomy (docs/design.md: Errors).

Covers every query.soql.* variant.
"""

from __future__ import annotations

from typing import Any

import pytest

from opendata_atlas.core.errors import map_upstream_error

PORTAL = {"portal_id": "data.seattle.gov", "portal_name": "City of Seattle"}


def mapped(status: int, body: Any = None, headers: Any = None, **kwargs: Any) -> dict[str, Any]:
    return map_upstream_error(status, body, headers, **kwargs).envelope.to_wire()


def test_no_such_column_with_position():
    body = {
        "code": "query.soql.no-such-column",
        "error": True,
        "message": "No such column: foo",
        "data": {"column": "foo", "position": {"line": 1, "column": 8, "row": 1}},
    }
    err = mapped(400, body, dataset_id="kzjm-xkqj", **PORTAL)
    assert err["code"] == "no_such_column"
    assert err["details"]["position"] == {"line": 1, "column": 8, "row": 1}
    assert err["repair"] == {
        "next_step": "inspect_columns",
        "tool": "atlas_describe_dataset",
        "arguments": {"portal": "data.seattle.gov", "dataset_id": "kzjm-xkqj", "detail": "full"},
    }
    assert "foo" not in err["message"], "upstream text is not echoed"


def test_code_only_in_message_text():
    body = {"message": "Query coordinator error: query.soql.no-such-column; No such column: x"}
    assert mapped(400, body, dataset_id="kzjm-xkqj")["code"] == "no_such_column"


def test_type_mismatch_is_syntax_error_with_position():
    body = {
        "errorCode": "query.soql.type-mismatch",
        "message": "Type mismatch",
        "data": {"position": {"line": 1, "column": 22}},
    }
    err = mapped(400, body)
    assert err["code"] == "soql_syntax_error"
    assert err["details"]["upstream_code"] == "query.soql.type-mismatch"
    assert err["details"]["position"] == {"line": 1, "column": 22}


def test_invalid_without_position():
    err = mapped(400, {"code": "query.soql.invalid", "data": {}})
    assert err["code"] == "soql_syntax_error"
    assert "position" not in err["details"]
    assert err["repair"]["arguments"] == {"topic": "soql", "item_id": "syntax"}


def test_rejected_token_only_when_configured():
    body = {"code": "permission_denied", "message": "Invalid app_token specified"}
    assert mapped(403, body, token_configured=True)["code"] == "app_token_rejected"
    assert mapped(403, body, token_configured=False)["code"] == "upstream_forbidden"


def test_generic_forbidden():
    err = mapped(403, {"code": "permission_denied", "message": "Forbidden"}, token_configured=True)
    assert err["code"] == "upstream_forbidden"
    assert "repair" not in err


def test_rate_limited_reads_retry_after():
    err = mapped(429, {}, {"Retry-After": "12"})
    assert err["code"] == "rate_limited"
    assert err["temporary"] is True
    assert err["retry_after_ms"] == 12_000


def test_rate_limited_has_no_repair():
    """temporary=true already means retry unchanged; a retry repair would echo caller text."""
    assert "repair" not in mapped(429, {}, {"Retry-After": "3"})


def test_rate_limited_without_header():
    err = mapped(429)
    assert err["temporary"] is True
    assert err["retry_after_ms"] is None


def test_server_error_is_temporary():
    err = mapped(503)
    assert err["code"] == "upstream_unavailable"
    assert err["temporary"] is True


def test_not_found_points_to_search():
    err = mapped(404, {"code": "not_found"}, dataset_id="abcd-1234", **PORTAL)
    assert err["code"] == "dataset_not_found"
    assert err["details"]["field"] == "dataset_id"
    assert err["repair"]["tool"] == "atlas_search_datasets"
    assert err["repair"]["arguments"] == {"portal": "data.seattle.gov"}


def test_repairs_that_call_a_data_tool_need_the_portal():
    """Without a portal there is no literal data-tool call, so no repair."""
    assert "repair" not in mapped(404, {}, dataset_id="abcd-1234")
    assert "repair" not in mapped(400, {"code": "query.soql.no-such-column"}, dataset_id="x")


def test_non_temporary_never_carries_delay():
    err = mapped(403, {}, {"Retry-After": "5"})
    assert err["temporary"] is False
    assert err["retry_after_ms"] is None


@pytest.mark.parametrize(
    ("status", "body", "headers", "expected", "temporary", "delay"),
    [
        (
            429,
            {"errorCode": "query.soql.type-mismatch"},
            {"Retry-After": "7"},
            "rate_limited",
            True,
            7000,
        ),
        (503, {"code": "query.soql.no-such-column"}, {}, "upstream_unavailable", True, None),
        (
            403,
            {"message": "Invalid app_token specified: query.soql.x"},
            {},
            "app_token_rejected",
            False,
            None,
        ),
    ],
)
def test_http_status_wins_over_soql_code(status, body, headers, expected, temporary, delay):
    err = mapped(status, body, headers, token_configured=True)
    assert err["code"] == expected
    assert err["temporary"] is temporary
    assert err["retry_after_ms"] == delay


@pytest.mark.parametrize("status", [302, 404])
def test_soql_diagnostics_only_apply_to_query_rejections(status):
    assert mapped(status, {"code": "query.soql.no-such-column"})["code"] != "no_such_column"


@pytest.mark.parametrize("endpoint", ["views", "catalog"])
def test_soql_diagnostics_only_apply_to_resource_endpoint(endpoint):
    err = mapped(400, {"code": "query.soql.no-such-column"}, endpoint=endpoint)
    assert err["code"] == "invalid_argument"


def test_message_code_is_bounded():
    err = mapped(400, {"message": "query.soql." + "a" * 3000})
    assert err["code"] == "invalid_argument"
    assert "upstream_code" not in err["details"]


@pytest.mark.parametrize("value", ["²", "\u0661", "9" * 5000])
def test_malformed_optional_numbers_are_ignored(value):
    err = mapped(
        400,
        {"code": "query.soql.invalid", "position": {"line": value, "column": "8"}},
    )
    assert err["code"] == "soql_syntax_error"
    assert err["details"]["position"] == {"column": 8}
    limited = mapped(429, headers={"Retry-After": value})
    assert limited["code"] == "rate_limited"
    assert limited["retry_after_ms"] is None
