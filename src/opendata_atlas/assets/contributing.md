# Contributing portal knowledge

Definitions for reading `tier` and `knowledge`, and the path for contributing a portal's knowledge pack. This file is `CONTRIBUTING-portals.md` in the repository; the server serves the same text as reference topic `contributing`.

## Portal tiers
A portal's `tier` summarizes it for discovery and contribution. It never stands in for dataset knowledge: an unreviewed dataset on a `curated` portal reports `none`.
- `generic`: registered from the Socrata catalog; no recorded knowledge.
- `profiled`: a knowledge pack holds profiler observations; nobody has reviewed enough of them for `curated`.
- `curated`: identity verified, at least one `reviewed` dataset with a guide, and the live smoke test and the portal's eval tasks passing.

`tests/test_tiers.py` checks the conditions a pack's contents decide: `profiled` needs at least one claim; `curated` needs a dataset that is `reviewed` and has a guide, and an eval file whose tasks' `covers` include all four kinds (step 9). Identity verification, the smoke test and the eval runs are live, so the promotion PR's CI runs them. A registered portal without a pack is `generic`.

## Knowledge levels
Reported per dataset and per column in `knowledge`, and as the dataset's level in `knowledge_notice`.
- `none`: nothing recorded; engine behavior only.
- `profiled`: the profiler recorded observations (fill rates, candidate placeholders, timezone tests); nobody reviewed them.
- `reviewed`: a contributor reviewed the observations and recorded interpretations (reliability, placeholder declarations, timezone, unit of observation).

A dataset is `reviewed` when it has a reviewed unit-of-observation claim and a reviewed claim for every place field it exposes and for its primary time column (the column `data_coverage` reports). A dataset with reviewed claims short of that is `profiled` if any claim on it is an unreviewed observation, else `none`; its reviewed claims still apply column by column.

A claim is reviewed when it carries an `interpretation`, or, for `placeholder_share`, a `placeholders` declaration; either way it records `reviewed_by` (an agent or person identifier) and `reviewed_at` (the review date). An agent's review counts as a review.

## Validation and freshness
`validation` says what a claim's checks last found: `"passed"`, `"contradicted"` or `"inconclusive"` from the last drift run, `"unchecked"` for a claim with no checks, and `"stale"` when the checks last ran over 180 days ago by the server's clock. A stale claim that vouched for the data stops vouching: an `ok` place field reports reliability `unknown`, a column timezone is omitted, and a placeholder declaration no longer removes its values (they are listed in `candidate_placeholders`, and `assigned_fraction` is omitted). A stale `partial` or `unreliable` verdict is kept, since withdrawing a warning is the dangerous direction. Scheduled drift checks cannot change an installed release; the runtime freshness rule is what protects old installs.

- The drift run, `uv run pytest --run-integration -m integration`, runs pack assertions live and records each checked claim's `checked_at` and `outcome` in `src/opendata_atlas/portals/validation.json`. Step 11 runs it scoped to one portal.
- The release gate, `tests/test_release_gate.py`, fails on a `contradicted` claim, a claim `inconclusive` twice running, an asserted claim with no entry in `validation.json`, or a claim whose assertion changed since its entry was checked (rerun the drift run on it).
- Staleness acts at runtime: the server degrades stale claims as above, by its own clock. The tests run at a pinned date, so `tests/test_tiers.py` never sees a review go stale. A drift run gives each claim it checks a new `checked_at`.

## Contribution path
A contribution is one pack PR for one portal. Run every step in a clone of the repository, from its root. `<host>` is the portal's canonical id, alias or public host. `<pack>` is the pack directory's name: the profiler's `--out` directory, by default the canonical id. An agent can follow this path with the `curate-portal` skill, `skills/curate-portal/SKILL.md` in the repository.

### Rules
- A pack PR must change only `src/opendata_atlas/portals/<pack>/`, `evals/portals/<pack>.json`, `src/opendata_atlas/portals/registry_overrides.toml` and `src/opendata_atlas/portals/validation.json`.
- Before committing profiler output, delete every claim whose `review_values` entry identifies a person (step 3).
- Write the profiler report (`--report`), any second profiler `--out`, and the eval output (`<out>`) under `.curation/` (git-ignored) or outside the repository; never commit them.
- Probe `evals/run.py` only with `uv run python evals/run.py --help`.
- Every `interpretation` must have a `reason`, and its claim must have `reviewed_by`, `reviewed_at`, and at least one `soql_probe`, `metadata_probe` or `document` evidence.
- Declare only a tier whose conditions hold.
- Never edit another pack, nor its entries in `validation.json`. This rule wins over every check below: a check that fails only on another pack's claims never makes you edit that pack.
- Name every claim of another pack that fails a check in the PR description.

### Steps
Follow them in order.

1. **Find or register the portal.** Call `atlas_find_portals` with `query` set to the place name or host. If no candidate is the portal, it is not registered: add an entry to `src/opendata_atlas/portals/registry_overrides.toml` in a separate registry PR (the file's comments describe the fields). In that PR, `scripts/build_registry.py` regenerates `src/opendata_atlas/portals/registry.json` from the entries; continue after it merges. The profiler profiles only registered portals.
2. **Profile it.** Run `uv run atlas-profile <host> --report .curation/report.json`. It writes a draft pack to `src/opendata_atlas/portals/<canonical id>/` (`--out` names another directory) and profiles the 10 most-viewed datasets (`--datasets N` for another count). On a nonzero exit:
   - 2: the host is not registered, the `--out` directory exists, or `--out` is missing because the command ran outside the repository root. Fix the argument or run from the root; the profiler never overwrites a pack.
   - 3: catalog identity did not verify. No pack is written; stop, because the registry's identity for the portal needs a fix (a registry PR) before it can be profiled.
   - 4: an upstream request failed before any dataset was profiled. The report's `error` names the step; rerun later.
   - 5: the emitted pack would not load. Nothing is written; stop and report the error as a profiler defect.
3. **Check the review values.** The profiler prints every emitted value outside the shared placeholder vocabulary on stderr, under "Review these values before committing; drop any that identify a person", and lists them in the report as `review_values` (`claim_id`, `value`). For each value that identifies a person, delete the `[[claim]]` with that `claim_id` from `facts/<dataset id>.toml`.
4. **Move the identity into the pack.** `portal.toml` now defines the portal's identity.
   - If `registry_overrides.toml` has an entry for the portal's id, delete it; `scripts/build_registry.py` rejects an override for a pack's id.
   - The profiler copies the registry's tier. Set `tier = "profiled"`.
   - If `jurisdiction` is missing, set it (`level`, `country`, and `region` where it applies) only from `document` evidence, such as a publisher page that names the city, county or state. Cite it in a comment above `[jurisdiction]`: the page's URL and the passage, verbatim. `country` is the ISO 3166-1 alpha-2 code (`US`); `region` is the ISO 3166-2 subdivision code without the country prefix (`HI`, not `US-HI`).
   - If `timezone` is missing, set it to the IANA zone name only when `jurisdiction` is set and lies in one zone.
   - When the jurisdiction spans several zones, leave `timezone` unset, record why in a comment in `portal.toml` (the zones it spans), and say so in the PR description.
   - With no document evidence for the jurisdiction, leave `jurisdiction` and `timezone` unset, record why in a comment in `portal.toml`, and say so in the PR description.
   - After setting `timezone`, rerun the profiler with `--out .curation/<name>`, and copy its `*-timezone` claims into `facts/`. Without a timezone the profiler runs no timezone tests, and a dataset with a time column cannot be `reviewed` without a reviewed claim on that column.
5. **Review observations.** Every draft claim is an observation: evidence and assertions, no interpretation. For each, read its evidence, and probe further with `atlas_query_dataset` where the evidence does not settle the meaning. Then interpret it (step 6), keep it as an observation, or delete it. The report's `notes` say why a column or probe gave no claim.
6. **Add interpretations with reasons.** Add `interpretation`, `reviewed_by` and `reviewed_at`; for `placeholder_share`, add a `placeholders` declaration with `reviewed_by` and `reviewed_at`. A reviewed `place_field` on a text column can declare its column's placeholders the same way, with `placeholders`; on a computed-region column, describe ignores them. The loader rejects a reviewed claim missing what its kind needs:
   - `place_field`: `interpretation.kind` (a place kind) and `reliability` (`ok`, `partial` or `unreliable`);
   - `region_layer`: those two and `label_column`;
   - `column_timezone`: `timezone`;
   - `unit_of_observation`: `unit` (write this claim by hand; the profiler emits none).

   Each kind has an example in `docs/pack-examples/<kind>.toml`. A dataset reaches `reviewed` only with all the claims Knowledge levels lists.
7. **Add `document` evidence where no probe suffices**, such as a unit of observation stated on the publisher's page: `kind = "document"`, `url`, `quote` (the passage, verbatim) and `observed_at`. A claim whose evidence is only `document` or `manual_observation` has no assertion and reports `validation: "unchecked"`.
8. **Write a guide per reviewed dataset** in `src/opendata_atlas/portals/<pack>/guides.py`: a `GUIDES` tuple of `opendata_atlas.core.guides.Guide`, one per dataset, with `Example` queries whose `arguments` are literal `atlas_query_dataset` calls. Run each example's `arguments` once with `atlas_query_dataset` and confirm it succeeds: the live guide test (`tests/test_live.py`) runs only Seattle's examples. `src/opendata_atlas/portals/seattle/guides.py` is the model.
9. **Write the eval tasks** in `evals/portals/<pack>.json`: a JSON list of tasks, each with `id`, `prompt` and `expect` (the grading criteria), and optionally `env`, `server_args` and `covers`. Together, the tasks' `covers` must include all four kinds:
   - `in_area`: an "in <area>" count on a reviewed place field;
   - `relative_date`: a relative date ("last month") on a reviewed time column;
   - `misleading_field`: a field that looks usable but is placeholder-heavy or sparse;
   - `not_published`: something the portal does not publish (an honest "not here").

   A `misleading_field` task's prompt must not name the column under test, nor the dataset it trips on. When the pack reviews more than one dataset, the tasks must span at least 2 of them.
10. **Declare `profiled`.** Keep `tier = "profiled"` in `portal.toml` through step 11.
11. **Run the checks**, in this order:
    1. `uv run pytest --run-integration -m integration tests/test_drift.py -k <portal id> --ignore=tests/test_curation_skill.py`, the drift run (live) for this portal's claims only, where `<portal id>` is the canonical id. It updates this portal's entries in `validation.json` and keeps every other entry. It never runs `tests/test_curation_skill.py`. Correct or remove every claim of this pack that does not pass, then rerun. Exit 5 ("no tests collected") means the pack has no asserted claim, or `<portal id>` is not the `id` in the pack's `portal.toml`. `-k` matches substrings of the test ids (`<portal id>:<claim id>`), so it also selects any other portal whose id contains `<portal id>`; those claims are another pack's (Rules).
    2. `uv run pytest -q --ignore=tests/test_curation_skill.py`, which includes `tests/test_packs.py`, `tests/test_tiers.py` and `tests/test_release_gate.py`, then `uv run prek run --all-files`. Both must pass, except that the release gate counts only this pack. Each gate failure line starts with its portal id (`<portal id>: <claim id>: ...`). Every line with this portal's id must be gone; lines with another portal's id go in the PR description. A rerun of this check after step 11.3 has started must not change the pack: run `uv run ruff check`, `uv run ruff format --check` and `uv run ty check` in place of `prek`, whose hooks rewrite files.
    3. Run `uv run python evals/run.py --portal <pack> <out>` 3 times, each with a new `<out>` under `.curation/`. Each run spends money: it launches one paid, headless agent session per task, so `--help` is the only safe probe. `evals/run.py` caps each session at $1 with `--max-budget-usd`. These are paid runs under `AGENTS.md`'s paid-run rule: an agent makes them only when asked, and a contributor running this path on their own request counts as asked. Grade each transcript against its task's `expect` as PASS, PARTIAL or FAIL. Treat a failure first as a knowledge gap (a missing or wrong claim) and fix the pack; only when the pack is right, report it as an engine defect. After any pack change, rerun step 11 from its first check: step 12 counts only the 3 eval runs made on the pack you submit.
12. **Promote to `curated` if it qualifies.** The conditions, all of which must hold:
    - a dataset is `reviewed` and has a guide, and the eval tasks' `covers` include all four kinds;
    - across the 3 eval runs of step 11, every task grades PASS in at least 2 runs and FAIL in at most 1.

    A person who curated the pack sets `tier = "curated"` in `portal.toml` only when they hold, and else keeps `profiled`. An agent that curated the pack keeps `profiled`: when the conditions hold, it says in the PR description that it proposes `curated` and gives the per-run grades, and only a reviewer other than that agent, after re-grading the eval answers, sets `curated`. After promoting, rerun `uv run pytest -q tests/test_tiers.py`; it must pass.
13. **Open a PR.** An agent commits on `curate/<pack>` and prints the PR title and description; it never pushes, and a human pushes the branch and opens the PR. Check that `git diff --name-only` against the base branch lists only the paths the Rules allow. The description must name the portal, the declared tier, the datasets reviewed, the drift outcomes, the eval grades of all 3 runs, and every claim of another pack that failed a check.
