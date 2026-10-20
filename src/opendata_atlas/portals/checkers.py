"""Typed checkers for pack assertions (docs/design.md: Fact model).

A checker reads evidence rows or metadata and returns `passed`, `contradicted` or
`inconclusive`. Missing data is never `passed`. This module imports nothing from `model.py`:
the model imports the catalog, not the reverse.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    from collections.abc import Callable

Outcome = Literal["passed", "contradicted", "inconclusive"]
CheckerName = Literal[
    "share_by_group",
    "value_present",
    "value_absent",
    "dst_gap",
    "diurnal_peak",
    "metadata_equals",
    "metadata_before",
]


@dataclass(frozen=True)
class CheckResult:
    outcome: Outcome
    #: One line naming the group or value that decided the outcome.
    detail: str


class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid")


_WHERE = re.compile(r"^\s*(\w+)\s*(<=|>=|<|>|=|!=)\s*(-?\d+(?:\.\d+)?)\s*$")


class ShareByGroup(_Params):
    group: str | None = None
    numerator: str
    denominator: str
    where: str | None = Field(default=None, pattern=_WHERE.pattern)
    min: float | None = None
    max: float | None = None
    min_groups: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def _needs_a_bound(self) -> ShareByGroup:
        if self.min is None and self.max is None:
            raise ValueError("at least one of min and max is required")
        return self


class ValuePresent(_Params):
    column: str
    value: str
    count: str | None = None
    min_count: int = Field(default=1, ge=1)


class ValueAbsent(_Params):
    column: str
    value: str


class DstGap(_Params):
    hour: str = "h"
    count: str = "n"
    gap_hour: int = Field(default=2, ge=0, le=23)
    min_neighbor_rows: int = Field(default=1, ge=0)
    max_gap_rows: int = Field(default=0, ge=0)


class DiurnalPeak(_Params):
    hour: str = "h"
    count: str = "n"
    peak_from: int = Field(ge=0, le=23)
    peak_to: int = Field(ge=0, le=23)
    min_hours: int = Field(default=20, ge=1, le=24)
    min_rows: int = Field(default=100, ge=1)

    @model_validator(mode="after")
    def _ordered(self) -> DiurnalPeak:
        if self.peak_from > self.peak_to:
            raise ValueError("peak_from must not exceed peak_to")
        return self


class MetadataEquals(_Params):
    field: str
    value: str | int | float | bool


class MetadataBefore(_Params):
    field: str
    before: date


def _inconclusive(detail: str) -> CheckResult:
    return CheckResult("inconclusive", detail)


def _num(v: Any) -> float | None:
    """A row value as a finite number; anything else is missing."""
    if isinstance(v, bool) or v is None:
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) else None


def _rows(data: Any) -> list[dict[str, Any]] | None:
    if isinstance(data, list) and all(isinstance(r, dict) for r in data):
        return data
    return None


def _share_by_group(p: ShareByGroup, data: Any) -> CheckResult:
    rows = _rows(data)
    if rows is None:
        return _inconclusive("expected a list of rows")
    if not rows:
        return _inconclusive("empty result")
    if p.where is not None:
        m = _WHERE.match(p.where)
        assert m is not None  # the field pattern guarantees it
        field, op, bound = m.group(1), m.group(2), float(m.group(3))
        tests = {
            "<=": lambda v: v <= bound,
            ">=": lambda v: v >= bound,
            "<": lambda v: v < bound,
            ">": lambda v: v > bound,
            "=": lambda v: v == bound,
            "!=": lambda v: v != bound,
        }
        kept = []
        for r in rows:
            v = _num(r.get(field))
            if v is not None and tests[op](v):
                kept.append(r)
        rows = kept
    counted = 0
    for i, r in enumerate(rows):
        num, den = _num(r.get(p.numerator)), _num(r.get(p.denominator))
        if num is None or den is None or den == 0:
            continue
        counted += 1
        share = num / den
        label = f"group {p.group}={r.get(p.group)}" if p.group else f"row {i}"
        if (p.min is not None and share < p.min) or (p.max is not None and share > p.max):
            return CheckResult("contradicted", f"{label}: share {share:.3f} outside bounds")
    if counted < p.min_groups:
        return _inconclusive(f"{counted} counted groups, fewer than min_groups {p.min_groups}")
    return CheckResult("passed", f"{counted} groups within bounds")


def _value_present(p: ValuePresent, data: Any) -> CheckResult:
    rows = _rows(data)
    if rows is None:
        return _inconclusive("expected a list of rows")
    if not rows:
        return _inconclusive("empty result")
    hits = [r for r in rows if r.get(p.column) == p.value]
    if not hits:
        return CheckResult("contradicted", f"value {p.value!r} not found in {p.column}")
    if p.count is not None:
        for r in hits:
            n = _num(r.get(p.count))
            if n is None:
                return _inconclusive(f"value {p.value!r} has unreadable count {r.get(p.count)!r}")
            if n < p.min_count:
                return CheckResult(
                    "contradicted",
                    f"value {p.value!r} has count {r.get(p.count)!r} < {p.min_count}",
                )
    return CheckResult("passed", f"value {p.value!r} found in {p.column}")


def _value_absent(p: ValueAbsent, data: Any) -> CheckResult:
    rows = _rows(data)
    if rows is None:
        return _inconclusive("expected a list of rows")
    if not rows:
        return _inconclusive("empty result")
    if any(r.get(p.column) == p.value for r in rows):
        return CheckResult("contradicted", f"value {p.value!r} found in {p.column}")
    return CheckResult("passed", f"value {p.value!r} absent from {p.column}")


def _hour_counts(rows: list[dict[str, Any]], hour: str, count: str) -> dict[int, float]:
    """Row counts by hour of day; rows with an unreadable hour or count are dropped."""
    out: dict[int, float] = {}
    for r in rows:
        h, n = _num(r.get(hour)), _num(r.get(count))
        if h is None or n is None or h != int(h) or not 0 <= h <= 23:
            continue
        out[int(h)] = out.get(int(h), 0) + n
    return out


def _dst_gap(p: DstGap, data: Any) -> CheckResult:
    rows = _rows(data)
    if rows is None:
        return _inconclusive("expected a list of rows")
    if not rows:
        return _inconclusive("empty result")
    counts = _hour_counts(rows, p.hour, p.count)
    before, after = (p.gap_hour - 1) % 24, (p.gap_hour + 1) % 24
    for h in (before, after):
        if counts.get(h, 0) < p.min_neighbor_rows:
            return _inconclusive(f"hour {h} has fewer than {p.min_neighbor_rows} rows")
    for r in rows:
        if _num(r.get(p.hour)) == p.gap_hour and _num(r.get(p.count)) is None:
            return _inconclusive(f"hour {p.gap_hour} has unreadable count {r.get(p.count)!r}")
    gap = counts.get(p.gap_hour, 0)
    if gap <= p.max_gap_rows:
        return CheckResult("passed", f"hour {p.gap_hour} has {gap:g} rows")
    return CheckResult("contradicted", f"hour {p.gap_hour} has {gap:g} rows > {p.max_gap_rows}")


def _diurnal_peak(p: DiurnalPeak, data: Any) -> CheckResult:
    rows = _rows(data)
    if rows is None:
        return _inconclusive("expected a list of rows")
    if not rows:
        return _inconclusive("empty result")
    counts = _hour_counts(rows, p.hour, p.count)
    total = sum(counts.values())
    if len(counts) < p.min_hours:
        return _inconclusive(f"{len(counts)} hours, fewer than min_hours {p.min_hours}")
    if total < p.min_rows:
        return _inconclusive(f"{total:g} rows, fewer than min_rows {p.min_rows}")
    peak = min(counts, key=lambda h: (-counts[h], h))
    if p.peak_from <= peak <= p.peak_to:
        return CheckResult("passed", f"peak hour {peak} within {p.peak_from}-{p.peak_to}")
    return CheckResult("contradicted", f"peak hour {peak} outside {p.peak_from}-{p.peak_to}")


_MISSING = object()


def _dig(data: dict[str, Any], path: str) -> Any:
    cur: Any = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return _MISSING
        cur = cur[part]
    return cur


def _same(actual: Any, expected: Any) -> bool:
    if isinstance(actual, bool) or isinstance(expected, bool):
        return isinstance(actual, bool) and isinstance(expected, bool) and actual == expected
    if isinstance(actual, int | float) and isinstance(expected, int | float):
        return actual == expected
    return type(actual) is type(expected) and actual == expected


def _metadata_equals(p: MetadataEquals, data: Any) -> CheckResult:
    if not isinstance(data, dict):
        return _inconclusive("expected a metadata object")
    actual = _dig(data, p.field)
    if actual is _MISSING or actual is None:
        return _inconclusive(f"field {p.field} missing")
    if _same(actual, p.value):
        return CheckResult("passed", f"{p.field} equals {p.value!r}")
    return CheckResult("contradicted", f"{p.field} is {actual!r}, not {p.value!r}")


def _as_date(v: Any) -> date | None:
    if isinstance(v, bool):
        return None
    try:
        if isinstance(v, int | float):
            return datetime.fromtimestamp(v, UTC).date()
        if isinstance(v, str):
            s = v.strip()
            # Epoch seconds have 9 or more digits; "20151020" is an ISO basic date.
            if s.isdigit() and len(s) >= 9:
                return datetime.fromtimestamp(int(s), UTC).date()
            when = datetime.fromisoformat(s)
            if when.tzinfo is not None:
                when = when.astimezone(UTC)
            return when.date()
    except (ValueError, OverflowError, OSError):
        return None
    return None


def _metadata_before(p: MetadataBefore, data: Any) -> CheckResult:
    if not isinstance(data, dict):
        return _inconclusive("expected a metadata object")
    raw = _dig(data, p.field)
    if raw is _MISSING:
        return _inconclusive(f"field {p.field} missing")
    when = _as_date(raw)
    if when is None:
        return _inconclusive(f"field {p.field} is not an epoch or ISO date: {raw!r}")
    if when < p.before:
        return CheckResult("passed", f"{p.field} {when} is before {p.before}")
    return CheckResult("contradicted", f"{p.field} {when} is not before {p.before}")


#: Each checker's params model and the evidence kind it reads.
CHECKERS: dict[CheckerName, tuple[type[BaseModel], Literal["soql_probe", "metadata_probe"]]] = {
    "share_by_group": (ShareByGroup, "soql_probe"),
    "value_present": (ValuePresent, "soql_probe"),
    "value_absent": (ValueAbsent, "soql_probe"),
    "dst_gap": (DstGap, "soql_probe"),
    "diurnal_peak": (DiurnalPeak, "soql_probe"),
    "metadata_equals": (MetadataEquals, "metadata_probe"),
    "metadata_before": (MetadataBefore, "metadata_probe"),
}


_RUNNERS: dict[CheckerName, Callable[[Any, Any], CheckResult]] = {
    "share_by_group": _share_by_group,
    "value_present": _value_present,
    "value_absent": _value_absent,
    "dst_gap": _dst_gap,
    "diurnal_peak": _diurnal_peak,
    "metadata_equals": _metadata_equals,
    "metadata_before": _metadata_before,
}


def run_check(checker: CheckerName, params: BaseModel, data: Any) -> CheckResult:
    """Run one checker. `data` is the probe's rows (SoQL) or metadata object (metadata)."""
    model = CHECKERS[checker][0]
    if not isinstance(params, model):
        raise TypeError(f"{checker} takes {model.__name__}, not {type(params).__name__}")
    return _RUNNERS[checker](params, data)
