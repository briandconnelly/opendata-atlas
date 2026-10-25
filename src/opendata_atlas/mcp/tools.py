"""The five tools (docs/design.md: Tools).

Handlers raise `AtlasError`; `mcp/server.py` turns every failure, including framework
argument validation, into the error envelope."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, Literal

# FastMCP resolves return annotations at registration, so this stays a runtime import.
from fastmcp.tools import ToolResult  # noqa: TC002
from fastmcp.tools.function_tool import FunctionTool
from mcp.types import ToolAnnotations
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from opendata_atlas.constants import (
    COUNTRY_PATTERN,
    DATASET_ID_PATTERN,
    FIND_PORTALS_PAGE_SIZE_MAX,
    PORTAL_PATTERN,
    QUERY_PAGE_SIZE_MAX,
    QUERY_TEXT_MAX_BYTES,
    SAMPLE_ROWS_MAX,
    SEARCH_PAGE_SIZE_MAX,
)
from opendata_atlas.core import arguments, catalog, describe, portals, query, reference_service
from opendata_atlas.core.http import get_client
from opendata_atlas.core.models import (
    DescribeResult,
    Detail,
    FindPortalsResult,
    QueryResult,
    ReferenceResult,
    SearchResult,
)
from opendata_atlas.mcp.result import success
from opendata_atlas.mcp.schema import compact_schema
from opendata_atlas.portals.registry import load_registry
from opendata_atlas.portals.resolve import resolve_portal

if TYPE_CHECKING:
    from fastmcp import FastMCP

_READ_ONLY_OPEN = ToolAnnotations(read_only_hint=True, open_world_hint=True)
_READ_ONLY_CLOSED = ToolAnnotations(read_only_hint=True, open_world_hint=False)

Portal = Annotated[
    str,
    Field(
        pattern=PORTAL_PATTERN,
        description="Portal id (its hostname) or alias, from atlas_find_portals. "
        "Repeat it on every page of a paged call.",
    ),
]
DatasetId = Annotated[
    str,
    Field(
        pattern=DATASET_ID_PATTERN,
        description="Socrata dataset id, e.g. abcd-1234 (from atlas_search_datasets).",
    ),
]
SearchDetail = Annotated[
    Detail | None, Field(description="summary (default) or full: adds descriptions.")
]
DescribeDetail = Annotated[
    Detail | None,
    Field(description="summary (default) or full: adds place-field values and column stats."),
]
QueryDetail = Annotated[
    Detail | None,
    Field(
        description="summary (default) or full: adds query_url and download_url "
        "(CSV of all matching rows)."
    ),
]
Cursor = Annotated[
    str | None,
    Field(min_length=1, description="next_cursor from the previous page; omit for page one."),
]
Text = Annotated[str, Field(min_length=1, max_length=QUERY_TEXT_MAX_BYTES)]


class Near(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: Annotated[
        str, Field(min_length=1, description="A column listed in describe's geo_columns.")
    ]
    latitude: Annotated[float, Field(ge=-90, le=90)]
    longitude: Annotated[float, Field(ge=-180, le=180)]
    radius_m: Annotated[float, Field(gt=0, le=50_000, description="Radius in meters.")]


def _upper(value: Any) -> Any:
    return value.upper() if isinstance(value, str) else value


async def atlas_find_portals(
    query: Annotated[
        str | None,
        Field(
            min_length=1,
            max_length=100,
            description="Place, portal name, alias or host label, e.g. Chicago. Every word "
            "must appear in one name; drop extra words if nothing matches. "
            "Omit, with no other argument, to page through every portal, curated first.",
        ),
    ] = None,
    level: Annotated[
        Literal["city", "county", "region", "state", "national", "other"] | None,
        Field(description="Only portals of this jurisdiction level; omit for all."),
    ] = None,
    country: Annotated[
        Annotated[str, Field(pattern=COUNTRY_PATTERN), BeforeValidator(_upper)] | None,
        Field(description="ISO 3166-1 alpha-2 country code, e.g. US (any case); omit for all."),
    ] = None,
    tier: Annotated[
        Literal["generic", "profiled", "curated"] | None,
        Field(description="Only portals of this tier; omit for all tiers."),
    ] = None,
    page_size: Annotated[
        int | None,
        Field(ge=1, le=FIND_PORTALS_PAGE_SIZE_MAX, description="Default 10."),
    ] = None,
    cursor: Cursor = None,
) -> ToolResult:
    """Find portals by place name; the portal id it returns goes in every other tool's `portal`.

    Call this before any tool that takes `portal` when you lack its id.
    It never picks a portal for you: an ambiguous place returns every candidate, told apart
    by jurisdiction.level (a city portal and its county portal can both match).
    When candidates differ in jurisdiction.level, ask the user which they mean, unless the
    request already says.
    Candidates are ordered by match (alias, name, place_name, host), then tier, then id.
    No match is an empty candidates list, not an error.
    With cursor, send only cursor and optionally page_size.
    Example: {"query": "Chicago"}. Reads the shipped registry; no network call.
    """
    arguments.check_find_portals(locals())
    result = portals.find_portals(
        load_registry(),
        query=query,
        level=level,
        country=country,
        tier=tier,
        page_size=page_size,
        cursor=cursor,
    )
    return success(result)


async def atlas_search_datasets(
    portal: Portal,
    query: Annotated[
        str | None,
        Field(
            min_length=1,
            max_length=200,
            description="Words to match; omit to list the most-viewed.",
        ),
    ] = None,
    asset_scope: Annotated[
        Literal["tabular", "all"] | None,
        Field(
            description="tabular (default): queryable datasets and filter views. "
            "all: adds federated ArcGIS and external links, which cannot be queried."
        ),
    ] = None,
    category: Annotated[
        str | None,
        Field(
            min_length=1,
            max_length=100,
            description="Exact category name, e.g. Public Safety; omit for all.",
        ),
    ] = None,
    page_size: Annotated[
        int | None, Field(ge=1, le=SEARCH_PAGE_SIZE_MAX, description="Default 10.")
    ] = None,
    cursor: Cursor = None,
    detail: SearchDetail = None,
) -> ToolResult:
    """Find a portal's datasets by topic. Call when you lack a dataset id.

    Results are candidates: match_evidence lists the query words each one's metadata
    lacks. Only queryability "supported" can be described or queried; a tabular search
    also returns up to 3 external_matches, which cannot.
    Illustrative example: {"portal": "example-city", "query": "fire 911"}. Typically 1-3 s.
    """
    arguments.check_search(
        {
            "portal": portal,
            "query": query,
            "asset_scope": asset_scope,
            "category": category,
            "page_size": page_size,
            "cursor": cursor,
            "detail": detail,
        }
    )
    result = await catalog.search(
        get_client(),
        resolve_portal(portal),
        query=query,
        asset_scope=asset_scope or "tabular",
        category=category,
        page_size=page_size,
        cursor=cursor,
        detail=detail or "summary",
    )
    return success(result)


async def atlas_describe_dataset(
    portal: Portal,
    dataset_id: DatasetId,
    column_query: Annotated[
        str | None,
        Field(
            min_length=1,
            max_length=100,
            description="Only columns whose name or description contains this; omit for all.",
        ),
    ] = None,
    sample_rows: Annotated[
        int | None,
        Field(ge=0, le=SAMPLE_ROWS_MAX, description="Example rows to include. Default 0."),
    ] = None,
    detail: DescribeDetail = None,
    column_cursor: Annotated[
        str | None,
        Field(
            min_length=1,
            description="next_column_cursor from the previous page; omit for page one.",
        ),
    ] = None,
) -> ToolResult:
    """Decide whether and how to query a dataset: columns, live row count, data_coverage
    (actual time range), place fields for "in <area>" questions (with reliability),
    and geo columns for `near`.

    Call before querying a dataset whose columns you do not know.
    For area questions, use detail="full".
    Filter a place field on its `value`, never its label; an area may span several values.
    Illustrative example: {"portal": "example-city", "dataset_id": "abcd-1234", "detail": "full"}.
    With column_cursor, send only portal, dataset_id, column_query, detail, column_cursor.
    Typically 1-3 s; fails with query_timeout after 30 s.
    """
    arguments.check_describe(locals())
    result = await describe.describe(
        get_client(),
        resolve_portal(portal),
        dataset_id=dataset_id,
        column_query=column_query,
        sample_rows=sample_rows or 0,
        detail=detail,
        column_cursor=column_cursor,
    )
    return success(result)


async def atlas_query_dataset(
    portal: Portal,
    dataset_id: DatasetId,
    mode: Annotated[
        Literal["clauses", "soql"] | None,
        Field(
            description="clauses (default): built from the clause arguments, paged by cursor. "
            "soql: run `soql` verbatim, one page."
        ),
    ] = None,
    select: Annotated[
        list[Text] | None,
        Field(
            min_length=1,
            description='Columns or expressions, e.g. ["type", "count(*) AS n"]. '
            "Omit for all data columns.",
        ),
    ] = None,
    where: Annotated[
        str | None,
        Field(
            min_length=1,
            max_length=QUERY_TEXT_MAX_BYTES,
            description="SoQL predicate, e.g. \"datetime >= '2026-09-01T00:00:00'\". "
            "Never append Z or call now(); both fail. Omit for all rows.",
        ),
    ] = None,
    group_by: Annotated[
        list[Text] | None,
        Field(min_length=1, description='e.g. ["type"]; omit for no grouping.'),
    ] = None,
    having: Annotated[
        str | None,
        Field(
            min_length=1,
            max_length=QUERY_TEXT_MAX_BYTES,
            description='Predicate on aggregated rows, e.g. "n > 10"; omit for none.',
        ),
    ] = None,
    order_by: Annotated[
        list[Text] | None,
        Field(
            min_length=1,
            description='e.g. ["n DESC"]; omit for arbitrary order. DESC lists nulls first: '
            "for most recent, add `col IS NOT NULL` to where.",
        ),
    ] = None,
    search_text: Annotated[
        str | None,
        Field(
            min_length=1,
            max_length=200,
            description="Full-text search across text columns; omit for none.",
        ),
    ] = None,
    near: Annotated[
        Near | None,
        Field(description="Rows within radius_m meters of a point; omit for no distance filter."),
    ] = None,
    soql: Annotated[
        str | None,
        Field(
            min_length=1,
            max_length=QUERY_TEXT_MAX_BYTES,
            description="Full SoQL statement; set mode='soql' and no clause arguments. "
            "Not paged: use LIMIT <= page_size and advance OFFSET.",
        ),
    ] = None,
    page_size: Annotated[
        int | None,
        Field(
            ge=1,
            le=QUERY_PAGE_SIZE_MAX,
            description="Most rows to return (default 100; wide rows may return fewer). "
            "Omit on a continuation to keep the first page's size.",
        ),
    ] = None,
    cursor: Cursor = None,
    detail: QueryDetail = None,
) -> ToolResult:
    """Run a bounded read or aggregate on one dataset; paging stops at 10,000 rows.

    For counts and breakdowns, use count(*) with group_by, not row paging.
    With cursor, send only portal, dataset_id, cursor, and optionally page_size or detail.
    For all rows, give the user download_url (detail="full") instead of paging.
    Illustrative example: {"portal": "example-city", "dataset_id": "abcd-1234",
    "select": ["type", "count(*) AS n"], "group_by": ["type"], "order_by": ["n DESC"]}.
    Typically 1-5 s; fails with query_timeout after 30 s.
    """
    arguments.check_query(dict(locals()))
    result = await query.run(
        get_client(),
        resolve_portal(portal),
        dataset_id=dataset_id,
        mode=mode or "clauses",
        clauses={
            "select": select,
            "where": where,
            "group_by": group_by,
            "having": having,
            "order_by": order_by,
            "search_text": search_text,
            "near": near.model_dump() if near else None,
        },
        soql=soql,
        page_size=page_size,
        cursor=cursor,
        detail=detail or "summary",
    )
    return success(result)


async def atlas_get_reference(
    topic: Annotated[
        Literal["index", "capabilities", "portals", "guides", "soql", "errors", "contributing"]
        | None,
        Field(description="Default index."),
    ] = None,
    item_id: Annotated[
        str | None,
        Field(
            min_length=1,
            # PORTAL_PATTERN allows 100 characters, and topic portals takes a portal here.
            max_length=100,
            description="An item from the topic's entries, or for portals a portal id or "
            "alias; omit for the index.",
        ),
    ] = None,
    portal: Annotated[
        str | None,
        Field(
            pattern=PORTAL_PATTERN,
            description="Portal id or alias. Required for topic guides; rejected on other topics.",
        ),
    ] = None,
    cursor: Cursor = None,
) -> ToolResult:
    """Read the server's reference: capability summary, portals, dataset guides, SoQL help,
    error catalog, and tier definitions. Call with no arguments for the index.

    Example: {"topic": "soql", "item_id": "dates"}.
    With cursor, repeat only topic and, for guides, portal.
    """
    arguments.check_reference(locals())
    context = resolve_portal(portal) if portal is not None else None
    result = reference_service.read(context, topic or "index", item_id, cursor=cursor)
    return success(result)


_TOOLS: tuple[tuple[Any, type[BaseModel], ToolAnnotations], ...] = (
    (atlas_find_portals, FindPortalsResult, _READ_ONLY_CLOSED),
    (atlas_search_datasets, SearchResult, _READ_ONLY_OPEN),
    (atlas_describe_dataset, DescribeResult, _READ_ONLY_OPEN),
    (atlas_query_dataset, QueryResult, _READ_ONLY_OPEN),
    (atlas_get_reference, ReferenceResult, _READ_ONLY_CLOSED),
)


def register_tools(mcp: FastMCP) -> None:
    for fn, output_model, hints in _TOOLS:
        tool = FunctionTool.from_function(
            fn,
            annotations=hints,
            output_schema=compact_schema(output_model.model_json_schema()),
        )
        tool.parameters = compact_schema(tool.parameters)
        mcp.add_tool(tool)
