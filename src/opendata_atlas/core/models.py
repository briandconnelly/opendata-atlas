"""Success output shapes for the four tools (docs/design.md: Tools).

Top-level results are open (`extra="allow"`): the documented extension point for
minor-release additions [9.additive-direction]. Nested objects are closed.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Pydantic resolves field annotations at class creation, so this stays a runtime import.
from opendata_atlas.core.errors import Repair  # noqa: TC001

# PlaceKind lives with the portal model, which core.models must not be imported by.
from opendata_atlas.portals.model import (  # noqa: TC001
    Jurisdiction,
    KnowledgeLevel,
    PlaceKind,
    Validation,
)

Detail = Literal["summary", "full"]
Queryability = Literal["supported", "external", "unsupported", "unknown"]
Origin = Literal["live_query", "cached_metadata"]
#: `unknown`: a reviewed `ok` whose checks are stale (docs/design.md: Validation state and
#: freshness).
Reliability = Literal["ok", "partial", "unreliable", "unknown"]
#: The one `validation` value entry-level fields carry; they are omitted otherwise.
Stale = Literal["stale"]


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Open(BaseModel):
    model_config = ConfigDict(extra="allow")


class SourcePortal(Closed):
    id: str
    alias: str | None = None
    name: str
    tier: Literal["generic", "profiled", "curated"]
    timezone: str | None = None


class Source(Closed):
    request_id: str
    portal: SourcePortal | None = None
    now_local: str | None = None
    now_weekday: str | None = None
    now_local_reason: Literal["multi_zone", "unknown"] | None = None
    retrieved_at: str | None = None


# --- search -----------------------------------------------------------------


class DatasetSummary(Closed):
    dataset_id: str
    title: str
    asset_type: str
    queryability: Queryability
    portal_url: str
    updated_at: str | None = None
    guide_uri: str | None = None
    derived_from: str | None = None
    external_url: str | None = None
    category: str | None = None
    description: str | None = None


MatchField = Literal["title", "tags", "columns", "description"]


class MatchEvidence(Closed):
    """Which query words a result's catalog metadata visibly contains; never a relevance verdict."""

    dataset_id: str
    matched_terms: list[str]
    unmatched_terms: list[str]
    matched_fields: list[MatchField]
    #: The map or chart whose metadata matched, when the result was folded into its parent.
    matched_via: str | None = None


class SearchResult(Open):
    datasets: list[DatasetSummary]
    has_more: bool
    next_cursor: str | None = None
    match_evidence: list[MatchEvidence] | None = None
    external_matches: list[DatasetSummary] | None = None
    external_search_status: Literal["completed", "unavailable"] | None = None
    suggestion: Repair | None = None
    #: Entries from another portal's domain, removed from `datasets` and `external_matches`.
    foreign_results_dropped: int | None = None
    #: Paging ended at the catalog's result cap, not at the end of the matches (#24).
    truncated: bool | None = None
    truncation_hint: str | None = None
    source: Source


# --- knowledge --------------------------------------------------------------


class Knowledge(Closed):
    """Level none (nothing recorded), profiled (observations only) or reviewed (interpretations)."""

    level: KnowledgeLevel
    validation: Validation


class KnowledgeNotice(Closed):
    """What this result relies on that no reviewed claim covers; level is the dataset's."""

    level: KnowledgeLevel
    message: str


# --- describe ---------------------------------------------------------------


class RowCount(Closed):
    value: int | None = None
    origin: Origin | None = None
    status: Literal["ok", "timeout", "unavailable"] = "ok"


class Coverage(Closed):
    column: str
    min: str | None = None
    max: str | None = None
    origin: Origin | None = None
    status: Literal["ok", "timeout", "unavailable"] = "ok"


class ColumnStats(Closed):
    top: list[str] | None = None
    smallest: str | None = None
    largest: str | None = None
    null: int | None = None
    origin: Literal["cached_metadata"] = "cached_metadata"


class Column(Closed):
    name: str
    type: str
    description: str | None = None
    stats: ColumnStats | None = None
    #: Set only when a claim covers the column.
    knowledge: Knowledge | None = None


class PlaceValue(Closed):
    label: str
    value: str


class PlaceholderValue(Closed):
    value: str
    rows: int


class PlaceField(Closed):
    column: str
    kind: PlaceKind
    kind_label: str | None = None
    source: Literal["column", "computed_region"]
    reliability: Reliability
    reliability_reason: str | None = None
    #: Set only when the field's claim is `stale`.
    validation: Stale | None = None
    value_count: int | None = None
    values: list[PlaceValue] | None = None
    placeholder_values: list[PlaceholderValue] | None = None
    candidate_placeholders: list[PlaceholderValue] | None = Field(
        default=None,
        description="Common placeholder values found here but not declared; "
        "still counted in values and assigned_fraction.",
    )
    assigned_fraction: float | None = None
    null_rows: int | None = None
    non_null_rows: int | None = None
    layer_id: str | None = None
    label_column: str | None = None
    labels_available: bool | None = None
    layer_features: list[PlaceValue] | None = Field(
        default=None,
        description="When stats_status is not ok: every feature of the region layer as label "
        "and feature id, read from the layer; not which features rows use. Omitted for a layer "
        "of over 100 features or when the result budget is short.",
    )
    boundary_vintage: str | None = None
    stats_status: Literal["ok", "timeout", "unavailable"] | None = None


class GeoColumn(Closed):
    column: str
    type: str


class GeoUnusable(Closed):
    column: str
    reason: str


class TimeSemantics(Closed):
    column: str
    type: str
    timezone: str | None = None
    evidence: str | None = None
    #: Set only when the column's timezone claim is `stale`.
    validation: Stale | None = None


class UnitOfObservation(Closed):
    unit: str
    reason: str | None = None


class ExampleQuery(Closed):
    question: str
    arguments: dict[str, Any]


class DescribeResult(Open):
    dataset_id: str
    title: str
    queryability: Queryability
    row_count: RowCount
    data_coverage: list[Coverage]
    columns: list[Column]
    columns_total: int = Field(description="Columns matching column_query, across all pages.")
    has_more_columns: bool
    next_column_cursor: str | None = Field(
        default=None, description="Send as column_cursor for the next columns; omitted on the last."
    )
    stats_available: bool
    place_fields: list[PlaceField]
    geo_columns: list[GeoColumn]
    geo_unusable: list[GeoUnusable] | None = None
    time_semantics: list[TimeSemantics]
    knowledge: Knowledge
    #: Set only from a reviewed unit_of_observation claim.
    unit_of_observation: UnitOfObservation | None = None
    guide_uri: str | None = None
    example_queries: list[ExampleQuery] | None = None
    sample_rows: list[dict[str, Any]] | None = None
    source: Source


# --- query ------------------------------------------------------------------


class ResultColumn(Closed):
    name: str
    type: str


class CoverageWarning(Closed):
    column: str
    reliability: Reliability
    reason: str
    #: Set only when the field's claim is `stale`.
    validation: Stale | None = None


class QueryResult(Open):
    dataset_id: str
    columns: list[ResultColumn]
    rows: list[dict[str, Any]]
    returned_rows: int
    has_more: bool
    next_cursor: str | None = None
    truncated: bool
    truncation_reason: str | None = None
    truncation_hint: str | None = None
    consistency: Literal["stable", "best_effort", "single_page"]
    coverage_warnings: list[CoverageWarning] | None = None
    knowledge_notice: KnowledgeNotice | None = None
    #: Repairs for a first page that may have matched nothing by accident (ruling 47).
    hints: list[Repair] | None = None
    query_url: str | None = None
    query_url_omitted: bool | None = None
    download_url: str | None = None
    download_url_omitted: bool | None = None
    effective_query: str | None = None
    source: Source


# --- reference --------------------------------------------------------------


class ReferenceEntry(Closed):
    item_id: str
    title: str
    description: str
    uri: str
    dataset_id: str | None = None


class ReferenceResult(Open):
    topic: str
    uri: str
    title: str
    summary: str
    version: str
    entries: list[ReferenceEntry] | None = None
    #: Present whenever `entries` is; `next_cursor` only when more entries follow.
    has_more: bool | None = None
    next_cursor: str | None = None
    body: str | None = None
    source: Source


# --- portals ----------------------------------------------------------------


class PortalCandidate(Closed):
    id: str
    aliases: list[str]
    name: str
    jurisdiction: Jurisdiction | None = None
    tier: Literal["generic", "profiled", "curated"]
    timezone: str | None = None
    dataset_count: int | None = None
    #: How the query matched; absent when listing without a query.
    match: Literal["alias", "name", "place_name", "host"] | None = None


class FindPortalsResult(Open):
    candidates: list[PortalCandidate]
    has_more: bool
    next_cursor: str | None = None
    registry_version: str
    source: Source
