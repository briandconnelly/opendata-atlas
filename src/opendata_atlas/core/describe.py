"""Dataset inspection (docs/design.md: Tools 3).

Live aggregates run concurrently under one deadline; a slow dataset degrades to
cached or absent values with an explicit status, never to a silent zero.
"""

from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING, Any, Literal

import anyio

from opendata_atlas.constants import (
    DESCRIBE_AGGREGATE_TIMEOUT_SECONDS,
    DESCRIBE_DEADLINE_SECONDS,
    GEO_TYPES,
    TIME_TYPES,
)
from opendata_atlas.core import cache
from opendata_atlas.core import cursor as cursors
from opendata_atlas.core.budget import RESULT_LIMIT, payload_size
from opendata_atlas.core.catalog import queryability
from opendata_atlas.core.context import make_source
from opendata_atlas.core.errors import (
    AtlasError,
    ErrorCode,
    ErrorDetails,
    Repair,
)
from opendata_atlas.core.http import shape_error
from opendata_atlas.core.models import (
    Column,
    ColumnStats,
    Coverage,
    DescribeResult,
    Detail,
    ExampleQuery,
    GeoColumn,
    GeoUnusable,
    PlaceField,
    PlaceholderValue,
    PlaceValue,
    RowCount,
    TimeSemantics,
    UnitOfObservation,
)
from opendata_atlas.core.reference import guide_uri
from opendata_atlas.core.soql import identifier
from opendata_atlas.core.text import clean, html_to_text, strip_control
from opendata_atlas.portals import freshness
from opendata_atlas.portals.knowledge import (
    SHARED_PLACEHOLDERS,
    column_knowledge,
    dataset_knowledge,
    primary_time,
)
from opendata_atlas.portals.model import Document, ManualObservation, MetadataProbe, SoqlProbe

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterable
    from datetime import date

    from opendata_atlas.core.http import SodaClient
    from opendata_atlas.core.models import Knowledge
    from opendata_atlas.portals.model import Claim, Evidence, Interpretation, PortalContext

_COORDINATE = re.compile(r"(^|_)(lat|latitude|lon|lng|long|longitude)$")
_LABEL_FETCH_TIMEOUT = 5.0
_MAX_VALUES = 100
_PLACE_CONCURRENCY = 4
#: Columns per page before the byte budget trims it: full detail carries descriptions and stats.
_PAGE_COLUMNS: dict[str, int] = {"summary": 100, "full": 25}

#: A column cursor cannot carry the original call's arguments back, and a describe of the
#: same dataset with fewer would answer a different question, so the repair reads how to
#: restart instead.
_RESTART = Repair(
    next_step="read_paging",
    tool="atlas_get_reference",
    arguments={"topic": "soql", "item_id": "paging"},
    alternative="Resend the first-page call with all its original arguments, without "
    "column_cursor.",
)


class _Outcome:
    """Result of one bounded upstream aggregate."""

    def __init__(self) -> None:
        self.value: Any = None
        self.status: Literal["ok", "timeout", "unavailable"] = "timeout"
        self.error: AtlasError | None = None


#: Failures the caller must see as the result of describe itself, not as a degraded field.
_ACTIONABLE = frozenset(
    {ErrorCode.APP_TOKEN_REJECTED, ErrorCode.UPSTREAM_FORBIDDEN, ErrorCode.RATE_LIMITED}
)


async def _bounded(outcome: _Outcome, work: Callable[..., Awaitable[Any]], *args: Any) -> None:
    try:
        outcome.value = await work(*args)
        outcome.status = "ok"
    except AtlasError as exc:
        outcome.error = exc
        outcome.status = (
            "timeout" if exc.envelope.code == ErrorCode.QUERY_TIMEOUT else "unavailable"
        )


async def _limited(
    limiter: anyio.CapacityLimiter,
    outcome: _Outcome,
    work: Callable[..., Awaitable[Any]],
    *args: Any,
) -> None:
    # The coroutine is created only after a slot frees, so a deadline never strands one.
    async with limiter:
        await _bounded(outcome, work, *args)


def _raise_actionable(outcomes: Iterable[_Outcome]) -> None:
    for outcome in outcomes:
        if outcome.error is not None and outcome.error.envelope.code in _ACTIONABLE:
            raise outcome.error


async def describe(
    client: SodaClient, portal: PortalContext, *, dataset_id: str, **kwargs: Any
) -> DescribeResult:
    """Bounded as a whole; the per-phase deadlines inside keep partial results useful."""
    try:
        with anyio.fail_after(DESCRIBE_DEADLINE_SECONDS):
            return await _describe(client, portal, dataset_id=dataset_id, **kwargs)
    except TimeoutError as exc:
        raise AtlasError(
            ErrorCode.QUERY_TIMEOUT,
            f"Describe did not finish within {DESCRIBE_DEADLINE_SECONDS:.0f} s.",
        ) from exc


async def _describe(
    client: SodaClient,
    portal: PortalContext,
    *,
    dataset_id: str,
    column_query: str | None,
    sample_rows: int,
    detail: Detail | None,
    column_cursor: str | None = None,
) -> DescribeResult:
    column_query, detail, offset, expected = _continuation(
        column_cursor, portal.id, dataset_id, column_query, detail
    )
    today = freshness.today()
    # Always fresh: describe is where an agent checks the schema, and it reseeds query's copy.
    view = await cache.fresh_view(client, portal, dataset_id)
    require_queryable(view, dataset_id, portal.id)

    # Filter views inherit their parent's curated facts.
    facts_id = view.get("modifyingViewUid") or dataset_id
    all_columns = view.get("columns") or []
    data_columns = [c for c in all_columns if not str(c.get("fieldName", "")).startswith(":")]
    time_columns = [c for c in data_columns if c.get("dataTypeName") in TIME_TYPES]
    coverage_columns = _coverage_columns(portal, facts_id, time_columns, today)
    places = place_specs(portal, facts_id, all_columns, today=today)
    guide = portal.guides_by_dataset.get(facts_id)

    row_count = _Outcome()
    coverage = {c["fieldName"]: _Outcome() for c in coverage_columns}
    sample = _Outcome()
    # Two phases: on an 11M-row police dispatch dataset, running place-field grouping alongside
    # the row count made even the row count time out.
    with anyio.move_on_after(DESCRIBE_AGGREGATE_TIMEOUT_SECONDS):
        async with anyio.create_task_group() as tg:
            tg.start_soon(_bounded, row_count, _count, client, portal, dataset_id)
            for name, outcome in coverage.items():
                tg.start_soon(_bounded, outcome, _min_max, client, portal, dataset_id, name)
            if sample_rows:
                tg.start_soon(
                    _bounded,
                    sample,
                    _sample,
                    client,
                    portal,
                    dataset_id,
                    data_columns,
                    sample_rows,
                )
    _raise_actionable([row_count, sample, *coverage.values()])

    place_stats = {p["column"]: _Outcome() for p in places} if detail == "full" else {}
    if place_stats:
        limiter = anyio.CapacityLimiter(_PLACE_CONCURRENCY)
        with anyio.move_on_after(DESCRIBE_AGGREGATE_TIMEOUT_SECONDS):
            async with anyio.create_task_group() as tg:
                for name, outcome in place_stats.items():
                    tg.start_soon(
                        _limited, limiter, outcome, _value_groups, client, portal, dataset_id, name
                    )
        _raise_actionable(place_stats.values())

    labels = await _region_labels(client, portal, places, place_stats) if place_stats else {}

    layers = {p["column"]: p["layer_id"] for p in places if p["source"] == "computed_region"}
    columns = [
        _column(
            c,
            detail,
            column_knowledge(
                portal, facts_id, c["fieldName"], layer_id=layers.get(c["fieldName"]), today=today
            ),
        )
        for c in data_columns
        if column_query is None or _matches(c, column_query)
    ]
    fingerprint = _fingerprint(columns)
    if expected is not None and fingerprint != expected:
        raise AtlasError(
            ErrorCode.CURSOR_EXPIRED,
            "The dataset's columns changed since the cursor was issued.",
            details=ErrorDetails(
                field="column_cursor", reason="The cursor's offsets no longer match the schema."
            ),
            repair=_RESTART,
        )
    result = DescribeResult(
        dataset_id=dataset_id,
        title=clean(view.get("name"), limit=200) or dataset_id,
        queryability="supported",
        row_count=_row_count(row_count, all_columns),
        data_coverage=[_coverage(c, coverage[c["fieldName"]]) for c in coverage_columns],
        columns=[],
        columns_total=len(columns),
        has_more_columns=False,
        stats_available=any(c.get("cachedContents") for c in data_columns),
        place_fields=[
            _place_field(
                p,
                place_stats.get(p["column"]),
                labels,
                **_declared_placeholders(portal, facts_id, p, today),
            )
            for p in places
        ],
        geo_columns=[
            GeoColumn(column=c["fieldName"], type=c["dataTypeName"])
            for c in data_columns
            if c.get("dataTypeName") in GEO_TYPES
        ],
        geo_unusable=_geo_unusable(data_columns) or None,
        time_semantics=[_time(portal, facts_id, c, today) for c in time_columns],
        knowledge=dataset_knowledge(
            portal,
            facts_id,
            [p["column"] for p in places],
            coverage_columns[0]["fieldName"] if coverage_columns else None,
            layers=layers,
            today=today,
        ),
        unit_of_observation=_unit(portal, facts_id),
        sample_rows=_fill(sample.value, data_columns)
        if sample_rows and sample.status == "ok"
        else None,
        guide_uri=guide_uri(portal.id, guide.guide_id) if guide else None,
        # Examples name their dataset: a filter view links its parent's guide, without examples.
        example_queries=[
            ExampleQuery(question=e.question, arguments=e.arguments) for e in guide.examples
        ]
        if guide and guide.dataset_id == dataset_id
        else None,
        source=make_source(portal, retrieved=True),
    )
    _page_columns(
        result,
        columns,
        offset=offset,
        state={"ds": dataset_id, "q": column_query, "d": detail, "f": fingerprint},
        portal=portal,
        too_large=lambda even_one: _too_large(
            portal.id,
            dataset_id,
            column_query=column_query,
            detail=detail,
            sample_rows=sample_rows,
            even_one=even_one,
            continued=column_cursor is not None,
        ),
    )
    return result


def _fingerprint(columns: list[Column]) -> str:
    """A short hash of the matching column names, in order, so a changed schema voids cursors."""
    return hashlib.sha256("\0".join(c.name for c in columns).encode()).hexdigest()[:12]


def _continuation(
    column_cursor: str | None,
    portal_id: str,
    dataset_id: str,
    column_query: str | None,
    detail: Detail | None,
) -> tuple[str | None, Detail, int, str | None]:
    """The `column_query`, `detail`, first column offset and schema fingerprint to expect.

    A cursor supplies omitted arguments.
    """
    if column_cursor is None:
        return column_query, detail or "summary", 0, None
    state = cursors.decode(
        column_cursor, "columns", portal_id=portal_id, restart=_RESTART, field="column_cursor"
    )
    bound = {"ds": dataset_id, "q": column_query, "d": detail}
    for key, given in bound.items():
        if given is not None and given != state.get(key):
            raise AtlasError(
                ErrorCode.INVALID_CURSOR,
                "The cursor was issued for a different describe call.",
                details=ErrorDetails(
                    field="column_cursor",
                    reason="dataset_id, column_query and detail must match the cursor.",
                ),
                repair=_RESTART,
            )
    if not {"q", "d", "o", "f"} <= state.keys():
        raise AtlasError(
            ErrorCode.INVALID_CURSOR,
            "The cursor uses an unsupported format.",
            details=ErrorDetails(
                field="column_cursor", reason="It lacks the fields a columns cursor carries."
            ),
            repair=_RESTART,
        )
    return state["q"], state["d"], int(state["o"]), state["f"]


def _page_columns(
    result: DescribeResult,
    columns: list[Column],
    *,
    offset: int,
    state: dict[str, Any],
    portal: PortalContext,
    too_large: Callable[[bool], AtlasError],
) -> None:
    """Settle `result.columns` on the most columns whose complete serialized result fits.

    The first page lists every column when they all fit. Otherwise a page holds at most
    the detail's page size, trimmed by bytes. The sections that are not paged are already
    in `result`, so they count against the budget on every page.
    """
    rest = columns[offset:]

    def settle(count: int) -> None:
        result.columns = rest[:count]
        more = count < len(rest)
        result.has_more_columns = more
        result.next_column_cursor = (
            cursors.encode("columns", {**state, "o": offset + count}, portal_id=portal.id)
            if more
            else None
        )

    settle(len(rest))
    if offset == 0 and payload_size(result) <= RESULT_LIMIT:
        return
    low, high = 0, min(len(rest), _PAGE_COLUMNS[state["d"]])
    # Largest count that fits; size grows with the count, so bisect.
    while low < high:
        middle = (low + high + 1) // 2
        settle(middle)
        if payload_size(result) <= RESULT_LIMIT:
            low = middle
        else:
            high = middle - 1
    settle(low)
    if (rest and low == 0) or payload_size(result) > RESULT_LIMIT:
        # The sections alone overflow when they do so with no column and no cursor.
        result.columns, result.has_more_columns, result.next_column_cursor = [], False, None
        raise too_large(payload_size(result) <= RESULT_LIMIT)


def _too_large(
    portal_id: str,
    dataset_id: str,
    *,
    column_query: str | None,
    detail: Detail,
    sample_rows: int,
    even_one: bool,
    continued: bool,
) -> AtlasError:
    """Only a smaller result can fit, so the repair shrinks one thing and keeps the question.

    Full detail gives way to summary, then samples to none; a summary without samples has
    nothing left to drop. Narrowing `column_query` cannot help: it changes only `columns`.
    """
    unpaged = (
        "place_fields, geo_columns, time_semantics, knowledge and unit_of_observation are not paged"
    )
    kept: dict[str, Any] = {} if column_query is None else {"column_query": column_query}
    field, next_step, repair_arguments = "dataset_id", None, None
    if detail == "full":
        field, next_step = "detail", "use_summary"
        repair_arguments = {**kept, "detail": "summary"}
        if sample_rows:
            repair_arguments["sample_rows"] = sample_rows
        reason = f"{unpaged}, and full detail enlarges them. Request detail=summary."
    elif sample_rows:
        field, next_step = "sample_rows", "drop_samples"
        repair_arguments = {**kept, "sample_rows": 0}
        reason = f"{unpaged}, and sample_rows adds to them. Request sample_rows=0."
    else:
        reason = (
            f"{unpaged}, and with one column they exceed the budget. This dataset's schema "
            "is too large to describe; query the dataset directly, selecting the columns you need."
        )
    return AtlasError(
        ErrorCode.DESCRIBE_TOO_LARGE,
        "The sections returned on every page exceed the result budget"
        + (" with even one column." if even_one else "."),
        details=ErrorDetails(field=field, reason=reason),
        repair=None
        if next_step is None
        else Repair(
            next_step=next_step,
            tool="atlas_describe_dataset",
            arguments={"portal": portal_id, "dataset_id": dataset_id, **(repair_arguments or {})},
            alternative="This restarts from the first page; column_cursor is dropped."
            if continued
            else None,
        ),
    )


def require_queryable(view: dict[str, Any], dataset_id: str, portal_id: str) -> None:
    asset_type = str(view.get("assetType") or view.get("viewType") or "unknown")
    if queryability(asset_type) == "supported" and view.get("viewType") == "tabular":
        return
    parent = view.get("modifyingViewUid")
    if view.get("viewType") == "tabular" and parent:
        repair = Repair(
            next_step="describe_parent",
            tool="atlas_describe_dataset",
            arguments={"portal": portal_id, "dataset_id": parent},
            alternative="This view renders its parent dataset; describe and query the parent.",
        )
    else:
        link = _access_point(view)
        repair = Repair(
            next_step="find_tabular",
            tool="atlas_search_datasets",
            arguments={"portal": portal_id, "asset_scope": "tabular"},
            alternative=f"Open this external entry outside this server: {link}"
            if link
            else "External entries can only be opened at their portal URL.",
        )
    raise AtlasError(
        ErrorCode.DATASET_NOT_QUERYABLE,
        "This catalog entry is not a queryable dataset.",
        details=ErrorDetails(
            field="dataset_id", value=dataset_id, reason=f"asset_type={asset_type}"
        ),
        repair=repair,
    )


def _access_point(view: dict[str, Any]) -> str | None:
    points = (view.get("metadata") or {}).get("accessPoints") or {}
    return next((str(u) for u in points.values() if str(u).startswith("https://")), None)


def _coverage_columns(
    portal: PortalContext, dataset_id: str, time_columns: list[dict[str, Any]], today: date
) -> list[dict[str, Any]]:
    """The primary time column(s), whose range describe reports (`knowledge.primary_time`)."""
    names = [c["fieldName"] for c in time_columns]
    primary = primary_time(portal, dataset_id, names, today=today)
    return [c for c in time_columns if c["fieldName"] in primary]


def _timezone_claim(
    portal: PortalContext, dataset_id: str, column: str, today: date
) -> Interpretation | None:
    """The reviewed timezone, unless its claim is stale (a stale timezone reads unknown)."""
    claim = portal.pack.column_timezone(dataset_id, column)
    if claim is None or claim.interpretation is None or not claim.interpretation.timezone:
        return None
    if freshness.degraded(portal, claim, today):
        return None
    return claim.interpretation


def _unit(portal: PortalContext, dataset_id: str) -> UnitOfObservation | None:
    """What one row is, from the dataset's reviewed unit_of_observation claim.

    A stale one is still served: it does not degrade, and it only says how to read a count.
    """
    claim = next(
        (
            c
            for c in portal.pack.claims
            if c.kind == "unit_of_observation" and c.scope.dataset == dataset_id and c.reviewed
        ),
        None,
    )
    if claim is None or claim.interpretation is None or claim.interpretation.unit is None:
        return None
    return UnitOfObservation(unit=claim.interpretation.unit, reason=claim.interpretation.reason)


def _declared_placeholders(
    portal: PortalContext, dataset_id: str, spec: dict[str, Any], today: date
) -> dict[str, frozenset[str]]:
    """A text place field's reviewed placeholder declarations, as `_place_field` keywords:
    the values fresh declarations make, and those only stale ones make.

    A stale declaration degrades whatever its claim's kind, so a stale `place_field`'s
    placeholders go to `stale_placeholders` even when its reliability is kept. A
    computed-region column has none.
    """
    fresh: set[str] = set()
    stale: set[str] = set()
    if spec["source"] == "column":
        for c in portal.pack.placeholder_declarations(dataset_id, spec["column"]):
            is_stale = freshness.claim_validation(portal, c, today) == "stale"
            (stale if is_stale else fresh).update(c.placeholders or [])
    return {"placeholder_values": frozenset(fresh), "stale_placeholders": frozenset(stale - fresh)}


def _freshness(
    spec: dict[str, Any], portal: PortalContext, claim: Claim | None, today: date
) -> dict[str, Any]:
    """Mark a stale claim's spec; a stale `ok` reads `unknown`, a stale warning is kept."""
    if claim is None or freshness.claim_validation(portal, claim, today) != "stale":
        return spec
    spec["validation"] = "stale"
    if freshness.degraded(portal, claim, today):
        checked = portal.checks[claim.id].checked_at
        spec["reliability"] = "unknown"
        spec["reason"] = (
            f"Reviewed as ok, but its checks last ran on {checked.isoformat()}, over "
            f"{freshness.STALE_AFTER_DAYS} days ago; treat its coverage as unknown."
        )
    return spec


def place_specs(
    portal: PortalContext, dataset_id: str, columns: list[dict[str, Any]], *, today: date
) -> list[dict[str, Any]]:
    """Place fields the pack reviews for this dataset, then every computed-region column.

    A claim whose column is absent from the live schema is skipped. A stale claim's spec
    carries `validation: "stale"`. A reviewed claim on a computed-region column does not add
    an entry: it sets that column's `kind` and `reliability` (and `reason`, `kind_label`) in
    its one computed-region entry, over the layer's claim and the structural default
    (ruling 62).
    """
    names = {c.get("fieldName") for c in columns}
    regions = {c.get("fieldName") for c in columns if _region_of(c)}
    reviewed = {
        name: claim
        for name, claim in portal.pack.place_fields(dataset_id).items()
        if claim.interpretation is not None
        and claim.interpretation.kind is not None
        and claim.interpretation.reliability is not None
    }
    specs: list[dict[str, Any]] = []
    for name, claim in reviewed.items():
        facts = claim.interpretation
        if name not in names or name in regions or facts is None:
            continue
        spec: dict[str, Any] = {
            "column": name,
            "source": "column",
            "kind": facts.kind,
            "reliability": facts.reliability,
        }
        if facts.reason is not None:
            spec["reason"] = facts.reason
        if facts.kind_label is not None:
            spec["kind_label"] = facts.kind_label
        specs.append(_freshness(spec, portal, claim, today))
    for c in columns:
        region = _region_of(c)
        if not region:
            continue
        layer_id = str(region).lstrip("_")
        layer = portal.pack.region_layer(layer_id)
        known = layer.interpretation if layer is not None else None
        region_spec: dict[str, Any] = {
            "column": c["fieldName"],
            "source": "computed_region",
            "layer_id": layer_id,
            "kind": known.kind if known else "other",
            "reliability": known.reliability if known else "partial",
            "reason": (known.reason if known else None)
            or (None if known else "Region layer not reviewed; check assigned_fraction."),
            "label_column": known.label_column if known else None,
            "vintage": known.vintage if known else None,
        }
        if known and known.kind_label is not None:
            region_spec["kind_label"] = known.kind_label
        governing = layer if known else None
        column_claim = reviewed.get(c["fieldName"])
        if column_claim is not None and column_claim.interpretation is not None:
            facts = column_claim.interpretation
            region_spec.update(kind=facts.kind, reliability=facts.reliability, reason=facts.reason)
            region_spec.pop("kind_label", None)
            if facts.kind_label is not None:
                region_spec["kind_label"] = facts.kind_label
            governing = column_claim
        specs.append(_freshness(region_spec, portal, governing, today))
    return specs


def _region_of(column: dict[str, Any]) -> Any:
    """The region layer a computed-region column is computed against, or None."""
    return ((column.get("computationStrategy") or {}).get("parameters") or {}).get("region")


async def _count(client: SodaClient, portal: PortalContext, dataset_id: str) -> int:
    rows = await client.soql(portal, dataset_id, {"$select": "count(*) AS n"})
    if len(rows) != 1 or not str(rows[0].get("n", "")).isdigit():
        raise shape_error("Expected one count row.")
    return int(rows[0]["n"])


async def _min_max(
    client: SodaClient, portal: PortalContext, dataset_id: str, column: str
) -> dict[str, Any]:
    rows = await client.soql(
        portal,
        dataset_id,
        {"$select": f"min({identifier(column)}) AS lo, max({identifier(column)}) AS hi"},
    )
    if len(rows) != 1:
        raise shape_error("Expected one min/max row.")
    return rows[0]


async def _value_groups(
    client: SodaClient, portal: PortalContext, dataset_id: str, column: str
) -> list[dict[str, Any]]:
    return await client.soql(
        portal,
        dataset_id,
        {
            "$select": f"{identifier(column)} AS v, count(*) AS n",
            "$group": identifier(column),
            "$order": "n DESC",
            "$limit": _MAX_VALUES + 1,
        },
    )


async def _sample(
    client: SodaClient,
    portal: PortalContext,
    dataset_id: str,
    columns: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    select = ",".join(identifier(c["fieldName"]) for c in columns)
    return await client.soql(portal, dataset_id, {"$select": select, "$limit": limit})


async def _region_labels(
    client: SodaClient,
    portal: PortalContext,
    places: list[dict[str, Any]],
    place_stats: dict[str, _Outcome],
) -> dict[str, dict[str, str]]:
    """Map each computed-region column's feature ids to labels, for layers with few used values."""
    labels: dict[str, dict[str, str]] = {}
    with anyio.move_on_after(_LABEL_FETCH_TIMEOUT):
        for spec in places:
            if spec["source"] != "computed_region" or not spec.get("label_column"):
                continue
            groups = place_stats[spec["column"]]
            if groups.status != "ok" or len(groups.value) > _MAX_VALUES:
                continue
            ids = sorted(
                {str(r["v"]) for r in groups.value if str(r.get("v", "")).isdigit()}, key=int
            )
            if not ids:
                continue
            layer = spec["layer_id"]
            # Cached names are published only once the lookup succeeds, so a failed or
            # timed-out lookup still reads as labels_available: false.
            labels[spec["column"]] = {}
            names = {
                i: label
                for i in ids
                if (label := cache.region_labels.get((portal.id, layer, i))) is not None
            }
            missing = [i for i in ids if i not in names]
            label_column = identifier(spec["label_column"])
            if missing:
                try:
                    rows = await client.soql(
                        portal,
                        layer,
                        {
                            "$select": f"_feature_id AS id, {label_column} AS label",
                            "$where": f"_feature_id IN ({','.join(missing)})",
                            "$limit": len(missing),
                        },
                    )
                except AtlasError as exc:
                    if exc.envelope.code in _ACTIONABLE:
                        raise
                    # Values keep their numeric ids; labels_available says the names are missing.
                    continue
                for r in rows:
                    feature, label = str(r["id"]), clean(str(r.get("label", "")), limit=100) or ""
                    names[feature] = label
                    cache.region_labels.put((portal.id, layer, feature), label)
            labels[spec["column"]] = names
    return labels


def _row_count(outcome: _Outcome, columns: list[dict[str, Any]]) -> RowCount:
    if outcome.status == "ok":
        return RowCount(value=outcome.value, origin="live_query")
    for c in columns:
        cached = c.get("cachedContents") or {}
        if "non_null" in cached and "null" in cached:
            return RowCount(
                value=int(cached["non_null"]) + int(cached["null"]),
                origin="cached_metadata",
                status=outcome.status,
            )
    return RowCount(status=outcome.status)


def _coverage(meta: dict[str, Any], outcome: _Outcome) -> Coverage:
    column = meta["fieldName"]
    if outcome.status != "ok":
        cached = meta.get("cachedContents") or {}
        lo, hi = _scalar(cached.get("smallest")), _scalar(cached.get("largest"))
        if lo or hi:
            return Coverage(
                column=column, min=lo, max=hi, origin="cached_metadata", status=outcome.status
            )
        return Coverage(column=column, status=outcome.status)
    return Coverage(
        column=column,
        min=outcome.value.get("lo"),
        max=outcome.value.get("hi"),
        origin="live_query",
    )


def _column(c: dict[str, Any], detail: Detail, knowledge: Knowledge | None) -> Column:
    if detail != "full":
        return Column(
            name=c["fieldName"], type=c.get("dataTypeName", "unknown"), knowledge=knowledge
        )
    return Column(
        name=c["fieldName"],
        type=c.get("dataTypeName", "unknown"),
        description=html_to_text(c.get("description"), limit=500),
        stats=_stats(c.get("cachedContents")),
        knowledge=knowledge,
    )


def _stats(cached: dict[str, Any] | None) -> ColumnStats | None:
    if not cached:
        return None
    top = [
        clean(str(t["item"]), limit=100) or ""
        for t in cached.get("top") or []
        if not isinstance(t.get("item"), dict | list)
    ][:5]
    return ColumnStats(
        top=top or None,
        smallest=clean(_scalar(cached.get("smallest")), limit=100),
        largest=clean(_scalar(cached.get("largest")), limit=100),
        null=int(cached["null"]) if str(cached.get("null", "")).isdigit() else None,
    )


def _scalar(value: Any) -> str | None:
    return None if value is None or isinstance(value, dict | list) else str(value)


def _place_field(
    spec: dict[str, Any],
    groups: _Outcome | None,
    labels: dict[str, dict[str, str]],
    *,
    placeholder_values: frozenset[str],
    stale_placeholders: frozenset[str],
) -> PlaceField:
    """`placeholder_values` are the pack's declared placeholders for this column.

    Shared-vocabulary values it does not declare are only `candidate_placeholders`: they
    stay in `values` and count as assigned. So are values only a stale declaration makes
    (`stale_placeholders`); with any, `assigned_fraction` is omitted, so the field never
    reads more complete than reviewed, and `placeholder_values` keeps only the fresh
    declarations' values.
    """
    field = PlaceField(
        column=spec["column"],
        kind=spec["kind"],
        kind_label=spec.get("kind_label"),
        source=spec["source"],
        reliability=spec["reliability"],
        reliability_reason=spec.get("reason"),
        validation=spec.get("validation"),
    )
    if groups is None:
        return field
    field.layer_id = spec.get("layer_id")
    field.label_column = spec.get("label_column")
    field.boundary_vintage = spec.get("vintage")
    if groups.status != "ok":
        field.stats_status = groups.status
        return field
    field.stats_status = "ok"
    placeholders = [
        PlaceholderValue(value=str(r.get("v", "")), rows=int(r["n"]))
        for r in groups.value
        if "v" in r and str(r["v"]) in placeholder_values
    ]
    nulls = sum(int(r["n"]) for r in groups.value if "v" not in r)
    if nulls:
        placeholders.append(PlaceholderValue(value="null", rows=nulls))
    if stale_placeholders:
        # Only what a fresh declaration removes; the null count is in `null_rows`.
        placeholders = [p for p in placeholders if p.value in placeholder_values]
    field.placeholder_values = placeholders or None
    flagged = (SHARED_PLACEHOLDERS | stale_placeholders) - placeholder_values
    candidates = [
        PlaceholderValue(value=str(r["v"]), rows=int(r["n"]))
        for r in groups.value
        if "v" in r and str(r["v"]) in flagged
    ]
    field.candidate_placeholders = candidates or None
    assigned = [r for r in groups.value if "v" in r and str(r["v"]) not in placeholder_values]
    if len(groups.value) <= _MAX_VALUES:
        field.value_count = len(assigned)
        names = labels.get(spec["column"], {})
        if spec["column"] in labels:
            field.labels_available = bool(names)
        field.values = sorted(
            (
                PlaceValue(
                    label=names.get(str(r["v"]), clean(str(r["v"]), limit=100) or ""),
                    value=str(r["v"]),
                )
                for r in assigned
            ),
            key=lambda v: v.label,
        )
        # Exact only when every group came back, and taken from that one snapshot: a row
        # count from another query can disagree with the groups as the data changes.
        total = sum(int(r["n"]) for r in groups.value)
        field.null_rows, field.non_null_rows = nulls, total - nulls
        if total and not stale_placeholders:
            unassigned = sum(p.rows for p in placeholders)
            field.assigned_fraction = round(1 - unassigned / total, 4)
    return field


def _geo_unusable(columns: list[dict[str, Any]]) -> list[GeoUnusable]:
    out: list[GeoUnusable] = []
    for c in columns:
        name = str(c.get("fieldName", ""))
        if not _COORDINATE.search(name):
            continue
        if c.get("dataTypeName") == "text":
            reason = "Text coordinate column (values may be redacted); near cannot use it."
        elif c.get("dataTypeName") == "number":
            reason = (
                "Numeric coordinate; filter with between on latitude and longitude instead of near."
            )
        else:
            continue
        out.append(GeoUnusable(column=name, reason=reason))
    return out


def _time(portal: PortalContext, dataset_id: str, c: dict[str, Any], today: date) -> TimeSemantics:
    """Timezone only from a reviewed claim that is not stale; absent means unknown, never
    assumed."""
    known = _timezone_claim(portal, dataset_id, c["fieldName"], today)
    claim = portal.pack.column_timezone(dataset_id, c["fieldName"])
    stale = claim is not None and freshness.claim_validation(portal, claim, today) == "stale"
    return TimeSemantics(
        column=c["fieldName"],
        type=c["dataTypeName"],
        timezone=known.timezone if known else None,
        evidence=served_evidence(claim.evidence) if known and claim else None,
        validation="stale" if stale else None,
    )


def served_evidence(evidence: list[Evidence]) -> str:
    """The text served as a claim's evidence (claims have at least one evidence).

    The first `manual_observation` note, else the first probe's `observation`, else the first
    `document` quote. A reviewer's note summarizes the claim, so probe evidence appended
    after it never changes what is served.
    """
    note = next((e.note for e in evidence if isinstance(e, ManualObservation)), None)
    if note is not None:
        return note
    probed = (e.observation for e in evidence if isinstance(e, SoqlProbe | MetadataProbe))
    observation = next(probed, None)
    if observation is not None:
        return observation
    return next(e.quote for e in evidence if isinstance(e, Document))


def _matches(c: dict[str, Any], needle: str) -> bool:
    needle = needle.lower()
    return (
        needle in str(c.get("fieldName", "")).lower()
        or needle in str(c.get("description") or "").lower()
    )


def _fill(rows: Any, columns: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """SODA2 omits null keys; restore them so every row has every selected column."""
    if not isinstance(rows, list):
        return None
    names = [c["fieldName"] for c in columns]
    return [{name: strip_control(row.get(name)) for name in names} for row in rows]
