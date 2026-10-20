"""Bounded reads and aggregates (docs/design.md: tool 3, Query engine)."""

from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

import anyio

from opendata_atlas.constants import (
    DOWNLOAD_LIMIT,
    GEO_TYPES,
    QUERY_DEADLINE_SECONDS,
    QUERY_LOGICAL_CAP,
    QUERY_TEXT_MAX_BYTES,
    TIME_TYPES,
    URL_MAX_CHARS,
)
from opendata_atlas.core import cache
from opendata_atlas.core import cursor as cursors
from opendata_atlas.core.budget import RESULT_LIMIT, fit, wire_size
from opendata_atlas.core.context import make_source
from opendata_atlas.core.describe import place_specs, require_queryable
from opendata_atlas.core.errors import (
    AtlasError,
    ErrorCode,
    ErrorDetails,
    Repair,
    describe_repair,
)
from opendata_atlas.core.http import resource_url
from opendata_atlas.core.models import (
    CoverageWarning,
    Detail,
    KnowledgeNotice,
    QueryResult,
    ResultColumn,
)
from opendata_atlas.core.text import strip_control
from opendata_atlas.portals import freshness
from opendata_atlas.portals.knowledge import knowledge_notice

if TYPE_CHECKING:
    from collections.abc import Callable

    from opendata_atlas.core.http import RowStream, SodaClient
    from opendata_atlas.portals.model import PortalContext

_AGGREGATE = re.compile(r"\b(count|sum|avg|min|max|stddev_pop|stddev_samp)\s*\(", re.IGNORECASE)
#: A backtick identifier, or a bare name that starts a token (not the `e5` of `1e5`) and is not
#: a function: `count(*)` and `date_trunc_ym (x)` name no column.
_IDENTIFIER = re.compile(r"`([^`]*)`|(?<!\w)([:@A-Za-z_][\w:@]*+)(?!\s*\()")
#: Strings and backtick names in one left-to-right pass, so no quote opens inside another; a
#: doubled quote escapes itself. Local to the pre-check, which `_QUOTED` does not serve.
_SPANS = re.compile(r"(`[^`]*`)|'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"")
_CAST = re.compile(r"::\s*\w+")
#: Syntax the pre-check does not model (pipes, windows): upstream decides (ruling 16).
_UNMODELED = re.compile(r"\|>|\bover\s*\(", re.IGNORECASE)
#: Words SoQL reads as syntax, so never as column names.
_SOQL_WORDS = frozenset(
    {"and", "or", "not", "is", "null", "in", "like", "between", "asc", "desc", "nulls"}
    | {"first", "last", "true", "false", "case", "when", "then", "else", "end", "as", "distinct"}
    | {"ilike"}
)
#: A dotted reference (`location.latitude`, `@t.column`): a subfield or join name the pre-check
#: does not model, so neither part is checked (ruling 16).
_DOTTED = re.compile(
    r"(?<!\w)(?:`[^`]*`|[:@A-Za-z_][\w:@]*)"  # the base name
    r"(?:\s*\.\s*(?:`[^`]*`|[A-Za-z_]\w*))+"  # one or more `.subfield`
)
#: Aggregates whose bare name may be the implicit alias upstream gives an unaliased call.
_IMPLICIT_ALIASES = frozenset({"count", "sum", "avg", "min", "max"})
_BACKTICKED = re.compile(r"`[^`]*`")
#: A backtick identifier or string literal, in one pass so neither opens the other.
_QUOTED = re.compile(r"`[^`]*`|'(?:[^']|'')*'")
_ALIAS_DECLARATION = re.compile(r"\bas\s+(`[^`]*`|[A-Za-z_]\w*)", re.IGNORECASE)
#: A select item's trailing `AS <alias>`.
_TRAILING_ALIAS = re.compile(r"\s+as\s+(`[^`]*`|[A-Za-z_]\w*)\s*$", re.IGNORECASE)
#: Raw SoQL clause keywords; string literals are blanked before splitting on them.
_CLAUSE = re.compile(
    r"\b(select|where|group\s+by|having|order\s+by|limit|offset|search)\b", re.IGNORECASE
)
#: Clauses where a name declared by `AS` in select means the alias, not a column.
_ALIAS_SCOPE = frozenset({"group by", "having", "order by"})
_DIRECTION = re.compile(r"\s+(asc|desc)(\s+nulls\s+(first|last))?\s*$", re.IGNORECASE)
_DEFAULT_PAGE_SIZE = 100
#: `<name> = '<literal>'`: the text equality filter a zero-match hint names (Task 7).
_TEXT_EQUALITY = re.compile(r"(?<![\w.:@`])(`[^`]+`|[A-Za-z_]\w*)\s*=\s*'((?:[^']|'')*)'")
_MAX_HINTS = 3
#: The longest literal a hint's `alternative` echoes before eliding the rest.
_HINT_ECHO_CHARS = 80
#: An ungrouped `count(*)` select item, with its alias if any (ruling 48).
_COUNT_STAR = re.compile(r"\s*count\s*\(\s*\*\s*\)\s*(?:as\s+(`[^`]*`|[A-Za-z_]\w*))?\s*", re.I)
#: A `NOT` that negates what follows, not one inside `IS NOT`, `NOT IN`, `NOT LIKE` and so on.
_NEGATION = re.compile(r"(?<![\w`])(?<!is )not\b(?!\s+(?:in|like|ilike|between|null)\b)", re.I)

#: The original clauses cannot be echoed back, and a `{dataset_id}`-only query would
#: answer a different question, so the repair reads how to restart instead (#16).
_RESTART = Repair(
    next_step="read_paging",
    tool="atlas_get_reference",
    arguments={"topic": "soql", "item_id": "paging"},
    alternative="Resend the first-page call with all its original arguments, without cursor.",
)


async def run(
    client: SodaClient, portal: PortalContext, *, dataset_id: str, **kwargs: Any
) -> QueryResult:
    """One query, bounded as a whole: metadata fetch plus the upstream stream."""
    loaded: list[bool] = []
    try:
        with anyio.fail_after(QUERY_DEADLINE_SECONDS):
            return await _run(client, portal, dataset_id=dataset_id, loaded=loaded, **kwargs)
    except TimeoutError as exc:
        raise AtlasError(
            ErrorCode.QUERY_TIMEOUT,
            f"The query did not finish within {QUERY_DEADLINE_SECONDS:.0f} s.",
            # The whole-call deadline can expire first, inside the metadata fetch.
            details=None if loaded else _METADATA_TIMEOUT,
            repair=_narrow(portal.id, dataset_id) if loaded else None,
        ) from exc


#: Describe waits on the same metadata, so no repair: `temporary` says retry later.
_METADATA_TIMEOUT = ErrorDetails(reason="The dataset's metadata did not load.")


def _narrow(portal_id: str, dataset_id: str) -> Repair:
    """Describe finds the time and place columns to narrow on; it returns no rows (#16)."""
    return Repair(
        next_step="inspect_for_narrowing",
        tool="atlas_describe_dataset",
        arguments={"portal": portal_id, "dataset_id": dataset_id},
        alternative="Resend the query with every original filter, aggregated server-side "
        "(count(*) with group_by) or split by where on a time column.",
    )


async def _run(
    client: SodaClient,
    portal: PortalContext,
    *,
    dataset_id: str,
    loaded: list[bool],
    mode: str,
    clauses: dict[str, Any],
    soql: str | None,
    page_size: int | None,
    cursor: str | None,
    detail: Detail,
) -> QueryResult:
    state: dict[str, Any] = {}
    if cursor is not None:
        state = cursors.decode(cursor, "query", portal_id=portal.id, restart=_RESTART)
        if state.get("ds") != dataset_id:
            raise AtlasError(
                ErrorCode.INVALID_CURSOR,
                "The cursor was issued for a different dataset.",
                details=ErrorDetails(
                    field="cursor", reason="dataset_id does not match the cursor."
                ),
                repair=_RESTART,
            )
        clauses = state["c"]
        mode = "clauses"
    size = page_size or int(state.get("ps", _DEFAULT_PAGE_SIZE))

    try:
        view = await cache.cached_view(client, portal, dataset_id)
    except AtlasError as exc:
        if exc.envelope.code == ErrorCode.QUERY_TIMEOUT:
            exc.envelope.details = _METADATA_TIMEOUT
        raise
    loaded.append(True)
    require_queryable(view, dataset_id, portal.id)
    columns = view.get("columns") or []
    facts_id = view.get("modifyingViewUid") or dataset_id
    today = freshness.today()
    places = place_specs(portal, facts_id, columns, today=today)

    def notice(referenced: set[str], text_filters: list[str]) -> KnowledgeNotice | None:
        return knowledge_notice(
            portal,
            facts_id,
            places={p["column"]: p.get("layer_id") for p in places},
            time_columns=[
                str(c["fieldName"])
                for c in columns
                if c.get("dataTypeName") in TIME_TYPES
                and not str(c.get("fieldName", "")).startswith(":")
            ],
            referenced=referenced,
            today=today,
            text_filters=text_filters,
        )

    try:
        if mode == "soql" and soql is not None:
            return await _run_soql(
                client, portal, dataset_id, soql, size, detail, columns, places, notice
            )
        return await _run_clauses(
            client, portal, dataset_id, clauses, state, size, detail, columns, places, notice
        )
    except AtlasError as exc:
        envelope = exc.envelope
        if envelope.code == ErrorCode.NO_SUCH_COLUMN:
            cache.views.pop((portal.id, dataset_id))
        if mode != "soql" and envelope.details is not None:
            # Upstream positions index the assembled query, which the agent never wrote.
            envelope.details.position = None
        if envelope.code == ErrorCode.QUERY_TIMEOUT and envelope.repair is None:
            envelope.repair = _narrow(portal.id, dataset_id)
        raise


# --------------------------------------------------------------------------
# Clauses mode
# --------------------------------------------------------------------------


async def _run_clauses(
    client: SodaClient,
    portal: PortalContext,
    dataset_id: str,
    clauses: dict[str, Any],
    state: dict[str, Any],
    page_size: int,
    detail: Detail,
    columns: list[dict[str, Any]],
    places: list[dict[str, Any]],
    notice: Callable[[set[str], list[str]], KnowledgeNotice | None],
) -> QueryResult:
    _check_columns(portal.id, dataset_id, clauses, columns)
    plan = _plan(portal.id, dataset_id, clauses, columns, places)
    emitted_before = int(state.get("n", 0))
    fetch = min(page_size, QUERY_LOGICAL_CAP - emitted_before)

    params = dict(plan["params"])
    where = list(plan["where"])
    if plan["kind"] == "keyset" and state.get("last"):
        last = str(state["last"]).replace("'", "''")
        where.append(f":id > '{last}'")
    if where:
        params["$where"] = " AND ".join(where)
    params["$limit"] = fetch + 1
    if plan["kind"] == "offset" and emitted_before:
        params["$offset"] = emitted_before

    stream = await client.stream_rows(portal, dataset_id, params, max_rows=fetch + 1)
    names, types = _visible(stream, plan["hidden"])
    rows = [_row(r, names) for r in stream.rows[:fetch]]
    used = _referenced(*_written(clauses, where))
    text_filters = _text_filters(
        clauses.get("where") or "",
        columns,
        group_by=" , ".join(clauses.get("group_by") or []),
        select=" , ".join(clauses.get("select") or []),
    )

    result = QueryResult(
        dataset_id=dataset_id,
        columns=[ResultColumn(name=n, type=t) for n, t in zip(names, types, strict=True)],
        rows=[],
        returned_rows=0,
        has_more=False,
        truncated=False,
        consistency="stable" if plan["kind"] == "keyset" else "best_effort",
        coverage_warnings=_warnings(used, places) or None,
        knowledge_notice=notice(used, text_filters),
        source=make_source(portal, retrieved=True),
    )
    if not state and _matched_nothing(rows, clauses):
        result.hints = _hints(portal.id, dataset_id, clauses, columns) or None
        while result.hints and wire_size(result) > RESULT_LIMIT:
            result.hints = result.hints[:-1] or None
    if detail == "full":
        _attach_urls(result, portal, dataset_id, params, plan)

    compact = {k: v for k, v in clauses.items() if v is not None}

    def settle(count: int) -> None:
        _reset_page(result, rows[:count])
        emitted_total = emitted_before + count
        if len(stream.rows) <= count:
            return
        if emitted_total >= QUERY_LOGICAL_CAP:
            result.truncated = True
            result.truncation_reason = "row_cap"
            result.truncation_hint = (
                f"Paged queries stop at {QUERY_LOGICAL_CAP:,} rows. Aggregate with "
                "select/group_by, narrow where, or hand the user download_url (detail='full')."
            )
            return
        next_state: dict[str, Any] = {
            "ds": dataset_id,
            "c": compact,
            "n": emitted_total,
            "ps": page_size,
        }
        if plan["kind"] == "keyset":
            next_state["last"] = stream.rows[count - 1].get(":id")
        result.has_more = True
        result.next_cursor = cursors.encode("query", next_state, portal_id=portal.id)

    _fit(result, rows, settle, portal.id)
    return result


def _matched_nothing(rows: list[dict[str, Any]], clauses: dict[str, Any]) -> bool:
    """No rows, or the one row of an ungrouped `count(*)` that counted 0 (ruling 48).

    Any other single row of zeros or nulls (a zero `sum`, a `count(col)` of nulls, a matched
    row) did match. An unaliased `count(*)` is read only when it is the sole select item.
    """
    if not rows:
        return True
    select = clauses.get("select") or []
    if clauses.get("group_by") or len(rows) != 1:
        return False
    for item in select:
        match = _COUNT_STAR.fullmatch(item)
        if match is None:
            continue
        if match.group(1):
            value = rows[0].get(match.group(1).strip("`"))
        elif len(select) == 1 and len(rows[0]) == 1:
            value = next(iter(rows[0].values()))
        else:
            continue
        return value in (0, "0")
    return False


def _hints(
    portal_id: str, dataset_id: str, clauses: dict[str, Any], columns: list[dict[str, Any]]
) -> list[Repair]:
    """One hint per text column that `where` tests for equality, at most `_MAX_HINTS`.

    A hint is a repair (ruling 47): it groups the column's values under the same filters, its
    own equality loosened; the column is `group_by[0]` and `alternative` is the message.
    """
    where = clauses.get("where") or ""
    texts = {str(c["fieldName"]) for c in columns if c.get("dataTypeName") == "text"}
    # Blank string contents, keeping offsets, so text inside a literal is never a filter.
    masked = _QUOTED.sub(
        lambda m: (
            m.group() if m.group().startswith("`") else "'" + " " * (len(m.group()) - 2) + "'"
        ),
        where,
    )
    aliases = {
        a.strip("`").lower()
        for a in _ALIAS_DECLARATION.findall(" ".join(clauses.get("select") or []))
    }
    if aliases & {n.lower() for n in _names(_unquote(where))}:
        return []  # the repair's select would not declare them (fail open, as ruling 16)
    negations = [m.start() for m in _NEGATION.finditer(masked)]
    carried = {k: clauses[k] for k in ("near", "search_text") if clauses.get(k)}
    hints: list[Repair] = []
    seen: set[str] = set()
    for match in _TEXT_EQUALITY.finditer(masked):
        written, literal = match.group(1), where[match.start(2) : match.end(2)]
        column = written.strip("`")
        if column not in texts or column in seen:
            continue
        if any(start < match.start() for start in negations):
            continue  # possibly negated: the hint would misstate the question
        seen.add(column)
        loosened = f"upper({written}) like '%{literal.strip().upper()}%'"
        clause_args = {
            "select": [written, "count(*) AS n"],
            "group_by": [written],
            "order_by": ["n DESC"],
            "where": where[: match.start()] + loosened + where[match.end() :],
            **carried,
        }
        if len(cursors.dump(clause_args)) > QUERY_TEXT_MAX_BYTES:
            continue  # over the clause cap: following it would be invalid_argument
        echo = literal if len(literal) <= _HINT_ECHO_CHARS else literal[:_HINT_ECHO_CHARS] + "…"
        hints.append(
            Repair(
                next_step="inspect_text_values",
                tool="atlas_query_dataset",
                arguments={"portal": portal_id, "dataset_id": dataset_id, **clause_args},
                alternative=f"No rows matched `{column}` = '{echo}'; its values may be "
                "padded or differ in case, so filter on a value this grouping returns.",
            )
        )
        if len(hints) == _MAX_HINTS:
            break
    return hints


def _plan(
    portal_id: str,
    dataset_id: str,
    clauses: dict[str, Any],
    columns: list[dict[str, Any]],
    places: list[dict[str, Any]],
) -> dict[str, Any]:
    types: dict[str, Any] = {str(c.get("fieldName")): c.get("dataTypeName") for c in columns}
    select = list(clauses.get("select") or [n for n in types if n and not n.startswith(":")])
    group_by = list(clauses.get("group_by") or [])
    order_by = list(clauses.get("order_by") or [])
    distinct = bool(select) and select[0].strip().lower().startswith("distinct ")
    aggregate = bool(group_by) or distinct or any(_AGGREGATE.search(s) for s in select)
    if clauses.get("having"):
        aggregate = True

    where: list[str] = []
    if clauses.get("where"):
        where.append(f"({clauses['where']})")
    near = clauses.get("near")
    if near:
        where.append(_within_circle(portal_id, dataset_id, near, types, places))

    hidden: set[str] = set()
    ordered = {_bare(o) for o in order_by}
    if distinct:
        kind = "offset"
        order = order_by + [k for k in _select_keys(select) if _bare(k) not in ordered]
    elif aggregate:
        kind = "offset"
        order = order_by + [g for g in group_by if _bare(g) not in ordered]
    elif order_by:
        kind = "offset"
        order = [*order_by, ":id"]
    else:
        kind = "keyset"
        order = [":id"]
        if ":id" not in select:
            select.append(":id")
            hidden.add(":id")

    params: dict[str, Any] = {"$select": ", ".join(select)}
    if group_by:
        params["$group"] = ", ".join(group_by)
    if clauses.get("having"):
        params["$having"] = clauses["having"]
    if order:
        params["$order"] = ", ".join(order)
    if clauses.get("search_text"):
        params["$q"] = clauses["search_text"]
    return {"params": params, "where": where, "kind": kind, "hidden": hidden}


_ALIAS = re.compile(r"\s+as\s+(`[^`]*`|[A-Za-z_]\w*)\s*$", re.IGNORECASE)


def _select_keys(select: list[str]) -> list[str]:
    """Each selected column's sort key: its alias, else the expression, without DISTINCT."""
    keys = []
    for index, item in enumerate(select):
        expression = item.strip()
        if index == 0 and expression.lower().startswith("distinct "):
            expression = expression[len("distinct ") :].strip()
        alias = _ALIAS.search(expression)
        keys.append(alias.group(1) if alias else expression)
    return keys


def _bare(expression: str) -> str:
    """A sort key for comparison: no direction, case, or backtick quoting."""
    return _DIRECTION.sub("", expression).strip().strip("`").lower()


def _within_circle(
    portal_id: str,
    dataset_id: str,
    near: dict[str, Any],
    types: dict[str, Any],
    places: list[dict[str, Any]],
) -> str:
    column = near["column"]
    kind = types.get(column)
    if kind not in GEO_TYPES:
        place_names = [p["column"] for p in places if p["source"] == "column"]
        alternative = (
            "Filter on a place field instead (" + ", ".join(place_names) + "); "
            "a neighborhood is not equivalent to a radius."
            if place_names
            else "This dataset has no point or location column; near is unavailable."
        )
        raise AtlasError(
            ErrorCode.COLUMN_NOT_GEOGRAPHIC,
            "near needs a point or location column.",
            details=ErrorDetails(
                field="near.column",
                value=column if kind is not None else None,
                reason=f"Column type is {kind}." if kind else "No such column in this dataset.",
            ),
            repair=Repair(
                next_step="inspect_geography",
                tool="atlas_describe_dataset",
                arguments={"portal": portal_id, "dataset_id": dataset_id, "detail": "full"},
                alternative=alternative,
            ),
        )
    return (
        f"within_circle({column}, {float(near['latitude'])!r}, "
        f"{float(near['longitude'])!r}, {float(near['radius_m'])!r})"
    )


# --------------------------------------------------------------------------
# Raw SoQL mode
# --------------------------------------------------------------------------


async def _run_soql(
    client: SodaClient,
    portal: PortalContext,
    dataset_id: str,
    soql: str,
    page_size: int,
    detail: Detail,
    columns: list[dict[str, Any]],
    places: list[dict[str, Any]],
    notice: Callable[[set[str], list[str]], KnowledgeNotice | None],
) -> QueryResult:
    params = {"$query": soql}
    stream = await client.stream_rows(portal, dataset_id, params, max_rows=page_size)
    names, types = _visible(stream, set())
    rows = [_row(r, names) for r in stream.rows]
    used = _referenced(*_soql_reads(soql))
    text_filters = _text_filters(
        _soql_where(soql),
        columns,
        group_by=_soql_clause(soql, "group by"),
        select=_soql_clause(soql, "select"),
    )
    result = QueryResult(
        dataset_id=dataset_id,
        columns=[ResultColumn(name=n, type=t) for n, t in zip(names, types, strict=True)],
        rows=[],
        returned_rows=0,
        has_more=False,
        truncated=False,
        consistency="single_page",
        coverage_warnings=_warnings(used, places) or None,
        knowledge_notice=notice(used, text_filters),
        source=make_source(portal, retrieved=True),
    )
    if detail == "full":
        url = resource_url(portal, dataset_id) + "?" + urlencode(params)
        _set_url(result, "query_url", url)
        result.effective_query = soql

    def settle(count: int) -> None:
        _reset_page(result, rows[:count])
        if stream.more or count < len(rows):
            result.truncated = True
            result.truncation_reason = "raw_soql_not_paged"
            result.truncation_hint = (
                f"Raw SoQL returns one page. Set LIMIT {count} and advance OFFSET by "
                f"{count}, or use clauses mode for cursor paging."
            )

    _fit(result, rows, settle, portal.id)
    return result


# --------------------------------------------------------------------------
# Shared
# --------------------------------------------------------------------------


def _visible(stream: RowStream, hidden: set[str]) -> tuple[list[str], list[str]]:
    fields = stream.fields or (list(stream.rows[0]) if stream.rows else [])
    types = stream.types if len(stream.types) == len(fields) else ["unknown"] * len(fields)
    pairs = [(f, t) for f, t in zip(fields, types, strict=True) if f not in hidden]
    return [p[0] for p in pairs], [p[1] for p in pairs]


def _row(raw: dict[str, Any], names: list[str]) -> dict[str, Any]:
    """SODA2 omits null keys; every row gets every visible column."""
    return {name: _plain(strip_control(raw.get(name))) for name in names}


def _plain(value: Any) -> Any:
    """ijson yields Decimal for JSON numbers (e.g. GeoJSON coordinates); emit plain numbers."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def _reset_page(result: QueryResult, rows: list[dict[str, Any]]) -> None:
    result.rows, result.returned_rows = rows, len(rows)
    result.has_more, result.next_cursor = False, None
    result.truncated, result.truncation_reason, result.truncation_hint = False, None, None


def _estimate(rows: list[dict[str, Any]], budget: int) -> int:
    """A fast upper bound on how many rows fit; `_fit` corrects it against the real size."""
    used = 0
    for count, row in enumerate(rows):
        used += 2 * len(json.dumps(row, separators=(",", ":"), ensure_ascii=False).encode())
        if used > budget:
            return count
    return len(rows)


def _fit(
    result: QueryResult,
    rows: list[dict[str, Any]],
    settle: Callable[[int], None],
    portal_id: str,
) -> None:
    """Settle the page on the most whole rows whose complete serialized result fits the budget."""
    count = fit(_estimate(rows, RESULT_LIMIT), settle, lambda: wire_size(result))
    # Also catches a page with no rows whose column descriptors alone overflow the budget.
    if (rows and count == 0) or wire_size(result) > RESULT_LIMIT:
        raise AtlasError(
            ErrorCode.ROW_TOO_LARGE,
            "A single row, or the column list alone, exceeds the response byte budget.",
            details=ErrorDetails(field="select", reason="Select fewer or narrower columns."),
            repair=Repair(
                next_step="project_fewer_columns",
                tool="atlas_describe_dataset",
                arguments={"portal": portal_id, "dataset_id": result.dataset_id},
            ),
        )


def _unquote(text: str) -> str:
    """Blank string literals; backtick identifiers stay."""
    return _QUOTED.sub(lambda m: m.group() if m.group().startswith("`") else " ", text)


def _written(clauses: dict[str, Any], where: list[str]) -> tuple[str, str]:
    """Every clause the agent wrote, split as `_soql_reads` splits raw SoQL.

    An omitted select is not scanned.
    """
    later = [clauses.get("having") or ""]
    for key in ("group_by", "order_by"):
        later += clauses.get(key) or []
    return " ".join([*where, *(clauses.get("select") or [])]), " ".join(later)


def _check_columns(
    portal_id: str, dataset_id: str, clauses: dict[str, Any], columns: list[dict[str, Any]]
) -> None:
    """Raise `no_such_column` for a name the agent wrote that the schema lacks.

    Some portals answer the engine's `$order=:id` with `soql_syntax_error` whatever the
    unknown column, so the schema already fetched decides. A name is a column unless it is a
    keyword, a function, a literal, or an `AS` alias select declared (in scope in every clause,
    since the probed portals accept one in `$where`). It rejects only when certain: a query with a
    pipe or a window in any clause is not checked and is left to upstream, and neither part of a
    dotted reference (`location.latitude`) is checked, nor an `order_by` name that may be the
    implicit alias of an unaliased aggregate in select (`count` after `count(*)`) (ruling 16).
    The name is not echoed [3.sec-sanitize]; `details.field` says which argument.
    """
    known = {str(c.get("fieldName")).lower() for c in columns if c.get("fieldName")}
    if not known:
        return
    texts = {
        "select": " ".join(clauses.get("select") or []),
        "where": clauses.get("where") or "",
        "group_by": " ".join(clauses.get("group_by") or []),
        "having": clauses.get("having") or "",
        "order_by": " ".join(clauses.get("order_by") or []),
    }
    cleaned = {f: _SPANS.sub(lambda m: m.group(1) or " ", w) for f, w in texts.items()}
    if any(re.search(r"['\"`]", _BACKTICKED.sub("", t)) for t in cleaned.values()):
        return  # unbalanced quotes: the scan cannot tell names from strings
    if any(_UNMODELED.search(t) for t in cleaned.values()):
        return  # a pipe or window can declare names any clause uses
    declared = _ALIAS_DECLARATION.findall(cleaned["select"])
    in_scope = known | {a.strip("`").lower() for a in declared}
    implicit = {f for f in _IMPLICIT_ALIASES if re.search(rf"\b{f}\s*\(", cleaned["select"], re.I)}
    for field, text in cleaned.items():
        for name in _names(_DOTTED.sub(" ", _CAST.sub(" ", _ALIAS_DECLARATION.sub(" ", text)))):
            column = name.lower()
            if column.startswith(":") or column in _SOQL_WORDS or column in in_scope:
                continue
            if field == "order_by" and column in implicit:
                continue
            raise AtlasError(
                ErrorCode.NO_SUCH_COLUMN,
                "A referenced column does not exist in this dataset.",
                details=ErrorDetails(
                    field=field, reason="Use API field names from the dataset schema."
                ),
                repair=describe_repair(portal_id, dataset_id, "inspect_columns", detail="full"),
            )


def _soql_reads(soql: str) -> tuple[str, str]:
    """Raw SoQL as (select and where, the clauses where select's aliases are in scope).

    Keywords inside a backtick identifier, such as an alias named `order by`, are not clauses.
    """
    text = _unquote(soql)
    masked = _BACKTICKED.sub(lambda m: "`" + "_" * (len(m.group()) - 2) + "`", text)
    direct, aliased, start, scope = [], [], 0, ""
    for match in _CLAUSE.finditer(masked):
        (aliased if scope in _ALIAS_SCOPE else direct).append(text[start : match.start()])
        scope, start = " ".join(match.group().lower().split()), match.end()
    (aliased if scope in _ALIAS_SCOPE else direct).append(text[start:])
    return " ".join(direct), " ".join(aliased)


def _soql_where(soql: str) -> str:
    """The text of raw SoQL's WHERE clause, up to the next clause keyword."""
    return _soql_clause(soql, "where")


def _soql_clause(soql: str, clause: str) -> str:
    """The text of one raw SoQL clause (`where`, `group by`, ...), up to the next keyword."""
    text = _unquote(soql)
    masked = _BACKTICKED.sub(lambda m: "`" + "_" * (len(m.group()) - 2) + "`", text)
    parts, start, scope = [], 0, ""
    for match in _CLAUSE.finditer(masked):
        if scope == clause:
            parts.append(text[start : match.start()])
        scope, start = " ".join(match.group().lower().split()), match.end()
    if scope == clause:
        parts.append(text[start:])
    return " ".join(parts)


def _text_filters(
    where: str, columns: list[dict[str, Any]], *, group_by: str = "", select: str = ""
) -> list[str]:
    """The text-typed columns a where clause or group_by reads, sorted (the knowledge notice
    names them; ruling 69). A group_by name that select declares as an alias reads the
    columns its select expression reads, as `_referenced` counts them (ruling 70)."""
    texts = {str(c["fieldName"]) for c in columns if c.get("dataTypeName") == "text"}
    sources = _alias_sources(select)
    grouped: set[str] = set()
    for name in _names(_unquote(group_by)):
        grouped |= _referenced(sources[name], "") if name in sources else {name}
    return sorted((_referenced(where, "") | grouped) & texts)


def _alias_sources(select: str) -> dict[str, str]:
    """Each alias select declares (`<expr> AS <alias>`), mapped to its expression."""
    items, depth, start, text = [], 0, 0, _unquote(select)
    for i, char in enumerate(text):
        depth += {"(": 1, ")": -1}.get(char, 0)
        if char == "," and depth == 0:
            items.append(text[start:i])
            start = i + 1
    items.append(text[start:])
    sources = {}
    for item in items:
        match = _TRAILING_ALIAS.search(item)
        if match:
            sources[match.group(1).strip("`")] = item[: match.start()]
    return sources


def _names(text: str) -> set[str]:
    """Identifiers read; a backtick identifier is one name, spaces and all."""
    return {quoted or bare for quoted, bare in _IDENTIFIER.findall(text)}


def _referenced(direct: str, aliased: str) -> set[str]:
    """The names the agent's text reads, for coverage warnings and the knowledge notice.

    String literals and `AS alias` names are not reads, nor, in `aliased`, a name select
    declared as an alias: `precinct AS neighborhood` then `order_by neighborhood` reads precinct.
    """
    direct, aliased = _unquote(direct), _unquote(aliased)
    aliases = {a.strip("`") for a in _ALIAS_DECLARATION.findall(direct)}
    return _names(_ALIAS_DECLARATION.sub(" ", direct)) | (_names(aliased) - aliases)


def _warnings(used: set[str], places: list[dict[str, Any]]) -> list[CoverageWarning]:
    """Warn on place fields the agent's text reads (docs/design.md: coverage warnings)."""
    return [
        CoverageWarning(
            column=p["column"],
            reliability=p["reliability"],
            reason=p.get("reason") or "This place field has known gaps.",
            validation=p.get("validation"),
        )
        for p in places
        if p["reliability"] != "ok" and p["column"] in used
    ]


def _attach_urls(
    result: QueryResult,
    portal: PortalContext,
    dataset_id: str,
    params: dict[str, Any],
    plan: dict[str, Any],
) -> None:
    _set_url(result, "query_url", resource_url(portal, dataset_id) + "?" + urlencode(params))
    download = {k: v for k, v in plan["params"].items()}
    if plan["where"]:
        download["$where"] = " AND ".join(plan["where"])
    download["$limit"] = DOWNLOAD_LIMIT
    _set_url(
        result, "download_url", resource_url(portal, dataset_id, "csv") + "?" + urlencode(download)
    )
    parts = [f"SELECT {params['$select']}"]
    for key, word in (
        ("$where", "WHERE"),
        ("$group", "GROUP BY"),
        ("$having", "HAVING"),
        ("$order", "ORDER BY"),
    ):
        if key in params:
            parts.append(f"{word} {params[key]}")
    if "$q" in params:
        parts.append(f"SEARCH {json.dumps(params['$q'])}")
    parts.append(f"LIMIT {params['$limit']}")
    if "$offset" in params:
        parts.append(f"OFFSET {params['$offset']}")
    result.effective_query = " ".join(parts)


def _set_url(result: QueryResult, name: str, url: str) -> None:
    if len(url) <= URL_MAX_CHARS:
        setattr(result, name, url)
    else:
        setattr(result, f"{name}_omitted", True)
