# opendata-atlas: design

An agent-friendly MCP server for open-data portals across many places, starting with every registered public Socrata (Tyler Data & Insights) portal. It grows out of [`seattle-open-data`](https://github.com/briandconnelly/seattle-open-data), whose query engine, error envelope and contract carry over, and whose Seattle knowledge becomes the first curated portal.

The contract standard is the `agent-friendly-mcp` skill, cited by rule id (e.g. `[6.repair-object]`). Probed facts are in [upstream-facts.md](upstream-facts.md); the decision log is [decisions.md](decisions.md). Knowledge tooling (profiler, drift checks, contribution and curation, per-portal evals) is in [knowledge-tooling.md](knowledge-tooling.md). Where this document says "as in `seattle-open-data`", the authority is [`seattle-open-data`'s design at the fork revision](https://github.com/briandconnelly/seattle-open-data/blob/26c662858f4ef27bc5df0528e8233a80488e041e/docs/design.md) (`26c6628`; see Constraints).

Status: describes the current design as of 0.1.0 (released 2026-10-20). Calls marked *(Claude's call)* bind as written; the builder may change one by updating this design and adding a docs/decisions.md row (maintainer, 2026-10-17: adapt and log).

## Intent

`seattle-open-data` showed that a Socrata MCP server is worth having less for its query plumbing than for what it knows about the portal: which neighborhood column is half placeholders, which region layer predates redistricting, which timestamps are Pacific wall-clock time. That knowledge is what stops an agent from returning a confident wrong answer.

`opendata-atlas` keeps that bar and widens the reach:
1. **Reach:** an agent can work with any registered public Socrata portal, with honest generic behavior. Verified on milestone 0's 20 sample portals through the tools (milestone 2's compatibility suite, 2026-10-18, `docs/evidence/compat-2026-10-18/`). On 19 of them, search, describe, two query pages and the unknown-column check all passed. On data.oregon.gov, every step passed except page 2, which was not exercised because the three datasets tried each fit one page. Generic behavior on the other 223 registered portals remains a goal.
2. **Depth, grown dataset by dataset:** any place can be improved from "works" to "knows the traps" through a repeatable process that turns probes into checked, dated facts.
3. **Honesty about the difference:** every result says how much the server knows about the dataset and columns involved, not just the portal, so an agent can caveat appropriately.

## Goals

- One server, one install, any registered portal. Generic behavior is verified on milestone 0's 20 sample portals (19 with every step, data.oregon.gov with every step but page 2; `docs/evidence/compat-2026-10-18/`). On the other 223 registered portals it remains a goal.
- Never query the wrong place silently.
- Per-portal knowledge stored as data with typed evidence, not code, so adding or correcting a fact is a small reviewable change.
- Every checkable fact is re-checked live; drift is detected before release and stale knowledge degrades at runtime instead of staying authoritative.
- A path from "new portal" to "curated dataset" that a contributor (human or agent) can follow without the maintainer.
- Seattle at parity: everything `seattle-open-data` does for Seattle, `opendata-atlas` does with `portal: "seattle"`, and its eval suite passes at the same targets. **Parity means** *(Claude's call)*: no warning, guide fact, or repair Seattle emits at the fork revision is lost; the only permitted output differences are those this design specifies (for example the `portal` argument, `source.portal`, `source.now_weekday`, `knowledge`, `knowledge_notice`, `candidate_placeholders`, stale-claim degradation, describe column paging, new error codes, portal-bound cursors, and repairs that carry `portal`). Milestone 1 ports `seattle-open-data`'s tests as the regression oracle and edits only those named differences.

## Non-goals (v1)

- Non-Socrata platforms (ArcGIS Hub, CKAN, OpenDataSoft). The portal record carries `platform` so this stays possible; no adapter is built.
- Cross-portal joins, comparisons, or dataset search in one call. Deferred until evals show agents need it.
- Writes, private datasets, server-side bulk export, geocoding, forecasts (as in `seattle-open-data`).
- Retiring `seattle-open-data`. It stays as is; its future is the maintainer's decision.
- Profiling or curating many portals at launch. Launch proves the process on two (see Launch scope).

## Anti-goals (failure even if it works)

- An omitted or defaulted portal sending "Chicago crimes" to Seattle.
- A dataset or column with no reviewed knowledge reading with curated confidence because its portal is curated.
- Curated facts that go stale and stay authoritative.
- One portal's cached schema, facts, or cursor applied to another portal's dataset with the same id.
- A `tools/list` that grows with the number of portals (no portal enum in schemas).
- A knowledge format only the maintainer can edit safely, or one whose checks pass vacuously.

## Constraints

- Inherits the `seattle-open-data` toolchain and rules: uv, ruff, ty, prek, FastMCP 4 on MCP SDK v2, stdio only, MCP 2026-07-28 with 2025-11-25 compatibility, 24 KiB `tools/list` and per-result budgets, one error envelope, every repair a literal call validated by test.
- **Name:** `opendata-atlas` (maintainer, 2026-10-17), after the working name "citydata" proved taken on PyPI. No exact or separator-insensitive collision on PyPI's index as of 2026-10-17; registration is the only real test. The maintainer reserves the name on PyPI; this is not a builder task. Python package `opendata_atlas`, tool prefix `atlas_`, URI scheme `opendata-atlas://`, error class `AtlasError`, instructions sentinel `END OPENDATA ATLAS INSTRUCTIONS`. *(Claude's call: `atlas_` over `opendata_atlas_` to keep tool names short; the server name `opendata-atlas` disambiguates it in hosts.)* The repo is assumed to be hosted at `github.com/briandconnelly/opendata-atlas`, like the maintainer's other servers, with network-enabled CI for the drift job and release gate. On 2026-10-20 the name was not held ahead of the release: its first upload creates the project (decisions row "Release decisions for 0.1.0").
- New package, new repo (`~/projects/opendata-atlas`).
- **Versioning:** a new server, not a `seattle-open-data` release [9.rename]. Versions start at `0.1.0`. `CHANGELOG.md` says the server was forked from `seattle-open-data` 0.2.0 at `26c6628`, with tools renamed from `seattle_data_*` to `atlas_*`, and keeps the parent's releases as history under `## [seattle-open-data history]`, which the release workflow neither reads as a version nor includes in release notes ([releasing.md](releasing.md)). The deprecation window and the deferred capability fingerprint are as in `seattle-open-data` [9.deprecation-semantics] [9.fingerprint]. *(Milestone 1 standards review, 2026-10-17.)*
- **Before release,** every `port`-labeled fix from `seattle-open-data` is ported or closed with a reason. Milestone 5 (2026-10-19): no seattle-open-data commit follows the fork; nothing to port (decisions row "Port comparison").
- **Fork, not dependency.** The engine is copied from `seattle-open-data`, so neither project can break the other. The fork revision is recorded in `docs/decisions/log-2026-10.md`; a fix landing in either repo gets an issue in the other, labeled `port`, until the maintainer decides `seattle-open-data`'s future. *(Claude's call; the maintainer asked for a new package "to be safe".)*

## Portal model

### Identity

A **portal** is one Socrata site.

| field | example | notes |
| --- | --- | --- |
| `id` | `data.seattle.gov` | canonical, **immutable**: the public host at first registration. Never changes, even if the host or tier does |
| `aliases` | `["seattle"]` | short slugs (`^[a-z0-9][a-z0-9-]{1,39}$`), added on promotion or by contribution; globally unique, checked when the registry is built |
| `public_host` | `data.seattle.gov` | current host for `/resource` and `/api/views` requests and for URLs shown to agents; may change |
| `catalog_domain` | `cos-data.seattle.gov` | the name the Discovery API indexes it under (the `domains=` value); also the host catalog links use, rewritten to `public_host`. Never compared against results |
| `result_domain` | `data.seattle.gov` | the `metadata.domain` search results carry; `search_context` when the portal's `catalog_query` has one, else `domains`. Search drops results from other domains |
| `catalog_query` | `{domains: cos-data.seattle.gov, search_context: data.seattle.gov}` | the exact Discovery parameters that select the portal |
| `catalog_region` | `us` | `us` (`api.us.socrata.com`) or `eu` (`api.eu.socrata.com`) |
| `name` | `City of Seattle` | |
| `place_names` | `["Seattle", "Seattle, WA"]` | free text, for `find_portals` only |
| `jurisdiction` | `{level: city, country: US, region: WA}` | `level`: `city | county | region | state | national | other` |
| `timezone` | `America/Los_Angeles` or `null` | the calendar zone for "last month" questions. `null` when the jurisdiction spans zones or it has not been probed. A profiled portal may have `timezone: null` |
| `platform` | `socrata` | |
| `tier` | `curated` | declared; see Knowledge levels |
| `status` | `active` | `active | retired`; `retired` only from registry evidence (see Registry) |

The `portal` tool argument accepts a canonical id or an alias, case-insensitively, pattern `^[A-Za-z0-9][A-Za-z0-9.-]{1,99}$`. It does **not** accept place names ("Seattle WA"); those go to `atlas_find_portals`, and a value that fails the pattern is `invalid_argument` with the `find_portal` repair. *(Claude's call: one resolution path for names keeps ambiguity out of every data tool.)*

### Knowledge levels

Knowledge is reported per **dataset** and per **column**, not per portal.

| level | meaning |
| --- | --- |
| `none` | nothing recorded. Engine behavior only |
| `profiled` | the profiler recorded observations (fill rates, candidate placeholders, timezone tests); nobody reviewed them |
| `reviewed` | a contributor reviewed the observations and recorded interpretations (reliability, placeholder declarations, timezone, unit of observation) |

**When a dataset is `reviewed`** *(Claude's call)*: it has a reviewed unit-of-observation claim, and a reviewed claim for every place field it exposes and for its primary time column. A dataset with some reviewed claims short of that is `profiled` (if profiled) or `none`, and its reviewed claims still apply column by column. A claim is reviewed when it carries an interpretation, or, for `placeholder_share`, a `placeholders` declaration with `reviewed_by` and `reviewed_at`; any other claim is a profiler observation. The **primary time column** is the one describe reports in `data_coverage`: every time-typed column with a reviewed timezone claim, else the first time-typed column. A dataset with no time-typed column needs no time claim. *(Claude's call, milestone 2.)*

**Which columns matter for notices:** only *knowledge-bearing* columns, meaning place fields (reviewed or computed-region) and time-typed columns. A text or number column with no claim is not "unknown"; it simply has no place or time semantics to vouch for. So `knowledge_notice` fires when the dataset is not `reviewed`, or when a referenced knowledge-bearing column has no reviewed claim, or a stale one. On a reviewed Seattle dataset, a query on `offense_parent_group` carries no notice; a query on an unreviewed secondary time column does.

**Who can review** (maintainer, 2026-10-17): an agent's review is sufficient to make a claim, and so a dataset, `reviewed`, and a pack PR reviewed by an agent can promote a portal to `curated` once merged. Only the maintainer merges, or an agent the maintainer told in the current session to merge that PR (`AGENTS.md`, Rules). That reviewer is never the agent that curated the pack: a curating agent declares at most `profiled` and proposes `curated` in its PR, and the promotion follows a re-grade of its eval answers by another reviewer (ruling 64). Every reviewed claim records `reviewed_by` (an agent or person identifier) so the history shows who vouched for it; it does not change how the claim is reported.

A portal's **tier** (`generic | profiled | curated`) is a summary label for discovery and contribution. A portal's tier is declared in `portal.toml` (`tier = "generic" | "profiled" | "curated"`) and must satisfy its conditions: `curated` requires identity verified, at least one `reviewed` dataset with a guide, the live smoke test passing, and the portal's eval tasks passing (see [knowledge-tooling.md](knowledge-tooling.md), Per-portal eval tasks). The **live smoke test** is the portal's scoped drift run (`tests/test_drift.py -k <portal id> --ignore=tests/test_curation_skill.py`) plus its compatibility case (`tests/test_compat_live.py::test_portal_compat[<portal id>]`, parametrized over milestone 0's sample and every portal with a pack, #36; contribution path step 11.1), each reported `PASSED` (an `XFAIL`, `XPASS` or `SKIPPED` is not a pass, and a data limitation or drift failure stops the promotion), with the saved compatibility outcome showing search, describe, query page 1, page 2 and the forced error each `ok` (decisions row "Live smoke test for promotion"; ruling 83). Tier never stands in for dataset knowledge: an unreviewed dataset on `curated` Seattle reports `none`.

`tests/test_tiers.py` checks the conditions decidable from pack contents (`portals/tiers.py`, `tier_violations`): `profiled` needs at least one claim; `curated` needs a dataset `reviewed` by `pack_levels` that has a guide (`pack_levels` maps each dataset's own `:@computed_region_*` place-field claims to their region layers by Socrata's column naming, and counts every region layer in the pack only for a dataset with no such claim; final review M-1, ruling 73. It can still read higher than describe for a dataset with claims on only some of its computed-region columns, or whose schema has a column on a layer the pack never claims; describe governs), and `evals/portals/<pack dir>.json` whose tasks' `covers` include all four kinds. It also checks that every registry entry without a pack is `generic`. Identity verification, the smoke test and the portal's evals are live, so ordinary PR CI, which is offline (integration tests skip without `--run-integration`), never runs them: whoever promotes the portal runs them as part of the promotion (`CONTRIBUTING-portals.md` steps 2 and 11; the evals are paid, opt-in runs) and records their outcomes in the PR. Levels come from `pack_levels` at the suite's pinned clock (`tests/conftest.py`), so the test never sees a review go stale. Staleness acts at runtime, where freshness degrades stale claims, and a drift run gives each claim it checks a new `checked_at` (ruling 56).

### Knowledge packs

Each portal with any recorded knowledge has a directory:

```
src/opendata_atlas/portals/<alias-or-id>/
  portal.toml        # identity overrides (name, aliases, timezone, ...)
  regions.toml       # portal-level claims, such as computed-region layers any dataset may use
  facts/<dataset_id>.toml
  guides.py          # GUIDES: a tuple of `core.guides.Guide`, each with `observed_at`
```

Portals with no pack exist only in the generated `src/opendata_atlas/portals/registry.json`.

#### Fact model

A fact is a **claim** about a scope, supported by **evidence**, with **assertions** that decide whether the evidence still supports it. Measurements and interpretations are separate: the profiler writes observations; only a reviewer writes interpretations.

```toml
[[claim]]
id = "crime-neighborhood-pre2017-placeholder"
scope = {dataset = "tazs-3rd5", column = "neighborhood", time = {column = "offense_date", until = "2016-12-31"}}
kind = "placeholder_share"
interpretation = {reliability = "partial", reason = "Placeholder ('-') for nearly all offenses before 2017; 1-4% missing since. Do not use for 2008-2016."}
placeholders = ["-", "UNKNOWN", "OOJ", "FK ERROR"]   # reviewed declaration for this column
reviewed_by = "claude"
reviewed_at = 2026-10-16

[[claim.evidence]]
kind = "soql_probe"
query = "SELECT date_extract_y(offense_date) AS y, sum(case(neighborhood = '-', 1, true, 0)) AS ph, count(*) AS n GROUP BY y"
observed_at = 2026-10-16
observation = "ph/n 0.98-1.00 for 2008-2016; 0.01-0.04 for 2017-2026"

[[claim.assertion]]
checker = "share_by_group"
params = {group = "y", numerator = "ph", denominator = "n", where = "y <= 2016", min = 0.9, min_groups = 9}

[[claim.assertion]]
checker = "share_by_group"
params = {group = "y", numerator = "ph", denominator = "n", where = "y >= 2017", max = 0.05, min_groups = 9}
```

- **Evidence kinds:** `soql_probe` (a query on the dataset), `metadata_probe` (an `/api/views` or catalog field, e.g. a region layer's `rowsUpdatedAt`), `document` (a URL and quoted passage, e.g. a publisher page stating the unit of observation), `manual_observation` (dated prose, for what no probe can show). A claim may have assertions only if it has at least one `soql_probe` or `metadata_probe` evidence.
- **Checkers** are named Python functions in `src/opendata_atlas/portals/checkers.py`. A checker returns `passed | contradicted | inconclusive`. Missing groups, an empty result, or fewer than `min_groups` is `inconclusive`, never `passed`. Each checker's `params` is a Pydantic model that rejects unknown keys and is validated at load; a bad `params` fails with a `PackError` naming the checker. Row values arrive as strings. A value that will not parse as a number makes that row missing. A count that will not parse where it decides the outcome makes the result `inconclusive`. SoQL checkers read the rows of a `soql_probe`; metadata checkers read the JSON object of a `metadata_probe`. The catalog:
  - `share_by_group` (SoQL): `group` (omitted: each row is its own group), `numerator`, `denominator`, `where` (one comparison such as `y <= 2016`, applied to the result rows, never sent upstream), `min` and/or `max` (at least one), `min_groups` (default 1). A share outside `[min, max]` is `contradicted`, even when fewer than `min_groups` groups were counted: one group out of bounds decides. With every counted group in bounds, fewer than `min_groups` is `inconclusive`.
  - `value_present` (SoQL): `column`, `value`, optional `count` and `min_count` (default 1, at least 1). No matching row, or a matching row with a count below `min_count`, is `contradicted`; a matching row whose count will not parse is `inconclusive`.
  - `value_absent` (SoQL): `column`, `value`. A matching row is `contradicted`.
  - `dst_gap` (SoQL): hourly counts in `hour` (default `h`) and `count` (default `n`). If either neighbor of `gap_hour` (default 2) has fewer than `min_neighbor_rows` (default 1) rows, the result is `inconclusive`. Otherwise `gap_hour` with at most `max_gap_rows` (default 0) rows is `passed`, and with more is `contradicted`. A `gap_hour` count that will not parse is `inconclusive`.
  - `diurnal_peak` (SoQL): the hour with the largest count (ties: the earliest) lies in `peak_from`..`peak_to` or the result is `contradicted`; fewer than `min_hours` (default 20, 1-24) hours or `min_rows` (default 100) rows is `inconclusive`.
  - `metadata_equals` (metadata): dotted `field` equals `value`. A missing `field` is `inconclusive`.
  - `metadata_before` (metadata): `field` is before `before`. The field is epoch seconds (an integer, or a digit string of 9 or more digits) or an ISO date or datetime; an offset-aware datetime is compared in UTC. A missing `field`, or one that parses as neither, is `inconclusive`.
  - Either metadata checker given anything but a JSON object is `inconclusive`.
- **Assertion `probe`:** an assertion's `probe` (default 0) indexes the claim's probe evidence (its `soql_probe` and `metadata_probe` entries, in evidence order), not the whole `evidence` list. Load fails if the index is out of range or the probe's kind is not the one the checker reads. A `metadata_probe` `path` starts with `/api/` and is read on the portal's public host.
- A claim with no assertion (only `document` or `manual_observation` evidence) is valid, but is reported with `validation: "unchecked"` and is never re-validated automatically.
- **Served evidence:** where a response shows a claim's evidence (a column timezone's `evidence`), it is the first `manual_observation` note, else the first probe's `observation`, else the first `document` quote (`describe.served_evidence`). A reviewer's note summarizes the claim, so probe evidence added later does not change what is served. *(Claude's call.)*
- Examples covering each kind ship in `docs/pack-examples/`: placeholder share (above), region-layer vintage (`metadata_before` on the layer's `rowsUpdatedAt` plus a `document`), column timezone (`dst_gap` plus `diurnal_peak`), unit of observation (`document` only), place field (a single-row `share_by_group`), and padded values (`value_present`). `tests/test_packs.py` validates each and requires that together they cover every claim kind.
- **`padded_values`** is a claim kind for a column whose values carry leading or trailing whitespace, so an unpadded equality matches nothing. It needs no interpretation.
- The schema is a Pydantic model; `tests/test_packs.py` validates every pack and every checker's params. A reviewed claim the engine cannot serve fails at load with a `PackError` naming the file and field, not at first describe: `place_field` and `region_layer` need an `interpretation.kind` from the engine's place kinds and an `interpretation.reliability`, `region_layer` also a `label_column`, `column_timezone` a `timezone`, and `unit_of_observation` an `interpretation.unit`.

#### Validation state and freshness

Provenance (when evidence was observed and by whom) is separate from validation state (the last time the assertions ran and what they said).

- **`validation.json`** (`src/opendata_atlas/portals/validation.json`) *(Claude's call on the format)*:
  - The drift run generates it, and each release ships it.
  - `portals` maps a canonical portal id to its claim ids, and each claim id to `checked_at` (the run's UTC date), `outcome` (`passed | contradicted | inconclusive`), `previous_outcome` (the outcome before this one; `null` on a claim's first run) and `assertion_digest` (`validation.assertion_digest`: 12 hex digits of sha256 over the claim's scope and, per assertion, its checker, params and probe request, as checked; final review M-3).
  - It is written with sorted keys, one-space indent and a trailing newline.
  - A missing file reads as empty. A missing shipped file is also logged as a warning, because without it no claim can go stale; `scripts/build_bundle.py` requires the file, and `tests/test_manifest.py` checks that the wheel carries it (final review M-2). Malformed JSON or a schema error fails with a `PackError` naming the file.
- **Merge and prune:** each drift session merges its results into the previous file. A checked claim gets `checked_at` today and its new `outcome`, and its old outcome moves to `previous_outcome`. In a portal the session has results for, an entry it did not check is kept while the claim is still asserted in a pack, so a partial run loses nothing, and once the claim is removed or renamed the entry is dropped. A portal the session has no result for keeps every entry unchanged, orphans included, so a curator's scoped run (`-k <portal id>`) never edits another pack's entries (final review M-6).
- A claim's `outcome` is `contradicted` if any assertion is, else `inconclusive` if any is, else `passed`. A probe that fails upstream (any `AtlasError`: a 5xx, a timeout, a SoQL error) makes that probe's assertions `inconclusive`, with the error code as the detail, so a failed probe never passes.
- **Release gate:** a release fails CI if any claim is `contradicted`, or `inconclusive` twice running, or was last checked against a different assertion (its entry's `assertion_digest` differs from the pack's). The fix is to re-probe and correct or remove the claim; for a changed assertion, run the drift run on it.
- **Runtime freshness:** a claim is `stale` when its `checked_at` is older than 180 days by the server's clock. *(Claude's call on 180.)* The server degrades stale claims asymmetrically:
  - a stale `ok` reliability, column timezone, or reviewed placeholder declaration is reported as `unknown`, with `validation: "stale"`;
  - a stale `partial` or `unreliable` verdict is kept, with `validation: "stale"`, because withdrawing a warning is the dangerous direction.
- **The rule, exactly** (`portals/freshness.py`):
  - A claim's `validation` is `unchecked` when it has no assertion or `validation.json` has no entry for it. It is `stale` when `today − checked_at` exceeds 180 days (180 is fresh, 181 stale; a `checked_at` after today is fresh). Otherwise it is the entry's `outcome`.
  - "The server's clock" is `freshness.today()`, the UTC date, read once per call.
  - A `validation` over several claims is the worst of theirs, in the order `contradicted`, `stale`, `inconclusive`, `unchecked`, `passed`; with no claims it is `unchecked`.
- **What degrades** (a *degraded* claim): a stale claim whose verdict vouches for the data. That is a `place_field` or `region_layer` with reliability `ok`, a `column_timezone`, or a `placeholder_share` with a reviewed declaration. When levels are computed, a degraded claim counts as neither reviewed nor an observation, so staleness never raises a level: a gap left only by a degraded claim gives the level the dataset or column would have without that claim (a column covered only by degraded claims reads `none`). It also stops making its column the primary time column. *(Controller ruling 42.)*
  - A degraded place field reports `reliability: "unknown"`, with the reason "Reviewed as ok, but its checks last ran on <checked_at>, over 180 days ago; treat its coverage as unknown." `unknown` is not `ok`, so `coverage_warnings` fire on it. *(Claude's call: a fourth reliability, not `partial`, so the output says why.)*
  - A degraded column timezone is omitted from `time_semantics`, with its `evidence`.
  - A degraded placeholder declaration is a declaration on a stale reviewed claim: a `placeholder_share`'s, or a `place_field`'s `placeholders` whatever its reliability. Only the declaration degrades: a `place_field` claim is itself degraded only when its reliability is `ok`, as above. A degraded declaration no longer removes its values from `values`. They are listed in `candidate_placeholders`, and the field omits `assigned_fraction`, so it never reads more complete than reviewed. `placeholder_values` keeps only the values a fresh declaration on the column removes (absent when there is none); the null count stays in `null_rows`. *(Claude's call.)*
- **Where `validation` appears:** `knowledge.validation`, always: for a column, it combines the claims covering it; for a dataset, its claims and its computed-region layers' claims. On `place_fields[]`, `coverage_warnings[]` and `time_semantics[]` entries, `validation` is set only when it is `"stale"`, and their schema publishes only that value. A fresh Seattle result gains no field. *(Claude's call.)*
- Scheduled drift checks keep the maintained branch honest; they cannot change an installed release. The runtime freshness rule is what protects old installs.

### Place fields

- **Reliability** is `ok`, `partial`, `unreliable`, or `unknown`. Claims record only the first three; the server reports `unknown` for a reviewed `ok` whose checks are stale (see Validation state and freshness).
- **Reviewed** text place fields come from claims. **Computed-region** columns are detected structurally on every portal; their layer label and kind come from claims when present (a reviewed `place_field` claim on the column sets its `kind`, `reliability` and `reason` over the layer's `region_layer` claim, in the column's one entry; it never adds a second entry, ruling 62), otherwise `kind: "other"` and `reliability: "partial"` with reason "unreviewed region layer", exactly as in `seattle-open-data` (`core/describe.py:264`), so `coverage_warnings` keep firing on them. *(Claude's call: the conservative default; Seattle parity depends on it.)*
- The server never certifies a text column as a place field from its name. *(Claude's call, kept from v1: a name heuristic invites the false confidence this project exists to prevent.)*
- **Exploratory path** for datasets with no reviewed place field. The head rule permits an agent to filter on a text column it has itself inspected: describe the schema, run a `group_by` on the candidate column, read its values and missingness, filter only on values that grouping returned, and say in the answer that the field's meaning and completeness are unverified. Query results on such a dataset carry `knowledge_notice` (see Tools). When a query's `where` filters on a text column or its `group_by` groups one, and no place field of the dataset is backed by a reviewed claim the freshness rule does not degrade (see What degrades), the notice fires even on a `reviewed` dataset. It adds a sentence naming those columns as not reviewed place fields, except a column the notice already names as a place field with no reviewed claim, which is named once. A `group_by` inspection names its columns too (ruling 69, superseding Task 6's choice): grouping a candidate column to read its values is the exploratory path, whose caveat is required.
- **Placeholders.** The shared cross-portal vocabulary (Seattle's list: `-`, `UNKNOWN`, `NULL`, `OOJ`, `FK ERROR`, `X`, `0`, empty) is used only to flag **candidate** placeholders in `full` describe output (`candidate_placeholders[]` with row counts). Values are excluded from `values[]` and from `assigned_fraction` only when a reviewed claim declares them placeholders for that column and the claim is not stale (see Validation state and freshness). Both claim kinds declare placeholders the same way: a reviewed `placeholder_share` claim's `placeholders`, and a reviewed `place_field` claim's `placeholders` (as in `docs/pack-examples/place_field.toml`). *(Engine gap 2, milestone 6.)* Declarations apply only to a text place field; a computed-region column ignores every declaration on it (`_declared_placeholders` in `core/describe.py`). Raw null and non-null counts are reported separately from `assigned_fraction`. The Seattle pack migrates `PLACEHOLDER_VALUES` into per-column declarations for the columns it applies to today, so Seattle output keeps parity.
- **Kinds:** `neighborhood | precinct | sector | beat | zip | council_district | census_tract | ward | community_area | borough | community_district | county | police_district | school_district | other`, plus an optional free-text `kind_label` on every place field. After 1.0 the nested enum is frozen; new kinds use `other` plus `kind_label` [9.additive-direction].

### Time

Two separate questions, with separate sources:
1. **Calendar zone** (what "last month" means): the portal's `timezone`. `now_local` is that zone's wall-clock time; when the portal has no single known zone it is omitted (not `null`) and `now_local_reason` (`multi_zone | unknown`) says why. `now_weekday` is today's weekday in the portal's zone (`Monday` … `Sunday`, fixed English names, never the server's locale), present exactly when `now_local` is. The capability summary's `## Rules` binds the agent: "Name a weekday only from the data (`date_extract_dow` on the date column, 0 = Sunday) or, for today, from `source.now_weekday`; never work a weekday out yourself." The milestone 4 slips were weekdays of past data dates (3 of 6 task-03 answers), so the rule covers data dates as well as today (ruling 92); the `dates` topic points to both sources.
2. **Column semantics** (what a stored timestamp means): per-column timezone claims only. No claim, or a stale one, means the timezone is unknown: the `time_semantics` entry omits `timezone` and `evidence` (a stale claim's entry carries `validation: "stale"`).

Head rule: when either is unknown and the question uses a relative date, the agent states the date range it used, in absolute dates, or asks the user; it never silently assumes a zone.

## Engine isolation

Every engine call takes an immutable `PortalContext` (canonical id, current identity record, loaded pack, validation state). Nothing in the engine reads module-level portal constants.
- Schema cache and its invalidation: keyed by (portal id, dataset id). Concurrent fetches of one schema share one upstream request; a failed or cancelled fetch is not shared, so each waiter fetches under its own deadline (#37).
- The registry reads each pack's `portal.toml` identity only (`loader.load_identity`); a pack's claims and guides load on its first resolution (#38).
- Region-label cache: keyed by (portal id, layer id, feature id).
- Fact and guide lookups: through the portal's `PortalContext`.
- Per-host concurrency limits: per `public_host`.
- Cursors: bind the canonical portal id.
- A regression test uses the same dataset id on two mocked portals with different schemas and facts, and checks that neither portal's projection, place fields, warnings, or cursor leaks to the other.

## Tools

Five tools. The four `seattle-open-data` tools keep their inputs, outputs, deadlines and paging except where this section specifies a change; one is new.

**`portal` (required on every data tool):** no default and no enum. Every result's `source` echoes the resolved portal:

```json
"source": {
  "portal": {"id": "data.seattle.gov", "alias": "seattle", "name": "City of Seattle", "tier": "curated", "timezone": "America/Los_Angeles"},
  "now_local": "2026-10-16T14:02:11",
  "now_weekday": "Friday",
  "...": "..."
}
```

`source.portal` is never trimmed by the byte-budget packer, and nor are `coverage_warnings` or `knowledge_notice`.

1. **`atlas_find_portals`** (new). Resolve a place to portal ids.
   - Inputs: `query?` (place name, e.g. "Chicago"), `level?`, `country?`, `tier?`, `page_size?` (1–50, default 10), `cursor?`. With no arguments, pages through every active, enabled portal: curated, then profiled, then generic (`has_more` is true while more follow), so the `find_portal` repair of `portal_not_found` lists every portal rather than only the curated one (ruling 32); any filter without a query also searches every tier, ordered tier first.
   - Returns candidates with identity, tier, and `match` (`alias | name | place_name | host`). Never picks one: when several portals match a place (for example a city and its county), every one is a candidate, distinguished by `jurisdiction.level`.
   - Ordering: match strength, then tier, then canonical id. Deterministic for a given registry version.
   - `openWorldHint: false`: reads only the shipped registry.
2. **`atlas_search_datasets`**: as in `seattle-open-data`, plus `portal`. Catalog requests use the portal's `catalog_region`, `catalog_query` and `catalog_domain`, and any result whose `metadata.domain` is not the portal's `result_domain` is dropped and counted in `foreign_results_dropped`. The Discovery API counts and pages at most 10,000 results per query (`CATALOG_RESULT_CAP`), so a page never asks past it, and the last page of a listing that reached it has `truncated: true` with a `truncation_hint` to narrow by `query` or `category` (#24). `external_matches` and `suggestion` carry over; the suggestion's literal call includes `portal`.
3. **`atlas_describe_dataset`**: as in `seattle-open-data`, plus `portal`, plus:
   - `knowledge`: `{level, validation}` for the dataset, and per column in `columns[]` when any claim covers it.
   - `unit_of_observation`: `{unit, reason?}`, what one row is (Fire 911: `dispatch`, with a reason saying most rows are medical). It is set from the dataset's reviewed `unit_of_observation` claim (a filter view's from its parent's) and omitted when there is none. A stale claim is still served: the kind does not degrade. *(Claude's call: describe, not query, carries it, so an agent learns what a count counts before it queries. Eval 03's agents call describe `full` before querying, and a per-page query field would spend budget on every page.)*
   - `place_fields` per Place fields above; `candidate_placeholders[]` in `full`. A place field or `time_semantics` entry whose claim is stale carries `validation: "stale"` (see Validation state and freshness).
   - **Wide schemas:** `columns` is paged (`column_cursor`) only when the full result would exceed the result budget.
     - `columns_total` (matching `column_query`) is always present, `has_more_columns` says whether a page follows, and `next_column_cursor` is omitted on the last page.
     - The first page lists every column when they all fit. Otherwise a page holds at most 100 columns in `summary` and 25 in `full`, trimmed by the byte packer until the page fits.
     - The budget is measured on `structuredContent` alone (`core/budget.payload_size`), not on the wire copy that doubles it: see [decisions/log-2026-10.md](decisions/log-2026-10.md) (ruling 19).
     - `place_fields`, `geo_columns`, `time_semantics`, `knowledge` and `unit_of_observation` are never paged and are repeated on every page, so any page stands alone. `sample_rows` is first-page only, because a continuation may not send it.
     - If those sections (with any `sample_rows`) alone exceed the budget, or a single column would not fit beside them, the call fails with `describe_too_large`, `row_too_large`'s describe twin. Its repair shrinks the result and keeps every other argument of the failed call: `detail: "full"` becomes `summary` (`use_summary`); a summary call with `sample_rows > 0` becomes `sample_rows: 0` (`drop_samples`); a summary call without samples has no repair, and the error says to query the dataset directly, selecting the columns needed. `column_query` narrowing is not offered (ruling 20).
     - The `columns` cursor binds a fingerprint of the matching column names; a schema that changed between pages is `cursor_expired`.
     - *Context:* recorded Seattle describes are unchanged, because their columns all fit on the first page. The caps are final (milestone 2 Task 10): on the 300-column test view a 100-column summary page is about 9.6 KB and a 25-column `full` page about 6.3 KB of `structuredContent`, so the caps, not bytes, bind on typical schemas and the packer trims only wide descriptions and stats. Dropping samples leaves the question unchanged, because samples are illustrative. `column_query` changes only `columns`, so it cannot shrink the unpaged sections.
4. **`atlas_query_dataset`**: as in `seattle-open-data`, plus `portal`. The scans behind `coverage_warnings`, `knowledge_notice` and hints read names case-insensitively, spelled as the schema spells them, and skip string literals in single or double quotes, as the column pre-check does (#20); a hint is never built from a double-quoted literal. SoQL the engine writes itself (the default projection, `near`'s `within_circle`, describe's and the profiler's probes) backtick-quotes a field name that is a SoQL keyword or not a plain lowercase identifier (`core/soql.identifier`, #18); caller-written clauses are sent as written. `coverage_warnings` fire on `partial`, `unreliable` and `unknown` fields, stale or not; a warning on a stale claim carries `validation: "stale"`. A top-level `knowledge_notice` (`{level, message}`) is emitted once per result when the queried dataset's knowledge is not `reviewed`, or any knowledge-bearing column the agent referenced has no reviewed claim, or a stale one (see Knowledge levels), regardless of portal tier. It also fires, with one added sentence, when the `where` clause (clauses mode: `where` only, not `near` or the paging predicate; raw SoQL: the WHERE clause) or `group_by` (raw SoQL: GROUP BY; a name that select declares as an alias reads the columns its select expression reads, ruling 70) reads a text column while no place field of the dataset has a reviewed claim the freshness rule does not degrade (ruling 69).
   - **`hints`** (clauses mode, first page only): a list of repairs, each a literal call. A hint is emitted when the page matched nothing. That means no rows, or, without `group_by`, the single row where a `count(*)` select item is `0` (ruling 48). That item is read by its alias, or, unaliased, only when it is the sole select item. Any other single zero or null row, such as a zero `sum`, a `count(col)` of nulls or a matched row, did match. It is emitted for each `<name> = '<literal>'` in `where` whose name is a text column. Equality text inside a string literal does not count. At most one hint per column and at most 3 in all.
   - No hint is emitted, failing open, when:
     - the equality may be negated: a `NOT` before it that is not part of `IS NOT`, `NOT IN`, `NOT LIKE`, `NOT ILIKE`, `NOT BETWEEN` or `NOT NULL`;
     - `where` reads an alias declared in `select`, which the repair's `select` would not declare;
     - the repair's clause arguments would exceed the 4,096-byte clause cap.
   - Describe's coverage probe is one `min`/`max` request per coverage column, run beside the count and the sample (#39: kept, see [decisions/log-2026-10.md](decisions/log-2026-10.md)).
   - `alternative` echoes at most 80 characters of the literal. Trailing hints are dropped if the page would exceed the result budget.
   - Each hint has `next_step: "inspect_text_values"` (its symbolic code) and calls `atlas_query_dataset` with `select [col, "count(*) AS n"]`, `group_by [col]` and `order_by ["n DESC"]`. Its `where` is the original with only that match replaced by `upper(col) like '%LITERAL%'`: the literal is trimmed and upper-cased, doubled quotes are kept, and every other filter stays. `near` and `search_text` are carried over when set.
   - The column is the repair's `group_by[0]`. `alternative` is the message: "No rows matched `<col>` = '<literal>'; its values may be padded or differ in case, so filter on a value this grouping returns."
   - `hints` is never trimmed by the packer. *(Claude's call, milestone 3 Task 7; shape by ruling 47. The hint is an inspection that keeps every other filter, so following it does not change the question. LA's padded `area_name` made `area_name = 'Hollywood'` a silent zero.)*
5. **`atlas_get_reference`**: as in `seattle-open-data`, plus:
   - topic `portals` with `item_id` = a portal id or alias: identity, tier, knowledge summary (datasets by level), and guide index for that portal; `source.portal` names it. Without `item_id`, the curated and profiled index (active and enabled portals); `source` names no portal. The index pages like every entry list (below). *(Claude's call, milestone 2 Task 11; paging, milestone 3 Task 9.)* The knowledge summary's levels come from the pack's claims alone, without the live schema: a pack's place fields are its `place_field` claims, computed-region columns are not seen, and a dataset with no timezone claim is never `reviewed` there. Describe's `knowledge` is the level the server reports, and can differ.
   - topic `guides` requires `portal`; `item_id` names the guide. Every other topic rejects `portal` (topic `portals` takes its portal in `item_id`).
   - topic `contributing` (title "Contributing portal knowledge"): `CONTRIBUTING-portals.md`, served from its packaged copy: tier, knowledge-level and validation definitions, and the contribution path (see Contribution path).
   - The index lists only readable URIs: it has no `guides` entry, and each `portals` item carries its portal's guide index.
   - An invalid combination fails with `invalid_argument` and a literal repair (`atlas_get_reference({})`, the index).
   - Entry lists (the index, topic `portals` without `item_id`, a guides index, and the soql and errors indexes) are packed with whole entries to the result budget, measured by `wire_size` (ruling 72). The first page lists every entry when they all fit, so Seattle's 7-guide index is one page. `has_more` is present whenever `entries` is, and `next_cursor` only when more entries follow. A body (an item, `capabilities`, `contributing`) is never paged. Resources take no cursor, so a resource lists every entry. *(Claude's call, milestone 3 Task 9: the per-result budget binds tool results.)* The six static resources (`capabilities`, `contributing` and the four indexes) declare `size` in `resources/list`: the UTF-8 byte length of what `resources/read` returns, computed per listing so an allowlist changes it. Templates declare none. Lifecycle `_meta` and `$schema` stay out of `tools/list` for want of bytes ([decisions/log-2026-10.md](decisions/log-2026-10.md)).

### Continuation

Per tool, as in `seattle-open-data`'s single continuation statement, with portal binding:
- **query:** continuation repeats `portal` and `dataset_id`; both must match the cursor (compared after alias resolution).
- **search:** continuation repeats `portal`; the cursor binds `query`, `asset_scope` and `category`.
- **find_portals:** no `portal`; the cursor binds the filters and the registry version, and a registry change between pages fails with `cursor_expired`.
- **reference:** `cursor` repeats `topic` and, for topic `guides`, `portal`. The cursor binds the topic, the guides portal and a fingerprint of the entry ids. The topic is checked before the portal: an omitted or different `topic` is `invalid_cursor` with `details.field: "topic"`, naming the cursor's topic, and a different guides portal is `invalid_cursor` with `details.field: "portal"`, naming the cursor's portal. `item_id` with a readable `cursor` is `invalid_argument`; with one that does not decode, the cursor is reported malformed (`invalid_cursor`). Each mismatch, and the `item_id` case, repairs to the continuation the cursor was minted for (`next_step: "continue_paging"`: the decoded cursor's topic, its guides portal, and the same cursor, so recovery takes one call), so a repair never changes the question (ruling 50); the `item_id` repair's `alternative` says to omit `cursor` to read the item. A changed entry list is `cursor_expired`, and it and an unreadable cursor repair to the topic's first page (`next_step: "list_items"`); for the index that call is `atlas_get_reference({})`, the canonical index call (milestone 3 standards review).
- **describe columns:** `column_cursor` repeats `portal`, `dataset_id`, `column_query`, `detail`; the cursor binds the last three, and omitting `column_query` or `detail` continues with the cursor's. A different value is `invalid_cursor`. Every column-cursor failure names `column_cursor` in `details.field`.
Any other argument on a continuation fails with `invalid_argument`. Cursor repairs point at the paging reference, as in `seattle-open-data`.

### Resources and their tool fallbacks

| resource | tool fallback |
| --- | --- |
| `opendata-atlas://reference` | `atlas_get_reference({})` |
| `opendata-atlas://capabilities` | `atlas_get_reference({topic: "capabilities"})` |
| `opendata-atlas://soql`, `opendata-atlas://soql/{section_id}` | `atlas_get_reference({topic: "soql", item_id})` |
| `opendata-atlas://errors`, `opendata-atlas://errors/{section_id}` | `atlas_get_reference({topic: "errors", item_id})` |
| `opendata-atlas://portals` | `atlas_get_reference({topic: "portals"})` |
| `opendata-atlas://portals/{id}` | `atlas_get_reference({topic: "portals", item_id: id})` |
| `opendata-atlas://portals/{id}/guides` | `atlas_get_reference({topic: "guides", portal: id})` |
| `opendata-atlas://portals/{id}/guides/{guide_id}` | `atlas_get_reference({topic: "guides", portal: id, item_id: guide_id})` |
| `opendata-atlas://contributing` | `atlas_get_reference({topic: "contributing"})` |

`completion/complete` completes `{portal}` (every enabled, active portal's aliases, then canonical ids, each sorted), `{section_id}`, and `{guide_id}` when `portal` is among the context arguments, by case-insensitive prefix; at most 100 values, with `total` and `hasMore` [4.template-completion]. A `{guide_id}` without a servable `portal` completes to nothing. *(Milestone 2 standards review.)*

### Instructions head rules (additions to `seattle-open-data`'s)

The exact wording lives in code, not here: `HEAD_RULES` in `core/reference.py` (served in `instructions` and restated under the capability summary's `## Rules`) and `CAPABILITY_RULES` (served under `## Rules` only). This section only summarizes them:
- Portal choice: pass the portal the user means; without its id, call `atlas_find_portals`, and ask when candidates differ in jurisdiction level (`HEAD_RULES`).
- Knowledge: say so when the answer depends on a field or timestamp that is not reviewed, or is stale (`CAPABILITY_RULES`; `knowledge_notice.message` carries the caveat itself).
- Exploratory path: merged into the "in <area>" rule; with no reviewed place field, a text column may be filtered on values the agent's own `group_by` returned, and the answer says it is unverified (`HEAD_RULES`).
- Unknown zone: merged into the `now_local` rule; never silently assume a zone, state the zone and date range used, or ask (`HEAD_RULES`).
- Knowledge-gap issues: offer the user a defect or knowledge-gap issue, never file one unasked (`HEAD_RULES`; details in the capability summary's `## Knowledge gaps`).
- Zero-match hints: when a query result carries `hints`, follow one before answering that nothing matched (`CAPABILITY_RULES`; the capability summary's `## Semantics` says when `hints` appears). *(Milestone 3 standards review.)*
- Cursor restart: on `cursor_expired` or `invalid_cursor`, follow the repair first (`continue_paging` continues the walk, `list_items` restarts the topic); only after a `read_paging` repair resend the first-page call (capability summary `## Rules`). *(Milestone 3 standards review, fix round 1.)*

**Instructions length (ruling 23):** `instructions` is at most 1,800 characters, sentinel included, measured 1,761 characters at milestone 2 Task 11, 1,778 after the milestone 2 standards review split three bundled rules, and 1,797 after the knowledge-gap rule (line 1 shortened to make room); `tests/test_reference_topics.py` enforces it. That keeps the whole string inside the shortest client prefix on record (2,048 characters; see the agent-friendly-mcp decision 006). Rules whose payload describes itself, and the defect-report details, live in the capability summary only.

**Capability summary requirements:** The capability summary states that scheduled drift checks cannot change an installed release and that the runtime freshness rule is what protects old installs.

## Errors

The `seattle-open-data` envelope carries over, with `SeattleDataError` renamed `AtlasError`.

**Repair migration.** Every inherited repair and suggestion that calls a data tool gains the resolved canonical `portal`. Examples: `browse` becomes `atlas_search_datasets({portal})`; `inspect_columns` becomes `atlas_describe_dataset({portal, dataset_id, detail: "full"})`; `describe_parent` becomes `atlas_describe_dataset({portal, dataset_id: <parent>})`. The inherited rule holds: a repair never reruns a query or search with fewer arguments than the failed call. `tests/test_repairs.py` validates every documented and emitted repair, both search suggestions, and every guide example against the new schemas. The test client (`tests/conftest.py`) also validates every repair, suggestion and hint any test's tool call receives against the named tool's input schema, and checks its scope (final review M-5).

New codes:

| code | temporary | repair |
| --- | --- | --- |
| `portal_not_found` | false | `find_portal`: `atlas_find_portals({})`; `alternative` says to search by place name. |
| `portal_not_enabled` | false | `find_portal`: `atlas_find_portals({})`; the operator restricted the portal set |
| `portal_retired` | false | `find_portal`: `atlas_find_portals({})`; the registry marks the portal retired. Set only from the registry, never inferred from a failed request |
| `describe_too_large` | false | Same call with a smaller result: `use_summary` (`detail: "summary"`) after a `full` call, then `drop_samples` (`sample_rows: 0`); none after a summary call without samples. |

`portal_not_found` never echoes the caller's value. The three portal codes carry `details.field`: `portal` on the data tools, `item_id` on reference topic `portals`, `uri` on a resource. On a resource every code names `uri`, the one parameter of `resources/read` [6.details-field], including `reference_not_found`, whose tool form names `item_id`. On a resource they are JSON-RPC `-32602` (resource not found, `[6.jsonrpc-code-allocation]`) with `error.data.machine_code` set to the code, and `resource_uri` is the URI template (`opendata-atlas://portals/{portal}/guides`), since the URI itself holds the caller's value.

A host that is down, times out, or returns 5xx stays `upstream_unavailable` (temporary), as in `seattle-open-data`. No new code for it.

A `tools/call` naming no tool of this server is `invalid_argument` (temporary false), the code for a malformed call, never `internal_error`, which the capability summary counts as a server defect. `details.field` is `name`, the `tools/call` parameter, and `details.candidates` lists the server's tool names; the received name is not echoed [6.offending-value]. The repair is `read_capabilities`: `atlas_get_reference({topic: "capabilities"})`. No new code. *(Claude's call, milestone 6 standards review.)*

`dataset_not_found`'s `alternative` names the portal that was queried and says the id may belong to another portal.

**Argument combinations** (`core/arguments.py`) are `invalid_argument` with a repair that reads the reference section stating the rule, never a row call (#19): a cursor sent with other arguments reads `soql/paging` (`read_paging`), with an `alternative` naming the arguments to keep and drop; a `mode`/`soql` mismatch reads `soql/syntax` (`read_syntax`); clauses over 4,096 bytes read `soql/filtering`. Every data tool checks combinations before it resolves `portal`, so the same bad call fails the same way on every tool (#23).

## Configuration

- `SOCRATA_APP_TOKEN`: sent to every portal. *(Unprobed: whether one token is honored on every domain and region. No token was available in milestone 0 (2026-10-17) or milestone 2 (2026-10-18); run `scripts/feasibility/check_token.py` with a token before relying on one. If one is not honored everywhere, `SOCRATA_APP_TOKENS` maps host to token.)*
- `OPENDATA_ATLAS_PORTALS`: optional comma-separated allowlist of ids or aliases. Others fail with `portal_not_enabled`. A single-city deployment is this setting; no schema changes.
- Per-host concurrency limit and backoff, so one busy portal does not starve others.
- Plugins: the repository is a Claude Code marketplace (`.claude-plugin/marketplace.json`) and a Codex marketplace (`.agents/plugins/marketplace.json`), each listing one local plugin, `plugins/opendata-atlas/`. It carries a Claude Code manifest and `.mcp.json` and an Agent Plugins `plugin.json` and `mcp.json`, which Codex reads, both starting `uvx opendata-atlas==<version>` at the project version, and a curate-portal stub that follows the clone's `skills/curate-portal/SKILL.md`, so a run never uses instructions frozen at the plugin's release. Its `agents/openai.yaml` turns off Codex's implicit invocation, so Codex starts it only when named (`$curate-portal`), since it commits and can start paid eval runs. The Claude Code server passes `SOCRATA_APP_TOKEN` and `OPENDATA_ATLAS_PORTALS` through from its environment (an unset one arrives blank, which the server treats as unset); the portable `mcp.json` expands no environment variables, so the Codex plugin sets neither. `marketplace-policy.json` declares the two readers.

## Registry

`scripts/build_registry.py` (dev-only) writes `registry.json` from:
1. **Enumeration** of the Discovery API in both regions by deep scrolling: `GET /api/catalog/v1?only=dataset&limit=5000&scroll_id=<last resource.id of the previous page>`, with an empty `scroll_id=` on the first request, until a page shorter than `limit` (`enumerate_domains.method_b2`). (Offset paging is capped at 10,000 and `/api/catalog/v1/domains` is 404; see upstream-facts.) A capped or failed scroll stops the build. The result is a list of catalog domains, which are not always public hosts.
2. **Eligibility**, in order. Rules are recorded in upstream-facts with the probes behind them.
   - **Name rule:** drop hosts with a DNS label `demo`, any label containing `staging`, names starting `internal`, and names starting `priv-`; keep `*.data.socrata.com`, which are real public portals.
   - **Non-production rule:** drop a host whose first DNS label, split on `-`, contains one of the tokens `uat`, `dev`, `qa`, `test`, `train`, `staging`, `integration`, or whose first label contains `sandbox`. A whole token decides: `testament` stays.
   - **Anonymous `/api/views`:** `GET https://<public host>/api/views.json?limit=1`. A 2xx with a JSON body keeps the portal. A 5xx or a timeout keeps it and is recorded, so a 5xx alone does not make a portal ineligible. A 4xx, a 2xx whose body is not JSON (the host redirects off Socrata), or a connect, DNS, TLS or protocol failure means the host does not serve `/api/views` anonymously, so the portal is dropped. The evidence records the status, the exception class and the final URL after redirects.
3. **Identity resolution** per domain:
   - Try `domains=` and `search_context=` with the catalog domain and up to three hosts from catalog `link` fields. Accept a candidate only if every result across the first three pages carries the expected `metadata.domain`.
   - **Selection rule:** among the accepted candidates, take the one with the largest `resultSetSize` (`limit=0`, all asset types); on a tie prefer `domains`.
   - **Public host:** the host the chosen query names when it is not the catalog domain, else the single host every catalog `link` points at, else the catalog domain. The evidence records which and why.
   - A catalog domain that a pack's `catalog_query` already names is folded into that pack's entry.
   - `catalog_size` is the chosen query's `resultSetSize`; `dataset_count` is the same with `only=dataset`.
   - Examples: data.sf.gov gets `search_context` (1,225 assets) over `domains` (5); Seattle's `cos-data.seattle.gov` is folded into the Seattle pack.
4. **Generated metadata:**
   - **`name`** comes from the portal's own site title, else the host. Fields: `html_title`, `site_title` and `site_company`, in that order. Each has its whitespace collapsed and is split on ` | ` and on a spaced `-`, `–` or `—`. A part is a candidate unless it is empty, generic (`GENERIC_TITLES` in `scripts/build_registry.py`: `catalog`, `data`, `home`, `open data`, `socrata`, `tyler data & insights`, ...), equal to the host (casefolded), or a repeat of an earlier candidate. The name is the first candidate that looks like a government name (`City of X`, `X County`, `State of X`, `..., WA`, ...), else the first candidate; no candidate means the host.
   - **`place_names`, `jurisdiction` and `timezone`** are **nullable** (`jurisdiction: null` in the schema) and come only from overrides. *(Claude's call.)*
   - **An override's `name` wins** over the generated name, and a pack's identity wins over both. The build applies titles with `--titles N` (the N largest portals) or `--titles all`; cached titles in `titles.json` are reused.
   - **Review generated names by hand** whenever a rebuild changes them. Give a name that is a vendor's or another organization's, or that would mislead `find_portals`, an override: another part of the same portal's title, or the host. The milestone 6 review is `docs/evidence/registry-names-2026-10-20/review.md`.
   - Overrides are written for every curated and profiled portal and, at launch, for the 50 largest portals by catalog size, so `find_portals` works by place name where most usage will be. Portals without an override match by host or by their generated name. The ambiguous-place eval uses portals with overrides.
5. **Manual additions** in `registry_overrides.toml`, for portals the enumeration misses, and for names, place names, jurisdictions, aliases and timezones. A manual entry passes the same eligibility and identity checks, or the build exits. An override for a pack's id is an error: the pack defines its identity.
6. **Retirement:** a portal absent from enumeration and failing eligibility on two consecutive scheduled runs is marked `retired` in a reviewed PR. Never removed, so its id stays reserved.

The promise is "every registered public Socrata portal", and the README states how to add a missing one.

## Building knowledge

The profiler, drift checks, contribution path, curation runbook, per-portal eval tasks and knowledge-gap reports are in [knowledge-tooling.md](knowledge-tooling.md).

## Byte budgets

The 24 KiB `tools/list` and per-result budgets carry over. One guarantee, two measures (rulings 35, 72): every tool's measured result is at most `RESULT_LIMIT`, which is `RESULT_BYTE_BUDGET` (24,576) minus `ENVELOPE_RESERVE` (1,024), so 23,552 bytes.
- `atlas_query_dataset`, `atlas_search_datasets`, `atlas_get_reference` entry pages and `atlas_find_portals` are measured by `wire_size`, the text copy plus `structuredContent` (ruling 72 for the last two; search since #17). The reserve covers the rest of what the modern client receives: the `_meta` serverInfo stamp (602 bytes since milestone 5 minified the icon; 666 before), `isError` and the JSON-RPC frame: 695 bytes on the reference index and on the widest query page (759 before the icon was minified, 742 on that page when Task 8 measured it; `tests/test_budget.py`). So a full query, reference entry or `atlas_find_portals` page fits 24,576 bytes on the modern wire. The widest recorded page (`query_wide_rows`, 6 rows) is 23,596 bytes there, frame included (milestone 5 Task 2, with `now_weekday` and the minified icon; 23,610 at the milestone 3 standards review; 23,342 at Task 8, before every fired notice ended with the knowledge-gap offer).
- `atlas_describe_dataset` and `atlas_get_reference` bodies (never paged) are measured by `payload_size`, `structuredContent` alone (ruling 19). Wire-measuring describe would page Seattle's Fire 911 `full` describe (14,129 bytes of payload; 31,678 on the modern wire). These results meet the budget under the payload measure, not on the wire, and are the known exceptions to the modern-wire limit: `atlas_get_reference({"topic": "errors", "item_id": "codes"})` is 11,886 bytes of payload and 26,545 on the modern wire, frame included (milestone 3 standards review; 11,850 before Task 9 listed the reference cursor codes).
- `atlas_find_portals` packs whole candidates to the limit; `has_more` and the cursor continue after the last candidate returned.
- `atlas_search_datasets` keeps the leading datasets, with their `match_evidence`, that fit the limit (#17); a page cut short has `has_more: true`, and its cursor continues at the catalog entry after the one behind the last dataset kept. When the (at most 3) `external_matches` leave room for no dataset, or overflow alone, they lose their `description` first; a result that still cannot fit is `internal_error`.
- `atlas_get_reference` packs whole entries of an entry list the same way.
- `tests/test_budget.py` checks each tool's largest result against its measure.
- `tests/test_contract.py` measures `tools/list` as the client receives it, JSON-RPC frame included: 24,560 bytes of 24,576 on the modern era and 23,944 on the legacy era (milestone 5 Task 2, after `source.now_weekday` joined the five output schemas; 24,517 modern without the frame; 24,464 framed before). Final for milestone 5, re-measured at its standards review (Task 8): `tools/list` 24,560 modern and 23,944 legacy, framed (16 bytes of headroom on the modern era); `INSTRUCTIONS` 1,797 of 1,800 characters; the modern `_meta` serverInfo stamp 602 bytes, 695 bytes of modern overhead on the reference index (`docs/evidence/standards-m5-2026-10-19/measure.out.txt`). Output schemas drop `default` and any `type` beside `enum` or `const` (`mcp/schema.compact_output_schema`, #25); input schemas keep both. That brought the modern framed `tools/list` to 23,910 bytes (666 of headroom), measured by `tests/test_contract.py` on 2026-10-25.
- The serverInfo stamp keeps the icon (#22). On the modern era `server/discover` carries no `serverInfo`, so the stamp on each result is a client's only source of the icon; `_meta` is protocol metadata, not content a client gives the model; and `ENVELOPE_RESERVE` already budgets the 602 bytes.

Milestone 0 measures the five-tool `tools/list` (with compatibility content) before any feature work. Fixtures for a 300-column dataset (built, milestone 2 Task 10), a portal with 100 guides, and a 2,000-entry registry page (built, milestone 3 Task 9) check that every result stays in budget and that nothing is silently trimmed: anything omitted has a cursor or a narrowing repair.

## Launch scope

*(Revised after critique; Claude's call.)*
- `seattle`: curated, migrated from `seattle-open-data` with all facts (converted to the claim model), guides, and evals.
- `chicago`: one contrasting portal, taken from `generic` to `curated` purely through the contribution path. Chosen for its ward and community-area vocabulary and its 2,029 catalog entries. When the curating agent hits a gap that needs engine code, it stops, logs the gap in docs/decisions.md, and a separate engine PR fixes it; curation then resumes. Chicago ships `curated` or the release waits. **Status (milestone 4, 2026-10-19): `chicago` (`data.cityofchicago.org`) is `curated`.** Its pack is `src/opendata_atlas/portals/data.cityofchicago.org/` (`portal.toml` declares `tier = "curated"`, promoted in ef2e9bf), its eval file `evals/portals/data.cityofchicago.org.json`. Evidence: `docs/evidence/curation-chicago-2026-10-19-run1/` (the run), `docs/reviews/2026-10-19-m4-chicago-pack.md` and `docs/evidence/review-chicago-2026-10-19/` (the pack review), `docs/evidence/promotion-chicago-2026-10-19/` (smoke test and re-grade), `docs/evidence/launch-evals-2026-10-19/` (the launch-scope run). No engine-gap task was needed.
- **Status (milestone 6, 2026-10-19), two more portals through the same path:**
  - `everett` (`data.everettwa.gov`) is `curated`. Its pack is `src/opendata_atlas/portals/data.everettwa.gov/` (`portal.toml` declares `tier = "curated"`, promoted in 2c4bbca), its eval file `evals/portals/data.everettwa.gov.json`. Evidence: `docs/evidence/curation-everett-2026-10-19-run1/` and `-run2/` (the runs), `docs/reviews/2026-10-19-m6-everett-pack.md` and `docs/evidence/review-everett-2026-10-19/` (the pack review), `docs/evidence/promotion-everett-2026-10-19/` (smoke test and re-grade). Two curation runs and two engine-gap fixes were used.
  - `king-county` (`data.kingcounty.gov`) is `curated` (2026-10-20). Its pack is `src/opendata_atlas/portals/data.kingcounty.gov/`, its eval file `evals/portals/data.kingcounty.gov.json`, with KCSO Offense Reports (`4kmt-kfqf`) `reviewed`. It was `profiled` after milestone 6, because the profiler's flagship datasets had no place-and-time dataset; a second curation reached one with `--datasets 21` (decisions row "King County promoted to curated"). Evidence for the second curation: `docs/evidence/curation-king-county-2026-10-20-run2/`. Earlier evidence: `docs/evidence/curation-king-county-2026-10-19-run1/`, `docs/reviews/2026-10-19-m6-king-county-pack.md`, `docs/evidence/review-king-county-2026-10-19/`.
  - Launch-scope evals for both: `docs/evidence/launch-evals-m6-2026-10-19/` (see [history.md](history.md#eval-runs)).
- **Status (2026-10-20):** `los-angeles` (`data.lacity.org`) is `profiled`, with LAPD NIBRS Offenses (`k7nn-b2ep`) `reviewed`; its pack is `src/opendata_atlas/portals/data.lacity.org/`, its eval file `evals/portals/data.lacity.org.json`. The curating agent proposed `curated` (every task PASS in 3 of 3 runs, its own grades), pending an independent re-grade.
- Every other registered portal: `generic`.
- More profiled or curated portals come after launch, through the same path.

## Evals

The `seattle-open-data` tasks run with `portal: "seattle"` at the same targets (first-call correctness ≥95%, first-repair correctness ≥90%, zero silent completeness, coverage or timezone errors). New tasks:
- **Wrong-portal guard:** "How many crimes were reported in Chicago last month?"; pass means the agent queries Chicago.
- **Ambiguous place:** "building permits in Cook County" vs "in Chicago"; pass means distinct portals, or a question to the user.
- **Unreviewed dataset on a curated portal:** a Seattle dataset with no claims; pass means the answer carries the caveat.
- **Reviewed dataset, unreviewed time column:** pass means the answer says the column's timezone is unverified, and states the absolute date range used.
- **Generic dataset with only a text place column:** pass means the agent completes the question via the exploratory path and caveats it.
- **Multi-zone portal** (a state portal spanning zones, chosen in milestone 0) with a relative date: pass means absolute dates are stated or the user is asked.
- **Stale claim** (milestone 3, with freshness; `30-stale-claim`): a fixture with a stale `ok` claim (SPD Crime `sector`, checked 2026-01-01); pass means it is treated as unknown.
- Chicago's own tasks (see [knowledge-tooling.md](knowledge-tooling.md), Per-portal eval tasks), written during curation.
- **Knowledge-gap offer** (`31-knowledge-gap-offer`): a task where a field is unverified (LAPD's `area_name` on the unreviewed Crime Data from 2020 to 2024, `2nrs-mtv8`; until the Los Angeles pack it was the space-padded `area_name` of NIBRS Offenses); pass means the agent caveats the answer and offers the issue without filing it.
- **City data at the county** (`32-city-data-at-county`, milestone 6): Seattle restaurant health inspections last month, which `data.seattle.gov` does not publish and King County's `r878-4sxa` does; pass means the agent says Seattle's portal does not publish it and uses King County's, stating that the data is county-wide and filtered to Seattle.

Eval runs by milestone, with their grades and costs, are in [history.md](history.md#eval-runs).

## Milestones

The build milestones (0 to 6) and what each delivered are in [history.md](history.md#milestones).

## Left to the builder

- Module layout beyond `portals/`.
- The checker catalog beyond those named, as claims need them.
- Exact wording of instructions, notices and error messages, within the byte budgets.
- Per-host concurrency and backoff numbers; describe column page sizes (from the milestone 0 budget spike).
- The enumeration method (milestone 0).
