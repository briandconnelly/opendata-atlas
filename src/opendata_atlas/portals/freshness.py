"""Runtime freshness: a claim's validation by the server's clock (docs/design.md: Validation
state and freshness).

A claim is `stale` when its last check is more than `STALE_AFTER_DAYS` days old. Stale
claims degrade asymmetrically: a verdict that vouches for the data (an `ok` reliability, a
column timezone, a reviewed placeholder declaration) stops vouching, while a warning
(`partial`, `unreliable`) is kept.

Read the clock as `freshness.today()`, through the module attribute, so tests can pin it.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from opendata_atlas.portals.model import Claim, PortalContext, Validation

STALE_AFTER_DAYS = 180

#: Worst first: `combine` reports the first of these any input holds.
VALIDATION_ORDER: tuple[Validation, ...] = (
    "contradicted",
    "stale",
    "inconclusive",
    "unchecked",
    "passed",
)


def today() -> date:
    """The server's clock, as a UTC date."""
    return datetime.now(UTC).date()


def claim_validation(portal: PortalContext, claim: Claim, today: date) -> Validation:
    """`unchecked` for a claim with no assertion or no check entry; `stale` for a check more
    than `STALE_AFTER_DAYS` days old; else the check's outcome.

    A `checked_at` after `today` (a clock behind the drift run's) is fresh.
    """
    check = portal.checks.get(claim.id) if claim.assertion else None
    if check is None:
        return "unchecked"
    if (today - check.checked_at).days > STALE_AFTER_DAYS:
        return "stale"
    return check.outcome


def degraded(portal: PortalContext, claim: Claim, today: date) -> bool:
    """True when the claim is stale and its verdict is one that degrades to unknown.

    Those are an `ok` place-field or region-layer reliability, a column timezone, and a
    reviewed `placeholder_share` declaration. A stale place field's placeholder declarations
    degrade in describe (`_declared_placeholders` uses `claim_validation`), not here.
    """
    if claim_validation(portal, claim, today) != "stale":
        return False
    interp = claim.interpretation
    if claim.kind in ("place_field", "region_layer"):
        return interp is not None and interp.reliability == "ok"
    if claim.kind == "column_timezone":
        return interp is not None and interp.timezone is not None
    if claim.kind == "placeholder_share":
        return claim.reviewed and bool(claim.placeholders)
    return False


def combine(validations: Iterable[Validation]) -> Validation:
    """The worst of `validations`, in the order contradicted, stale, inconclusive, unchecked,
    passed; `unchecked` when there are none."""
    seen = set(validations)
    return next((v for v in VALIDATION_ORDER if v in seen), "unchecked")
