# Trace of the revised `skills/curate-portal/SKILL.md` (Task 14 fix round 1, no paid run)

This walks the skill step by step on 2026-10-18 (local), using the real commands in read-only or `--help` form, from the repository root, at the fix-round working tree.
- `evals/run.py` ran only with `--help`, with a fake `claude` on PATH that logs each launch. The known positive at the end of the 11.3 block shows a real launch is logged.
- Step 2 profiled 1 dataset into the git-ignored `.curation/trace/`. That makes live GET requests only, and `git status` shows nothing under `.curation/`.
- `.curation/` was deleted after the trace.
- No pack was written to `src/`, no commit was made, and no paid session ran.

Step map:
- 0: `.curation/` is ignored (rules 5, 6).
- 1: `atlas_find_portals`.
- 2: the profiler, with its `--help` and an ignored `--out`.
- 3: `review_values` in the report.
- 4: the page fetch (2 passages contain "City and County of Honolulu") and the UTC-date command (rule 20).
- 5/6: describe shows the computed-region place field and the time columns, with `knowledge` still `none` at HEAD; the pack examples exist.
- 8: the skill's literal tool-call command.
- 9: rule 22's known positive. Run 2's `misleading_field` prompt names both its dataset and its column, and the new rule forbids that.
- 11.1: the drift selection. Seattle collects 8; Honolulu exits 5 at HEAD, where it has no pack.
- 11.3: `--help` only, zero launches.
- 12: the test's tier check flags run 2's self-declared `curated` (known positive) and accepts `profiled`.
- Ending: the `git switch -c` and `git commit` help forms; SKILL.md names no `gh` command (rule 10).

```
## step 0: .curation ignored
.gitignore:63:.curation/	.curation/report.json
## step 1
candidates: ['data.honolulu.gov']
## step 2
usage: atlas-profile [-h] [--datasets DATASETS] [--out OUT] [--report REPORT]
                     host

atlas-profile: wrote 0 claims to .curation/trace/pack
exit 0
 M CHANGELOG.md
 M CONTRIBUTING-portals.md
 M docs/decisions.md
 M docs/design.md
 M docs/evidence/curation-2026-10-18/audit.md
 M docs/evidence/curation-2026-10-18/summary.json
 M skills/curate-portal/SKILL.md
 M src/opendata_atlas/assets/contributing.md
 M tests/test_contributing.py
 M tests/test_curation_env.py
 M tests/test_curation_skill.py
(git status above: nothing under .curation)
## step 3
review_values entries: 0 keys: ['asset_mix', 'datasets', 'error', 'flagship_basis', 'identity_detail', 'identity_verified', 'portal_id', 'profiled_at', 'review_values']
## step 4 page fetch + rule 20 date
2
2026-10-19
## step 5/6 describe
place_fields [(':@computed_region_7asa_3qps', 'computed_region')] time ['datecreated', 'dateupdated'] knowledge none
column_timezone.toml
padded_values.toml
place_field.toml
placeholder_share.toml
region_layer.toml
unit_of_observation.toml
## step 9 rules 22/23 against run 2's eval file (known positive)
03-311-zipcode-column names dataset id: True | names column zipcode: True
datasets in expects: ['6hui-dvrh', 'jdy7-ftwe', 'pxs8-ci86']
## step 11.1 (collect-only form)
8 tests collected in 0.01s
honolulu at HEAD (no pack): exit 5 (5 = no tests collected)
## step 11.3 (--help only, fake claude logs launches)
--help exit 0
--portal --help exit 0
launches: 0
known positive launches:        1
## step 12 / test tier check against run 2's portal.toml (known positive)
tier = "curated"
tier_failure(curated): declared tier 'curated'; the curating agent declares at most `profiled`
tier_failure(profiled): None
## Ending (help forms; no commit made)
    -c, --[no-]create <branch>
                  [--dry-run] [(-c | -C | --squash) <commit> | --fixup [(amend|reword):]<commit>]
rule 10: the Ending names no gh command: 0
step 8 (skill literal command): isError False returned_rows 1
```

## Fix round 2 (ruling 67)

Step 11.2's command became `uv run pytest -q --ignore=tests/test_curation_skill.py` (rule 15). Traced:

```
$ uv run pytest --collect-only -q | grep test_curation_skill        # known positive
tests/test_curation_skill.py::test_curation_skill_produces_a_passing_pack
$ uv run pytest --collect-only -q --ignore=tests/test_curation_skill.py | grep -c test_curation_skill
0
$ uv run pytest -q --ignore=tests/test_curation_skill.py
1108 passed, 45 skipped
```

The other ruling 67 changes are wording only (rule 4 "Commit only", rule 13's move after 11.3, steps 11.1, 11.2 and 12); they change no command.
