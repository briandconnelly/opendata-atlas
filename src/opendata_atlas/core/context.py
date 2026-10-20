"""Per-call provenance: request id and the portal's wall-clock time."""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from opendata_atlas.core.models import Source, SourcePortal

if TYPE_CHECKING:
    from opendata_atlas.portals.model import PortalContext

#: Day names by `datetime.weekday()`; fixed English, never the process locale (`strftime("%A")`).
WEEKDAYS: tuple[str, ...] = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def new_request_id() -> str:
    request_id = uuid.uuid4().hex[:16]
    _request_id.set(request_id)
    return request_id


def current_request_id() -> str:
    return _request_id.get() or new_request_id()


def local_now(
    portal: PortalContext, now: datetime
) -> tuple[str | None, Literal["multi_zone", "unknown"] | None]:
    """`now` as ISO 8601 in the portal's zone, or `(None, reason)` when it has no single zone."""
    tz = portal.tz
    if tz is not None:
        return now.astimezone(tz).isoformat(timespec="seconds"), None
    jurisdiction = portal.identity.jurisdiction
    if jurisdiction is not None and jurisdiction.level in ("state", "national"):
        return None, "multi_zone"
    return None, "unknown"


def weekday_of(now_local: str) -> str:
    """The day of the week of an ISO 8601 local time, as `local_now` formats it."""
    return WEEKDAYS[datetime.fromisoformat(now_local).weekday()]


def make_source(
    portal: PortalContext | None, *, retrieved: bool = False, now: datetime | None = None
) -> Source:
    """Provenance for a result. `portal=None` is for results that are independent of any portal.

    `now` defaults to the current time; tests pass it to pin the clock.
    """
    if now is None:
        now = datetime.now(UTC)
    retrieved_at = now.isoformat(timespec="seconds").replace("+00:00", "Z") if retrieved else None
    if portal is None:
        return Source(request_id=current_request_id(), retrieved_at=retrieved_at)
    now_local, reason = local_now(portal, now)
    identity = portal.identity
    return Source(
        request_id=current_request_id(),
        portal=SourcePortal(
            id=identity.id,
            alias=identity.aliases[0] if identity.aliases else None,
            name=identity.name,
            tier=identity.tier,
            timezone=identity.timezone,
        ),
        now_local=now_local,
        now_weekday=weekday_of(now_local) if now_local is not None else None,
        now_local_reason=reason,
        retrieved_at=retrieved_at,
    )
