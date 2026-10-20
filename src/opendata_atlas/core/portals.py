"""Portal search over the registry (docs/design.md: Tools 1).

Pure and offline: it reads a `Registry` and never chooses between candidates.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Literal

from opendata_atlas.constants import FIND_PORTALS_DEFAULT_PAGE_SIZE
from opendata_atlas.core import budget
from opendata_atlas.core import cursor as cursors
from opendata_atlas.core.budget import fit, wire_size
from opendata_atlas.core.context import make_source
from opendata_atlas.core.errors import AtlasError, ErrorCode, ErrorDetails, Repair
from opendata_atlas.core.models import FindPortalsResult, PortalCandidate
from opendata_atlas.portals.resolve import allowed_ids

if TYPE_CHECKING:
    from opendata_atlas.portals.model import PortalIdentity
    from opendata_atlas.portals.registry import Registry, RegistryEntry

Match = Literal["alias", "name", "place_name", "host"]

_CURSOR_KIND = "portals"
_CURSOR_PORTAL = "*"
_TIER_RANK = {"curated": 0, "profiled": 1, "generic": 2}
_MATCH_RANK: dict[Match, int] = {"alias": 0, "name": 1, "place_name": 2, "host": 3}
_TOKEN = re.compile(r"\w+")
_RESTART = Repair(
    next_step="read_paging",
    tool="atlas_get_reference",
    arguments={"topic": "soql", "item_id": "paging"},
    alternative="Resend the first-page call with all its original arguments, without cursor.",
)
_LIST_ALL = Repair(next_step="find_portal", tool="atlas_find_portals", arguments={})


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.casefold()))


def _match(entry: RegistryEntry, query: str, tokens: set[str]) -> Match | None:
    """The strongest way `query` matches the portal, or None."""
    ident = entry.identity
    needle = query.strip().casefold()
    if needle in {ident.id.casefold(), *(a.casefold() for a in ident.aliases)}:
        return "alias"
    if tokens and tokens <= _tokens(ident.name):
        return "name"
    if tokens and any(tokens <= _tokens(p) for p in ident.place_names):
        return "place_name"
    if _host_labels_match(ident.public_host, query):
        return "host"
    return None


def _host_labels_match(host: str, query: str) -> bool:
    """The query, without whitespace, equals one or more consecutive whole labels of `host`."""
    needle = "".join(query.split()).casefold()
    labels = host.casefold().split(".")
    return bool(needle) and any(
        ".".join(labels[i:j]) == needle
        for i in range(len(labels))
        for j in range(i + 1, len(labels) + 1)
    )


def _candidate(entry: RegistryEntry, match: Match | None) -> PortalCandidate:
    ident = entry.identity
    return PortalCandidate(
        id=ident.id,
        aliases=list(ident.aliases),
        name=ident.name,
        jurisdiction=ident.jurisdiction,
        tier=ident.tier,
        timezone=ident.timezone,
        dataset_count=entry.dataset_count,
        match=match,
    )


def _malformed() -> AtlasError:
    return AtlasError(
        ErrorCode.INVALID_CURSOR,
        "The cursor is malformed.",
        details=ErrorDetails(field="cursor", reason="It does not hold a portal search."),
        repair=_RESTART,
    )


def _expired(reason: str) -> AtlasError:
    return AtlasError(
        ErrorCode.CURSOR_EXPIRED,
        "The cursor has expired or the server restarted.",
        details=ErrorDetails(field="cursor", reason=reason),
        repair=_RESTART,
    )


def _restore(cursor: str, registry: Registry) -> tuple[Any, Any, Any, Any, int, int]:
    """Filters, offset and page size from a cursor; a wrong-shaped state is `invalid_cursor`."""
    saved = cursors.decode(cursor, _CURSOR_KIND, portal_id=_CURSOR_PORTAL, restart=_RESTART)
    version = saved.get("rv")
    if version is None:
        raise _malformed()
    if version != registry.version:
        raise _expired("The portal registry changed since this cursor was issued.")
    try:
        return (
            saved["q"],
            saved["lv"],
            saved["c"],
            saved["t"],
            int(saved["off"]),
            int(saved["ps"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise _malformed() from exc


def _eligible(
    ident: PortalIdentity,
    enabled: frozenset[str] | None,
    level: str | None,
    country: str | None,
    tier: str | None,
) -> bool:
    if ident.status != "active" or (enabled is not None and ident.id not in enabled):
        return False
    if tier is not None and ident.tier != tier:
        return False
    jurisdiction = ident.jurisdiction
    if level is not None and (jurisdiction is None or jurisdiction.level != level):
        return False
    return country is None or (jurisdiction is not None and jurisdiction.country == country)


def find_portals(
    registry: Registry,
    *,
    query: str | None,
    level: str | None,
    country: str | None,
    tier: str | None,
    page_size: int | None,
    cursor: str | None,
) -> FindPortalsResult:
    offset = 0
    if cursor is not None:
        query, level, country, tier, offset, saved_size = _restore(cursor, registry)
        page_size = page_size or saved_size
    elif query is not None and not _tokens(query):
        raise AtlasError(
            ErrorCode.INVALID_ARGUMENT,
            "Invalid arguments for atlas_find_portals.",
            details=ErrorDetails(
                field="query", reason="query: must contain at least one letter or digit."
            ),
            repair=_LIST_ALL,
        )
    page_size = page_size or FIND_PORTALS_DEFAULT_PAGE_SIZE
    country = country.upper() if country else None

    tokens = _tokens(query) if query else set()
    enabled = allowed_ids()
    ranked: list[tuple[tuple[int, int, str], PortalCandidate]] = []
    for entry in registry.entries.values():
        ident = entry.identity
        if not _eligible(ident, enabled, level, country, tier):
            continue
        match = None
        if query is not None:
            match = _match(entry, query, tokens)
            if match is None:
                continue
        strength = _MATCH_RANK[match] if match else 0
        ranked.append(((strength, _TIER_RANK[ident.tier], ident.id), _candidate(entry, match)))
    ranked.sort(key=lambda pair: pair[0])

    page = [c for _, c in ranked[offset : offset + page_size]]
    result = FindPortalsResult(
        candidates=[],
        has_more=False,
        registry_version=registry.version,
        source=make_source(None),
    )
    saved_state: dict[str, Any] = {
        "q": query,
        "lv": level,
        "c": country,
        "t": tier,
        "ps": page_size,
        "rv": registry.version,
    }

    def settle(count: int) -> None:
        result.candidates = page[:count]
        result.has_more = offset + count < len(ranked)
        result.next_cursor = (
            cursors.encode(
                _CURSOR_KIND, {**saved_state, "off": offset + count}, portal_id=_CURSOR_PORTAL
            )
            if result.has_more
            else None
        )

    # Whole candidates, measured by wire_size (ruling 72); read at call time so tests can
    # lower the limit.
    fit(len(page), settle, lambda: wire_size(result), limit=budget.RESULT_LIMIT)
    if page and not result.candidates:
        # A defect, not a caller error: a candidate is about 540 bytes. Fail as
        # `internal_error` rather than serve an empty page whose cursor never advances.
        raise AtlasError(
            ErrorCode.INTERNAL_ERROR, "A single portal candidate exceeds the result budget."
        )
    return result
