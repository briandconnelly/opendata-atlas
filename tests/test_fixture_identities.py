"""No recorded fixture holds a person's name or email; the recorder scrubs before it writes."""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import httpx

from tests import http_fixtures

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "scrub_fixtures.py"
#: Recordings committed under `docs/evidence` that the guard covers like a fixture.
EVIDENCE_RECORDINGS = sorted((ROOT / "docs" / "evidence").glob("describe-budget-*/*.json"))


find_identities = http_fixtures.scrubber.find_identities
scrub = http_fixtures.scrubber.scrub


def test_guard_catches_a_synthetic_identity():
    node = {
        "owner": {"displayName": "Jane Doe", "screenName": "jdoe"},
        "body": json.dumps({"Contact Email": "jane.doe@seattle.gov"}),
    }
    assert find_identities(node) == Counter({"displayName": 1, "screenName": 1, "email": 1})


def test_scrub_replaces_names_and_emails_everywhere():
    out = scrub({"members": [{"display_name": "A B"}], "description": "mail a@b.gov now"})
    assert out == {
        "members": [{"display_name": "Fixture Person"}],
        "description": "mail redacted-email now",
    }
    assert find_identities(out) == Counter()


def test_guard_and_scrub_cover_a_metadata_contact_pair():
    node = {
        "domain_metadata": [
            {"key": "Common-Core_Contact-Name", "value": "Jane Doe"},
            {"key": "Common-Core_Publisher", "value": "City of Example"},
        ]
    }
    assert find_identities(node) == Counter({"Common-Core_Contact-Name": 1})
    out = scrub(node)
    assert out == {
        "domain_metadata": [
            {"key": "Common-Core_Contact-Name", "value": "Fixture Person"},
            {"key": "Common-Core_Publisher", "value": "City of Example"},
        ]
    }
    assert find_identities(out) == Counter()


def test_scrub_rewrites_json_inside_a_string_only_when_it_changes():
    clean = '{"a": 1}'
    assert scrub(clean) == clean
    out = scrub(json.dumps({"owner": {"screenName": "jdoe"}}))
    assert out == '{"owner":{"screenName":"Fixture Person"}}'


def test_guard_catches_synthetic_account_ids():
    node = {
        "id": "abcd-1234",
        "owner": {"id": "aaaa-0001", "members": [{"id": "aaaa-0002"}, {"id": "fixt-0003"}]},
        "tableAuthor": {"id": "aaaa-0001"},
        "approvals": [{"submitter": {"id": "aaaa-0004"}, "reviewer": {"id": "aaaa-0005"}}],
        "rowsUpdatedBy": "aaaa-0006",
        "results": [{"creator": {"id": "aaaa-0007"}, "resource": {"id": "efgh-5678"}}],
        "parent_fxf": ["ijkl-9012"],
    }
    assert find_identities(node) == Counter({"account_id": 7})


def test_scrub_maps_each_account_id_to_one_placeholder():
    node = {
        "id": "abcd-1234",
        "owner": {"id": "aaaa-0001", "members": [{"id": "aaaa-0002"}]},
        "tableAuthor": {"id": "aaaa-0001"},
        "rowsUpdatedBy": "aaaa-0002",
        "body": json.dumps({"creator": {"id": "aaaa-0001"}}),
    }
    out = scrub(node)
    assert out == {
        "id": "abcd-1234",
        "owner": {"id": "fixt-0001", "members": [{"id": "fixt-0002"}]},
        "tableAuthor": {"id": "fixt-0001"},
        "rowsUpdatedBy": "fixt-0002",
        "body": '{"creator":{"id":"fixt-0001"}}',
    }
    assert find_identities(out) == Counter()


def test_scrub_replaces_an_account_id_inside_a_profile_url():
    url = "/api/users/aaaa-0001/profile_images/LARGE"
    node = {"owner": {"id": "aaaa-0001", "profileImageUrlLarge": url}}
    assert find_identities(node) == Counter({"account_id": 2})
    out = scrub(node)
    assert out == {
        "owner": {
            "id": "fixt-0001",
            "profileImageUrlLarge": "/api/users/fixt-0001/profile_images/LARGE",
        }
    }
    assert find_identities(out) == Counter()


def test_scrub_numbers_new_account_ids_after_existing_placeholders():
    node = {"owner": {"id": "fixt-0007"}, "tableAuthor": {"id": "aaaa-0001"}}
    assert scrub(node) == {"owner": {"id": "fixt-0007"}, "tableAuthor": {"id": "fixt-0008"}}


def test_restoring_one_account_id_in_a_fixture_fails_the_guard():
    path = ROOT / "tests" / "fixtures" / "http" / "describe_crime_full.json"
    data = json.loads(path.read_text())
    view = next(entry["body"] for key, entry in data.items() if "/api/views/" in key)
    view["owner"]["id"] = "aaaa-0001"
    assert find_identities(data) == Counter({"account_id": 1})


def test_no_evidence_recording_holds_an_identity():
    assert EVIDENCE_RECORDINGS, "the describe-budget recording moved; point the guard at it"
    found = {p.name: find_identities(json.loads(p.read_text())) for p in EVIDENCE_RECORDINGS}
    assert {k: v for k, v in found.items() if v} == {}


def test_no_fixture_holds_an_identity():
    found = {
        p.name: find_identities(json.loads(p.read_text()))
        for p in (ROOT / "tests" / "fixtures").rglob("*.json")
    }
    assert {k: v for k, v in found.items() if v} == {}


def test_check_cli_fails_on_an_identity_and_passes_when_clean(tmp_path):
    dirty = tmp_path / "dirty.json"
    dirty.write_text(json.dumps({"owner": {"displayName": "Jane Doe"}}))
    check = [sys.executable, str(SCRIPT), "--check", str(tmp_path)]
    assert subprocess.run(check, check=False, capture_output=True).returncode == 1
    subprocess.run([sys.executable, str(SCRIPT), str(tmp_path)], check=True, capture_output=True)
    assert subprocess.run(check, check=False, capture_output=True).returncode == 0


async def test_recorder_save_scrubs(tmp_path, monkeypatch):
    monkeypatch.setattr(http_fixtures, "FIXTURES", tmp_path)
    body = {
        "owner": {"displayName": "Jane Doe", "id": "aaaa-0001"},
        "description": "write jane.doe@seattle.gov",
    }
    recorder = http_fixtures.Recorder("scrubbed")
    live = httpx.MockTransport(lambda request: httpx.Response(200, json=body))
    monkeypatch.setattr(recorder, "_live", live)
    await recorder.handle_async_request(httpx.Request("GET", "https://example.test/api/x"))
    assert find_identities(recorder.entries) == Counter(
        {"displayName": 1, "email": 1, "account_id": 1}
    )
    recorder.save()
    path = tmp_path / "scrubbed.json"
    assert find_identities(json.loads(path.read_text())) == Counter()


async def test_recorder_numbers_account_ids_after_every_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(http_fixtures, "FIXTURES", tmp_path)
    other = {"k": {"body": {"owner": {"id": "fixt-0005"}}, "headers": {}, "status": 200}}
    (tmp_path / "other.json").write_text(json.dumps(other))
    recorder = http_fixtures.Recorder("new")
    body = {"owner": {"id": "aaaa-0001"}}
    monkeypatch.setattr(
        recorder, "_live", httpx.MockTransport(lambda r: httpx.Response(200, json=body))
    )
    await recorder.handle_async_request(httpx.Request("GET", "https://example.test/api/x"))
    recorder.save()
    saved = json.loads((tmp_path / "new.json").read_text())
    assert [entry["body"]["owner"]["id"] for entry in saved.values()] == ["fixt-0006"]


async def test_a_recorded_request_with_an_email_in_its_key_still_replays(tmp_path, monkeypatch):
    monkeypatch.setattr(http_fixtures, "FIXTURES", tmp_path)
    url = "https://example.test/resource/abcd-1234.json"
    params = {"$where": "contact_email = 'jane.doe@seattle.gov'"}
    recorder = http_fixtures.Recorder("email_key")
    live = httpx.MockTransport(lambda request: httpx.Response(200, json=[{"n": 1}]))
    monkeypatch.setattr(recorder, "_live", live)
    await recorder.handle_async_request(httpx.Request("GET", url, params=params))
    recorder.save()
    assert find_identities(json.loads((tmp_path / "email_key.json").read_text())) == Counter()
    replay = http_fixtures.Replay("email_key")
    response = await replay.handle_async_request(httpx.Request("GET", url, params=params))
    assert response.json() == [{"n": 1}]
