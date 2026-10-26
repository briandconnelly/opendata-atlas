"""Per-process caches of upstream metadata (docs/design.md: Engine isolation).

Only metadata is cached here: dataset schemas and region-layer labels. Rows,
counts, and coverage are always live. Every key starts with the portal id: two portals
can serve the same dataset or layer id with different contents.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import anyio

from opendata_atlas.constants import (
    REGION_LABEL_CACHE_MAX,
    REGION_LABEL_TTL_SECONDS,
    VIEW_CACHE_MAX,
    VIEW_TTL_SECONDS,
)

if TYPE_CHECKING:
    from collections.abc import Hashable

    from opendata_atlas.core.http import SodaClient
    from opendata_atlas.portals.model import PortalContext


class TtlCache[K: Hashable, V]:
    """Entries expire after `ttl` seconds; past `max_entries`, the oldest write is evicted."""

    def __init__(self, ttl: float, max_entries: int) -> None:
        self.ttl = ttl
        self.max_entries = max_entries
        self._entries: dict[K, tuple[float, V]] = {}

    def get(self, key: K) -> V | None:
        hit = self._entries.get(key)
        if hit is None:
            return None
        if time.monotonic() - hit[0] >= self.ttl:
            del self._entries[key]
            return None
        return hit[1]

    def put(self, key: K, value: V) -> None:
        # Re-inserting moves the key to the end, so eviction order follows write time.
        self._entries.pop(key, None)
        self._entries[key] = (time.monotonic(), value)
        while len(self._entries) > self.max_entries:
            del self._entries[next(iter(self._entries))]

    def pop(self, key: K) -> None:
        self._entries.pop(key, None)

    def clear(self) -> None:
        self._entries.clear()

    def __contains__(self, key: object) -> bool:
        return self.get(key) is not None  # ty: ignore[invalid-argument-type]

    def __len__(self) -> int:
        return len(self._entries)


#: `(portal_id, dataset_id)` to the dataset's view metadata.
views: TtlCache[tuple[str, str], dict[str, Any]] = TtlCache(VIEW_TTL_SECONDS, VIEW_CACHE_MAX)
#: `(portal_id, layer_id, feature_id)` to label. Boundary layers change on redistricting,
#: not daily.
region_labels: TtlCache[tuple[str, str, str], str] = TtlCache(
    REGION_LABEL_TTL_SECONDS, REGION_LABEL_CACHE_MAX
)


@dataclass
class _Flight:
    """One view fetch in progress; callers that arrive meanwhile wait for it (#37)."""

    done: anyio.Event = field(default_factory=anyio.Event)
    view: dict[str, Any] | None = None


#: `(portal_id, dataset_id)` to the fetch in progress, if any.
_flights: dict[tuple[str, str], _Flight] = {}


async def cached_view(client: SodaClient, portal: PortalContext, dataset_id: str) -> dict[str, Any]:
    view = views.get((portal.id, dataset_id))
    return view if view is not None else await fresh_view(client, portal, dataset_id)


async def fresh_view(client: SodaClient, portal: PortalContext, dataset_id: str) -> dict[str, Any]:
    """Fetch the schema and store it, so the query that usually follows reuses it.

    Concurrent calls for one dataset share one upstream request; a fetch that started before
    the call is as fresh as one it would start. A failed or cancelled fetch is not shared: each
    waiter then fetches for itself, so it gets its own error under its own deadline.
    """
    key = (portal.id, dataset_id)
    flight = _flights.get(key)
    if flight is not None:
        await flight.done.wait()
        if flight.view is not None:
            return flight.view
        # Not coalesced again, but cached, so the query that follows reads this schema.
        view = await client.view(portal, dataset_id)
        views.put(key, view)
        return view
    flight = _flights[key] = _Flight()
    try:
        flight.view = await client.view(portal, dataset_id)
        views.put(key, flight.view)
        return flight.view
    finally:
        del _flights[key]
        flight.done.set()


def clear() -> None:
    views.clear()
    region_labels.clear()
