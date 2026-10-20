"""Probe how to enumerate every Socrata domain the Discovery API indexes (dev-only).

Usage: uv run python scripts/feasibility/enumerate_domains.py OUT.json

Tries, per region (`us`, `eu`): (a) the `/domains` endpoint, (b) offset paging, (b2) deep
scrolling with `scroll_id`, (c) per-topic-word search. Each method pages at most
MAX_REQUESTS times per region. Prints a JSON summary; writes the full result to OUT.json.
"""

import json
import sys
from typing import Any

from _http import REGIONS, get

MAX_REQUESTS = 20
SCROLL_LIMIT = 5000
TOPIC_WORDS = [
    "police", "budget", "311", "crime", "parks", "employees", "health", "transportation",
    "housing", "permits", "election", "school", "water", "traffic", "covid", "library",
    "fire", "business", "census", "energy",
]  # fmt: skip


def is_eligible(domain: str) -> bool:
    """False for demo, staging, internal and private hosts; all other hosts are public."""
    host = domain.lower()
    labels = host.split(".")
    return not (
        "demo" in labels
        or any("staging" in label for label in labels)
        or host.startswith(("internal", "priv-"))
    )


def _domains_of(payload: Any) -> set[str]:
    return {r["metadata"]["domain"] for r in payload.get("results", []) if "metadata" in r}


def method_a(base: str) -> dict[str, Any]:
    status, _ = get(f"{base}/api/catalog/v1/domains")
    return {"status": status, "works": status == 200, "domains": []}


def method_b(base: str) -> dict[str, Any]:
    """Offset paging with limit=10000; stops at the first non-200 or short page."""
    found: set[str] = set()
    requests, stop = 0, None
    for page in range(MAX_REQUESTS):
        offset = page * 10000
        status, payload = get(
            f"{base}/api/catalog/v1", {"only": "dataset", "limit": 10000, "offset": offset}
        )
        requests += 1
        if status != 200 or payload is None:
            stop = {"offset": offset, "status": status, "error": payload}
            break
        found |= _domains_of(payload)
        if len(payload["results"]) < 10000:
            stop = {"offset": offset, "short_page": len(payload["results"])}
            break
    return {
        "requests": requests,
        "stop": stop,
        "capped": not (stop and "short_page" in stop),
        "domains": sorted(found),
    }


def method_b2(base: str) -> dict[str, Any]:
    """Deep scrolling: scroll_id is the last id of the previous page ("" on the first request)."""
    found: set[str] = set()
    growth: list[int] = []
    scroll_id = ""  # the first request must send an empty scroll_id to start in id order
    ids: set[str] = set()
    results_seen = 0
    exhausted = False
    requests = 0
    for _ in range(MAX_REQUESTS):
        params: dict[str, Any] = {"only": "dataset", "limit": SCROLL_LIMIT, "scroll_id": scroll_id}
        status, payload = get(f"{base}/api/catalog/v1", params)
        requests += 1
        if status != 200 or payload is None:
            return {
                "requests": requests,
                "status": status,
                "error": payload,
                "capped": True,
                "domains": sorted(found),
            }
        results = payload["results"]
        results_seen += len(results)
        ids |= {r["resource"]["id"] for r in results}
        found |= _domains_of(payload)
        growth.append(len(found))
        if len(results) < SCROLL_LIMIT:
            exhausted = True
            break
        scroll_id = results[-1]["resource"]["id"]
    return {
        "requests": requests,
        "results_seen": results_seen,
        "unique_ids": len(ids),
        "domain_growth_per_page": growth,
        "exhausted": exhausted,
        "capped": not exhausted,
        "domains": sorted(found),
    }


def method_c(base: str) -> dict[str, Any]:
    found: set[str] = set()
    growth: list[int] = []
    requests = 0
    for word in TOPIC_WORDS[:MAX_REQUESTS]:
        status, payload = get(
            f"{base}/api/catalog/v1", {"q": word, "only": "dataset", "limit": 1000}
        )
        requests += 1
        if status == 200 and payload:
            found |= _domains_of(payload)
        growth.append(len(found))
    return {
        "requests": requests,
        "domain_growth_per_word": growth,
        "capped": True,
        "domains": sorted(found),
    }


def main(out_path: str) -> None:
    methods: dict[str, dict[str, Any]] = {}
    union: dict[str, set[str]] = {}
    for region, base in REGIONS.items():
        for name, fn in (("a", method_a), ("b", method_b), ("b2", method_b2), ("c", method_c)):
            result = fn(base)
            methods[f"{region}:{name}"] = {k: v for k, v in result.items() if k != "domains"}
            methods[f"{region}:{name}"]["domain_count"] = len(result["domains"])
            union.setdefault(region, set()).update(result["domains"])
            print(f"{region}:{name} {methods[f'{region}:{name}']}", file=sys.stderr)
    all_domains = sorted(set().union(*union.values()))
    eligible = [d for d in all_domains if is_eligible(d)]
    complete = {
        region: [
            name
            for name in ("a", "b", "b2")
            if methods[f"{region}:{name}"]["domain_count"]
            and not methods[f"{region}:{name}"]["capped"]
        ]
        for region in REGIONS
    }
    summary = {
        "method": "per region, the methods that finished with no cap observed (see complete_by)",
        "complete_by": complete,
        "regions": {r: len(d) for r, d in union.items()},
        "domain_count": len(all_domains),
        "eligible_count": len(eligible),
        "capped": not all(complete.values()),
    }
    with open(out_path, "w") as f:  # noqa: PTH123
        json.dump(
            {
                "summary": summary,
                "methods": methods,
                "by_region": {r: sorted(d) for r, d in union.items()},
                "eligible": eligible,
            },
            f,
            indent=1,
        )
    print(json.dumps(summary))


if __name__ == "__main__":
    main(sys.argv[1])
