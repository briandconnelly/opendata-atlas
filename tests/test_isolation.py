"""Two portals serving the same dataset id never share schema, place fields, or cursors.

Portals A and B are test packs under tests/fixtures/portals; their responses are written by
hand in tests/fixtures/http/isolation_two_portals.json, never recorded against real hosts.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from opendata_atlas.core import cache, cursor, describe, query
from opendata_atlas.core.errors import AtlasError, ErrorCode
from opendata_atlas.core.http import SodaClient
from opendata_atlas.core.query import _RESTART as READ_PAGING
from opendata_atlas.portals.loader import load_portal
from tests.http_fixtures import Replay

if TYPE_CHECKING:
    from opendata_atlas.portals.model import PortalContext

FIXTURE_PORTALS = Path(__file__).parent / "fixtures" / "portals"
DATASET = "aaaa-bbbb"
CLAUSES: dict[str, Any] = {
    "select": None,
    "where": None,
    "group_by": None,
    "having": None,
    "order_by": None,
    "search_text": None,
    "near": None,
}


@pytest.fixture
def two_portals() -> tuple[PortalContext, PortalContext]:
    return load_portal(FIXTURE_PORTALS / "a"), load_portal(FIXTURE_PORTALS / "b")


@pytest.fixture
def replay() -> Replay:
    return Replay("isolation_two_portals")


def _describe(client: SodaClient, portal: PortalContext):
    return describe.describe(
        client, portal, dataset_id=DATASET, column_query=None, sample_rows=0, detail="full"
    )


def _query(client: SodaClient, portal: PortalContext, *, page_size=None, cursor=None):
    return query.run(
        client,
        portal,
        dataset_id=DATASET,
        mode="clauses",
        clauses=CLAUSES,
        soql=None,
        page_size=page_size,
        cursor=cursor,
        detail="summary",
    )


def _views(replay: Replay, host: str) -> int:
    return sum(r.startswith(f"{host}/api/views/") for r in replay.requests)


def _encode_v1(kind: str, state: dict[str, Any]) -> str:
    """The fork's cursor format: version 1, no portal, signed with this process's key."""
    payload = cursor.dump({"v": 1, "k": kind, "t": int(time.time()), "s": state})
    signature = hmac.new(cursor._KEY, payload, hashlib.sha256).digest()[:16]
    return f"{cursor._b64(payload)}.{cursor._b64(signature)}"


def _assert_invalid_cursor(error: AtlasError, token: str) -> None:
    envelope = error.envelope
    assert envelope.code == ErrorCode.INVALID_CURSOR
    assert envelope.temporary is False
    assert envelope.repair == READ_PAGING
    text = envelope.model_dump_json()
    assert token not in text, "the cursor is never echoed"
    assert "example.gov" not in text, "the cursor's portal is never echoed"


async def test_same_dataset_id_on_two_portals_never_shares_state(two_portals, replay):
    a, b = two_portals
    client = SodaClient(transport=replay)
    da = await _describe(client, a)
    db = await _describe(client, b)
    assert [c.name for c in da.columns] == ["alpha"]
    assert [c.name for c in db.columns] == ["beta"]
    assert {f.column for f in da.place_fields or []} == {":@computed_region_cccc_dddd"}
    assert {f.column for f in db.place_fields or []} == {":@computed_region_cccc_dddd_b"}
    assert _views(replay, "a.example.gov") == 1
    assert _views(replay, "b.example.gov") == 1, "B's schema is fetched, never A's reused"
    assert (a.id, DATASET) in cache.views
    assert (b.id, DATASET) in cache.views

    qa = await _query(client, a, page_size=1)
    assert [c.name for c in qa.columns] == ["alpha"]
    assert _views(replay, "a.example.gov") == 1, "A's query reuses A's cached schema"
    assert qa.next_cursor is not None

    with pytest.raises(AtlasError) as err:
        await _query(client, b, cursor=qa.next_cursor)
    _assert_invalid_cursor(err.value, qa.next_cursor)


async def test_query_after_describe_on_another_portal_uses_its_own_schema(two_portals, replay):
    a, b = two_portals
    client = SodaClient(transport=replay)
    await _describe(client, a)
    qb = await _query(client, b, page_size=1)
    assert _views(replay, "b.example.gov") == 1
    assert [c.name for c in qb.columns] == ["beta"]
    assert all(r.startswith("b.example.gov/") for r in replay.requests[-2:])


def test_version1_cursor_rejected():
    legacy = _encode_v1("query", {"dataset_id": "kzjm-xkqj"})
    with pytest.raises(AtlasError) as err:
        cursor.decode(legacy, "query", portal_id="data.seattle.gov", restart=READ_PAGING)
    _assert_invalid_cursor(err.value, legacy)


def test_cursor_is_bound_to_its_portal():
    token = cursor.encode("search", {"off": 10}, portal_id="a.example.gov")
    assert cursor.decode(token, "search", portal_id="a.example.gov", restart=READ_PAGING) == {
        "off": 10
    }
    with pytest.raises(AtlasError) as err:
        cursor.decode(token, "search", portal_id="b.example.gov", restart=READ_PAGING)
    _assert_invalid_cursor(err.value, token)


def test_version2_cursor_without_portal_rejected():
    payload = cursor.dump({"v": 2, "k": "search", "t": int(time.time()), "s": {"off": 10}})
    signature = hmac.new(cursor._KEY, payload, hashlib.sha256).digest()[:16]
    token = f"{cursor._b64(payload)}.{cursor._b64(signature)}"
    with pytest.raises(AtlasError) as err:
        cursor.decode(token, "search", portal_id="a.example.gov", restart=READ_PAGING)
    _assert_invalid_cursor(err.value, token)


async def test_region_labels_come_from_each_portals_own_layer(two_portals, replay):
    """Same layer id and feature id on two portals: the label cache never crosses portals."""
    a, b = two_portals
    client = SodaClient(transport=replay)
    da = await _describe(client, a)
    db = await _describe(client, b)
    (fa,) = da.place_fields or []
    (fb,) = db.place_fields or []
    assert fa.layer_id == fb.layer_id == "cccc-dddd"
    assert fa.labels_available is True and fb.labels_available is True
    assert [(v.value, v.label) for v in fa.values or []] == [("1", "NORTH")]
    assert [(v.value, v.label) for v in fb.values or []] == [("1", "SOUTH")]
    assert cache.region_labels.get((a.id, "cccc-dddd", "1")) == "NORTH"
    assert cache.region_labels.get((b.id, "cccc-dddd", "1")) == "SOUTH"
    labels = [r for r in replay.requests if "/resource/cccc-dddd.json" in r]
    assert [r.split("/")[0] for r in labels] == ["a.example.gov", "b.example.gov"]
