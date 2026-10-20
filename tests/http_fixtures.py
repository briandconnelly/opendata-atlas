"""Record real SODA responses once, replay them in tests.

`RECORD_FIXTURES=1 uv run pytest` hits the live API and rewrites fixture files;
a plain run replays them and fails on any request not recorded.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from typing import Any

import httpx

FIXTURES = Path(__file__).parent / "fixtures" / "http"
RECORDING = bool(os.environ.get("RECORD_FIXTURES"))
#: The engine reads column names and types from the X-SODA2 headers; dropping them changes results.
_KEPT_HEADERS = ("content-type", "retry-after", "x-soda2-fields", "x-soda2-types")


def _load_scrubber():
    path = Path(__file__).resolve().parent.parent / "scripts" / "scrub_fixtures.py"
    spec = importlib.util.spec_from_file_location("scrub_fixtures", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: `scripts/scrub_fixtures.py`, loaded once here for every test that needs it.
scrubber = _load_scrubber()
#: Recorded responses carry owners' names and emails; nothing identifying reaches disk.
scrub = scrubber.scrub


def _key(request: httpx.Request) -> str:
    params = sorted(request.url.params.multi_items())
    return request.url.host + request.url.path + "?" + json.dumps(params)


class Recorder(httpx.AsyncBaseTransport):
    def __init__(self, name: str) -> None:
        self.path = FIXTURES / f"{name}.json"
        # Tests may share a fixture file; merge rather than overwrite.
        self.entries: dict[str, dict[str, Any]] = (
            json.loads(self.path.read_text()) if self.path.exists() else {}
        )
        self._live = httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._live.handle_async_request(request)
        body = await response.aread()
        self.entries[_key(request)] = {
            "status": response.status_code,
            "headers": {k: v for k, v in response.headers.items() if k.lower() in _KEPT_HEADERS},
            "body": json.loads(body) if body else None,
        }
        # `aread()` already decoded the body; forwarding Content-Encoding would decode it twice.
        headers = {
            k: v
            for k, v in response.headers.items()
            if k.lower() not in ("content-encoding", "content-length")
        }
        return httpx.Response(response.status_code, headers=headers, content=body, request=request)

    def save(self) -> None:
        # Only the file is scrubbed: while recording, a test sees the live body, so never
        # assert on an identity value. New account-id placeholders are numbered after every
        # fixture's, so no two files give one placeholder to different accounts.
        others = (json.loads(p.read_text()) for p in FIXTURES.glob("*.json") if p != self.path)
        ids = scrubber.AccountIds.after(self.entries, *others)
        self.path.write_text(json.dumps(scrub(self.entries, ids), indent=1, sort_keys=True) + "\n")


class Replay(httpx.AsyncBaseTransport):
    def __init__(self, name: str, overrides: dict[str, Any] | None = None) -> None:
        self.entries: dict[str, dict[str, Any]] = json.loads(
            (FIXTURES / f"{name}.json").read_text()
        )
        self.overrides = overrides or {}
        self.requests: list[str] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        key = _key(request)
        self.requests.append(key)
        for fragment, action in self.overrides.items():
            if fragment in key:
                if action == "timeout":
                    raise httpx.ReadTimeout("simulated", request=request)
                status, body = action
                return httpx.Response(status, json=body, request=request)
        # Saved keys are scrubbed (`Recorder.save`), so look up the scrubbed form.
        stored = scrub(key)
        if stored not in self.entries:
            raise AssertionError(f"unrecorded request: {stored}")
        entry = self.entries[stored]
        return httpx.Response(
            entry["status"], headers=entry["headers"], json=entry["body"], request=request
        )
