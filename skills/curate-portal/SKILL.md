---
name: curate-portal
description: Use when asked to "curate <portal>" in the opendata-atlas repository, where <portal> is a registered Socrata portal's id, alias, host or place name, or to take a registered portal from generic to profiled (or improve an existing pack) through the contribution path in CONTRIBUTING-portals.md. Works for Claude Code and Codex agents. Ends in a `.curation/outcome.json` naming how it ended and, unless it stopped before changing anything, one knowledge-pack commit on a curate/ branch with the printed title and body of its PR for a human to push and open. A completed run reviewed a dataset and made the portal's 3 eval runs, whatever their grades; a run that ends with no reviewed dataset, or blocked on an engine gap, ends earlier without paid eval runs. The agent never raises a tier to curated; a reviewer other than the curating agent decides any promotion.
---

# Curate a portal

This skill takes one registered portal through the contribution path in `CONTRIBUTING-portals.md`, headless, to one knowledge-pack commit and the text of its PR. The path's details live in that file; the steps below follow its numbering.

## Rules

1. Never set a `reliability` unless its claim's `interpretation` has a `reason` and the claim has `soql_probe`, `metadata_probe` or `document` evidence.
2. Never declare a `tier` that `tests/test_tiers.py` rejects.
3. Never raise a `tier` to `curated`. A new pack declares at most `profiled`; an existing pack keeps the tier it has. Step 12 says how to propose `curated`.
4. Commit only the path-rule paths: `src/opendata_atlas/portals/<pack>/`, `evals/portals/<pack>.json`, `src/opendata_atlas/portals/registry_overrides.toml`, `src/opendata_atlas/portals/validation.json` and `CHANGELOG.md` (the one-line entry of Ending step 4). Rule 6's working files under `.curation/` are never committed.
5. Never write a file or directory, or point a command's output, outside the repository.
6. Write every working file (profiler reports, a second profiler `--out`, the compatibility evidence, eval output, `served-check.json`, `outcome.json`) under `.curation/` in the repository root.
7. Name every engine defect you find in the PR body, whether or not you work around it in the pack. Never record one in a repository file.
8. Engine gaps:
   1. When, before step 11.3 starts, the pack cannot be made right without engine code (a claim the engine ignores, or a failing test only engine code can fix), stop curating and go to the Ending with outcome `blocked_engine`, the gap named in the PR body.
   2. With outcome `blocked_engine`, keep the tier rule 3 allows and run checks 11.1 and 11.2 first, accepting the failure the gap causes.
   3. An engine defect found after step 11.3 starts leaves the outcome `completed`; name it in the PR body (rule 7).
9. Never push.
10. Never open a PR.
11. Never file an issue.
12. Check order:
    1. Before the commit, run checks 11.1 (the drift run and the compatibility case) and 11.2 (step 11.2's commands) after your last change to a tracked file (`.curation/` is not tracked).
    2. Before the commit, run check 11.3 (the eval runs) after your last pack change.
    3. With outcome `blocked_engine` or `profiled_without_review`, skip 11.3.
13. The freeze after step 11.3 starts:
    1. Never change the pack or its eval file after step 11.3 starts. The drift rerun's update of `validation.json` is not a pack change.
    2. After step 11.3 starts, never run a command that can rewrite the pack or its eval file (`prek`, `ruff format` without `--check`, `ruff check --fix`), even on one file to diagnose a failure.
    3. When a check fails on this pack after step 11.3 starts (an 11.1 or 11.2 rerun under rule 12.1), or the pack digest changed (Ending step 1), leave the pack as it is and name the failing claim, line or digest in the PR body.
    4. After a failure rule 13.3 names, never propose `curated`.
14. Run `uv run python evals/run.py` only as step 11.3 prescribes (3 runs) or with `--help`.
15. Never run `tests/test_curation_skill.py`.
16. Never set `ATLAS_RUN_CURATION`.
17. The contribution path's rules:
    1. Follow every rule under "Contribution path, Rules" in `CONTRIBUTING-portals.md`.
    2. Where a rule here and one there both apply, both bind; rules 3, 4, 7, 8, 12 and 13 here win over that file where they differ.
    3. `AGENTS.md` allows paid runs only when the maintainer asks; a curation run the maintainer started counts as asked for step 11.3's 3 eval runs, and for no other paid run.
18. Write `reviewed_by` as your agent's identifier on every claim you review: `"claude"` for Claude Code, `"codex"` for Codex.
19. Never write a person's name, email address or phone number into a file you author or commit (the pack, the eval file, `CHANGELOG.md`, `served-check.json`, `outcome.json`), a commit message or PR text. Profiler reports and eval transcripts under `.curation/` may hold raw upstream rows; never copy a value from them into those files.
20. Write every `reviewed_at` and `observed_at` you add as today's date in UTC (Context: Today's date).
21. Set a missing `jurisdiction` only from a publisher page, cited in a comment above `[jurisdiction]` with the page's URL and the passage quoted exactly as the page has it, HTML entities included.
22. In a `misleading_field` task's prompt, never name the column under test or the dataset it trips on.
23. When the pack reviews more than one dataset, the eval tasks must span at least 2 of them.
24. When a command is denied, never get its effect through another command (such as `uv run python`). Copying a file is reading it and writing it with your file tools, not a workaround.
25. Stage files by path (`git add <path> ...`); never `git add -A` or `git add .`.
26. Every number and factual statement in a guide, a claim's `reason` or an eval `expect` comes from a probe recorded in the pack or one you ran in this session, or from a cited publisher page. Name a column you did not review as unreviewed; never describe it as if it were.
27. Give an `in_area` or `relative_date` task only when its `targets` name a column this pack reviews (step 9). In a pack with no reviewed dataset, no task covers either kind; never remove an existing pack's task whose targets are reviewed.
28. Every run ends through the Ending, which writes `.curation/outcome.json`, including a run that stops before changing anything (steps 0 to 2).
29. Call every opendata-atlas tool in-process from the repository root (Context: Tool calls), never through a connected MCP server, even when opendata-atlas tools are connected as MCP tools.
30. Start each eval run in a directory that does not exist yet (step 11.3), and never overwrite a transcript an eval run wrote.
31. In an existing pack, bringing profiler claims in never deletes or overwrites a claim the pack already has: merge them into an existing facts file (step 5). Remove an existing claim only as step 11.1 directs, for a check it fails, and name each removed claim in the PR body.

## Steps

Before step 0, read `CONTRIBUTING-portals.md` in full. The output paths below are under `.curation/` (rule 6), which git ignores and rule 4 keeps out of the commit. Run long commands (the profiler, the drift run, the compatibility case, each eval run) with a command timeout of at least 10 minutes: in Claude Code, a Bash timeout of 600000 ms.

0. **Check the prerequisites.** Run `uv --version`, `git rev-parse --show-toplevel` and `claude --version`. Step 11.3's eval runs launch Claude Code sessions whichever agent curates (Context: Reading a transcript), so `claude` must be installed even for a Codex curator. When one fails, stop: go to the Ending with outcome `preflight_failed`, naming the missing command in `reason`.
1. **Find the portal.** Call `atlas_find_portals` with `{"query": "<portal>"}` (rule 29). The candidate that is the portal gives `<portal id>`, its `id`.
   - When no candidate is the portal, stop: go to the Ending with outcome `not_registered`; the PR body says the portal needs a registry PR (CONTRIBUTING step 1).
   - When more than one candidate could be the portal and `<portal>` does not single one out (the candidates differ in `jurisdiction.level` and `<portal>` names no level, or several share its place name), stop before any profiler run: you cannot ask which one is meant. Go to the Ending with outcome `needs_input`, with each candidate's `id` and `jurisdiction.level` in `reason`.
2. **Profile it.** Find the existing pack, if any: the directory under `src/opendata_atlas/portals/` whose `portal.toml` has `id = "<portal id>"` (search every `portal.toml`; Seattle's pack is `data.seattle.gov/`). If there is none, run `uv run atlas-profile <portal id> --report .curation/report.json`; `<pack>` is the directory it writes. If there is one, `<pack>` is its directory name: run `uv run atlas-profile <portal id> --out .curation/profile --report .curation/report.json`, keep every claim the pack already has (rule 31), and bring into the pack only the claims you choose in step 5, after step 3 has screened them. Act on a nonzero exit as CONTRIBUTING step 2 says. On exit 3, 4 (after one retry), 5 or 6, stop: go to the Ending with outcome `profiler_failed`, with the exit code and the report's `error` in `reason`. None of these exits writes a pack, so the worktree is unchanged.
3. **Check the review values.** Read `review_values` in every profiler report you use. For each value that is a person's name, email address or phone number, delete the `[[claim]]` with that `claim_id` from the `facts/<dataset id>.toml` it is in, before copying any of it into the pack. Count the deletions for the PR body (rule 19 keeps the values out of it).
4. **Move the identity into the pack**, as CONTRIBUTING step 4 says. For an existing pack, check each item and change only what is missing:
   - delete the portal's entry in `registry_overrides.toml`, if it has one;
   - set `tier = "profiled"` in a new pack (rule 3);
   - if `jurisdiction` is missing, find a publisher page that names the city, county or state (Context: Fetching a page) and set `jurisdiction` from it (rule 21). `country` is the ISO 3166-1 alpha-2 code and `region` the ISO 3166-2 subdivision code without the country prefix (`HI`, not `US-HI`);
   - if `timezone` is missing and the jurisdiction lies in one zone, set `timezone` to that IANA zone name;
   - if the jurisdiction spans several zones, or no page gives the jurisdiction, leave `timezone` (and the missing `jurisdiction`) unset, and record why in a `portal.toml` comment and in the PR body;
   - after setting `timezone`, run `uv run atlas-profile <portal id> --out .curation/tz-pack --report .curation/tz-report.json` and bring its `*-timezone` claims into the pack's `facts/` files as step 5 merges them. On exit 4, retry once. On another nonzero exit, or a second exit 4, no dataset with a time column can reach `reviewed` (step 6) without the timezone claim: keep the claims as observations, name the exit and the report's `error` in the PR body, go to step 9, and end with outcome `profiled_without_review`.
5. **Choose and review a dataset.** Pick one profiled dataset that has a place field and a time column: `atlas_describe_dataset` lists a time column in `time_semantics`, and a place field either in `place_fields` or as a text column whose name names a place (`city`, `neighborhood`, `district`, `ward`, `zip`, `precinct`, `beat`, `community`, `tract`, `council`). If none has both, search, within these bounds: at most 6 `atlas_search_datasets` calls (for example "incident", "crime", "service request", "permit", "inspection", "violation"), then `atlas_describe_dataset` on at most 10 candidates. In an existing pack, choose a dataset the pack does not already review. Profile the first candidate that has both with `uv run atlas-profile <portal id> --dataset <id> --out .curation/<id> --report .curation/<id>-report.json`; on exit 2 (the `--out` exists) choose a new `--out`, and on exit 3 to 6 move to the next candidate. Run step 3 on its report, then bring its claims into the pack (rule 24):
   - when the pack has no `facts/<id>.toml`, copy the profiler's `facts/<id>.toml` into the pack;
   - when it has one, merge: add each profiler `[[claim]]` whose `id` the file does not hold, and keep every claim the file already holds, with its interpretation, as it is (rule 31). A profiler claim whose `id` the file already holds is not copied.

   If no candidate has both, record the queries and the candidates you described: in an existing pack that already reviews a dataset, change nothing and go to the Ending with outcome `no_change`; otherwise keep the claims as observations, go to step 9, and end with outcome `profiled_without_review`. Otherwise read the evidence of every draft claim on the chosen dataset, and probe with `atlas_query_dataset` where the evidence does not settle the meaning. For each time column, read the profiler's notes and probes: a share of rows at exactly 00:00:00 may be a default for an unknown time, and a max after today is a future-dated row; decide what each means and say so in the claim's `reason`. Keep the other datasets' claims as observations.
6. **Add interpretations with reasons**, as CONTRIBUTING step 6 says, until the dataset has every claim the Knowledge levels section lists for `reviewed`: a hand-written `unit_of_observation` claim, a reviewed claim for each place field and one for the primary time column. Review a computed-region place field (`source: "computed_region"`) either with a `region_layer` claim in `regions.toml`, which covers that layer on every dataset, or with a `place_field` claim on the column, which sets that dataset's `kind` and `reliability` over the layer's. Model each claim on `docs/pack-examples/<kind>.toml`. Then call `atlas_describe_dataset` on the dataset with `{"detail": "full"}`: its `knowledge.level` must be `reviewed`, and each reviewed claim must show in what it serves, as CONTRIBUTING step 6 lists (the place field's `kind` and `reliability`; declared placeholders out of the values and `assigned_fraction` below 1; the time column's `timezone`; a region's labels). Write `.curation/served-check.json`: a JSON list with one object per reviewed claim, `{"claim_id", "expected", "served", "matches"}`, where `served` is the value describe returned. Fix the pack until every `matches` is `true`; a claim the engine ignores although it loads is an engine defect (rules 7 and 8).
7. **Add `document` evidence where no probe suffices**, as CONTRIBUTING step 7 says.
8. **Write a guide for the reviewed dataset** in `src/opendata_atlas/portals/<pack>/guides.py`, modelled on `src/opendata_atlas/portals/data.seattle.gov/guides.py`, with `observed_at` set to today's date in UTC, the date you probed its figures. Check every number and statement in it against its source (rule 26). Call `atlas_query_dataset` with each `Example`'s `arguments`: every call must return `"isError": false`.
9. **Write the eval tasks** in `evals/portals/<pack>.json`, modelled on `evals/portals/data.seattle.gov.json`, as CONTRIBUTING step 9 says: each prompt asking the user's question and naming the place (rules 22 and 23), and each `expect` stating what PASS, PARTIAL and FAIL look like, with the reference values you probed and the identifiers, units and caveats a PASS must state correctly. Give each `in_area` task `targets` `{"dataset", "place": [<reviewed place columns>]}` and each `relative_date` task `targets` with `"time": <the reviewed time column>` (rule 27). With a reviewed dataset, cover all four kinds (`in_area`, `relative_date`, `misleading_field`, `not_published`); in a pack with no reviewed dataset, cover only the kinds a task truly tests (rule 27).
10. **Declare the tier.** Keep the tier rule 3 allows.
11. **Run the checks**, in order:
    1. The drift run: `uv run pytest --run-integration -m integration tests/test_drift.py -k <portal id> --ignore=tests/test_curation_skill.py`. Before step 11.3 starts, correct or remove each claim of this pack that does not pass, and rerun until it exits 0; after it starts, rule 13 applies. Exit 5 ("no tests collected") means `<portal id>` is not the `id` in `portal.toml`, which you fix, or the pack has no asserted claim, which you name in the PR body. Then the compatibility case, as CONTRIBUTING step 11.1 states it: `COMPAT_EVIDENCE_DIR=.curation/compat uv run pytest --run-integration -m integration tests/test_compat_live.py -k "test_portal_compat and <portal id>"`. It must report `PASSED`, and `.curation/compat/partial/outcomes.md` must show search, describe, query page 1, page 2 and the forced error each `ok` for `<portal id>`; an `XFAIL`, `XPASS` or `SKIPPED` is not a pass. A compatibility failure is an upstream or engine finding, not a pack error: it does not stop the run, but name it in the PR body, and with it never propose `curated` (step 12).
    2. Stage the pack directory and the eval file (`git add <path> ...`, rule 25), so that `prek`, which checks only tracked files, sees new ones. Run `uv run pytest -q --ignore=tests/test_curation_skill.py`, then `uv run prek run --all-files`, then `uv run ruff check` and `uv run ruff format --check`. Before step 11.3 starts, fix every failure that names `<portal id>`, a file in the pack or the eval file (rule 8 covers one only engine code can fix); after it starts, rule 13 applies, and a rerun of this check must not change the pack: run `uv run ruff check`, `uv run ruff format --check` and `uv run ty check` in place of `prek`, whose hooks rewrite files. List other portals' failures for the PR body.
    3. Only with a reviewed dataset (rule 12). First choose the run directory `.curation/<pack>-<UTC date>-<n>`, where `<n>` is the smallest positive integer for which that directory does not exist (rule 30). Run `uv run python scripts/pack_digest.py <pack>` and write `.curation/outcome.json` as `{"outcome": "completed", "pack": "<pack>", "pack_digest": "<its output>", "eval_runs": ["<run directory>/evals-1", "<run directory>/evals-2", "<run directory>/evals-3"]}`. Then make the 3 eval runs, into those directories. A run is one call per task id in `evals/portals/<pack>.json`: `uv run python evals/run.py --portal <pack> <run directory>/evals-<k> <task id>`. `evals/run.py` exits 2 without starting a session when a transcript it would write already exists; that means the directory was not new, and you choose the next `<n>` and rewrite `eval_runs`. Grade each transcript against its task's `expect` as PASS, PARTIAL or FAIL (Context: Reading a transcript); a transcript with no `result` event, or one whose `subtype` is not `"success"` (a session over its budget, say), grades FAIL and is not rerun (rule 14); `evals/run.py` exits 1 for such a session, which is that grade, not a reason to rerun. A session that used any tool other than the server's (`uv run python evals/report.py <out>` flags it and exits 1) also grades FAIL, and an answer that misstates an identifier, a unit or a caveat the `expect` requires grades at most PARTIAL, even with the right count. A FAIL that shows a pack error goes in the PR body as a knowledge gap (rule 13).
12. **Propose `curated` if it qualifies.** Keep the tier rule 3 allows. When an existing `curated` pack's runs fall short of these conditions, say so in the PR body for the reviewer; never change the tier yourself. When a dataset is `reviewed` with a guide, the tasks' `covers` include all four kinds, step 11.1's drift run and compatibility case both passed, across the 3 runs every task grades PASS in at least 2 and FAIL in at most 1 (CONTRIBUTING step 12), and no check failed on this pack after step 11.3 started (rule 13.4), say in the PR body that you propose `curated`, give the per-run grades, and say that the grades are your own and a reviewer other than you must re-grade the eval answers before promoting.

## Ending

Every run ends here (rule 28).

1. With outcome `completed`, run `uv run python scripts/pack_digest.py <pack>` again; when it differs from `pack_digest` in `.curation/outcome.json`, rule 13.3 applies.
2. Write `.curation/outcome.json`: `{"outcome", "pack", ...}`. `outcome` is one of:
   - `completed`: step 11.3 ran; keep its `pack_digest` and `eval_runs`;
   - `profiled_without_review`: the pack ends with no reviewed dataset;
   - `blocked_engine`: rule 8.1;
   - `no_change`: step 5, an existing pack with nothing new to review;
   - `preflight_failed`: step 0;
   - `not_registered`: step 1, no candidate is the portal;
   - `needs_input`: step 1, the portal is ambiguous;
   - `profiler_failed`: step 2's profiler run.

   Every outcome but `completed` adds `"reason"`: one sentence naming the search bound reached, the engine gap, the missing command, the candidates and their levels, or the profiler's exit code and `error`. `pack` is `<pack>` once step 2 has named it, and `null` before. With `no_change`, `preflight_failed`, `not_registered`, `needs_input` or `profiler_failed`, stop here: print the outcome and its reason (for `no_change`, the step 5 search), and make no commit.
3. Run `git status --short`. Every path you stage must be a path-rule path (rule 4).
4. Add one line to `CHANGELOG.md` under `## [Unreleased]`, in its `### Added` subsection for a new pack or `### Changed` for an existing one (create the subsection if it is missing): the portal id, the declared tier, and the datasets reviewed, in the style of the entries around it.
5. Commit on the current branch if its name starts with `curate/`; otherwise run `git switch -c curate/<pack>` first. Stage the paths, then commit with the message `feat: add the <portal id> knowledge pack (<declared tier>)` for a new pack, or `feat: curate the <portal id> knowledge pack` for an existing one, followed by any attribution lines your harness requires. With outcome `completed`, run the digest once more after the commit, since a commit hook can rewrite files; a change is rule 13.3's.
6. Print the PR title (the commit subject) and the PR body as your final message, for a human to push the branch and open the PR (rules 9 and 10).

The PR body names the portal, the outcome, the declared tier, whether you propose `curated` and why (step 12), the datasets reviewed (and, for `profiled_without_review`, the step 5 search), the served check, the drift outcomes, the compatibility case's outcome (each step's cell for the portal), the eval grades of all 3 runs (task by task) and their directories, how many claims step 3 deleted, any unset `jurisdiction` or `timezone` and why, every knowledge gap and engine defect found (rule 7), and every claim of another pack that failed a check.

## Context

### Tool calls

The steps call the opendata-atlas tools in-process (rule 29): a connected server, such as the one the opendata-atlas plugin adds, runs an installed release, which reads its own packs, not the ones you are editing. Call each one from the repository root, with its arguments as one JSON argument:

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

`evals/run.py` writes `<task id>.transcript.jsonl` per task: one JSON event per line. The last line is the `result` event: `subtype` is `"success"` when the session ended normally, and `result` is the agent's final answer, the text you grade. The eval sessions run in Claude Code, capped at $1 each, whichever agent curates.

### Names and files

- `<portal>` is what the user named; `<portal id>` is the canonical id (the `id` in `portal.toml`); `<pack>` is the pack directory's name, by default the canonical id, so for `data.honolulu.gov` the eval file is `evals/portals/data.honolulu.gov.json`.
- Seattle's pack (`src/opendata_atlas/portals/data.seattle.gov/`) and `evals/portals/data.seattle.gov.json` are the worked model of a curated portal.
- The drift run writes this portal's entries into `validation.json`; `tests/test_release_gate.py` fails until every asserted claim has an entry.
- `tests/test_curation_skill.py` runs this skill headless (`ATLAS_CURATION_HOST`: `claude`, or `codex` under `codex exec` with a workspace-write sandbox that allows network) on a branch `curate/test-<date>`, and checks the commit against the path rule and rule 3, `.curation/outcome.json` (for `completed`: its digest against the committed pack, a transcript per task in each of the 3 `eval_runs`, `served-check.json` and the compatibility case's evidence for the portal; no eval run otherwise; no commit for the outcomes that stop at Ending step 2), that every claim the base pack held is still there or named in the final message, the checks for its outcome and the guide examples. Under it, commands outside the allowlist (`git switch`, `gh`, `rm`, `cp`) are denied, and so are writes outside the repository.
