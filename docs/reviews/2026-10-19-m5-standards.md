# Milestone 5 standards review (2026-10-19)

Branch `feat/release-prep`, the surface diff `docs/design..feat/release-prep` (from `31a1617` to `2af3256`) plus this review's fix. Milestone 5 is release prep: nothing is published. The branch was reviewed against two standards:

- `agent-friendly-mcp` (`references/review-workflow.md`, standard `references/contract-checklist.md`);
- `separating-context-from-constraints` (R1–R5).

The served surface was read through the in-process `fastmcp.Client(build_server())`, on the modern era (2026-07-28) and the legacy handshake (`mode="legacy"`):

- `tools/list`, `serverInfo`, `instructions`;
- `resources/list` with each static resource read back, and `resources/templates/list`;
- `atlas_get_reference` for topic `guides` with `portal: "seattle"` (a portal-bound `source`), the index (a portal-independent `source`), topic `soql` item `dates`, and a forced `portal_not_found`.

Scripts and output are in `docs/evidence/standards-m5-2026-10-19/`:

- `surface.py.txt` and `surface.json`: the served surface;
- `allow.py.txt` and `allow.out.jsonl`: resource `size` under `OPENDATA_ATLAS_PORTALS` unset, `seattle` and `nope.example`;
- `variants.py.txt` and `variants.out.txt`: the plan's injection measure, rerun for F8 and F10. Its first line's "after icon" figure is the planning-time formula and means nothing on this head, where the icon saving is already in the base;
- `strict.py.txt` and `strict.out.txt`: what an enum on `now_weekday` would cost;
- `dow-probe.sh.txt` and `dow-probe.json`: one live, free SoQL query (F1);
- `measure.py.txt` and `measure.out.txt`: the final figures;
- `codex-exec-help-counts.txt`: the Codex host re-check.

Severity mapping for the counts: Critical and Major count as Material, Minor and Nit count as Minor.

## Part 1: agent-friendly-mcp

### Route

**Focused route.** The surface changes are these:

- `source.now_weekday`: a new output field in the five output schemas;
- the capability summary's weekday rule (`## Rules`) and Time line (`## Semantics`), and one line in the `dates` topic;
- the minified icon in `serverInfo.icons`;
- `size` on the six static resources in `resources/list`.

Task 4's describe budget change was dropped (ruling 93), so describe's code and description are unchanged; its stated deadline was still checked against the evidence Task 4 recorded.

Named sections:

- §1, for the icon (`[1.display-metadata]`, `[1.metadata-contract]`);
- §2, for the capability summary's rule (`[2.summary]`, `[2.rules-then-context]`);
- §3, for `now_weekday` (`[3.strict-types]`, `[3.advertised-fields]`) and `$schema` (`[3.dialect]`);
- §4, for `size` (`[4.triage-metadata]`);
- §7, for describe's deadline (`[7.declare-duration]`);
- §9, for lifecycle `_meta` (`[9.tier-metadata]`) and the output addition (`[9.additive-direction]`).

`[1.spec-revision]` and the native-vs-convention rule (SKILL.md) were read first, and the named sections were read in full. Closing over the cited ids pulled in only `[8.cacheable-results]`, cited by `[4.subscriptions]`, `[9.list-changed]` and `[9.additive-direction]`. That is one section beyond those named, so the review did not escalate to the full walk.

**Protocol target (`[1.spec-revision]`).** Unchanged: the capability summary declares MCP 2026-07-28, compatible with 2025-11-25, with no extensions required. Both eras served the same tools, the same icon and the same resources, and the legacy `instructions` equal `INSTRUCTIONS`.

### Findings

**F1**

- **Severity:** Major (Material). **Fixed** in 3562456, test first.
- **Section:** §2 (`[2.summary]`), §3 (`[3.descriptions]` by analogy: the rule is the only served place that tells an agent which function to use)
- **Summary:** The weekday rule sent agents to `date_extract_dow` without its numbering, so an agent mapping the returned number to a name had to guess the convention.
- **Evidence:**
  - `src/opendata_atlas/core/reference.py:141`, before the fix: "Name a weekday only from the data (`date_extract_dow` on the date column) or, for today, from `source.now_weekday`; never work a weekday out yourself."
  - Probed live (`dow-probe.json`): `date_extract_dow` returns the string `"0"` for Sunday, 2026-10-11, through `"6"` for Saturday, 2026-10-17. Python's `date.weekday()` numbers Monday 0. An agent that assumes the Python convention names every weekday one day off. That is the slip the rule exists to stop: weekday labels off by one in 3 of 6 milestone 4 task-03 answers.
  - The numbering was served only in the `dates` topic (`reference.py:595`, "(0 = Sunday)"), which an agent following the capability rule need not read.
  - No transcript shows an agent mis-mapping `date_extract_dow`. Without that, the defect stays at Major, not Critical.
- **Remediation, as applied:** the rule now reads "(`date_extract_dow` on the date column, 0 = Sunday)". `tests/test_reference_topics.py::test_weekday_rule_gives_date_extract_dow_numbering` failed before the change (RED) and passes after it. The fact is recorded in `docs/upstream-facts.md` ("Weekday numbering of `date_extract_dow`"). The capability summary grows 12 bytes, from 10,559 to 10,571 (`surface.json`). The commit message says 13; that figure is wrong, and the commit is not amended. `tools/list` and `INSTRUCTIONS` are unchanged.

**F2**

- **Severity:** Minor. **Deferred.**
- **Section:** §3 (`[3.strict-types]`)
- **Summary:** `source.now_weekday` is a free `string` although its value set is fixed, and no served surface names the set.
- **Evidence:**
  - `tests/snapshots/tools_list.json:166` (and the four other output schemas): `"now_weekday": {"type": "string"}`.
  - The capability summary's Time line (`reference.py:150`) says what it means ("today's weekday in the portal's zone") but not its form. The form (`Monday` … `Sunday`, fixed English names) is in `docs/design.md` and `CHANGELOG.md`, which are not served.
  - It is recoverable: every value is a self-describing English day name, and `src/opendata_atlas/core/context.py` takes it from a fixed tuple (`WEEKDAYS`), never the locale.
- **Remediation:** an enum of the seven names costs **+400 bytes** of `tools/list` (+320 without `type`; `strict.out.txt`) against 16 bytes of headroom, so it does not fit. A cheaper step is to name the form in the capability summary's Time line, which is outside the `tools/list` budget.
- **Reason deferred:** Minor findings are deferred in this task. Decisions row "Weekday beside `now_local` (milestone 5)" already records the no-enum choice. Revisit when a surface change frees bytes.

**F3**

- **Severity:** Minor. **Deferred.**
- **Section:** §7 (`[7.declare-duration]`)
- **Summary:** describe's description says "Typically 1-3 s", but a `full` describe of a large dataset can take far longer, and it does not say that place stats can time out inside the deadline.
- **Evidence:**
  - `src/opendata_atlas/mcp/tools.py:248`: "Typically 1-3 s; fails with query_timeout after 30 s."
  - `docs/evidence/describe-budget-2026-10-19/chicago-crimes.json`, run 2, the shipped fixed 10 s place-stats phase: 17.0 s for Chicago Crimes `detail: "full"`, with 6 of 11 place fields `ok`. That is one run.
  - Timeout behavior is stated: the 30 s deadline and `query_timeout` are in the description, and the capability summary says `values` is absent when `stats_status` is not ok. Partial progress is not observable, and none is promised.
- **Remediation:** when bytes allow, add a `full` bound to the duration clause, measured over more than one run.
- **Reason deferred:** the stated 30 s deadline holds, and the timing is from one run. Any added wording costs `tools/list` bytes, and 16 are left. Task 4's evidence stands (ruling 93).

**F4**

- **Severity:** Nit. **Deferred.**
- **Section:** §4 (`[4.triage-metadata]`)
- **Summary:** the static resources carry `title`, `description`, `mimeType` and now `size`, but no `annotations.lastModified`.
- **Evidence:** `surface.json`, `modern_resources`: `has_lastModified` is false for all six.
- **Reason deferred:** the bodies ship with the package, so the only honest `lastModified` is the build time, which says little an agent can use. `resources/list` carries `ttlMs: 3600000`, `cacheScope: "public"`, which bounds staleness (`[8.cacheable-results]`).

**F5**

- **Severity:** Nit (inherited from milestone 2 F8). **Deferred.**
- **Section:** §9 (`[9.tier-metadata]`)
- **Summary:** no record carries a lifecycle `_meta` key; the `preview` tier is stated only in the capability summary.
- **Evidence:** re-measured on this head (`variants.out.txt`): `io.github.briandconnelly/lifecycle` on the five tools adds **195 bytes** against 16 of headroom.
- **Reason deferred (reason checked, holds):** it does not fit. Every record shares one tier, so a per-record tier tells an agent nothing the summary's `Stability: preview` line does not. The rule keeps the summary as the off-the-shelf client's carrier anyway.

**F6**

- **Severity:** Nit (inherited from milestone 2 F10). **Deferred.**
- **Section:** §3 (`[3.dialect]`)
- **Summary:** no input or output schema declares `$schema`.
- **Evidence:** re-measured (`variants.out.txt`): **+285 bytes** on the five input schemas, +570 with the output schemas, against 16.
- **Reason deferred (reason checked, holds):** it does not fit. The rule says "where supported", and the schemas use only flat, closed constructs (`[3.portable-schema]`), so a validator has little to infer.

### Checked and OK

- **`now_weekday` naming and absence.** The name pairs with `now_local`. It costs 160 bytes, where `now_local_weekday` costs 190 and does not fit (decisions row "Weekday beside `now_local` (milestone 5)"). It is present exactly when `now_local` is (`models.py:53`, `context.py:81`). The probe agrees: a portal-bound `source` has `now_local` and `now_weekday`, and the weekday matches `now_local`'s date; a portal-independent `source` has only `request_id`. `[3.advertised-fields]` is met: the field is conditional, and the capability summary states the condition. Pinned by `tests/test_portal_model.py::test_weekday_is_the_portal_local_day`, `::test_weekday_ahead_of_utc_in_a_positive_offset_zone` and `::test_weekday_absent_without_now_local`.
- **`[9.additive-direction]`.** `now_weekday` is an output addition to closed schemas. Nothing has been published, so no client holds a cached schema; `CHANGELOG.md` says the tool surface changes.
- **Icon (`[1.display-metadata]`).** Both eras serve one icon: `mimeType: "image/svg+xml"`, `sizes: ["any"]`, a 430-character `data:` URI. The `viewBox` is kept, so `sizes: ["any"]` stays honest without the dropped `width`/`height`. Shapes and colors are unchanged (`tests/test_legacy_protocol.py::test_icon_is_minified`). `serverInfo` name, title and version are unchanged (`[1.metadata-contract]`).
- **Resource `size` (`[4.triage-metadata]`).** Each of the six `size` values equals the UTF-8 length of its `resources/read` body, on both eras and under each allowlist value probed. The `portals` index measured 617, 453 and 303 bytes, and each read matched. A bad allowlist entry does not break `resources/list` (`allow.out.jsonl`). The five templates declare no `size`, which is right: a template has no body until a URI is chosen.

### Probes

| Probe | Evidence |
| --- | --- |
| Cold start | **Measured:** `instructions` is 1,797 characters on both eras (cap 1,800), unchanged by milestone 5. **Not checked:** a live session on a target client. |
| First repair | `atlas_get_reference {"topic": "portals", "item_id": "nope.example"}` returns `isError: true`, `portal_not_found`, `details.field: "item_id"` and repair `atlas_find_portals({})`. `content[0].text` parses equal to `structuredContent` on both eras. |
| Advertised vs actual | `now_weekday` appears exactly where `now_local` does. Every resource `size` equals its read. |
| Discovery cost | `tools/list` framed: **24,560 bytes** modern and **23,944** legacy, against 24,576: 16 bytes of headroom. The snapshot changed only in Task 2 (five `now_weekday` insertions), and this review's fix does not touch it. |
| Resource freshness | `resources/list` carries `ttlMs: 3600000` and `cacheScope: "public"`. `size` is computed on each listing, so it follows the environment. |
| Cross-version | No fingerprint (deferred under `[9.fingerprint]`); `now_weekday` is pre-release (above). |
| Long-running operation | describe states a 30 s deadline and `query_timeout`. F3 covers its typical duration. |
| Tool selection | Skipped: no tool name or description changed. |
| Capability gating | Skipped: no capability changed. |
| Security boundary | Skipped: no tool or annotation changed. |

### Coverage

| Section | Status | Notes |
| --- | --- | --- |
| §1 Server-Level | OK | Icon and `serverInfo` as above; `[1.spec-revision]` unchanged. |
| §2 Discovery | finding F1 (fixed) | Otherwise OK: `instructions` unchanged at 1,797; the weekday rule lives in the capability summary only, as design (Instructions length, ruling 23) places rules whose payload describes itself. |
| §3 Tools | findings F2, F6 | Otherwise OK: `[3.advertised-fields]`, `[3.closed-schemas]` (the `source` object stays `additionalProperties: false`). |
| §4 Resources | finding F4 | `size` OK, as above. |
| §5 Prompts | not-checked | Focused route; there are no prompts. |
| §6 Failure Recovery | not-checked | Focused route; one forced error was read (First repair). |
| §7 Long-Running Operations | finding F3 | describe's deadline is stated; no task or progress is defined. |
| §8 Token Efficiency | not-checked | Focused route; only `[8.cacheable-results]` was read, by closure (OK). |
| §9 Versioning | finding F5 | Otherwise OK: deterministic order (`tests/test_contract.py::test_listing_is_deterministic`); every surface change has a CHANGELOG line. |

**Residual risks:**

- `tools/list` has 16 bytes of headroom, so the next schema change needs bytes freed first.
- No live client session checked the instructions prefix or the icon rendering.
- Desktop's handling of the README snippets and the bundle is untested (`docs/release-checklist.md` step 1).

## Part 2: separating-context-from-constraints

### Targets and classification

| Target | Surface class | Result |
| --- | --- | --- |
| Capability summary `## Rules`, the weekday rule (`reference.py:141`), changed by Task 2 and by F1 | compact item in a long-form document's rule section | clean |
| Capability summary `## Semantics`, the Time line (`reference.py:150`) | compact item in a context section | clean |
| `dates` topic, the weekday line (`reference.py:599`) | compact list item | clean |
| Resource descriptions | compact | unchanged: Task 3 moved the six static resources to `add_static` with the same strings (`surface.json`) |
| Tool descriptions | compact | unchanged: the only snapshot change is the five `now_weekday` schema insertions |
| `docs/release-checklist.md` step 5.2 and 5.3, changed by this task | long-form runbook | clean |
| `docs/design.md`, Time (item 1) and Byte budgets, changed by this task | long-form | clean |

### Findings

None under R1–R5.

- **Weekday rule.** It sits in `## Rules` (R1). "only" and "never" make it mandatory (R2). It can be checked against an answer's weekday and the query that produced it (R3). It states one obligation; the "never" clause restates the "only" (R4). It conflicts with no other rule (R5). The "0 = Sunday" that F1 added is a load-bearing fact the rule needs, inline beside the function it describes.
- **Time line.** It states facts only and sits in `## Semantics`; `tests/test_reference_topics.py::test_weekday_semantics_states_only_the_fact` keeps "never" out of it.
- **`dates` line.** It is an imperative tip in a list of SoQL tips, and its strength is clear from the imperative. The capability rule carries the binding version.
- **Checklist step 5.** The kept-history route now gives the commands in a block, then the check (`git branch --show-current` prints `main`), then "Work in this checkout from now on". Step 3 names the checkout to run in. Each is an imperative instruction with an observable result.

### Outside R1–R5 (accuracy and carried items)

- **A-1 (Minor, noted).** The F1 commit message (3562456) says the capability summary grows 13 bytes; it grows 12. The commit is not amended (no amend, by rule). The figure is right here and in the decisions row.
- **A-2 (Minor, fixed; Task 7 carry).** `docs/release-checklist.md` kept-history route created `main` but never checked it out, while the Rules say to commit on `main`. It now runs `git branch main docs/design` and `git switch main` in `~/projects/opendata-atlas`, and step 3 says which checkout runs `gh repo create`. This was traced in a scratch clone with its remote removed: `git branch --show-current` printed `main`, the step 2 count on `main` printed 76, and a test commit landed on `main`. `gh repo create` was not run.
- **A-3 (Minor, fixed; Task 4 carry).** The Chicago Crimes recording behind the 24,385 and 31,747 B figures was only in the session scratchpad. It is now committed as `docs/evidence/describe-budget-2026-10-19/describe_chicago_crimes_full.json` (114,511 bytes, 21 requests). Its contents are aggregate counts, ward and area labels, and scrubbed view metadata. The checks each ran on a known positive first:
  - `scripts/scrub_fixtures.py --check`: exit 1 on a synthetic owner fixture, then exit 0, `left: {}`, on the recording;
  - the email scan: 1 on `kp-email.txt`, then 0;
  - a phone-number pattern: 1 on a synthetic line, then 0.

  `measure.py.txt` now points `tests.http_fixtures.FIXTURES` at that directory. Rerun with no copy in `tests/fixtures/http/`, it printed `size 31747` with columns and `size 24385` without. The repository's fixture guard covers only `tests/fixtures`, so these checks were run by hand.
- **A-4 (noted).** Decisions row "Weekday beside `now_local` (milestone 5)" still quotes the rule as Task 2 wrote it. The row is history; row "Milestone 5 standards review" records the change, and `docs/design.md` (Time) carries the current wording.

**Safety note:** none. No target held instructions aimed at the auditor.

### Summary

| Rule | Count |
| --- | --- |
| R1 | 0 |
| R2 | 0 |
| R3 | 0 |
| R4 | 0 |
| R5 | 0 |

| Severity | Count |
| --- | --- |
| Material | 0 |
| Minor | 0 |

Outside R1–R5: three Minor items (A-1 to A-3, two fixed and one noted) and one note (A-4).

**Assessment.** Milestone 5's served prose changes are three lines, and each already kept rules and facts apart: the rule is in `## Rules`, the fact in `## Semantics`, and the tip in the `dates` topic. The one defect the two reviews found together was missing content: the rule sent agents to a numbered function without its numbering. That is F1 in Part 1, now fixed.

## Counts

| Review | Material | Minor |
| --- | --- | --- |
| agent-friendly-mcp | 1 (F1, fixed) | 5 (F2, F3, F4, F5, F6; all deferred with reasons) |
| separating-context-from-constraints | 0 | 0 (plus A-1 to A-3 outside R1–R5) |

## Final measures

| Measure | Value | Limit |
| --- | --- | --- |
| `tools/list` framed, modern (2026-07-28) | 24,560 B (24,517 unframed) | 24,576 |
| `tools/list` framed, legacy (2025-11-25) | 23,944 B | 24,576 |
| `INSTRUCTIONS` | 1,797 characters | 1,800 |
| modern `_meta` serverInfo stamp | 602 B (icon `data:` URI 430 characters) | — |
| modern overhead on the reference index | 695 B | 1,024 reserve |
| capability summary | 10,571 B (10,559 before F1) | — |

Source: `measure.out.txt`, `surface.json`, and `uv run pytest tests/test_contract.py::test_tools_list_within_byte_budget tests/test_reference_topics.py::test_instructions_fit_the_ruling_23_limit -s` (2 passed; it printed "tools/list serialized size: 24560 bytes (budget 24576)").
