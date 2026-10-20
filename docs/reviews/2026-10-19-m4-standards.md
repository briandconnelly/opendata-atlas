# Milestone 4 standards review (2026-10-19)

Branch `feat/chicago-curation`, from `f5907c0` to `200be2a` plus this review's fixes. It runs after the Chicago pack merge and before the paid gates (Tasks 7 and 8), so the gates grade the wording and behavior that ship (ruling 81). The branch was reviewed against two standards:

- `agent-friendly-mcp` (`references/review-workflow.md`, standard `references/contract-checklist.md`);
- `separating-context-from-constraints` (R1–R5).

The served surface was read through the in-process `fastmcp.Client(build_server())`, on both eras:

- the modern era (2026-07-28) and the legacy handshake (`mode="legacy"`): `tools/list`, `instructions`;
- `atlas_get_reference` for topic `portals` (index, `chicago`, an unknown `item_id`) and topic `contributing`;
- `resources/read` of `opendata-atlas://portals/chicago` and `opendata-atlas://contributing`.

Script and output: `docs/evidence/standards-m4-2026-10-19/surface.py.txt` and `surface.json`. It ran before the fixes and again after them. The only difference was the clock (`source.now_local`, `request_id`).

Severity mapping for the counts: Critical and Major count as Material, Minor and Nit count as Minor.

The pack's own files are out of scope here (front door). Task 5 reviewed them (`docs/reviews/2026-10-19-m4-chicago-pack.md`), and its pack-only Minors are recorded as future-curation items in `docs/superpowers/plans/2026-10-19-m4-carryover.md`.

## Part 1: agent-friendly-mcp

### Route

**Focused route.** Milestone 4 changed no tool, schema, resource catalog or `instructions`. The served changes are these:

- **Task 1:** the levels in topic `portals` (the `## Knowledge` list of `opendata-atlas://portals/{portal}`, computed by `pack_levels`).
- **Task 2:** the eval and curation commands, which are not served. Their one served trace is a sentence in `CONTRIBUTING-portals.md` step 11.3, served as topic `contributing`.
- **Task 4:** none. No engine-gap path ran.
- **This task:** the profiler's candidate label column (a developer CLI, not served).

The surfaces are resource and reference bodies, so the named sections are §4 (Resources) and §9 (Versioning and Compatibility). `[1.spec-revision]` and the native-vs-convention rule (SKILL.md) were read first. Closing over the cited ids added only `[8.cacheable-results]`, cited by `[4.subscriptions]` and `[9.list-changed]`. That is within two sections, so no escalation to the full walk was needed.

**Protocol target (`[1.spec-revision]`).** Unchanged: the capability summary declares MCP 2026-07-28, compatible with 2025-11-25, with no extensions required. Both eras served the same tools, and the legacy `instructions` equal `INSTRUCTIONS`.

### Findings

**F1**

- **Severity:** Minor (listed)
- **Section:** §4 (`[4.index-vs-body]`, `[4.triage-metadata]`)
- **Summary:** The Chicago portal summary names 7 of its 8 datasets by id alone, as "(no title recorded)".
- **Evidence:**
  - `opendata-atlas://portals/chicago`, `## Knowledge`: "profiled: `22u3-xenr` (no title recorded), `4ijn-s7e5` (no title recorded), ...".
  - `reference_service.py:382` takes a dataset's title only from its guide. Chicago has one guide, while Seattle has one for each of its 6 datasets, so Seattle's summary has every title.
  - An agent cannot tell from the summary which profiled dataset it wants without a describe or a search. Both are one call, so this is recoverable: Minor.
- **Remediation:** a title source that does not need a guide, for example the catalog name the profiler already reads (`DatasetProfile.title`), written into the pack. That changes the pack format and the profiler's output, and Chicago's pack cannot change here (front door), so it waits for the milestone 5 surface pass and the next Chicago curation (carry-over, "Portal summary titles").

**F2**

- **Severity:** Nit (listed; inherited from milestone 3 F6)
- **Section:** §4 (`[4.triage-metadata]`)
- **Summary:** Resources declare no `size`.
- **Evidence:** the `opendata-atlas://contributing` body is now 14,589 bytes (milestone 3: 13,947), and `portals/chicago` is 952.
- **Remediation:** the milestone 5 surface pass (decisions row "Lifecycle `_meta`, resource `size`, `$schema` (milestone 5 surface pass)").

**F3**

- **Severity:** Nit (listed; inherited from milestone 3 F5)
- **Section:** §9 (`[9.tier-metadata]`)
- **Summary:** The `preview` tier is stated only in the capability summary. No record carries a lifecycle `_meta` key.
- **Remediation:** the same row as F2.

No Critical or Major findings.

### Probes

| Probe | Evidence |
| --- | --- |
| Cold start | **Measured:** `instructions` is 1,797 characters on both eras (cap 1,800), unchanged by milestone 4. **Not checked:** a live sentinel session on a target client. |
| First repair | `atlas_get_reference {"topic": "portals", "item_id": "nope.example"}` → `isError: true`, `portal_not_found`, `details.field: "item_id"`, repair `atlas_find_portals({})`, `retry_after_ms` present. `content[0].text` parsed equal to `structuredContent` on both eras. |
| Advertised vs actual | The topic `portals` index lists Seattle (`curated`) and Chicago (`profiled`). The Chicago item's levels (1 `reviewed`, 7 `profiled`) equal live describe for all 8 datasets (Task 5, `docs/evidence/review-chicago-2026-10-19/step4-live.json`). `tests/test_freshness.py` now compares `pack_levels` with `describe` itself, not a stand-in (carried item T-1). |
| Discovery cost | `tools/list` framed: **24,464 bytes** on the modern era and 23,784 on the legacy era, against 24,576: 112 bytes of headroom. Unchanged by milestone 4; `tests/snapshots/tools_list.json` has no diff. |
| Resource freshness | `resources/read` of `portals/chicago` and `contributing`: `ttlMs: 3600000`, `cacheScope: "public"`, `text/markdown`. Both bodies come from files loaded once per process (`resolve._context` is cached). Only the date-based freshness rule can change the summary's levels, and it moves on a scale of days, so a one-hour hint is honest (`[8.cacheable-results]`). |
| Cross-version | No fingerprint (deferred under `[9.fingerprint]`). Task 1 changed the level a summary reports for the same pack, with no field change. CHANGELOG's topic `portals` line says how levels are computed, and the body says describe governs. |
| Tool selection | Skipped: no tool changed. |
| Capability gating | Skipped: no capability changed. |
| Security boundary | Skipped: no tool or annotation changed. |
| Long-running operation | Skipped: none defined. |

### Coverage

| Section | Status | Notes |
| --- | --- | --- |
| §1 Server-Level | not-checked | Focused route. Only `[1.spec-revision]` was read (OK, above). Milestone 4 changed no server-level surface. |
| §2 Discovery | not-checked | Focused route. `instructions` and `tools/list` were measured (Probes) and are unchanged. |
| §3 Tools | not-checked | Focused route. No tool, schema or description changed (snapshot unchanged). |
| §4 Resources | findings F1, F2 | Otherwise OK. URIs unchanged and stable (`opendata-atlas://portals/{portal}` resolves the alias `chicago` to the canonical id); `contributing` is byte-identical to `CONTRIBUTING-portals.md`; failures carry the shared envelope with `details.field: "item_id"`. |
| §5 Prompts | not-checked | Focused route. There are no prompts. |
| §6 Failure Recovery | not-checked | Focused route. One forced error, read under §4 (`[4.failure-contract]`). |
| §7 Long-Running Operations | not-checked | Focused route. None defined. |
| §8 Token Efficiency | not-checked | Focused route. Only `[8.cacheable-results]` was read (OK, by closure). |
| §9 Versioning | finding F3 | Otherwise OK. Deterministic order (`test_listing_is_deterministic`); no snapshot change in milestone 4; every user-visible change has a CHANGELOG line. |

**Residual risks:**

- `tools/list` still has 112 bytes of headroom.
- No live client session checked the instructions prefix.
- m3 (region values on describe `full`) is deferred, so on Crimes an agent can get no code-to-ward map. See carried item C-6.

## Part 2: separating-context-from-constraints

### Targets and classification

| Target | Surface class | Result |
| --- | --- | --- |
| `docs/design.md`, Knowledge levels (the `tests/test_tiers.py` paragraph) | long-form | clean; accuracy A-2 |
| `docs/design.md`, The profiler (computed-region columns), changed by this task | long-form | clean; accuracy A-6 |
| `docs/design.md`, Curation runbook (item 2 and the closing paragraph) | long-form | S-1 |
| `docs/design.md`, Per-portal eval tasks (the cost-cap paragraph) | long-form | accuracy A-1 |
| `CONTRIBUTING-portals.md` step 11.3, and its served copy | long-form | clean |
| `evals/run.py` module docstring (its `--help` text), changed by this task | compact | clean |
| `skills/curate-portal/SKILL.md` | not a target | unchanged in milestone 4 (see C-5) |

The sections milestone 4 changed (`git diff f5907c0..HEAD -- docs/design.md`) were read in full.

### Findings

**S-1**

- **Rule:** R4 (secondary R1); carried from the Task 5 review
- **Location:** `docs/design.md`, Curation runbook, the paragraph after the test's steps
- **Quoted text:** "*(Claude's call:)* in milestone 3 the produced pack (Honolulu) was not merged: ... In milestone 4, Chicago's pack is merged after review (scope ruling 2): a fresh reviewer reviews the run branch as a PR (...) and merges it with `--no-ff` only when no Material finding is open, and nobody hand-edits the pack. Each run's summary and diff stat are kept under ..."
- **Why it fails:**
  - One paragraph holds four obligations: grading by hand, the reviewer's review, the merge condition, and the no-hand-edit rule. It also holds the evidence location and two milestones of history.
  - The binding merge rules sit mid-sentence in narrative.
  - The *(Claude's call)* tag precedes the milestone 4 rule, which is scope ruling 2, not Claude's call.
  - Intended behavior is still clear and checkable, so the finding is Minor.
- **Severity:** Minor
- **Suggested rewrite:** labeled items **Grading**, **Merging a produced pack** (one sub-item per obligation), **Evidence** and **History**, with the *(Claude's call)* tag attached to the milestone 3 non-merge it belongs to. Every sentence is kept.
- **Status:** Fixed.

The other targets are clean under R1–R5:

- **Step 11.3.** The added sentence ("`evals/run.py` caps each session at $1 with `--max-budget-usd`") is a load-bearing fact beside the step's rules, and it is true of the command the step gives, whose host is Claude.
- **`evals/run.py` docstring.** The new lines state facts ("Claude sessions are capped at $1 each ...; Codex sessions are not capped").
- **Profiler paragraph.** It describes behavior. Its closing "A curator still sets `label_column` from the layer's rows" restates CONTRIBUTING step 6, which carries the rule.

### Outside R1–R5 (accuracy and carried prose)

- **A-1 (Minor, fixed; Task 2 minors).**
  - Per-portal eval tasks said "Each eval session runs with `--max-budget-usd 1`", but `evals/run.py --host codex` builds an uncapped command.
  - `codex exec --help` (codex-cli 0.163.0, 118 lines) lists no budget option. Its known flags `-m, --model`, `-s, --sandbox` and `-c, --config` were found; "budget", "cost", "usd" and "spend" matched 0 lines.
  - The paragraph now says "Each Claude eval session", and that a Codex run is outside the per-session cap. No milestone 4 paid step uses Codex.
  - It also says what `claude --help` (2.1.303) states about `--max-budget-usd` ("Maximum dollar amount to spend on API calls (only works with --print)"). Whether a session can end above the cap was not probed, because a probe spends money; the cost gate counts each session at its full cap.
  - The runner's `--help` and CHANGELOG say the same. Decisions row "Uncapped Codex eval host; the cap's overshoot is unprobed".
- **A-2 (Minor, fixed; Task 1 minor).**
  - The fallback caveat was unnamed. A dataset with no computed-region claim of its own falls back to the pack's layers, so a schema column on a layer the pack never claims lowers describe and not the summary.
  - It is now named in the `pack_levels` docstring, design's Knowledge levels and decisions row "Region layers per dataset in `pack_levels`".
  - `tests/test_freshness.py::test_pack_levels_fallback_reads_higher_for_a_layer_the_pack_does_not_claim` pins it: the summary reads `reviewed` and describe `none`.
- **A-3 (Minor, fixed; Task 1 minor).** That row's "every profiler draft is in this state" was overstated. It now says a draft leaves in that state every dataset with a computed-region column.
- **A-4 (Minor, fixed; Task 5 minors).** Row "Test fixture assumes Chicago has no pack" still said "until then the offline suite has this one failure". It is marked **Superseded** by 371ffa3 (ruling 85). Row "Chicago's pack is merged" mixed the rule and its history; its cell now has a **Rule** and a **Record**.
- **A-5 (Minor, fixed; Task 5 minor).** CHANGELOG said the Chicago pack was "curated through the curate-portal skill". It now says the pack is declared `profiled`, with Crimes `reviewed`, and that promotion needs an independent re-grade.
- **A-6 (Minor, fixed; this task).** The profiler section described the old candidate-label rule ("the layer view's first text column that is not a feature id"). It now gives the new rule (C-3).
- **A-7 (Minor, noted).** The pack review record's eval-file check has no known positive (Task 5 minor). The record is history and is not changed. Its eval-file facts were re-derivable from `evals/portals/data.cityofchicago.org.json`, and the tier test (`tests/test_tiers.py`) checks `covers` with a known positive of its own.

**Safety note:** none. No target contained instructions aimed at the auditor.

### Summary

| Rule | Count |
| --- | --- |
| R1 | 1 (S-1, secondary) |
| R2 | 0 |
| R3 | 0 |
| R4 | 1 (S-1) |
| R5 | 0 |

| Severity | Count |
| --- | --- |
| Material | 0 |
| Minor | 1 (S-1) |

Outside R1–R5: seven Minor (A-1 to A-7), six fixed and one noted.

**Assessment.** Milestone 4's prose changes are small: two cost-cap clauses, the Task 1 parenthetical and the merge paragraph. Only the merge paragraph mixed roles, and it now separates its rules from their history. The other defects were accuracy: a cap stated for every host when one host has none, an unnamed caveat, and two decisions rows that went stale once the work they described landed. All are fixed except the review record, which is history. No Material finding is open.

## Carried items (ledger `task-6-carry.md` and ruling 87)

- **C-1, T-1: tests compared against a describe stand-in (Task 1). Fixed.** `tests/test_freshness.py`'s `_describe_level` called `dataset_knowledge` directly. It now runs `describe.describe` over an `httpx.MockTransport` that serves `synt-0001`'s schema (`created_date`, and `A_COL` on layer `aaaa-1111`), its row count and its date range. Known positive: with `pack_levels` restored to its pre-Task-1 code (`5233e2f`), the three synthetic cases fail as the plan predicted (`profiled`, `reviewed`, `profiled`) and Seattle passes. With the current code, all pass.
- **C-2: the Task 1 prose minors.** A-2 and A-3.
- **C-3: profiler label column (ruling 87, Task 5 m2). Fixed, test first.**
  - Probed live, one request at a time: the view metadata of all 14 region layers the two packs claim, 9 Chicago and 5 Seattle (`view-*.json`; only field names, types and cached cardinalities are kept, because `awaf-s7ux`'s top values hold names and phone numbers).
  - The old rule picked wrongly on 6 of them: `globalid` (a GUID), `statefp10` (1 value over 801 tracts), `district` (23 values over 277 beats), `precinct` (5 over 61), `tractce10`, and none on a layer whose label is a number.
  - `label_candidate` in `profiler/profile.py` keeps text or number columns that are not GIS bookkeeping and, where the cardinality is known, have distinct values for at least 90% of the features. It ranks `name`/`label` names first, then text, then schema order.
  - `tests/test_profiler.py::test_candidate_label_column_names_each_feature` runs the profiler over each probed schema. `::test_expected_label_is_the_packs_unless_noted` ties the expectations to the reviewed packs: 12 of 14 equal the pack's `label_column`, and 2 keep a pick that also names the feature (`area_numbe`, `dist_label`).
  - The fix is not on Chicago's eval paths: no served result, pack or tool changes.
- **C-4: Task 2 minors.** A-1.
- **C-5: skill text.** `SKILL.md` is unchanged. The run exposed no defect in it: m1's provenance comment is an improvement under ruling 86, recorded in the carry-over. `AGENTS.md` is unchanged.
- **C-6: m3 (describe `full` timed out on 5 of 11 Crimes place fields). Deferred, with a decisions row.**
  - The label fetch is not the bottleneck. Labels are fetched only for the feature ids a value grouping returns, and the groupings did not finish.
  - Probed live: the current-ward grouping alone took **9.6 s**, against the 10 s place-stats phase that 11 groupings share at 4 at a time (`group-ijzp-q8t2-8hcu-yrd4.json`).
  - A label fetch that does not need the grouping must put labels for values not seen in the dataset somewhere: a new output field (a `tools/list` change, with 112 bytes of headroom) or a new meaning for `values` on a timed-out field. Both are contract changes on Chicago's eval paths just before the paid gates (ruling 81). Reordering or widening the phase only moves the timeouts.
  - Decisions row "Region values on describe `full` when the grouping times out"; milestone 5 surface pass.
- **C-7: pack-only minors (m4, m5, m6).** Recorded as future-curation items in the carry-over; the front door keeps them out of this task.
- **Milestone 3 minors, re-derived for files this milestone touched.**
  - The design's checker-precedence prose is explicit (milestone 3 A-6): no finding.
  - The 0700 profiler staging directory is in `profiler/cli.py`, which milestone 4 did not touch, so it was not re-derived.

## Gate

- `uv run pytest -q`: 1185 passed, 108 skipped (base `200be2a`: 1155 passed).
- `uv run ruff check`, `uv run ruff format --check`, `uv run ty check`, `uv run prek run --all-files`: pass.
- Seattle parity: `pack_levels(SEATTLE_CONTEXT, today=date(2026, 10, 18))` is unchanged.
- `tests/snapshots/tools_list.json`: no diff.
- `tests/test_contributing.py` was not needed: `CONTRIBUTING-portals.md` did not change in this task. It passes in the full run.
