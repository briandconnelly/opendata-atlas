"""NYC's dataset guides (docs/design.md: Knowledge packs). Facts were probed live on 2026-10-31; every example runs in
`tests/test_live.py::test_guide_examples_run`."""

from __future__ import annotations

from datetime import date

from opendata_atlas.core.guides import Example, Guide

#: When this pack's guide figures were probed (its docstring).
OBSERVED = date(2026, 10, 31)

SEPT_2026 = "'2026-09-01T00:00:00' and '2026-09-30T23:59:59'"


GUIDES: tuple[Guide, ...] = (
    Guide(
        "nyc-311",
        "erm2-nwe9",
        "311 Service Requests from 2020 to Present",
        "NYC 311 service requests directed to a city agency since 2020, updated daily; one row per request.",
        """
## What a row is
One 311 service request directed to a city agency. In September 2026, 323,632 rows had 323,632 distinct `unique_key` values, so `count(*)` counts requests. About 23 million rows; `created_date` runs from 2020-01-01. Requests from 2010-2019 are in a separate dataset, `76ig-c548`.

## Key fields
- `created_date`: when the request was created, New York wall-clock time with no offset. The newest rows are about a day old.
- `complaint_type`, `descriptor`, `agency`, `status`. In September 2026 the largest complaint types were Illegal Parking (53,276) and Noise - Residential (31,602).
- `closed_date` and `due_date` are unreviewed; `closed_date` has values after today.

## Area filters
- `borough`: upper-case names (`BROOKLYN`, `QUEENS`, `BRONX`, `MANHATTAN`, `STATEN ISLAND`); 0.2% of rows say `Unspecified`.
- `council_district`: two-digit text, `'01'` to `'51'`. `council_district = '1'` matches nothing; use `'01'`.
- Computed-region columns hold the layer's feature id, not the district number; `atlas_describe_dataset` with `detail: "full"` lists each feature's label:
  - `:@computed_region_yeji_bk3q`: boroughs (Brooklyn is `2`).
  - `:@computed_region_sbqj_enih`: police precincts (precinct 5 is `2`).
  - `:@computed_region_f5dn_yrer`: community districts, labelled by 3-digit code (Manhattan CD 12, code 112, is `47`).
  - `:@computed_region_92fq_4b7q`: 2015 council districts, which disagree with `council_district` on 14.7% of 2026 rows.
- `police_precinct`, `community_board` and `incident_zip` are unreviewed text columns.
""",
        (
            Example(
                "Which complaint types were most common in September 2026?",
                {
                    "portal": "data.cityofnewyork.us",
                    "dataset_id": "erm2-nwe9",
                    "select": ["complaint_type", "count(*) AS requests"],
                    "where": f"created_date between {SEPT_2026}",
                    "group_by": ["complaint_type"],
                    "order_by": ["requests DESC"],
                    "page_size": 10,
                },
            ),
            Example(
                "How many requests by borough in September 2026?",
                {
                    "portal": "data.cityofnewyork.us",
                    "dataset_id": "erm2-nwe9",
                    "select": ["borough", "count(*) AS requests"],
                    "where": f"created_date between {SEPT_2026}",
                    "group_by": ["borough"],
                    "order_by": ["requests DESC"],
                },
            ),
            Example(
                "How many requests in City Council District 1 in September 2026?",
                {
                    "portal": "data.cityofnewyork.us",
                    "dataset_id": "erm2-nwe9",
                    "select": ["count(*) AS requests"],
                    "where": f"created_date between {SEPT_2026} AND council_district = '01'",
                },
            ),
        ),
        rules=(
            "For council districts, filter `council_district` with a two-digit value ('01'), never the 2015 layer `:@computed_region_92fq_4b7q`.",
            "Never filter a computed-region column by a district or precinct number; look up the feature id from describe's labels.",
        ),
        observed_at=OBSERVED,
    ),
)
