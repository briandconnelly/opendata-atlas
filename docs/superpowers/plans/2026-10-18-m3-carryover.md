# Carry-over from milestone 2 into the milestone 3 plan

Inputs the milestone 3 plan must account for, collected during milestone 2 (branch `feat/portal-surface`, 2026-10-18) and by its standards review (`docs/reviews/2026-10-18-m2-standards.md`). Each item names its source. The milestone 3 plan either schedules it or records a decision not to.

**Reconciled 2026-10-18** (milestone 3 Task 16, `docs/reviews/2026-10-18-m3-standards.md`). Each item ends with its status: **Done** names the task and commit; **Deferred** names the `docs/decisions.md` row that defers it.

## User decision before the repo goes public

- **Owner and contact identities in inherited fixtures.** `tests/fixtures/` holds 76 occurrences of 7 distinct `@seattle.gov` email addresses across 21 files. They sit in `/api/views` owner and contact metadata (`screenName`, `displayName`, `contact_email` and similar), mostly inherited from seattle-open-data's fixtures; milestone 2 Task 9 (`1f53550`) added 6 occurrences. It is public publisher metadata, but it names people. **The maintainer decides whether to scrub them before the repository is made public.** Nothing is scrubbed until then. Counted 2026-10-18 with `grep -rhoi "[A-Za-z0-9._%+-]*@seattle\.gov" tests/fixtures`. `docs/evidence/` holds none: milestone 2 rulings 25 and 27 redact saved bodies. **Deferred** (decisions row "Inherited fixture identities (maintainer's decision)"; recounted 2026-10-18: unchanged).

## Knowledge (milestone 3 scope)

- **Padded text values give a silent zero.** On data.lacity.org, `area_name` values carry trailing spaces (`'Hollywood   '`), so `area_name = 'Hollywood'` returns 0 rows: a false zero with no warning (milestone 2 Task 15, eval run). Options: a placeholder or padding claim in the profiler's output, or a server hint when an equality filter on a text column returns 0 rows. **Done:** both. Task 1 (`53b3e2f`) adds the `padded_values` kind and Task 11 (`fe931d3`) has the profiler emit it; Task 7 (`d7e65f7`, `7b4af20`) adds the zero-match `hints`.
- **`knowledge_notice` does not name text place columns.** On a dataset with no reviewed place field, the notice fires for the dataset but does not say which text column the agent filtered as a place (for example LA `area_name`), so the caveat is generic (Task 15). **Done:** Task 6 (`1d394eb`) names filtered text columns; Task 15 (`b1ee5bd`, `f13583a`; rulings 69, 70) adds grouped and aliased ones; this review (Task 16) fixes the sentence's wording.
- **Fire 911: "most calls are medical" (eval 03).** The Seattle guide's `type` line already says it (inherited from seattle-open-data), and the guide index description says "most are medical, not fires". Yet the milestone 2 run graded `03-fire-capitol-hill` PARTIAL for not saying it, as in the baseline: agents do not read the guide on that task. Serve the fact where the query path sees it (for example a reviewed unit-of-observation claim's reason, or a describe note), then re-run 03. **Done:** Task 5 (`54adaa1`, `04dfd0a`, `772b8ce`) serves describe's `unit_of_observation` from a reviewed, asserted claim; the milestone 3 run graded 03 PASS (Task 15, `b1ee5bd`).
- **Eval 14's 2025-relevant `expect`.** Done in milestone 2 Task 15 (`fa70b88`): it now expects the 2025 unassigned share (1–4% since 2017). Listed only so the controller's list is accounted for; no milestone 3 work. **Done** (milestone 2, `fa70b88`).
- **Freshness and `validation.json`.** Moved from milestone 2 by the decisions row "Freshness milestone". Milestone 2 reports `validation: "unchecked"` for every claim and degrades none. **Done:** Task 2 (`d383194`) writes `validation.json`; Task 3 (`fe6afbe`, `752f429`, `7268b83`) degrades stale claims at runtime; Task 4 (`a115f56`, `851a4e6`) adds the release gate.
- **Knowledge-gap head rule.** The design's three obligations (head rule, capability `## Knowledge gaps`, `knowledge-gap` label) arrive with knowledge-gap reports in milestone 3. `tests/test_reference_topics.py::test_knowledge_gap_rule_waits_for_milestone_3` pins their absence until then. The instructions are 1,778 of 1,800 characters (ruling 23), so the head rule must fit in 22 characters or displace text. **Done:** Task 10 (`37b0447`): the head rule, `## Knowledge gaps` and the label, with line 1 shortened (1,797 characters); ruling 68 (`b1ee5bd`) restates the offer in every fired notice.
- **Seattle per-column place probes** (from the milestone 2 carry-over): four Seattle place fields (tazs-3rd5, ppi5-g2bj `sector`/`beat`) rest on the fork's general verified statement; the drift probes should add per-column probes. **Done:** Task 2 (`d383194`; decisions row "Seattle per-column place probes (milestone 2 carry-over, closed)").
- **`describe._time` evidence pick** (from the milestone 2 carry-over): it serves `evidence[0]`, while `tests/test_guides.py` picks the first `manual_observation`. Reconcile when probe evidence arrives. **Done:** Task 2 (`d383194`; decisions row "`describe._time` evidence pick (milestone 2 carry-over, closed)").

## Design artifacts not built yet

`docs/design.md` names these in the present tense; each is now marked "not built yet":

- `tests/test_tiers.py` (Knowledge levels): the tier conditions decidable from pack contents. **Done:** Task 13 (`cce5908`).
- `docs/pack-examples/` (Fact model): one example per claim kind. **Done:** Task 1 (`53b3e2f`).
- Byte-budget fixtures for a portal with 100 guides and a 2,000-entry registry page (Byte budgets). The 300-column fixture exists (Task 10). **Done:** Task 9 (`07d4284`).

`grep -n "not built yet" docs/design.md` finds the marker at `4d61a9d` (lines 144 and 361, the known positive) and nothing at Task 16.

## From the milestone 2 standards review (listed, not fixed)

- **One result-budget unit (ruling 19, review finding F6).** Query measures `wire_size` (text copy plus `structuredContent`), describe `payload_size` (`structuredContent` alone), and reference and `atlas_find_portals` results are not measured. `atlas_get_reference({topic: "errors", item_id: "codes"})` is 26,388 bytes on the modern wire and 11,829 bytes of `structuredContent`. Recommendation: one unit for every tool, `payload_size`, with a test over each tool's largest result. Moving query to it changes how many rows a byte-trimmed page holds, so it needs its own decisions row. **Done:** Task 8 (`647ab84`, `d90e9aa`; ruling 35, decisions row "Result budget measures (ruling 35, carry-over F6)"): one guarantee with two measures, and every tool's largest result is tested.
- **Envelope reserve vs the modern `serverInfo` stamp (F6).** `core/budget.ENVELOPE_RESERVE` is 512 bytes. Every 2026-07-28 result carries a 666-byte `_meta` `io.modelcontextprotocol/serverInfo` stamp (the SDK adds it), mostly the 560-byte data-URI icon. A query page packed to `RESULT_LIMIT` could therefore exceed 24,576 bytes on the modern wire by about 187 bytes, plus about 36 bytes of JSON-RPC frame (`jsonrpc`, `id`, `result`). The client receives 699 bytes more than `wire_size` counts: the 676-byte `_meta` member and 23 bytes of other protocol fields (milestone 2 final review; it was given as about 176). This is computed, not observed: the widest fixture page is 23,299 bytes. Fix with the budget unit above: a reserve that covers the stamp, or a smaller icon. **Done:** Task 8 (`647ab84`): the reserve is 1,024 bytes and covers the 759 bytes measured outside `content` and `structuredContent`.
- **Icon bytes on every modern result (F7).** The same stamp makes the modern `tools/list` 23,582 bytes against 22,902 on the legacy handshake. Option: serve the icon by `https` URL once the repository is public (milestone 5), or minify the SVG. **Deferred** (decisions row "Icon by URL, README status word, release-cut test (milestone 5)").
- **Per-record lifecycle metadata (F8, `[9.tier-metadata]`).** The `preview` stability tier is stated only in the capability summary's `## Context`, not under a `_meta` lifecycle key on each tool, resource and template. **Deferred** (decisions row "Lifecycle `_meta`, resource `size`, `$schema` (milestone 5 surface pass)").
- **Resource `size` (F9, `[4.triage-metadata]`).** Static resources could declare `size`. **Deferred** (same row).
- **Schema dialect (F10, `[3.dialect]`).** Input and output schemas carry no `$schema` (inherited). **Deferred** (same row).
- **README status word.** The README says "alpha"; the capability summary says "preview". Pick one at the release cut. **Deferred** (decisions row "Icon by URL, README status word, release-cut test (milestone 5)").

## Deferred milestone 2 carry-over items (decisions rows)

- Token probe and `SOCRATA_APP_TOKENS` (row "Token probe (milestone 2 carry-over)"). **Deferred** (decisions row "Token probe (milestone 3 carry-over)").
- Eval gate single-run noise (row "Eval gate noise (milestone 2 carry-over)"); the per-portal eval runner is milestone 3 scope. **Done:** Task 12 (`d16d928`, `caac5f7`) runs eval files per portal, and Task 15's gate (2 of 3 runs; decisions row "Milestone 3 eval run (Task 15)") closes the noise row.
- `Portal.guides_by_id` is still unused in `src/` (row "`guides_by_id` (milestone 2 carry-over)"). **Deferred:** left as is (decisions row "`guides_by_id` (milestone 3 carry-over)").
- `tests/test_versioning.py` asserts `## [Unreleased]`; update it at the first release cut, milestone 5 (row "Release-cut test (milestone 2 carry-over)"). **Deferred** (decisions row "Icon by URL, README status word, release-cut test (milestone 5)").

## Out of scope for milestone 3 (decisions rows)

- Chicago curation: milestone 4. **Deferred** (decisions row "Chicago curation (milestone 4)").
