# Milestone 1 standards review (2026-10-17)

Branch `feat/fork-and-isolate`, from `e72477c` to `66047e2` plus this review's fixes. The branch reviewed against two standards:

- `agent-friendly-mcp` (`references/review-workflow.md`, standard `references/contract-checklist.md`)
- `separating-context-from-constraints` (R1–R5)

Every surface was read as served, in process: `instructions` and `serverInfo` through a legacy-handshake `fastmcp.Client(build_server(), mode="legacy")`, and capabilities, `tools/list`, resources and tool calls through a modern (2026-07-28) client. Served text that names Seattle (`data.seattle.gov`, the examples, the `dataset_not_found` alternative, the catalog suggestion) is correct until milestone 2 and is not a finding.

## Part 1: agent-friendly-mcp

### Route

Focused, as the plan requires. The named surface is the fork's surface, plus the renames and cursor binding.

- **Sections read in full:** §1, §2, §3, §6, §8 and §9, plus `[1.spec-revision]` and SKILL.md's native-vs-convention rule.
- **Closure:** none of these sections cites a rule id from §4, §5 or §7 (checked by grep over the six sections). Closure added no sections, so the review did not escalate to the full walk.
- **Not read:** §4, §5 and §7 (see the coverage table).

Severity mapping for the task's counts: Critical and Major count as Material, Minor and Nit as Minor.

**Protocol target (`[1.spec-revision]`).** The capability summary declares "MCP 2026-07-28, compatible with 2025-11-25; no extensions required." The modern client negotiated `2026-07-28` and the legacy client `2025-11-25`. Both get identical tools.

### Findings

**F1**

- **Severity:** Major (fixed)
- **Section:** §9, §1 (`[1.metadata-contract]`, `[9.rename]`)
- **Summary:** The renamed server presented itself as seattle-open-data's 0.2.0. Its CHANGELOG did not say it was a fork, and the parent's release sections could be published as this server's releases.
- **Evidence:**
  - Before the fix, `serverInfo` was `{"name": "opendata-atlas", "version": "0.2.0"}`, the capability summary title was `# opendata-atlas 0.2.0`, and the error catalog said `"version": "0.2.0"`.
  - `CHANGELOG.md` had no fork statement. Its first versioned heading was `## [0.2.0] - 2026-10-16`, and that section lists `seattle_data_*` tools.
  - `release.yml` checks that first `## [X.Y.Z]` heading against pyproject, then publishes that section as the GitHub release notes.
  - A `v0.2.0` tag would therefore have shipped seattle-open-data's notes, naming tools this server does not have. A `v0.1.0` tag would have failed the version check, and its extractor would have pulled seattle-open-data's "First release" section instead.
  - The defect rule in `instructions` asks agents to report "server version". A 0.2.0 here would be a version this server never released.
- **Remediation (done):**
  - The version is `0.1.0` in `pyproject.toml`, `uv.lock`, `manifest.json` (regenerated) and the README status line. `__version__`, `serverInfo.version`, the capability summary title, `CONTENT_VERSION` and the User-Agent all derive from it.
  - CHANGELOG `[Unreleased]` says this is a new server forked from seattle-open-data 0.2.0 at 26c6628, with tools renamed from `seattle_data_*` to `atlas_*` and no aliases.
  - The parent's releases sit under `## [seattle-open-data history]`. The heading fails `release.yml`'s version regex, and it ends the workflow's awk extraction, so a cut `## [0.1.0]` section's release notes stop before the parent's entries. (Fix round 1: the first fix used `## seattle-open-data history`, which the awk does not stop at, so the notes would have run on into the parent's 0.2.0 and 0.1.0 entries.) `docs/releasing.md` documents the cut.
  - `docs/design.md` Constraints gains a Versioning line.
  - Regression: `tests/test_versioning.py`, which includes running the workflow's own awk on a CHANGELOG cut as `## [0.1.0] - 2026-10-18`.

**F2**

- **Severity:** Minor (listed; inherited)
- **Section:** §2 (`[2.discover-first]`), §1 (`[1.negotiated-caps]`)
- **Summary:** Modern capabilities advertise the `io.modelcontextprotocol/ui` extension, but the server serves no UI. The capability summary says only that no extensions are required.
- **Evidence:**
  - The modern client's `server_capabilities` include `"extensions": {"io.modelcontextprotocol/ui": {}}`, which is FastMCP 4.1.0's default (`fastmcp/apps/config.py`).
  - Since the import commit `2ce4258`, `build_server` changed only to pass the portal context, so this is inherited.
- **Remediation:** In milestone 2, which takes the full walk, either suppress the extension in `_advertise_fixed_surface` (and pin the result in `tests/test_legacy_protocol.py`), or add a line to the capability summary's `## Context`: "Advertises `io.modelcontextprotocol/ui` by framework default; serves no UI resources."

**F3**

- **Severity:** Nit (listed; inherited)
- **Section:** §1 (`[1.display-metadata]`)
- **Summary:** Implementation info carries only `name` and `version`. There is no `title` and no `icons`, although the MCPB manifest declares `display_name: "Open Data Atlas"` and two icons.
- **Evidence:** `serverInfo` is `{"name": "opendata-atlas", "version": "0.1.0"}`, and `manifest.json` has `display_name` and `icons`.
- **Remediation:** In milestone 2, pass `website_url` and `icons` to `FastMCP(...)` in `build_server` (FastMCP 4.1's constructor accepts both), plus a title if the SDK exposes one.

No Critical findings. The one Major (F1) is fixed. No Material finding needed a snapshot change, so nothing is deferred to milestone 2 on that ground. `tests/snapshots/tools_list.json` is unchanged since `23d8bcf`.

### Probes

| Probe | Evidence |
| --- | --- |
| Cold start | `instructions` is 1,607 characters: scope, a full-contract pointer, the sentinel check, negative scope, 8 rules, then the sentinel line, which `tests/test_reference.py` pins last. That is under Claude Code's measured 4,096-character default and the earlier 2,048 (the skill's `decisions/006-instructions-prefix.md`), so the whole string falls inside every measured prefix. A live sentinel session on a target client was **not-checked**: no client was run in this review. The capability summary restates all 8 rules under `## Rules` (`tests/test_review_separation.py`). |
| First repair | `atlas_query_dataset` with `page_size: 900` returned `invalid_argument`, `details.field: "page_size"`, `temporary: false`, `retry_after_ms: null`. `atlas_get_reference` with `{"topic": "soql", "item_id": "nope"}` returned `reference_not_found` with `candidates` and the repair `{"topic": "soql"}`. Every cursor error below carries the `read_paging` repair, and calling it (`atlas_get_reference` `soql/paging`) succeeded. |
| Tool selection | Four tools with distinct verbs and nouns (search, describe, query, get_reference). The search description says "Call first when you lack a dataset id", and the describe description says "Call before querying a dataset whose columns you do not know". |
| Advertised vs actual | Each cursor error was `isError: true`, with the envelope in `structuredContent`. `content[0].text` parsed equal to it. `retry_after_ms` was present (`null`), and the cursor was never echoed. A resource miss (`opendata-atlas://nope`) was JSON-RPC `-32602`, with `machine_code: "reference_not_found"`, `human_message` and `resource_uri`. |
| Discovery cost | The serialized `tools/list` is 15,230 bytes, against a 24,576-byte budget. |
| Capability gating | No optional client capability is used: no tasks, elicitation, completions or subscriptions. Prompts are not advertised, and `listChanged` is false (`tests/test_legacy_protocol.py`). See F2 for the `ui` extension. |
| Security boundary | All tools are `readOnlyHint: true`; search, describe and query are `openWorldHint: true`. The head rule treats dataset text as publisher data. Cursor errors never echo the cursor or its portal (probed, and `tests/test_isolation.py`). |
| Cross-version | No fingerprint, which the parent deferred under `[9.fingerprint]`. The served version moved from 0.2.0 to 0.1.0 with F1. The tool definitions and `instructions` are byte-identical before and after this review's fixes (diffed from two in-process dumps). |
| Resource freshness | `tools/list` and `resources/list` carry `ttlMs: 3600000` and `cacheScope: "public"`. Their content is static per process. |
| Long-running operation | Skipped: none defined. Describe and query have 30 s whole-call deadlines, stated in their descriptions. |

**The §6 cursor path (Review Focus 1, cross-portal).** Each case below is a real `atlas_query_dataset` call in process, made with `dataset_id: "kzjm-xkqj"` and the cursor shown:

| Cursor | Code | `message` / `details.reason` |
| --- | --- | --- |
| v1 payload signed with another process's key (any seattle-open-data cursor) | `cursor_expired` | "The cursor has expired or the server restarted." / "Its signature does not match: cursors do not survive a server restart." |
| v1 payload signed with this process's key | `invalid_cursor` | "The cursor uses an unsupported format." / "It was issued by a different server version." |
| v2, another portal (`data.cityofnewyork.us`) | `invalid_cursor` | "The cursor belongs to a different portal." / "Use a cursor only with the portal that returned it." |
| v2, another tool's cursor | `invalid_cursor` | "The cursor belongs to a different tool." |
| Undecodable string | `invalid_cursor` | "The cursor is malformed." |

Every case carries `temporary: false` and the `read_paging` repair. `atlas_search_datasets` behaves the same for a cross-portal cursor, with its search-specific `alternative`.

A seattle-open-data cursor therefore fails with `cursor_expired`, not the `invalid_cursor` the plan predicted. The agent's action is identical (restart from page one with every original argument), so this is not a finding against the server. The plan's wording is prose finding S-M1.

### Coverage

| Section | Status | Notes |
| --- | --- | --- |
| §1 Server-Level | findings F1, F3 | OK otherwise. `opendata-atlas` is distinctive and has no version in it. Transport is stdio, logs go to stderr (`main`), and the capability summary declares the protocol target. The auth failure modes are distinct (anonymous, `app_token_rejected`, `upstream_forbidden`). Cursors are declared as state handles: 1 h lifetime, no survival across a restart. |
| §2 Discovery | finding F2 | OK otherwise. The capability summary is a resource with a tool fallback (`atlas_get_reference(topic="capabilities")`). Negative scope sits in the instructions head, the rules are restated in the summary, and the sentinel is pinned. Prefix: the whole string is inside every measured client prefix. A live sentinel check is not-checked. |
| §3 Tools | OK | `atlas_` prefix with verb and noun, and titles renamed to match (`Atlas Search Datasets`, ...). Read-only annotations are honest. Descriptions name when to call and carry an example and typical latency. Schemas are unchanged since Task 1 (`git diff --quiet 23d8bcf HEAD -- tests/snapshots/`). |
| §4 Resources | not-checked | Not a named section, and closure did not reach it. The only change is the URI scheme rename; the resource error path was exercised under the probes above. |
| §5 Prompts | not-checked | The server defines no prompts; `prompts/list` is removed (`tests/test_legacy_protocol.py`). |
| §6 Failure Recovery | OK | One envelope on both carriers (probed). Symbolic codes; `retry_after_ms` is always present; repairs are literal and callable (`tests/test_repairs.py`). The cursor path is in the table above. |
| §7 Long-Running Operations | not-checked | No long-running operations and no tasks. Not a named section. |
| §8 Token Efficiency | OK | Cursor pagination with `has_more` and `next_cursor` (a house convention, in `structuredContent`), cursor lifetime declared, `truncated` with `truncation_reason`, a `detail` toggle on every data tool, and native `ttlMs`/`cacheScope` on list results. |
| §9 Versioning | finding F1 | OK otherwise. `listChanged` is false (fixed surface), ordering is pinned by the snapshot, and the fingerprint is deferred per `[9.fingerprint]` (inherited). `[9.rename]`'s alias window does not apply, because the old names stay served by seattle-open-data, under its own server name. |

**Residual risks for milestone 2:**

- The cross-portal `invalid_cursor` path is reachable in milestone 1 only with a forged cursor, because one portal is served.
- The capability summary's paging semantics and `soql/paging` do not yet say that a cursor works only with the portal that issued it. The error catalog's `invalid_cursor` example shows only the wrong-tool reason.
- Milestone 2 adds the `portal` argument. It must state the portal binding there, and it must make the cursor repair carry `portal`, as `docs/design.md` requires.

## Part 2: separating-context-from-constraints

### Targets and classification

| Target | Surface class | Result |
| --- | --- | --- |
| Server `instructions` (as served, 1,607 characters) | compact (one field) | findings S-m1, S-m2, S-m3 |
| Capability summary (`opendata-atlas://capabilities`, as served) | long-form | S-m1–S-m3 (rules restated verbatim), S-M2 |
| The four tool descriptions (as served in `tools/list`) | compact | clean |
| Error catalog `alternative` texts (`opendata-atlas://errors/codes`, as served: `column_not_geographic`, `dataset_not_found`, `dataset_not_queryable`, `query_timeout`, `cursor_expired`, `invalid_cursor`) | compact (one field each) | clean |
| `AGENTS.md` | long-form | S-m5, S-m6 (fixed) |
| `CLAUDE.md` | compact (`@AGENTS.md` only) | clean |
| Plan `docs/superpowers/plans/2026-10-17-m0-m1-fork-and-isolate.md`, Global Constraints | long-form section | S-M1, S-m7, S-m8, S-m9 |

### Findings

**S-M1**

- **Rule:** R1 (a load-bearing fact inside a binding rule; the fact is also wrong)
- **Location:** Plan, Global Constraints, the "Seattle parity" bullet (the same claim is in Review Focus 1)
- **Quoted text:** "cursor format v2 with portal binding (pre-fork cursors fail with `invalid_cursor`; Review Focus 1)"
- **Why it fails:**
  - The parity rule's list of permitted differences embeds an outcome claim.
  - Probed in process, a cursor from another process, which includes every seattle-open-data cursor, fails with `cursor_expired`. Only a same-process v1 cursor gives `invalid_cursor`.
  - A reader verifying parity against the rule would treat correct behavior as a violation, or "fix" the code to match.
- **Severity:** Material
- **Suggested rewrite:**
  - Rule: "In this plan the only permitted output differences are renames (tool prefix, URI scheme, server name, sentinel, issues URL) and cursor format v2 with portal binding."
  - Context, outside the rule: "A cursor from `seattle-open-data` or an earlier build fails with `cursor_expired` (another process's key) or `invalid_cursor` (a v1 cursor from the same process); both carry the `read_paging` repair."
- **Status:** Recorded, not edited. The plan text stays as history, and the SDD ledger (kept outside the repo) supersedes it with its ruling on the Task 5 CHANGELOG wording. CHANGELOG states the probed behavior.

**S-m1**

- **Rule:** R4 (secondary R1)
- **Location:** `instructions` Rules and capability summary `## Rules` (`HEAD_RULES[6]` in `core/reference.py`)
- **Quoted text:** "On isError, branch on structuredContent.code. temporary=false: never retry unchanged. temporary=true: the same call may succeed later, after retry_after_ms when set. Follow repair when present."
- **Why it fails:** One item carries three independently checkable obligations and one fact ("may succeed later"). The intended behavior is still clear.
- **Severity:** Minor
- **Suggested rewrite:** Split it into "On isError, branch on structuredContent.code." / "When temporary is false, never retry the call unchanged." / "Follow repair when present."
  - **Author decision** for the `temporary=true` clause:
    - (a) Promoted: "When temporary is true, you may retry the same call, after retry_after_ms when it is set."
    - (b) Demoted: move "temporary=true means the same call may succeed later, after retry_after_ms when set" to `## Semantics`.
- **Status:** Listed. The text is inherited verbatim from the fork.

**S-m2**

- **Rule:** R4
- **Location:** `instructions` Rules and capability summary `## Rules` (`HEAD_RULES[3]`)
- **Quoted text:** "Never report a count filtered or grouped on an unreliable field in coverage_warnings as the answer; report a partial field's counts only with its reliability caveat."
- **Why it fails:** Two obligations with different triggers (`unreliable`, `partial`) share one item.
- **Severity:** Minor
- **Suggested rewrite:** Two items: "Never report a count filtered or grouped on an `unreliable` field in coverage_warnings as the answer." / "Report counts on a `partial` field only with its reliability caveat."
- **Status:** Listed (inherited). `tests/test_review_separation.py` looks this rule up as one item.

**S-m3**

- **Rule:** R4 (secondary R1)
- **Location:** `instructions` Rules and capability summary `## Rules` (`HEAD_RULES[7]`)
- **Quoted text:** "For a defect in this server (capabilities ## Defects), offer the user https://github.com/briandconnelly/opendata-atlas/issues with the error code, request_id, and server version; never file unasked: the tracker is public."
- **Why it fails:** The item holds two obligations (offer; never file unasked) plus a rationale clause.
- **Severity:** Minor
- **Suggested rewrite:** "For a defect in this server (capabilities ## Defects), offer the user <URL> with the error code, request_id, and server version." / "Never file an issue unasked." Move "The tracker is public" to the summary's `## Defects`.
- **Status:** Listed (inherited).

**S-M2**

- **Rule:** R1
- **Location:** Capability summary, `## Defects`, the last item
- **Quoted text:** "Report to: <URL>. Include the error code, `request_id`, server version (this summary's title), and the tool call once the user has reviewed it."
- **Why it fails:** A binding, privacy-relevant obligation sits outside `## Rules`: include the tool call only after the user's review. The head rule (in `instructions` and `## Rules`) lists what to include without it, so a reader who follows the rules alone can put an unreviewed tool call, which may carry the user's query text, into a public issue.
- **Severity:** Material (reclassified from Minor in fix round 1)
- **Suggested rewrite:** Add to `## Rules`: "In a defect report, include the tool call only after the user has reviewed it." Keep "Report to: <URL>" in `## Defects` as a fact.
- **Status:** Deferred to milestone 2. Fixing it changes served text, which is frozen in this milestone; milestone 2 rewrites the capability summary for the `portal` argument. Inherited from the fork.

**S-m5**

- **Rule:** R1
- **Location:** `AGENTS.md` `## Rules`, the first and third items
- **Quoted text:** "The tool surface is contract." / "`tests/test_repairs.py` enforces this for documented and emitted repairs."
- **Why it fails:** Context sits inside the rules section.
- **Severity:** Minor
- **Suggested rewrite:** Keep the obligations in `## Rules` and move both facts to a new `## Context`.
- **Status:** Fixed.

**S-m6**

- **Rule:** R1
- **Location:** `AGENTS.md` `## Toolchain`
- **Quoted text:** "uv for everything (`uv add`, `uv sync`, `uv run`); never pip."
- **Why it fails:** A binding rule sits in a facts section, beside tool facts.
- **Severity:** Minor
- **Suggested rewrite:** In `## Rules`: "Use uv for all project and package management; never pip." Toolchain keeps "uv (`uv add`, `uv sync`, `uv run`)."
- **Status:** Fixed.

**S-m7**

- **Rule:** R5
- **Location:** Plan, the Global Constraints parity bullet vs Task 11 Step 1
- **Quoted text:** "the only permitted output differences are renames (...) and cursor format v2 with portal binding" / "a renamed server is a new server; its version starts at `0.1.0`"
- **Why it fails:** Setting the version changes `serverInfo.version` and the capability summary title. Neither is a listed difference, and the plan does not say which rule wins.
- **Severity:** Minor. The controller's Task 11 note made the specific instruction bind.
- **Suggested rewrite:** **Author decision**, with these alternatives:
  - (a) Add "the server version and the capability summary title (Task 11)" to the permitted differences.
  - (b) State that a task's own step overrides the parity list for the outputs that step names.
  - (c) Keep the parity list exhaustive and drop the version reset.
- **Status:** Recorded; the plan stays as history. Resolved by the controller's binding note.

**S-m8**

- **Rule:** R4
- **Location:** Plan, Global Constraints, "Prose standard"
- **Quoted text:** "... is audited with the `separating-context-from-constraints` skill ..., and the task is not complete while a **Material** finding is open. Minor findings are fixed or listed in the task's commit message."
- **Why it fails:** Three independently checkable obligations share one item: audit, a completion gate, and the handling of Minor findings.
- **Severity:** Minor
- **Suggested rewrite:** Three items:
  - "Audit every listed prose surface the task writes or changes with ..."
  - "Do not mark a task complete while a Material finding is open."
  - "Fix each Minor finding or list it in the task's commit message."
- **Status:** Recorded; the plan stays as history.

**S-m9**

- **Rule:** R4
- **Location:** Plan, Global Constraints, the commits bullet
- **Quoted text:** "Conventional Commits; feature branches with a type prefix; never commit to `main`. Commit trailer: `🤖 Generated with Claude Code`."
- **Why it fails:** Four obligations are bundled in one item.
- **Severity:** Minor
- **Suggested rewrite:** One item each: commit subjects, branch names, no commits to `main`, and the trailer.
- **Status:** Recorded; the plan stays as history.

**Outside R1–R5 (accuracy, fixed):** `AGENTS.md` "What this is" said "An agent-friendly MCP server for Seattle Open Data." It now describes a Socrata multi-portal server, forked from seattle-open-data, that serves Seattle only until milestone 2.

**Safety note:** none. No target contained instructions aimed at the auditor.

### Summary

| Rule | Count |
| --- | --- |
| R1 | 6 (S-M1, S-M2, S-m1, S-m3, S-m5, S-m6) |
| R2 | 0 |
| R3 | 0 |
| R4 | 5 (S-m1, S-m2, S-m3, S-m8, S-m9) |
| R5 | 1 (S-m7) |

| Severity | Count |
| --- | --- |
| Material | 2 |
| Minor | 8 |

**Assessment.** The served surfaces separate rules from context well. The tool descriptions and the error catalog's `alternative` texts are clean. `instructions` and the capability summary carry labeled rule lists, and the summary restates every head rule verbatim. All four served-text findings are bundling or placement issues inherited unchanged from seattle-open-data at 26c6628. Served text is frozen in this milestone (Task 7 verified it byte-identical to the fork for parity), and milestone 2 rewrites these surfaces for the `portal` argument, so they wait for it. Three are Minor and listed. S-M2, a privacy-relevant obligation outside `## Rules`, is Material and deferred to milestone 2.

The other Material finding, S-M1, is in the plan. Its parity rule embeds a wrong cursor outcome, which the probe above corrects. It is recorded and superseded rather than edited, because the plan is kept as history.

`AGENTS.md`'s two placement issues and its stale description are fixed.
