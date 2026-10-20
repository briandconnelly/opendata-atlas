"""Probe which Discovery parameters select a portal's catalog (dev-only).

Usage: uv run python scripts/feasibility/check_identity.py HOST [HOST...]

For each host: fetch up to three pages (limit=100) with `domains=<h>` and `search_context=<h>`
for the host and for each catalog `link` host seen on its first page, and report which satisfy
`identity_matches`. Also checks anonymous `/api/views.json?limit=1` and one
`/resource/<id>.json?$limit=1` on the public host. Prints a JSON report.
"""

import json
import sys
from typing import Any
from urllib.parse import urlparse

from _http import REGIONS, get

PAGES = 3
PAGE_SIZE = 100


def identity_matches(pages: list[list[dict]], expected_domain: str) -> bool:
    """True when there is a non-empty page and every result is on `expected_domain`."""
    if not pages or not any(pages):
        return False
    return all(
        result.get("metadata", {}).get("domain") == expected_domain
        for page in pages
        for result in page
    )


def fetch_pages(region: str, param: str, value: str) -> list[list[dict]]:
    pages: list[list[dict]] = []
    for page in range(PAGES):
        status, payload = get(
            f"{REGIONS[region]}/api/catalog/v1",
            {param: value, "limit": PAGE_SIZE, "offset": page * PAGE_SIZE},
        )
        if status != 200 or not payload or not payload["results"]:
            break
        pages.append(payload["results"])
        if len(payload["results"]) < PAGE_SIZE:
            break
    return pages


def probe_param(region: str, param: str, value: str) -> dict[str, Any]:
    pages = fetch_pages(region, param, value)
    seen: dict[str, int] = {}
    for page in pages:
        for r in page:
            d = r.get("metadata", {}).get("domain", "?")
            seen[d] = seen.get(d, 0) + 1
    return {
        "pages": len(pages),
        "results": sum(len(p) for p in pages),
        "matches": identity_matches(pages, value),
        "domains_seen": dict(sorted(seen.items(), key=lambda kv: -kv[1])[:5]),
        "first_dataset_id": pages[0][0]["resource"]["id"] if pages else None,
        "link_hosts": sorted({urlparse(r.get("link", "")).hostname or "" for r in pages[0]})
        if pages
        else [],
    }


def probe_host(host: str) -> dict[str, Any]:
    report: dict[str, Any] = {"host": host}
    region_counts = {}
    for region in REGIONS:
        for param in ("domains", "search_context"):
            status, payload = get(f"{REGIONS[region]}/api/catalog/v1", {param: host, "limit": 0})
            region_counts[f"{region}:{param}"] = payload["resultSetSize"] if status == 200 else None
    report["resultSetSize"] = region_counts
    live = [k for k, v in region_counts.items() if v]
    region = live[0].split(":")[0] if live else "us"
    report["region"] = region

    attempts: dict[str, Any] = {}
    link_hosts: set[str] = set()
    for param in ("domains", "search_context"):
        attempts[f"{param}={host}"] = probe_param(region, param, host)
        link_hosts |= set(attempts[f"{param}={host}"]["link_hosts"])
    for link_host in sorted(link_hosts - {host, ""})[:3]:
        for param in ("domains", "search_context"):
            attempts[f"{param}={link_host}"] = probe_param(region, param, link_host)
    report["attempts"] = attempts
    report["satisfying"] = sorted(k for k, v in attempts.items() if v["matches"])

    status, _ = get(f"https://{host}/api/views.json", {"limit": 1})
    report["api_views_status"] = status
    dataset_id = next(
        (v["first_dataset_id"] for v in attempts.values() if v["first_dataset_id"]), None
    )
    if dataset_id:
        status, payload = get(f"https://{host}/resource/{dataset_id}.json", {"$limit": 1})
        report["resource_probe"] = {
            "id": dataset_id,
            "status": status,
            "rows": len(payload) if isinstance(payload, list) else None,
        }
    return report


if __name__ == "__main__":
    reports = [probe_host(h) for h in sys.argv[1:]]
    print(json.dumps(reports, indent=1))
