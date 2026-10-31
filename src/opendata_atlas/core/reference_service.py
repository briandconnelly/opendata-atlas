"""Read static reference content for the reference tool and the resources."""

from __future__ import annotations

import hashlib
from collections import Counter
from typing import TYPE_CHECKING, Any

from opendata_atlas.core import budget
from opendata_atlas.core import cursor as cursors
from opendata_atlas.core.budget import fit, wire_size
from opendata_atlas.core.context import make_source
from opendata_atlas.core.errors import AtlasError, ErrorCode, ErrorDetails, Repair
from opendata_atlas.core.models import ReferenceEntry, ReferenceResult
from opendata_atlas.core.reference import (
    CAPABILITIES,
    CONTENT_VERSION,
    guide_uri,
    portal_uri,
    topic_uri,
    topics,
)
from opendata_atlas.portals import freshness
from opendata_atlas.portals.knowledge import pack_levels
from opendata_atlas.portals.registry import load_registry
from opendata_atlas.portals.resolve import allowed_ids, resolve_portal

if TYPE_CHECKING:
    from datetime import date

    from opendata_atlas.portals.model import PortalContext

_TOOL = "atlas_get_reference"
#: Topics read as one body, with no items.
_BODIES = {"capabilities": CAPABILITIES}
#: Tiers the portal index lists; every portal is reachable by atlas_find_portals.
_INDEXED_TIERS = ("curated", "profiled")
_CURSOR_KIND = "reference"


def _uri(portal: PortalContext | None, topic: str, item_id: str | None = None) -> str:
    if topic == "guides" and portal is not None:
        return guide_uri(portal.id, item_id)
    if topic == "portals":
        return portal_uri(portal.id if portal is not None else None)
    return topic_uri(topic, item_id)


def read(
    portal: PortalContext | None,
    topic: str,
    item_id: str | None,
    *,
    cursor: str | None = None,
    paged: bool = True,
) -> ReferenceResult:
    """`portal` is the resolved portal of topic guides; every other topic takes none.

    Topic portals resolves its `item_id` itself: with one, the result names that portal in
    `source`; without one, `source` names no portal.

    An entry list is packed to the result budget, whole entries only, and continues by
    `cursor`; a body is never paged. `paged=False` lists every entry (resources, which take
    no cursor).
    """
    offset, fingerprint = 0, None
    if cursor is not None:
        offset, fingerprint = _restore(cursor, portal, topic, item_id=item_id)
    result = _read(portal, topic, item_id)
    if result.entries is not None:
        _page(result, portal, topic, offset, fingerprint, paged=paged)
    return result


def _read(portal: PortalContext | None, topic: str, item_id: str | None) -> ReferenceResult:
    if topic == "guides" and portal is None:
        raise ValueError("topic 'guides' needs a portal")
    if topic == "portals":
        return _portals(item_id)
    table = topics(portal)
    source = make_source(portal if topic == "guides" else None)
    if topic == "index":
        listed = [t for t in table.values() if t.topic != "guides"]
        return ReferenceResult(
            topic="index",
            uri=topic_uri("reference"),
            title="opendata-atlas reference",
            summary="Topics: " + ", ".join(t.topic for t in listed) + ". Topic guides "
            "needs a portal; each portals item lists that portal's guide index.",
            version=CONTENT_VERSION,
            entries=[
                ReferenceEntry(
                    item_id=t.topic, title=t.title, description=t.summary, uri=_uri(None, t.topic)
                )
                for t in listed
            ],
            source=source,
        )
    if topic in _BODIES:
        return ReferenceResult(
            topic=topic,
            uri=topic_uri(topic),
            title=table[topic].title,
            summary=table[topic].summary,
            version=CONTENT_VERSION,
            body=_BODIES[topic],
            source=source,
        )

    entry = table[topic]
    if item_id is None:
        return ReferenceResult(
            topic=topic,
            uri=_uri(portal, topic),
            title=entry.title,
            summary=entry.summary,
            version=CONTENT_VERSION,
            entries=[
                ReferenceEntry(
                    item_id=d.item_id,
                    title=d.title,
                    description=d.description,
                    uri=_uri(portal, topic, d.item_id),
                    dataset_id=d.dataset_id,
                )
                for d in entry.documents
            ],
            source=source,
        )

    document = next((d for d in entry.documents if d.item_id == item_id), None)
    if document is None:
        raise AtlasError(
            ErrorCode.REFERENCE_NOT_FOUND,
            f"No such reference item under topic '{topic}'.",
            details=ErrorDetails(
                field="item_id",
                reason="Unknown item.",
                candidates=[d.item_id for d in entry.documents] or None,
            ),
            repair=Repair(next_step="list_items", tool=_TOOL, arguments=_list_items(portal, topic)),
        )
    return ReferenceResult(
        topic=topic,
        uri=_uri(portal, topic, item_id),
        title=document.title,
        summary=document.description,
        version=CONTENT_VERSION,
        body=document.body,
        source=source,
    )


def _list_items(portal: PortalContext | None, topic: str) -> dict[str, str]:
    """The topic's index call; a guides index names its portal (canonical id), and the
    top-level index is the canonical `atlas_get_reference({})`."""
    if topic == "index":
        return {}
    if topic == "guides" and portal is not None:
        return {"topic": topic, "portal": portal.id}
    return {"topic": topic}


# --------------------------------------------------------------------------
# Paging (docs/design.md: Tools 5, Continuation)
# --------------------------------------------------------------------------


#: Every reference cursor binds no envelope portal; the guides portal travels in its state
#: (`p`), so the topic is checked before the portal and each mismatch is named.
_CURSOR_PORTAL = "*"


def _guides_portal(portal: PortalContext | None, topic: str) -> str | None:
    return portal.id if topic == "guides" and portal is not None else None


def _restart(portal: PortalContext | None, topic: str) -> Repair:
    """Page one of the topic, for a cursor that cannot be read or continued."""
    return Repair(next_step="list_items", tool=_TOOL, arguments=_list_items(portal, topic))


def _continue(
    topic: str, portal_id: str | None, cursor: str, alternative: str | None = None
) -> Repair:
    """The continuation call: the cursor's topic, its guides portal, and the same cursor."""
    arguments: dict[str, str] = {"topic": topic}
    if topic == "guides" and portal_id is not None:
        arguments["portal"] = portal_id
    arguments["cursor"] = cursor
    return Repair(
        next_step="continue_paging", tool=_TOOL, arguments=arguments, alternative=alternative
    )


def _item_with_cursor(owner: str, owner_portal: str | None, cursor: str) -> AtlasError:
    """`item_id` with a readable cursor; the repair continues the cursor's own walk."""
    return AtlasError(
        ErrorCode.INVALID_ARGUMENT,
        f"Invalid argument combination for {_TOOL}.",
        details=ErrorDetails(
            field="item_id",
            reason="A cursor continues the topic's entries; repeat only topic and, for guides, "
            "portal.",
        ),
        repair=_continue(
            owner,
            owner_portal,
            cursor,
            alternative="To read the item, omit cursor and keep item_id.",
        ),
    )


def _malformed(portal: PortalContext | None, topic: str) -> AtlasError:
    return AtlasError(
        ErrorCode.INVALID_CURSOR,
        "The cursor is malformed.",
        details=ErrorDetails(field="cursor", reason="It does not hold a reference listing."),
        repair=_restart(portal, topic),
    )


def _mismatch(field: str, message: str, reason: str, repair: Repair) -> AtlasError:
    return AtlasError(
        ErrorCode.INVALID_CURSOR,
        message,
        details=ErrorDetails(field=field, reason=reason),
        repair=repair,
    )


def _restore(
    cursor: str, portal: PortalContext | None, topic: str, *, item_id: str | None
) -> tuple[int, str]:
    """Offset and entry-list fingerprint.

    An unreadable cursor is `invalid_cursor` and restarts page one. A readable one sent with
    `item_id` is `invalid_argument`; with another topic, then another guides portal, it is
    `invalid_cursor` naming that field. Those repairs continue the cursor's own walk
    (rulings 50, 51).
    """
    saved: dict[str, Any] = cursors.decode(
        cursor, _CURSOR_KIND, portal_id=_CURSOR_PORTAL, restart=_restart(portal, topic)
    )
    owner, owner_portal = saved.get("t"), saved.get("p")
    offset, fingerprint = saved.get("o"), saved.get("f")
    if (
        not isinstance(owner, str)
        or not (owner_portal is None or isinstance(owner_portal, str))
        or (owner == "guides") != (owner_portal is not None)
        or not isinstance(offset, int)
        or offset < 0
        or not isinstance(fingerprint, str)
    ):
        raise _malformed(portal, topic)
    if item_id is not None:
        raise _item_with_cursor(owner, owner_portal, cursor)
    proceed = _continue(owner, owner_portal, cursor)
    if owner != topic:
        raise _mismatch(
            "topic",
            f"The cursor belongs to topic `{owner}`.",
            f"Send topic `{owner}` with this cursor.",
            proceed,
        )
    if owner_portal != _guides_portal(portal, topic):
        raise _mismatch(
            "portal",
            f"The cursor belongs to portal `{owner_portal}`.",
            f"Send portal `{owner_portal}` with this cursor.",
            proceed,
        )
    return offset, fingerprint


def _fingerprint(entries: list[ReferenceEntry]) -> str:
    return hashlib.sha256("\n".join(e.item_id for e in entries).encode()).hexdigest()[:12]


def _page(
    result: ReferenceResult,
    portal: PortalContext | None,
    topic: str,
    offset: int,
    fingerprint: str | None,
    *,
    paged: bool,
) -> None:
    """Pack whole entries from `offset` to the budget, measured by wire_size (ruling 72)."""
    entries = result.entries or []
    current = _fingerprint(entries)
    if fingerprint is not None and fingerprint != current:
        raise AtlasError(
            ErrorCode.CURSOR_EXPIRED,
            "The cursor has expired: the topic's entries changed.",
            details=ErrorDetails(
                field="cursor", reason="The entry list changed since this cursor was issued."
            ),
            repair=_restart(portal, topic),
        )
    result.has_more = False
    if not paged:
        return
    rest = entries[offset:]
    state = {"t": topic, "p": _guides_portal(portal, topic), "f": current}

    def settle(count: int) -> None:
        result.entries = rest[:count]
        result.has_more = offset + count < len(entries)
        result.next_cursor = (
            cursors.encode(
                _CURSOR_KIND,
                {**state, "o": offset + count},
                portal_id=_CURSOR_PORTAL,
            )
            if result.has_more
            else None
        )

    # Read at call time so tests can lower the limit.
    fit(len(rest), settle, lambda: wire_size(result), limit=budget.RESULT_LIMIT)
    if rest and not result.entries:
        # A defect, not a caller error: an entry is a few hundred bytes. Fail rather than
        # serve an empty page whose cursor never advances.
        raise AtlasError(
            ErrorCode.INTERNAL_ERROR, "A single reference entry exceeds the result budget."
        )


# --------------------------------------------------------------------------
# Topic portals (docs/design.md: Tools 5)
# --------------------------------------------------------------------------


def _portals(item_id: str | None) -> ReferenceResult:
    meta = topics(None)["portals"]
    if item_id is not None:
        portal = resolve_portal(item_id, field="item_id")
        identity = portal.identity
        return ReferenceResult(
            topic="portals",
            uri=portal_uri(portal.id),
            title=f"{identity.name} ({portal.id})",
            summary=f"Identity, tier, knowledge by dataset, and guide index for {identity.name}.",
            version=CONTENT_VERSION,
            body=portal_summary(portal),
            source=make_source(portal),
        )
    enabled = allowed_ids()
    listed = [
        e.identity
        for e in load_registry().ordered
        if e.identity.tier in _INDEXED_TIERS
        and e.identity.status == "active"
        and (enabled is None or e.identity.id in enabled)
    ]
    return ReferenceResult(
        topic="portals",
        uri=portal_uri(),
        title=meta.title,
        summary=meta.summary + " atlas_find_portals finds every registered portal.",
        version=CONTENT_VERSION,
        entries=[
            ReferenceEntry(
                item_id=ident.id,
                title=ident.name,
                description=f"{ident.tier} portal"
                + (f", {ident.jurisdiction.level}" if ident.jurisdiction else ""),
                uri=portal_uri(ident.id),
            )
            for ident in listed
        ],
        source=make_source(None),
    )


def _dataset(portal: PortalContext, dataset_id: str) -> str:
    """A dataset's id and title; packs record titles only through their guides."""
    guide = portal.guides_by_dataset.get(dataset_id)
    return f"`{dataset_id}` ({guide.title})" if guide else f"`{dataset_id}` (no title recorded)"


def _validation_counts(portal: PortalContext, today: date) -> str:
    """How many of the pack's claims report each `validation`, worst first."""
    counts = Counter(freshness.claim_validation(portal, c, today) for c in portal.pack.claims)
    parts = [f"{counts[v]} `{v}`" for v in freshness.VALIDATION_ORDER if counts[v]]
    return "Claim `validation`: " + ", ".join(parts) + "."


def portal_summary(portal: PortalContext) -> str:
    """Markdown: identity, tier, datasets by knowledge level, and the guide index."""
    ident = portal.identity
    where = ident.jurisdiction
    today = freshness.today()
    lines = [
        f"# {ident.name}",
        "",
        "## Identity",
        f"- id: `{ident.id}`",
        f"- aliases: {', '.join(f'`{a}`' for a in ident.aliases) or 'none'}",
        f"- public host: {ident.public_host}",
        "- jurisdiction: "
        + (
            ", ".join(x for x in (where.level, where.country, where.region) if x)
            if where
            else "not recorded"
        ),
        "- calendar zone: "
        + (ident.timezone or "not recorded (its results carry no `source.now_local`)"),
        f"- tier: `{ident.tier}`",
        f"- status: `{ident.status}`",
        "",
        "## Knowledge",
    ]
    levels = pack_levels(portal, today=today)
    if levels:
        lines += [
            "Levels from this portal's pack claims alone, without the live schema. "
            "atlas_describe_dataset computes the level against the schema, so its `knowledge` "
            "can differ from this list; describe's is the level the server reports.",
        ]
        for level in ("reviewed", "profiled", "none"):
            ids = [d for d, lv in levels.items() if lv == level]
            if ids:
                lines.append(f"- {level}: " + ", ".join(_dataset(portal, d) for d in ids))
        lines.append(f"- Every other dataset: `none`. {_validation_counts(portal, today)}")
    else:
        lines.append("- No recorded knowledge: every dataset reports `none`.")
    lines += ["", "## Guides"]
    if portal.guides:
        lines += [
            f"- `{g.guide_id}` ({g.dataset_id}): {g.title}. {guide_uri(portal.id, g.guide_id)}"
            for g in portal.guides
        ]
    else:
        lines.append("- No guides for this portal.")
    return "\n".join(lines) + "\n"
