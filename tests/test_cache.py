"""Metadata caches: describe reseeds the schema, region labels are fetched once."""

from __future__ import annotations

from typing import Any

import anyio
import pytest

from opendata_atlas.core import cache, describe
from opendata_atlas.core.cache import TtlCache
from opendata_atlas.core.errors import AtlasError, ErrorCode
from opendata_atlas.core.http import SodaClient, set_client
from tests.conftest import SEATTLE_CONTEXT, wire
from tests.http_fixtures import Replay

FIRE = "kzjm-xkqj"
THREE_CALLS = "incident_number in ('F260124133', 'F260124199', 'F260124257')"


def _views_fetched(transport: Replay) -> int:
    return sum("/api/views/" in r for r in transport.requests)


@pytest.mark.soda_fixture("describe_fire_summary")
async def test_describe_then_query_fetches_the_schema_once(client, soda):
    described = wire(
        await client.call_tool_mcp(
            "atlas_describe_dataset", {"portal": "seattle", "dataset_id": FIRE}
        )
    )
    assert described["isError"] is False
    assert (SEATTLE_CONTEXT.id, FIRE) in cache.views

    replay = Replay("query_three_rows")
    set_client(SodaClient(transport=replay))
    queried = wire(
        await client.call_tool_mcp(
            "atlas_query_dataset",
            {
                "portal": "seattle",
                "dataset_id": FIRE,
                "select": ["incident_number"],
                "where": THREE_CALLS,
                "page_size": 3,
            },
        )
    )
    assert queried["isError"] is False
    assert _views_fetched(replay) == 0, "query reuses the schema describe just fetched"


@pytest.mark.soda_fixture("describe_fire_summary")
async def test_describe_always_fetches_a_fresh_schema(client, soda):
    for _ in range(2):
        result = await client.call_tool_mcp(
            "atlas_describe_dataset", {"portal": "seattle", "dataset_id": FIRE}
        )
        assert wire(result)["isError"] is False
    if hasattr(soda, "requests"):
        assert _views_fetched(soda) == 2


@pytest.mark.soda_fixture("describe_fire_full")
async def test_region_labels_are_fetched_once_per_feature(client, soda):
    args = {"portal": "seattle", "dataset_id": FIRE, "detail": "full", "column_query": "type"}
    first = wire(await client.call_tool_mcp("atlas_describe_dataset", args))
    if not hasattr(soda, "requests"):
        return  # recording: the second call would only repeat recorded requests
    assert [r for r in soda.requests if "_feature_id" in r], "the first call resolves labels"

    soda.requests.clear()
    second = wire(await client.call_tool_mcp("atlas_describe_dataset", args))
    assert not [r for r in soda.requests if "_feature_id" in r]
    assert second["structuredContent"]["place_fields"] == first["structuredContent"]["place_fields"]


#: One feature per region layer on Fire 911, from the describe_fire_full fixture.
_ONE_LABEL_PER_LAYER = {
    "2day-rhn5": "97",
    "cyqu-gs94": "1",
    "kuhn-3gp2": "1",
    "q256-3sug": "4839",
    "ru88-fbhk": "1",
}


def _warm_one_label_per_layer() -> None:
    for layer, feature in _ONE_LABEL_PER_LAYER.items():
        cache.region_labels.put((SEATTLE_CONTEXT.id, layer, feature), "CACHED")


def _region_fields(result: dict) -> list[dict]:
    assert result["isError"] is False, result["structuredContent"]
    fields = result["structuredContent"]["place_fields"]
    return [p for p in fields if p["source"] == "computed_region" and p.get("values")]


@pytest.mark.soda_fixture(
    "describe_fire_full", overrides={"_feature_id": (500, {"message": "unavailable"})}
)
async def test_partial_label_cache_does_not_hide_a_failed_lookup(client, soda):
    _warm_one_label_per_layer()
    args = {"portal": "seattle", "dataset_id": FIRE, "detail": "full", "column_query": "type"}
    fields = _region_fields(wire(await client.call_tool_mcp("atlas_describe_dataset", args)))
    assert fields
    for field in fields:
        assert field["labels_available"] is False, field["column"]
        assert all(v["label"] == v["value"] for v in field["values"]), "names stay ids"


@pytest.mark.soda_fixture("describe_fire_full")
async def test_partial_label_cache_does_not_hide_a_label_timeout(client, soda, monkeypatch):
    soql = SodaClient.soql

    async def hang_on_labels(self, portal, dataset_id, params, *a, **kw):
        if "_feature_id" in params.get("$select", ""):
            await anyio.sleep(60)
        return await soql(self, portal, dataset_id, params, *a, **kw)

    monkeypatch.setattr(SodaClient, "soql", hang_on_labels)
    monkeypatch.setattr(describe, "_LABEL_FETCH_TIMEOUT", 0.05)
    _warm_one_label_per_layer()
    args = {"portal": "seattle", "dataset_id": FIRE, "detail": "full", "column_query": "type"}
    fields = _region_fields(wire(await client.call_tool_mcp("atlas_describe_dataset", args)))
    assert fields
    assert all(f.get("labels_available") is not True for f in fields)


def test_ttl_cache_expires_and_evicts(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(cache.time, "monotonic", lambda: now[0])
    entries: TtlCache[str, int] = TtlCache(ttl=10, max_entries=2)

    entries.put("a", 1)
    entries.put("b", 2)
    entries.put("a", 3)  # rewriting moves "a" behind "b"
    entries.put("c", 4)
    assert "b" not in entries, "the oldest write is evicted"
    assert entries.get("a") == 3 and entries.get("c") == 4

    now[0] = 10.0
    assert entries.get("a") is None, "entries expire at the TTL"
    assert len(entries) == 1


class _SlowViews:
    """A client whose `view` waits for `release`, counting calls; fails while `fail` is set."""

    def __init__(self) -> None:
        self.calls = 0
        self.release = anyio.Event()
        self.fail = False

    async def view(self, portal, dataset_id):
        self.calls += 1
        await self.release.wait()
        if self.fail:
            raise AtlasError(ErrorCode.UPSTREAM_UNAVAILABLE, "down")
        return {"id": dataset_id, "columns": []}


async def _concurrently(client: _SlowViews, n: int) -> list[Any]:
    out: list[Any] = []

    async def one() -> None:
        try:
            out.append(await cache.cached_view(client, SEATTLE_CONTEXT, "aaaa-bbbb"))  # ty: ignore[invalid-argument-type]
        except AtlasError as exc:
            out.append(exc)

    async with anyio.create_task_group() as tg:
        for _ in range(n):
            tg.start_soon(one)
        await anyio.sleep(0.01)
        client.release.set()
    return out


async def test_concurrent_misses_share_one_fetch():
    """#37: four simultaneous reads used to make four upstream calls."""
    cache.clear()
    client = _SlowViews()
    views = await _concurrently(client, 4)
    assert client.calls == 1
    assert all(v == {"id": "aaaa-bbbb", "columns": []} for v in views)
    assert ("data.seattle.gov", "aaaa-bbbb") in cache.views


async def test_a_failed_fetch_is_not_shared():
    """Each waiter fetches for itself after the leader fails, so it gets its own error."""
    cache.clear()
    client = _SlowViews()
    client.fail = True
    errors = await _concurrently(client, 3)
    assert client.calls == 3
    assert all(isinstance(e, AtlasError) for e in errors)
    assert len({id(e) for e in errors}) == 3


async def test_a_cancelled_leader_does_not_strand_waiters():
    """A leader cancelled by its own deadline wakes its waiters, which then fetch themselves."""
    cache.clear()
    client = _SlowViews()
    scope = anyio.CancelScope()
    results: list[Any] = []

    async def leader() -> None:
        with scope:
            await cache.cached_view(client, SEATTLE_CONTEXT, "aaaa-bbbb")  # ty: ignore[invalid-argument-type]

    async def waiter() -> None:
        results.append(await cache.cached_view(client, SEATTLE_CONTEXT, "aaaa-bbbb"))  # ty: ignore[invalid-argument-type]

    async with anyio.create_task_group() as tg:
        tg.start_soon(leader)
        await anyio.sleep(0.01)
        tg.start_soon(waiter)
        await anyio.sleep(0.01)
        scope.cancel()
        await anyio.sleep(0.01)
        client.release.set()
    assert results == [{"id": "aaaa-bbbb", "columns": []}]
    assert client.calls == 2
    # Copilot on #44: the waiter's own fetch is cached for the query that follows.
    assert cache.views.get(("data.seattle.gov", "aaaa-bbbb")) == {"id": "aaaa-bbbb", "columns": []}
