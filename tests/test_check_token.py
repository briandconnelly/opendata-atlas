"""Offline tests for the dev-only app-token probe's outcome classes."""

import importlib.util
import sys
from pathlib import Path

import httpx
import pytest

PROBES = Path(__file__).resolve().parent.parent / "scripts" / "feasibility"
URL = "https://data.example.gov/resource/abcd-1234.json"
SECRET = "s3cret-token-value"


def _load():
    sys.path.insert(0, str(PROBES))
    try:
        spec = importlib.util.spec_from_file_location("check_token", PROBES / "check_token.py")
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(PROBES))


check_token = _load()


def _probe(handler) -> str:
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        return check_token.probe(client, URL, SECRET)


def test_check_token_classifies_rejection():
    seen = {}

    def rejected(request: httpx.Request) -> httpx.Response:
        seen["token"] = request.headers.get("x-app-token")
        return httpx.Response(
            403, json={"code": "authentication.app_token", "message": "Invalid app_token"}
        )

    assert _probe(rejected) == "rejected_token"
    assert seen["token"] == SECRET


def test_check_token_classifies_accepted():
    assert _probe(lambda r: httpx.Response(200, json=[{"a": "1"}])) == "accepted"


def test_check_token_classifies_forbidden_other():
    body = {"code": "forbidden", "message": "You are not allowed to see this"}
    assert _probe(lambda r: httpx.Response(403, json=body)) == "forbidden_other"
    assert _probe(lambda r: httpx.Response(403, text="<html>no</html>")) == "forbidden_other"


@pytest.mark.parametrize("status", [404, 429, 500, 503])
def test_check_token_classifies_unavailable(status):
    assert _probe(lambda r: httpx.Response(status, json={})) == "unavailable"


def test_check_token_classifies_transport_error():
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    assert _probe(boom) == "transport_error"


def test_check_token_never_prints_the_token(capsys, monkeypatch):
    monkeypatch.setenv("SOCRATA_APP_TOKEN", SECRET)
    monkeypatch.setattr(check_token, "first_dataset_id", lambda host: "abcd-1234")
    monkeypatch.setattr(check_token, "get", lambda *a, **k: (200, []))
    transport = httpx.MockTransport(lambda r: httpx.Response(403, json={"message": "app_token"}))
    monkeypatch.setattr(check_token, "make_client", lambda: httpx.Client(transport=transport))
    check_token.main(["data.example.gov"])
    out = capsys.readouterr()
    assert SECRET not in out.out + out.err
    assert "rejected_token" in out.out
