"""Offline: the live compatibility suite's evidence keeps no personal data (ruling 25)."""

from __future__ import annotations

import json

from tests.test_compat_live import _saved_body

# Synthetic values only; none is a real person.
NAME = "Zzyzx Qwertyson"
ADDRESS = "1234 Imaginary Lane"
EMAIL = "zzyzx.q@example.com"
PHONES = ["(555) 010-4477", "555-010-4478", "555.010.4479"]

VIEW = {
    "id": "abcd-1234",
    "name": "Permits",
    "description": f"Questions: {EMAIL} or {PHONES[0]}.",
    "owner": {"id": "aaaa-0001", "displayName": NAME, "screenName": NAME},
    "tableAuthor": {"id": "aaaa-0002", "displayName": NAME, "screenName": NAME},
    "approvals": [{"submitter": {"id": "aaaa-0003", "displayName": NAME}}],
    "rowsUpdatedBy": "aaaa-0004",
    "metadata": {
        "custom_fields": {
            "Contact Information": {"Contact Name": NAME, "Telephone": PHONES[1]},
            "Point of Contact": {"Contact Email": EMAIL},
            "Dataset Information": {"Agency": "Department of Permits"},
        }
    },
    "columns": [
        {
            "fieldName": "applicant_name",
            "dataTypeName": "text",
            "cachedContents": {
                "null": "3",
                "not_null": "97",
                "non_null": "97",
                "cardinality": "40",
                "count": "100",
                "top": [{"item": NAME, "count": "5"}, {"item": PHONES[2], "count": "2"}],
                "largest": ADDRESS,
                "smallest": EMAIL,
                "average": "12",
                "sum": "1200",
            },
        }
    ],
}
CATALOG = {
    "results": [
        {
            "resource": {"id": "abcd-1234", "name": "Permits", "contact_email": EMAIL},
            "owner": {"id": "aaaa-0001", "user_type": "interactive", "display_name": NAME},
            "creator": {"id": "aaaa-0001", "display_name": NAME},
        }
    ],
    "resultSetSize": 1,
}


POSTCODE = "ZZ9 9ZZ"
#: A UK-style number the phone pattern does not catch; only the key can redact it.
UK_PHONE = "0000 000 0000"
#: Discovery `classification.domain_metadata`: a list of `{key, value}` objects.
METADATA_ITEMS = [
    {"key": "Common-Core_Contact-Name", "value": NAME},
    {"key": "Common-Core_Contact-Email", "value": EMAIL},
    {"key": "Dataset-Summary_Dataset-Owner", "value": NAME},
    {"key": "Point-of-Contact_Address", "value": ADDRESS},
    {"key": "Point-of-Contact_Postcode", "value": POSTCODE},
    {"key": "Point-of-Contact_Telephone", "value": UK_PHONE},
    {"key": "point_of_contact_author", "value": NAME},
    {"key": "Point-of-Contact_Directorate", "value": "Directorate of Permits"},
]
DOMAIN_METADATA = {
    "results": [
        {
            "resource": {"id": "abcd-1234", "name": "Permits"},
            "classification": {"domain_metadata": METADATA_ITEMS},
        }
    ],
    "resultSetSize": 1,
}


def _text(step: str, body: dict) -> str:
    return json.dumps(_saved_body(step, json.dumps(body).encode()))


def test_view_body_keeps_no_personal_data():
    saved = _text("describe", VIEW)
    for value in [NAME, ADDRESS, EMAIL, *PHONES]:
        assert value not in saved
    for key in ("top", "largest", "smallest", "average", "sum", "screenName", "displayName"):
        assert f'"{key}"' not in saved
    column = json.loads(saved)["columns"][0]
    assert column["cachedContents"] == {
        "null": "3",
        "not_null": "97",
        "non_null": "97",
        "cardinality": "40",
        "count": "100",
    }
    assert json.loads(saved)["owner"] == "<identity redacted>"
    assert "Department of Permits" in saved  # agency metadata survives


def test_catalog_body_keeps_no_personal_data():
    saved = _text("search", CATALOG)
    for value in [NAME, EMAIL]:
        assert value not in saved
    assert json.loads(saved)["resultSetSize"] == 1


def test_large_view_summary_keeps_no_personal_data():
    big = {**VIEW, "padding": "x" * 70_000}
    saved = _text("describe", big)
    for value in [NAME, ADDRESS, EMAIL, *PHONES]:
        assert value not in saved


def test_query_rows_stay_reduced():
    saved = json.loads(_text("query_p1", [{"applicant_name": NAME, "phone": PHONES[1]}]))  # ty: ignore[invalid-argument-type]
    assert saved["row_count"] == 1 and saved["keys"] == ["applicant_name", "phone"]


def test_domain_metadata_key_value_list_keeps_no_personal_data():
    saved = _text("search", DOMAIN_METADATA)
    for value in [NAME, ADDRESS, EMAIL, POSTCODE, UK_PHONE]:
        assert value not in saved
    items = json.loads(saved)["results"][0]["classification"]["domain_metadata"]
    assert [i["key"] for i in items] == [i["key"] for i in METADATA_ITEMS]
    assert {i["value"] for i in items[:-1]} == {"<identity redacted>"}
    assert items[-1]["value"] == "Directorate of Permits"  # not an identity key
