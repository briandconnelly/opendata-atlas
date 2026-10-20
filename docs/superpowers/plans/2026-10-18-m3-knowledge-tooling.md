# opendata-atlas Milestone 3: Knowledge Tooling — Implementation Plan

> **Status: complete.** Historical plan, kept for provenance; do not execute it. Current design: [docs/design.md](../../design.md).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make portal knowledge checkable and self-maintaining. This milestone adds typed checkers, a drift run that writes `validation.json`, runtime freshness, a release gate, a profiler, a contribution path and a curation skill an agent can follow, and the knowledge-gap rule. It also fixes three knowledge failures found in milestone 2's evals.

**Architecture:** Claims gain typed assertions (`portals/checkers.py`). The drift run (`portals/drift.py`, driven by `tests/test_drift.py`) executes each assertion's probe live and merges outcomes into the shipped `portals/validation.json`. `PortalContext` carries those checks. `portals/freshness.py` turns them into a per-claim `validation`, and degrades stale verdicts in one place that describe, query and the portal summary all read. The profiler (`opendata_atlas/profiler/`, console script `atlas-profile`) writes draft packs made only of observations. `CONTRIBUTING-portals.md` and `skills/curate-portal/SKILL.md` describe the path from a draft pack to a curated portal, and `tests/test_tiers.py` enforces it.

**Tech Stack:** Python ≥3.13, uv, FastMCP 4 on MCP SDK v2, Pydantic, httpx, ijson, anyio; ruff, ty, prek; pytest with the record/replay `tests/http_fixtures.py`; `claude -p` for evals and the curation run.

**Spec:** `docs/design.md`: Milestones item 3, Fact model, Validation state and freshness, Building knowledge, Byte budgets, Evals ("Stale claim", "Knowledge-gap offer"). Read it with `docs/decisions.md` and `docs/upstream-facts.md`. Carry-over inputs: `docs/superpowers/plans/2026-10-18-m3-carryover.md`. Scope rulings: the controller's milestone 3 scope file, items 1–16. Standards: `agent-friendly-mcp` and `separating-context-from-constraints`.

**Scope notes:**
- **Out of scope**, each recorded as a decisions row in Task 16 and not planned:
  - the token probe and `SOCRATA_APP_TOKENS`;
  - icon by URL (F7), the README status word and the release-cut test (milestone 5);
  - F8 lifecycle `_meta`, F9 resource `size` and F10 `$schema` (milestone 5 surface pass);
  - `guides_by_id` (left as is);
  - scrubbing inherited fixture identities (the maintainer's decision);
  - Chicago curation (milestone 4).
- **Base branch:** `docs/design` (head `06a3c76`). Work on `feat/knowledge-tooling`. The repo has no remote: never push.
- **Live and paid steps** are marked **[LIVE]** or **[PAID, background]**. A background step runs with `run_in_background`. Its result is checked against the stated expected outcome before the task continues.

## Global Constraints

- Names: tool prefix `atlas_`, URI scheme `opendata-atlas`, error class `AtlasError`, sentinel `END OPENDATA ATLAS INSTRUCTIONS`.
- Tooling and transport: uv only (never pip, no `requirements.txt`); ruff, ty and prek; FastMCP 4 on MCP SDK v2; stdio only; MCP 2026-07-28, compatible with 2025-11-25.
- Gate for every task: `uv run pytest -q`, `uv run ruff check`, `uv run ruff format --check`, `uv run ty check`, `uv run prek run --all-files`.
- Commits: Conventional Commits, each ending with a blank line, then `🤖 Generated with Claude Code` and `Claude-Session: https://claude.ai/code/session_01CH7uTSKtTjy4NoHCYKFHyx` on the next line. Never commit to `docs/design` directly.
- "24 KiB `tools/list` and per-result budgets"; "one error envelope, every repair a literal call validated by test" (design Constraints). `tools/list` is 22,852 bytes today (compact, as `tests/test_contract.py` measures).
- `instructions` is "at most 1,800 characters, sentinel included" (ruling 23). Never raise the cap.
- Freshness: "a claim is `stale` when its `checked_at` is older than 180 days by the server's clock." A stale `ok` reliability, column timezone or reviewed placeholder declaration "is reported as `unknown`, with `validation: "stale"`". A stale `partial` or `unreliable` verdict "is kept, with `validation: "stale"`".
- Checkers: "A checker returns `passed | contradicted | inconclusive`. Missing groups, an empty result, or fewer than `min_groups` is `inconclusive`, never `passed`." "A claim with no assertion … is reported with `validation: "unchecked"`."
- "The profiler never writes an interpretation, reliability, or tier."
- "A pack PR touches only `portals/<id>/`, `evals/portals/<id>.json` and `registry_overrides.toml`" (Task 13 adds `portals/validation.json`; see its decisions row).
- **Seattle parity (this milestone):** with `portal: "seattle"`, wording may change, but warnings, values and repairs must not. The exception is a claim that is genuinely stale under the fixture clock. A test assertion change beyond `validation` values, the new fields this plan names, or Fire 911's knowledge level (Task 5) is a parity difference: stop and report it.
- **Surface changes are intended** in Tasks 3, 5, 7 and 9 only. Regenerate `tests/snapshots/tools_list.json` (`UPDATE_SNAPSHOTS=1`) only for the change the task specifies, and add a CHANGELOG `## [Unreleased]` line naming it. Any other snapshot change is a defect.
- Facts: record only facts you probed. Label reviewer-reported facts `(review)`. Cite facts carried over from seattle-open-data as `seattle-open-data docs/upstream-facts.md@26c6628`. Commit raw probe outputs under `docs/evidence/<topic>-<date>/` and cite them by repo path. Saved bodies keep no personal data (rulings 25, 27).
- When a design choice changes, update `docs/design.md` and add a row to `docs/decisions.md`. Choices marked *(Claude's call)* in this plan get that row in the task that makes them.
- Polite upstream access: the profiler and drift run send one request at a time, through `SodaClient` (its User-Agent, a timeout on every request, ≤ 4 concurrent per host).
- The one clock: runtime freshness reads `opendata_atlas.portals.freshness.today()`, called through the module attribute so tests can pin it.
- Prose standard: the implementer audits every agent-consumed prose surface its task changes with `separating-context-from-constraints` and lists the findings and fixes in the task report. Those surfaces are instructions, the capability summary, tool and resource descriptions, error and hint messages, `knowledge_notice` text, `CONTRIBUTING-portals.md`, `SKILL.md`, `AGENTS.md`, `docs/design.md` and plans. A task is not complete while a Material finding it introduced is open.

## Per-task review lenses

- When a task's diff touches the MCP surface, the reviewer applies `agent-friendly-mcp`'s focused route to the sections touched:
  - read `[1.spec-revision]` and the native-vs-convention rule;
  - read the touched sections in full;
  - close over the ids they cite;
  - report the rest `not-checked`.
- When a task's diff touches a listed prose surface, the reviewer applies `separating-context-from-constraints` R1–R5 to the changed text.

## Review Focus

1. **A probe fails upstream** (a 5xx, a timeout, `query.soql.*`). Expected: that probe's assertions are `inconclusive`, with the error code in `detail`. The session still writes `validation.json`, and the claim is never `passed`. Test in Task 2.
2. **The 180-day boundary and clock skew.** Expected: a check exactly 180 days old is fresh and one 181 days old is stale. A `checked_at` later than the server's date (a release built ahead, or a skewed clock) is fresh and never an error. Test in Task 3.
3. **A claim removed or renamed in a pack whose old id is still in `validation.json`.** Expected: the runtime ignores the entry, and the next drift merge drops it. The release gate never counts an orphan as a failure. Test in Task 2.
4. **A zero-match text equality whose literal holds `''`, `%` or `_`; an equality on a number column.** Expected: the hint's repair `where` is valid SoQL (quotes stay doubled) and validates against the schema. A number-column equality gets no hint. Test in Task 7.
5. **The profiler on a portal with `timezone: null`, or a dataset with zero rows or no time column.** Expected: no timezone claim, a `notes` entry saying why, and exit 0. Test in Task 11.

---

## File Structure

```
src/opendata_atlas/
  portals/
    checkers.py        # checker params, functions, CHECKERS                        (Task 1)
    model.py           # typed Assertion, padded_values kind, PortalContext.checks  (Tasks 1, 3)
    validation.py      # ClaimCheck, ValidationFile, load/write, gate_failures      (Tasks 2, 4, 12)
    validation.json    # generated by the drift run; shipped                        (Task 2)
    drift.py           # asserted_claims, check_claim, merge_results               (Task 2)
    freshness.py       # today(), claim_validation, degraded, combine               (Task 3)
    knowledge.py       # takes the portal and today; text-filter notice             (Tasks 3, 6)
    tiers.py           # tier_violations                                           (Task 13)
    seattle/facts/*.toml   # probes on 4 place fields, 3 timezones; Fire 911 unit   (Tasks 2, 5)
  profiler/            # cli.py, profile.py, emit.py; console script atlas-profile   (Task 11)
  core/
    budget.py          # wire_size (query) / payload_size (others), ENVELOPE_RESERVE, fit()  (Task 8)
    describe.py, query.py, portals.py, reference.py, reference_service.py, models.py, arguments.py
  assets/contributing.md   # served copy of CONTRIBUTING-portals.md                  (Task 13)
CONTRIBUTING-portals.md                                                             (Task 13)
skills/curate-portal/SKILL.md                                                       (Task 14)
scripts/drift_issues.py, scripts/capture_server.py                                  (Tasks 4, 12)
.github/workflows/drift.yml                                                         (Task 4)
docs/pack-examples/*.toml                                                           (Task 1)
evals/run.py, evals/tasks.json, evals/portals/seattle.json, evals/fixtures/          (Task 12)
tests/  test_checkers.py, test_drift.py (integration), test_drift_offline.py, test_freshness.py,
        test_release_gate.py, test_drift_issues.py, test_budget.py, test_reference_paging.py,
        test_profiler.py, test_evals.py, test_contributing.py, test_tiers.py,
        test_curation_skill.py (integration, opt-in)
```

---

### Task 1: Typed checkers, the `padded_values` kind and pack examples

**Files:**
- Create: `src/opendata_atlas/portals/checkers.py`, `tests/test_checkers.py`, `docs/pack-examples/` with one file per claim kind: `placeholder_share.toml`, `region_layer.toml`, `column_timezone.toml`, `unit_of_observation.toml`, `place_field.toml`, `padded_values.toml`.
- Modify: `src/opendata_atlas/portals/model.py`, `tests/test_packs.py`, `docs/design.md` (Fact model), `docs/decisions.md`, `CHANGELOG.md`.

**Interfaces:**
- Produces, in `checkers.py` (no import from `model.py`):
  - `Outcome = Literal["passed", "contradicted", "inconclusive"]`.
  - `CheckerName = Literal["share_by_group", "value_present", "value_absent", "dst_gap", "diurnal_peak", "metadata_equals", "metadata_before"]`.
  - `@dataclass(frozen=True) CheckResult`: `outcome: Outcome`, `detail: str`. `detail` is one line naming the group or value that decided the outcome.
  - The params models below are `extra="forbid"`. Row values arrive as strings; a value that will not parse as a number makes that row missing.
    - `ShareByGroup`: `group: str | None = None` (None: every row is one group), `numerator: str`, `denominator: str`, `where: str | None = None` (pattern `^\s*\w+\s*(<=|>=|<|>|=|!=)\s*-?\d+(\.\d+)?\s*$`, applied to the result rows), `min: float | None = None`, `max: float | None = None`, `min_groups: int = 1` (≥ 1). At least one of `min` and `max` is required.
    - `ValuePresent`: `column: str`, `value: str`, `count: str | None = None`, `min_count: int = 1`.
    - `ValueAbsent`: `column: str`, `value: str`.
    - `DstGap`: `hour: str = "h"`, `count: str = "n"`, `gap_hour: int = 2` (0–23), `min_neighbor_rows: int = 1`, `max_gap_rows: int = 0`.
    - `DiurnalPeak`: `hour: str = "h"`, `count: str = "n"`, `peak_from: int`, `peak_to: int` (0–23, `peak_from ≤ peak_to`), `min_hours: int = 20`, `min_rows: int = 100`.
    - `MetadataEquals`: `field: str` (dotted path), `value: str | int | float | bool`.
    - `MetadataBefore`: `field: str`, `before: date`. The field's value is epoch seconds or an ISO date or datetime.
  - `CHECKERS: dict[CheckerName, tuple[type[BaseModel], Literal["soql_probe", "metadata_probe"]]]`: each checker's params model and the evidence kind it reads.
  - `run_check(checker: CheckerName, params: BaseModel, data: Any) -> CheckResult`. `data` is `list[dict[str, Any]]` for SoQL checkers and `dict[str, Any]` for metadata checkers; a wrong type is `inconclusive`.
- Semantics:
  - **Common to the SoQL checkers:** an empty result is `inconclusive`.
  - `share_by_group`: keep the rows that pass `where`. A row missing either field, or with denominator 0, is not a group. Fewer counted groups than `min_groups` is `inconclusive`. Any share outside `[min, max]` is `contradicted`, and `detail` names that group. Otherwise `passed`.
  - `value_present`: no row with `column == value` is `contradicted`. A row whose `count` is below `min_count` is also `contradicted`.
  - `value_absent`: a matching row is `contradicted`.
  - `dst_gap`: a missing hour counts as 0 rows. Either neighbor (`gap_hour ± 1`) below `min_neighbor_rows` is `inconclusive`. A gap hour with at most `max_gap_rows` rows is `passed`; otherwise `contradicted`.
  - `diurnal_peak`: fewer than `min_hours` distinct hours, or fewer than `min_rows` rows in total, is `inconclusive`. The peak is the hour with the largest count; on a tie, the earliest. A peak within `[peak_from, peak_to]` is `passed`; otherwise `contradicted`.
  - `metadata_*`: a missing or unparseable field is `inconclusive`. `metadata_before` passes when the value's date is before `before`.
- Produces, in `model.py`:
  - `Assertion`: `checker: CheckerName`, `probe: int = 0` (≥ 0), `params: dict[str, Any] = {}`. An after-validator validates `params` against `CHECKERS[checker][0]`, and the error names the checker. Property `typed_params -> BaseModel`.
  - `Claim.kind` gains `"padded_values"`: values carry leading or trailing whitespace, so an unpadded equality matches nothing. It needs no interpretation.
  - Property `Claim.probes -> list[SoqlProbe | MetadataProbe]` lists the probe evidence in evidence order. A validator requires each assertion's `probe < len(claim.probes)` and `claim.probes[probe].kind == CHECKERS[checker][1]`.
  - `MetadataProbe.path` gains the pattern `^/api/`: a path on the portal's public host.
- *(Claude's call)* Two choices get a decisions row:
  - `probe` indexes the claim's probe evidence, because a claim may hold several probes and the design does not say which one an assertion reads.
  - `padded_values` is a claim kind, because the carry-over's padded-values observation needs one.

- [ ] **Step 1: Failing tests** in `tests/test_checkers.py`, over literal row lists. Each checker gets a passed, a contradicted and an inconclusive case.
  - Design example rows: `[{"y": "2008", "ph": "98", "n": "100"}, … through "2016"]` with `ShareByGroup(group="y", numerator="ph", denominator="n", where="y <= 2016", min=0.9, min_groups=9)` gives `passed`. With 8 years it gives `inconclusive`. With one year at `ph/n = 0.5` it gives `contradicted`, and `"2011"` is in `detail`.
  - `test_empty_result_is_inconclusive_for_every_soql_checker`.
  - `test_missing_fields_are_not_groups`: rows lacking `ph` with `min_groups=1` give `inconclusive`.
  - `test_dst_gap`: hours 1 and 3 have rows and hour 2 is absent: `passed`. Hour 2 with 5 rows: `contradicted`. Hour 1 absent: `inconclusive`.
  - `test_diurnal_peak_ties_take_the_earliest_hour`.
  - `test_metadata_before_reads_epoch_and_iso`: `{"rowsUpdatedAt": 1437350400}` before `2016-01-01` passes.
  - `test_params_reject_unknown_keys` (`ShareByGroup(..., foo=1)`).
  - `test_where_rejects_soql`: `where="y <= 2016 OR 1=1"` raises.
- [ ] **Step 2: Failing tests** in `tests/test_packs.py`:
  - `test_assertion_params_are_validated_at_load`: `_CLAIM_TOML`'s `params = {x = 1}` raises `PackError` naming `value_present`. Update `_CLAIM_TOML` to `params = {column = "v", value = "-"}`.
  - `test_assertion_probe_index_in_range`: probe 1 with one probe raises.
  - `test_metadata_checker_needs_metadata_probe`.
  - `test_pack_examples_validate`: each `docs/pack-examples/*.toml` loads as a `Pack`, and together they cover every `Claim.kind` value, six kinds.
- [ ] **Step 3: Run → FAIL** (`uv run pytest tests/test_checkers.py tests/test_packs.py -v`).
- [ ] **Step 4: Implement** `checkers.py` and the `model.py` changes, and write the six examples with illustrative ids (`abcd-1234`):
  - `placeholder_share`: the design's example, verbatim.
  - `region_layer`: `metadata_before` on `rowsUpdatedAt`, plus a `document` evidence.
  - `column_timezone`: `dst_gap` (probe 0) and `diurnal_peak` (probe 1).
  - `unit_of_observation`: `document` only.
  - `place_field`: single-row `share_by_group`.
  - `padded_values`: `value_present`.
- [ ] **Step 5: Run → PASS**; full gate.
- [ ] **Step 6: Docs.**
  - `docs/design.md` Fact model:
    - name the params per checker and the `probe` index;
    - add `padded_values`;
    - remove "*(not built yet: milestone 3 carry-over)*" from the pack-examples bullet.
  - Add the decisions row and a CHANGELOG line ("pack assertions are typed").
- [ ] **Step 7: Commit** — `feat: type pack assertions with a checker catalog`

---

### Task 2: Drift run, `validation.json` and Seattle probes

**Files:**
- Create: `src/opendata_atlas/portals/validation.py`, `src/opendata_atlas/portals/drift.py`, `src/opendata_atlas/portals/validation.json` (generated), `tests/test_drift.py` (integration), `tests/test_drift_offline.py`, `tests/fixtures/http/drift_seattle.json` (recorded).
- Modify:
  - `tests/conftest.py`;
  - `src/opendata_atlas/core/describe.py` (`served_evidence`);
  - `tests/test_guides.py`, `tests/test_seattle_pack_parity.py`;
  - `src/opendata_atlas/portals/seattle/facts/tazs-3rd5.toml`, `ppi5-g2bj.toml`, `kzjm-xkqj.toml`, `65db-xm6k.toml`, `33kz-ixgy.toml`;
  - `docs/upstream-facts.md`, `docs/design.md` (Validation state, Drift checks), `docs/decisions.md`, `CHANGELOG.md`.

**Interfaces:**
- Consumes: `Claim.probes`, `Assertion.typed_params`, `run_check`, `Outcome`, `SodaClient.soql`, `SodaClient.get_json`, `load_portal`, `PORTALS_DIR`.
- Produces, in `validation.py`:
  - `VALIDATION_PATH = PORTALS_DIR / "validation.json"`.
  - `ClaimCheck(_Strict)`: `checked_at: date`, `outcome: Outcome`, `previous_outcome: Outcome | None = None`.
  - `ValidationFile(_Strict)`: `portals: dict[str, dict[str, ClaimCheck]] = {}`, keyed by canonical portal id, then claim id.
  - `load_validation(path: Path | None = None) -> ValidationFile`.
    - A missing file gives an empty `ValidationFile`.
    - Malformed JSON or a schema error raises `PackError` naming the file.
    - Cached only for the default path.
  - `write_validation(file: ValidationFile, path: Path) -> None`: sorted keys, `indent=1`, trailing newline.
- Produces, in `drift.py`:
  - `@dataclass AssertionResult`: `checker: str`, `probe: int`, `outcome: Outcome`, `detail: str`, `request: str` (the SoQL text or the metadata path).
  - `@dataclass ClaimResult`: `portal_id: str`, `claim_id: str`, `outcome: Outcome`, `assertions: list[AssertionResult]`.
  - `asserted_claims(packs_dir: Path = PORTALS_DIR) -> list[tuple[PortalContext, Claim]]`: every claim with at least one assertion, in every pack directory that has a `portal.toml`.
  - `async check_claim(client: SodaClient, portal: PortalContext, claim: Claim) -> ClaimResult`.
    - Each probe the assertions name runs once, sequentially.
    - A `soql_probe` runs as `client.soql(portal, claim.scope.dataset or claim.scope.layer, {"$query": probe.query})`.
    - A `metadata_probe` runs as `client.get_json(f"https://{portal.identity.public_host}{probe.path}", portal=portal)`.
    - An `AtlasError` makes that probe's assertions `inconclusive`, with `detail` = the error code (Review Focus 1).
    - The claim's outcome is `contradicted` if any assertion is, else `inconclusive` if any is, else `passed`.
  - `merge_results(old: ValidationFile, results: Iterable[ClaimResult], today: date, live: Mapping[str, set[str]]) -> ValidationFile`.
    - A result sets `checked_at=today` and `outcome`, and moves the old outcome to `previous_outcome`.
    - An entry with no result is kept if its claim is in `live` (portal id → asserted claim ids), and dropped otherwise (Review Focus 3).
  - `report_json(results: list[ClaimResult]) -> dict[str, Any]`: `{"generated_at", "results": [{"portal", "claim", "outcome", "assertions": [{"checker", "probe", "outcome", "detail", "request"}]}]}`.
- Produces, in `tests/conftest.py`:
  - option `--drift-report PATH`;
  - fixture `drift_results` (session stash, `list[ClaimResult]`);
  - `pytest_sessionfinish`: when results exist, it writes `merge_results(load_validation(VALIDATION_PATH), …, datetime.now(UTC).date(), live)` to `VALIDATION_PATH`, plus the report when `--drift-report` is given.
- Produces `tests/test_drift.py`: `pytestmark = pytest.mark.integration`, and `test_claim_still_holds`. It is parametrized over `asserted_claims()` with ids `f"{portal.id}:{claim.id}"`, appends its result to `drift_results`, and asserts `outcome == "passed"`.
- Produces `describe.served_evidence(evidence: list[Evidence]) -> str` *(Claude's call)*, which replaces `_evidence_text`. It serves the first `manual_observation` note, else the first probe's `observation`, else the first `document` quote. `tests/test_guides.py` (`TIME_EVIDENCE`) and `tests/test_seattle_pack_parity.py` both call it, which reconciles the carry-over's evidence pick. Served Seattle text stays byte-identical, because new probe evidence is appended after the existing note.

- [ ] **Step 1: Failing offline tests** in `tests/test_drift_offline.py`:
  - `test_merge_moves_outcome_to_previous`;
  - `test_merge_keeps_unrun_live_claims`;
  - `test_merge_drops_claims_no_longer_in_packs` (Review Focus 3);
  - `test_probe_failure_is_inconclusive`: an `httpx.MockTransport` answers 503; outcome `inconclusive`, `"upstream_unavailable"` in `detail` (Review Focus 1);
  - `test_missing_validation_file_is_empty`;
  - `test_malformed_validation_file_names_it`;
  - `test_served_evidence_prefers_the_manual_note`.
- [ ] **Step 2: Run → FAIL. Step 3: Implement** `validation.py`, `drift.py`, the conftest hooks, `served_evidence` and `tests/test_drift.py`.
- [ ] **Step 4: [LIVE] Probe and write the Seattle assertions.** Run each query below once through `client.soql`, sequentially. Save the rows to `docs/evidence/drift-<date>/seattle-probes.json`.
  - **Place fields:** `tazs-3rd5` `sector` and `beat`, and `ppi5-g2bj` `sector` and `beat`. On each existing `-place` claim, append a `soql_probe`:
    - query: `SELECT sum(case(<col> IS NULL OR <col> IN ('', '-', '0', 'FK ERROR', 'NULL', 'OOJ', 'UNKNOWN', 'X'), 1, true, 0)) AS ph, count(*) AS n`;
    - `observation`: the observed `ph/n`;
    - assertion: `share_by_group {numerator = "ph", denominator = "n", max = <observed share rounded up to 0.01, plus 0.02>}`.
  - **Timezones:** `kzjm-xkqj` `datetime`, `65db-xm6k` `date` and `33kz-ixgy` `cad_event_original_time_queued`. Append two `soql_probe` evidences:
    - probe 0, `SELECT date_extract_hh(<col>) AS h, count(*) AS n WHERE <col> >= '2026-03-08T00:00:00' AND <col> < '2026-03-09T00:00:00' GROUP BY h`, checked by `dst_gap {}`;
    - probe 1, the same grouping over `'2025-01-01T00:00:00'` to `'2026-01-01T00:00:00'`, checked by `diurnal_peak {peak_from = <observed peak − 2>, peak_to = <observed peak + 2>}`. For `65db-xm6k`, whose rows are one per hour, `n` is the `sum(...)` of the total count column its live view names.
  - Keep each claim's `manual_observation` first.
  - If a probe contradicts the claim it is meant to support, stop: re-probe once. If it still contradicts, record it in upstream-facts and ask the controller before changing the interpretation.
- [ ] **Step 5: [LIVE] Record the replay fixture.**
  - Run `RECORD_FIXTURES=1 uv run pytest tests/test_drift_offline.py::test_check_claim_replays_recorded_probes`. It writes `drift_seattle.json`.
  - The test runs `check_claim` on the seven Seattle claims with `@pytest.mark.soda_fixture("drift_seattle")` and asserts every outcome is `passed`.
  - Then run it without `RECORD_FIXTURES`. Expected: PASS offline.
- [ ] **Step 6: [LIVE] Drift run.**
  - Run `uv run pytest --run-integration -m integration tests/test_drift.py tests/test_live.py -v --drift-report docs/evidence/drift-<date>/report.json`.
  - Expected: 7 `test_claim_still_holds` PASS and every guide example PASS.
  - `validation.json` then holds `data.seattle.gov` with exactly the 7 claim ids, each `outcome: "passed"`, `checked_at` today, `previous_outcome: null`.
  - Before trusting that, confirm the writer surfaces a failure. Run `test_merge_*` with a synthetic contradicted result and check that it appears in the merged file.
- [ ] **Step 7: Docs.**
  - `docs/upstream-facts.md`: record the probe results as Verified, dated, citing the evidence.
  - Decisions rows:
    - close "Seattle per-column place probes (milestone 2 carry-over)";
    - close "`describe._time` evidence pick" with the `served_evidence` rule;
    - add one row for the `validation.json` format and the merge and prune rules.
  - `docs/design.md`: describe the format and the drift session.
  - CHANGELOG.
- [ ] **Step 8: Commit** — `feat: run pack assertions live and write validation.json`

---

### Task 3: Runtime freshness and asymmetric degradation

**Files:**
- Create: `src/opendata_atlas/portals/freshness.py`, `tests/test_freshness.py`.
- Modify:
  - `src/opendata_atlas/portals/model.py`, `loader.py`, `registry.py`, `knowledge.py`;
  - `src/opendata_atlas/core/models.py`, `describe.py`, `query.py`, `reference.py`, `reference_service.py`;
  - `tests/conftest.py`, `tests/test_knowledge.py` (callers of the new signatures) and every test that pins `validation: "unchecked"`;
  - `tests/snapshots/tools_list.json`, `CHANGELOG.md`, `docs/design.md`, `docs/decisions.md`.

**Interfaces:**
- Consumes: `ValidationFile`, `ClaimCheck`, `load_validation`.
- Produces:
  - `PortalContext.checks: Mapping[str, ClaimCheck] = field(default_factory=dict)`: claim id to check, for this portal.
  - `load_portal(directory: Path, *, validation: ValidationFile | None = None) -> PortalContext`. `None` means `load_validation()`. It fills `checks` from `validation.portals.get(identity.id, {})`.
  - `context_for` passes through to `load_portal`; without a pack, `checks` is empty.
  - In `freshness.py`:
    - `STALE_AFTER_DAYS = 180`.
    - `today() -> date`: `datetime.now(UTC).date()`.
    - `claim_validation(portal: PortalContext, claim: Claim, today: date) -> Validation`. No assertion, or no entry, gives `"unchecked"`. `(today - checked_at).days > 180` gives `"stale"`. Otherwise the entry's outcome. A future `checked_at` is fresh (Review Focus 2).
    - `degraded(portal: PortalContext, claim: Claim, today: date) -> bool`: True when the claim is stale and its verdict is one that degrades. Those are a `place_field` or `region_layer` interpretation with `reliability == "ok"`, a `column_timezone` interpretation, or a `placeholder_share` with a reviewed declaration.
    - `combine(validations: Iterable[Validation]) -> Validation`: the worst value in the order `contradicted`, `stale`, `inconclusive`, `unchecked`, `passed`. An empty input gives `"unchecked"`.
  - `knowledge.py` takes the portal and today (signatures change from `pack` to `portal: PortalContext` and gain `today`):
    - `primary_time(portal, dataset_id, time_columns, *, today: date) -> list[str]`;
    - `column_knowledge(portal, dataset_id, column, *, layer_id: str | None = None, today: date) -> Knowledge | None`;
    - `dataset_knowledge(portal, dataset_id, knowledge_bearing, primary_time, *, layers: Mapping[str, str] | None = None, today: date) -> Knowledge`;
    - `knowledge_notice(portal, dataset_id, *, places, time_columns, referenced, today: date) -> KnowledgeNotice | None`;
    - `pack_levels(portal, *, today: date) -> dict[str, KnowledgeLevel]`.
    - Effective rule:
      - A degraded claim counts as unreviewed for every level and for `primary_time`.
      - `validation` is `combine` over the covering claims (column) or the dataset's claims and layers (dataset).
      - The notice treats a referenced knowledge-bearing column with any stale covering claim as a gap. The message names it, with the word "stale".
  - `describe.place_specs(portal, dataset_id, columns, *, today: date)`.
    - A degraded place claim gives a spec with `reliability: "unknown"` and `validation: "stale"`. Its reason: "Reviewed as ok, but its checks last ran on <checked_at>, over 180 days ago; treat its coverage as unknown."
    - A stale `partial` or `unreliable` claim keeps its reliability and reason and gets `validation: "stale"`.
  - `core/models.py`:
    - `Reliability = Literal["ok", "partial", "unreliable", "unknown"]`.
    - `PlaceField.validation: Validation | None = None`, `CoverageWarning.validation: Validation | None = None` and `TimeSemantics.validation: Validation | None = None`. Each is set only when `"stale"`, so fresh Seattle output gains no field *(Claude's call)*.
    - `coverage_warnings` fire on `unknown` too, since `_warnings` already fires on every reliability other than `ok`.
  - A stale timezone claim makes `time_semantics` report `timezone` and `evidence` omitted, with `validation: "stale"`.
  - A stale reviewed placeholder declaration *(Claude's call)*:
    - its values are no longer excluded, and appear in `candidate_placeholders`;
    - `placeholder_values` and `assigned_fraction` are omitted, so the field never reads more complete than reviewed;
    - the column's knowledge is `validation: "stale"`.
  - Every caller passes `today=freshness.today()`, computed once per call in `describe._describe`, `query._run` and `reference_service.portal_summary`.
  - `core/reference.py`:
    - CAPABILITIES `## Semantics` Knowledge item replaces "In this release every claim reports `validation: "unchecked"` …" with the freshness rule and the `unknown` reliability. Add the design-required sentence: "Scheduled drift checks cannot change an installed release; the runtime freshness rule is what protects old installs."
    - CONTRIBUTING's `validation` paragraph says the same.
  - `portal_summary`: its final Knowledge line reports validation counts instead of "Every claim: `validation: \"unchecked\"`".
  - `tests/conftest.py`: an autouse fixture monkeypatches `opendata_atlas.portals.freshness.today` to `date(2026, 10, 18)`.

- [ ] **Step 1: Failing tests** in `tests/test_freshness.py`:
  - `test_fresh_check_reports_its_outcome`: `kzjm-xkqj-datetime-timezone` reports `"passed"`;
  - `test_claim_without_assertions_is_unchecked` (`region-ru88-fbhk`);
  - `test_asserted_claim_without_entry_is_unchecked`;
  - `test_180_days_is_fresh_181_is_stale` (Review Focus 2);
  - `test_future_checked_at_is_fresh` (Review Focus 2);
  - `test_combine_order`.
- [ ] **Step 2: Failing behavior tests** over the recorded fixtures `describe_crime_full`, `query_coverage_grouped` and `describe_fire_full`. Each uses a context whose checks put the claim at `today − 181 days`:
  - `test_stale_ok_place_field_reads_unknown`:
    - the `tazs-3rd5` `sector` place field has `reliability == "unknown"` and `validation == "stale"`;
    - a query grouping by `sector` carries a coverage warning with `reliability == "unknown"` and `validation == "stale"`;
    - the `knowledge_notice` message contains `` `sector` `` and "stale".
  - `test_stale_partial_verdict_is_kept`: a test claim, partial, asserted and stale keeps `reliability == "partial"` with `validation == "stale"`, and its warning is kept.
  - `test_stale_timezone_reads_unknown`: the Fire 911 `datetime` entry in `time_semantics` has no `timezone`, with `validation == "stale"`.
  - `test_stale_placeholder_declaration_withholds_assigned_fraction`: a test asserted placeholder claim leaves `assigned_fraction` and `placeholder_values` absent, and the declared values sit in `candidate_placeholders`.
  - `test_fresh_seattle_output_has_no_validation_fields`: no `validation` key on Seattle place fields, warnings or time entries.
  - `test_capability_summary_states_installed_release_rule`.
- [ ] **Step 3: Run → FAIL. Step 4: Implement.**
- [ ] **Step 5: Parity check.**
  - Run the full suite and update only assertions that pin `validation` values (`"unchecked"` becomes `"passed"` for the 7 asserted claims, or what `combine` gives for datasets).
  - Put the list of changed assertions in the report. Any other change is a parity difference.
- [ ] **Step 6: Snapshot and docs.**
  - Snapshot: `Reliability` gains `unknown`; the three `validation` fields. Inspect the diff and check `tools/list` ≤ 24,576.
  - CHANGELOG.
  - `docs/design.md`:
    - Validation state: remove the "Milestone 2:" bullet; add `unknown`, the placeholder rule and the field placement;
    - Place fields;
    - Tools: describe and query.
  - Decisions rows: the `unknown` reliability; the stale placeholder declaration; validation fields only when stale.
- [ ] **Step 7: Commit** — `feat: degrade stale claims at runtime`

---

### Task 4: Release gate and the weekly drift workflow

**Files:**
- Create: `tests/test_release_gate.py`, `scripts/drift_issues.py`, `tests/test_drift_issues.py`, `.github/workflows/drift.yml`, `tests/test_workflows.py`.
- Modify: `src/opendata_atlas/portals/validation.py`, `pyproject.toml` (`uv add --dev pyyaml`), `docs/releasing.md`, `docs/design.md` (Drift checks), `docs/decisions.md`.

**Interfaces:**
- Consumes: `load_validation`, `asserted_claims`, `report_json`'s shape.
- Produces:
  - `validation.gate_failures(file: ValidationFile, asserted: Mapping[str, set[str]]) -> list[str]`. It returns one line per failing claim:
    - `outcome == "contradicted"`;
    - `outcome == "inconclusive" and previous_outcome == "inconclusive"`;
    - an asserted claim with no entry.
    Orphaned entries are not failures (Review Focus 3).
  - In `scripts/drift_issues.py` (pure functions, then a CLI):
    - `issue_bodies(report: dict[str, Any]) -> dict[str, tuple[str, str]]`: portal id → (title, Markdown body). It covers only portals with a contradicted or inconclusive claim. Title: `f"Drift: {portal_id}"`. The body has a table with columns claim, outcome, checker, request, detail, then the line "Re-probe, then correct or remove the claim (docs/design.md: Release gate)."
    - `main(argv: list[str] | None = None) -> int`: `drift_issues.py <report.json> --out <dir>` writes `<dir>/<portal_id>.md` and `<dir>/titles.tsv` (`portal_id<TAB>title`).
  - `.github/workflows/drift.yml`:
    - triggers: `schedule: cron "41 15 * * 1"` and `workflow_dispatch`;
    - permissions: `contents: read`, `issues: write`;
    - checkout and setup-uv pinned to the SHAs `live.yml` uses;
    - steps: `uv sync --locked`; `uv run pytest --run-integration -m integration tests/test_drift.py --drift-report drift-report.json` with `continue-on-error: true`; `uv run python scripts/drift_issues.py drift-report.json --out drift-issues` with `if: always()`; then a shell loop over `titles.tsv`. The loop runs `gh issue list --label drift --state open --search "<title> in:title"`, then `gh issue comment` on a match, else `gh issue create --label drift`, with `GH_TOKEN: ${{ github.token }}`.
    - It is **unexercised until the repository has a remote**; the workflow's header comment and the decisions row say so.

- [ ] **Step 1: Failing tests.**
  - `tests/test_release_gate.py`:
    - `test_shipped_validation_passes_the_gate`: `gate_failures(load_validation(), live) == []`;
    - `test_gate_catches_contradicted`, `test_gate_catches_inconclusive_twice`, `test_gate_allows_one_inconclusive`, `test_gate_catches_missing_entry`. These are the known positives on synthetic files.
    - `test_gate_ignores_orphaned_entries` (Review Focus 3).
  - `tests/test_drift_issues.py`:
    - `test_only_failing_portals_get_issues`;
    - `test_body_lists_query_and_observed_result` (the request text and `detail` are in the body);
    - `test_titles_tsv_written`.
  - `tests/test_workflows.py::test_drift_workflow_shape`, parsed with `yaml.safe_load`: weekly schedule, `issues: write`, the pytest command string, and `if: always()` on the issue steps. `test_live_workflow_unchanged`: its run line is still `uv run pytest --run-integration -m integration`.
- [ ] **Step 2: Run → FAIL. Step 3: Implement. Step 4: Run → PASS**; full gate.
- [ ] **Step 5: Docs.**
  - `docs/releasing.md` `## Rules`: "Before tagging, run `uv run pytest --run-integration -m integration` and commit the regenerated `src/opendata_atlas/portals/validation.json`; `tests/test_release_gate.py` must pass."
  - Decisions row: the gate rules; the workflow is unexercised without a remote; issues are deduplicated by title.
- [ ] **Step 6: Commit** — `feat: gate releases on validation and open drift issues weekly`

---

### Task 5: Fire 911 "most calls are medical" on the describe path

**Files:**
- Modify: `src/opendata_atlas/portals/seattle/facts/kzjm-xkqj.toml`, `src/opendata_atlas/portals/validation.json`, `src/opendata_atlas/core/models.py`, `core/describe.py`, tests that pin Fire 911's knowledge level or notice, `tests/test_search_describe.py`, snapshot, CHANGELOG, `docs/design.md` (Tools: describe), `docs/upstream-facts.md`, `docs/decisions.md`.

**Interfaces:**
- Produces:
  - `UnitOfObservation(Closed)`: `unit: str`, `reason: str | None = None`.
  - `DescribeResult.unit_of_observation: UnitOfObservation | None = None`. It is set from the reviewed `unit_of_observation` claim on `facts_id`, so a filter view gets its parent's. It is never paged and repeats on every columns page.
  - Claim `kzjm-xkqj-unit`, kind `unit_of_observation`:
    - `interpretation = {unit = "dispatch", reason = "Most rows are medical responses (Aid Response, Medic Response), not fires; a count of 'fire calls' covers every response type."}`;
    - `reviewed_by = "claude"`, `reviewed_at` = today;
    - evidence: a `manual_observation` quoting the guide's inherited `type` line (seattle-open-data@26c6628), then the `soql_probe` from Step 1;
    - assertion: `share_by_group {group = "y", numerator = "med", denominator = "n", min = 0.5, min_groups = 6}`.
  - With every Fire 911 layer reviewed (`region-ru88`, `2day`, `cyqu`, `kuhn`, `q256`) and `datetime`'s timezone reviewed, Fire 911 becomes `knowledge.level: "reviewed"`, and its queries lose the unit-of-observation notice. This is the one permitted Fire 911 difference. *(Claude's call: describe, not query, carries the unit. Eval 03's agents call describe `full` before querying (`evals/results/2026-10-18-m2/03-fire-capitol-hill.capture.jsonl`), and a per-page query field would spend budget on every page.)*

- [ ] **Step 1: [LIVE] Probe** (sequential; save to `docs/evidence/drift-<date>/fire-types.json`):
  - `SELECT type, count(*) AS n GROUP BY type ORDER BY n DESC LIMIT 20` confirms the medical type names;
  - `SELECT date_extract_y(datetime) AS y, sum(case(type IN (<medical types>), 1, true, 0)) AS med, count(*) AS n WHERE datetime >= '2020-01-01T00:00:00' GROUP BY y`.
  - If any year's `med/n` is below 0.5, stop and report: the claim's wording would be unsupported.
- [ ] **Step 2: Failing tests.**
  - `test_fire_describe_serves_medical_unit` (fixture `describe_fire_full`): `unit_of_observation.unit == "dispatch"`, `"medical" in unit_of_observation.reason` and `knowledge.level == "reviewed"`.
  - `test_unit_absent_without_reviewed_claim` (fixture `query_knowledge`, `egc4-d24i`).
  - `test_crime_describe_serves_offense_unit`.
- [ ] **Step 3: Run → FAIL. Step 4: Implement**; add the claim.
- [ ] **Step 5: [LIVE]** `uv run pytest --run-integration -m integration tests/test_drift.py -k kzjm-xkqj-unit`. Expected: 1 PASS; `validation.json` gains `kzjm-xkqj-unit` `passed`, and the other 7 entries are unchanged.
- [ ] **Step 6:** Snapshot (`unit_of_observation`), CHANGELOG, design, upstream-facts (the type shares, Verified), decisions row. The row closes "Fire 911 'most calls are medical'" and points the eval re-run to Task 15. Full gate.
- [ ] **Step 7: Commit** — `feat: serve a dataset's unit of observation in describe`

---

### Task 6: `knowledge_notice` names the text columns a query filtered on

**Files:**
- Modify: `src/opendata_atlas/portals/knowledge.py`, `src/opendata_atlas/core/query.py`, `tests/test_knowledge.py`, `docs/design.md` (Place fields: Exploratory path; Tools: query), `docs/decisions.md`, `CHANGELOG.md`.

**Interfaces:**
- Produces:
  - `knowledge_notice(..., today: date, text_filters: Sequence[str] = ())`.
    - When `text_filters` is non-empty and no place field of the dataset is backed by a reviewed, non-degraded claim, the notice fires, even on a `reviewed` dataset.
    - Its message adds one sentence: `` "Text column(s) `area_name` filtered here are not reviewed place fields; if one stands for an area, say its meaning and completeness are unverified." `` It uses `_named` for the list, so a long list ends "(+N more)".
  - `query._text_filters(where: str, columns: list[dict[str, Any]]) -> list[str]`: the sorted names `_referenced(where, "")` returns whose view `dataTypeName` is `"text"`.
    - In clauses mode, `where` is `clauses["where"]` only, so `near` and the engine's keyset predicate are excluded.
    - In raw SoQL, `where` is the text between `WHERE` and the next clause keyword, from new `_soql_where(soql: str) -> str` (the `_CLAUSE` split).
- *(Claude's call: "filtered on" means the `where` clause; a `group_by`-only inspection carries no extra sentence.)*

- [ ] **Step 1: Failing tests**, with an `httpx.MockTransport` view (`area_name` text, `date_rptd` `floating_timestamp`, no claims), as in `tests/test_review_m3.py`:
  - `test_notice_names_filtered_text_column`: the message contains `` `area_name` `` and "not reviewed place fields";
  - `test_notice_ignores_grouped_only_text_column`;
  - `test_raw_soql_where_text_column_is_named`;
  - `test_no_extra_sentence_with_a_reviewed_place_field`: Seattle `tazs-3rd5` with where `offense_category = 'X'` gets no text-column sentence.
- [ ] **Step 2: FAIL. Step 3: Implement. Step 4: PASS**; full gate; design, CHANGELOG and decisions row.
- [ ] **Step 5: Commit** — `feat: name filtered text columns in the knowledge notice`

---

### Task 7: Zero-match hint for a text equality filter

**Files:**
- Modify: `src/opendata_atlas/core/models.py`, `core/query.py`, `tests/conftest.py` (`_check_repair_scope` also reads `hints[].repair`), `tests/test_repairs.py`, `tests/test_query.py`, snapshot, CHANGELOG, `docs/design.md` (Tools: query), `docs/upstream-facts.md`, `docs/decisions.md`.

**Interfaces:**
- Produces:
  - `QueryHint(Closed)`: `code: Literal["text_filter_matched_nothing"]`, `column: str`, `message: str`, `repair: Repair`.
  - `QueryResult.hints: list[QueryHint] | None = None`, never trimmed by the packer.
  - Trigger *(Claude's call, from `_run_clauses`)*. All of the following hold:
    - clauses mode, first page (`cursor is None`);
    - `clauses["where"]` contains `<name> = '<literal>'`, matched by `_TEXT_EQUALITY = re.compile(r"(?<![\w.:@`])(`[^`]+`|[A-Za-z_]\w*)\s*=\s*'((?:[^']|'')*)'")`, where `<name>` is a view column with `dataTypeName == "text"`;
    - the page is empty: `returned_rows == 0`, or there is no `group_by`, exactly one row, and every value in it is `0`, `"0"` or null. An ungrouped `count(*)` of nothing returns one zero row, which is how milestone 2's LA run met it.
    - At most one hint per column, and at most 3 hints.
  - Repair:
    ```python
    Repair(next_step="inspect_text_values", tool="atlas_query_dataset",
           arguments={"portal": portal.id, "dataset_id": dataset_id,
                      "select": [col, "count(*) AS n"], "group_by": [col], "order_by": ["n DESC"],
                      "where": <clauses["where"] with that one match replaced by
                               f"upper({col}) like '%{literal.strip().upper()}%'">,
                      **{k: clauses[k] for k in ("near", "search_text") if clauses.get(k)}},
           alternative="Values may be padded or differ in case; filter on a value this grouping returns.")
    ```
    Every other filter is kept. The literal keeps its doubled quotes (Review Focus 4). `message`: "No rows matched `<col>` = '<literal>'; this text column's values may carry padding or different case."
- Upstream facts this relies on, probed in Step 1: SoQL `upper()` and `like` on a text column; the padded `area_name` values (milestone 2 Task 15, `evals/results/2026-10-18-m2.md`).

- [ ] **Step 1: [LIVE] Probe** on data.lacity.org `k7nn-b2ep`:
  - `SELECT area_name, count(*) AS n WHERE upper(area_name) like '%HOLLYWOOD%' GROUP BY area_name ORDER BY n DESC`.
  - Expected: rows including the space-padded `'Hollywood'` and `'N Hollywood'`.
  - Save to `docs/evidence/hints-<date>/lacity-hollywood.json` and record in upstream-facts. If `upper()` is rejected, use `like` alone and record that.
- [ ] **Step 2: Failing tests** (MockTransport view: `area_name` text, `n_count` number):
  - `test_zero_rows_on_text_equality_gets_hint`;
  - `test_zero_count_aggregate_gets_hint` (one row `{"n": "0"}`);
  - `test_hint_repair_keeps_other_filters`: `where = "date_rptd >= '2026-09-01' AND area_name = 'Hollywood'"`, and the repair `where` still holds the date clause;
  - `test_literal_with_quote_and_wildcards`: `area_name = 'O''Brien_%'`; the repair `where` contains `'%O''BRIEN_%%'` and validates against the schema (Review Focus 4);
  - `test_number_equality_gets_no_hint` (Review Focus 4);
  - `test_nonempty_page_gets_no_hint`;
  - `test_continuation_page_gets_no_hint`;
  - add the hint case to `tests/test_repairs.py` `EMITTED_CASES`, so `assert_repair_callable` and `assert_repair_scope` run on `hints[0].repair`.
- [ ] **Step 3: FAIL. Step 4: Implement. Step 5: PASS.**
- [ ] **Step 6:** Snapshot (`hints`), CHANGELOG, design, decisions row (the trigger, and why the repair is an inspection that keeps every other filter), full gate.
- [ ] **Step 7: Commit** — `feat: hint when a text equality filter matches nothing`

---

### Task 8: Every result measured, and an envelope reserve that covers the stamp

**Controller ruling 35 (replaces the scope file's "one unit, payload_size" item):** do not loosen query. A query page's cost to the agent is what the client receives, and its text copy mirrors `structuredContent`; moving query to `payload_size` would let a trimmed page reach about twice its present wire size. So the rule is **one guarantee, two measures, every tool measured**:
- query keeps `wire_size` (text copy plus `structuredContent`), now against `RESULT_LIMIT` with a reserve that covers the modern `_meta` stamp and the JSON-RPC frame, so a full query page is ≤ 24,576 bytes on the modern wire;
- describe, reference and `atlas_find_portals` are measured by `payload_size` (ruling 19 kept: wire-measuring describe would page Seattle's 13.4 KB-payload fire `full` describe and break parity);
- every tool now has a test over its largest result. The decisions row says which measure each tool uses and why, and closes carry-over F6.

**Files:**
- Create: `tests/test_budget.py`.
- Modify: `src/opendata_atlas/core/budget.py`, `core/portals.py` (packing), `core/reference_service.py` only if a measured topic is over, existing whole-wire assertions the reserve change moves (`tests/test_query.py:125`, `tests/test_review_m3.py:77,89`, `tests/test_review_whole.py:186`: update their expected limit, never loosen them), `docs/design.md` (Byte budgets), `docs/decisions.md`, `CHANGELOG.md`.

**Interfaces:**
- Produces:
  - `ENVELOPE_RESERVE = 1024` *(Claude's call: 699 bytes of protocol fields and `_meta` measured in the milestone 2 final review, plus about 36 bytes of JSON-RPC frame, rounded up)*.
  - `RESULT_LIMIT = RESULT_BYTE_BUDGET - ENVELOPE_RESERVE` (23,552).
  - `wire_size` and `payload_size` both stay; `budget.py`'s module docstring names which tools use which.
  - `fit(count: int, settle: Callable[[int], None], measure: Callable[[], int], *, limit: int = RESULT_LIMIT) -> int`: bisects to the largest `n ≤ count` with `measure() ≤ limit` after `settle(n)`, and leaves the result settled at `n` (may be 0). Query's `_fit` and `find_portals` packing use it.
  - `find_portals` packs whole candidates with `fit` (measure `payload_size`); `has_more` and the cursor offset continue after the last candidate returned.

- [ ] **Step 1: Failing tests** in `tests/test_budget.py`:
  - `test_envelope_reserve_covers_modern_overhead`: call `atlas_get_reference({"topic": "index"})` with the `client` fixture; `overhead = len(compact_json({k: v for k, v in wire(result).items() if k not in ("structuredContent", "content")}).encode()) + len('{"jsonrpc":"2.0","id":2147483647,"result":}')`; assert `overhead > 600` (known positive: the stamp is present) and `overhead ≤ ENVELOPE_RESERVE`.
  - `test_query_page_fits_modern_wire`: the `query_wide_rows` first page, as the modern client receives it (whole `wire(result)` plus the frame string above), is ≤ 24,576 bytes and holds ≥ 1 row.
  - `test_largest_result_per_tool_fits`, parametrized, each asserting its tool's measure ≤ `RESULT_LIMIT`: query `query_wide_rows` page (`wire_size`); describe 300-column summary and full first pages and Seattle fire `full` (`payload_size`); reference every static topic and item, the Seattle `portals` item and the Seattle guides index (`payload_size`); find_portals no-argument call with `page_size: 50` (`payload_size`).
  - `test_find_portals_packing_continues`: with a limit forced low via `monkeypatch` on `budget.RESULT_LIMIT`, walking `has_more`/cursor returns every candidate exactly once.
- [ ] **Step 2: Run** `uv run pytest tests/test_budget.py -v`: FAIL (reserve 512; no `fit`).
- [ ] **Step 3: Implement.** Record the `query_wide_rows` first-page row count before and after for the decisions row (it may drop by a row; paging delivers every row).
- [ ] **Step 4: PASS**; full gate.
- [ ] **Step 5: Docs.** `docs/design.md` Byte budgets: the guarantee, which measure each tool uses, the reserve; replace the "could reach about 187 bytes over" sentence with the measured result of `test_query_page_fits_modern_wire`. Decisions row "Result budget measures (ruling 35, carry-over F6)" with before/after row counts. CHANGELOG line if the trimmed page's row count changed.
- [ ] **Step 6: Commit** — `fix: reserve room for the modern result envelope`

---

### Task 9: Budget fixtures for 100 guides and 2,000 portals; reference paging

**Files:**
- Create: `tests/test_reference_paging.py`.
- Modify: `src/opendata_atlas/core/reference_service.py`, `core/models.py`, `core/arguments.py` (`check_reference`), `mcp/tools.py`, `mcp/resources.py`, `tests/test_find_portals.py`, snapshot, CHANGELOG, `docs/design.md` (Tools 5, Continuation, Byte budgets), `docs/decisions.md`.

**Interfaces:**
- Consumes: `fit`, `payload_size`, `cursors.encode/decode`.
- Produces:
  - `atlas_get_reference` gains `cursor: Cursor = None`.
  - `ReferenceResult.has_more: bool | None = None` and `next_cursor: str | None = None`. `has_more` is present whenever `entries` is, and `next_cursor` only when more entries follow.
  - `reference_service.read(portal, topic, item_id, *, cursor: str | None = None, paged: bool = True) -> ReferenceResult`.
    - Entry lists are packed with `fit`. The first page lists every entry when they all fit. A body is never paged.
    - Cursor kind `"reference"`, with `portal_id` = the guides portal's id, else `"*"`, and state `{"t": topic, "o": offset, "f": <sha256[:12] of entry ids>}`.
    - A changed entry list gives `cursor_expired`.
  - Continuation: with `cursor`, `topic` must equal the cursor's, and `portal` is required for `guides` and must resolve to the cursor's portal; a mismatch is `invalid_cursor`. `item_id` is `invalid_argument`. Repair: `list_items` with the topic (and `portal` for guides).
  - Resources call `read(..., paged=False)` *(Claude's call: a resource has no cursor parameter, and the per-result budget binds tool results; F9 resource `size` is milestone 5)*.
- Estimate behind this task: Seattle's 7-guide index is 2,309 bytes of payload, about 270 per entry, so 100 guides would be about 27 KB, over `RESULT_LIMIT`.

- [ ] **Step 1: Failing tests** in `tests/test_reference_paging.py`. Fixtures: a context with 100 synthetic guides (titles of 60 characters, descriptions of 200, bodies of about 2 KB), and a 2,000-entry registry (`load_registry(tmp_path / "registry.json", packs_dir=tmp_path)`, 40-character names, generic).
  - `test_hundred_guides_index_pages_within_budget`: the first page has `has_more`, and every page satisfies `payload_size ≤ RESULT_LIMIT`. The walk yields 100 unique ids in order.
  - `test_hundred_guides_portal_summary_fits`: the body names all 100 and fits.
  - `test_seattle_guides_index_is_not_paged`: `has_more` is False, there is no `next_cursor`, and the 7 entries are unchanged.
  - `test_reference_cursor_rules`: `item_id` with `cursor` is `invalid_argument`; another topic or portal is `invalid_cursor`; a changed list is `cursor_expired`.
  - `test_guides_resource_is_unpaged`.
  - In `tests/test_find_portals.py`, `test_two_thousand_portals_page_within_budget`: the no-argument walk at `page_size` 50 keeps every page within budget, and the union is all 2,000 ids, with no duplicates.
  - `test_portal_index_with_many_profiled_portals_pages`: 300 entries are profiled, and the `portals` index pages within budget.
- [ ] **Step 2: FAIL. Step 3: Implement. Step 4: PASS.**
- [ ] **Step 5:**
  - Snapshot (`cursor` parameter; `has_more`, `next_cursor`) and check `tools/list` ≤ 24,576.
  - CHANGELOG.
  - `docs/design.md`: Tools 5 replaces "a cursor arrives if it outgrows the result budget" with the rule; add a Continuation bullet; in Byte budgets remove both "(not built yet …)" markers.
  - Decisions row.
  - Full gate.
- [ ] **Step 6: Commit** — `feat: page reference entry lists within the result budget`

---

### Task 10: Knowledge-gap head rule and capability section

**Files:**
- Modify: `src/opendata_atlas/core/reference.py`, `tests/test_reference_topics.py`, `docs/design.md` (Instructions head rules; Knowledge-gap reports), `docs/decisions.md`, `CHANGELOG.md`.

**Interfaces:**
- Produces:
  - In `HEAD_RULES`, "Offer a server defect (capabilities ## Defects) to the user." becomes **"Offer the user a defect or knowledge-gap issue (capabilities ## Defects, ## Knowledge gaps)."**. "Never file an issue unasked." stays.
  - `INSTRUCTIONS` line 1 becomes **"Read-only SoQL access to registered public Socrata portals; every data tool takes `portal`."** to make room. Measured: these two edits give 1,797 characters, against 1,778 today and the cap of 1,800.
  - CAPABILITIES gets `## Knowledge gaps` right after `## Defects`. It holds:
    - what qualifies: a field, timestamp or dataset that misled the answer, or knowledge it needed that was missing (no reviewed place field, a stale claim, a placeholder or padding the pack does not declare);
    - what does not: the publisher's data quality as such; a gap is the server's missing or wrong account of it;
    - what to include: portal id, dataset id, column, and what was wrong;
    - the label: issues carry the `knowledge-gap` label, which is the curation queue;
    - the tracker is public: offer, and never file unasked.
  - The `knowledge-gap` label itself cannot be created without a remote. The decisions row says the maintainer creates it when the repository is published.

- [ ] **Step 1: Failing tests.**
  - Replace `test_knowledge_gap_rule_waits_for_milestone_3` with `test_knowledge_gap_head_rule_and_section`:
    - the exact rule is in `HEAD_RULES`;
    - `## Knowledge gaps` follows `## Defects`;
    - it contains `knowledge-gap`, "portal id", "dataset id" and "column";
    - "Never file an issue unasked." is in `HEAD_RULES`.
  - Update `test_defect_head_rule_is_short_and_details_stay_in_defects` to the new rule.
  - `test_instructions_fit_the_ruling_23_limit` is unchanged.
- [ ] **Step 2: FAIL. Step 3: Implement. Step 4: PASS.**
- [ ] **Step 5:** Prose audit of the changed instructions and capability summary. Design: remove "Knowledge-gap issues: milestone 3 …; not served yet." CHANGELOG, decisions row (the displaced wording and the length), full gate.
- [ ] **Step 6: Commit** — `feat: let agents offer knowledge-gap issues`

---

### Task 11: The profiler

**Files:**
- Create: `src/opendata_atlas/profiler/__init__.py`, `profiler/cli.py`, `profiler/profile.py`, `profiler/emit.py`, `tests/test_profiler.py`, `docs/evidence/profile-<date>/`.
- Modify: `pyproject.toml` (`[project.scripts] atlas-profile = "opendata_atlas.profiler.cli:main"`), `docs/upstream-facts.md`, `docs/design.md` (The profiler), `docs/decisions.md`, `CHANGELOG.md`.

**Interfaces:**
- Consumes: `load_registry`, `RegistryEntry`, `SodaClient` (`get_json`, `view`, `soql`), `SHARED_PLACEHOLDERS`, `run_check`, `Claim`, `PortalIdentity`.
- Produces, in `profile.py`:
  - `DatasetProfile(BaseModel)`: `dataset_id: str`, `title: str`, `page_views: int | None`, `claims: list[str]`, `notes: list[str]`.
  - `ProfileReport(BaseModel)`: `portal_id: str`, `identity_verified: bool`, `identity_detail: str`, `asset_mix: dict[str, int]`, `flagship_basis: str`, `datasets: list[DatasetProfile]`, `profiled_at: date`.
  - `async profile_portal(client: SodaClient, entry: RegistryEntry, *, datasets: int, today: date) -> tuple[ProfileReport, list[Claim]]`. Requests run one at a time, with no task groups.
  - Pure helpers, tested offline:
    - `identity_verified(pages: list[list[dict]], result_domain: str) -> bool`;
    - `flagships(results: list[dict], n: int) -> list[dict]`: by `resource.page_views.page_views_total` descending (missing counts as 0), then id;
    - `spring_forward(zone: ZoneInfo, lo: date, hi: date) -> date | None`: the latest date in `[lo, hi]` whose UTC offset increases;
    - `observe_text(dataset_id: str, column: str, query: str, rows: list[dict], today: date) -> list[Claim]`;
    - `observe_region(dataset_id: str, column: str, layer_id: str, query: str, rows: list[dict], today: date) -> Claim`;
    - `observe_time(dataset_id: str, column: str, gap: tuple[str, list[dict]], day: tuple[str, list[dict]], today: date) -> Claim | None`.
- Steps, following design "The profiler" 1–5:
  1. **Identity:** three Discovery pages with the entry's `catalog_query`, compared against `result_domain`. If identity is not verified, write the report and exit 3.
  2. **Asset mix:** `GET https://api.{region}.socrata.com/api/catalog/v1/domains/{catalog_domain}/facets`, reading `datatypes` (Verified in `docs/upstream-facts.md`).
  3. **Flagships:** one Discovery page, `catalog_query` + `only=dataset&order=page_views_total&limit=100`, sorted client-side by `flagships`. `flagship_basis` records which.
  4. **Per dataset** (the view, then sequential probes):
     - **Computed-region columns:** `SELECT count(<col>) AS filled, count(*) AS n` gives a `place_field` claim with no interpretation. Its assertion is `share_by_group {numerator="filled", denominator="n", min=<observed − 0.05, floored to 0.01>}`. The observation names the layer id and the candidate label column (the layer view's first text column other than `_feature_id`).
     - **Text columns:** the first 20 in schema order, each grouped as `SELECT <col> AS v, count(*) AS n GROUP BY <col> ORDER BY n DESC LIMIT 101`. Only columns with ≤ 100 groups (categorical) are observed; the rest are noted as skipped, which keeps free text and personal names out *(Claude's call)*.
       - A group value in `SHARED_PLACEHOLDERS` gives a `placeholder_share` claim, with no `placeholders` declaration, and one `value_present {column="v", value, count="n"}` per candidate.
       - Values that differ from `value.strip()` give a `padded_values` claim. Its observation reports the padded groups' share of rows, and its assertion is `value_present` on the most common padded value.
     - **Time columns:** the first 3 time-typed columns. Run `min`/`max` first. If the portal has a timezone with DST and `spring_forward(zone, lo, hi)` is not None, run the `dst_gap` day probe and the `diurnal_peak` probe over the last year in the data, giving a `column_timezone` claim with no interpretation. Otherwise add a note saying why, and emit no claim (Review Focus 5).
  5. **Assertions:** an assertion is emitted only if `run_check` passes on the profiler's own probe rows; otherwise the claim keeps the evidence without it.
  - Claim ids: `f"{dataset_id}-{column}-{suffix}"`, with suffix `fill`, `placeholders`, `padded` or `timezone`. Unique.
- Produces, in `emit.py`:
  - `render_claims(claims: list[Claim]) -> str`: TOML. Strings use `json.dumps(..., ensure_ascii=True)`; dates are bare; params are inline tables.
  - `pack_files(identity: PortalIdentity, claims: list[Claim]) -> dict[str, str]`: `{"portal.toml", "facts/<id>.toml", "regions.toml" only if layer claims}`. `portal.toml` copies the registry identity, including its current `tier` unchanged *(Claude's call: `PortalIdentity` requires a tier; copying it never promotes one)*.
- Produces, in `cli.py`: `main(argv: list[str] | None = None) -> int` for `atlas-profile <host> [--datasets N] [--out DIR] [--report PATH]`.
  - `--datasets` defaults to 10.
  - `--out` defaults to `src/opendata_atlas/portals/<id>` when `src/opendata_atlas/portals` exists under the working directory; otherwise it is required.
  - An unknown host, or an existing `--out`, is exit 2.
  - `--report` defaults to stdout JSON.

- [ ] **Step 1: [LIVE] Probe the flagship order.**
  - Run `curl -s 'https://api.us.socrata.com/api/catalog/v1?domains=data.lacity.org&only=dataset&order=page_views_total&limit=3' -A opendata-atlas-profiler/0 | python3 -m json.tool > docs/evidence/profile-<date>/order-probe.json`.
  - Expected: HTTP 200, 3 results whose `resource.page_views.page_views_total` descend.
  - Record it in upstream-facts. If the response is 4xx, drop `order` and record that.
- [ ] **Step 2: Failing tests** in `tests/test_profiler.py`. An `httpx.MockTransport` serves a synthetic portal: one dataset with a padded `area_name`, a `-` placeholder in `zone`, a computed-region column, and a `floating_timestamp` with an empty 2 a.m. on 2026-03-08 under `America/Los_Angeles`.
  - `test_profile_emits_observations_only`: no claim has an interpretation, reliability, `placeholders` or `reviewed_by`.
  - `test_profile_never_writes_a_tier`: `portal.toml`'s tier equals the registry entry's.
  - `test_emitted_assertions_pass_on_their_own_probe`.
  - `test_padded_values_claim`: the value is `'Hollywood   '`.
  - `test_dst_claim_on_spring_forward_day`.
  - `test_null_timezone_portal_skips_timezone_probes` (Review Focus 5).
  - `test_zero_row_dataset_is_noted` (Review Focus 5).
  - `test_noncategorical_text_column_is_skipped`.
  - `test_emitted_pack_round_trips`: `load_portal` on the written directory succeeds, and claims are equal after re-parse.
  - `test_unverified_identity_exits_3`, `test_existing_out_dir_exits_2`, `test_requests_are_sequential` (max in-flight is 1).
  - `test_spring_forward` (2026-03-08 for Los Angeles; None for `Pacific/Honolulu`).
- [ ] **Step 3: FAIL. Step 4: Implement. Step 5: PASS**; full gate (including `uv run atlas-profile --help`).
- [ ] **Step 6: [LIVE, background] Profiler run.**
  - `uv run atlas-profile data.lacity.org --datasets 5 --out docs/evidence/profile-$(date +%F)/data.lacity.org --report docs/evidence/profile-$(date +%F)/report.json`
  - Expected:
    - exit 0;
    - `report.json` has `identity_verified: true` and 5 `datasets`;
    - the draft directory loads with `uv run python -c "from pathlib import Path; from opendata_atlas.portals.loader import load_portal; load_portal(Path('docs/evidence/profile-<date>/data.lacity.org'))"`;
    - re-running `drift.check_claim` over its asserted claims (one-off script, output saved as `recheck.json`) gives `passed` for every claim.
  - Personal-data check:
    - first confirm the pattern catches a known positive: `echo 'a.b@seattle.gov (206) 555-0100' | grep -cE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}|\(?[0-9]{3}\)?[-. ][0-9]{3}[-. ][0-9]{4}'` prints 1;
    - then the same `grep -rnE` over the evidence directory must print nothing.
- [ ] **Step 7:** Record in upstream-facts what the run observed; design "The profiler" (CLI flags, the categorical rule, the assertion-passes rule, the tier copy); decisions row; CHANGELOG.
- [ ] **Step 8: Commit** — `feat: add the atlas-profile draft-pack profiler`

---

### Task 12: Per-portal eval runner, task move and new eval tasks

**Files:**
- Create: `evals/portals/seattle.json`, `evals/fixtures/validation-stale.json`, `tests/test_evals.py`.
- Modify: `evals/tasks.json`, `evals/run.py`, `scripts/capture_server.py`, `src/opendata_atlas/portals/validation.py`, `docs/design.md` (Per-portal eval tasks; Evals), `docs/decisions.md`.

**Interfaces:**
- Produces:
  - `evals/run.py [--host claude|codex] [--portal NAME] <out_dir> [task_id ...]`. `--portal NAME` reads `evals/portals/NAME.json`, where `NAME` is the pack directory name; otherwise it reads `evals/tasks.json` (cross-portal tasks). The `claude -p --tools ""` restriction is unchanged.
  - Task fields: `id`, `prompt`, `expect`, optional `env`, `server_args: list[str]` (appended to the `capture_server.py` arguments) and `covers: list[Literal["in_area", "relative_date", "misleading_field", "not_published"]]` (design "Per-portal eval tasks", decidable by Task 13).
  - `scripts/capture_server.py [--validation PATH] <capture.jsonl>`. `--validation` calls `validation.set_override(path)` before `build_server()`.
  - `validation.set_override(path: Path | None) -> None`: `load_validation()` with no argument then reads `path`. It clears the default cache.
  - Split *(Claude's call)*:
    - `evals/portals/seattle.json` holds tasks 01–24, `27-unreviewed-on-curated` and new `30-stale-claim`;
    - `evals/tasks.json` keeps `25`, `26`, `28` and `29`, and gains new `31-knowledge-gap-offer`.
    - `covers` on Seattle: `03` `["in_area", "relative_date"]`, `14` `["misleading_field"]`, `04` and `24` `["not_published"]`.
  - `30-stale-claim`:
    - `server_args: ["--validation", "evals/fixtures/validation-stale.json"]`. The fixture is the shipped `validation.json` with `tazs-3rd5-sector-place` `checked_at = 2026-01-01`, more than 180 days before any run date in this milestone.
    - prompt: a September 2026 offense count in one SPD sector; the sector value is taken from live describe output in Step 3.
    - expect: "Surfaces the sector coverage warning (reliability `unknown`, validation `stale`) and caveats the count as unverified; never presents sector as a verified field."
  - `31-knowledge-gap-offer`:
    - prompt: "Using LAPD's crime data, how many offenses were reported in the Hollywood area last month?"
    - expect: "Answers from data.lacity.org `k7nn-b2ep`, caveats `area_name` as unverified or padded, and offers the user a knowledge-gap issue (portal, dataset, column, what misled) without claiming to have filed one."

- [ ] **Step 1: Failing tests** in `tests/test_evals.py`:
  - `test_task_ids_unique_across_files`;
  - `test_task_fields_allowed`;
  - `test_covers_values_known`;
  - `test_server_args_paths_exist`;
  - `test_seattle_file_holds_the_seattle_tasks` (01–24, 27, 30);
  - `test_cross_portal_file` (25, 26, 28, 29, 31);
  - `test_stale_fixture_marks_only_its_claim_stale`: with `today=2026-10-18`, only `tazs-3rd5-sector-place` is stale;
  - `test_claude_command_restricts_tools`: `"--tools", ""` is in `claude_command(...)`, and the capture args include `server_args`.
- [ ] **Step 2: FAIL. Step 3: Implement**; choose task 30's sector value from a live `atlas_describe_dataset` (`tazs-3rd5`, `full`) and record it in `expect`.
- [ ] **Step 4: PASS**; full gate. The run itself is Task 15.
- [ ] **Step 5:** Docs.
  - Design: Per-portal eval tasks (the runner flag, `covers`, `server_args`); Milestones item 3 ("Seattle's existing eval tasks move to `evals/portals/seattle.json`" is done).
  - Decisions row: the split and the fixture mechanism; there is no product configuration for validation paths.
- [ ] **Step 6: Commit** — `feat: run eval tasks per portal and add the stale-claim and knowledge-gap tasks`

---

### Task 13: Contribution path, served as topic `contributing`, and the tier test

**Files:**
- Create: `CONTRIBUTING-portals.md`, `src/opendata_atlas/assets/contributing.md` (byte-identical served copy), `src/opendata_atlas/portals/tiers.py`, `tests/test_tiers.py`, `tests/test_contributing.py`.
- Modify: `src/opendata_atlas/core/reference.py` (`CONTRIBUTING` reads the packaged copy via `importlib.resources`; topic title "Contributing portal knowledge"), `tests/test_reference_topics.py`, `docs/design.md` (Knowledge levels; Contribution path; Tools 5 `contributing`), `docs/decisions.md`, `CHANGELOG.md`.

**Interfaces:**
- Produces:
  - `tiers.tier_violations(portal: PortalContext, pack_dir: Path, evals_dir: Path, *, today: date) -> list[str]`, the conditions decidable from pack contents:
    - `curated`: at least one dataset `reviewed` by `pack_levels` that has a guide, and `evals_dir / f"{pack_dir.name}.json"` whose tasks' `covers` include all four values;
    - `profiled`: at least one claim.
    - Not decidable offline, so not checked: identity verification (live), the smoke test and passing evals, which run in the promotion PR's CI.
  - `tests/test_tiers.py` also checks that every registry entry without a pack is `generic`.
  - Document sections:
    - portal tiers and knowledge levels (the current CONTRIBUTING text, kept);
    - validation and freshness;
    - the path: find or register the portal (`atlas_find_portals`; `registry_overrides.toml`), profile it (`uv run atlas-profile <host>`), review observations, add interpretations with reasons, add `document` evidence where no probe suffices, write a guide per reviewed dataset, write `evals/portals/<pack>.json` with `covers`, run `uv run pytest --run-integration -m integration` and `uv run python evals/run.py --portal <pack> <out>`, and open a PR;
    - the path rule: a pack PR touches only `portals/<id>/`, `evals/portals/<id>.json`, `registry_overrides.toml` and `portals/validation.json`.
  - *(Claude's call: `portals/validation.json` joins the path rule, because Task 4's gate requires an entry for every asserted claim, and a pack PR adds assertions.)*

- [ ] **Step 1: Failing tests.**
  - `tests/test_contributing.py`:
    - `test_served_copy_matches_root`; its failure message says to copy the root file;
    - `test_contributing_names_every_step` (the profiler command, the drift command, `evals/run.py --portal`, the four `covers` values, the path rule);
    - `test_contributing_fits_budget`.
  - `tests/test_tiers.py`:
    - `test_shipped_packs_satisfy_their_tiers`;
    - known positives on synthetic packs: `test_curated_without_guide_violates`, `test_curated_without_eval_coverage_violates`, `test_profiled_without_claims_violates`;
    - `test_registry_only_portals_are_generic`.
  - `test_contributing_topic_defines_tiers_and_levels` still passes.
- [ ] **Step 2: FAIL. Step 3: Implement. Step 4: PASS.**
- [ ] **Step 5:** Prose audit of `CONTRIBUTING-portals.md`. Design: remove "*(Not built yet: milestone 3 carry-over.)*" from Knowledge levels, and update the topic `contributing` line. Decisions rows (the served copy, the tier module, the path rule). CHANGELOG. Full gate.
- [ ] **Step 6: Commit** — `feat: publish the contribution path and test declared tiers`

---

### Task 14: Curation skill and its headless test

**Files:**
- Create: `skills/curate-portal/SKILL.md`, `tests/test_curation_skill.py` (integration, opt-in), `docs/evidence/curation-<date>/`.
- Modify: `CONTRIBUTING-portals.md` and its served copy (one line naming the skill), whatever the run finds, `docs/design.md` (Curation runbook), `docs/decisions.md`, `CHANGELOG.md`.

**Interfaces:**
- Consumes: `atlas-profile`, `tests/test_packs.py`, `tests/test_tiers.py`, `tests/test_release_gate.py`, `tests/test_drift.py`, `evals/run.py --portal`.
- Produces:
  - `SKILL.md`:
    - frontmatter: `name: curate-portal`, and a `description` that triggers on "curate <portal>";
    - `## Rules` (binding, one obligation each):
      - never set a reliability without a reason and probe or document evidence;
      - never declare a tier `tests/test_tiers.py` rejects;
      - touch only the path-rule paths (Task 13);
      - on a gap that needs engine code, stop and log it in `docs/decisions.md`; that is the only other file allowed;
      - never push, and never file an issue;
      - run the four checks before the final commit;
    - `## Steps`, mirroring `CONTRIBUTING-portals.md`;
    - the ending: commit on `curate/<pack>`, then `gh pr create` if `git remote` lists one, else print the PR title and body;
    - `## Context`.
  - `tests/test_curation_skill.py`, `pytestmark = pytest.mark.integration`, skipped unless `ATLAS_RUN_CURATION=1`, so the weekly live and drift workflows never run it. Portal: `ATLAS_CURATION_PORTAL`, default `data.honolulu.gov` *(Claude's call: 72 datasets, a US portal, not Chicago; fall back to `opendata.camden.gov.uk` if Honolulu has no dataset with both a place-like and a time column)*. The test:
    1. runs `git worktree add <tmp>/wt -b curate/test-<date> HEAD`;
    2. runs `claude -p "Curate <portal> by following skills/curate-portal/SKILL.md." --allowedTools "Read,Edit,Write,Glob,Grep,Bash(uv run:*),Bash(git add:*),Bash(git commit:*),Bash(git status:*),Bash(git diff:*),Bash(git log:*),Bash(ls:*),Bash(mkdir:*)" --permission-mode acceptEdits --max-turns 200 --output-format stream-json --verbose` with `cwd=wt`, under a 3-hour timeout;
    3. asserts the transcript ends `subtype: "success"`;
    4. asserts the branch has at least one commit, and `git diff --name-only HEAD~N` lies within the path rule;
    5. in the worktree, asserts `uv run pytest -q tests/test_packs.py tests/test_tiers.py tests/test_release_gate.py` exits 0, `uv run pytest --run-integration -m integration tests/test_drift.py -k <portal id>` exits 0, and `uv run python evals/run.py --portal <pack> <tmp>/evals` leaves every transcript `subtype: "success"`, with the eval file covering all four `covers`;
    6. writes `summary.json` (pack dir, declared tier, claim counts by kind, each check's exit code, eval answers) to `ATLAS_CURATION_EVIDENCE` if set.
  - Eval answers are graded by hand in Step 3, not by the test: grading needs a judgment the test cannot make.
  - *(Claude's call: the produced pack is not merged into this branch. Launch scope is Seattle plus Chicago, and the run is evidence that the skill works. Its summary and diff stat are kept under `docs/evidence/curation-<date>/`.)*

- [ ] **Step 1: Write `SKILL.md` and the test.** Trace the skill by hand against `CONTRIBUTING-portals.md` and each command it names: run every command once with `--help`, or on Seattle where it is read-only. The test is collected and skipped without the env var (`uv run pytest --run-integration -m integration tests/test_curation_skill.py` reports 1 skipped).
- [ ] **Step 2:** Audit `SKILL.md` with `separating-context-from-constraints`. Fix every Material finding and list the findings in `docs/evidence/curation-<date>/audit.md`.
- [ ] **Step 3: [PAID, background] Curation run.**
  - `ATLAS_RUN_CURATION=1 ATLAS_CURATION_EVIDENCE=docs/evidence/curation-$(date +%F) uv run pytest --run-integration -m integration tests/test_curation_skill.py -v -s`
  - Expected: 1 PASS; `summary.json` names the pack directory, a declared tier `tests/test_tiers.py` accepts, every check's exit code 0, and at least one claim with an interpretation, a reason and probe evidence.
  - Grade the portal's eval answers against their `expect` and add the grades to `summary.json`.
- [ ] **Step 4: Fix what it finds.**
  - Each failure, or skill step the agent misread, becomes a fix: in `SKILL.md` or `CONTRIBUTING-portals.md`, or in the engine with a regression test and a decisions row, per design "When the curating agent hits a gap that needs engine code".
  - Re-run Step 3 after the fixes, at most 3 runs in total. If it still fails, stop and report to the controller with the evidence.
- [ ] **Step 5:** Docs.
  - Design Curation runbook: the test's checks, the opt-in variable, the portal choice.
  - Decisions rows: the portal; the run is not merged; the hand grading.
  - CHANGELOG (the skill ships in the repository, not the wheel).
  - Remove the worktree (`git worktree remove`). Full gate.
- [ ] **Step 6: Commit** — `feat: add the curate-portal skill and its headless test`

---

### Task 15: Milestone 3 eval run

**Files:**
- Create: `evals/results/<date>-m3.md`, `evals/results/<date>-m3-runs.json` (excerpts).
- Modify: `docs/design.md` (Evals), `docs/decisions.md`.

**Interfaces:**
- Consumes: Task 12's runner and tasks; the baseline `evals/results/2026-10-18-m2.md`.
- Gate:
  - Retained from milestone 2, which closes the decisions row "Eval gate noise (milestone 2 carry-over)":
    - a task graded below its baseline is re-run twice, and the gate fails only if it grades below baseline in at least 2 of 3 runs;
    - new tasks `30` and `31` must PASS in at least 2 of 3 runs;
    - first-call error-free ≥ 95% across the run (proxy, labeled as such).
  - Expected this milestone: `03-fire-capitol-hill` PASS ("notes most calls are medical"), up from its baseline PARTIAL.

- [ ] **Step 1: [PAID, background] Seattle tasks.** `uv run python evals/run.py --portal seattle evals/results/$(date +%F)-m3/seattle`. Expected: 26 transcripts, each ending `type: "result"`, `subtype: "success"`, `is_error: false`.
- [ ] **Step 2: [PAID, background] Cross-portal tasks.** `uv run python evals/run.py evals/results/$(date +%F)-m3/cross`. Expected: 5 healthy transcripts.
- [ ] **Step 3: [PAID, background] Re-runs.** New tasks 30 and 31 run twice more, into `-m3-run2/` and `-m3-run3/`, each with `--portal seattle 30-stale-claim` or the cross-portal file with `31-knowledge-gap-offer`. Every below-baseline task runs twice more into `-m3-rerun1/` and `-m3-rerun2/`.
- [ ] **Step 4: Check the restriction.** First check the instrument: the restriction check must surface the known positive, as in milestone 2. Then every `system/init` lists only the five `mcp__opendata-atlas__atlas_*` tools, and no `tool_use` names any other tool.
- [ ] **Step 5: Grade and record.** Grade on substance against `expect`. Record `evals/results/<date>-m3.md`: setup, run health, cost, a table against baseline, totals, the gate, and re-runs. Add excerpts for every run used in the 2-of-3 rule, with emails and phones redacted. Add the design Evals line. If the gate fails, stop and report; do not edit an `expect` without a controller ruling.
- [ ] **Step 6: Commit** — `test: record the milestone 3 eval run`

---

### Task 16: Standards review and docs reconciliation

**Files:**
- Create: `docs/reviews/<date>-m3-standards.md`.
- Modify: whatever the findings require; `docs/superpowers/plans/2026-10-18-m3-carryover.md`, `docs/design.md`, `docs/decisions.md`, `CHANGELOG.md`, `AGENTS.md` (the drift command, the curation-skill opt-in).

- [ ] **Step 1:** Run the `agent-friendly-mcp` **full walk** (the surface changed in Tasks 3, 5, 7, 9 and 10): `references/contract-checklist.md` §1–§9, per `references/review-workflow.md`. Give every section a finding, `OK` with evidence, or `not-applicable` with a one-line reason.
- [ ] **Step 2:** Run a `separating-context-from-constraints` audit of the instructions, capability summary, tool and resource descriptions, hint and notice messages, `CONTRIBUTING-portals.md`, `SKILL.md`, `AGENTS.md` and `docs/design.md`.
- [ ] **Step 3:** Fix every Material finding; a behavior finding gets a failing-first regression test. Fix or list the Minor findings. Run the full gate and the `tools/list` byte check.
- [ ] **Step 4: Reconcile.**
  - `grep -n "not built yet" docs/design.md` returns nothing. Confirm first that the same grep finds the marker on `docs/design` HEAD.
  - The design's "Milestone 2:" freshness bullet and its `validation: "unchecked"` statements are gone or restated for milestone 3.
  - `2026-10-18-m3-carryover.md` gets a "Reconciled" header like the milestone 2 one. Each item ends **Done** (task and commit) or **Deferred** (decisions row).
  - Decisions rows for each out-of-scope item:
    - the token probe;
    - F7 icon by URL, the README status word and the release-cut test (milestone 5);
    - F8, F9 and F10 (milestone 5 surface pass);
    - `guides_by_id` (left);
    - fixture identities (the maintainer's decision);
    - Chicago (milestone 4).
  - Read the CHANGELOG `## [Unreleased]` end to end: one line per user-visible change in this milestone.
- [ ] **Step 5:** Record the reviews; add a decisions row. **Commit** — `docs: record milestone 3 standards review and reconcile carry-over`

---

## Done criteria

- The gate is clean on the branch.
- `uv run pytest --run-integration -m integration` passes (the curation test skips without its opt-in), and `validation.json` holds 8 `passed` Seattle entries.
- `tests/test_release_gate.py` passes.
- Every snapshot change is named in Tasks 3, 5, 7 or 9 and in `CHANGELOG.md`; `tools/list` ≤ 24,576 bytes; `instructions` ≤ 1,800 characters.
- Seattle parity holds per Global Constraints, shown by Task 3's change list and Task 15's gate.
- One profiler run (Task 11) and one passing curation run (Task 14) are recorded under `docs/evidence/`.
- Task 16's reviews are recorded, with no open Material finding. Every carry-over item is Done or has a decisions row.

**Next:** milestone 4, Chicago through the front door with `skills/curate-portal/SKILL.md`.
