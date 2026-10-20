# Milestone 6 standards review (2026-10-19)

Branch `feat/more-portals`, the milestone diff `0104ebd..2b5040c` plus this review's fix (486de61) and docs commit. Milestone 6 named registry portals from their site titles, rebuilt the registry, and merged the Everett (`profiled`, to be promoted) and King County (`profiled`) packs, with two engine fixes (715b183, 7e9f8bf). The branch was reviewed against two standards:

- `agent-friendly-mcp` (`references/review-workflow.md`, standard `references/contract-checklist.md`);
- `separating-context-from-constraints` (R1–R5).

The served surface was read through the in-process `fastmcp.Client(build_server())`, on the modern era (2026-07-28) and the legacy handshake (`mode="legacy"`):

- `tools/list` (framed size) and `instructions`;
- `atlas_find_portals` with no argument and for 15 queries: the Review Focus place names, aliases and hosts, plus "Cook County", "New Jersey", "City of Albany", "open data", "Tyler", "Government Financial Reports", "Franklin" and "FranklinForward";
- `atlas_get_reference` topic `portals` (index, and items `everett` and `king-county`);
- a `tools/call` naming a tool the server does not have.

Scripts and output are in `docs/evidence/standards-m6-2026-10-19/`:

- `surface.py.txt` and `surface.json`: the served surface after the fix;
- `unknown-tool-red.txt`: the failing-first run of F1's test, before the fix.

No paid command ran. No live upstream call was needed: `atlas_find_portals` and topic `portals` read the shipped registry and packs.

Severity mapping for the counts: Critical and Major count as Material, Minor and Nit count as Minor.

## Part 1: agent-friendly-mcp

### Route

**Focused route.** The surface changes:

- registry `name` values from site titles, in `atlas_find_portals` candidates and in topic `portals` entries and items (no schema or description change; `tests/snapshots/tools_list.json` is unchanged from `0104ebd`);
- two new portals in both, with aliases `everett` and `king-county`;
- Task 4's change (7e9f8bf): describe honors `placeholders` on a reviewed `place_field`. Its fields (`placeholder_values`, `candidate_placeholders`, `assigned_fraction`) already existed, so only their values change;
- the routed engine defect: an unknown tool name answers `internal_error` (F1).

Named sections: §2 (discovery: `find_portals` and topic `portals` are how an agent finds a portal), §6 (F1), §8 (the no-argument listing and its size), §9 (deterministic order, the name changes as a versioned surface).

`[1.spec-revision]` and the native-vs-convention rule (SKILL.md) were read first, and the four named sections were read in full. Closing over the cited ids pulled in two rules outside them, both in §1: `[1.negotiated-caps]` (cited by `[2.discover-first]`) and `[1.transport]` (cited by `[6.jsonrpc-code-allocation]`). Neither cites further. One section beyond those named, so the review did not escalate to the full walk.

**Protocol target (`[1.spec-revision]`).** Unchanged: MCP 2026-07-28, compatible with 2025-11-25, no extension required. Both eras served the same `atlas_find_portals` candidates, the same topic `portals` index (930 bytes) and, after the fix, the same unknown-tool envelope.

### Findings

**F1**

- **Severity:** Major (Material). **Fixed** in 486de61, test first.
- **Section:** §6 (`[6.symbolic-codes]`, `[6.repair-hints]`, `[6.repair-callable]`, `[6.field-feedback]`), §2 (`[2.summary]`, the `## Defects` routing)
- **Summary:** a `tools/call` naming a tool the server does not have answered `internal_error`, "The server failed unexpectedly.", with no `repair`, so an agent that guessed a tool name was told the server broke.
- **Evidence:**
  - Routed by the King County curating agent (decisions row "Unknown tool name answers `internal_error`"). Reproduced in process on both eras before the fix: `isError: true`, `code: "internal_error"`, no `details`, no `repair`, and a logged traceback (`unexpected failure in atlas_no_such_tool`).
  - `src/opendata_atlas/mcp/server.py`, `EnvelopeMiddleware.on_call_tool`: every non-`AtlasError`, non-validation exception went to `_to_error`, which returns `INTERNAL_ERROR`. FastMCP raises its own `NotFoundError("Unknown tool: ...")`, unwrapped (`fastmcp/server/server.py:1464`). Only `on_read_resource` mapped `NotFoundError`.
  - The capability summary's `## Defects` (`core/reference.py:162`) lists "an `internal_error`" as a defect in this server and tells the agent to offer the user a defect issue. The wrong code therefore invites a false defect report, and it gives the agent nothing to branch on: no field, no candidates, no next call.
  - No transcript shows an agent looping on it, so it stays Major, not Critical.
- **Remediation, as applied:** `on_call_tool` maps that `NotFoundError` to `invalid_argument` (temporary false). That is the existing code for a malformed call, which `## Defects` lists as not a defect, so the design gains no code. The envelope has:
  - `details.field: "name"`, the `tools/call` parameter, as `test_unknown_argument_is_named` names a stray key;
  - `details.candidates`: the server's tool names, read from the server;
  - no echo of the received name (`[6.offending-value]`; the error catalog already discloses that received values are never echoed);
  - repair `{next_step: "read_capabilities", tool: "atlas_get_reference", arguments: {topic: "capabilities"}}`. The right tool must be chosen, not corrected, so the repair is the lookup (`[6.repair-callable]`).

  RED: `tests/test_error_wire.py::test_unknown_tool_is_a_malformed_call[modern]` and `[legacy]` failed with `assert 'internal_error' == 'invalid_argument'` (`unknown-tool-red.txt`), and so did the new `EMITTED_CASES` entry in `tests/test_repairs.py`. GREEN: all three pass, and the repair validates against `atlas_get_reference`'s schema. Following it returns no `invalid_argument`. The design's Errors section and decisions row "Unknown tool name is `invalid_argument` (milestone 6 standards review)" record the choice. CHANGELOG: one Fixed line. `tools/list`, `INSTRUCTIONS` and the capability summary are unchanged.

**F2**

- **Severity:** Minor. **Deferred.**
- **Section:** §2 (`[2.summary]`, findability through `atlas_find_portals`)
- **Summary:** a portal whose only name is a renamed title part and whose host label is not its place cannot be found by its place. "Franklin" finds nothing. "FranklinForward" finds `performance.franklintn.gov`.
- **Evidence:** `surface.json`, `find["Franklin"]` is `[]`. Override 55 renamed the portal to "FranklinForward: City's Strategic Plan Website", and its host label is `performance`. The portal has no `place_names`.
- **Remediation:** an override with `place_names`, after the place is checked (the host `franklintn.gov` suggests Franklin, Tennessee; that is an inference, not probed).
- **Reason deferred:** design Registry step 4 limits place-name overrides to curated and profiled portals and the 50 largest, and says the rest match by host or generated name. This portal is in none of those groups, and the rename made it findable by its own title, where before it was findable only as "Government Financial Reports App".

**F3**

- **Severity:** Nit. **Deferred.**
- **Section:** §6 (`[6.details-field]`, `[6.document-codes]`)
- **Summary:** F1's `details.field: "name"` is not a parameter of any published tool, and the errors topic does not mention the unknown-tool case.
- **Evidence:** `[6.details-field]` names a published tool parameter for argument validation, and the method's own parameter for a non-tool RPC failure. An unknown tool fits neither case cleanly; `name` is the `tools/call` parameter that was wrong. `test_unknown_argument_is_named` already makes the same exception for a stray key.
- **Reason deferred:** the envelope describes itself. `reason` says to call one of `candidates`, `candidates` lists the five names, and the repair reads the contract. Documenting the case in the errors topic would add served bytes for a payload that needs no glossary (`[2.instructions-prefix]`'s reasoning about self-describing payloads).

### Checked and OK

- **Review Focus 1 (finding the new portals).** "Everett", "Everett, WA" and `everett` each return `data.everettwa.gov` alone. "King County", "King County, WA" and `king-county` each return `data.kingcounty.gov` alone. Both eras agree.
- **Review Focus 2 (Seattle and King County apart).** "Seattle" returns only `data.seattle.gov`, and "King County" only `data.kingcounty.gov`. "WA" returns all three Washington portals and `data.wa.gov`, by place name, as expected.
- **Review Focus 3 (no generic name).** "Tyler" and "Government Financial Reports" return nothing. "open data" returns 27 portals whose names contain both words (e.g. "City of Bloomington Open Data"). That is the documented every-word match, and none of these names is generic as a whole: `test_shipped_names_are_not_generic` passes. "Cook County" ranks `datacatalog.cookcountyil.gov` first, and the rejected `cookcounty.data.socrata.com` third, by host.
- **Review Focus 4 (no-argument listing).** `atlas_find_portals {}` returns `isError: false` and 1,963 bytes on both eras. It lists Chicago and Seattle (`curated`), then Everett and King County (`profiled`), then `generic` portals by id. With `page_size: 50` it is 6,968 bytes.
- **Names as data, not schema (`[9.additive-direction]`, `[2.surface-is-contract]`).** Portal `id` is the identifier, and it did not change for any entry (the review's diff check: 242 to 242, none dropped or added). `name` is a label inside an unchanged schema, and the CHANGELOG says which names changed. Non-ASCII names (`California State Controller’s Office`) match an ASCII-apostrophe query.
- **Order (`[9.deterministic-order]`).** Candidates are ordered by match, then tier, then id, as the description says (`tests/test_find_portals.py`).
- **Topic `portals`.** The index lists the four curated and profiled portals with titles from their names. The Everett item lists its reviewed `f6vp-3svh` and its guide. The King County item says "No guides for this portal." and lists `j56h-zgnm` as profiled, which matches the merged pack.
- **Task 4 change (7e9f8bf).** No schema or description changed. Seattle parity (`test_pack_levels_seattle_unchanged`) and Chicago `curated` pass in the full suite.

### Probes

| Probe | Evidence |
| --- | --- |
| Cold start | **Measured:** `instructions` is 1,797 characters on both eras (cap 1,800), unchanged. **Not checked:** a live session on a target client. |
| First repair | Unknown tool, after F1: `invalid_argument`, `details.field: "name"`, five candidates, repair `atlas_get_reference({"topic": "capabilities"})`, on both eras. `content[0].text` parses equal to `structuredContent` (`test_unknown_tool_is_a_malformed_call`). |
| Advertised vs actual | Every candidate's `name` is its registry name. The topic `portals` titles equal the candidates' names. |
| Discovery cost | `tools/list` framed: **24,560 bytes** modern and **23,944** legacy, against 24,576. Unchanged from milestone 5; the snapshot did not change. |
| Resource freshness | Not re-read: no resource changed. |
| Cross-version | No fingerprint (deferred under `[9.fingerprint]`). |
| Long-running operation | Skipped: no duration changed. |
| Tool selection | Skipped: no tool name or description changed. |
| Capability gating | Skipped: no capability changed. |
| Security boundary | Skipped: no tool or annotation changed. |

### Coverage

| Section | Status | Notes |
| --- | --- | --- |
| §1 Server-Level | not-checked | Focused route. Only `[1.spec-revision]` (unchanged), `[1.negotiated-caps]` and `[1.transport]` were read, by closure; no §1 surface changed. |
| §2 Discovery | finding F2 | Otherwise OK: Review Focus 1–4 above. |
| §3 Tools | not-checked | Focused route; no tool schema or description changed. |
| §4 Resources | not-checked | Focused route; no resource changed. |
| §5 Prompts | not-checked | Focused route; there are no prompts. |
| §6 Failure Recovery | findings F1 (fixed), F3 | Otherwise OK: the fix keeps the tool-result carrier (`[6.tool-errors]`) and the one envelope (`[6.repair-object]`, `[6.presence]`). |
| §7 Long-Running Operations | not-checked | Focused route; no duration changed. |
| §8 Token Efficiency | OK | No-argument listing 1,963 B; page of 50 6,968 B; topic `portals` 930 B. |
| §9 Versioning | OK | Ids unchanged, names are data, order deterministic, CHANGELOG lines present. |

**Residual risks:**

- `tools/list` still has 16 bytes of headroom.
- About 95 portals keep their host as their name and match only by host label.
- No live client session checked F1's envelope on a real host.

## Part 2: separating-context-from-constraints

### Targets and classification

| Target | Surface class | Result |
| --- | --- | --- |
| `docs/design.md` Registry step 4 (17dd54d, 519053a) | long-form; a rule-bearing list item | S1 (fixed), S2 (deferred) |
| `docs/design.md` Curation runbook, milestone 6 bullets and the Evidence and Merging bullets | long-form | clean under R1–R5; A-5 (accuracy) |
| `registry_overrides.toml` header (519053a, 2ddddb0) | long-form comment block | S3 (fixed); A-4 (accuracy) |
| `CONTRIBUTING-portals.md` step 6 and its served copy, changed by this review | long-form runbook step | clean |
| `docs/design.md` Place fields "Placeholders" and "What degrades" (7e9f8bf), changed by this review | long-form, definitions | clean under R1–R5; A-2 (clarity) |
| `skills/curate-portal/SKILL.md` | — | unchanged in the milestone; not audited |

### Findings

**S1**

- **Rule:** R2 (secondary R1). **Severity:** Minor. **Fixed.**
- **Location:** `docs/design.md`, Registry step 4, fourth bullet.
- **Quoted text:** "**Generated names are reviewed by hand** when a rebuild changes them. A name that is a vendor's or another organization's, or that would mislead `find_portals`, gets an override: …"
- **Why it fails:** it is phrased in the present tense, like the facts around it in step 4, so a reader cannot tell whether it describes what milestone 6 did or binds every later rebuild. Every review since has treated it as binding.
- **Rewrite, as applied:** "**Review generated names by hand** whenever a rebuild changes them. Give a name that is a vendor's or another organization's, or that would mislead `find_portals`, an override: another part of the same portal's title, or the host." This is the promoted form. The milestone 6 review applied the step to every changed name, so binding is the intent.

**S2**

- **Rule:** R3. **Severity:** Minor. **Deferred (author decision).**
- **Location:** the same bullet: "or that would mislead `find_portals`".
- **Why it fails:** "mislead" names no event a reviewer can check. The two cases on record are checkable: a name that ranks the portal above another portal for that portal's own place (`cookcounty.data.socrata.com`), and a name equal to another portal's (`health.data.ny.gov`). The bullet does not say whether those are the whole test.
- **Alternatives (the author decides):**
  - (a) Narrow: "or that ranks the portal ahead of another portal for that other portal's place, or equals another portal's name".
  - (b) Keep it open and add the cases as examples: "or that would mislead `find_portals` (for example, …)".
- **Reason deferred:** each option changes the policy's scope, which is the maintainer's call. No rebuild is planned in this milestone.

**S3**

- **Rule:** R1. **Severity:** Minor. **Fixed.**
- **Location:** `registry_overrides.toml` header, end of "Coverage".
- **Quoted text:** "… have no override. Give aliases only to portals being curated or profiled: so far Chicago …"
- **Why it fails:** the one rule in the block sat at the end of a paragraph listing coverage facts.
- **Rewrite, as applied:** a separate paragraph: "Aliases: give them only to portals being curated or profiled. So far: Chicago (milestone 2), and Everett and King County (milestone 6), each now in its pack."

The other changed prose is clean:

- **CONTRIBUTING step 6.** The new sentence is a permission ("can declare", R2 clear), plus the fact that bounds it (computed-region columns ignore declarations). It is checkable against describe's output (R3).
- **Curation runbook milestone 6 bullets.** History only, with no rule.
- **Registry step 4's other bullets.** They state the naming algorithm and override precedence as facts, and `tests/test_registry.py` pins them.

### Outside R1–R5 (accuracy, and the items routed to this task)

- **A-1 (Minor, fixed; routed item 2).** `CONTRIBUTING-portals.md` step 6 and the served copy (`src/opendata_atlas/assets/contributing.md`) described `placeholders` only for `placeholder_share`, behind 7e9f8bf. Step 6 now adds: "A reviewed `place_field` on a text column can declare its column's placeholders the same way, with `placeholders`; on a computed-region column, describe ignores them." `tests/test_contributing.py` passes (the copies match; the topic is 15,151 B against 23,552).
- **A-2 (Minor, fixed; routed item 3).** In the design:
  - The "Placeholders" bullet now says declarations apply only to a text place field, and a computed-region column ignores every declaration on it (`_declared_placeholders` gates on `source == "column"`).
  - In "What degrades", the two sentences about a `place_field`'s declaration have moved out of the definition of a degraded claim and into the degraded-declaration sub-bullet, which now says that only the declaration degrades.
  - The described behavior is unchanged.
- **A-3 (Minor, fixed; routed item 4).** "Government Financial Reports [App] is the vendor app's name" was stated as fact. It was inferred from the string heading three unrelated portals' titles, and nothing probed it. It now reads as an inference, marked not probed, in overrides 54–56, `docs/evidence/registry-names-2026-10-20/review.md` (six places), and the Task 2 decisions row "Registry rebuilt with title names (milestone 6)". The renames stand on the inference.
- **A-4 (Minor, fixed).** The overrides header was stale after the King County merge. It said 58–59 were "for curation", noted only Everett's move into its pack, and left `data.kingcounty.gov` out of the pack-defined portals. It now says both entries moved into their packs, and it lists all four pack-defined portals.
- **A-5 (Minor, fixed).** The Curation runbook named only milestone 4's paths: evidence `curation-chicago-<date>-run<N>/` and review `<date>-m4-chicago-pack.md`. Milestone 6's runs use `curation-everett-…` and `curation-king-county-…`. The runbook now gives `curation-<portal>-<date>-run<N>/` and `<date>-m<N>-<portal>-pack.md`, with milestone 4's as examples.

**Safety note:** none. No target held instructions aimed at the auditor.

### Summary

| Rule | Count |
| --- | --- |
| R1 | 2 (S3; S1 secondary) |
| R2 | 1 (S1) |
| R3 | 1 (S2) |
| R4 | 0 |
| R5 | 0 |

| Severity | Count |
| --- | --- |
| Material | 0 |
| Minor | 3 (S1 and S3 fixed, S2 deferred) |

Outside R1–R5: five Minor items (A-1 to A-5), all fixed.

**Assessment.** The milestone's prose is mostly facts: the naming algorithm, override precedence and run history. They are stated as facts, and tests pin the algorithm. Its two rules both needed work. The rule for reviewing names by hand read as a description (S1), and it rests on a judgment word (S2). The aliases rule was buried in a coverage list (S3). Most of the defects were drift, not separation: served and design text lagged a behavior fix (A-1, A-2), comments lagged a pack merge (A-4), and an inference was stated as fact (A-3).

## Counts

| Review | Material | Minor |
| --- | --- | --- |
| agent-friendly-mcp | 1 (F1, fixed) | 2 (F2, F3; deferred with reasons) |
| separating-context-from-constraints | 0 | 3 (S1, S3 fixed; S2 deferred, author decision), plus A-1 to A-5 outside R1–R5, all fixed |

## Final measures

| Measure | Value | Limit |
| --- | --- | --- |
| `tools/list` framed, modern (2026-07-28) | 24,560 B | 24,576 |
| `tools/list` framed, legacy (2025-11-25) | 23,944 B | 24,576 |
| `INSTRUCTIONS` | 1,797 characters | 1,800 |
| capability summary | 10,571 B (unchanged) | — |
| topic `contributing` payload | 15,151 B (14,984 before A-1) | 23,552 |
| `atlas_find_portals {}` `structuredContent` | 1,963 B | — |

Source: `surface.json`, and `tests/test_contributing.py::test_contributing_fits_budget`.
