# Review: the data.cityofchicago.org knowledge pack (milestone 4, curation run 1)

- **Reviewed:** `curate/chicago-run1` at 5a2a9c8, "feat: add the data.cityofchicago.org knowledge pack (profiled)". It branched from 064d819 and has 1 commit, 15 files, +1724/−9.
- **Reviewer:** a fresh Claude agent (Task 5). It did not run the curation, which was the headless `claude -p` child of Task 3.
- **Review worktree:** `<scratchpad>/m4/review-run1`, on `curate/chicago-run1`.
- **Evidence:** `docs/evidence/review-chicago-2026-10-19/` holds the probe outputs, the check output and the scripts, saved as `.py.txt`.
- **Verdict:** no Material finding and 7 Minor findings. **The pack is approved for merge.**

## Checks

Each check was first run on the known positive in brackets, and that run reported the positive.

| Check | Known positive | Result |
| --- | --- | --- |
| Path rule: `git diff --name-only 064d819 HEAD` through `path_violations` | `["README.md"]` returns `["README.md"]` | 15 paths, `[]` |
| Reliability evidence (rule 1) and `reviewed_by = "claude"` (rule 18), over `facts/*.toml` and `regions.toml` | a temp copy of `ijzp-q8t2.toml` with the ward claim's `reason` deleted is reported | 9 files and 16 claims set `reliability`: no problem. All 19 reviewed claims have `reviewed_by = "claude"`. `claim_summary` gives reviewed 19, reason and probe 17. The other 2 are the `unit_of_observation` claim, which has a reason and `document` evidence, and the `placeholder_share` claim, which has `placeholders` and no interpretation |
| Personal data: the scan over the pack, `evals/portals/data.cityofchicago.org.json` and `summary.json` `final_message` | `tests/fixtures/http/`: 76 `@seattle.gov` lines | no match. I read every sample value, the guide, the 3 `expect`s and the PR body: there are no names. The sample values are counts, layer ids, `UNKNOWN`, `" "`, and area, ward and ZIP labels |
| Tier: `tier`, `timezone` and the rule-21 comment above `[jurisdiction]` | a temp copy with a comment line above `[jurisdiction]` counts 1 | `tier = "profiled"`, `timezone = "America/Chicago"`, `jurisdiction` city/US/IL. **No comment** above `[jurisdiction]` (0). See finding m1 |
| Eval file | n/a | `covers` holds all 4 kinds, none missing. The `misleading_field` prompt (02) names neither `community_area`, `ijzp-q8t2` nor the dataset title (rule 22). One dataset is reviewed, so rule 23 does not apply. All 3 `expect`s state PASS, PARTIAL and FAIL |
| Guides: `summary.json` `checks.guide_examples` | a copy with one `is_error: true` item is reported | `exit_code` 0, 3 examples, all `is_error: false`. The prose agrees with the claims it cites, except finding m5. I re-probed the guide's September 2026 figures live (probe 14): 19,747 rows and 19,745 distinct `case_number`, as stated |
| Shared-file isolation (ruling 82): `registry_overrides.toml` | a copy with another table (`datahub.hhs.gov`) changed is reported | only the `data.cityofchicago.org` table changed. It was removed (CONTRIBUTING step 4). Every other table equals the base |
| Shared-file isolation (ruling 82): `validation.json`, parsed as JSON | a copy with one Seattle entry's `outcome` changed reports `portals[data.seattle.gov]` | only `portals["data.cityofchicago.org"]` differs (new, 62 entries). Every other portal equals the base, and so do the top-level keys |
| Step 3 offline gate: `uv run pytest -q tests/test_packs.py tests/test_tiers.py tests/test_release_gate.py` in the review worktree | n/a | 44 passed, exit 0 |
| Step 4 [LIVE]: `atlas_find_portals {"query": "Chicago"}` | n/a | first candidate `data.cityofchicago.org` |
| Step 4 [LIVE]: `atlas_describe_dataset` for every dataset `pack_levels` returns, at `freshness.today()` = 2026-10-19 | n/a | 8 of 8 match: `ijzp-q8t2` is `reviewed`, the other 7 are `profiled` (`step4-live.json`) |
| Step 4 [LIVE]: `atlas_get_reference {"topic": "portals", "item_id": "chicago"}` | n/a | `isError: false`, tier `profiled`. The alias is intact |

## Region codes ([LIVE], one probe at a time)

The pack relates computed-region codes to community areas and wards. Each probe below queried one layer view or the Crimes dataset, at `https://data.cityofchicago.org/resource/<id>.json`. Outputs are probes 01–12.

| Probe | Result | Pack statement it tests |
| --- | --- | --- |
| 01 `vrxf-vc4k` features for HYDE PARK, AUSTIN, DOUGLAS | `_feature_id` 8 is HYDE PARK (area 41), 26 is AUSTIN (area 25), 1 is DOUGLAS (area 35) | `regions.toml` (feature 1 is area 35, DOUGLAS); the guide (HYDE PARK is `8`, DOUGLAS is `1`); eval 01 (`'8'`); eval 02 (`'26'`, AUSTIN) |
| 02 Crimes, `community_area = '41'`, September 2026, by computed region | 197 in region 8, 2 in 5, 2 in 7: 201 | eval 01 reference 201; the code is the layer's `_feature_id` |
| 03 Crimes, region `'8'`, September 2026 | 202 | eval 01 reference 202 |
| 04 Crimes, `community_area = '25'`, 2003, by computed region | 30,196 in region 26 | eval 02's region 26 is Austin |
| 05 Crimes, region `'26'`, 2001–2003 | 29,277 / 28,289 / 30,238 | eval 02 reference |
| 06 Crimes, `community_area = '25'`, 2001–2003 | 296 / 21,120 / 30,841 | eval 02 misleading-field reference |
| 07 `8hcu-yrd4` features 3 and 5 | feature 3 is ward 5, and 5 is ward 7. `globalid` is a GUID | `regions.toml` and the guide (feature 3 is ward 5); the profiler defect (m2) |
| 08 `43wa-7qmu` features 1 and 33 | feature 1 is ward 12, and 33 is ward 5 | `regions.toml`; the ward-5 agreement probe in `ijzp-q8t2.toml` |
| 09 `awaf-s7ux`, highest `ward` | `OUT` features exist | `regions.toml` (an `OUT` feature) |
| 11 `bdys-3d7i` sample | `statefp10` is `17` in every row, and the tract is `name10` | the label column the pack set by hand (m2) |
| 12 `d9mm-jgwp` features 3, 4, 8 and 22 | 3, 4 and 8 are district 31, and 22 is district 1 | `regions.toml` (31 on features 3, 4 and 8); the district-001 agreement probe |

How an agent gets from a code to a named area:
- `regions.toml` sets `label_column = "community"` for `vrxf-vc4k`. In-process `atlas_describe_dataset` with `detail: "full"` lists label to code, for example `AUSTIN` 26, `HYDE PARK` 8, and `AVALON PARK` 41 (the trap that eval 01's FAIL names). The output is in `10-describe-ijzp-q8t2-place-fields.json`.
- The same labels reach a dataset that has no claim of its own: `22u3-xenr` lists `ALBANY PARK` 14 and `name10` for tracts.

**Verdict: the pack states the mapping correctly.** The pack and the guide say, for each affected layer, that a code is a feature id and not the area or ward number, with a correct example. `describe` resolves codes to names. Every eval `expect` value matches a live probe. There is no Material finding.

**For Task 7's re-grade: the agent's eval answers slipped.**
- All three runs of 02 call the computed code "area 26":
  - run 1: "Austin is area 26";
  - run 2: "(Austin is area 26)";
  - run 3: "filtered to community area 26 (Austin)".

  Austin's community-area number is 25, and 26 is its feature id. The counts are right, so the answer still meets PASS as the `expect` words it. The label is wrong.
- Run 2 of 01 took area 41 "from my own knowledge", not from the portal (finding m4).
- Run 1 of 03 mislabels weekdays: it calls Oct 10, a Saturday, a Friday.
- The runs of 01 (in runs 1 and 3) and 03 (in runs 2 and 3) state the region and lag facts correctly.

## Findings

No Material finding.

**Minor**
- **m1. No provenance comment above `[jurisdiction]`.** The brief's tier check expects the rule-21 comment, and the pack has none.
  - Rule 21 and CONTRIBUTING step 4 require it only when `jurisdiction` is missing. Here it came from the registry override at 064d819, whose comment named its source: "source: country US, region IL: the milestone 2 brief; geography (the named place lies there), not the title".
  - The agent followed its rules, and the values equal the base. The provenance now lives only in git history.
  - Suggestion (Task 6): the skill could say to carry an override's source comment into `portal.toml`.
- **m2. Profiler label-column defect (engine; not fixed here).** `Profiler.label_column` (`profiler/profile.py:486`) takes the layer's first `text` column.
  - Verified live: that is a GUID (`globalid`) for `8hcu-yrd4` and a constant state code (`statefp10` = `17`) for `bdys-3d7i`. It is `area_numbe` for `vrxf-vc4k` and `dist_label` for `d9mm-jgwp`.
  - The pack's workaround is sound. `regions.toml` sets `ward`, `name10`, `community` and `dist_num` by hand. These are portal-level claims, and `describe` applies them on reviewed and unreviewed datasets alike (checked on `ijzp-q8t2` and `22u3-xenr`).
  - The 7 unreviewed facts files keep the profiler's "candidate label column `statefp10`" text in their observations. That is harmless, because no interpretation uses it, but it can mislead a human reader.
  - The decisions row "Profiler's candidate label column" records it.
- **m3. Region values are not always listed.** The guide says `describe` with `detail: "full"` "lists each region's values with labels". On my call, 5 of the 9 computed regions on `ijzp-q8t2` came back `stats_status: "timeout"` with no values, among them the current wards (`8hcu-yrd4`) and police districts.
  - Community areas did resolve, so the eval paths work. For wards, though, an agent may get no code-to-ward map, and the guide gives only one example (feature 3 is ward 5) and no fallback.
- **m4. Reported `community_area` numbers carry no names.** Nothing in the pack says how to go from a reported number (`'41'`) to a name. The layer's `area_numbe` holds it, as the `regions.toml` observation notes, but no guide line says so. The pack steers 2001–2002 counts to the computed region, which has names, so this does not mislead. It is why eval 01 run 2 used outside knowledge.
- **m5. The guide overstates the fill rate.** It says the computed regions are "about 98.6% filled in every year". The pack's own claim gives 96.6% for 2002 on `vrxf-vc4k`, and 98.6% is the all-years figure.
- **m6. The reported `ward` value `0` is not declared.** `describe` lists `0` as a candidate placeholder on `ward` (2,629 rows). The pack declares `'0'` only for `community_area`, and the guide says nothing about ward 0.
- **m7. A stale test (ruling 85, fixed).** `tests/test_reference_topics.py::test_portals_item_for_a_portal_without_a_pack` used `chicago` as its portal without a pack.
  - On the pack tree it failed: `1 failed, 55 passed`.
  - Commit 371ffa3 on `feat/chicago-curation` (a `test:` commit, not a pack edit) picks the smallest `registry.json` id that no `portal.toml` defines, and asserts that the item is that portal, tier `generic`, knowledge `none` and no guides.
  - After the fix, the file passes on the base tree (56 passed) and on the pack tree, with the patch applied in the review worktree and then restored (56 passed; the chosen portal is `al-amcc.data.socrata.com`).

## Agent's own eval grades (PR body; self-graded, Task 7 re-grades)

| Task | covers | Run 1 | Run 2 | Run 3 |
| --- | --- | --- | --- | --- |
| 01-hyde-park-last-month | in_area, relative_date | PASS | PASS | PASS |
| 02-austin-2001-2003 | misleading_field | PASS | PASS | PASS |
| 03-crimes-yesterday | not_published | PASS | PASS | PASS |

The agent proposes `curated`, conditional on the test fix (m7, now made).

## Preserved eval transcripts (for Task 7)

- The agent's 3 runs are local and git-ignored. They are in `evals/results/2026-10-19-m4-curation-run1/evals-{1,2,3}/{01-hyde-park-last-month,02-austin-2001-2003,03-crimes-yesterday}.transcript.jsonl`, 9 transcripts, all `subtype: "success"`.
- The test's own eval run is in `<scratchpad>/m4/run1/test_curation_skill_produces_a0/evals/*.transcript.jsonl`.
- The curation transcript is `<scratchpad>/m4/run1/test_curation_skill_produces_a0/curation.transcript.jsonl`.
