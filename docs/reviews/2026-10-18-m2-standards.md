# Milestone 2 standards review (2026-10-18)

Branch `feat/portal-surface`, from `e99b930` to `6a179ab` plus this review's fixes. The branch was reviewed against two standards:

- `agent-friendly-mcp` (`references/review-workflow.md`, standard `references/contract-checklist.md`)
- `separating-context-from-constraints` (R1–R5)

Every surface was read as served, through the in-process `fastmcp.Client(build_server())`:

- the legacy handshake (`mode="legacy"`, protocol 2025-11-25): `initialize` (capabilities, `serverInfo`, `instructions`) and `tools/list`;
- the modern era (2026-07-28): `server/discover`, `tools/list`, `resources/list`, `resources/templates/list`, a `resources/read` of every listed resource and of 12 further URIs (11 template instances and one unknown URI), 6 of them failing;
- 16 forced tool errors, and 11 successful `atlas_find_portals` and `atlas_get_reference` calls validated against their `outputSchema`.

The search, describe and query paths were read through the recorded-fixture tests and one live integration run.

Severity mapping for the counts: Critical and Major count as Material, Minor and Nit as Minor.

## Part 1: agent-friendly-mcp

### Route

**Full walk**, §1 to §9, as the plan requires for a milestone that adds a tool, a resource family and new error codes.

**Protocol target (`[1.spec-revision]`).** The capability summary's `## Context` declares "MCP 2026-07-28, compatible with 2025-11-25; no extensions required". The modern client negotiated `2026-07-28`, and `server/discover` lists `supportedVersions: ["2026-07-28"]`. The legacy client negotiated `2025-11-25`. Both eras serve the same tools (`tests/test_legacy_protocol.py`).

### Findings

**F1**

- **Severity:** Major (fixed; carried item 2)
- **Section:** §6, §4 (`[6.details-field]`, `[4.jsonrpc-errors]`)
- **Summary:** A `reference_not_found` on a resource named `details.field: "item_id"`. That is the tool fallback's parameter, and `resources/read` has no such parameter.
- **Evidence:** `resources/read` of `opendata-atlas://soql/nope`, `opendata-atlas://errors/nope` and `opendata-atlas://portals/seattle/guides/nope` each returned JSON-RPC `-32602` with `error.data.details.field: "item_id"`. The portal codes on the same carrier already named `uri`.
- **Remediation (done):** `EnvelopeMiddleware.on_read_resource` (`mcp/server.py`) sets `details.field` to `uri` for every error that leaves through `resources/read`, so no handler can name a tool parameter there. The tool keeps `item_id`. Regression tests: `tests/test_standards_m2.py::test_reference_not_found_on_a_resource_names_uri` (3 URIs) and `::test_reference_not_found_on_the_tool_still_names_item_id`.

**F2**

- **Severity:** Major (fixed)
- **Section:** §6 (`[6.details-field]`)
- **Summary:** `atlas_describe_dataset`'s column-cursor failures named `details.field: "cursor"`, a parameter describe does not take.
- **Evidence:**
  - `atlas_describe_dataset({"portal": "seattle", "dataset_id": "kzjm-xkqj", "column_cursor": "garbage"})` returned `invalid_cursor` with `details.field: "cursor"`, and its `alternative` said "without column_cursor".
  - Every failure in `core/cursor.decode` hard-coded `field="cursor"`.
  - An agent that sends `cursor` to describe gets a second error (`invalid_argument`, unexpected keyword).
- **Remediation (done):** `cursor.decode` takes the published `field`, and describe passes `column_cursor`. Regression: `tests/test_standards_m2.py::test_describe_cursor_errors_name_column_cursor` (malformed, another tool's cursor, another portal's cursor).

**F3**

- **Severity:** Minor (fixed; carried item 1)
- **Section:** §4, §2 (`[4.template-completion]`, `[2.completion]`)
- **Summary:** Five resource templates had no `completion/complete`. The largest value space was `{portal}`: 243 portals and 245 names with aliases.
- **Evidence:**
  - Neither era's capabilities had `completions`.
  - A wrong `{portal}` fails with `portal_not_found` and an `atlas_find_portals` repair. The tool fallback (`[4.tool-fallback]`) does reach every value, so no demonstrated task failure: Minor.
- **Remediation (done):**
  - FastMCP 4.1's `add_completion_handler` registers `completion/complete` and declares the capability on both eras.
  - `mcp/resources.complete` completes `{portal}` on the three portal templates: the aliases, then the canonical ids, each sorted, restricted to active portals the allowlist enables.
  - It also completes `{section_id}` on `soql` and `errors`, and `{guide_id}` when `portal` is among the context arguments.
  - Matching is a case-insensitive prefix, capped at 100 values (the protocol's cap) with `total` and `hasMore`.
  - The capability summary's `## Context` and `docs/design.md` (Resources) state it.
  - Regression: 9 tests in `tests/test_standards_m2.py`, among them both eras, the cap (`total` 245, `hasMore`), the allowlist, and a guide completion with no portal or a bad one.

**F4**

- **Severity:** Minor (fixed)
- **Section:** §1, §2 (`[1.negotiated-caps]`, `[2.discover-first]`)
- **Summary:** Both eras advertised `logging: {}`, but the server never sends a log message to the client. Logging is also deprecated in 2026-07-28 (SKILL.md Spec Baseline).
- **Evidence:** `server/discover` and `initialize` capabilities: `{"logging": {}, "resources": {...}, "tools": {...}}`. FastMCP registers `logging/setLevel` on every server, and the SDK derives the capability from that handler. `src/opendata_atlas/mcp/` has no `ctx.log`.
- **Remediation (done):** `_advertise_fixed_surface` removes the `logging/setLevel` handler, the same way it removes the prompt handlers. Regression: `tests/test_standards_m2.py::test_logging_is_not_advertised` (both eras).

**F5**

- **Severity:** Minor (fixed)
- **Section:** §3 (`[3.required-optional]`)
- **Summary:** Three optional parameters did not say what omitting them does: describe's `column_cursor`, and query's `search_text` and `near`.
- **Evidence:** `tools/list`: "next_column_cursor from the previous page.", "Full-text search across text columns.", "Rows within radius_m meters of a point."
- **Remediation (done):** each now ends with its omission semantics ("omit for page one", "omit for none", "omit for no distance filter"). The snapshot was regenerated, and CHANGELOG names the change.

**F6**

- **Severity:** Minor (listed; carried item 3, recommendation only)
- **Section:** §8, §2 (`[8.concise-default]`, `[2.compact-baseline]`)
- **Summary:** The per-result budget has no single unit:
  - query measures `wire_size`;
  - describe measures `payload_size` (ruling 19);
  - reference and `atlas_find_portals` results are not measured.
  - The 512-byte envelope reserve is smaller than the modern `serverInfo` stamp.
- **Evidence:**
  - `core/budget.py`.
  - `atlas_get_reference({"topic": "errors", "item_id": "codes"})` is 26,388 bytes as the modern client receives it, 25,689 by query's own `wire_size`, and 11,829 bytes of `structuredContent`. seattle-open-data's at the fork, by the same `wire_size` arithmetic, was 19,672 and 9,046.
  - Every 2026-07-28 result carries a 666-byte `_meta["io.modelcontextprotocol/serverInfo"]`, which the SDK stamps per the spec's SHOULD.
  - `RESULT_LIMIT` is 24,064 bytes, so a query page packed to it could reach about 24,752 bytes on the modern wire. *(Corrected in the milestone 2 final review: about 24,763 bytes, 187 over 24,576, plus about 36 bytes of JSON-RPC frame, since the modern client receives 699 bytes more than `wire_size` counts, as `errors/codes` shows: 26,388 − 25,689.)* That is computed, not observed: the widest fixture page (`query_wide_rows`, 6 rows) is 23,299 bytes with the stamp.
- **Remediation:** see the ruling-19 judgment below. The item is carried to milestone 3 (`docs/superpowers/plans/2026-10-18-m3-carryover.md`).

**F7**

- **Severity:** Minor (listed)
- **Section:** §2, §8 (`[2.compact-baseline]`)
- **Summary:** The modern `serverInfo` stamp inlines the 560-byte data-URI icon (Task 16) in every 2026-07-28 result, `tools/list` included.
- **Evidence:** the modern `tools/list` is 23,582 bytes, and the legacy one 22,902 bytes; the difference is the stamp. The stamp is also the only modern carrier of `serverInfo`, since `server/discover` has no `serverInfo` field, so dropping the icon from it would drop the icon from the modern era.
- **Remediation:** milestone 5, once the repository is public: serve the icon by `https` URL, or minify the SVG. Carried.

**F8**

- **Severity:** Nit (listed; inherited)
- **Section:** §9 (`[9.tier-metadata]`)
- **Summary:** The `preview` stability tier is stated once, in the capability summary. There is no `_meta` lifecycle key on any tool, resource or template.
- **Evidence:** `## Context`: "Stability: preview (0.1.0)". Tool `_meta` holds only `{"fastmcp": {"tags": []}}`.
- **Remediation:** a `<reverse-dns>/lifecycle` `_meta` entry per record when tiers start to differ. Today every record shares one tier, and there are 994 bytes of `tools/list` headroom on the modern wire. Carried.

**F9**

- **Severity:** Nit (listed; inherited)
- **Section:** §4 (`[4.triage-metadata]`)
- **Summary:** Resources carry `title`, `description` and `mimeType` but no `size`.
- **Evidence:** `resources/list`.
- **Remediation:** declare `size` for the static bodies. Carried.

**F10**

- **Severity:** Nit (listed; inherited)
- **Section:** §3 (`[3.dialect]`)
- **Summary:** No schema declares `$schema`.
- **Evidence:** `tools/list` `inputSchema` and `outputSchema`.
- **Remediation:** add the 2020-12 dialect URI if a target client is found to need it. Each copy costs about 50 bytes. Carried.

No Critical findings. Both Majors (F1, F2) are fixed with failing-first tests.

**Outside the standards (gate).** The live run failed `tests/test_live.py::test_search_and_describe_fire_911` with `KeyError: 'datasets'`: its search call had no `portal` since Task 5 (`26c4324`) made it required, and integration tests do not run in the offline gate. The call now passes `portal: "seattle"`, and the live file passes (15 tests).

### Ruling 19 (carried item 3): kept, with a recommendation

**Ruling:** describe's result budget is measured on `structuredContent` alone; query measures the text copy plus `structuredContent`.

**Against `[8.*]`.** The §8 rules govern what a result contains: the concise default, the detail toggle, paging and truncation. Describe meets them. `detail` changes field density, columns page with a cursor, and `describe_too_large` carries a shrinking repair. None of them names a byte unit.

**Against `[2.compact-baseline]`.** This rule's "measure the serialized wire response" governs `tools/list` definitions. Applied by analogy to results, it argues for the wire.

**Why keep it:**

- The result's text block is a serialized copy of `structuredContent` ([3.content-types]). It is optional, and a reader consumes one copy or the other. Which copy each target host gives its model is not probed here.
- So the payload is the unit that tracks what a reader takes in, and the wire double-counts it.
- Switching describe to the wire would turn Seattle's documented `detail: "full"` fire describe (26.9 KB wire, 13.4 KB payload) into `describe_too_large`, which breaks parity.

**The defect is the inconsistency, not ruling 19 (F6).**

**Recommendation for milestone 3, as its own decisions row:**

- Measure every tool's result as `payload_size`, with a test over each tool's largest result, reference topics included.
- Raise `ENVELOPE_RESERVE` to cover the modern stamp, or shrink the stamp.
- Moving query to `payload_size` changes how many rows a byte-trimmed page holds. That is visible in Seattle's paging (not in its warnings, values or repairs), so it needs its own decision.
- The alternative is to replace the serialized text copy with a short human-rendering block, so the wire is close to the payload. That breaks clients that parse `content[0].text`, which the error catalog documents as holding the same JSON.

This review does not change the measure.

### Probes

| Probe | Evidence |
| --- | --- |
| Cold start | **Measured:** `instructions` is 1,778 characters (1,761 before the S-1 to S-3 splits), identical on both eras. Its order is scope, the full-contract pointer, the sentinel check, negative scope, 13 rules, and the sentinel last (pinned by `tests/test_reference.py`). The rules start at character 435. The whole string is inside both measured Claude Code prefixes (2,048 characters, and 4,096 since 2.1.296; `decisions/006-instructions-prefix.md`). Codex carries the string inside each tool description, which is ruling 23's reason for the 1,800 cap. **Not checked:** a live sentinel session on a target client. **Other carrier:** every head rule is restated under the capability summary's `## Rules` (`tests/test_reference_topics.py::test_every_rule_is_restated_under_rules`). |
| First repair | 16 forced errors (scratch probe, wire as received). `page_size: 900` → `invalid_argument`, `details.field: "page_size"`. `portal: "nope.example"` → `portal_not_found`, repair `atlas_find_portals({})`, value not echoed. `" seattle"` → `invalid_argument` (pattern). Missing `portal` → `invalid_argument`, field `portal`. Garbage cursors on query, search, describe and find_portals → `invalid_cursor` with the `read_paging` repair (describe named `cursor`: F2). `find_portals({"query": "..."})` → `invalid_argument` with the `find_portal` repair. Reference `guides` without `portal`, and `soql` with one, → `invalid_argument`, field `portal`, repair `atlas_get_reference({})`. In every case `content[0].text` parsed equal to `structuredContent`, and `retry_after_ms` was present. |
| Tool selection | Five tools with distinct verb–noun names. `atlas_find_portals` ("Find portals by place name") and `atlas_get_reference` topic `portals` overlap only in listing curated portals; the reference index entry says "atlas_find_portals finds every registered portal". The find_portals description said "before any other tool", which included `atlas_get_reference` (prose S-9, fixed). |
| Advertised vs actual | 11 successes (find_portals with no arguments, a query, and `level: state` with 50 per page; every reference topic) validate against `outputSchema` (`jsonschema`). Search, describe and query successes are validated in 8 test files. Tool errors carry `isError: true` with the envelope in `structuredContent`. Resource errors are JSON-RPC `-32602` with `machine_code`, `human_message`, `resource_uri`, and `details.field: "uri"` after F1. |
| Discovery cost | `tools/list`: 23,582 bytes (modern, as `tests/test_contract.py` measures, including the 666-byte stamp) and 22,902 bytes (legacy), against 24,576. It was 23,510 and 22,830 before this review's description changes. Per tool (modern): find_portals 3,296, search 4,430, describe 7,458, query 5,592, get_reference 2,044. |
| Capability gating | After the fixes, both eras advertise `resources` (no subscribe, no listChanged), `tools` (no listChanged) and `completions`; no prompts, no logging (F4), no extensions (the UI extension was stripped in Task 16). No client capability is required: no tasks, elicitation or roots. `completion/complete` is answered on both eras (`tests/test_standards_m2.py`). |
| Security boundary | Every tool is `readOnlyHint: true`. Search, describe and query are `openWorldHint: true`; find_portals and get_reference are `false`. The first head rule treats dataset text as publisher data. Portal codes never echo the portal value; a resource reports the URI template in `resource_uri`. Cursor errors never echo the cursor or its portal. The value-echo policy is disclosed in `errors/envelope`. |
| Cross-version | No fingerprint (deferred under `[9.fingerprint]`, as in milestone 1). The `tools/list` diff over this review is four description strings (F5, S-9). Ordering is pinned by `tests/test_contract.py`. |
| Resource freshness | `server/discover`, the list methods and `resources/read` carry `ttlMs: 3600000`, `cacheScope: "public"`. Their bodies are static per process; portal bodies vary only by the operator's allowlist. `listChanged` is false; no subscriptions. |
| Long-running operation | Skipped: none defined. Describe and query are blocking calls with 30 s deadlines stated in their descriptions. Cancellation is covered by `tests/test_cancellation.py`. |

### Coverage

| Section | Status | Notes |
| --- | --- | --- |
| §1 Server-Level | finding F4 | Otherwise OK. `opendata-atlas`, title "Open Data Atlas", icon. stdio, logs on stderr (`main`). Revision target declared. Credential modes are distinct (anonymous, `app_token_rejected`, `upstream_forbidden`). Cursors are declared state handles (1 h, no restart survival, portal-bound). The allowlist is declared in `## Context`. |
| §2 Discovery | findings F3, F6, F7 | Otherwise OK. Capability summary as a resource with a tool fallback. Negative scope at the head. Sentinel pinned last. Rules restated. Every reference index lists only readable URIs. |
| §3 Tools | findings F5, F10 | Otherwise OK. `atlas_` verb–noun names. Honest read-only annotations, explicit `openWorldHint`, no mutation hints. Closed, union-free input schemas. An `outputSchema` per tool, open at the top with `source` required and closed below. Example and latency in each description. |
| §4 Resources | findings F1, F3, F9 | Otherwise OK. Stable `opendata-atlas://` URIs. JSON indexes before markdown bodies. Every resource has a tool fallback (design table). Short descriptions. `-32602` with the unified envelope on failure. |
| §5 Prompts | not-applicable | No prompts: `prompts/list` and `prompts/get` are removed, and no capability is advertised (`tests/test_legacy_protocol.py`). |
| §6 Failure Recovery | findings F1, F2 | Otherwise OK. Symbolic codes, documented per tool in `errors/codes`. `retry_after_ms` always present. One repair object, validated by `tests/test_repairs.py`. Field-level details. Disclosed value policy. `request_id` on both carriers. |
| §7 Long-Running Operations | not-applicable | No operation outlives a request. Two blocking tools declare 30 s deadlines. No tasks extension. |
| §8 Token Efficiency | finding F6 | Otherwise OK. `detail` on search, describe and query. Cursor paging with `has_more`/`next_cursor` (house convention, in `structuredContent`). `truncated`. Describe column paging. Native `ttlMs`/`cacheScope`. Nulls stripped. |
| §9 Versioning | finding F8 | Otherwise OK. Deterministic order (snapshot). `listChanged` false on a fixed surface. Every snapshot change named in CHANGELOG. Fingerprint deferred per `[9.fingerprint]`. |

**Residual risks:**

- No live client session checked the instructions prefix, or how a host renders completion.
- Completion was exercised only through the in-process client.
- The budget overshoot in F6 is computed, not observed.

## Part 2: separating-context-from-constraints

### Targets and classification

| Target | Surface class | Result |
| --- | --- | --- |
| Served `instructions` (1,761 characters before, 1,778 after) | compact (one field) | S-1, S-2, S-3 |
| Capability summary (`opendata-atlas://capabilities`, served) | long-form | S-1–S-3 (verbatim restatement); accuracy A-1 |
| The five tool descriptions and their parameter descriptions (`tools/list`) | compact | S-9 |
| 6 resource and 5 template descriptions | compact | clean |
| Error catalog `alternative` and `reason` texts: `errors/codes` as served, and every `alternative=`/`reason=` in `src/` | compact (one field each) | clean |
| `contributing` body | long-form | accuracy A-2 |
| `AGENTS.md` | long-form | S-4, S-5, S-6 |
| `README.md` | long-form | S-8 |
| `docs/design.md` | long-form | S-7; accuracy A-3, A-4 |

**`docs/design.md` coverage.** The sections changed in milestone 2 (per `git diff e99b930..HEAD`) were read in full: Intent, Goals, Identity, Knowledge levels, Fact model, Validation state and freshness, Tools, Continuation, Instructions head rules, Errors, Configuration, Registry and Evals. These were skimmed: Non-goals, Anti-goals, Constraints, Knowledge packs (layout), Place fields, Time, Engine isolation, Resources, Building knowledge, Byte budgets, Launch scope, Milestones and Left to the builder.

### Findings

**S-1**

- **Rule:** R4
- **Location:** `instructions` Rules and capability `## Rules` (`HEAD_RULES`); milestone 1's S-m2
- **Quoted text:** "Never answer with a count filtered or grouped on a field coverage_warnings marks unreliable; give a partial field's counts only with its caveat."
- **Why it fails:** Two obligations with different triggers (`unreliable`, `partial`) share one item.
- **Severity:** Minor
- **Suggested rewrite:** "Never answer with a count filtered or grouped on a field coverage_warnings marks unreliable." / "Give a partial field's counts only with its caveat."
- **Status:** Fixed.

**S-2**

- **Rule:** R4 (secondary R1)
- **Location:** `HEAD_RULES`; milestone 1's S-m1
- **Quoted text:** "On isError, branch on structuredContent.code. temporary=false: never retry unchanged. temporary=true: retry later, after retry_after_ms when set. Follow repair when present."
- **Why it fails:** Four independently checkable obligations share one item. Task 11 had already chosen the promoted reading of the `temporary=true` clause ("retry later").
- **Severity:** Minor
- **Suggested rewrite:** four items: "On isError, branch on structuredContent.code." / "If temporary is false, never retry the call unchanged." / "If temporary is true, retry later, after retry_after_ms when set." / "Follow repair when present."
- **Status:** Fixed.

**S-3**

- **Rule:** R4 (secondary R1)
- **Location:** `HEAD_RULES`; milestone 1's S-m3, as shortened by ruling 23
- **Quoted text:** "Offer a server defect (capabilities ## Defects) to the user; never file unasked: the tracker is public."
- **Why it fails:** Two obligations and a rationale share one item.
- **Severity:** Minor
- **Suggested rewrite:** "Offer a server defect (capabilities ## Defects) to the user." / "Never file an issue unasked." Move "The tracker is public." to `## Defects`, as context.
- **Status:** Fixed.

**S-4**

- **Rule:** R1
- **Location:** `AGENTS.md` `## Rules`, third item
- **Quoted text:** "Every failure leaves as the error envelope in `docs/design.md` (Errors). Raise `AtlasError` from handlers; never return ad-hoc error text."
- **Why it fails:** A fact about the server's behavior opens a rule item.
- **Severity:** Minor
- **Suggested rewrite:** Rules keeps "Raise `AtlasError` from handlers; never return ad-hoc error text." `## Context` gains "Every failure leaves as the error envelope in `docs/design.md` (Errors); `mcp/server.py` turns an `AtlasError` into it."
- **Status:** Fixed.

**S-5**

- **Rule:** R4
- **Location:** `AGENTS.md` `## Rules`
- **Quoted text:** "Never report an upstream fact you did not probe. Label reviewer-reported facts as such in `docs/upstream-facts.md`."
- **Why it fails:** Two independently checkable obligations share one item.
- **Severity:** Minor
- **Suggested rewrite:** one item each.
- **Status:** Fixed.

**S-6**

- **Rule:** R1
- **Location:** `AGENTS.md` `## Rules`, last item
- **Quoted text:** "Live tests use the `integration` marker and run with `uv run pytest --run-integration -m integration`."
- **Why it fails:** A rule (mark live tests) and a fact (the command) share one item, and the rule is phrased as a description.
- **Severity:** Minor
- **Suggested rewrite:** Rules: "Mark live tests with the `integration` marker." Context: "Live tests run with `uv run pytest --run-integration -m integration`."
- **Status:** Fixed.

**S-7**

- **Rule:** R1
- **Location:** `docs/design.md`, Tools §3, the "Wide schemas" item
- **Quoted text:** a single 2,000-character item mixing the paging rules and `describe_too_large`'s repair with byte measurements, the "final" status of the caps, and rationale ("samples are illustrative, so the question is unchanged").
- **Why it fails:** The binding paging contract can only be pulled out by parsing the narrative.
- **Severity:** Minor
- **Suggested rewrite:** sub-items, one per rule, then a labeled *Context* item with the measurements and rationale. Every sentence is kept.
- **Status:** Fixed.

**S-8**

- **Rule:** R1
- **Location:** `README.md`, "Choosing a portal"
- **Quoted text:** "…told apart by `jurisdiction.level`, so ask the user which they mean unless the request names the level."
- **Why it fails:** An imperative sits in a human-facing narrative paragraph, which is not where the contract is kept. An agent could take the README for the contract.
- **Severity:** Minor
- **Suggested rewrite:** demoted to context, since the binding copy is the head rule: "…and the server's rules tell the agent to ask the user which one they mean unless the request names the level."
- **Status:** Fixed.

**S-9**

- **Rule:** R5
- **Location:** `atlas_find_portals` description vs `atlas_get_reference`'s optional `portal`
- **Quoted text:** "Call this before any other tool when you lack a portal id."
- **Why it fails:** With no portal id, an agent that only wants the SoQL reference is told to call find_portals first, while `atlas_get_reference` takes no portal on that topic. The conflict is reachable, though harmless.
- **Severity:** Minor
- **Suggested rewrite:** "Call this before any tool that takes `portal` when you lack its id."
- **Status:** Fixed (snapshot regenerated).

**Outside R1–R5 (accuracy):**

- **A-1 (Material, fixed).**
  - Location: capability `## Rules`.
  - The text said: "On `cursor_expired` or `invalid_cursor`, resend the first-page call with all its original arguments and no `cursor`".
  - On describe the cursor is `column_cursor`. An agent following the rule alone resends the same `column_cursor` and fails again.
  - It now reads "no `cursor` or `column_cursor`", matching `soql/paging` and describe's repair `alternative`.
- **A-2 (Minor, fixed).**
  - Location: the `contributing` body.
  - It said "is not published yet; it is not published in this release." It now says "is not published in this release." (ruling 24's wording).
- **A-3 (Minor, fixed).**
  - Location: `docs/design.md`, Time.
  - It said "`now_local` is that zone's wall-clock time, or `null`". On the wire `now_local` is omitted, not `null`, as CHANGELOG and the capability summary say. Corrected.
- **A-4 (Minor, fixed).**
  - Location: `docs/design.md`, Knowledge levels, Fact model and Byte budgets.
  - These name `tests/test_tiers.py`, `docs/pack-examples/` and the 100-guide and 2,000-entry budget fixtures in the present tense. None exists.
  - Each is now marked "not built yet" and carried to milestone 3.

**Safety note:** none. No target contained instructions aimed at the auditor.

### Summary

| Rule | Count |
| --- | --- |
| R1 | 6 (S-2, S-3, S-4, S-6, S-7, S-8) |
| R2 | 0 |
| R3 | 0 |
| R4 | 4 (S-1, S-2, S-3, S-5) |
| R5 | 1 (S-9) |

| Severity | Count |
| --- | --- |
| Material | 0 |
| Minor | 9 |

Outside R1–R5: one Material (A-1) and three Minor (A-2, A-3, A-4), all fixed.

**Assessment.** The served surfaces separate rules from context well. The tool and resource descriptions mark their constraints inline, and the error catalog's `alternative` and `reason` texts are clean. `instructions` and the capability summary keep labeled rule lists, and the summary restates every head rule verbatim.

The three bundled head rules, which milestone 1 listed and served-text parity froze, are now split, and the instructions still fit ruling 23 (1,778 of 1,800 characters). `AGENTS.md`'s remaining mixed items are separated. The design's one long contract paragraph is restructured.

The one Material defect was not a separation issue. It was a cursor-restart rule that omitted describe's cursor parameter, and it is fixed. No Material finding is open.
