"""Live cross-portal compatibility through the MCP tools. Run with --run-integration.

The 20 portals of milestone 0's sample (`docs/evidence/feasibility-2026-10-17/compat.json`), plus
`data.everettwa.gov` (milestone 6, for its promotion smoke), by registry id. Per portal,
sequentially and with a pause between portals:

1. `atlas_search_datasets` for "permits"; with no tabular result, browse (`{portal}`) instead.
2. `atlas_describe_dataset` on the first queryable result, `detail: "full"`.
3. `atlas_query_dataset` page 1 (`page_size: 20`), then page 2 through the cursor. When the
   dataset is empty or fits one page, steps 2-3 move to the next queryable result, up to
   `MAX_CANDIDATES` results in all; `attempts` records each one tried.
4. `select: ["no_such_column_xyz"]`: `no_such_column`, with no `/resource` request sent.

A step is a *data* outcome only when a saved 2xx upstream response explains it (no tabular
search result, a 0-row dataset, one page because the dataset is smaller than the page); the test
then xfails with the reason. Any other failure is an *engine* failure and fails the test.
`test_run_is_not_vacuous` fails a full run that exercised too little.

Every upstream exchange is saved per portal under `COMPAT_EVIDENCE_DIR` (default: a pytest
temporary directory), with `outcomes.json` and `outcomes.md` for the run; a run of fewer than all
`SAMPLE` portals writes to its `partial/` subdirectory instead. Saved bodies keep no personal data:
see `_saved_body`. To record:
`COMPAT_EVIDENCE_DIR=docs/evidence/compat-2026-10-18 uv run pytest --run-integration -m
integration tests/test_compat_live.py -v`.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest

from opendata_atlas.core.http import SodaClient, set_client
from opendata_atlas.portals.registry import load_registry
from opendata_atlas.portals.resolve import _pack_dirs
from tests.conftest import wire
from tests.http_fixtures import scrubber

pytestmark = pytest.mark.integration

#: Milestone 0's sample hosts, in its order. All 20 are registry ids (none was dropped by
#: the registry's eligibility rules); a missing one fails `test_sample_is_in_registry`.
SAMPLE = [
    "data.seattle.gov",
    "data.sf.gov",
    "data.cityofchicago.org",
    "data.cityofnewyork.us",
    "data.kingcounty.gov",
    "datahub.austintexas.gov",
    "www.dallasopendata.com",
    "data.lacity.org",
    "data.nola.gov",
    "datacatalog.cookcountyil.gov",
    "data.montgomerycountymd.gov",
    "data.wa.gov",
    "data.ny.gov",
    "data.texas.gov",
    "data.cdc.gov",
    "data.calgary.ca",
    "www.datos.gov.co",
    "data.oregon.gov",
    "data.honolulu.gov",
    "opendata.camden.gov.uk",
    "data.everettwa.gov",
]
PAGE_SIZE = 20
PAUSE_SECONDS = 0.5
FORCED_COLUMN = "no_such_column_xyz"
#: Queryable search results tried in turn when a dataset is empty or fits one page.
MAX_CANDIDATES = 3
#: Ruling 26: a full run below these fails `test_run_is_not_vacuous`.
MIN_FULLY_OK = 16
MAX_XFAIL = 4
MIN_PAGE_TWO = 15
#: A saved body above this is summarized, so each evidence file stays under 1 MB.
BODY_CAP = 64 * 1024
FILE_CAP = 1_000_000
#: Cook County's `/api/views` answered HTTP 500 in Task 2; that is an upstream outcome.
COOK = "datacatalog.cookcountyil.gov"
QUERY_STEPS = ("query_p1", "query_p2", "forced")

# Evidence redaction (ruling 25) ------------------------------------------------------------

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]\d{4}(?!\d)")
#: Column statistics kept from `cachedContents`: counts only, never values.
_STAT_COUNTS = frozenset({"null", "not_null", "non_null", "cardinality", "count"})
IDENTITY_REDACTED = "<identity redacted>"


def _redact(value: Any) -> Any:
    """Emails and phone numbers out of text; identities and column value stats out of metadata."""
    if isinstance(value, str):
        return _PHONE.sub("<phone redacted>", _EMAIL.sub("<email redacted>", value))
    if isinstance(value, list):
        return [_redact(v) for v in value]
    if isinstance(value, dict):
        if scrubber.is_metadata_pair(value) and scrubber.identity_metadata_key(value["key"]):
            return {"key": _redact(value["key"]), "value": IDENTITY_REDACTED}
        out: dict[str, Any] = {}
        for k, v in value.items():
            if scrubber.identity_key(k):
                out[k] = IDENTITY_REDACTED
            elif k == "cachedContents" and isinstance(v, dict):
                out[k] = {s: v[s] for s in v if s in _STAT_COUNTS}
            else:
                out[_redact(k)] = _redact(v)
        return out
    return value


def _json(body: bytes) -> Any:
    try:
        return json.loads(body) if body else None
    except ValueError:
        return None


def _saved_body(step: str, body: bytes) -> Any:
    """The response as saved, with no personal data.

    Query rows are reduced to their count and keys: row values can be personal data, and every
    query-step outcome depends only on the row count. Every other body loses owner, contact and
    account identities (including Discovery `classification.domain_metadata` `{key, value}`
    items whose key names one, see `identity_metadata_key` in `scripts/scrub_fixtures.py`),
    `cachedContents` values (`top`, `largest`, `smallest` and the like, which are the column's
    own values; counts stay), emails and phone numbers. The hash is of the body as received.
    """
    parsed = _json(body)
    digest = hashlib.sha256(body).hexdigest()
    if step in QUERY_STEPS and isinstance(parsed, list):
        keys = sorted({k for r in parsed if isinstance(r, dict) for k in r})
        return {"row_count": len(parsed), "keys": keys, "sha256": digest}
    if len(body) <= BODY_CAP:
        return _redact(parsed if parsed is not None else body.decode("utf-8", "replace"))
    summary: dict[str, Any] = {
        "summarized": f"{len(body):,} bytes, over the {BODY_CAP:,}-byte cap",
        "sha256": digest,
    }
    if isinstance(parsed, dict):
        summary["keys"] = sorted(parsed)
        if isinstance(parsed.get("columns"), list):
            summary["column_count"] = len(parsed["columns"])
            summary["column_field_names"] = [c.get("fieldName") for c in parsed["columns"]]
        for key in ("id", "name", "rowsUpdatedAt"):
            if key in parsed:
                summary[key] = parsed[key]
    elif isinstance(parsed, list):
        summary["length"] = len(parsed)
    return _redact(summary)


# Transport spy and outcome rows --------------------------------------------------------------


@dataclass
class Exchange:
    step: str
    url: str
    status: int
    body: bytes


class Spy(httpx.AsyncBaseTransport):
    """The live transport, keeping every response so the evidence is what the engine saw."""

    def __init__(self) -> None:
        self._live = httpx.AsyncHTTPTransport()
        self.log: list[Exchange] = []
        self.step = ""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._live.handle_async_request(request)
        body = await response.aread()
        await response.aclose()
        self.log.append(Exchange(self.step, str(request.url), response.status_code, body))
        # `aread()` already decoded the body; forwarding Content-Encoding would decode it twice.
        headers = {
            k: v
            for k, v in response.headers.items()
            if k.lower() not in ("content-encoding", "content-length")
        }
        return httpx.Response(response.status_code, headers=headers, content=body, request=request)

    async def aclose(self) -> None:
        await self._live.aclose()

    def of(self, step: str, path_part: str = "", since: int = 0) -> list[Exchange]:
        return [x for x in self.log[since:] if x.step == step and path_part in x.url]


@dataclass
class Row:
    portal: str
    steps: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: Each dataset tried for describe and query, in order, with why it was left.
    attempts: list[dict[str, Any]] = field(default_factory=list)

    def record(self, step: str, outcome: str, kind: str, **extra: Any) -> None:
        """kind: ok, data (explained by a saved 2xx response) or engine."""
        self.steps[step] = {"outcome": outcome, "kind": kind, **extra}

    @property
    def engine(self) -> list[str]:
        return [f"{s}: {v['outcome']}" for s, v in self.steps.items() if v["kind"] == "engine"]

    @property
    def data(self) -> list[str]:
        return [f"{s}: {v['outcome']}" for s, v in self.steps.items() if v["kind"] == "data"]

    @property
    def fully_ok(self) -> bool:
        cols = ("search", "describe", "query_p1", "query_p2", "forced_no_such_column")
        return all(self.steps.get(c, {}).get("kind") == "ok" for c in cols)


# Fixtures ---------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def evidence_dir(request, tmp_path_factory) -> Path:
    configured = os.environ.get("COMPAT_EVIDENCE_DIR")
    path = Path(configured) if configured else tmp_path_factory.mktemp("compat")
    selected = [i for i in request.session.items if i.name.startswith("test_portal_compat[")]
    if len(selected) != len(PORTALS):
        path = path / "partial"  # never overwrite a full run's evidence with a subset
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture(scope="module")
def table(evidence_dir):
    rows: list[Row] = []
    yield rows
    if rows:
        _write_table(evidence_dir, rows)


def _cell(step: dict[str, Any] | None) -> str:
    if step is None:
        return "-"
    return "ok" if step["kind"] == "ok" else f"{step['outcome']} ({step['kind']})"


def _write_table(evidence_dir: Path, rows: list[Row]) -> None:
    data = [{"portal": r.portal, "steps": r.steps, "attempts": r.attempts} for r in rows]
    (evidence_dir / "outcomes.json").write_text(json.dumps(data, indent=2) + "\n")
    cols = ["search", "describe", "query_p1", "query_p2", "forced_no_such_column"]
    lines = [
        "| portal | dataset (result #) | " + " | ".join(cols) + " | evidence |",
        "| --- | --- |" + " --- |" * (len(cols) + 1),
    ]
    for r in rows:
        used = r.attempts[-1] if r.attempts else None
        dataset = "-" if used is None else f"{used['dataset_id']} (#{used['result']})"
        cells = " | ".join(_cell(r.steps.get(c)) for c in cols)
        lines.append(f"| {r.portal} | {dataset} | {cells} | `{_file_name(r.portal)}` |")
    (evidence_dir / "outcomes.md").write_text("\n".join(lines) + "\n")


def _file_name(portal: str) -> str:
    return portal.replace(".", "_") + ".json"


@pytest.fixture
async def spy(no_network):
    transport = Spy()
    set_client(SodaClient(transport=transport))
    yield transport
    set_client(None)
    await transport.aclose()
    await asyncio.sleep(PAUSE_SECONDS)  # politeness between portals


def _save(evidence_dir: Path, row: Row, spy: Spy) -> Path:
    path = evidence_dir / _file_name(row.portal)
    doc = {
        "portal": row.portal,
        "steps": row.steps,
        "attempts": row.attempts,
        "exchanges": [
            {"step": x.step, "url": x.url, "status": x.status, "body": _saved_body(x.step, x.body)}
            for x in spy.log
        ],
    }
    text = json.dumps(doc, indent=1, ensure_ascii=False) + "\n"
    assert len(text.encode()) < FILE_CAP, f"{path.name} would exceed 1 MB"
    path.write_text(text)
    return path


# Steps ----------------------------------------------------------------------------------------


async def _call(client, spy: Spy, step: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    spy.step = step
    return wire(await client.call_tool_mcp(tool, args))


def _queryable(found: dict[str, Any]) -> list[str]:
    datasets = found["structuredContent"].get("datasets", [])
    return [d["dataset_id"] for d in datasets if d["queryability"] == "supported"]


def _catalog_2xx(spy: Spy, step: str) -> bool:
    hits = spy.of(step, "/api/catalog/")
    return bool(hits) and all(200 <= x.status < 300 for x in hits)


async def _run(client, spy: Spy, portal: str, row: Row) -> None:
    found = await _call(
        client, spy, "search", "atlas_search_datasets", {"portal": portal, "query": "permits"}
    )
    if found["isError"]:
        row.record("search", found["structuredContent"]["code"], "engine")
        return
    candidates, via = _queryable(found), "query"
    if not candidates:
        browsed = await _call(client, spy, "browse", "atlas_search_datasets", {"portal": portal})
        if browsed["isError"]:
            row.record("search", "browse: " + browsed["structuredContent"]["code"], "engine")
            return
        candidates, via = _queryable(browsed), "browse"
    if not candidates:
        explained = _catalog_2xx(spy, "search") and _catalog_2xx(spy, "browse")
        row.record("search", "no_tabular_result", "data" if explained else "engine")
        return
    row.record("search", "ok", "ok", via=via, queryable_results=len(candidates))

    tried = candidates[:MAX_CANDIDATES]
    for index, dataset_id in enumerate(tried, start=1):
        for step in ("describe", "query_p1", "query_p2"):
            row.steps.pop(step, None)
        await _describe_and_query(client, spy, portal, dataset_id, row)
        tiny = any(row.steps.get(s, {}).get("kind") == "data" for s in ("query_p1", "query_p2"))
        row.attempts.append(
            {
                "result": index,
                "dataset_id": dataset_id,
                "left_because": "empty or one page" if tiny and index < len(tried) else None,
            }
        )
        if not tiny or index == len(tried):
            break
    if row.steps["describe"]["kind"] == "ok":
        await _forced(client, spy, portal, row.attempts[-1]["dataset_id"], row)


async def _describe_and_query(client, spy: Spy, portal: str, dataset_id: str, row: Row) -> None:
    since = len(spy.log)
    described = await _call(
        client,
        spy,
        "describe",
        "atlas_describe_dataset",
        {"portal": portal, "dataset_id": dataset_id, "detail": "full"},
    )
    content = described["structuredContent"]
    if described["isError"]:
        code = content["code"]
        views = spy.of("describe", "/api/views/", since)
        if (
            portal == COOK
            and code == "upstream_unavailable"
            and any(x.status >= 500 for x in views)
        ):
            row.record("describe", code, "data", note="Cook County /api/views 5xx (Task 2)")
        else:
            row.record("describe", code, "engine", message=content.get("message"))
        return
    row_count = (content.get("row_count") or {}).get("value")
    row.record("describe", "ok", "ok", columns=content.get("columns_total"), row_count=row_count)
    await _query_pages(client, spy, {"portal": portal, "dataset_id": dataset_id}, row)


async def _forced(client, spy: Spy, portal: str, dataset_id: str, row: Row) -> None:
    before = len(spy.log)
    forced = await _call(
        client,
        spy,
        "forced",
        "atlas_query_dataset",
        {"portal": portal, "dataset_id": dataset_id, "select": [FORCED_COLUMN], "page_size": 5},
    )
    resource_requests = [x.url for x in spy.log[before:] if "/resource/" in x.url]
    code = forced["structuredContent"].get("code") if forced["isError"] else "no_error"
    if code == "no_such_column" and not resource_requests:
        row.record("forced_no_such_column", "ok", "ok")
    else:
        row.record(
            "forced_no_such_column", code, "engine", resource_requests=len(resource_requests)
        )


async def _query_pages(client, spy: Spy, base: dict[str, Any], row: Row) -> None:
    since = len(spy.log)
    first = await _call(
        client, spy, "query_p1", "atlas_query_dataset", {**base, "page_size": PAGE_SIZE}
    )
    p1 = first["structuredContent"]
    if first["isError"]:
        row.record("query_p1", p1["code"], "engine", message=p1.get("message"))
        return
    upstream = [
        _json(x.body) for x in spy.of("query_p1", "/resource/", since) if 200 <= x.status < 300
    ]
    sent = upstream[-1] if upstream and isinstance(upstream[-1], list) else None
    if p1["returned_rows"] == 0:
        empty = sent == [] and not p1["has_more"]
        row.record("query_p1", "zero_rows", "data" if empty else "engine")
        return
    row.record("query_p1", "ok", "ok", rows=p1["returned_rows"], truncated=p1["truncated"])
    if not p1["has_more"]:
        # Data only when the upstream itself had no more rows than one page holds.
        smaller = sent is not None and len(sent) == p1["returned_rows"] < PAGE_SIZE + 1
        row.record(
            "query_p2",
            "single_page",
            "data" if smaller and not p1["truncated"] else "engine",
            upstream_rows=None if sent is None else len(sent),
        )
        return
    second = await _call(
        client, spy, "query_p2", "atlas_query_dataset", {**base, "cursor": p1["next_cursor"]}
    )
    p2 = second["structuredContent"]
    if second["isError"]:
        row.record("query_p2", p2["code"], "engine", message=p2.get("message"))
    elif p2["returned_rows"] == 0:
        row.record("query_p2", "zero_rows", "engine")
    else:
        row.record("query_p2", "ok", "ok", rows=p2["returned_rows"])


# Tests ----------------------------------------------------------------------------------------


def test_sample_is_in_registry():
    entries = load_registry().entries
    assert [p for p in SAMPLE if p not in entries] == []


#: The sample plus every portal with a pack, so a newly curated portal has its case (#36).
PORTALS = [*SAMPLE, *sorted(set(_pack_dirs()) - set(SAMPLE))]


@pytest.mark.parametrize("portal", PORTALS)
async def test_portal_compat(portal, client, spy, evidence_dir, table):
    row = Row(portal)
    table.append(row)
    try:
        await _run(client, spy, portal, row)
    finally:
        path = _save(evidence_dir, row, spy)
    assert not row.engine, f"engine failure on {portal}: {row.engine} (evidence: {path})"
    if row.data:
        pytest.xfail(f"data outcome on {portal}: {'; '.join(row.data)} (evidence: {path.name})")


def test_run_is_not_vacuous(table):
    """Ruling 26: a run that exercised too little fails, whatever each portal's verdict."""
    assert len(table) == len(SAMPLE), f"{len(table)} portals recorded, not {len(SAMPLE)}"
    fully_ok = sum(r.fully_ok for r in table)
    xfailed = sum(bool(r.data) and not r.engine for r in table)
    page_two = sum(r.steps.get("query_p2", {}).get("kind") == "ok" for r in table)
    assert fully_ok >= MIN_FULLY_OK, f"only {fully_ok} portals fully ok"
    assert xfailed <= MAX_XFAIL, f"{xfailed} portals xfailed"
    assert page_two >= MIN_PAGE_TWO, f"only {page_two} portals exercised page 2"
