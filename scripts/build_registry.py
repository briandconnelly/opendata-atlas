"""Build the portal registry from live Discovery API data (dev-only).

Usage:
    uv run python scripts/build_registry.py \\
        --out src/opendata_atlas/portals/registry.json \\
        --evidence docs/evidence/registry-<date>/ [--titles N|all]

Steps (docs/design.md, Registry):
1. Enumerate catalog domains in both regions by deep scrolling (`enumerate_domains.method_b2`).
2. Eligibility: the milestone 0 name rule (`is_eligible`), the non-production token rule
   (`is_production`), then anonymous `GET https://<public host>/api/views.json?limit=1`
   (`views_verdict`: a 2xx JSON body, a 5xx or a timeout keeps; a 4xx, a 2xx that is not JSON,
   or a connect, DNS, TLS or protocol failure drops).
3. Identity per catalog domain: `domains=` and `search_context=` for the catalog domain and for
   up to three public-host candidates taken from catalog `link` fields; three pages each
   (`check_identity.fetch_pages`), accepted by `identity_matches`; the matched candidate with the
   largest `resultSetSize` wins (`choose_catalog_query`).
4. Names from site titles (`apply_title_names`, rule in `title_name`), then overrides from
   `registry_overrides.toml` (`merge_overrides`; an override's `name` wins), pack identities on
   top, then the case-insensitive id/alias check (`check_aliases`) before anything is written.

The evidence directory doubles as the cache: `enumeration.json` and `probes.jsonl` are reused on a
re-run, so a crash resumes where it stopped (`--refresh` re-enumerates, re-probes and
re-fetches titles). Probes with errors are retried on the next run, and `--reprobe-views`
re-runs only the views probe; a superseded line is kept in `probes.retries.jsonl`.
`--titles N` also fetches the site titles of the N largest portals (`--titles all`: every
portal), and of every override, into `titles.json`; cached records are reused. Titles are the
source for generated names; without `--titles` only cached titles name portals.
Requests are sequential through `feasibility/_http.py` (0.2 s apart, a timeout on each).
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import re
import sys
import time
import tomllib
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import ValidationError

from opendata_atlas.portals.loader import PORTALS_DIR, load_portal
from opendata_atlas.portals.model import PortalIdentity
from opendata_atlas.portals.registry import RegistryEntry

sys.path.insert(0, str(Path(__file__).resolve().parent / "feasibility"))
import _http
from check_identity import PAGE_SIZE, PAGES, fetch_pages, identity_matches
from enumerate_domains import is_eligible, method_b2

USER_AGENT = "opendata-atlas-registry/0"
TIMEOUT_SECONDS = 60.0
MAX_LINK_HOSTS = 3
TOP_N = 50
OVERRIDE_FIELDS = frozenset(
    {
        "name",
        "aliases",
        "place_names",
        "jurisdiction",
        "timezone",
        "public_host",
        "catalog_query",
        "status",
    }
)
OVERRIDES_PATH = PORTALS_DIR / "registry_overrides.toml"


# --------------------------------------------------------------------------- pure functions


def choose_catalog_query(
    candidates: list[tuple[dict[str, str], int, bool]],
) -> dict[str, str] | None:
    """The matched candidate with the largest resultSetSize; ties prefer `domains`."""
    matched = [(params, size) for params, size, ok in candidates if ok]
    if not matched:
        return None
    best = max(matched, key=lambda c: (c[1], "domains" in c[0]))
    return dict(best[0])


def choose_public_host(
    catalog_domain: str, chosen: dict[str, str], link_hosts: dict[str, int]
) -> tuple[str, str]:
    """Public host for a catalog domain, and why.

    A query that matched on another host names that host. Otherwise, when every catalog `link`
    points at one other host, that host is public. Otherwise the catalog domain is.
    """
    other = sorted({v for v in chosen.values() if v != catalog_domain})
    if len(other) == 1:
        return other[0], f"identity matched on {other[0]} ({_fmt(chosen)})"
    hosts = {h: n for h, n in link_hosts.items() if h}
    if len(hosts) == 1:
        ((only, n),) = hosts.items()
        if only != catalog_domain:
            return only, f"every catalog link ({n}) points at {only}"
        return catalog_domain, f"every catalog link ({n}) points at the catalog domain"
    if not hosts:
        return catalog_domain, "no catalog links seen; catalog domain kept"
    return catalog_domain, f"catalog links on several hosts {hosts}; catalog domain kept"


def _base_identity(id_: str) -> dict[str, Any]:
    return {
        "id": id_,
        "aliases": [],
        "public_host": id_,
        "catalog_query": {"domains": id_},
        "catalog_region": "us",
        "name": id_,
        "platform": "socrata",
        "status": "active",
        "tier": "generic",
    }


def merge_overrides(
    entries: dict[str, RegistryEntry], overrides: dict[str, dict]
) -> dict[str, RegistryEntry]:
    """Apply hand-written overrides; an override for an unknown id adds a manual entry."""
    merged = dict(entries)
    for id_, over in overrides.items():
        unknown = sorted(set(over) - OVERRIDE_FIELDS)
        if unknown:
            raise SystemExit(f"registry_overrides: {id_!r}: field(s) {unknown} not allowed")
        old = merged.get(id_)
        base = old.identity.model_dump() if old is not None else _base_identity(id_)
        try:
            ident = PortalIdentity.model_validate(base | over)
        except ValidationError as e:
            raise SystemExit(f"registry_overrides: {id_!r}: {e}") from e
        merged[id_] = RegistryEntry(
            identity=ident,
            dataset_count=old.dataset_count if old is not None else None,
            catalog_size=old.catalog_size if old is not None else None,
        )
    return merged


GENERIC_TITLES = frozenset(
    {
        "catalog",
        "data",
        "data portal",
        "home",
        "open data",
        "open data portal",
        "performance management",
        "rally",
        "socrata",
        "socrata data cloud",
        "this site has moved",
        "tyler data & insights",
        "tyler technologies",
    }
)
GOV = re.compile(
    r"^(?:(?:city|town|village|county|state|commonwealth|city and county|district) of \S.*"
    r"|.*\S county|.*, [A-Z]{2})$",
    re.IGNORECASE,
)
_TITLE_SEPARATOR = re.compile(r"\s+\|\s+|\s+[-\u2013\u2014]\s+")
_TITLE_FIELDS = ("html_title", "site_title", "site_company")


def title_name(record: dict[str, Any], host: str) -> str | None:
    """A portal's name from its own titles, or None when they give none.

    Reads `html_title`, `site_title` and `site_company` in that order, splits each on ` | ` and on
    a spaced hyphen, en dash or em dash, and drops parts that are empty, generic
    (`GENERIC_TITLES`), the host itself, or repeats. The first remaining part that looks like a
    government name (`GOV`) wins, else the first remaining part.
    """
    candidates: list[str] = []
    for field in _TITLE_FIELDS:
        value = record.get(field)
        if not isinstance(value, str):
            continue
        for part in _TITLE_SEPARATOR.split(" ".join(value.split())):
            if not part or part.casefold() in GENERIC_TITLES or part.casefold() == host.casefold():
                continue
            if part not in candidates:
                candidates.append(part)
    return next((c for c in candidates if GOV.match(c)), candidates[0] if candidates else None)


def apply_title_names(
    entries: dict[str, RegistryEntry], titles: dict[str, dict[str, Any]]
) -> dict[str, RegistryEntry]:
    """Replace `identity.name` with the title-derived name where the title gives one."""
    named = dict(entries)
    for id_, entry in entries.items():
        name = title_name(titles.get(id_, {}), entry.identity.public_host)
        if name is not None:
            ident = entry.identity.model_copy(update={"name": name})
            named[id_] = entry.model_copy(update={"identity": ident})
    return named


def check_aliases(entries: dict[str, RegistryEntry]) -> None:
    """Ids and aliases share one case-insensitive namespace; exit naming both on a clash."""
    owner: dict[str, str] = {}
    for key, entry in entries.items():
        ident = entry.identity
        if key != ident.id:
            raise SystemExit(f"registry: entry key {key!r} differs from its id {ident.id!r}")
        for name in [ident.id, *ident.aliases]:
            folded = name.casefold()
            if folded in owner and owner[folded] != ident.id:
                raise SystemExit(
                    f"registry: {name!r} of portal {ident.id!r} collides with portal "
                    f"{owner[folded]!r}; no registry written"
                )
            owner[folded] = ident.id


def _serialize(entries: dict[str, RegistryEntry]) -> list[dict[str, Any]]:
    return [entries[k].model_dump(mode="json") for k in sorted(entries)]


def registry_version(entries: dict[str, RegistryEntry], today: date) -> str:
    """`<YYYY-MM-DD>-<sha256[:12] of the sorted entries>`."""
    blob = json.dumps(_serialize(entries), sort_keys=True, separators=(",", ":"))
    return f"{today.isoformat()}-{hashlib.sha256(blob.encode()).hexdigest()[:12]}"


def write_registry(entries: dict[str, RegistryEntry], out: Path, today: date) -> str:
    """Check names, then write atomically. A collision exits before anything is written."""
    check_aliases(entries)
    version = registry_version(entries, today)
    payload = {"version": version, "entries": _serialize(entries)}
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n")
    tmp.replace(out)
    return version


NON_PRODUCTION_TOKENS = frozenset({"uat", "dev", "qa", "test", "train", "staging", "integration"})


def is_production(domain: str) -> bool:
    """False when the first DNS label, split on `-`, has a non-production token, or the label
    contains `sandbox`. A whole token decides (`testament` is production); `is_eligible` (the
    milestone 0 name rule) runs first and is unchanged."""
    label = domain.lower().split(".", 1)[0]
    return "sandbox" not in label and not (NON_PRODUCTION_TOKENS & set(label.split("-")))


def views_verdict(views: dict[str, Any]) -> tuple[bool, str]:
    """Eligibility from anonymous `GET /api/views.json?limit=1` (docs/design.md, Registry 2).

    Kept: a 2xx with a JSON body; a 5xx; an httpx.TimeoutException. Dropped: a 2xx whose body is
    not JSON, a 4xx, and any other transport failure (connect, DNS, TLS, protocol), since then
    the host does not serve `/api/views` anonymously.
    """
    status = views["status"]
    if status == 0:
        if "timeout" not in views:
            raise SystemExit(f"views probe {views} lacks its failure class; re-probe it")
        if views["timeout"]:
            return True, f"kept: timeout ({views.get('error')})"
        return False, f"dropped: transport failure ({views.get('error')})"
    if 200 <= status < 300:
        if views["json"]:
            return True, "kept: 2xx JSON"
        return False, f"dropped: {status} with a body that is not JSON"
    if 500 <= status < 600:
        return True, f"kept: {status}"
    return False, f"dropped: {status}"


def expected_domain(query: dict[str, str]) -> str:
    """The `metadata.domain` every result must carry: the search_context value when present
    (it rewrites result domains), else the domains value."""
    return query.get("search_context") or query["domains"]


def check_manual(id_: str, rec: dict[str, Any]) -> None:
    """A manual override entry passes eligibility and identity or the build exits."""
    ident = rec.get("identity")
    if rec.get("errors") or not ident or not ident.get("matches") or not ident.get("complete_read"):
        raise SystemExit(f"manual override {id_!r} fails identity: {rec}")
    ok, why = views_verdict(rec["views"])
    if not ok:
        raise SystemExit(f"manual override {id_!r} fails eligibility ({why}): {rec}")


def reject_pack_overrides(overrides: dict[str, dict], pack_ids: set[str]) -> None:
    """A pack defines its own identity; an override for it is an error."""
    clash = sorted(set(overrides) & pack_ids)
    if clash:
        raise SystemExit(f"registry_overrides: {clash} are pack ids; edit the pack's portal.toml")


def _fmt(params: dict[str, str]) -> str:
    return "&".join(f"{k}={v}" for k, v in params.items())


# --------------------------------------------------------------------------- network probes


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _size(region: str, params: dict[str, str], **extra: Any) -> tuple[int, int | None]:
    status, payload = _http.get(
        f"{_http.REGIONS[region]}/api/catalog/v1", {**params, **extra, "limit": 0}
    )
    size = payload.get("resultSetSize") if status == 200 and isinstance(payload, dict) else None
    return status, size


def _query_pages(region: str, params: dict[str, str]) -> list[list[dict]]:
    """`check_identity.fetch_pages` for a query of several parameters."""
    if len(params) == 1:
        ((param, value),) = params.items()
        return fetch_pages(region, param, value)
    pages: list[list[dict]] = []
    for page in range(PAGES):
        status, payload = _http.get(
            f"{_http.REGIONS[region]}/api/catalog/v1",
            {**params, "limit": PAGE_SIZE, "offset": page * PAGE_SIZE},
        )
        if status != 200 or not payload or not payload["results"]:
            break
        pages.append(payload["results"])
        if len(payload["results"]) < PAGE_SIZE:
            break
    return pages


def _candidate(
    region: str, params: dict[str, str], pages: list[list[dict]] | None = None
) -> dict[str, Any]:
    if pages is None:
        pages = _query_pages(region, params)
    status, size = _size(region, params)
    seen = Counter(r.get("metadata", {}).get("domain", "?") for p in pages for r in p)
    expected = min(PAGES, math.ceil((size or 0) / PAGE_SIZE))
    return {
        "params": dict(params),
        "status": status,
        "result_set_size": size,
        "pages": len(pages),
        "results": sum(len(p) for p in pages),
        "matches": identity_matches(pages, expected_domain(params)),
        "domains_seen": dict(seen.most_common(5)),
        # fetch_pages stops silently on a non-200; a short read is an error to retry.
        "complete_read": status == 200 and len(pages) >= expected,
    }


def _link_hosts(pages: list[list[dict]]) -> dict[str, int]:
    counts = Counter(urlparse(r.get("link", "")).hostname or "" for p in pages for r in p)
    return dict(counts.most_common())


def _views(host: str) -> dict[str, Any]:
    d = _http.get_detail(f"https://{host}/api/views.json", {"limit": 1})
    return {
        "status": d["status"],
        "json": d["json"] is not None,
        "final_url": d["final_url"],
        "error": d["error"],
        "timeout": d["timeout"],
        "probed_at": _now(),
    }


def probe_domain(region: str, domain: str) -> dict[str, Any]:
    started = time.monotonic()
    base_pages = fetch_pages(region, "domains", domain)
    links = _link_hosts(base_pages)
    values = [domain, *[h for h in links if h and h != domain][:MAX_LINK_HOSTS]]
    cands = []
    for value in values:
        for param in ("domains", "search_context"):
            reuse = base_pages if (param, value) == ("domains", domain) else None
            cands.append(_candidate(region, {param: value}, reuse))
    chosen = choose_catalog_query(
        [
            (c["params"], c["result_set_size"] or 0, c["matches"] and c["complete_read"])
            for c in cands
        ]
    )
    rec: dict[str, Any] = {
        "kind": "enumerated",
        "domain": domain,
        "region": region,
        "probed_at": _now(),
        "link_hosts": links,
        "candidates": cands,
        "chosen": chosen,
        "errors": sum(1 for c in cands if not c["complete_read"]),
    }
    if chosen is not None:
        host, reason = choose_public_host(domain, chosen, links)
        rec["public_host"], rec["public_host_reason"] = host, reason
        rec["views"] = _views(host)
        status, rec["dataset_count"] = _size(region, chosen, only="dataset")
        rec["errors"] += int(status != 200)
    rec["seconds"] = round(time.monotonic() - started, 1)
    return rec


def probe_query(id_: str, ident: PortalIdentity, kind: str) -> dict[str, Any]:
    """Counts and identity of a pack's or manual entry's query (every parameter at once)."""
    region = ident.catalog_region
    q = dict(ident.catalog_query)
    rec: dict[str, Any] = {"kind": kind, "id": id_, "region": region, "probed_at": _now()}
    rec["query"] = q
    rec["identity"] = _candidate(region, q)
    rec["catalog_size"] = rec["identity"]["result_set_size"]
    status, rec["dataset_count"] = _size(region, q, only="dataset")
    rec["errors"] = int(status != 200) + int(not rec["identity"]["complete_read"])
    rec["views"] = _views(ident.public_host)
    return rec


_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def fetch_title(host: str) -> dict[str, Any]:
    """The site's own name for itself: site_theme `strings.site_title` and `strings.company`,
    and the home page `<title>` (whitespace collapsed, HTML entities unescaped)."""
    theme_url = f"https://{host}/api/configurations.json"
    theme_params = {"type": "site_theme", "defaultOnly": "true", "merge": "true"}
    status, payload = _http.get(theme_url, theme_params)
    props: dict[str, Any] = {}
    if status == 200 and isinstance(payload, list) and payload:
        props = {p.get("name"): p.get("value") for p in payload[0].get("properties", [])}
    home_status, text = _http.get_text(f"https://{host}/")
    m = _TITLE.search(text or "")
    return {
        "fetched_at": _now(),
        "site_theme_url": f"{theme_url}?type=site_theme&defaultOnly=true&merge=true",
        "site_theme_status": status,
        "site_title": props.get("strings.site_title"),
        "site_company": props.get("strings.company"),
        "home_url": f"https://{host}/",
        "home_status": home_status,
        "html_title": html.unescape(" ".join(m.group(1).split())) if m else None,
    }


# --------------------------------------------------------------------------- CLI


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _enumerate(path: Path, refresh: bool) -> dict[str, Any]:
    if path.exists() and not refresh:
        return json.loads(path.read_text())
    data: dict[str, Any] = {"started_at": _now(), "method": "method_b2", "regions": {}}
    for region, base in _http.REGIONS.items():
        _log(f"enumerating {region} ...")
        data["regions"][region] = r = method_b2(base)
        _log(f"  {region}: {len(r['domains'])} domains, exhausted={r.get('exhausted')}")
    data["finished_at"] = _now()
    capped = [r for r, v in data["regions"].items() if v.get("capped")]
    if capped:
        path.with_name("enumeration.capped.json").write_text(json.dumps(data, indent=1))
        raise SystemExit(f"enumeration capped or failed in {capped}; see enumeration.capped.json")
    path.write_text(json.dumps(data, indent=1) + "\n")
    return data


def _key(rec: dict[str, Any]) -> str:
    return rec.get("domain") or f"{rec['kind']}:{rec['id']}"


def _load_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    done: dict[str, dict[str, Any]] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                done[_key(rec)] = rec  # a later line (a retry) replaces an earlier one
    return done


def _append(path: Path, rec: dict[str, Any]) -> None:
    with path.open("a") as f:
        f.write(json.dumps(rec, separators=(",", ":")) + "\n")


def _rewrite_jsonl(path: Path, records: dict[str, dict[str, Any]]) -> None:
    tmp = path.with_suffix(".tmp")
    with tmp.open("w") as f:
        for key in sorted(records):
            f.write(json.dumps(records[key], separators=(",", ":")) + "\n")
    tmp.replace(path)


def _packs() -> dict[str, PortalIdentity]:
    out: dict[str, PortalIdentity] = {}
    for p in sorted(PORTALS_DIR.glob("*/portal.toml")):
        ident = load_portal(p.parent).identity
        out[ident.id] = ident
    return out


def _titles_arg(value: str) -> int | str:
    if value == "all":
        return value
    try:
        n = int(value)
    except ValueError:
        n = 0
    if n < 1:
        raise argparse.ArgumentTypeError(f"{value!r} is not a positive integer or 'all'")
    return n


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Build the portal registry (dev-only).")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--evidence", type=Path, required=True)
    ap.add_argument("--overrides", type=Path, default=OVERRIDES_PATH)
    ap.add_argument(
        "--titles",
        type=_titles_arg,
        default=0,
        help="fetch site titles of the N largest portals, or of every portal with 'all'",
    )
    ap.add_argument(
        "--refresh", action="store_true", help="re-enumerate, re-probe and re-fetch titles"
    )
    ap.add_argument(
        "--reprobe-views",
        nargs="+",
        default=[],
        metavar="DOMAIN",
        help="re-run only the /api/views probe for these catalog domains",
    )
    ap.add_argument("--today", type=date.fromisoformat, default=datetime.now(UTC).date())
    return ap


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0912, PLR0915
    args = build_parser().parse_args(argv)

    started, t0 = _now(), time.monotonic()
    _http.configure(USER_AGENT, TIMEOUT_SECONDS)
    ev: Path = args.evidence
    ev.mkdir(parents=True, exist_ok=True)

    # 1. Enumeration (cached)
    enum = _enumerate(ev / "enumeration.json", args.refresh)
    region_of: dict[str, str] = {}
    for region, r in enum["regions"].items():
        for d in r["domains"]:
            region_of.setdefault(d, region)
    catalog_domains = sorted(region_of)

    # 2a. Name rules: milestone 0's `is_eligible`, then the non-production token rule
    by_name = [d for d in catalog_domains if is_eligible(d)]
    name_rejected = [d for d in catalog_domains if not is_eligible(d)]
    non_production = [d for d in by_name if not is_production(d)]
    production = [d for d in by_name if is_production(d)]

    # 3. Identity per domain (resumable; errored probes are retried)
    probes_path = ev / "probes.jsonl"
    retries_path = ev / "probes.retries.jsonl"  # superseded probe lines, kept as evidence
    titles_path = ev / "titles.json"
    if args.refresh:
        for stale in (probes_path, retries_path, titles_path):
            stale.unlink(missing_ok=True)
    done = _load_jsonl(probes_path)
    for d in args.reprobe_views:
        old = done[d]
        _append(retries_path, old | {"superseded_at": _now(), "superseded_by": "reprobe-views"})
        done[d] = old | {"views": _views(old["public_host"])}
        _append(probes_path, done[d])
        _log(f"views {d}: {old.get('views')} -> {done[d]['views']}")
    todo = [d for d in production if d not in done or done[d]["errors"]]
    for i, d in enumerate(todo, 1):
        if d in done:
            _append(retries_path, done[d] | {"superseded_at": _now(), "superseded_by": "retry"})
        rec = probe_domain(region_of[d], d)
        done[d] = rec
        _append(probes_path, rec)
        _log(
            f"[{i}/{len(todo)}] {d}: chosen={rec['chosen']} host={rec.get('public_host')} "
            f"views={rec.get('views', {}).get('status')} errors={rec['errors']} {rec['seconds']}s"
        )

    packs = _packs()
    overrides: dict[str, dict] = (
        tomllib.loads(args.overrides.read_text()) if args.overrides.exists() else {}
    )
    reject_pack_overrides(overrides, set(packs))
    claimed = {v: pid for pid, ident in packs.items() for v in [*ident.catalog_query.values(), pid]}

    # 2b + 3. Build enumerated entries
    entries: dict[str, RegistryEntry] = {}
    unresolved: dict[str, str] = {}
    views_dropped: dict[str, str] = {}
    views_kept_on_failure: dict[str, str] = {}
    folded: dict[str, str] = {}
    host_differs: dict[str, dict[str, str]] = {}
    duplicates: list[dict[str, Any]] = []
    for d in production:
        rec = done[d]
        if rec["errors"]:
            unresolved[d] = f"probe errors ({rec['errors']}); re-run to retry"
            continue
        if rec["chosen"] is None:
            sizes = {_fmt(c["params"]): c["result_set_size"] for c in rec["candidates"]}
            unresolved[d] = f"no candidate matched on every result of three pages: {sizes}"
            continue
        host = rec["public_host"]
        if d in claimed or host in claimed:
            folded[d] = claimed.get(d) or claimed[host]
            continue
        ok, why = views_verdict(rec["views"])
        if not ok:
            views_dropped[d] = why
            continue
        if why != "kept: 2xx JSON":
            views_kept_on_failure[d] = why
        size = next(c["result_set_size"] for c in rec["candidates"] if c["params"] == rec["chosen"])
        ident = PortalIdentity.model_validate(
            _base_identity(host) | {"catalog_query": rec["chosen"], "catalog_region": rec["region"]}
        )
        entry = RegistryEntry(identity=ident, dataset_count=rec["dataset_count"], catalog_size=size)
        if host in entries:
            prev = entries[host]
            keep = entry if (size or 0) > (prev.catalog_size or 0) else prev
            duplicates.append(
                {
                    "id": host,
                    "catalog_domains": [prev.identity.catalog_domain, d],
                    "kept": _fmt(keep.identity.catalog_query),
                }
            )
            entries[host] = keep
            continue
        entries[host] = entry
        if host != d:
            host_differs[d] = {"public_host": host, "why": rec["public_host_reason"]}

    # Pack entries and manual overrides get their own probes (cached in probes.jsonl too).
    manual_ids = sorted(set(overrides) - set(entries) - set(packs))
    staged = merge_overrides(entries, {k: overrides[k] for k in manual_ids})
    to_probe = [(pid, ident, "pack") for pid, ident in packs.items()]
    to_probe += [(mid, staged[mid].identity, "manual") for mid in manual_ids]
    for pid, ident, kind in to_probe:
        key = f"{kind}:{pid}"
        if key not in done or done[key]["errors"]:
            done[key] = probe_query(pid, ident, kind)
            _append(probes_path, done[key])
            _log(f"{key}: {done[key]}")
        rec = done[key]
        if kind == "manual":
            check_manual(pid, rec)
        entries[pid] = RegistryEntry(
            identity=ident, dataset_count=rec["dataset_count"], catalog_size=rec["catalog_size"]
        )
    # Titles: the source for generated names (before overrides, so an override's name wins).
    ranked = sorted(
        (e for e in entries.values() if e.identity.id not in packs),
        key=lambda e: (-(e.catalog_size or 0), e.identity.id),
    )
    titles: dict[str, Any] = json.loads(titles_path.read_text()) if titles_path.exists() else {}
    if args.titles:
        limit = len(ranked) if args.titles == "all" else args.titles
        wanted = [e.identity.id for e in ranked[:limit]] + sorted(overrides)
        for id_ in wanted:
            if id_ not in titles and id_ in entries:
                titles[id_] = t = fetch_title(entries[id_].identity.public_host)
                _log(f"title {id_}: {t['site_title']!r} / {t['html_title']!r}")
        titles_path.write_text(json.dumps(dict(sorted(titles.items())), indent=1) + "\n")
    entries = apply_title_names(entries, titles)
    top = [e.identity.id for e in ranked[:TOP_N]]
    entries = merge_overrides(entries, overrides)
    for pid, ident in packs.items():  # the pack defines its identity
        old = entries[pid]
        entries[pid] = RegistryEntry(
            identity=ident, dataset_count=old.dataset_count, catalog_size=old.catalog_size
        )

    _rewrite_jsonl(probes_path, done)
    version = write_registry(entries, args.out, args.today)

    summary = {
        "command": "uv run python scripts/build_registry.py " + " ".join(sys.argv[1:] or []),
        "run_started_at": started,
        "run_seconds": round(time.monotonic() - t0, 1),
        "probe_seconds_total": round(
            sum(r.get("seconds", 0) for r in done.values() if r["kind"] == "enumerated"), 1
        ),
        "user_agent": USER_AGENT,
        "registry_version": version,
        "enumeration": {
            "started_at": enum["started_at"],
            "finished_at": enum["finished_at"],
            "regions": {
                r: {k: v for k, v in s.items() if k != "domains"}
                | {"domain_count": len(s["domains"])}
                for r, s in enum["regions"].items()
            },
        },
        "counts": {
            "catalog_domains": len(catalog_domains),
            "eligible_by_name": len(by_name),
            "ineligible_by_name": len(name_rejected),
            "non_production": len(non_production),
            "production": len(production),
            "identity_resolved": len(production) - len(unresolved),
            "unresolved": len(unresolved),
            "folded_into_pack": len(folded),
            "ineligible_by_views": len(views_dropped),
            "kept_on_views_5xx_or_timeout": len(views_kept_on_failure),
            "duplicate_public_hosts": len(duplicates),
            "manual_entries": len(manual_ids),
            "overrides": len(overrides),
            "registry_entries": len(entries),
        },
        "ineligible_by_name": name_rejected,
        "non_production": non_production,
        "unresolved": unresolved,
        "folded_into_pack": folded,
        "ineligible_by_views": {
            d: {"why": why, "views": done[d]["views"]} for d, why in views_dropped.items()
        },
        "kept_on_views_5xx_or_timeout": {
            d: {"why": why, "views": done[d]["views"]} for d, why in views_kept_on_failure.items()
        },
        "public_host_differs": host_differs,
        "duplicate_public_hosts": duplicates,
        "chosen_search_context": sorted(
            e.identity.id for e in entries.values() if "search_context" in e.identity.catalog_query
        ),
        f"top{TOP_N}_by_catalog_size": [[i, entries[i].catalog_size] for i in top],
        f"top{TOP_N}_without_override": [i for i in top if i not in overrides],
    }
    (ev / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    _log(json.dumps(summary["counts"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
