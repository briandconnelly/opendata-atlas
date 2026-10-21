"""Los Angeles's dataset guides (docs/design.md: Knowledge packs). Facts were probed live on
2026-10-20; each example was run once with `atlas_query_dataset` on that date."""

from __future__ import annotations

from opendata_atlas.core.guides import Example, Guide

SEPT_2026 = "'2026-09-01T00:00:00' and '2026-09-30T23:59:59'"


GUIDES: tuple[Guide, ...] = (
    Guide(
        "nibrs-offenses",
        "k7nn-b2ep",
        "LAPD NIBRS Offenses Dataset",
        "LAPD crime offenses in NIBRS format since the March 2024 records system; one row per offense, not per incident.",
        """
## What a row is
One NIBRS offense, not one incident: an incident with several offenses has several rows. `uniquenibrno` is unique on every row; `caseno` is the case. In September 2026 (by `date_rptd`), 18,313 rows covered 16,600 distinct `caseno` values, so count distinct `caseno` for incidents. LAPD's records system began on 2024-03-07; the publisher notes NIBRS "may result in higher counts" than the older UCR-based crime datasets, so do not compare these counts with "Crime Data from 2020 to 2024".

## Key fields
- `nibr_description`: the offense, as statute, felony/misdemeanor flag, name and NIBRS code (e.g. "487(D)(1) - PC - F - Grand Theft Auto - GTA  - 240", the most common in September 2026). `nibr_code`, `crime_against` (Property, Person, Society, or the combined "Person, Property, Society").
- `date_rptd`: when the offense was reported, Los Angeles wall-clock, no timezone suffix. 7,940 of 498,741 rows (1.6%) have no `date_rptd` and drop out of any date filter on it. 1,415 rows are dated before 2024-03-07, back to 1980.
- `date_occ`: when it occurred, Los Angeles wall-clock as entered; its time part repeats the text `time_occ`. About 2.5% of rows are stamped exactly 00:00, which may mean an unknown time. A few rows carry implausible dates back to 1800, so its minimum is not the start of the data. Recent occurrences lag reports: on 2026-10-20 the newest `date_occ` was 2026-10-03 and the newest `date_rptd` 2026-10-12.
- `status_desc`: case status (most rows "Investigation Continued").

## Area filters
- `area_name`: the 21 LAPD geographic Areas (codes 01-21 in `area`), filled on every row. They are police Areas, not neighborhoods: "Hollywood" and "N Hollywood" are different Areas.
- Every `area_name` value is right-padded with spaces to 20 characters, so `area_name = 'Hollywood'` matches nothing. Filter with `trim(area_name) = 'Hollywood'`, or with a value a `group_by` on `area_name` returns.
- `rpt_dist_no` (reporting district) and the hundred-block `hndrdth_lat`, `hndrdth_lon` and `hndrdth_loc_chk` are unreviewed. There are no computed-region columns.
""",
        (
            Example(
                "Which offenses were reported most in September 2026?",
                {
                    "portal": "los-angeles",
                    "dataset_id": "k7nn-b2ep",
                    "select": ["nibr_description", "count(*) AS offenses"],
                    "where": f"date_rptd between {SEPT_2026}",
                    "group_by": ["nibr_description"],
                    "order_by": ["offenses DESC"],
                    "page_size": 10,
                },
            ),
            Example(
                "How many offenses and incidents were reported in the Hollywood Area in September 2026?",
                {
                    "portal": "los-angeles",
                    "dataset_id": "k7nn-b2ep",
                    "select": ["count(*) AS offenses", "count(distinct caseno) AS incidents"],
                    "where": f"date_rptd between {SEPT_2026} AND trim(area_name) = 'Hollywood'",
                },
            ),
            Example(
                "How many incidents were reported in each LAPD Area in September 2026?",
                {
                    "portal": "los-angeles",
                    "dataset_id": "k7nn-b2ep",
                    "select": ["area_name", "count(distinct caseno) AS incidents"],
                    "where": f"date_rptd between {SEPT_2026}",
                    "group_by": ["area_name"],
                    "order_by": ["incidents DESC"],
                    "page_size": 25,
                },
            ),
        ),
        rules=(
            "Say whether a count is offenses (rows) or incidents (distinct caseno).",
            "Compare area_name with trim() or a padded value a group_by returns, never an unpadded literal.",
        ),
    ),
)
