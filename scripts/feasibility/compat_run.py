"""Run the unchanged engine against the 20 sample portals (dev-only).

Usage: uv run python scripts/feasibility/compat_run.py IDENTITY.json [OUT.json]

For each host in Task 2's identity results, with an empty knowledge pack: `search` ("permits"),
`describe` (first queryable result, detail="full"), `query` (two pages through the cursor) and
one forced error (`select=["no_such_column_xyz"]`, expecting `no_such_column`). Sequential,
with a pause between portals, the engine's own deadlines and the engine's User-Agent. Prints a
table and writes the raw rows as JSON.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

from opendata_atlas.core import catalog, describe, query
from opendata_atlas.core.errors import AtlasError
from opendata_atlas.core.http import SodaClient
from opendata_atlas.portals.model import PortalContext, PortalIdentity
from opendata_atlas.portals.registry import context_for

PAUSE_SECONDS = 0.5
FORCED_SELECT = "no_such_column_xyz"


def build_context(host: str, catalog_query: dict[str, str], region: str = "us") -> PortalContext:
    """An empty-pack, generic-tier context for a probed host."""
    identity = PortalIdentity(
        id=host,
        aliases=[],
        public_host=host,
        catalog_query=catalog_query,
        catalog_region=region,  # ty: ignore[invalid-argument-type]
        name=host,
        place_names=[],
        jurisdiction=None,
        # Plumbing placeholder so `make_source` does not raise (it needs a zone until
        # milestone 2). Never a recorded fact about the portal; the results make no time claims.
        timezone="UTC",
        platform="socrata",
        status="active",
        tier="generic",
    )
    return context_for(identity, None)


def catalog_queries_for(entry: dict[str, Any]) -> list[dict[str, str]]:
    """The accepted Discovery parameters for the host itself, `domains` first."""
    host = entry["host"]
    return [
        {param: host}
        for param in ("domains", "search_context")
        if f"{param}={host}" in entry["satisfying"]
    ]


def outcome(exc: BaseException) -> dict[str, Any]:
    if isinstance(exc, AtlasError):
        env = exc.envelope
        return {"outcome": env.code.value, "message": env.message, "engine_error": False}
    return {
        "outcome": f"exception:{type(exc).__name__}",
        "message": str(exc)[:300],
        "engine_error": True,
    }


async def step(label: str, row: dict[str, Any], work: Any) -> Any:
    try:
        value = await work
    except Exception as exc:
        row[label] = outcome(exc)
        return None
    row[label] = {"outcome": "ok"}
    return value


async def run_host(
    client: SodaClient, entry: dict[str, Any], cq: dict[str, str] | None
) -> dict[str, Any]:
    host = entry["host"]
    row: dict[str, Any] = {"host": host}
    if cq is None:
        row["identity"] = "none"
        return row
    row["catalog_query"] = cq
    row["identity"] = "ok"
    portal = build_context(host, cq, entry.get("region", "us"))
    started = time.monotonic()

    found = await step(
        "search",
        row,
        catalog.search(
            client,
            portal,
            query="permits",
            asset_scope="tabular",
            category=None,
            page_size=10,
            cursor=None,
            detail="summary",
        ),
    )
    dataset_id = None
    if found is not None:
        row["search"]["results"] = len(found.datasets)
        supported = [d for d in found.datasets if d.queryability == "supported"]
        if supported:
            dataset_id = supported[0].dataset_id
            row["dataset_id"] = dataset_id
            row["dataset_title"] = supported[0].title
        else:
            row["search"] = {
                "outcome": "no_tabular_result",
                "results": len(found.datasets),
                "engine_error": False,
            }

    if dataset_id is not None:
        described = await step(
            "describe",
            row,
            describe.describe(
                client,
                portal,
                dataset_id=dataset_id,
                column_query=None,
                sample_rows=0,
                detail="full",
            ),
        )
        if described is not None:
            row["describe"]["columns"] = len(described.columns)

        def clauses() -> dict[str, Any]:
            return {
                k: None
                for k in (
                    "select",
                    "where",
                    "group_by",
                    "having",
                    "order_by",
                    "search_text",
                    "near",
                )
            }

        page1 = await step(
            "query_p1",
            row,
            query.run(
                client,
                portal,
                dataset_id=dataset_id,
                mode="clauses",
                clauses=clauses(),
                soql=None,
                page_size=20,
                cursor=None,
                detail="summary",
            ),
        )
        if page1 is not None:
            row["query_p1"]["rows"] = page1.returned_rows
            if page1.has_more and page1.next_cursor:
                page2 = await step(
                    "query_p2",
                    row,
                    query.run(
                        client,
                        portal,
                        dataset_id=dataset_id,
                        mode="clauses",
                        clauses=clauses(),
                        soql=None,
                        page_size=None,
                        cursor=page1.next_cursor,
                        detail="summary",
                    ),
                )
                if page2 is not None:
                    row["query_p2"]["rows"] = page2.returned_rows
            else:
                row["query_p2"] = {"outcome": "single_page", "engine_error": False}

        forced = clauses()
        forced["select"] = [FORCED_SELECT]
        try:
            await query.run(
                client,
                portal,
                dataset_id=dataset_id,
                mode="clauses",
                clauses=forced,
                soql=None,
                page_size=5,
                cursor=None,
                detail="summary",
            )
            row["forced_error"] = {"outcome": "no_error", "engine_error": True}
        except AtlasError as exc:
            code = exc.envelope.code.value
            row["forced_error"] = {
                "outcome": "ok" if code == "no_such_column" else code,
                "message": exc.envelope.message[:200],
                "engine_error": code != "no_such_column",
            }
        except Exception as exc:
            row["forced_error"] = outcome(exc)

    row["seconds"] = round(time.monotonic() - started, 1)
    return row


def table(rows: list[dict[str, Any]]) -> str:
    cols = ["search", "describe", "query_p1", "query_p2", "forced_error"]
    lines = ["host | " + " | ".join(cols) + " | seconds"]
    flat: list[dict[str, Any]] = []
    for r in rows:
        flat.append(r)
        if "retry_with_other_parameter" in r:
            flat.append({**r["retry_with_other_parameter"], "host": r["host"] + " (retry)"})
    for r in flat:
        if r.get("identity") == "none":
            lines.append(f"{r['host']} | identity: none")
            continue
        cells = [r.get(c, {}).get("outcome", "-") for c in cols]
        lines.append(f"{r['host']} | " + " | ".join(cells) + f" | {r.get('seconds')}")
    return "\n".join(lines)


async def main(identity_path: str, out_path: str | None) -> None:
    entries = json.loads(Path(identity_path).read_text())
    client = SodaClient()
    rows = []
    try:
        for entry in entries:
            queries = catalog_queries_for(entry)
            row = await run_host(client, entry, queries[0] if queries else None)
            if row.get("search", {}).get("outcome") == "no_tabular_result" and len(queries) > 1:
                # Same host, the other accepted parameter: separates a data gap from an
                # identity-selection gap.
                await asyncio.sleep(PAUSE_SECONDS)
                row["retry_with_other_parameter"] = await run_host(client, entry, queries[1])
            rows.append(row)
            await asyncio.sleep(PAUSE_SECONDS)
    finally:
        await client.aclose()
    print(table(rows))
    if out_path:
        Path(out_path).write_text(json.dumps(rows, indent=2) + "\n")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))
