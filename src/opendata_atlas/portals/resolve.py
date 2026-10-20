"""Resolve a caller's `portal` argument to a context, enforcing the operator allowlist."""

from __future__ import annotations

import logging
import os
import re
import tomllib
from functools import cache
from typing import TYPE_CHECKING

from opendata_atlas.constants import PORTAL_PATTERN, PORTALS_ENV
from opendata_atlas.core.errors import AtlasError, ErrorCode, ErrorDetails, Repair
from opendata_atlas.portals.loader import PORTALS_DIR
from opendata_atlas.portals.registry import context_for, load_registry

if TYPE_CHECKING:
    from pathlib import Path

    from opendata_atlas.portals.model import PortalContext
    from opendata_atlas.portals.registry import RegistryEntry

log = logging.getLogger(__name__)

#: code -> (message, details.reason, repair.alternative). The one source for emitted envelopes
#: and the worked examples in core/reference.py.
PORTAL_ERROR_TEXT: dict[ErrorCode, tuple[str, str, str]] = {
    ErrorCode.PORTAL_NOT_FOUND: (
        "No portal has this id or alias.",
        "Portal ids are hostnames; aliases are short names.",
        "Search by place name with atlas_find_portals.",
    ),
    ErrorCode.PORTAL_NOT_ENABLED: (
        "This portal is not enabled on this server.",
        "The operator restricted the portal set.",
        "Choose another portal with atlas_find_portals.",
    ),
    ErrorCode.PORTAL_RETIRED: (
        "This portal is retired and no longer served.",
        "The registry marks this portal retired.",
        "Pick an active portal with atlas_find_portals.",
    ),
}

_FIND = Repair(next_step="find_portal", tool="atlas_find_portals", arguments={})


def _error(code: ErrorCode, field: str) -> AtlasError:
    """Portal failures never carry the caller's value, in any field."""
    message, reason, alternative = PORTAL_ERROR_TEXT[code]
    return AtlasError(
        code,
        message,
        details=ErrorDetails(field=field, reason=reason),
        repair=_FIND.model_copy(update={"alternative": alternative}),
    )


@cache
def _pack_dirs() -> dict[str, Path]:
    found: dict[str, Path] = {}
    for toml in sorted(PORTALS_DIR.glob("*/portal.toml")):
        found[tomllib.loads(toml.read_text())["id"]] = toml.parent
    return found


@cache
def _context(portal_id: str) -> PortalContext:
    entry = load_registry().entries[portal_id]
    return context_for(entry.identity, _pack_dirs().get(portal_id))


@cache
def _parse_allowlist(raw: str) -> frozenset[str] | None:
    """Canonical ids for one env string; logs unknown entries once per distinct string."""
    names = [n.strip() for n in raw.split(",") if n.strip()]
    if not names:
        return None
    registry = load_registry()
    ids: set[str] = set()
    for name in names:
        entry = registry.by_alias(name)
        if entry is None:
            log.warning("%s: entry %r matches no portal id or alias; ignored", PORTALS_ENV, name)
        else:
            ids.add(entry.identity.id)
    if not ids:
        log.error("%s: no entry matches a portal; every portal is blocked", PORTALS_ENV)
    return frozenset(ids)


def allowed_ids() -> frozenset[str] | None:
    """Canonical ids the operator enabled; None when the allowlist is blank or unset."""
    return _parse_allowlist(os.environ.get(PORTALS_ENV, ""))


def resolve_portal(value: str, *, field: str = "portal") -> PortalContext:
    """Precedence: bad pattern, unknown, not enabled, retired.

    `field` is the published parameter path that carried `value` (`portal`, `item_id`, or
    `uri` for a resource); every failure names it in `details.field`.
    """
    if not re.fullmatch(PORTAL_PATTERN, value):
        # On a resource the whole URI is the field; the reason names the segment instead.
        subject = "the {portal} segment" if field == "uri" else field
        raise AtlasError(
            ErrorCode.INVALID_ARGUMENT,
            f"Invalid arguments for {field}.",
            details=ErrorDetails(
                field=field,
                reason=f"{field}: {subject} must be a portal id or alias of 2 to 100 letters, "
                "digits, dots or hyphens, with no spaces.",
            ),
            # A place name ("Seattle WA") is the likely cause; atlas_find_portals resolves it.
            repair=_FIND.model_copy(
                update={"alternative": PORTAL_ERROR_TEXT[ErrorCode.PORTAL_NOT_FOUND][2]}
            ),
        )
    entry: RegistryEntry | None = load_registry().by_alias(value)
    if entry is None:
        raise _error(ErrorCode.PORTAL_NOT_FOUND, field)
    portal_id = entry.identity.id
    allowed = allowed_ids()
    if allowed is not None and portal_id not in allowed:
        raise _error(ErrorCode.PORTAL_NOT_ENABLED, field)
    if entry.identity.status == "retired":
        raise _error(ErrorCode.PORTAL_RETIRED, field)
    return _context(portal_id)
