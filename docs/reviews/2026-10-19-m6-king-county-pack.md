# Review: the data.kingcounty.gov knowledge pack (milestone 6, curation run 1)

- **Reviewed:** `curate/king-county-run1` at a3f48d1, "feat: add the data.kingcounty.gov knowledge pack (profiled)". It branched from 4b769dc and has 1 commit, 6 files, +115/−10. The base already holds the engine fixes 715b183 and 7e9f8bf.
- **Reviewer:** a fresh Claude agent (Task 5). It did not run the curation, which was the headless `claude -p` child of Task 3.
- **Review worktree:** `<scratchpad>/m6/review-king-county-run1`, detached at a3f48d1. The branch itself is checked out in the run's kept test worktree, which this review did not touch.
- **Evidence:** `docs/evidence/review-king-county-2026-10-19/` holds the check output, the live outputs and the scripts, saved as `.py.txt`. In `probes-live.json` the presidential tickets' names are redacted; the party codes and vote counts are kept.
- **What the pack is:** a thin `profiled` pack. The profiler's 10 flagship datasets are 9 election-results-by-precinct tables, which have no time column, and Adult Jail Booking (`j56h-zgnm`), which has no place field. No dataset has both, so skill step 5 skipped to step 9. The pack holds `portal.toml`, 2 unreviewed `column_timezone` claims on `j56h-zgnm`, and a 4-task eval file. It has no reviewed dataset and no guide, and it does not propose `curated`. Following the controller's ruling, it is judged as a `profiled` pack that will not be promoted in this milestone.
- **Verdict:** 0 Material findings and 5 Minor findings. **The pack is approved for merge as `profiled`.**

## Checks

Each check was first run on the known positive in brackets, and that run reported the positive.

| Check | Known positive | Result |
| --- | --- | --- |
| Path rule: `git diff --name-only 4b769dc HEAD` through `path_violations` | `["README.md"]` returns `["README.md"]` | 6 paths, `[]` |
| Reliability evidence (rule 1) and `reviewed_by = "claude"` (rule 18), over `facts/*.toml` and `regions.toml` | a temp copy of Everett's `f6vp-3svh.toml` with the neighborhood claim's `reason` deleted is reported. The King County pack has no reason to delete | no problem. No claim sets `reliability` and none is reviewed, so both rules hold vacuously. `claim_summary` gives `column_timezone` 2, reviewed 0, reason-and-probe 0 |
| Personal data: the scan over the pack, `evals/portals/data.kingcounty.gov.json`, the PR body (`summary.json` `final_message`), the run's evidence directory and the agent's decisions row | `docs/evidence/scrub-known-positive/`: 1 match | no match. The read for names is below |
| Identity | a temp copy of the overrides with `datahub.hhs.gov` changed is reported (isolation row below) | `tier = "profiled"`. `name` (`King County`), `aliases` (`king-county`), `place_names` (`King County`, `King County, WA`), `jurisdiction` (county/US/WA) and `timezone = "America/Los_Angeles"` each equal override 59 at 4b769dc. The comment above `[jurisdiction]` cites https://kingcounty.gov/ and quotes "Home - King County, Washington". Fetched live, the page's title and `og:title` are exactly that string (`jurisdiction-page.txt`). Rule 21 did not strictly apply, because `jurisdiction` was already set. The `data.kingcounty.gov` table is gone from `registry_overrides.toml` |
| Eval file | `"PASS: x. FAIL: y."` is reported as missing a grade. A prompt naming `current_facility` and `j56h-zgnm` is reported | `covers` holds all 4 kinds, with none missing. The `misleading_field` prompt (02) names neither `current_facility`, `release_date_time`, `j56h-zgnm` nor "Adult Jail Booking" (rule 22); it says "booked into King County jail", which is the user's question, not the dataset's name. No dataset is reviewed, so rule 23 does not apply. All 4 `expect`s state PASS, PARTIAL and FAIL. Validity of the tasks: see "Eval-task validity" |
| Guides: `summary.json` `checks.guide_examples` | Everett's `summary.json` with one `is_error: true` item is reported | `exit_code` 0 and `examples: []`. The pack has no `guides.py`, as step 5's skip requires, so the non-empty rule does not apply. No guide prose exists to check against claims |
| Shared-file isolation (ruling 82): `registry_overrides.toml` | a copy with `datahub.hhs.gov` changed reports it | only the `data.kingcounty.gov` table changed, and it was removed (10 lines removed, none added). Every other table equals the base |
| Shared-file isolation (ruling 82): `validation.json`, parsed as JSON | a copy with one Seattle `outcome` changed reports `portals[data.seattle.gov]` | only `portals["data.kingcounty.gov"]` differs (new, 2 entries, both `passed`, `checked_at` 2026-10-20). Every other portal and top-level key equals the base |
| Step 3 offline gate: `uv run pytest -q tests/test_packs.py tests/test_tiers.py tests/test_release_gate.py tests/test_find_portals.py` in the review worktree | n/a | 77 passed, exit 0. `test_shipped_registry_finds_everett_and_king_county` and `test_seattle_and_king_county_do_not_cross_match` pass with the identity in the pack (Review Focus 1–2) |
| Step 4 [LIVE]: `atlas_find_portals` | n/a | "King County", "King County, WA" and `king-county` each return `data.kingcounty.gov` as the only candidate. "Seattle" returns `data.seattle.gov` only |
| Step 4 [LIVE]: `atlas_describe_dataset` for every dataset `pack_levels` returns, at `freshness.today()` = 2026-10-20 | n/a | 1 of 1 matches: `j56h-zgnm` is `profiled`, validation `passed`. `pack_levels` is the same at 2026-10-19 and 2026-10-20 (`step4-live.json`) |
| Step 4 [LIVE]: `atlas_get_reference {"topic": "portals", "item_id": "king-county"}` | n/a | `isError: false`, tier `profiled` |

## Live re-probes of the pack's figures

Each figure was probed in process with `atlas_query_dataset` or `atlas_search_datasets` on 2026-10-19 (Pacific) / 2026-10-20 (UTC). The outputs are in `probes-live.json`. Only aggregates were requested and printed.

| Statement | Live result |
| --- | --- |
| Timezone claim, `booking_date_time`: spring-forward day hour 2 has 2 rows, hours 1 and 3 have 3 and 0; peak hour 19 (2,124 of 39,852), 24 of 24 hours | 2, 3, 0; peak 19 with 2,124 of 39,852, 24 hours |
| Timezone claim, `release_date_time`: hour 2 has 13, hours 1 and 3 have 3 and 9; peak hour 20 (4,101 of 33,633), 24 of 24 hours | 13, 3, 9; peak 20 with 4,101 of 33,633, 24 hours |
| Eval 01: September 2026 has 1,388 distinct bookings over 2,888 rows | 1,388 / 2,888 |
| Dataset: 39,852 rows, 17,897 bookings, bookings 2025-10-01 to 2026-09-30, latest release 2026-10-01; title "… to Sep 2, 2026 as of Oct 2, 2026" | 39,852 / 17,897; min `2025-10-01T00:08:07`, max `2026-09-30T23:52:04`, release max `2026-10-01T06:37:03`; title as stated |
| Eval 02: no release date on 1,444 bookings over 6,219 rows; by facility 596, 446, 400, 1, 1 blank | 1,444 / 6,219; 596 King County Correctional Facility, 446 Maleng Regional Justice Center, 400 Electronic Home Detention, 1 Community Correction Division, 1 null |
| Eval 02: facility filled on 2,367 rows that have a release date; 8,584 rows with a facility | 2,367 rows (905 bookings); 8,584 |
| Eval 03: LD 43, presidential race, Republican ticket 8,747 votes over 207 precincts; Times Counted 83,076 | 8,747 (party `RPN`); 207 precincts; Times Counted 83,076, Registered Voters 95,811 |
| Eval answers: 188 rows have no `leg` | 188 |
| Eval 04: no collision dataset | "traffic collision", "collision" and "crash" each return 0 datasets. Known positive: "jail booking" returns 5, `j56h-zgnm` first |

## Eval-task validity

- **02 (`misleading_field`) is sound.** `current_facility` reads like a custody status, but 905 released bookings (2,367 rows) still list a facility, so counting it overstates custody. Every reference value probes as stated, and the rubric separates the right method (no release date, distinct bookings) from the trap (row counts, the facility column). The field is misleading because it is filled where it should be empty, not because it is placeholder-heavy or sparse. That is looser than CONTRIBUTING step 9's wording (finding m1), but it is the trap the kind exists to test.
- **03 (`in_area`) is valid as a task for this pack, but it does not meet the `in_area` definition.** CONTRIBUTING step 9 defines `in_area` as "an 'in <area>' count on a reviewed place field". `leg` is not reviewed, and live describe of `u6ig-5qm8` lists no `place_fields` at all (level `none`). What the task does test is the server's exploratory rule: with no reviewed place field, filter a column on values the agent's own query returned, and say the result is unverified. The reference is probed and exact, the FAIL cases (non-candidate rows, whole county, another election) discriminate, and all 3 runs said the district field was unverified. Its PASS line does not require that statement, though (m1).
- **01 (`relative_date`) has the same gap.** The definition requires "a reviewed time column", and `booking_date_time`'s timezone is unreviewed. The task still tests the `now_local` rule for an unknown column timezone: state the zone and the absolute range used. Every run did, but PASS does not require it (m1). Its premise of "Pacific wall-clock time" is not supported by the pack's own evidence (m2).
- **04 (`not_published`) is sound.** Probed live as above. The answers point to WSDOT's crash portal, and one gives its URL from the `data.wa.gov` "State Crash Data" listing. That is another publisher, not an invented dataset id, so the rubric allows it.
- **Judgment:** no task is unsafe or wrong for a `profiled` pack. `covers` labels matter only to the tier test's `curated` condition, and King County is not promoted in this milestone. A future curation that reviews a dataset should replace or relabel 01 and 03 against a reviewed column, through the front door.

## Personal-data read

- **Pack:** I read every value in `portal.toml` and `facts/j56h-zgnm.toml`. They hold hour counts, dates and SoQL over the two time columns. There is no sample value, name or booking number.
- **Eval file:** I read the 4 prompts and 4 `expect`s. They name columns (`book_of_arrest_number`, `current_facility`, `leg`, `countertype`, `sumofcount`) and give counts. They hold no person's name and no booking number. Task 03 names the "Republican presidential ticket" without naming the candidates.
- **PR body:** no name, booking number, email or phone.
- **The profiler skipped the name columns:** confirmed. The run's report (`.curation/report.json` in the kept worktree, read only) has `review_values: []` and notes for `j56h-zgnm` that say `last_name`, `first_name`, `middle_name`, `book_of_arrest_number`, `charge`, `court_case_cause_number`, `court` and `rcw_ordinance_number` were "more than 100 groups, not categorical; skipped". No claim is scoped to those columns.
- **Committed eval answers:** I read all 16 answers: `summary.json`'s 4 and the 12 preserved runs. None carries a jail-booked person's name or a booking number. Task 03's answers name the 2012 presidential tickets, which are public candidates in certified results.
- **Local transcripts (not committed):** see N2.

## Findings

**Material:** none.

**Minor**

- **m1. `covers` labels on 01 and 03 do not meet the CONTRIBUTING step 9 definitions, and their PASS lines do not require the unverified caveat.**
  - `relative_date` requires a reviewed time column, and `in_area` a reviewed place field. The pack has neither, and `leg` is not even a detected place field. 02's field is misleading because it is wrongly filled, not because it is sparse.
  - The PASS lines for 01 and 03 do not require the statements the server's rules demand (the zone used, and "unverified" for a filter on an unreviewed column). All 9 preserved answers made them anyway.
  - **Effect:** none at `profiled`. A later promotion would get a passing `covers` check from tasks that do not exercise reviewed knowledge.
  - **Routing:** a future King County curation, once a dataset is reviewed.
- **m2. Eval 01's "Pacific wall-clock time" premise is unsupported.** The pack's own `dst_gap` probe shows rows in the hour that does not exist on the spring-forward day: 2 bookings, and 13 releases. The profiler therefore emitted only the `diurnal_peak` assertion (`profiler/profile.py`, `observe_time`). The claims name no timezone, as they should. The reference count uses floating bounds, and a one-hour shift would fall inside the rubric's PARTIAL tolerance, so no grade depends on the premise.
- **m3. Knowledge gaps the PR body names, left for a future curation:**
  - `j56h-zgnm` has no `unit_of_observation`. It has one row per charge: 39,852 rows over 17,897 bookings.
  - `current_facility` is filled on released bookings.
  - Both timezone claims are unreviewed.
  - The title says "to Sep 2, 2026", but bookings run to Sep 30.

  Every eval answer inferred the first two from the data and flagged them as unverified.
- **m4. The agent's decisions row names a branch that does not exist.** Its source says `curate/test-2026-10-19 (king county curation)`, the test harness's branch name, as Everett's row 164 did. The commit is on `curate/king-county-run1`. The row is the agent's, so I leave it unchanged. The merge's decisions row names the right branch.
- **m5. Dates are UTC (rule 20), with no behavioral change.** `observed_at` and `checked_at` are 2026-10-20 while the local date was 2026-10-19. `pack_levels` is the same on both dates.

**Noted, not pack findings**

- **N1. Unknown tool name answers `internal_error`.** This is the agent's decisions row, an engine defect that leaves the pack unaffected. By controller ruling it is not an engine-gap instance, and it goes to the standards review (Task 6).
- **N2. The local eval transcripts carry person names.** In every task-02 transcript (the 3 preserved runs and the test's own run), the eval agent called `atlas_describe_dataset` on `j56h-zgnm` with `sample_rows: 2`. The result returns raw rows: names and booking numbers, published upstream by King County. Every run also aggregated over the name columns to estimate people per booking, and printed only counts.
  - The transcripts are git-ignored (`.gitignore:66`, `evals/results/*/`) and in the scratchpad, and none is committed.
  - **For Task 7:** re-grading reads these transcripts. Never copy a tool result from them into committed evidence.
  - **For Task 6:** the profiler keeps name columns out of claims only by cardinality (more than 100 groups), not by a name screen, and describe's sample rows surface them on request.

## Agent's own eval grades (PR body; self-graded, Task 7 re-grades)

| Task | covers | Run 1 | Run 2 | Run 3 |
| --- | --- | --- | --- | --- |
| 01-jail-bookings-last-month | relative_date | PASS | PASS | PASS |
| 02-still-in-custody | misleading_field | PASS | PASS | PASS |
| 03-ld43-2012-republican-president | in_area | PASS | PASS | PASS |
| 04-traffic-collisions | not_published | PASS | PASS | PASS |

On my reading, the 12 answers match their grades:
- 01 gives 1,388 every time, explains the row-per-charge structure and states the Pacific assumption.
- 02 gives 1,444 with the facility split, the Oct 2 snapshot caveat and the October 2025 start. The count of released bookings that still list a facility varies (about 900, 1,503 and 905; 905 probes live). The rubric does not grade it.
- 03 gives 8,747 over 207 precincts, with the 83,076 check.
- 04 finds no collision dataset, invents no id and points to WSDOT.

The test's own run (`summary.json`) is also 4 of 4 by the same reading.

## Preserved eval transcripts (for Task 7)

- The agent's 3 runs are local and git-ignored, in `evals/results/2026-10-19-m6-king-county-run1/evals-{1,2,3}/{01-jail-bookings-last-month,02-still-in-custody,03-ld43-2012-republican-president,04-traffic-collisions}.transcript.jsonl`. That is 12 transcripts, all `subtype: "success"`.
- The test's own eval run is in `<scratchpad>/m6/king-county-run1/test_curation_skill_produces_a0/evals/*.transcript.jsonl`.
- The curation transcript is `<scratchpad>/m6/king-county-run1/test_curation_skill_produces_a0/curation.transcript.jsonl`.
- The task-02 transcripts carry person names (N2).
