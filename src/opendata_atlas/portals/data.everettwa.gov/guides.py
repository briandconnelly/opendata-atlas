"""Everett's dataset guides (docs/design.md: Knowledge packs). Facts were probed live on 2026-10-20."""

from __future__ import annotations

from datetime import date

from opendata_atlas.core.guides import Example, Guide

#: When this pack's guide figures were probed (its docstring).
OBSERVED = date(2026, 10, 20)

SEPT_2026 = "'2026-09-01T00:00:00' and '2026-09-30T23:59:59'"


GUIDES: tuple[Guide, ...] = (
    Guide(
        "police-incidents",
        "f6vp-3svh",
        "Police Incidents",
        "Everett Police calls for service and officer-initiated activity since 2015; one row per incident.",
        """
## What a row is
One police incident (`eventnumber`), whether a 911 call or officer-initiated activity such as a traffic stop. In September 2026, 10,357 rows had 10,357 distinct `eventnumber` values, so `count(*)` counts incidents. These are calls for service, not reported crimes: some incidents lead to a case in Police Cases (`szww-y224`).

## Key fields
- `incidenttype`: e.g. TRAFFIC, SUSPICIOUS EVENT, FOLLOW-UP, 911 HANG UP.
- `datetimereceived`: when the incident was reported or initiated, Pacific wall-clock, no timezone suffix. One row (eventnumber 2025-00119644) is dated 2026-12-20, in the future, so `data_coverage` max is wrong: judge freshness by recent months.
- `howreceived`, `incidentprogress`, `disposition`.
- Addresses and `geomcoordinate` are blurred to the hundred block.

## Area filters
- `neighborhood`: the 19 Everett neighborhoods, uppercase (e.g. PORT GARDNER, BAYSIDE). About 7.5% of rows are the placeholder `Not Assigned`; exclude it from rankings.
- `:@computed_region_cx6t_gkq3`: the same 19 neighborhoods as a computed region (PORT GARDNER is `10`); about 11% of rows are null. Counts differ slightly from `neighborhood` (September 2026, Port Gardner: 1,628 by the region, 1,640 by the text field).
- `:@computed_region_psyp_nrnc` is the city-limits layer: it says only whether a point is inside Everett. Never use it to split the city.
- `area` (North, Central, South), `precinct` (North, South), `beat`.
""",
        (
            Example(
                "What were the most common incident types in September 2026?",
                {
                    "portal": "data.everettwa.gov",
                    "dataset_id": "f6vp-3svh",
                    "select": ["incidenttype", "count(*) AS incidents"],
                    "where": f"datetimereceived between {SEPT_2026}",
                    "group_by": ["incidenttype"],
                    "order_by": ["incidents DESC"],
                    "page_size": 10,
                },
            ),
            Example(
                "How many incidents were there in each neighborhood in September 2026?",
                {
                    "portal": "data.everettwa.gov",
                    "dataset_id": "f6vp-3svh",
                    "select": ["neighborhood", "count(*) AS incidents"],
                    "where": f"datetimereceived between {SEPT_2026} AND neighborhood != 'Not Assigned'",
                    "group_by": ["neighborhood"],
                    "order_by": ["incidents DESC"],
                },
            ),
        ),
        rules=(
            "Always bound `datetimereceived` to the period you mean.",
            "Exclude `Not Assigned` from neighborhood rankings and say how many incidents it holds.",
            "Never use `:@computed_region_psyp_nrnc` as an area filter within Everett.",
            "For reported crimes, use Police Cases (`szww-y224`) and say which you used.",
        ),
        observed_at=OBSERVED,
    ),
)
