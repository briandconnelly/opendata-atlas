"""Probe whether one Socrata app token is honored on every portal (dev-only).

Usage: SOCRATA_APP_TOKEN=... uv run python scripts/feasibility/check_token.py HOST [HOST...]

Requests `/resource/<id>.json?$limit=1` on each host with the token (header
`X-App-Token`), using each host's first dataset id from its catalog. Without a token it
prints `token: unavailable` and exits 0. Each host's `with_token` is one of `accepted`,
`rejected_token` (403 whose body matches the engine's app-token rejection predicate),
`forbidden_other`, `unavailable` (404, 429, 5xx) or `transport_error`. The token is never printed.
"""

import json
import os
import sys
import time
from typing import Literal

import httpx
from _http import DELAY_SECONDS, REGIONS, TIMEOUT_SECONDS, USER_AGENT, get

from opendata_atlas.core.errors import is_app_token_rejection

Outcome = Literal["accepted", "rejected_token", "forbidden_other", "unavailable", "transport_error"]


def make_client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_SECONDS, follow_redirects=True
    )


def probe(client: httpx.Client, url: str, token: str) -> Outcome:
    """GET `url?$limit=1` with the token and classify the outcome. Never echoes the token."""
    time.sleep(DELAY_SECONDS)
    try:
        response = client.get(url, params={"$limit": 1}, headers={"X-App-Token": token})
    except httpx.HTTPError:
        return "transport_error"
    status = response.status_code
    if 200 <= status < 300:
        return "accepted"
    if status == 403:
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict) and is_app_token_rejection(body):
            return "rejected_token"
        return "forbidden_other"
    return "unavailable"


def first_dataset_id(host: str) -> str | None:
    for base in REGIONS.values():
        status, payload = get(
            f"{base}/api/catalog/v1", {"domains": host, "only": "dataset", "limit": 1}
        )
        if status == 200 and payload["results"]:
            return payload["results"][0]["resource"]["id"]
    return None


def main(hosts: list[str]) -> None:
    token = os.environ.get("SOCRATA_APP_TOKEN")
    if not token:
        print("token: unavailable")
        return
    results = {}
    client = make_client()
    for host in hosts:
        dataset_id = first_dataset_id(host)
        if not dataset_id:
            results[host] = {"status": None, "note": "no dataset id found"}
            continue
        status, _ = get(f"https://{host}/resource/{dataset_id}.json", {"$limit": 1})
        url = f"https://{host}/resource/{dataset_id}.json"
        outcome = probe(client, url, token)
        results[host] = {"id": dataset_id, "anonymous": status, "with_token": outcome}
    client.close()
    print(json.dumps(results, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
