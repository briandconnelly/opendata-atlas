"""Capture the engine's own request for a forced no_such_column, then probe it (dev-only).

Usage: uv run python scripts/feasibility/no_such_column_probe.py OUT.json

For data.lacity.org, data.wa.gov and data.sf.gov: (a) run the engine's `query.run` with
`select=["no_such_column_xyz"]` through a transport that logs every outbound URL and response;
(b) send single-variable probes by hand: `$select=no_such_column_xyz` alone, with `:id` added to
`$select` only, and with `$order=:id` only. Sequential, 0.5 s apart.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import httpx
from compat_run import build_context

from opendata_atlas.core import query
from opendata_atlas.core.errors import AtlasError
from opendata_atlas.core.http import SodaClient

HOSTS = {
    "data.lacity.org": "k5qd-jg2c",
    "data.wa.gov": "yccr-zbpr",
    "data.sf.gov": "i98e-djp9",
}
BAD = "no_such_column_xyz"
PROBES = {
    "select_bad_only": {"$select": BAD, "$limit": "5"},
    "select_bad_plus_id": {"$select": f"{BAD}, :id", "$limit": "5"},
    "order_id_only": {"$select": BAD, "$order": ":id", "$limit": "5"},
    "select_and_order_id": {"$select": f"{BAD}, :id", "$order": ":id", "$limit": "5"},
}
PAUSE = 0.5


class Logging(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.inner = httpx.AsyncHTTPTransport()
        self.log: list[dict[str, Any]] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self.inner.handle_async_request(request)
        body = await response.aread()
        self.log.append(
            {
                "url": str(request.url),
                "status": response.status_code,
                "body": body.decode(errors="replace")[:400],
            }
        )
        headers = [
            (k, v)
            for k, v in response.headers.items()
            if k.lower() not in ("content-encoding", "content-length")
        ]
        return httpx.Response(response.status_code, headers=headers, content=body)


def code_of(body: str) -> str | None:
    try:
        return json.loads(body).get("errorCode")
    except (ValueError, AttributeError):
        return None


async def main(out: str) -> None:
    result: dict[str, Any] = {}
    for host, ds in HOSTS.items():
        entry: dict[str, Any] = {"dataset_id": ds}
        transport = Logging()
        client = SodaClient(transport=transport)
        portal = build_context(host, {"domains": host})
        clauses = dict.fromkeys(
            ("select", "where", "group_by", "having", "order_by", "search_text", "near")
        )
        clauses["select"] = [BAD]
        try:
            await query.run(
                client,
                portal,
                dataset_id=ds,
                mode="clauses",
                clauses=clauses,
                soql=None,
                page_size=5,
                cursor=None,
                detail="summary",
            )
            entry["engine_outcome"] = "no_error"
        except AtlasError as exc:
            entry["engine_outcome"] = exc.envelope.code.value
        await client.aclose()
        for req in transport.log:
            req["errorCode"] = code_of(req["body"])
        entry["engine_requests"] = transport.log
        await asyncio.sleep(PAUSE)
        probes = {}
        async with httpx.AsyncClient(headers={"User-Agent": "opendata-atlas-feasibility/0"}) as h:
            for name, params in PROBES.items():
                r = await h.get(f"https://{host}/resource/{ds}.json", params=params)
                probes[name] = {
                    "url": str(r.request.url),
                    "status": r.status_code,
                    "errorCode": code_of(r.text),
                    "body": r.text[:300],
                }
                await asyncio.sleep(PAUSE)
        entry["probes"] = probes
        result[host] = entry
        print(
            host,
            entry["engine_outcome"],
            {k: v["errorCode"] for k, v in probes.items()},
            [(q["status"], q["errorCode"]) for q in transport.log],
        )
    Path(out).write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
