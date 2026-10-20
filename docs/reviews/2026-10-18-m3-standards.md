# Milestone 3 standards review (2026-10-18)

Branch `feat/knowledge-tooling`, from `4d61a9d` to `cc62e3e` plus this review's fixes (`c1cdc8f`, and fix round 1 after the task review). The branch was reviewed against two standards:

- `agent-friendly-mcp` (`references/review-workflow.md`, standard `references/contract-checklist.md`)
- `separating-context-from-constraints` (R1–R5)

Every surface was read as served, through the in-process `fastmcp.Client(build_server())`:

- the legacy handshake (`mode="legacy"`, protocol 2025-11-25): `initialize` (capabilities, `serverInfo`, `instructions`) and `tools/list`;
- the modern era (2026-07-28): capabilities, `tools/list`, `resources/list`, `resources/templates/list`, a `resources/read` of every listed resource and of 4 failing URIs;
- 16 forced tool errors, and 12 successful `atlas_get_reference` and `atlas_find_portals` calls.

The query, describe and search paths, and the milestone 3 additions on them (`hints`, `knowledge_notice` text columns, `unit_of_observation`, `validation`), were read through the recorded-fixture tests and one live integration run.

Severity mapping for the counts: Critical and Major count as Material, Minor and Nit as Minor.

## Part 1: agent-friendly-mcp

### Route

**Full walk**, §1 to §9. The surface changed in Tasks 3 (`validation`, reliability `unknown`), 5 (`unit_of_observation`), 7 (`hints`) and 9 (reference paging, a new `cursor` argument and two new error codes on `atlas_get_reference`).

**Protocol target (`[1.spec-revision]`).** Unchanged from milestone 2. The capability summary's `## Context` declares "MCP 2026-07-28, compatible with 2025-11-25; no extensions required". The modern client negotiated `2026-07-28` and the legacy client `2025-11-25`, and both serve the same tools.

### Findings

**F1**

- **Severity:** Minor (fixed)
- **Section:** §3, §2 (`[3.advertised-fields]`, `[2.summary]`)
- **Summary:** Milestone 3's two new result fields, query's `hints` and describe's `unit_of_observation`, were documented on no agent-visible surface. Neither the tool descriptions, the `outputSchema` descriptions nor the capability summary said when they appear, or what a zero result with a hint means.
- **Evidence:**
  - `tools/list`: `hints` is `{"items": {...next_step, tool, arguments, alternative}, "type": "array"}` with no `description`. `unit_of_observation` has none either.
  - The capability summary's `## Semantics` named neither field, and no rule said what to do with a hint.
  - A hint's `alternative` explains itself ("its values may be padded or differ in case, so filter on a value this grouping returns"), and eval task 31 passed. So no task failure is demonstrated: Minor.
- **Remediation (done):**
  - `## Semantics` gains a `Hints` item (when `hints` appears, up to 3, one per column, `inspect_text_values`, why) and a `Rows` item for `unit_of_observation`.
  - `## Rules` gains "When a query result carries `hints`, follow one before answering that nothing matched." (`CAPABILITY_RULES`; served under `## Rules` only, so `instructions` is unchanged).
  - `outputSchema` descriptions were not added: a snapshot change is outside this task (milestone 3 allowed surface changes only in Tasks 3, 5, 7 and 9), and `tools/list` has 155 bytes of headroom. Recorded for the milestone 5 surface pass.
  - Regression: `tests/test_standards_m3.py::test_capability_semantics_describe_hints_and_unit_of_observation` and `::test_hints_rule_is_a_capability_rule`.

**F2**

- **Severity:** Minor (listed; kept by ruling 68)
- **Section:** §8 (`[8.ap-fixed-prose]`)
- **Summary:** Every fired `knowledge_notice` ends with the same 133-character sentence, the knowledge-gap offer.
- **Evidence:** `portals/knowledge.GAP_OFFER`: "When you caveat a gap named here, also offer the user a knowledge-gap issue (capabilities ## Knowledge gaps); never file one unasked." The rule says to state an invariant once.
- **Remediation:** none. The sentence is attached only when a notice fires, which varies per result, and ruling 68 chose it on eval evidence: with the rule in `instructions` alone, task 31 offered the issue in 0 of 3 runs, and with the cue in 3 of 3 (`evals/results/2026-10-18-m3.md`). Revisit if notices become frequent on a single answer.

**F3**

- **Severity:** Nit (fixed; Task 9 review M5)
- **Section:** §6 (`[6.repair-callable]`, `[6.repair-object]`)
- **Summary:** The index has two literal calls. `invalid_argument` repaired to `atlas_get_reference({})`, but an unreadable or expired index cursor repaired to `atlas_get_reference({"topic": "index"})`.
- **Evidence:** `atlas_get_reference({"cursor": "garbage"})` returned `invalid_cursor` with repair arguments `{"topic": "index"}`; `atlas_get_reference({"topic": "guides"})` returned `invalid_argument` with `{}`. Both are callable; design.md calls `{}` the index.
- **Remediation (done):** `reference_service._list_items` returns `{}` for the index, so every index repair is one call. `next_step` stays `list_items`. Regression: `tests/test_standards_m3.py::test_unreadable_cursor_without_topic_restarts_with_the_index_call`, `::test_expired_index_cursor_restarts_with_the_index_call`, and `::test_other_topics_still_restart_on_their_own_first_page` (unchanged behavior).

**F4**

- **Severity:** Minor (listed; inherited F7)
- **Section:** §2, §8 (`[2.compact-baseline]`)
- **Summary:** The modern `serverInfo` stamp inlines the data-URI icon in every 2026-07-28 result.
- **Evidence:** modern `tools/list` 24,421 bytes, legacy 23,741; the difference is the stamp.
- **Remediation:** milestone 5 (decisions row "Icon by URL, README status word, release-cut test (milestone 5)").

**F5**

- **Severity:** Nit (listed; inherited F8)
- **Section:** §9 (`[9.tier-metadata]`)
- **Summary:** The `preview` tier is stated only in the capability summary; no record carries a `_meta` lifecycle key.
- **Evidence:** tool `_meta` is `{"fastmcp": {"tags": []}}`.
- **Remediation:** milestone 5 surface pass (decisions row "Lifecycle `_meta`, resource `size`, `$schema` (milestone 5 surface pass)").

**F6**

- **Severity:** Nit (listed; inherited F9)
- **Section:** §4 (`[4.triage-metadata]`)
- **Summary:** Resources declare no `size`, including the new `opendata-atlas://contributing` (13,947 bytes).
- **Evidence:** `resources/list`.
- **Remediation:** same row as F5.

**F7**

- **Severity:** Nit (listed; inherited F10)
- **Section:** §3 (`[3.dialect]`)
- **Summary:** No schema declares `$schema`.
- **Evidence:** `tools/list`.
- **Remediation:** same row as F5.

No Critical or Major findings.

**Outside the standards (gate).**

- The live run (`uv run pytest --run-integration -m integration`, 2026-10-19 03:39 UTC) passed 43 tests, with 1 xfail (data.oregon.gov page 2, as recorded) and 1 skip (the curation test, opt-in).
- One drift case was `inconclusive`: SPD Call Data's `diurnal_peak` probe returned `query_timeout` upstream, while its `dst_gap` passed. That is the designed outcome for a failed probe (Review Focus 1), so the merge recorded `inconclusive`.
- So the full integration run did not pass cleanly: it had 1 failure, that upstream `query_timeout`. Rerun alone (`tests/test_drift.py -k 33kz-ixgy-cad_event_original_time_queued-timezone`), the case passed. The full suite was not re-run. `validation.json` now holds 8 `passed` Seattle entries, `checked_at` 2026-10-19 (the run's UTC date). That claim's `previous_outcome` is `inconclusive`, which the release gate does not count as twice running.

### Probes

| Probe | Evidence |
| --- | --- |
| Cold start | **Measured:** `instructions` is 1,797 characters, identical on both eras: scope, the full-contract pointer, the sentinel check, negative scope, 13 rules, and the sentinel last. The whole string is inside the shortest measured client prefix (2,048 characters; `decisions/006-instructions-prefix.md`). This review left it unchanged. **Not checked:** a live sentinel session on a target client. |
| First repair | 16 forced errors (scratch probe, wire as received). `page_size: 900` → `invalid_argument`, field `page_size`. `portal: "nope.example"` → `portal_not_found`, repair `atlas_find_portals({})`, no echo. Missing or malformed `portal` → `invalid_argument`, field `portal`, the same repair. Garbage cursors: query, search and find_portals → `invalid_cursor`, field `cursor`, repair `read_paging`; describe → field `column_cursor`; reference → `list_items` (F3). `topic: "guides"` without `portal`, and `soql` with one → `invalid_argument`, field `portal`, repair `{}`. `capabilities` with `item_id` → `fields: ["topic", "item_id"]`. Unknown soql item → `reference_not_found`, field `item_id`, repair to the soql index. In every case `content[0].text` parsed equal to `structuredContent`, and `retry_after_ms` was present. |
| Tool selection | Five tools, unchanged names. Reference paging adds `cursor` to `atlas_get_reference` only; its description says "With cursor, repeat only topic and, for guides, portal." |
| Advertised vs actual | The fixture tests validate successes against `outputSchema`: query results with `hints` (`tests/test_query.py`, its `q` helper), Fire 911's describe with `unit_of_observation` (`tests/test_knowledge.py`), and the published `validation` values (`tests/test_freshness.py`). Tool errors carry `isError: true` with the envelope in `structuredContent`. Resource errors are JSON-RPC `-32602` with `machine_code`, `human_message` and `details.field: "uri"` (4 URIs). |
| Discovery cost | `tools/list`: 24,421 bytes (modern, as `tests/test_contract.py` measures) and 23,741 (legacy), against 24,576: 155 bytes of headroom. Per tool (modern): find_portals 3,312, search 4,430, describe 7,718, query 5,933, get_reference 2,275. Unchanged by this review. |
| Capability gating | Both eras advertise `resources` (no subscribe, no listChanged), `tools` (no listChanged) and `completions`; no prompts, logging or extensions. No client capability is required. |
| Security boundary | Every tool is `readOnlyHint: true`; search, describe and query are `openWorldHint: true`, find_portals and get_reference `false`. The first head rule treats dataset text as publisher data. A hint's `alternative` echoes at most 80 characters of the agent's own literal. |
| Cross-version | No fingerprint (deferred under `[9.fingerprint]`). Over the milestone, `tests/snapshots/tools_list.json` changed in Tasks 3 (`fe6afbe`, `7268b83`), 5 (`54adaa1`), 7 (`d7e65f7`) and 9 (`07d4284`) only, each named in CHANGELOG. |
| Resource freshness | Lists and reads carry `ttlMs: 3600000`, `cacheScope: "public"`. Bodies are static per process. |
| Long-running operation | Skipped: none defined. |

### Coverage

| Section | Status | Notes |
| --- | --- | --- |
| §1 Server-Level | OK | Unchanged from milestone 2: name, title, icon, stdio, revision target, credential modes, cursors as declared state handles (1 h, portal-bound; reference cursors bind the topic, guides portal and an entry fingerprint). |
| §2 Discovery | findings F1, F4 | Otherwise OK. Capability summary as a resource and a tool fallback; sentinel pinned last; every head rule restated under `## Rules`; the index lists `contributing`. |
| §3 Tools | findings F1, F7 | Otherwise OK. Closed input schemas; `hints` reuses the repair shape, so one next-step vocabulary serves errors and success results. |
| §4 Resources | finding F6 | Otherwise OK. `contributing` is a markdown body under `opendata-atlas://contributing` with a tool fallback; resources list every entry (no cursor). |
| §5 Prompts | not-applicable | No prompts and no prompts capability. |
| §6 Failure Recovery | finding F3 | Otherwise OK. Reference cursor mismatches name `topic` or `portal` and repair to the cursor's own continuation (rulings 50, 51). The capability summary's cursor rule contradicted that repair (Part 2, S-1). |
| §7 Long-Running Operations | not-applicable | No operation outlives a request. |
| §8 Token Efficiency | finding F2 | Otherwise OK. Every tool's largest result is tested against its measure (`tests/test_budget.py`); reference entry lists page; the hint is never trimmed and costs nothing on a page that matched. |
| §9 Versioning | finding F5 | Otherwise OK. Deterministic order; every snapshot change named in CHANGELOG. |

**Residual risks:**

- `tools/list` has 155 bytes of headroom, so any milestone 4 description change must buy its bytes.
- No live client session checked the instructions prefix.
- The milestone 3 eval run graded the notice wording before this review changed it (Part 2, S-2, A-1 to A-3). No paid run re-graded it.

## Part 2: separating-context-from-constraints

### Targets and classification

| Target | Surface class | Result |
| --- | --- | --- |
| Served `instructions` (1,797 characters) | compact (one field) | S-3 (listed) |
| Capability summary (served) | long-form | S-1, S-4, S-5, S-6 |
| The five tool descriptions and their parameter descriptions | compact | clean |
| 6 resource and 5 template descriptions | compact | clean |
| Hint `alternative` and `knowledge_notice` messages (`portals/knowledge.py`, `core/query.py`) | compact (one field each) | S-2; accuracy A-1, A-2, A-3 |
| `CONTRIBUTING-portals.md` (and its served copy) | long-form | S-8 |
| `skills/curate-portal/SKILL.md` (frontmatter and body) | compact and long-form | clean |
| `AGENTS.md` | long-form | accuracy A-8 |
| `docs/design.md` | long-form | S-7; accuracy A-4, A-5, A-6, A-7 |

**`docs/design.md` coverage.** The sections milestone 3 changed (per `git diff 4d61a9d..HEAD`) were read in full: Knowledge levels, Fact model, Validation state and freshness, Place fields, Tools, Continuation, Instructions head rules, Building knowledge (profiler, drift checks, contribution path, curation runbook, per-portal eval tasks, knowledge-gap reports), Byte budgets, Evals and Milestones. The rest was skimmed.

### Findings

**S-1**

- **Rule:** R5
- **Location:** capability summary `## Rules`: the cursor rule against "Follow repair when present."
- **Quoted text:** "On `cursor_expired` or `invalid_cursor`, resend the first-page call with all its original arguments and no `cursor` or `column_cursor`; never restart with fewer arguments."
- **Why it fails:** Since Task 9 (rulings 50, 51), an `atlas_get_reference` cursor sent with an omitted or different `topic` is `invalid_cursor` whose repair continues the walk (`continue_paging`). The two rules prescribe incompatible calls on that input, and nothing says which wins. Task 9's reviewer named an omitted `topic` the likeliest mistake. On it, "all its original arguments" holds no topic, so the restart reads the index: a different question.
- **Severity:** Material
- **Suggested rewrite:** "On `cursor_expired` or `invalid_cursor`, follow a `continue_paging` repair when one is given; otherwise resend the first-page call with all its original arguments and no `cursor` or `column_cursor`; never restart with fewer arguments."
- **Status:** Fixed. Regression: `tests/test_standards_m3.py::test_cursor_restart_rule_defers_to_a_continuation_repair`. Fix round 1 closed the residual: on a `read_paging` repair, "Follow repair when present" and "otherwise resend" still named two calls with no order. The rule now reads "…follow the repair: `continue_paging` continues the same walk, and `list_items` restarts the topic. After a `read_paging` repair, resend the first-page call…", so every cursor error follows its repair first (`::test_cursor_rule_follows_every_repair_before_restarting`).

**S-2**

- **Rule:** R3 (secondary R1); carried from the Task 6 review
- **Location:** `knowledge_notice` text-column sentence (`portals/knowledge._text_sentence`)
- **Quoted text:** "…are not reviewed place fields; if one stands for an area, say its meaning and completeness are unverified."
- **Why it fails:** Whether a column "stands for an area" is a judgment no output settles. The sibling sentence says "say in the answer", and this one does not say where.
- **Severity:** Minor
- **Suggested rewrite:** "…; if your answer uses it as an area, say in the answer that its meaning and completeness are unverified." The trigger is now the answer's own use, which a grader can check.
- **Status:** Fixed. Regression: `tests/test_standards_m3.py::test_text_sentence_reads_in_the_singular_for_one_column` and `::…_plural_for_several_columns`.

**S-3**

- **Rule:** R2 (secondary R1); carried from the Task 10 review
- **Location:** `instructions` head rule
- **Quoted text:** "Offer the user a defect or knowledge-gap issue (capabilities ## Defects, ## Knowledge gaps)."
- **Why it fails:** On its own line, "a defect" does not say whose: milestone 2's wording said "a server defect".
- **Severity:** Minor
- **Suggested rewrite:** "Offer the user a server-defect or knowledge-gap issue (capabilities ## Defects, ## Knowledge gaps)."
- **Status:** Listed, not fixed. The rewrite costs 7 characters, and `instructions` has 3 left (ruling 23 forbids raising the cap). Only rewording another inherited rule would pay for it. The same line names `## Defects`, which defines a defect in this server and lists the publisher's data as not one. The milestone 3 eval graded the offer with this wording (task 31, 3 of 3). The trade is recorded in the decisions row "Milestone 3 standards review".

**S-4**

- **Rule:** R2; Task 10 review
- **Location:** capability summary `## Knowledge gaps`
- **Quoted text:** "Label: issues carry the `knowledge-gap` label, which is the curation queue."
- **Why it fails:** It is a fact in a list of obligations, with no actor. The agent only offers the issue, and the user files it.
- **Severity:** Minor
- **Suggested rewrite:** "In an issue you offer, name the `knowledge-gap` label; maintainers read that label as the curation queue."
- **Status:** Fixed.

**S-5**

- **Rule:** R1; Task 10 review
- **Location:** `## Knowledge gaps`
- **Quoted text:** "Include: portal id, dataset id, column, and what was wrong."
- **Why it fails:** It is a labeled fragment, so its strength and its object are implicit.
- **Severity:** Minor
- **Suggested rewrite:** "In an issue you offer, include portal id, dataset id, column, and what was wrong."
- **Status:** Fixed.

**S-6**

- **Rule:** R4; Task 10 review
- **Location:** `## Knowledge gaps`
- **Quoted text:** "Report to the tracker under ## Defects. It is public: offer the issue, never file it unasked."
- **Why it fails:** It points at another section for the URL, and it states two obligations behind a vague reference. Task 10's test never asserted "unasked" in the section.
- **Severity:** Minor
- **Suggested rewrite:** "Report to: <issues URL>, the tracker under ## Defects. It is public: offer the issue, never file it unasked."
- **Status:** Fixed. Regression: `tests/test_standards_m3.py::test_knowledge_gaps_section_states_its_obligations_in_full` (also covers S-4 and S-5).

**S-7**

- **Rule:** R4; Task 2 carry
- **Location:** `docs/design.md`, Validation state and freshness, first item
- **Quoted text:** one item holding the file's role, its schema, its write format, and its load errors.
- **Why it fails:** Four independently checkable rules share one item.
- **Severity:** Minor
- **Suggested rewrite:** a labeled item with one sub-item each; every sentence is kept.
- **Status:** Fixed.

**S-8**

- **Rule:** R5
- **Location:** `CONTRIBUTING-portals.md`, step 11.3 against step 12
- **Quoted text:** "Treat a failure first as a knowledge gap (a missing or wrong claim) and fix the pack" / "across the 3 eval runs of step 11, every task grades PASS in at least 2 runs"
- **Why it fails:** After a pack fix, nothing says whether the earlier runs still count toward promotion.
- **Severity:** Minor
- **Suggested rewrite (author decision, taken as Claude's call):** (a) "After any pack change, rerun step 11 from its first check: step 12 counts only the 3 eval runs made on the pack you submit." (b) Runs before the change still count. The fix takes (a), because a grade on an earlier pack says nothing about the one submitted. The skill is unaffected: its rule 13 forbids pack changes once the runs start, and its rule 17 lets rule 13 win.
- **Status:** Fixed in both copies (`tests/test_contributing.py` keeps them identical).

**Outside R1–R5 (accuracy):**

- **A-1 (Minor, fixed; Task 6 carry).** The text-column sentence read "Text column(s) … are" for a single column. It is now singular or plural.
- **A-2 (Minor, fixed; Task 6 carry).** A filtered text column that is itself an unreviewed place field was named twice: once as a place field with no reviewed claim, and again as not a reviewed place field. It is now named once. Regression: `tests/test_standards_m3.py::test_text_sentence_skips_a_column_already_named_as_a_place_gap` and `::test_text_sentence_keeps_columns_not_named_as_place_gaps`.
- **A-3 (Minor, fixed; found by this review's test).**
  - The notice's gap sentence read "say in the answer that area breakdowns is unverified", and the same for "timestamp timezones": the verb counted effects, not their grammatical number.
  - Only "what each row counts" takes "is" now.
  - Regression: `tests/test_standards_m3.py::test_gap_sentence_verb_agrees_with_a_plural_effect`.
  - `tests/test_knowledge.py:383` ("what each row counts is unverified") still passes, the known positive.
- **A-4 (Minor, fixed; Task 6 carry).**
  - `docs/design.md` (Place fields, Tools 4) and CHANGELOG said the text-column sentence fires while no place field has a "reviewed, non-stale claim".
  - The code (`knowledge._reviewed`) counts a stale `partial` claim as reviewed, because only a degraded claim stops counting.
  - Both now say "a reviewed claim the freshness rule does not degrade".
- **A-5 (Minor, fixed; Task 13 carry).** The design's Drift checks said the integration session runs "every guide example". `tests/test_live.py` runs Seattle's only. The text now says so, and names where a new pack's examples run: the curation test, and step 8 by hand.
- **A-6 (Minor, fixed; Task 1 carry).**
  - The checker catalog did not say that `share_by_group` returns `contradicted` on one out-of-bounds group before it checks `min_groups` (`checkers.py:162`).
  - Nor did it say that a missing or unparseable metadata field, or a non-object, is `inconclusive` (`checkers.py:272-309`).
  - Both are documented now.
- **A-7 (Minor, fixed; Task 9 review M4).**
  - Byte Budgets gave figures from before Tasks 9 and 15.
  - Measured now with `tests/test_budget.py`'s measures:
    - envelope overhead 759 bytes on both the index and the widest query page;
    - `query_wide_rows` 23,610 bytes framed (was 23,342);
    - `errors/codes` 11,886 payload and 26,545 framed (was 11,850 and 26,473);
    - Fire 911 `full` 14,129 and 31,678, unchanged.
  - CHANGELOG's 11,850 is corrected too.
- **A-8 (Minor, fixed; revised in fix round 1 by ruling 71).**
  - `AGENTS.md` did not say that the live session is the drift run and rewrites `validation.json`, nor that the curation test is opt-in. `## Context` now states both.
  - `## Rules` gains a paid-run rule, scoped by ruling 71: "Start a paid run (`tests/test_curation_skill.py` with its `ATLAS_RUN_CURATION=1` opt-in, or `evals/run.py` with an out directory) only when the maintainer asks. A curation run the maintainer started counts as asked for the curate-portal skill's own step 11.3 eval runs." The first wording had no such scope, so it conflicted (R5) with the skill's step 11.3, which a headless curating agent loads with `AGENTS.md` through `CLAUDE.md`. The skill's rule 17 now cites the rule. Decisions row "Paid-run rule in `AGENTS.md` (ruling 71)" (Claude's call; maintainer to confirm).
  - `## Rules` also gains: commit a regenerated `validation.json` only from a drift run you intended to record.

**Fix round 1 (task review Minors).** The Hints item now says hints *can* appear, and names the exceptions: a negated equality, a `where` that reads a select alias, and a repair over the clause cap. The `## Knowledge gaps` "Report to:" fragment is now "The tracker is <URL> (also under ## Defects)". The notice's verb agreement is keyed on each effect's grammatical number, not on a literal. Design's promotion rule says "on the submitted pack". The Chicago carry-over item is marked **Deferred**.

**Safety note:** none. No target contained instructions aimed at the auditor.

### Summary

| Rule | Count |
| --- | --- |
| R1 | 3 (S-2, S-3, S-5) |
| R2 | 2 (S-3, S-4) |
| R3 | 1 (S-2) |
| R4 | 2 (S-6, S-7) |
| R5 | 2 (S-1, S-8) |

| Severity | Count |
| --- | --- |
| Material | 1 (S-1) |
| Minor | 7 |

Outside R1–R5: eight Minor (A-1 to A-8), all fixed.

**Assessment.** The surfaces milestone 3 added keep their rules apart from context. `CONTRIBUTING-portals.md` has a labeled `### Rules` list, and the curation skill states 25 numbered rules with explicit precedence. The tool and resource descriptions are unchanged and clean. The one Material defect was a precedence gap: milestone 3 added a reference repair that continues a cursor walk, while the capability summary's older cursor rule still said to restart at page one. That rule now defers to the repair. Of the Minor findings, all but one are fixed. The exception is the head rule's "a defect" (S-3), which would cost `instructions` characters the cap does not allow, and is kept with its reason recorded. No Material finding is open.
