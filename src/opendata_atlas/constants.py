"""Engine-wide limits and names; per-portal facts live under `opendata_atlas.portals`."""

from __future__ import annotations

SERVER_NAME = "opendata-atlas"
SERVER_TITLE = "Open Data Atlas"
TOOL_PREFIX = "atlas_"
URI_SCHEME = "opendata-atlas"

#: A portal id or alias as callers pass it (either case); no surrounding whitespace.
PORTAL_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9.-]{1,99}$"
#: Any case is accepted; the tool upper-cases the argument before it filters.
COUNTRY_PATTERN = r"^[A-Za-z]{2}$"
#: Operator allowlist: comma-separated portal ids or aliases; blank or unset allows every portal.
PORTALS_ENV = "OPENDATA_ATLAS_PORTALS"

DATASET_ID_PATTERN = r"^[a-z0-9]{4}-[a-z0-9]{4}$"

SEARCH_PAGE_SIZE_MAX = 50
QUERY_PAGE_SIZE_MAX = 500
QUERY_LOGICAL_CAP = 10_000
QUERY_TEXT_MAX_BYTES = 4096
SAMPLE_ROWS_MAX = 5
FIND_PORTALS_PAGE_SIZE_MAX = 50
FIND_PORTALS_DEFAULT_PAGE_SIZE = 10

RESULT_BYTE_BUDGET = 24 * 1024
TOOLS_LIST_BYTE_BUDGET = 24 * 1024

CACHE_TTL_SECONDS = 3600

#: Dataset schemas, refreshed by every describe and on `no_such_column`.
VIEW_TTL_SECONDS = 3600
VIEW_CACHE_MAX = 256
REGION_LABEL_TTL_SECONDS = 24 * 3600
REGION_LABEL_CACHE_MAX = 4096

INSTRUCTIONS_SENTINEL = "END OPENDATA ATLAS INSTRUCTIONS"

#: Where a defect in this server is reported. Also `[project.urls] Issues` in pyproject.toml,
#: and from there manifest.json `support`; `tests/test_issues_url.py` pins the copies together.
ISSUES_URL = "https://github.com/briandconnelly/opendata-atlas/issues"

UPSTREAM_TIMEOUT_SECONDS = 30.0
DESCRIBE_AGGREGATE_TIMEOUT_SECONDS = 10.0
#: The external-asset lookup beside a tabular search is optional; it must not stall the search.
SEARCH_EXTERNAL_TIMEOUT_SECONDS = 5.0
SEARCH_EXTERNAL_LIMIT = 3
UPSTREAM_MAX_BYTES = 8 * 1024 * 1024
#: Concurrent requests to one upstream host; keeps one busy portal from starving the others.
PER_HOST_CONCURRENCY = 4
CURSOR_TTL_SECONDS = 3600

GEO_TYPES = frozenset({"point", "location"})
TIME_TYPES = frozenset({"floating_timestamp", "calendar_date", "fixed_timestamp", "date"})

#: Upper bound written into download_url; SODA2 accepted it when probed 2026-10-15.
DOWNLOAD_LIMIT = 1_000_000_000
URL_MAX_CHARS = 2048
#: Whole-call deadlines, metadata fetch included; tool descriptions state these.
QUERY_DEADLINE_SECONDS = 30.0
DESCRIBE_DEADLINE_SECONDS = 30.0
