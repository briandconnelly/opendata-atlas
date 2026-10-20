"""Per-host concurrency limit: one busy portal must not starve the others."""

from __future__ import annotations

import anyio
import httpx
import pytest

from opendata_atlas.constants import PER_HOST_CONCURRENCY
from opendata_atlas.core.errors import AtlasError
from opendata_atlas.core.http import SodaClient


class Recorder:
    """A transport that records the peak in-flight request count per host."""

    def __init__(
        self, hold: anyio.Event | None = None, hold_host: str | None = None, rows: int = 1
    ) -> None:
        self.current: dict[str, int] = {}
        self.peak: dict[str, int] = {}
        self.hold, self.hold_host, self.rows = hold, hold_host, rows
        self.entered = anyio.Event()

    async def handler(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        self.current[host] = self.current.get(host, 0) + 1
        self.peak[host] = max(self.peak.get(host, 0), self.current[host])
        try:
            if self.hold is not None and host == self.hold_host:
                self.entered.set()
                await self.hold.wait()
            else:
                await anyio.sleep(0.02)
            return httpx.Response(200, json=[{"a": i} for i in range(self.rows)])
        finally:
            self.current[host] -= 1


async def test_requests_to_one_host_never_exceed_the_limit():
    rec = Recorder()
    client = SodaClient(transport=httpx.MockTransport(rec.handler))
    async with anyio.create_task_group() as tg:
        for i in range(12):
            tg.start_soon(
                client.get_json, f"https://data.example.gov/resource/aaaa-bbbb.json?i={i}"
            )
    await client.aclose()
    assert rec.peak["data.example.gov"] == PER_HOST_CONCURRENCY


async def test_stream_rows_releases_the_limit_on_early_close():
    rec = Recorder(rows=5)
    client = SodaClient(transport=httpx.MockTransport(rec.handler))
    portal = type(
        "P",
        (),
        {"id": "x", "identity": type("I", (), {"public_host": "data.example.gov", "name": "X"})()},
    )()
    results = []

    async def one() -> None:
        results.append(await client.stream_rows(portal, "aaaa-bbbb", {}, max_rows=1))  # ty: ignore[invalid-argument-type]

    async with anyio.create_task_group() as tg:
        for _ in range(10):
            tg.start_soon(one)
    assert len(results) == 10
    assert all(r.more and len(r.rows) == 1 for r in results)
    assert rec.peak["data.example.gov"] == PER_HOST_CONCURRENCY
    assert client._limiters["data.example.gov"].borrowed_tokens == 0
    await client.aclose()


async def test_two_hosts_in_parallel_do_not_block_each_other():
    hold = anyio.Event()
    rec = Recorder(hold=hold, hold_host="a.example.gov")
    client = SodaClient(transport=httpx.MockTransport(rec.handler))
    async with anyio.create_task_group() as tg:
        for i in range(PER_HOST_CONCURRENCY + 2):
            tg.start_soon(client.get_json, f"https://a.example.gov/resource/aaaa-bbbb.json?i={i}")
        with anyio.fail_after(5):
            await rec.entered.wait()
            await anyio.sleep(0.05)  # let host A reach its limit
            assert rec.current["a.example.gov"] == PER_HOST_CONCURRENCY
            body = await client.get_json("https://b.example.gov/resource/aaaa-bbbb.json")
        assert body == [{"a": 0}]
        hold.set()
    await client.aclose()
    assert rec.peak["a.example.gov"] == PER_HOST_CONCURRENCY


async def test_limiter_is_released_after_a_request_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    client = SodaClient(transport=httpx.MockTransport(handler))
    for _ in range(PER_HOST_CONCURRENCY + 2):
        with pytest.raises(AtlasError):
            await client.get_json("https://data.example.gov/resource/aaaa-bbbb.json")
    limiter = client._limiters["data.example.gov"]
    assert limiter.borrowed_tokens == 0
    await client.aclose()


async def test_limiter_is_released_after_cancellation():
    hold = anyio.Event()
    rec = Recorder(hold=hold, hold_host="data.example.gov")
    client = SodaClient(transport=httpx.MockTransport(rec.handler))
    async with anyio.create_task_group() as tg:
        tg.start_soon(client.get_json, "https://data.example.gov/resource/aaaa-bbbb.json")
        with anyio.fail_after(5):
            await rec.entered.wait()
        tg.cancel_scope.cancel()
    assert client._limiters["data.example.gov"].borrowed_tokens == 0
    await client.aclose()
