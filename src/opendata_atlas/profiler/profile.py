"""Profile a portal into draft claims (docs/knowledge-tooling.md: The profiler).

Every claim is an observation: evidence, and an assertion only where the checker passes on the
profiler's own probe rows. The profiler never writes an interpretation, a reliability, a
placeholder declaration or a tier; a reviewer adds those in a PR.

Requests go through `SodaClient`, awaited one at a time.
"""

from __future__ import annotations

import math
import re
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from opendata_atlas.constants import TIME_TYPES
from opendata_atlas.core.errors import AtlasError
from opendata_atlas.core.http import shape_error
from opendata_atlas.core.soql import identifier
from opendata_atlas.portals.checkers import CHECKERS, CheckerName, run_check
from opendata_atlas.portals.knowledge import SHARED_PLACEHOLDERS
from opendata_atlas.portals.model import Assertion, Claim, Scope, SoqlProbe
from opendata_atlas.portals.registry import context_for

if TYPE_CHECKING:
    from opendata_atlas.core.http import SodaClient
    from opendata_atlas.portals.model import PortalContext
    from opendata_atlas.portals.registry import RegistryEntry

#: Discovery identity check: three pages, as Registry step 3.
IDENTITY_PAGES = 3
PAGE_SIZE = 100
#: Text columns grouped per dataset, in schema order.
MAX_TEXT_COLUMNS = 20
#: A text column with more groups than this is not categorical and is not observed.
MAX_GROUPS = 100
#: Time-typed columns probed per dataset, in schema order.
MAX_TIME_COLUMNS = 3
#: The place-field fill assertion sits this far below the observed share.
FILL_MARGIN = 0.05
#: The diurnal-peak assertion's window around the observed peak hour.
PEAK_HALF_WIDTH = 2
#: At least this share of a window's rows at exactly 00:00:00 reads as an unknown-time default,
#: so the diurnal probe leaves them out (decisions row "Profiler reads default-midnight rows as a
#: diurnal peak"). A real time of day puts about 1 row in 86,400 on that exact second.
MIDNIGHT_MIN_SHARE = 0.02
#: A label candidate has at least this share of the layer's features as distinct values.
LABEL_MIN_DISTINCT = 0.9
#: GIS bookkeeping columns, never a label: row ids, GUIDs and geometry measures.
_NOT_LABELS = re.compile(r"^(_feature_id.*|objectid|globalid|shape_.*|st_area.*|st_length.*)$")


class DatasetProfile(BaseModel):
    dataset_id: str
    title: str
    page_views: int | None
    #: Ids of the claims emitted for this dataset.
    claims: list[str]
    #: Why a column or probe produced no claim.
    notes: list[str]


class ReviewValue(BaseModel):
    """An emitted value outside the shared placeholder vocabulary: the operator reviews it."""

    claim_id: str
    value: str


class ProfileReport(BaseModel):
    portal_id: str
    identity_verified: bool
    identity_detail: str
    asset_mix: dict[str, int]
    flagship_basis: str
    datasets: list[DatasetProfile]
    profiled_at: date
    #: Set when identity, the asset mix or the flagships failed upstream (`<step>: <code>`), or
    #: when a `--dataset` id is not on the portal (`datasets: not on this portal: <ids>`).
    error: str | None = None
    #: Every emitted value not in `SHARED_PLACEHOLDERS`, for review before committing.
    review_values: list[ReviewValue] = []


# Pure helpers


def identity_verified(pages: list[list[dict]], result_domain: str) -> bool:
    """True when there is a non-empty page and every result carries `result_domain`."""
    if not any(pages):
        return False
    return all(
        (r.get("metadata") or {}).get("domain") == result_domain for page in pages for r in page
    )


def _views(result: dict) -> int | None:
    v = ((result.get("resource") or {}).get("page_views") or {}).get("page_views_total")
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def flagships(results: list[dict], n: int) -> list[dict]:
    """The top `n` by `resource.page_views.page_views_total` descending (missing is 0), then id."""
    return sorted(results, key=lambda r: (-(_views(r) or 0), str(r["resource"]["id"])))[:n]


def _offset(zone: ZoneInfo, day: date) -> timedelta | None:
    return datetime.combine(day, time(0), zone).utcoffset()


def spring_forward(zone: ZoneInfo, lo: date, hi: date) -> date | None:
    """The latest date in `[lo, hi]` whose UTC offset increases (a spring-forward day)."""
    day = hi
    while day >= lo:
        try:
            after = _offset(zone, day + timedelta(days=1))
        except OverflowError:
            after = None
        before = _offset(zone, day)
        if after is not None and before is not None and after > before:
            return day
        day -= timedelta(days=1)
    return None


def gap_hour(zone: ZoneInfo, day: date) -> int | None:
    """The first wall-clock hour of `day` that does not exist in `zone`."""
    for h in range(24):
        wall = datetime.combine(day, time(h), zone)
        back = wall.astimezone(UTC).astimezone(zone)
        if back.replace(tzinfo=None) != wall.replace(tzinfo=None):
            return h
    return None


def _num(v: Any) -> float | None:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) else None


def _passing(
    checker: CheckerName, params: dict[str, Any], probe: int, rows: Any
) -> Assertion | None:
    """The assertion, only if it passes on the profiler's own probe rows."""
    typed = CHECKERS[checker][0].model_validate(params)
    if run_check(checker, typed, rows).outcome != "passed":
        return None
    return Assertion(checker=checker, probe=probe, params=params)


def _probe(query: str, observation: str, today: date) -> SoqlProbe:
    return SoqlProbe(kind="soql_probe", query=query, observed_at=today, observation=observation)


def _share(part: float, whole: float) -> str:
    return f"{part:,.0f} of {whole:,.0f} rows ({part / whole:.3f})" if whole else "0 rows"


def _quote(value: str) -> str:
    """A value as it reads in an observation: double-quoted, so padding shows."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _groups(rows: list[dict]) -> list[tuple[str, float]]:
    """(value, count) for each group with a text value and a readable count; nulls are dropped."""
    out = []
    for r in rows:
        v, n = r.get("v"), _num(r.get("n"))
        if isinstance(v, str) and n is not None:
            out.append((v, n))
    return out


def observe_text(
    dataset_id: str, column: str, query: str, rows: list[dict], today: date
) -> list[Claim]:
    """A placeholder-share claim for shared-vocabulary values, and a padded-values claim.

    `rows` are `query`'s groups (`v`, `n`). More than `MAX_GROUPS` groups is not categorical:
    nothing is observed.
    """
    if len(rows) > MAX_GROUPS:
        return []
    groups = _groups(rows)
    total = sum(_num(r.get("n")) or 0 for r in rows)
    scope = Scope(dataset=dataset_id, column=column)
    claims: list[Claim] = []

    candidates = [(v, n) for v, n in groups if v in SHARED_PLACEHOLDERS]
    if candidates:
        parts = "; ".join(f"{_quote(v)} {_share(n, total)}" for v, n in candidates)
        observation = f"Groups include shared-vocabulary placeholder values: {parts}."
        assertions = [
            a
            for v, _ in candidates
            if (a := _passing("value_present", {"column": "v", "value": v, "count": "n"}, 0, rows))
        ]
        claims.append(
            Claim(
                id=f"{dataset_id}-{column}-placeholders",
                kind="placeholder_share",
                scope=scope,
                evidence=[_probe(query, observation, today)],
                assertion=assertions,
            )
        )

    padded = [(v, n) for v, n in groups if v != v.strip()]
    if padded:
        top_value, top_n = min(padded, key=lambda g: (-g[1], g[0]))
        padded_rows = sum(n for _, n in padded)
        assertion = _passing(
            "value_present", {"column": "v", "value": top_value, "count": "n"}, 0, rows
        )
        # The value is quoted only beside its assertion, so every emitted value is in an
        # assertion's params, where `review_values` lists it.
        top = f"most common {_quote(top_value)}" if assertion else "the most common"
        observation = (
            f"{len(padded)} of {len(groups)} groups have leading or trailing whitespace, "
            f"{_share(padded_rows, total)}; {top} has {top_n:,.0f} rows."
        )
        claims.append(
            Claim(
                id=f"{dataset_id}-{column}-padded",
                kind="padded_values",
                scope=scope,
                evidence=[_probe(query, observation, today)],
                assertion=[assertion] if assertion else [],
            )
        )
    return claims


def _fill_min(share: float) -> float:
    """`share - FILL_MARGIN`, rounded down to hundredths, at least 0.01."""
    return max(math.floor(round((share - FILL_MARGIN) * 100, 6)) / 100, 0.01)


def label_candidate(columns: list[dict[str, Any]]) -> str | None:
    """The layer column most likely to name each feature, from its view metadata.

    A candidate is a text or number column that is not GIS bookkeeping (`_NOT_LABELS`) and,
    where `cachedContents.cardinality` is known, has distinct values for at least
    `LABEL_MIN_DISTINCT` of the features (`_feature_id`'s cardinality, else the largest
    known). That drops constants such as a state code and groupings such as a precinct.
    Among candidates, a name containing `name` or `label` comes first, then text before
    number, then schema order.
    """

    def distinct(c: dict[str, Any]) -> float | None:
        return _num((c.get("cachedContents") or {}).get("cardinality"))

    named = [c for c in columns if isinstance(c, dict) and isinstance(c.get("fieldName"), str)]
    feature_id = next((c for c in named if c["fieldName"] == "_feature_id"), None)
    known = [d for c in named if (d := distinct(c)) is not None]
    features = (distinct(feature_id) if feature_id else None) or max(known, default=None)
    candidates = [
        c
        for c in named
        if c.get("dataTypeName") in ("text", "number")
        and not _NOT_LABELS.match(c["fieldName"])
        and (features is None or (d := distinct(c)) is None or d >= LABEL_MIN_DISTINCT * features)
    ]
    # A stable sort, so schema order breaks the ties.
    ranked = sorted(
        candidates,
        key=lambda c: (
            not ("name" in c["fieldName"] or "label" in c["fieldName"]),
            c.get("dataTypeName") != "text",
        ),
    )
    return ranked[0]["fieldName"] if ranked else None


def observe_region(
    dataset_id: str,
    column: str,
    layer_id: str,
    query: str,
    rows: list[dict],
    today: date,
    *,
    label_column: str | None = None,
) -> Claim:
    """A place-field fill-rate observation for a computed-region column.

    `rows` are `query`'s one row (`filled`, `n`). The observation names the layer and the
    candidate label column; nothing says what the layer means.
    """
    row = rows[0] if len(rows) == 1 else {}
    filled, n = _num(row.get("filled")), _num(row.get("n"))
    label = f"`{label_column}`" if label_column else "none found"
    where = f"computed-region layer {layer_id}, candidate label column {label}"
    assertions: list[Assertion] = []
    if filled is None or n is None:
        observation = f"No readable fill count; {where}."
    else:
        observation = f"{_share(filled, n)} have a value; {where}."
        if n:
            params = {"numerator": "filled", "denominator": "n", "min": _fill_min(filled / n)}
            if a := _passing("share_by_group", params, 0, rows):
                assertions.append(a)
    return Claim(
        id=f"{dataset_id}-{column}-fill",
        kind="place_field",
        scope=Scope(dataset=dataset_id, column=column),
        evidence=[_probe(query, observation, today)],
        assertion=assertions,
    )


def _hour_counts(rows: list[dict]) -> dict[int, float]:
    out: dict[int, float] = {}
    for r in rows:
        h, n = _num(r.get("h")), _num(r.get("n"))
        if h is not None and n is not None and h == int(h) and 0 <= h <= 23:
            out[int(h)] = out.get(int(h), 0) + n
    return out


def observe_time(
    dataset_id: str,
    column: str,
    gap: tuple[str, list[dict]] | None,
    day: tuple[str, list[dict]],
    today: date,
    *,
    gap_hour: int = 2,
    midnight: tuple[str, float, float] | None = None,
) -> Claim | None:
    """A column-timezone observation from a spring-forward-day probe and a year-by-hour probe.

    `gap` and `day` are each (query, rows of `h`, `n`); `gap` is None in a zone with no
    spring-forward day in range. `midnight` is (query, rows in the window, rows at exactly
    00:00:00) when `day` leaves those rows out. None when every probe returned no rows.
    The claim names no timezone: it records what the hours show.
    """
    gap_query, gap_rows = gap if gap is not None else ("", [])
    day_query, day_rows = day
    if not gap_rows and not day_rows:
        return None
    evidence: list[SoqlProbe] = []
    assertions: list[Assertion] = []
    if gap is not None:
        by_hour = _hour_counts(gap_rows)
        before, after = (gap_hour - 1) % 24, (gap_hour + 1) % 24
        gap_obs = (
            f"On the spring-forward day probed, hour {gap_hour} has "
            f"{by_hour.get(gap_hour, 0):,.0f} rows; hours {before} and {after} have "
            f"{by_hour.get(before, 0):,.0f} and {by_hour.get(after, 0):,.0f}."
        )
        evidence.append(_probe(gap_query, gap_obs, today))
        if a := _passing("dst_gap", {"gap_hour": gap_hour}, 0, gap_rows):
            assertions.append(a)
    day_probe = len(evidence)
    year = _hour_counts(day_rows)
    if year:
        peak = min(year, key=lambda h: (-year[h], h))
        total = sum(year.values())
        day_obs = (
            f"Rows peak at hour {peak} ({year[peak]:,.0f} of {total:,.0f}); "
            f"{len(year)} of 24 hours populated."
        )
        params = {
            "peak_from": max(peak - PEAK_HALF_WIDTH, 0),
            "peak_to": min(peak + PEAK_HALF_WIDTH, 23),
        }
        if a := _passing("diurnal_peak", params, day_probe, day_rows):
            assertions.append(a)
    else:
        day_obs = "No rows by hour in the window."
    if midnight is not None:
        day_obs += " Rows at exactly 00:00:00 are left out (next probe)."
    evidence.append(_probe(day_query, day_obs, today))
    if midnight is not None:
        m_query, m_total, m_count = midnight
        evidence.append(
            _probe(
                m_query,
                f"{_share(m_count, m_total)} in the window are at exactly 00:00:00, which may be "
                "a default for an unknown time.",
                today,
            )
        )
    return Claim(
        id=f"{dataset_id}-{column}-timezone",
        kind="column_timezone",
        scope=Scope(dataset=dataset_id, column=column),
        evidence=evidence,
        assertion=assertions,
    )


# The run


def _discovery(entry: RegistryEntry) -> str:
    return f"https://api.{entry.identity.catalog_region}.socrata.com/api/catalog/v1"


def _results(payload: Any) -> list[dict]:
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list) or not all(isinstance(r, dict) for r in results):
        raise shape_error("Expected Discovery results.")
    return results


async def _identity(
    client: SodaClient, portal: PortalContext, entry: RegistryEntry
) -> tuple[bool, str]:
    pages: list[list[dict]] = []
    for page in range(IDENTITY_PAGES):
        params = {**entry.identity.catalog_query, "limit": PAGE_SIZE, "offset": page * PAGE_SIZE}
        results = _results(await client.get_json(_discovery(entry), params, portal=portal))
        if not results:
            break
        pages.append(results)
        if len(results) < PAGE_SIZE:
            break
    expected = entry.identity.result_domain
    ok = identity_verified(pages, expected)
    seen: dict[str, int] = {}
    for r in (r for p in pages for r in p):
        d = str((r.get("metadata") or {}).get("domain"))
        seen[d] = seen.get(d, 0) + 1
    n = sum(seen.values())
    query = "&".join(f"{k}={v}" for k, v in entry.identity.catalog_query.items())
    if ok:
        detail = f"All {n} results on {len(pages)} Discovery pages ({query}) carry {expected}."
    else:
        detail = (
            f"{seen.get(expected, 0)} of {n} results on {len(pages)} Discovery pages ({query}) "
            f"carry {expected}; metadata.domain seen: {dict(sorted(seen.items()))}."
        )
    return ok, detail


async def _asset_mix(client: SodaClient, portal: PortalContext, entry: RegistryEntry) -> dict:
    url = f"{_discovery(entry)}/domains/{entry.identity.catalog_domain}/facets"
    facets = await client.get_json(url, portal=portal)
    for facet in facets if isinstance(facets, list) else []:
        if isinstance(facet, dict) and facet.get("facet") == "datatypes":
            return {
                str(v["value"]): int(v["count"])
                for v in facet.get("values") or []
                if isinstance(v, dict) and "value" in v and isinstance(v.get("count"), int)
            }
    raise shape_error("Expected a datatypes facet.")


async def _flagships(
    client: SodaClient, portal: PortalContext, entry: RegistryEntry, n: int
) -> tuple[list[dict], str]:
    params = {
        **entry.identity.catalog_query,
        "only": "dataset",
        "order": "page_views_total",
        "limit": PAGE_SIZE,
    }
    results = _results(await client.get_json(_discovery(entry), params, portal=portal))
    own = [
        r
        for r in results
        if (r.get("metadata") or {}).get("domain") == entry.identity.result_domain
        and isinstance((r.get("resource") or {}).get("id"), str)
    ]
    picked = flagships(own, n)
    basis = (
        f"Discovery only=dataset&order=page_views_total&limit={PAGE_SIZE} ({len(own)} results), "
        "re-sorted by resource.page_views.page_views_total descending (missing as 0), then id; "
        f"top {len(picked)}."
    )
    return picked, basis


async def _requested(
    client: SodaClient, portal: PortalContext, entry: RegistryEntry, ids: list[str]
) -> tuple[list[dict], str, list[str]]:
    """The datasets named by `--dataset`, in the order given (a repeated id once), and the ids
    not on this portal."""
    ids = list(dict.fromkeys(ids))
    params = {**entry.identity.catalog_query, "only": "dataset", "ids": ids, "limit": len(ids)}
    results = _results(await client.get_json(_discovery(entry), params, portal=portal))
    own = {
        r["resource"]["id"]: r
        for r in results
        if (r.get("metadata") or {}).get("domain") == entry.identity.result_domain
        and isinstance((r.get("resource") or {}).get("id"), str)
    }
    picked = [own[i] for i in ids if i in own]
    missing = [i for i in ids if i not in own]
    basis = f"Requested by --dataset: {', '.join(ids)} (Discovery only=dataset&ids=...)."
    return picked, basis, missing


def _code(e: AtlasError) -> str:
    return str(e.envelope.code)


class _Dataset:
    """One dataset's probes, in order; each failure becomes a note."""

    def __init__(
        self, client: SodaClient, portal: PortalContext, dataset_id: str, today: date
    ) -> None:
        self.client, self.portal, self.id, self.today = client, portal, dataset_id, today
        self.claims: list[Claim] = []
        self.notes: list[str] = []

    async def rows(self, query: str, what: str, dataset: str | None = None) -> list[dict] | None:
        try:
            return await self.client.soql(self.portal, dataset or self.id, {"$query": query})
        except AtlasError as e:
            self.notes.append(f"{what}: probe failed ({_code(e)}).")
            return None

    async def run(self, layer_labels: dict[str, str | None]) -> None:
        try:
            view = await self.client.view(self.portal, self.id)
        except AtlasError as e:
            self.notes.append(f"Metadata unavailable ({_code(e)}); not profiled.")
            return
        listed = view.get("columns") or []
        columns = [c for c in listed if isinstance(c, dict) and isinstance(c.get("fieldName"), str)]
        if len(columns) < len(listed):
            self.notes.append(f"{len(listed) - len(columns)} columns without a field name skipped.")
        if not columns:
            self.notes.append("No columns in metadata; not profiled.")
            return
        count = await self.rows("SELECT count(*) AS n", "row count")
        if count is None:
            return
        n = _num(count[0].get("n")) if len(count) == 1 else None
        if n is None:
            self.notes.append("Row count unreadable; not profiled.")
            return
        if n == 0:
            self.notes.append("Dataset has 0 rows; no column probes run.")
            return
        await self.regions(columns, layer_labels)
        await self.texts(columns)
        await self.times(columns)

    async def regions(self, columns: list[dict], layer_labels: dict[str, str | None]) -> None:
        for c in columns:
            region = ((c.get("computationStrategy") or {}).get("parameters") or {}).get("region")
            if not region:
                continue
            col, layer = c["fieldName"], str(region).lstrip("_")
            if layer not in layer_labels:
                layer_labels[layer] = await self.label_column(layer)
            query = f"SELECT count({identifier(col)}) AS filled, count(*) AS n"
            rows = await self.rows(query, col)
            if rows is not None:
                self.claims.append(
                    observe_region(
                        self.id,
                        col,
                        layer,
                        query,
                        rows,
                        self.today,
                        label_column=layer_labels[layer],
                    )
                )

    async def label_column(self, layer: str) -> str | None:
        """The layer's candidate label column (`label_candidate`)."""
        try:
            view = await self.client.view(self.portal, layer)
        except AtlasError as e:
            self.notes.append(f"Layer {layer} metadata unavailable ({_code(e)}).")
            return None
        return label_candidate(view.get("columns") or [])

    async def texts(self, columns: list[dict]) -> None:
        text = [c["fieldName"] for c in columns if c.get("dataTypeName") == "text"]
        if len(text) > MAX_TEXT_COLUMNS:
            self.notes.append(
                f"{len(text) - MAX_TEXT_COLUMNS} text columns after the first "
                f"{MAX_TEXT_COLUMNS} not probed."
            )
        for col in text[:MAX_TEXT_COLUMNS]:
            q = identifier(col)
            query = (
                f"SELECT {q} AS v, count(*) AS n GROUP BY {q} ORDER BY n DESC "
                f"LIMIT {MAX_GROUPS + 1}"
            )
            rows = await self.rows(query, col)
            if rows is None:
                continue
            if len(rows) > MAX_GROUPS:
                self.notes.append(
                    f"{col}: more than {MAX_GROUPS} groups, not categorical; skipped."
                )
                continue
            if any(_has_surrogate(r.get("v")) for r in rows):
                # The TOML would carry U+FFFD instead, which the assertion could not match.
                self.notes.append(f"{col}: values that are not valid Unicode; skipped.")
                continue
            self.claims.extend(observe_text(self.id, col, query, rows, self.today))

    async def times(self, columns: list[dict]) -> None:
        cols = [c["fieldName"] for c in columns if c.get("dataTypeName") in TIME_TYPES]
        if not cols:
            self.notes.append("No time-typed column; no timezone probes.")
            return
        zone_name = self.portal.identity.timezone
        for col in cols[:MAX_TIME_COLUMNS]:
            if zone_name is None:
                self.notes.append(f"{col}: the portal has no timezone; no timezone probes.")
                continue
            await self.time(col, ZoneInfo(zone_name))

    async def window(self, col: str) -> tuple[date, date] | None:
        """The column's min and max dates, the max capped at today; None, noted, if unusable."""
        q = identifier(col)
        rows = await self.rows(f"SELECT min({q}) AS lo, max({q}) AS hi", col)
        if rows is None:
            return None
        row = rows[0] if len(rows) == 1 else {}
        try:
            lo = datetime.fromisoformat(str(row["lo"])).date()
            hi = datetime.fromisoformat(str(row["hi"])).date()
        except (KeyError, ValueError):
            self.notes.append(f"{col}: no readable min and max; no timezone probes.")
            return None
        if hi > self.today:
            self.notes.append(
                f"{col}: max {hi} is after today ({self.today}); the probe window ends today."
            )
            hi = self.today
        if hi < lo:
            self.notes.append(f"{col}: every row is dated after today; no timezone probes.")
            return None
        return lo, hi

    async def time(self, col: str, zone: ZoneInfo) -> None:
        if (bounds := await self.window(col)) is None:
            return
        lo, hi = bounds
        day = spring_forward(zone, lo, hi)
        hour = gap_hour(zone, day) if day else None
        if day is None or hour is None:
            day = hour = None
            self.notes.append(
                f"{col}: no spring-forward day in {zone.key} between {lo} and {hi}; "
                "by-hour probe only."
            )
        q = identifier(col)
        by_hour = f"SELECT date_extract_hh({q}) AS h, count(*) AS n WHERE"
        start = max(hi - timedelta(days=365), lo)
        window = f"{q} >= '{_ts(start)}' AND {q} < '{_ts(hi + timedelta(days=1))}'"
        day_query = f"{by_hour} {window} GROUP BY h"
        gap: tuple[str, list[dict]] | None = None
        if day is not None:
            gap_query = (
                f"{by_hour} {q} >= '{_ts(day)}' AND {q} < '{_ts(day + timedelta(days=1))}' "
                "GROUP BY h"
            )
            if (gap_rows := await self.rows(gap_query, col)) is None:
                return
            gap = (gap_query, gap_rows)
        if (day_rows := await self.rows(day_query, col)) is None:
            return
        if set(_hour_counts(gap[1] if gap else [])) | set(_hour_counts(day_rows)) == {0}:
            self.notes.append(f"{col}: date-only; no timezone test applies.")
            return
        midnight = await self.midnight(col, window)
        if midnight is not None:
            day_query = (
                f"{by_hour} {window} AND (date_extract_hh({q}) != 0 OR "
                f"date_extract_mm({q}) != 0 OR date_extract_ss({q}) != 0) GROUP BY h"
            )
            if (day_rows := await self.rows(day_query, col)) is None:
                return
        claim = observe_time(
            self.id,
            col,
            gap,
            (day_query, day_rows),
            self.today,
            gap_hour=2 if hour is None else hour,
            midnight=midnight,
        )
        if claim is None:
            self.notes.append(f"{col}: no rows in the probes; no timezone claim.")
        else:
            self.claims.append(claim)

    async def midnight(self, col: str, window: str) -> tuple[str, float, float] | None:
        """(query, rows, rows at exactly 00:00:00) when those rows reach `MIDNIGHT_MIN_SHARE`."""
        q = identifier(col)
        query = (
            f"SELECT count(*) AS n, sum(case(date_extract_hh({q}) = 0 AND "
            f"date_extract_mm({q}) = 0 AND date_extract_ss({q}) = 0, 1, true, 0)) AS midnight "
            f"WHERE {window}"
        )
        rows = await self.rows(query, col)
        row = rows[0] if rows and len(rows) == 1 else {}
        total, count = _num(row.get("n")), _num(row.get("midnight"))
        if not total or count is None or count / total < MIDNIGHT_MIN_SHARE:
            return None
        return query, total, count


def _has_surrogate(v: Any) -> bool:
    return isinstance(v, str) and any(0xD800 <= ord(ch) <= 0xDFFF for ch in v)


def _ts(d: date) -> str:
    return f"{d.isoformat()}T00:00:00"


async def profile_portal(
    client: SodaClient,
    entry: RegistryEntry,
    *,
    datasets: int,
    today: date,
    dataset_ids: list[str] | None = None,
) -> tuple[ProfileReport, list[Claim]]:
    """Profile the portal's top `datasets` datasets, or exactly `dataset_ids` when given.
    Requests run one at a time.

    An unverified identity, or an upstream failure in identity, the asset mix or the flagships,
    stops the run: the report says why (`error` for a failure), with no datasets and no claims.
    So does a requested dataset that is not on the portal (`error` names it).
    """
    portal = context_for(entry.identity, None)
    report = ProfileReport(
        portal_id=entry.identity.id,
        identity_verified=False,
        identity_detail="",
        asset_mix={},
        flagship_basis="",
        datasets=[],
        profiled_at=today,
    )
    step = "identity"
    try:
        report.identity_verified, report.identity_detail = await _identity(client, portal, entry)
        if not report.identity_verified:
            return report, []
        step = "asset mix"
        report.asset_mix = await _asset_mix(client, portal, entry)
        step = "flagships"
        if dataset_ids:
            picked, report.flagship_basis, missing = await _requested(
                client, portal, entry, dataset_ids
            )
            if missing:
                report.error = f"datasets: not on this portal: {', '.join(missing)}"
                return report, []
        else:
            picked, report.flagship_basis = await _flagships(client, portal, entry, datasets)
    except AtlasError as e:
        report.error = f"{step}: {_code(e)}"
        return report, []
    claims: list[Claim] = []
    layer_labels: dict[str, str | None] = {}
    for result in picked:
        resource = result["resource"]
        ds = _Dataset(client, portal, resource["id"], today)
        await ds.run(layer_labels)
        claims.extend(ds.claims)
        report.datasets.append(
            DatasetProfile(
                dataset_id=ds.id,
                title=str(resource.get("name") or ""),
                page_views=_views(result),
                claims=[c.id for c in ds.claims],
                notes=ds.notes,
            )
        )
    report.review_values = [
        ReviewValue(claim_id=c.id, value=v)
        for c in claims
        for a in c.assertion
        if isinstance(v := a.params.get("value"), str) and v not in SHARED_PLACEHOLDERS
    ]
    return report, claims
