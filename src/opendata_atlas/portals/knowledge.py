"""Knowledge levels and notices (docs/design.md: Knowledge levels).

A claim is reviewed when it carries a reviewer's interpretation (`Claim.reviewed`); any
other claim is a profiler observation. Levels are computed on the server's clock: a claim
the freshness rule degrades (`freshness.degraded`) counts as neither reviewed nor an
observation for every level, and as unreviewed for the primary time column, so staleness
never raises a level, and `validation` is the worst of the covering claims'
(`freshness.combine`).

**Primary time column:** the column describe reports as `data_coverage`: every time-typed
column with a reviewed timezone claim, else the first time-typed column in schema order.

**Knowledge-bearing columns:** place fields (reviewed text fields and computed-region
columns) and time-typed columns. Only these can make a query carry a notice; a plain text
or number column has no place or time meaning to vouch for. A time column counts as reviewed
only through a reviewed timezone claim, never through another claim on the column.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from opendata_atlas.core.models import Knowledge, KnowledgeNotice
from opendata_atlas.portals import freshness

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence
    from datetime import date

    from opendata_atlas.portals.model import Claim, KnowledgeLevel, PortalContext, Validation

#: The shared cross-portal placeholder vocabulary, migrated from `seattle-open-data`'s
#: `PLACEHOLDER_VALUES`. It only flags candidates: a value leaves `values` and
#: `assigned_fraction` only when a reviewed claim declares it for that column.
SHARED_PLACEHOLDERS = frozenset({"-", "UNKNOWN", "NULL", "OOJ", "FK ERROR", "X", "0", ""})

#: Names listed per kind in a notice before the rest are counted.
_MAX_NAMED = 3


def _effective(portal: PortalContext, claim: Claim, today: date) -> bool:
    """Reviewed, and not degraded by the freshness rule."""
    return claim.reviewed and not freshness.degraded(portal, claim, today)


def primary_time(
    portal: PortalContext, dataset_id: str, time_columns: Sequence[str], *, today: date
) -> list[str]:
    """The primary time column(s): those with a reviewed timezone, else the first one."""
    reviewed = [c for c in time_columns if timezone_reviewed(portal, dataset_id, c, today)]
    return reviewed or list(time_columns[:1])


def timezone_reviewed(portal: PortalContext, dataset_id: str, column: str, today: date) -> bool:
    claim = portal.pack.column_timezone(dataset_id, column)
    return bool(
        claim
        and claim.interpretation
        and claim.interpretation.timezone
        and not freshness.degraded(portal, claim, today)
    )


def place_reviewed(
    portal: PortalContext, dataset_id: str, column: str, layer_id: str | None, today: date
) -> bool:
    """A place interpretation covers the column: its own `place_field` claim, or, for a
    computed-region column, its layer's `region_layer` claim, reviewed and not degraded."""
    claims = [portal.pack.place_fields(dataset_id).get(column)]
    if layer_id:
        claims.append(portal.pack.region_layer(layer_id))
    return any(c is not None and _effective(portal, c, today) for c in claims)


def _covering(
    portal: PortalContext, dataset_id: str, column: str, layer_id: str | None
) -> list[Claim]:
    pack = portal.pack
    claims = [c for c in pack.claims if c.scope.dataset == dataset_id and c.scope.column == column]
    layer = pack.region_layer(layer_id) if layer_id else None
    return [*claims, layer] if layer is not None else claims


def _validation(portal: PortalContext, claims: Iterable[Claim], today: date) -> Validation:
    return freshness.combine(freshness.claim_validation(portal, c, today) for c in claims)


def column_knowledge(
    portal: PortalContext,
    dataset_id: str,
    column: str,
    *,
    layer_id: str | None = None,
    today: date,
) -> Knowledge | None:
    """The column's level, or None when no claim covers it.

    `layer_id` names a computed-region column's layer, whose portal-level claim covers it.
    """
    claims = _covering(portal, dataset_id, column, layer_id)
    if not claims:
        return None
    return Knowledge(
        level=_level(portal, claims, today), validation=_validation(portal, claims, today)
    )


def _level(portal: PortalContext, claims: list[Claim], today: date) -> KnowledgeLevel:
    """`reviewed` if any claim is effectively reviewed, else `profiled` if any is an
    observation, else `none`. A degraded claim is neither (Ruling 42), so staleness never
    raises a level."""
    if any(_effective(portal, c, today) for c in claims):
        return "reviewed"
    return "profiled" if any(not c.reviewed for c in claims) else "none"


def _reviewed(
    portal: PortalContext, dataset_id: str, column: str, layer_id: str | None, today: date
) -> bool:
    known = column_knowledge(portal, dataset_id, column, layer_id=layer_id, today=today)
    return known is not None and known.level == "reviewed"


def _has_unit(portal: PortalContext, dataset_id: str, today: date) -> bool:
    return any(
        c.kind == "unit_of_observation"
        and c.scope.dataset == dataset_id
        and _effective(portal, c, today)
        for c in portal.pack.claims
    )


def dataset_knowledge(
    portal: PortalContext,
    dataset_id: str,
    knowledge_bearing: list[str],
    primary_time: str | None,
    *,
    layers: Mapping[str, str] | None = None,
    today: date,
) -> Knowledge:
    """`reviewed` when the dataset has a reviewed unit-of-observation claim and a reviewed
    claim for every place field it exposes and for its primary time column.

    `knowledge_bearing` lists the exposed place-field columns; `layers` maps each
    computed-region one to its layer id. Time columns other than `primary_time` do not
    affect the dataset's level. Short of the rule: `profiled` when any claim on the dataset
    or its layers is an unreviewed observation, else `none`; a degraded claim counts as
    neither reviewed nor an observation.
    `validation` combines every claim on the dataset and its layers.
    """
    if layers is None:
        if any(c.startswith(":") for c in knowledge_bearing):
            raise ValueError("computed-region columns need `layers` to find their layer claims")
        layers = {}
    pack = portal.pack
    claims = [c for c in pack.claims if c.scope.dataset == dataset_id]
    claims += [
        layer
        for layer_id in sorted(set(layers.values()))
        if (layer := pack.region_layer(layer_id)) is not None
    ]
    validation = _validation(portal, claims, today)
    places = all(_reviewed(portal, dataset_id, c, layers.get(c), today) for c in knowledge_bearing)
    time = primary_time is None or timezone_reviewed(portal, dataset_id, primary_time, today)
    if _has_unit(portal, dataset_id, today) and places and time:
        return Knowledge(level="reviewed", validation=validation)
    # A degraded claim is neither reviewed nor an observation: it can lower, never raise.
    observed = any(not c.reviewed for c in claims)
    return Knowledge(level="profiled" if observed else "none", validation=validation)


def knowledge_notice(
    portal: PortalContext,
    dataset_id: str,
    *,
    places: Mapping[str, str | None],
    time_columns: Sequence[str],
    referenced: Iterable[str],
    today: date,
    text_filters: Sequence[str] = (),
) -> KnowledgeNotice | None:
    """The notice a query result carries, or None.

    It fires when the dataset is not `reviewed`, or when a referenced knowledge-bearing
    column has no reviewed claim or a stale covering claim. `places` maps each place-field
    column to its layer id (None for a text field); `referenced` holds the names the agent
    wrote, as the coverage-warning scan reads them. On an unreviewed dataset the message
    names every gap in the rule, plus any referenced column without a reviewed claim. A gap
    with a stale covering claim is named as stale.

    `text_filters` names the text columns the query's where clause or group_by read
    (ruling 69). While no place field is backed by a reviewed, non-degraded claim, they fire
    the notice even on a `reviewed` dataset, and the message adds a sentence naming them
    (docs/design.md: Place fields, Exploratory path).
    """
    primary = primary_time(portal, dataset_id, time_columns, today=today)
    layers = {c: layer for c, layer in places.items() if layer}
    dataset = dataset_knowledge(
        portal,
        dataset_id,
        list(places),
        primary[0] if primary else None,
        layers=layers,
        today=today,
    )
    used = set(referenced)
    rule_gaps = dataset.level != "reviewed"
    no_unit = rule_gaps and not _has_unit(portal, dataset_id, today)

    def stale(column: str, layer_id: str | None = None) -> bool:
        claims = _covering(portal, dataset_id, column, layer_id)
        return any(freshness.claim_validation(portal, c, today) == "stale" for c in claims)

    place_gaps = [
        c
        for c, layer in places.items()
        if ((rule_gaps or c in used) and not _reviewed(portal, dataset_id, c, layer, today))
        or (c in used and stale(c, layer))
    ]
    time_gaps = [
        c
        for c in time_columns
        if (
            ((rule_gaps and c in primary) or c in used)
            and not timezone_reviewed(portal, dataset_id, c, today)
        )
        or (c in used and stale(c))
    ]
    unbacked = bool(text_filters) and not any(
        _reviewed(portal, dataset_id, c, layer, today) for c, layer in places.items()
    )
    if not (no_unit or place_gaps or time_gaps or unbacked):
        return None
    stale_places = [c for c in place_gaps if stale(c, places[c])]
    stale_times = [c for c in time_gaps if stale(c)]
    sentences = []
    if no_unit or place_gaps or time_gaps:
        sentences.append(
            _message(
                no_unit,
                [c for c in place_gaps if c not in stale_places],
                [c for c in time_gaps if c not in stale_times],
                stale_places,
                stale_times,
            )
        )
    named = [c for c in text_filters if c not in place_gaps]
    if unbacked and named:
        sentences.append(_text_sentence(named))
    sentences.append(GAP_OFFER)
    message = " ".join(sentences)
    return KnowledgeNotice(level=dataset.level, message=message)


#: Ends every fired notice (ruling 68): the head rule's knowledge-gap offer, at the point of use.
GAP_OFFER = (
    "When you caveat a gap named here, also offer the user a knowledge-gap issue "
    "(capabilities ## Knowledge gaps); never file one unasked."
)


def _listed(names: Sequence[str]) -> str:
    shown = ", ".join(f"`{n}`" for n in names[:_MAX_NAMED])
    more = f" (+{len(names) - _MAX_NAMED} more)" if len(names) > _MAX_NAMED else ""
    return f"{shown}{more}"


def _named(noun: str, names: list[str]) -> str:
    return f"{noun}{'s' if len(names) > 1 else ''} {_listed(names)}"


def _text_sentence(names: Sequence[str]) -> str:
    """Names the text columns that no place-gap sentence already named."""
    if len(names) == 1:
        lead, claim, pronoun = "Text column", "is not a reviewed place field", "it"
    else:
        lead, claim, pronoun = "Text columns", "are not reviewed place fields", "one"
    return (
        f"{lead} {_listed(names)} filtered or grouped here {claim}; if your answer uses "
        f"{pronoun} as an area, say in the answer that its meaning and completeness are "
        "unverified."
    )


def _series(items: list[str], conjunction: str) -> str:
    if len(items) < 3:
        return f" {conjunction} ".join(items)
    return f"{', '.join(items[:-1])}, {conjunction} {items[-1]}"


def _message(
    no_unit: bool,
    place_gaps: list[str],
    time_gaps: list[str],
    stale_places: list[str],
    stale_times: list[str],
) -> str:
    """One sentence: what no reviewed claim covers, what rests on stale checks, then the
    caveat the answer must carry."""
    subjects: list[str] = []
    stale: list[str] = []
    effects: list[tuple[str, bool]] = []  # (effect, plural)
    if no_unit:
        subjects.append("the unit of observation (what one row is)")
        effects.append(("what each row counts", False))
    if place_gaps:
        subjects.append(_named("place field", place_gaps))
    if stale_places:
        stale.append(_named("place field", stale_places))
    if place_gaps or stale_places:
        effects.append(("area breakdowns", True))
    if time_gaps:
        subjects.append(_named("time column", time_gaps))
    if stale_times:
        stale.append(_named("time column", stale_times))
    if time_gaps or stale_times:
        effects.append(("timestamp timezones", True))
    clauses: list[str] = []
    if subjects:
        clauses.append(f"No reviewed claim covers {_series(subjects, 'or')}")
    if stale:
        lead = "the" if clauses else "The"
        clauses.append(
            f"{lead} checks on {_series(stale, 'and')} are stale (last run over "
            f"{freshness.STALE_AFTER_DAYS} days ago)"
        )
    verb = "are" if len(effects) > 1 or effects[0][1] else "is"
    return (
        f"{', and '.join(clauses)}; "
        f"say in the answer that {_series([e for e, _ in effects], 'and')} {verb} unverified."
    )


_REGION_PREFIX = ":@computed_region_"


def pack_levels(portal: PortalContext, *, today: date) -> dict[str, KnowledgeLevel]:
    """Each dataset the pack's claims name, at the level those claims alone support.

    Offline, for the portal summary (topic `portals`), without the live schema:
    - The place fields are the dataset's `place_field` claim columns. Each of its
      `:@computed_region_*` ones maps to its own region layer by Socrata's column naming
      (`:@computed_region_abcd_1234` is layer `abcd-1234`); describe reads the layer from
      the column's metadata instead. Other `:` columns are dropped.
    - A dataset with no computed-region claim falls back to every region layer in the pack,
      since its schema may expose any of them.
    - The primary time column is one with a timezone claim. A dataset with no timezone
      claim is never `reviewed` here, since its schema may hold a time column.

    Describe, which reads the schema, governs. Caveats:
    - the mapping relies on Socrata's column naming;
    - a dataset with claims on only some of its computed-region columns under-counts its
      layers, so the summary can read higher than describe;
    - the fallback counts only the pack's layers, so a schema column on a layer the pack
      never claims lowers describe and not the summary, which can read higher.
    The robust alternative is a `layer` in the scope of the profiler's fill claim.
    """
    pack = portal.pack
    pack_layers = {
        f":layer:{c.scope.layer}": c.scope.layer
        for c in pack.claims
        if c.kind == "region_layer" and c.scope.layer
    }
    out: dict[str, KnowledgeLevel] = {}
    for dataset_id in sorted({c.scope.dataset for c in pack.claims if c.scope.dataset}):
        claimed = pack.place_fields(dataset_id)
        own = [c for c in claimed if c.startswith(_REGION_PREFIX)]
        layers = {c: c.removeprefix(_REGION_PREFIX).replace("_", "-") for c in own} or pack_layers
        places = [c for c in claimed if not c.startswith(":")] + list(layers)
        timed = [
            c.scope.column
            for c in pack.claims
            if c.kind == "column_timezone" and c.scope.dataset == dataset_id and c.scope.column
        ]
        primary = primary_time(portal, dataset_id, timed, today=today)
        # An unseen schema may hold a time column: name one no claim covers.
        time_column = primary[0] if primary else "\0unknown"
        out[dataset_id] = dataset_knowledge(
            portal, dataset_id, places, time_column, layers=layers, today=today
        ).level
    return out
