# Review: the data.everettwa.gov knowledge pack (milestone 6, curation run 2)

- **Reviewed:** `curate/everett-run2` at 2ddddb0, "feat: add the data.everettwa.gov knowledge pack (profiled)". It branched from 3cea5d6 and has 1 commit, 11 files, +562/−13.
- **Reviewer:** a fresh Claude agent (Task 5). It did not run the curation, which was the headless `claude -p` child of Task 3. Run 1 (`curate/everett-run1`) stopped on an engine gap that 715b183 fixed, and is not under review.
- **Review worktree:** `<scratchpad>/m6/review-everett-run2`, on `curate/everett-run2`.
- **Evidence:** `docs/evidence/review-everett-2026-10-19/` holds the check output, the live outputs and the scripts, saved as `.py.txt`.
- **Re-review (below):** on the fixed engine (7e9f8bf), M1 is resolved and no Material finding is open. **The pack is approved for merge.**
- **First verdict:** 1 Material finding (M1) and 5 Minor findings. **The pack is not merged.** M1 is an engine gap: the shipped `place_field` example models a `placeholders` declaration that the engine ignores, and the agent followed that example. It goes to Task 4, on the pre-merge path.

## Checks

Each check was first run on the known positive in brackets, and that run reported the positive.

| Check | Known positive | Result |
| --- | --- | --- |
| Path rule: `git diff --name-only 3cea5d6 HEAD` through `path_violations` | `["README.md"]` returns `["README.md"]` | 11 paths, `[]` |
| Reliability evidence (rule 1) and `reviewed_by = "claude"` (rule 18), over `facts/*.toml` and `regions.toml` | a temp copy of `f6vp-3svh.toml` with the neighborhood claim's `reason` deleted is reported | 5 claims set `reliability`, with no problem. All 7 reviewed claims have `reviewed_by = "claude"`. `claim_summary` gives reviewed 7 and reason-and-probe 7 |
| Personal data: the scan over the pack, `evals/portals/data.everettwa.gov.json`, the PR body (`summary.json` `final_message`), and the run's evidence files | `docs/evidence/scrub-known-positive/`: 1 match | no match. I read every sample value, the guide, the 3 `expect`s, the PR body and the 10 eval answers, and found no names. The values are counts, layer names, neighborhood names, incident and case types, and one incident number (2025-00119644) |
| Identity | a temp copy of the overrides with `datahub.hhs.gov` changed is reported (isolation row below) | `tier = "profiled"`. `name`, `aliases` (`everett`), `place_names` (`Everett`, `Everett, WA`), `jurisdiction` (city/US/WA) and `timezone = "America/Los_Angeles"` each equal override 58 at 3cea5d6. The override's comment is carried into `portal.toml` as 3 comment lines above `[jurisdiction]`. Rule 21 did not apply, because `jurisdiction` was already set. The `data.everettwa.gov` table is gone from `registry_overrides.toml` |
| Eval file | n/a | `covers` holds all 4 kinds, with none missing. The `misleading_field` prompt (02, "How many crimes in Everett in 2025 involved gangs?") names neither `gangrelated`, `szww-y224` nor "Police Cases" (rule 22). The tasks span `f6vp-3svh` and `szww-y224` (rule 23). All 3 `expect`s state PASS, PARTIAL and FAIL |
| Guides: `summary.json` `checks.guide_examples` | a copy with one `is_error: true` item is reported | `exit_code` 0, 2 examples, both `is_error: false`. Rerun live, both return `isError: false` (10 and 19 rows). The prose agrees with the claims it cites, apart from finding m2 and the effect of M1 |
| Shared-file isolation (ruling 82): `registry_overrides.toml` | a copy with `datahub.hhs.gov` changed reports it | only the `data.everettwa.gov` table changed, and it was removed (CONTRIBUTING step 4). Every other table equals the base |
| Shared-file isolation (ruling 82): `validation.json`, parsed as JSON | a copy with one Seattle `outcome` changed reports `portals[data.seattle.gov]` | only `portals["data.everettwa.gov"]` differs (new, 16 entries, all `passed`). Every other portal and top-level key equals the base |
| Step 3 offline gate: `uv run pytest -q tests/test_packs.py tests/test_tiers.py tests/test_release_gate.py tests/test_find_portals.py` in the review worktree | n/a | 76 passed, exit 0. Review Focus 1 and 2 hold with the identity in the pack (live row below) |
| Step 4 [LIVE]: `atlas_find_portals` | n/a | "Everett", "Everett, WA" and `everett` each return `data.everettwa.gov` first. "Seattle" returns `data.seattle.gov` |
| Step 4 [LIVE]: `atlas_describe_dataset` for every dataset `pack_levels` returns, at `freshness.today()` = 2026-10-20 | n/a | 4 of 4 match. `f6vp-3svh` is `reviewed`, and `qvfa-2v26`, `szww-y224` and `w35j-83t3` are `profiled` (`step4-live.json`) |
| Step 4 [LIVE]: `atlas_get_reference {"topic": "portals", "item_id": "everett"}` | n/a | `isError: false`, tier `profiled` |

## Live re-probes of the pack's figures

Each figure below was probed in process with `atlas_query_dataset`, or directly against `data.everettwa.gov`, on 2026-10-19 (Pacific) / 2026-10-20 (UTC). The outputs are in `probes-live.json` and `probe-cx6t-null-by-year.txt`.

| Pack statement | Live result |
| --- | --- |
| September 2026: 10,357 rows, 10,357 distinct `eventnumber` (unit claim, guide) | 10,357 / 10,357 |
| Port Gardner, September 2026: 1,640 by `neighborhood`, 1,628 by `:@computed_region_cx6t_gkq3 = '10'` (guide, eval 01) | 1,640 and 1,628. Layer `cx6t-gkq3` has 19 features with 19 names, and PORT GARDNER is `_feature_id` 10 |
| `Not Assigned` is about 7.5% of rows (claim, guide) | 120,857 of 1,618,409 (all years), and 617 of 10,357 in September 2026 |
| Computed-region nulls are "7-14% a year since 2015" | 13.9% (2015) down to 7.6% (2023) |
| `psyp-nrnc` has 5 features, all code EV | 5 features, all `EV` |
| One row (eventnumber 2025-00119644) is dated 2026-12-20 (guide, row 164) | the only row after 2026-10-21 is that one, at `2026-12-20T10:16:00` |
| Publisher's description (unit claim's `document` quote) and "blurred to the hundred block" (guide) | the quote is verbatim in `/api/views/f6vp-3svh.json`, and the same description says addresses are "partially obfuscated to the nearest 100 block" |
| Gang flag, 2025: 59 YES – BELIEVED, 6,935 blank of 11,899, no plain YES (claim, eval 02) | 59, 6,935 blank, 4,902 NO – NOT BELIEVED, 3 UNKNOWN IF; total 11,899; no plain `YES` |
| No inspection dataset (eval 03) | the catalog search on `data.everettwa.gov` for "restaurant inspection", "food health inspections" and "inspection" returns 0 results |

## Findings

**Material**

- **M1. The `Not Assigned` declaration on `neighborhood` has no effect (engine gap, Task 4, pre-merge).**
  - The neighborhood claim `f6vp-3svh-neighborhood-place-field` is a `place_field` claim that carries `placeholders = ["Not Assigned"]`. The engine reads placeholder declarations only from `placeholder_share` claims (`placeholder_declarations`, `portals/model.py:317`), so the key is silently ignored.
  - Live, as shipped, describe reports the reviewed `neighborhood` field with `assigned_fraction: 1.0` and `value_count: 20`. It lists only `null` (16 rows) as a placeholder, which counts the placeholder as a 20th neighborhood.
  - In a counterfactual where the declaration is honored (an in-memory patch, with no file changed: `placeholder-counterfactual.txt`), describe reports `assigned_fraction: 0.9253`, `value_count: 19` and `Not Assigned` with 120,857 rows.
  - The shipped field therefore reads more complete than reviewed, which design's freshness rules exist to prevent ("so it never reads more complete than reviewed"). It does so on the reviewed dataset's primary text place field, which is the pack's main knowledge. `Not Assigned` is not in the shared vocabulary, so it is not even listed as a candidate.
  - The `reliability_reason` text still warns ("plus the placeholder 'Not Assigned' on about 7.5% of rows; exclude it from rankings"), and all 10 eval answers to task 01 report the 617 unassigned incidents. That limits the harm to agents that read the reason. It does not correct the structured number.
  - **Why it is an engine gap, not agent variance:** `docs/pack-examples/place_field.toml`, which SKILL step 6 tells the agent to model each claim on, puts `placeholders = ["-"]` on a `place_field` claim. The loader accepts the key there, and `tests/test_packs.py` loads the example, so no check could fail. The agent did what the shipped example showed. No other shipped pack uses the form, so Seattle and Chicago are unaffected.
  - **Routing:** Task 4, pre-merge. One fix leaves this pack right unchanged, so it can merge after the fix with no new curation run: honor a reviewed `placeholders` declaration on a `place_field` claim (the counterfactual's behavior), pinned by a test on the example.
  - The other fix would also send the pack back to Task 3 (run 3 of 3): reject the key outside `placeholder_share` and correct the example. The pack would then fail to load.

**Minor**

- **m1. Future-dated rows set the profiler's window and `data_coverage` max (decisions row 164; engine, not fixed here).**
  - Row 164 is accurate. `start = max(hi - timedelta(days=365), lo)` is at `profiler/profile.py:595`, and describe reports `f6vp-3svh` `data_coverage` max `2026-12-20T10:16:00` with `status: "ok"`.
  - **Judgment: a legitimate workaround, not a gap the pack cannot work around.**
    - The timezone claim is right. Its `dst_gap` probe is independent of the window, and its diurnal probe still covers about 10 months (98,730 rows, peak at hour 14). Both assertions pass in drift, and the observation says why the window ends in the future.
    - The guide warns that the max is wrong and says to judge freshness by recent months.
    - The defect changes no knowledge level and no reviewed verdict.
    - The eval agents handled it: at least answer 01 in run 2 and in the test's own run flagged the future max unprompted.
  - The defect is not Everett-specific. Describe also reports `qvfa-2v26` `issuedate` from `1900-01-01` to `2087-03-16` with `status: "ok"`. That dataset is unreviewed, so the pack has no guide for it.
  - Suggestion (engine, after this milestone or in a Task 4 instance if one is opened for M1): cap `hi` at the server's today in the profiler, and flag a `data_coverage` max after today.
- **m2. `area` and `precinct` carry an undeclared `Not Assigned`.** The guide lists `area` (North, Central, South) and `precinct` (North, South) as area filters. Each also holds `Not Assigned` on 52,971 rows (3.3%), and the guide does not say so. No claim covers these columns.
- **m3. Police Cases is half-reviewed.** On `szww-y224`, only `gangrelated` is reviewed. Its unit of observation and its `datetimereceived` timezone are observations. The PR body names this as a knowledge gap, and the task 02 answers flag both as unconfirmed. It did not change a grade.
- **m4. Row 164's source names a branch that does not exist.** Row 164 (and `summary.json` `branch`) say `curate/test-2026-10-19`, the test harness's branch name. The run's commit lives on `curate/everett-run2`, and `curate/test-2026-10-19` is not a branch in the repository. The row is the agent's, so I leave it unchanged. The merge's decisions row should name `curate/everett-run2`.
- **m5. Dates are UTC (rule 20). This changes no behavior.**
  - Every `reviewed_at`, `observed_at` and `checked_at` in the pack is 2026-10-20, the UTC date (rule 20 and the drift run both write UTC). The local date was 2026-10-19, and the milestone's other decisions rows say 2026-10-19.
  - `freshness.today()` is UTC (2026-10-20 at review). `pack_levels` gives the same 4 levels at `date(2026, 10, 19)` and at `date(2026, 10, 20)` (`step4-live.json`). `claim_validation` treats a `checked_at` after today as fresh, so a server whose clock reads 2026-10-19 sees no change either.
  - Eval 01's `expect` keys "last month" to `now_local`, and every run answered September 2026, so the UTC stamp does not move the reference month. Recorded only for the record.

## Agent's own eval grades (PR body; self-graded, Task 7 re-grades)

| Task | covers | Run 1 | Run 2 | Run 3 |
| --- | --- | --- | --- | --- |
| 01-port-gardner-last-month | in_area, relative_date | PASS | PASS | PASS |
| 02-gang-crimes-2025 | misleading_field | PASS | PASS | PASS |
| 03-restaurant-inspections | not_published | PASS | PASS | PASS |

The agent proposes `curated`. On my reading, the 9 answers match their grades:
- 01 gives 1,640 with a floor caveat each time, and every run also gives 1,628.
- 02 gives 59, with the 6,935 blank cases (58%) and a floor caveat.
- 03 finds no inspection dataset, invents no id and points to the county health department.

For Task 7:
- 03's answers name the Snohomish County Health Department and say Washington inspections are county-run. That comes from outside knowledge, not from a portal.
- Run 1 of 03 describes the dining guide's columns, phone among them, and gives no values.

## Preserved eval transcripts (for Task 7)

- The agent's 3 runs are local and git-ignored, in `evals/results/2026-10-19-m6-everett-run2/evals-{1,2,3}/{01-port-gardner-last-month,02-gang-crimes-2025,03-restaurant-inspections}.transcript.jsonl`: 9 transcripts, all `subtype: "success"`, $1.04 in total.
- The test's own eval run is in `<scratchpad>/m6/everett-run2/test_curation_skill_produces_a0/evals/*.transcript.jsonl`.
- The curation transcript is `<scratchpad>/m6/everett-run2/test_curation_skill_produces_a0/curation.transcript.jsonl`.

## Re-review on the fixed engine

- **What changed:** Task 4 fixed M1 as engine gap 2 in 7e9f8bf ("fix: honor placeholder declarations on reviewed place-field claims"), on `feat/more-portals`. The controller ruled that the same commit, 2ddddb0, is re-reviewed on the fixed engine, with no new curation run.
- **Trees:**
  - A new review worktree on `curate/everett-run2` (2ddddb0) for the pack checks.
  - The run branch lacks 7e9f8bf, so the engine-dependent checks ran in a temporary worktree, detached at `feat/more-portals` (7e9f8bf), with `git merge --no-ff --no-commit curate/everett-run2`.
  - That merge conflicted only in `docs/decisions.md`, where both sides added a row after 163. I kept both rows there for testing.
  - The temporary merge was aborted with nothing committed. Both worktrees passed the never-force check and were removed plainly.
- **Evidence:** `rereview-*.txt`, `rereview-step4-live.json` and `m1_check.py.txt` in `docs/evidence/review-everett-2026-10-19/`.

| Check | Known positive | Result |
| --- | --- | --- |
| Step 2 mechanical checks. Nothing they read changed (the pack, the eval file, `summary.json`, and the base's overrides and `validation.json`). I re-ran them anyway, because they are free | the same positives as above, each reported again | output identical to the first review (`rereview-step2-checks.txt`) |
| M1: describe `f6vp-3svh`, `neighborhood` | the pre-fix behavior restored in memory gives `assigned_fraction` 1.0, `Not Assigned` in `values` and 20 values, and the check reports it unresolved | fixed engine, as on disk: `assigned_fraction` 0.9253, `placeholder_values` with `Not Assigned` (120,857 rows) and `null` (16), `Not Assigned` not in `values`, 19 values, reliability `partial`, level `reviewed`. **Resolved** |
| Step 3 offline gate (4 files) on the merged tree | n/a | 77 passed, exit 0. The full suite gives 1,242 passed and 124 skipped |
| Step 4 [LIVE] on the merged tree, at `freshness.today()` = 2026-10-20 | n/a | `atlas_find_portals` puts `data.everettwa.gov` first for "Everett", "Everett, WA" and `everett`, and `data.seattle.gov` for "Seattle". Levels match 4 of 4 (`f6vp-3svh` `reviewed`, 3 `profiled`). `atlas_get_reference` portals/`everett` gives `isError: false`, tier `profiled` |
| Guide examples on the merged tree | a copy with one `is_error: true` is reported | both examples return `isError: false` (10 and 19 rows) |

**Verdict:** M1 is closed by the engine fix, with the pack unchanged. No new finding. Minor findings m1–m5 stand, none of them blocking. No Material finding is open: **the pack is approved for merge.**
