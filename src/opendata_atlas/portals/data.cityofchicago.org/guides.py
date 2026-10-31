"""Chicago's dataset guides (docs/design.md: Knowledge packs). Facts were probed live on 2026-10-19;
each example was run once with `atlas_query_dataset` on that date."""

from __future__ import annotations

from datetime import date

from opendata_atlas.core.guides import Example, Guide

#: When this pack's guide figures were probed (its docstring).
OBSERVED = date(2026, 10, 19)

SEPT_2026 = "'2026-09-01T00:00:00' and '2026-09-30T23:59:59'"


GUIDES: tuple[Guide, ...] = (
    Guide(
        "crimes",
        "ijzp-q8t2",
        "Crimes - 2001 to Present",
        "Chicago Police reported crime incidents since 2001, minus the most recent seven days.",
        """
## What a row is
One reported crime incident, except homicides, which have one row per victim: since 2025, 783 homicide rows cover 737 case numbers. In September 2026, 19,747 rows had 19,745 distinct `case_number` values. The publisher withholds the most recent seven days: on 2026-10-19 the newest `date` was 2026-10-11.

## Key fields
- `primary_type` (UPPERCASE, e.g. THEFT, BATTERY, CRIMINAL DAMAGE, ASSAULT, MOTOR VEHICLE THEFT), `description`, `iucr`, `fbi_code`.
- `date`: when the incident occurred, Chicago wall-clock, no timezone suffix; the publisher calls it "sometimes a best estimate". Over half the rows in the midnight hour are stamped exactly 00:00, a default for an unknown time, so do not read hour 0 as a crime peak.
- `arrest`, `domestic`: checkboxes (true/false). In 2025, 38,431 of 238,158 rows (16%) had `arrest = true`.
- `year`: the year of `date`, as a number.
- `updated_on`: when the record last changed, not when the crime occurred.

## Area filters
- Reported columns: `ward` (number), `community_area` (text, '1'-'77'; '0' is not an area), `district` (text, '001'), `beat` (text, '1834'). `ward` and `community_area` are under 2% filled for 2001 and 73% for 2002; complete since 2003.
- Computed regions (from the incident location, about 98.6% filled in every year):
  - `:@computed_region_8hcu_yrd4`: current (2023-) wards. Feature ids are not ward numbers (feature 3 is ward 5).
  - `:@computed_region_vrxf_vc4k`: the 77 community areas. Feature ids are not area numbers: HYDE PARK is `8`, DOUGLAS is `1`.
  - `:@computed_region_d9mm_jgwp`: police districts.
  - `:@computed_region_43wa_7qmu` (2015-2023 wards) and `:@computed_region_awaf_s7ux` (2003-2015 wards) are superseded boundaries.
- `atlas_describe_dataset` with `detail: "full"` lists each region's values with labels (`layer_features` when its stats time out).
""",
        (
            Example(
                "How many crimes of each type were reported in September 2026?",
                {
                    "portal": "chicago",
                    "dataset_id": "ijzp-q8t2",
                    "select": ["primary_type", "count(*) AS crimes"],
                    "where": f"date between {SEPT_2026}",
                    "group_by": ["primary_type"],
                    "order_by": ["crimes DESC"],
                    "page_size": 10,
                },
            ),
            Example(
                "How many crimes occurred in Hyde Park (community area feature 8) in September 2026?",
                {
                    "portal": "chicago",
                    "dataset_id": "ijzp-q8t2",
                    "select": ["count(*) AS crimes"],
                    "where": f"date between {SEPT_2026} AND :@computed_region_vrxf_vc4k = '8'",
                },
            ),
            Example(
                "How many crimes were reported in each community area in 2001 and 2002?",
                {
                    "portal": "chicago",
                    "dataset_id": "ijzp-q8t2",
                    "select": ["year", ":@computed_region_vrxf_vc4k AS area", "count(*) AS crimes"],
                    "where": "year in (2001, 2002)",
                    "group_by": ["year", ":@computed_region_vrxf_vc4k"],
                    "order_by": ["crimes DESC"],
                    "page_size": 10,
                },
            ),
        ),
        rules=(
            "Always bound `date` to the period you mean, and say the last seven days are not published yet.",
            "For counts by ward or community area that include 2001 or 2002, use the computed regions `:@computed_region_8hcu_yrd4` or `:@computed_region_vrxf_vc4k`, never the reported `ward` or `community_area`.",
            "Never use `:@computed_region_awaf_s7ux` for counts; for current wards use `:@computed_region_8hcu_yrd4`.",
            "Count homicide victims with `count(*)` and homicide cases with `count(distinct case_number)`.",
        ),
        observed_at=OBSERVED,
    ),
)
