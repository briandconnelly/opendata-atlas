# Carry-over from milestone 3 into the milestone 4 plan

Inputs the milestone 4 plan must account for, collected from the milestone 3 execution (branch `feat/knowledge-tooling`, squash-merged into `docs/design` as `177b45b`, 2026-10-19). Each item names its source. The milestone 4 plan either schedules it or records a decision not to.

**Reconciled 2026-10-19** (milestone 4 Task 9). Each item ends with its status: **Done** names the task and commit; **Deferred** names the `docs/decisions.md` row that defers it. Milestone 4 ran on `feat/chicago-curation`; the milestone's items below are accounted for at b6b39ec.

## Must address first

- **`pack_levels` does not map datasets to their region layers** (final review M-1, controller ruling 73). The portal summary and `tests/test_tiers.py` count every `region_layer` claim in a pack against every dataset, and drop the dataset's own `:@computed_region_*` place-field claims. The shipped code is wrong in both directions:

  - **Over-reach:** dataset A exposes reviewed layer LA, and dataset B exposes LB as an unreviewed observation. Describe reports A as `reviewed`, but the summary reports it as `profiled`.
  - **Under-reach:** A carries the profiler's fill observation on its computed-region column, the pack has no layer claim, and LB is reviewed. Describe reports A as `profiled`, but the summary reports it as `reviewed`, which is higher than describe. Every profiler draft is in this state, so the tier test could accept a `curated` declaration that describe would not support.
  - **Reviewed override:** the dataset has its own reviewed claim on the column (ruling 62), and the layer claim is an observation. Describe reports `reviewed`, but the summary reports `profiled`.
  - **Smallest fix,** probed in the final re-review but not committed. Change `pack_levels` in `src/opendata_atlas/portals/knowledge.py` (around lines 336-354). For each dataset, take its own `:@computed_region_*` place-field claim columns. Map each to its layer with `c.removeprefix(":@computed_region_").replace("_", "-")`. Pass those columns as `places`, with `layers=` set to that map. Fall back to the current all-pack-layers set only when the dataset has no such claims. Other `:` columns stay dropped. The probe showed:
    - all three cases above then match describe;
    - Seattle's `pack_levels` is unchanged (33kz-ixgy and kzjm-xkqj `reviewed`, the other four `none`);
    - with ru88 made an unreviewed observation, all six Seattle datasets read `profiled`, which matches the Fire 911 describe emulation.
  - **Caveats:**
    - The fix relies on Socrata's column-naming convention.
    - A dataset with claims on only some of its computed-region columns would under-count its layers.
    - The robust alternative is to record `layer` in the scope of the profiler's fill claim.
  - **Wording to correct with the fix:**
    - `docs/decisions.md` (the M-1 row) says the summary reads "never higher" than describe, which is false.
    - `CHANGELOG.md` and `docs/design.md` (Knowledge levels) say the summary lowers "as describe" does.
    - The M-1 row's note that the profiler emits region-layer observations is also false. The profiler never emits `region_layer` claims (`profiler/profile.py`, `emit.py`).
  - **Tests:** add the three synthetic cases above. **Done** (Task 1, `69fc7ea`; the wording corrections landed with it, and Task 6 `7da6d20` compares `pack_levels` with the real describe). Seattle's levels are unchanged.

## Maintainer decisions recorded as "Claude's call; maintainer to confirm"

- **The paid-run rule in `AGENTS.md`** (rulings 71 and M-7). Paid runs start only when the maintainer asks: `tests/test_curation_skill.py` with its opt-in, and `evals/run.py` with an out directory. Two cases count as asked: a curation run the maintainer started (for the skill's own step 11.3 evals), and a contributor running the path at their own request. Unchanged by milestone 4: the maintainer has not confirmed it. **Deferred** (decisions row "Milestone 4 carry-over reconciliation", item 1; the original row is "Paid-run rule in `AGENTS.md` (ruling 71)").

## Milestone 4 inputs from the curation skill

- **The revised `skills/curate-portal/SKILL.md` was traced by hand, never run** (ruling 66). Rulings 63, 64 and 67 changed it after its last real run. Chicago's curation is its first end-to-end run. **Done** (Task 3, `f0b962f`): the skill ran end to end on Chicago (1 test passed in 2,465 s; the agent's commit is 5a2a9c8). It exposed no defect in `SKILL.md`, which is unchanged.
- **The curating agent declares at most `profiled`** (ruling 64). Promotion to `curated` needs a reviewer other than the curating agent to re-grade the eval answers. Chicago "ships curated" therefore needs that review step in the milestone 4 plan. **Done** (Task 7, `ef2e9bf`): a reviewer other than the curating agent re-graded the 3 preserved runs and 3 fresh runs, and promoted Chicago to `curated` (decisions row "Chicago promoted to `curated`").
- **`--strict-mcp-config` isolation.** With `--mcp-config`, it was observed to drop claude.ai connectors (milestone 3 eval run, 50 of 50 sessions). The curation command, which passes no `--mcp-config`, was not observed. Check the curation child's `system/init` on the first Chicago run. **Done** (Task 3 Step 5, `f0b962f`): run 1's curation `system/init` lists no MCP server and no tool, and the check flagged a synthetic init that lists a connector first (`docs/evidence/curation-chicago-2026-10-19-run1/init-check.json`).
- **Branch `curate/test-2026-10-18`** (`c1acae5`) holds the Honolulu pack from run 2. It is unmerged and kept for inspection. It declared `curated` itself, because it predates ruling 64. Still present at `c1acae5`, untouched. **Deferred** (decisions row "Milestone 4 carry-over reconciliation", item 2; the maintainer's call).

## Still open (unchanged from earlier milestones)

- **Inherited fixture identities.** 76 `@seattle.gov` emails and 246 display or screen names remain in `tests/fixtures/http/`. The maintainer decides whether to scrub them before the repository is made public. Recounted 2026-10-19: 76 occurrences of 7 distinct addresses in 21 files, unchanged; none in `docs/evidence/`. **Deferred** (decisions row "Inherited fixture identities (milestone 4 carry-over)").
- **Token portability is unprobed.** It needs a `SOCRATA_APP_TOKEN` from the maintainer. No token was available in milestone 4 either. **Deferred** (decisions row "Token probe (milestone 4 carry-over)").
- **PyPI name reservation** (the maintainer's task). **Deferred** (decisions row "Milestone 4 carry-over reconciliation", item 3; milestone 5).
- **prek pins ruff v0.17.0.** That version missed a RUF007 that `uv run ruff check` caught, so the gate keeps both. Bump the pin at release. Still `v0.17.0` in `.pre-commit-config.yaml`; the gate keeps both linters. **Deferred** (decisions row "Milestone 4 carry-over reconciliation", item 4: bump at release).
- **Deferred minors** from the milestone 3 task reviews. The final review triaged all 34 as fine to defer. Notable ones:
  - the checker precedence and metadata-field prose in `docs/design.md`;
  - the profiler staging directory being mode 0700;
  - test-only hygiene items.
  The task reviews are not kept. Re-derive these by reviewing the touched files if milestone 4 changes them. **Done** for the ones milestone 4 touched (Task 6 Step 1, `9ccfd9e`, `docs/reviews/2026-10-19-m4-standards.md`, which re-derived them from the touched files); the rest stay fine to defer.

## Future-curation items (Chicago pack; added in milestone 4 Task 6)

The front door keeps these out of milestone 4: the pack's contents change only through a curation run's commit. Each is a Minor from the pack review (`docs/reviews/2026-10-19-m4-chicago-pack.md`). The next Chicago curation should address them:

- **m4, `community_area` numbers carry no names.** No guide line says how to go from a reported number (`'41'`) to a name. The community-area layer `vrxf-vc4k` has the number in `area_numbe` and the name in `community`. Eval 01 run 2 used outside knowledge for it.
- **m5, the guide overstates the fill rate.** The guide says the computed regions are "about 98.6% filled in every year". The pack's own claim gives 96.6% for 2002 on `vrxf-vc4k`, and 98.6% is the all-years figure.
- **m6, the reported `ward` value `0` is not declared.** Describe lists `0` as a candidate placeholder on `ward` (2,629 rows). The pack declares `'0'` only for `community_area`.
- **m1, provenance of the carried-over `[jurisdiction]`** (skill improvement, not a defect: ruling 86). The skill could say to carry a registry override's source comment into `portal.toml` when it removes the override. `SKILL.md` is unchanged in milestone 4, because the run exposed no defect in it.
- **m2, profiler label column.** Fixed in engine code (Task 6, ruling 87). 6 of the 7 unreviewed Chicago facts files still say "candidate label column `statefp10`" (the old profiler's pick) in their observations. A re-profile replaces that text.
- **m3, region values on describe `full`.** Deferred to the milestone 5 surface pass (decisions row "Region values on describe `full` when the grouping times out").
- **Portal summary titles.** The Chicago summary (topic `portals`) lists 7 of its 8 datasets as "(no title recorded)", because a dataset's title there comes only from its guide. Seattle has a guide for each of its 6 datasets, so its summary has every title (standards review F1).

Each item above is **Deferred** (decisions row "Chicago pack knowledge gaps for a future curation"), except m2, which is **Done** (Task 6, `2dccb87`, ruling 87) and m3, which is **Deferred** to milestone 5 (decisions row "Region values on describe `full` when the grouping times out"). Added in Task 9 and covered by the same row: the guide-level gaps found when the pack was re-graded (eval 02 reads code 26 as "area 26", eval 03's `expect` could forbid an estimated range for yesterday, ruling 88). Milestone 5 surface items found in milestone 4 are in the row "Milestone 5 surface items found in milestone 4".
