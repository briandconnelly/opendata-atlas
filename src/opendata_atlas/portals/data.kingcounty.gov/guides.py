"""King County's dataset guides (docs/design.md: Primitives). Facts were probed live on 2026-10-20."""

from __future__ import annotations

from opendata_atlas.core.guides import Example, Guide

SEPT_2026 = "incident_datetime >= '2026-09-01T00:00:00' AND incident_datetime < '2026-10-01T00:00:00'"


GUIDES: tuple[Guide, ...] = (
    Guide(
        "kcso-offense-reports",
        "4kmt-kfqf",
        "KCSO Offense Reports",
        "King County Sheriff's Office NIBRS offense reports since 2020; one row per offense.",
        """
## What a row is
One offense in a King County Sheriff's Office (KCSO) report. A report (`case_number`) can list several offenses: in 2025, 20,530 rows had 18,713 distinct `case_number` values. `count(*)` counts offenses; `count(distinct case_number)` counts reports. Say which you give.

## Who is covered
KCSO's own page says it serves "unincorporated areas and thirteen contract cities", and provides police for the Muckleshoot Tribe, Metro and Sound Transit and the King County International Airport. Offenses policed by a city's own department are not here: for Seattle, use the Seattle portal (`data.seattle.gov`).

## Key fields
- `incident_datetime`: when the offense started, Pacific wall-clock, no timezone suffix. About 7% of rows sit at exactly 00:00:00, a default for an unknown time; do not read hour 0 as a midnight peak. `hour_of_day` repeats its hour.
- 1,112 rows are dated before 2020 (one in the year 1019), so `data_coverage` min is wrong: the data starts in 2020.
- `created_at`: when the report was created; about 6% of a month's offenses are reported after the month ends, and the publisher withdraws reports while they are re-approved, so recent counts move.
- `nibrs_code`, `nibrs_code_name`: the NIBRS offense (e.g. Simple Assault, All Other Offenses).

## Area filters
- `city` is the address's city or community, not the jurisdiction. Use it for a city KCSO patrols (`city = 'BURIEN'`: 99% of its rows are in patrol districts N1-N6). It also holds unincorporated communities (WHITE CENTER, BRYN MAWR-SKYWAY, FAIRWOOD) and postal cities: `SEATTLE` rows are Metro Transit police incidents and unincorporated areas with Seattle addresses, never Seattle Police data. For Seattle crime, use the Seattle portal (`data.seattle.gov`).
- `precinct` (2, 3, 4, 5; blank on about 10%, mostly transit), `district` (patrol districts such as `District N5`, Metro Transit `MT10`-`MT30`, and `Out of Jurisdiction`) and `reporting_area` are unreviewed.
""",
        (
            Example(
                "How many offenses and reports were there in Burien in September 2026?",
                {
                    "portal": "data.kingcounty.gov",
                    "dataset_id": "4kmt-kfqf",
                    "select": ["count(*) AS offenses", "count(distinct case_number) AS reports"],
                    "where": f"{SEPT_2026} AND city = 'BURIEN'",
                },
            ),
            Example(
                "What were the most common offenses in September 2026?",
                {
                    "portal": "data.kingcounty.gov",
                    "dataset_id": "4kmt-kfqf",
                    "select": ["nibrs_code_name", "count(*) AS offenses"],
                    "where": SEPT_2026,
                    "group_by": ["nibrs_code_name"],
                    "order_by": ["offenses DESC"],
                    "page_size": 10,
                },
            ),
        ),
        rules=(
            "Always bound `incident_datetime` to the period you mean.",
            "Say whether a count is offenses (rows) or reports (distinct `case_number`).",
            "Never present `city = 'SEATTLE'` as Seattle's crime.",
            "Say recent months may still grow as late reports are approved.",
        ),
    ),
)
