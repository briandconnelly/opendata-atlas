---
name: curate-portal
description: Use when asked to "curate <portal>" in the opendata-atlas repository, where <portal> is a registered Socrata portal's id, alias, host or place name, or to take a registered portal from generic to profiled through the contribution path in CONTRIBUTING-portals.md. Ends in one knowledge-pack commit on a curate/ branch, declared at most profiled, that passed the drift run, the offline gate and the portal's evals, and the printed title and body of its PR for a human to push and open. A reviewer other than the curating agent decides any promotion to curated.
---

# Curate a portal

This skill takes one registered portal through the contribution path in `CONTRIBUTING-portals.md`, headless, to one knowledge-pack commit and the text of its PR. The path's details live in that file; the steps below follow its numbering.

## Rules

1. Never set a `reliability` unless its claim's `interpretation` has a `reason` and the claim has `soql_probe`, `metadata_probe` or `document` evidence.
2. Never declare a `tier` that `tests/test_tiers.py` rejects.
3. Never declare `tier = "curated"`; declare at most `profiled`. Step 12 says how to propose `curated`.
4. Commit only the path-rule paths: `src/opendata_atlas/portals/<pack>/`, `evals/portals/<pack>.json`, `src/opendata_atlas/portals/registry_overrides.toml` and `src/opendata_atlas/portals/validation.json`. Rule 7 adds the only exception, `docs/decisions.md`. Rule 6's working files under `.curation/` are never committed.
5. Never write a file or directory, or point a command's output, outside the repository.
6. Write every working file (profiler reports, a second profiler `--out`, eval output) under `.curation/` in the repository root.
7. Log every engine defect you find as one row of the table in `docs/decisions.md`, whether or not you work around it in the pack.
8. When the pack cannot be made right without engine code, stop curating: keep `tier = "profiled"`, run checks 11.1 and 11.2, and go to the Ending with the gap named in the PR body.
9. Never push.
10. Never open a PR.
11. Never file an issue.
12. Before the commit, run checks 11.1 (the drift run) and 11.2 (`uv run pytest -q --ignore=tests/test_curation_skill.py`, then `uv run prek run --all-files`) after your last change to any file, and check 11.3 (the eval runs) after your last pack change. After a rule 8 stop, skip 11.3.
13. Never change the pack after step 11.3 starts. When a check fails on this pack after that (an 11.1 or 11.2 rerun under rule 12), leave the pack unchanged, name the failing claim or line in the PR body, and do not propose `curated`.
14. Run `uv run python evals/run.py` only as step 11.3 prescribes (3 runs) or with `--help`.
15. Never run `tests/test_curation_skill.py`.
16. Never set `ATLAS_RUN_CURATION`.
17. Follow every rule under "Contribution path, Rules" in `CONTRIBUTING-portals.md`. Where a rule here and one there both apply, both bind; rules 4, 7, 8 and 13 here win over that file where they differ. `AGENTS.md` allows paid runs only when the maintainer asks; a curation run the maintainer started counts as asked for step 11.3's 3 eval runs, and for no other paid run.
18. Write `reviewed_by = "claude"` on every claim you review.
19. Never write a person's name, email address or phone number into any file, commit message or PR text.
20. Write every `reviewed_at` and `observed_at` you add as today's date in UTC (Context: Today's date).
21. Set a missing `jurisdiction` only from a publisher page, cited in a comment above `[jurisdiction]` with the page's URL and the passage quoted exactly as the page has it, HTML entities included.
22. In a `misleading_field` task's prompt, never name the column under test or the dataset it trips on.
23. When the pack reviews more than one dataset, the eval tasks must span at least 2 of them.
24. When a command is denied, never get its effect through another command (such as `uv run python`).
25. Stage files by path (`git add <path> ...`); never `git add -A` or `git add .`.

## Steps

Before step 1, read `CONTRIBUTING-portals.md` in full. The output paths below are under `.curation/` (rule 6), which git ignores and rule 4 keeps out of the commit.

1. **Find the portal.** Call `atlas_find_portals` with `{"query": "<portal>"}` (Context: Tool calls). The candidate that is the portal gives `<portal id>`, its `id`. If none is, stop: print that the portal needs a registry PR (CONTRIBUTING step 1) and make no commit.
2. **Profile it.** Run `uv run atlas-profile <portal id> --report .curation/report.json`, with a Bash timeout of 600000 ms. `<pack>` is the directory it writes, `src/opendata_atlas/portals/<portal id>/`. Act on a nonzero exit as CONTRIBUTING step 2 says. On exit 3, 4 (after one retry) or 5, stop: print the exit code and the report's `error`, and make no commit.
3. **Check the review values.** Read `review_values` in `.curation/report.json`. For each value that is a person's name, email address or phone number, delete the `[[claim]]` with that `claim_id` from `src/opendata_atlas/portals/<pack>/facts/<dataset id>.toml`. Count the deletions for the PR body (rule 19 keeps the values out of it).
4. **Move the identity into the pack**, as CONTRIBUTING step 4 says:
   - delete the portal's entry in `registry_overrides.toml`, if it has one;
   - set `tier = "profiled"`;
   - if `jurisdiction` is missing, find a publisher page that names the city, county or state (Context: Fetching a page) and set `jurisdiction` from it (rule 21). `country` is the ISO 3166-1 alpha-2 code and `region` the ISO 3166-2 subdivision code without the country prefix (`HI`, not `US-HI`);
   - if `timezone` is missing and the jurisdiction lies in one zone, set `timezone` to that IANA zone name;
   - if the jurisdiction spans several zones, or no page gives the jurisdiction, leave `timezone` (and the missing `jurisdiction`) unset, and record why in a `portal.toml` comment and in the PR body;
   - after setting `timezone`, run `uv run atlas-profile <portal id> --out .curation/tz-pack --report .curation/tz-report.json` and copy its `*-timezone` claims into the pack's `facts/` files.
5. **Review observations.** Pick one dataset that has a place field and a time column (`atlas_describe_dataset` lists both in `place_fields` and `time_semantics`); if no profiled dataset has both, skip to step 9. Read the evidence of every draft claim on that dataset, and probe with `atlas_query_dataset` where the evidence does not settle the meaning. Keep the other datasets' claims as observations.
6. **Add interpretations with reasons**, as CONTRIBUTING step 6 says, until the dataset has every claim the Knowledge levels section lists for `reviewed`: a hand-written `unit_of_observation` claim, a reviewed claim for each place field and one for the primary time column. Review a computed-region place field (`source: "computed_region"`) either with a `region_layer` claim in `regions.toml`, which covers that layer on every dataset, or with a `place_field` claim on the column, which sets that dataset's `kind` and `reliability` over the layer's. Model each claim on `docs/pack-examples/<kind>.toml`. Then call `atlas_describe_dataset` on the dataset: its `knowledge.level` must be `reviewed`.
7. **Add `document` evidence where no probe suffices**, as CONTRIBUTING step 7 says.
8. **Write a guide for the reviewed dataset** in `src/opendata_atlas/portals/<pack>/guides.py`, modelled on `src/opendata_atlas/portals/seattle/guides.py`. Call `atlas_query_dataset` with each `Example`'s `arguments`: every call must return `"isError": false`.
9. **Write the eval tasks** in `evals/portals/<pack>.json`, modelled on `evals/portals/seattle.json`: at least one task per `covers` kind (`in_area`, `relative_date`, `misleading_field`, `not_published`), each prompt asking the user's question and naming the place (rules 22 and 23), each `expect` stating what PASS, PARTIAL and FAIL look like, with the reference values you probed.
10. **Declare `profiled`.** Keep `tier = "profiled"`.
11. **Run the checks**, in order:
    1. `uv run pytest --run-integration -m integration tests/test_drift.py -k <portal id> --ignore=tests/test_curation_skill.py`. Before step 11.3 starts, correct or remove each claim of this pack that does not pass, and rerun until it exits 0; after it starts, rule 13 applies. Exit 5 ("no tests collected") means `<portal id>` is not the `id` in `portal.toml`, which you fix, or the pack has no asserted claim, which you name in the PR body.
    2. `uv run pytest -q --ignore=tests/test_curation_skill.py`, then `uv run prek run --all-files`. Before step 11.3 starts, fix every failure line that starts with `<portal id>` or names a file in the pack; after it starts, rule 13 applies, and a rerun of this check must not change the pack: run `uv run ruff check`, `uv run ruff format --check` and `uv run ty check` in place of `prek`, whose hooks rewrite files. List other portals' failures for the PR body.
    3. Make 3 eval runs, into `.curation/evals-1`, `.curation/evals-2` and `.curation/evals-3`. A run is one call per task id in `evals/portals/<pack>.json`: `uv run python evals/run.py --portal <pack> .curation/evals-<n> <task id>`, each with a Bash timeout of 600000 ms. Grade each transcript against its task's `expect` as PASS, PARTIAL or FAIL (Context: Reading a transcript); a transcript with no `result` event, or one whose `subtype` is not `"success"`, grades FAIL. A FAIL that shows a pack error goes in the PR body as a knowledge gap (rule 13).
12. **Propose `curated` if it qualifies.** Keep `tier = "profiled"` (rule 3). When a dataset is `reviewed` with a guide, the tasks' `covers` include all four kinds, across the 3 runs every task grades PASS in at least 2 and FAIL in at most 1 (CONTRIBUTING step 12), and no check failed on this pack after step 11.3 started (rule 13), say in the PR body that you propose `curated`, give the per-run grades, and say that the grades are your own and a reviewer other than you must re-grade the eval answers before promoting.

## Ending

1. Run `git status --short`. Every path you stage must be a path-rule path, or `docs/decisions.md` (rule 7).
2. Commit on the current branch if its name starts with `curate/`; otherwise run `git switch -c curate/<pack>` first. Stage the paths, then commit with the message `feat: add the <portal id> knowledge pack (profiled)`, followed by any attribution lines your harness requires.
3. Print the PR title (the commit subject) and the PR body as your final message, for a human to push the branch and open the PR (rules 9 and 10).

The PR body names the portal, the declared tier, whether you propose `curated` and why (step 12), the datasets reviewed, the drift outcomes, the eval grades of all 3 runs (task by task), how many claims step 3 deleted, any unset `jurisdiction` or `timezone` and why, every knowledge gap and engine defect found (with its `docs/decisions.md` row), and every claim of another pack that failed a check.

## Context

### Tool calls

The steps call the opendata-atlas tools. When they are not connected as MCP tools, call each one in-process, from the repository root, with its arguments as one JSON argument:

```
uv run python -c 'import asyncio, json, sys
from fastmcp import Client
from opendata_atlas.mcp.server import build_server
async def main():
    async with Client(build_server()) as c:
        r = await c.call_tool_mcp(sys.argv[1], json.loads(sys.argv[2]))
    print(json.dumps(r.model_dump(mode="json", by_alias=True, exclude_none=True), indent=1))
asyncio.run(main())' atlas_find_portals '{"query": "honolulu"}'
```

The output is the result as a client receives it: `isError`, and `structuredContent` with the tool's fields or, on failure, the error envelope. The in-process server reads the pack as it is on disk, so a describe call shows your edits. When the arguments hold a SoQL string literal (single quotes), wrap the JSON argument in double quotes and escape its inner double quotes: `"{\"portal\": \"seattle\", \"dataset_id\": \"kzjm-xkqj\", \"select\": [\"count(*) AS n\"], \"where\": \"type = 'Aid Response'\"}"`.

### Fetching a page

To read a publisher page for `document` evidence, print every passage of it that contains a phrase:

```
uv run python -c 'import re, sys, httpx
text = httpx.get(sys.argv[1], follow_redirects=True, timeout=30).text
print(*sorted(set(re.findall(r"[^<>]{0,120}" + re.escape(sys.argv[2]) + r"[^<>]{0,120}", text))), sep="\n")' https://data.honolulu.gov/ "Honolulu"
```

The output keeps the page's HTML entities, such as `&copy;`; rule 21 quotes them as they appear.

### Today's date

`uv run python -c 'from datetime import UTC, datetime; print(datetime.now(UTC).date())'` prints today's UTC date, the date the profiler and the drift run write.

### Reading a transcript

`evals/run.py` writes `<task id>.transcript.jsonl` per task: one JSON event per line. The last line is the `result` event: `subtype` is `"success"` when the session ended normally, and `result` is the agent's final answer, the text you grade.

### Names and files

- `<portal>` is what the user named; `<portal id>` is the canonical id (the `id` in `portal.toml`); `<pack>` is the pack directory's name, by default the canonical id, so for `data.honolulu.gov` the eval file is `evals/portals/data.honolulu.gov.json`.
- Seattle's pack (`src/opendata_atlas/portals/seattle/`) and `evals/portals/seattle.json` are the worked model of a curated portal.
- The drift run writes this portal's entries into `validation.json`; `tests/test_release_gate.py` fails until every asserted claim has an entry.
- `tests/test_curation_skill.py` runs this skill headless on a branch `curate/test-<date>` with a fixed tool allowlist, and checks the commit against the path rule, a declared tier of at most `profiled`, the four checks and the guide examples. Under it, commands outside the allowlist (`git switch`, `gh`, `rm`) are denied, and so are writes outside the repository.
