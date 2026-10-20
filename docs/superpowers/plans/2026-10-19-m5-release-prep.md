# opendata-atlas Milestone 5: Release, Built to Release-Ready — Implementation Plan

> **Status: complete.** Historical plan, kept for provenance; do not execute it. Current design: [docs/design.md](../../design.md).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Leave `feat/release-prep` cut-ready for 0.1.0 without publishing anything. That means:
- the inherited fixture identities are scrubbed and guarded;
- the deferred surface items are decided by measured bytes;
- the describe region-values timeout is fixed within the 30 s deadline;
- the release cut is rehearsed on a temp copy;
- the wheel, sdist and bundle are built, inspected and smoke-tested locally;
- the maintainer can try the server from a checkout, a wheel or a bundle;
- a release checklist lists what only the maintainer can do.

**Architecture:** Eight tasks.
- **Task 1** scrubs the fixtures and adds a guard.
- **Tasks 2–4** make the surface and engine changes. Only Task 2 changes `tests/snapshots/tools_list.json`.
- **Tasks 5–6** make the release mechanics reproducible locally: the cut rehearsal, the artifact checks, and the try-it-locally paths.
- **Task 7** writes the port comparison and the maintainer docs.
- **Task 8** runs the standards review and reconciles the deferred decisions rows.

**Tech Stack:** Python ≥3.13, uv and `uv_build`, FastMCP 4.1 on MCP SDK v2, pytest with the record/replay `tests/http_fixtures.py`, the `mcpb` CLI 2.1.2 (installed at `/opt/homebrew/bin/mcpb`), awk.

**Spec:** `docs/design.md`: Milestones item 5 ("Release. Bundle, PyPI, docs. All `port` issues ported or closed."), Constraints (line 50: every `port`-labeled fix ported or closed with a reason), Time, Resources, Byte budgets.
- Deferred rows in `docs/decisions.md`:
  - "Icon by URL, README status word, release-cut test (milestone 5)";
  - "Lifecycle `_meta`, resource `size`, `$schema` (milestone 5 surface pass)";
  - "Region values on describe `full` when the grouping times out";
  - "Milestone 5 surface items found in milestone 4";
  - "Release-cut test (milestone 2 carry-over)";
  - "Uncapped Codex eval host; the cap's overshoot is unprobed";
  - "Inherited fixture identities (milestone 4 carry-over)";
  - "Name timing and hosting".
- Release procedure: `docs/releasing.md`, `.github/workflows/release.yml` and `build.yml`.
- Scope rulings and the maintainer's answers bind (the controller's milestone 5 scope file, items 1–9).

**Scope notes:**
- **Build everything needed to publish, but publish nothing (maintainer).** Forbidden: creating a remote, pushing, tagging, running the release workflow, uploading anywhere, rewriting history. The cut itself (renaming `## [Unreleased]`) is **not** made: it is rehearsed on a temp copy.
- **Out of scope**, so no task plans these:
  - paid runs (evals, curation);
  - re-curating any portal, or editing a pack (front door);
  - editing `/Users/bdc/projects/seattle-open-data` (read only; never switch its branches);
  - the profiler's `label_candidate` gap (item (c) of row "Milestone 5 surface items found in milestone 4"). Task 8 keeps it Deferred.
- **Base:** `docs/design` at `da2150d`, plus the commit that adds this plan. Work on `feat/release-prep` in the worktree `/Users/bdc/projects/opendata-atlas-m5`, called `$WT` below. Other agents may use the main checkout: never switch branches there.
- **[LIVE]** marks a step that calls a public Socrata portal. These calls are free and need the network. No step is paid.

### Measured before planning (2026-10-19, at `da2150d`)

| Measure | Value | Limit |
| --- | --- | --- |
| `tools/list` framed, modern era (2026-07-28) | 24,464 B: tools 23,727, plus the 666 B `_meta` serverInfo stamp | 24,576 (112 B headroom) |
| `tools/list` framed, legacy era (2025-11-25; no stamp) | 23,784 B | 24,576 (792 B headroom) |
| `INSTRUCTIONS` | 1,797 chars | 1,800 |
| serverInfo stamp, per modern result | 666 B, of which `icons` 549 B (data URI 494 chars, from a 351 B SVG) | — |
| Fixture emails (`tests/fixtures/`; known positive: a synthetic `jane.doe@seattle.gov` line counts 1) | 76 occurrences, 7 distinct, 21 files, all under `http/` | — |
| Fixture names (JSON walk of `tests/fixtures/`; known positive: a synthetic owner counts 2) | `displayName` 124, `screenName` 102, `display_name` 20 (total 246), and `Contact Name` 1 | — |

The modern era binds, because its `tools/list` carries the stamp. Here is what each candidate change would add to modern `tools/list`. Each figure was measured by injecting the change into the live listing:

| Candidate | Bytes |
| --- | --- |
| Minified icon (302 B SVG, data URI 430 chars) | −64 |
| F8 lifecycle `_meta` (`io.github.briandconnelly/lifecycle`, `{"stability":"preview"}`) on 5 tools | +195 |
| F10 `$schema` on 5 input schemas | +285 |
| F10 `$schema` on input and output schemas | +570 |
| `source.now_local_weekday` (5 output schemas) | +190 |
| `source.now_weekday` | +160 |
| `source.weekday` | +140 |

**Decisions from these figures** *(Claude's call; each gets its decisions row in the task named)*:
- **Minify the icon and keep it base64** (Task 2). A URL is unavailable, since there is no public repo. Base64 decodes in every host. A percent-encoded URI would save 13 B more (419 vs 432), at a portability risk.
- **Add `source.now_weekday`** (Task 2). After the icon saving there are 176 B of headroom: `now_local_weekday` (+190) does not fit, and `now_weekday` (+160) does. The result is modern 24,560 and legacy 23,944, leaving **16 B of headroom**.
- **F9 resource `size`: do it** (Task 3). `resources/list` is outside the `tools/list` budget.
- **F8 and F10: defer, with rows** (Task 3). Neither fits (195 > 176; 285 > 176).

## Global Constraints

- Gate for every task: `uv run pytest -q`, `uv run ruff check`, `uv run ruff format --check`, `uv run ty check`, `uv run prek run --all-files`. prek pins ruff v0.17.0 while `uv run ruff` is 0.17.1, and the gate keeps both linters (carry-over).
- Commits: Conventional Commits, each ending with a blank line, then `🤖 Generated with Claude Code` and `Claude-Session: https://claude.ai/code/session_01CH7uTSKtTjy4NoHCYKFHyx` on the next line. Commit only on `feat/release-prep`. Never push, tag, amend, rebase, force, or create a remote.
- **Byte limits:** framed `tools/list` ≤ 24,576 on both eras (`tests/test_contract.py`); `INSTRUCTIONS` ≤ 1,800 characters (`tests/test_reference_topics.py`); every result within its measure (`tests/test_budget.py`).
- **Snapshot:** `tests/snapshots/tools_list.json` changes only in Task 2 (`now_weekday` in the five output schemas' `source`). In any other task, a snapshot diff is a defect. Every surface change gets a CHANGELOG line under `## [Unreleased]`, which stays uncut.
- **Seattle and Chicago parity:** levels, warnings, values and repairs stay unchanged, except for the named changes: `source.now_weekday`, the minified icon, resource `size`, and Task 4's extra `stats_status: "ok"` fields. `pack_levels(SEATTLE_CONTEXT, today=date(2026, 10, 18))` stays `{'33kz-ixgy': 'reviewed', '65db-xm6k': 'none', '76t5-zqzr': 'none', 'kzjm-xkqj': 'reviewed', 'ppi5-g2bj': 'none', 'tazs-3rd5': 'none'}`. No file under `src/opendata_atlas/portals/<pack>/` changes.
- **Personal data:** none in commits. The email scan is `grep -rnE '[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z.]{2,}' PATHS`. Once Task 1 lands, the fixtures no longer hold a known positive, so check the scan first on `/private/tmp/claude-501/-Users-bdc-projects-seattle-open-data/eaa96e21-62d3-4c8a-95e9-0767b5ab2bf4/scratchpad/m5/kp-email.txt` (create it holding `jane.doe@seattle.gov`; it must match). Print counts, never values.
- **Facts:** never report an upstream fact you did not probe. `validation.json`: after any `--run-integration` run, `git restore src/opendata_atlas/portals/validation.json` (AGENTS.md).
- **Design changes:** update `docs/design.md` and add a `docs/decisions.md` row in the task that makes the change.
- **Prose standard:** audit every agent-consumed prose surface a task changes with `separating-context-from-constraints`, and list the findings in the task report.

## Review Focus

1. **Weekday across UTC midnight.** At `2026-10-18T03:00Z`, Seattle's wall clock is Saturday 20:00. Expected: `now_weekday == "Saturday"`, the local day, not the UTC day. Pinned by `test_weekday_is_the_portal_local_day` (Task 2).
2. **No single zone.** A multi-zone, unknown-zone or portal-independent result. Expected: `now_weekday` is absent wherever `now_local` is absent, never `null` or a guessed day. Pinned by `test_weekday_absent_without_now_local` (Task 2).
3. **A fixture recorded after the scrub.** Expected: `RECORD_FIXTURES=1` output is scrubbed on save, so the guard never fails on a contributor's fresh recording. Pinned by `test_recorder_save_scrubs` (Task 1).
4. **Slow metadata eating the describe deadline.** Expected: the place phase shrinks to what is left, never below 0. Describe returns degraded fields rather than failing the whole call with `query_timeout`. Pinned by `test_place_phase_budget_never_negative` (Task 4).
5. **Resource `size` under an allowlist.** With `OPENDATA_ATLAS_PORTALS` set, the `portals` index is shorter. Expected: `size` equals the UTF-8 byte length of what `resources/read` returns under the same environment. Pinned by `test_resource_size_matches_read_under_allowlist` (Task 3).

---

## File Structure

```
scripts/scrub_fixtures.py                 # scrub(node) and the CLI that rewrites fixtures          (Task 1)
tests/http_fixtures.py                    # Recorder.save scrubs                                   (Task 1)
tests/test_fixture_identities.py          # guard, known positive first                            (Task 1)
tests/fixtures/http/*.json                # scrubbed                                               (Task 1)
src/opendata_atlas/assets/icon.svg        # minified                                               (Task 2)
src/opendata_atlas/core/{context,models,reference}.py  # now_weekday and its served wording         (Task 2)
src/opendata_atlas/mcp/resources.py       # SizedResource                                          (Task 3)
src/opendata_atlas/core/describe.py       # place phase takes the deadline's remainder             (Task 4)
tests/test_describe_phases.py, tests/fixtures/http/describe_chicago_crimes_full.json         (Task 4)
scripts/rehearse_release.py, tests/test_versioning.py                                         (Task 5)
scripts/smoke_test.py, scripts/build_bundle.py, tests/test_manifest.py, tests/test_readme.py  (Task 6)
README.md, docs/release-checklist.md                                                          (Tasks 5–7)
docs/reviews/2026-10-19-m5-standards.md                                                       (Task 8)
docs/design.md, docs/decisions.md, CHANGELOG.md                                               (every task as needed)
```

---

### Task 1: Scrub the inherited fixture identities and guard them

**Files:**
- Create: `scripts/scrub_fixtures.py`, `tests/test_fixture_identities.py`.
- Modify: `tests/http_fixtures.py` (`Recorder.save`), every `tests/fixtures/http/*.json` that holds an identity, `docs/decisions.md` (row "Inherited fixture identities"), `CHANGELOG.md` (one line under Changed: test-only, no runtime change).

**Interfaces:**
- Produces:
  - `IDENTITY_KEYS: frozenset[str] = {"displayName", "screenName", "display_name", "Contact Name"}`;
  - `PLACEHOLDER_NAME = "Fixture Person"`;
  - `PLACEHOLDER_EMAIL = "redacted-email"` (no `@`, so the email guard stays absolute);
  - `EMAIL: re.Pattern[str]`, the Global Constraints scan pattern;
  - `scrub(node: Any) -> Any`, which returns a scrubbed copy and recurses into dicts, lists, and strings that parse as JSON;
  - `find_identities(node: Any) -> Counter[str]`, counts per kind (`email`, or the identity key), with no values;
  - CLI `uv run python scripts/scrub_fixtures.py [--check] [PATHS...]` (default `tests/fixtures/`). It rewrites in place, or with `--check` exits 1 when anything is left.
- Task 4 relies on `Recorder.save` calling `scrub`.

- [ ] **Step 1: Worktree.** `git -C /Users/bdc/projects/opendata-atlas worktree add /Users/bdc/projects/opendata-atlas-m5 -b feat/release-prep docs/design`, then `cd /Users/bdc/projects/opendata-atlas-m5 && uv sync && uv run pytest -q`. Expected: 1185 passed, 108 skipped.
- [ ] **Step 2: Failing tests** in `tests/test_fixture_identities.py`. The first two are the guard's known positives:

```python
def test_guard_catches_a_synthetic_identity():
    node = {
        "owner": {"displayName": "Jane Doe", "screenName": "jdoe"},
        "body": json.dumps({"Contact Email": "jane.doe@seattle.gov"}),
    }
    assert find_identities(node) == Counter({"displayName": 1, "screenName": 1, "email": 1})


def test_scrub_replaces_names_and_emails_everywhere():
    out = scrub({"members": [{"display_name": "A B"}], "description": "mail a@b.gov now"})
    assert out == {
        "members": [{"display_name": "Fixture Person"}],
        "description": "mail redacted-email now",
    }
    assert find_identities(out) == Counter()


def test_no_fixture_holds_an_identity():
    found = {
        p.name: find_identities(json.loads(p.read_text()))
        for p in Path("tests/fixtures").rglob("*.json")
    }
    assert {k: v for k, v in found.items() if v} == {}


async def test_recorder_save_scrubs(tmp_path, monkeypatch):
    # Recorder with FIXTURES pointed at tmp_path, one entry whose body has an owner and an email
    ...
    assert find_identities(json.loads(path.read_text())) == Counter()
```

  A `Fixture Person` value is not counted: `find_identities` skips a value equal to `PLACEHOLDER_NAME`.
- [ ] **Step 3: Run them.** `uv run pytest tests/test_fixture_identities.py -v`. Expected: the two known positives and the scrub test PASS once `scrub_fixtures.py` exists. `test_no_fixture_holds_an_identity` FAILS with 21 files. `test_recorder_save_scrubs` FAILS.
- [ ] **Step 4: Implement** `scripts/scrub_fixtures.py`. Load it from tests with `importlib.util.spec_from_file_location`, as `tests/test_manifest.py` loads `build_bundle.py`. Then make `Recorder.save` write `scrub(self.entries)`. A string that parses as JSON is scrubbed inside and re-serialized compactly only when a value changed. The CLI writes each file in `Recorder.save`'s format (`json.dumps(…, indent=1, sort_keys=True) + "\n"`), so a file without identities is byte-identical. Run the CLI over `tests/fixtures/`.
- [ ] **Step 5: Run the replay suite and the gate.** Expected: every test passes, unchanged in number plus the new ones. The scan (known positive first) counts 0 emails in `tests/fixtures/`. `scripts/scrub_fixtures.py --check` exits 0. The names walk counts 0 non-placeholder values. If a test asserted on an identity value, change the assertion to the placeholder, not the fixture back, and name the test in the report.
- [ ] **Step 6: Docs.** Mark the decisions row "Inherited fixture identities" **Done**: the counts before (76/7/21; 246 names plus 1 `Contact Name`) and after (0), the guard's name, and "earlier commits still contain them; the public push needs a fresh history or a deliberate decision (`docs/release-checklist.md`, Task 7)". Note the guard's limit: free-text row values, such as business names in permit rows, are not person fields, and the guard does not read them.
- [ ] **Step 7: Commit** `test: scrub inherited fixture identities and guard against new ones`.

---

### Task 2: Minify the icon and add `source.now_weekday`

**Files:**
- Modify: `src/opendata_atlas/assets/icon.svg`, `src/opendata_atlas/core/context.py`, `src/opendata_atlas/core/models.py:49-54` (`Source`), `src/opendata_atlas/core/reference.py:149` (capability summary `## Semantics`, Time line), `tests/snapshots/tools_list.json` (regenerated).
- Test: `tests/test_portal_model.py`, `tests/test_legacy_protocol.py`, `tests/test_contract.py`.
- Modify: `docs/design.md` (Time; Goals' parity list of permitted differences, line 25; Byte budgets lines 460 and 465 with the new figures), `docs/decisions.md` (two rows), `CHANGELOG.md`.

**Interfaces:**
- Produces:
  - `WEEKDAYS: tuple[str, ...] = ("Monday", …, "Sunday")` in `core/context.py`. It is locale-independent: never `strftime("%A")`.
  - `weekday_of(now_local: str) -> str`, which returns `WEEKDAYS[datetime.fromisoformat(now_local).weekday()]`.
  - `Source.now_weekday: str | None = None`, declared right after `now_local`, set by `make_source` exactly when `now_local` is set.
  - `make_source(portal, *, retrieved: bool = False, now: datetime | None = None) -> Source`: `now` defaults to `datetime.now(UTC)`, so tests can pin the clock.
- `local_now`'s signature is unchanged.

- [ ] **Step 1: Failing tests** in `tests/test_portal_model.py`, with `NOW = 2026-10-17T19:00Z`:
  - `test_seattle_source_carries_the_local_weekday`: `make_source(load_portal(SEATTLE), now=NOW)` gives `now_weekday == "Saturday"`.
  - `test_weekday_is_the_portal_local_day`: `2026-10-18T03:00Z` gives `"Saturday"` for Seattle.
  - `test_weekday_absent_without_now_local`: the multi-zone, unknown and `make_source(None)` sources have `now_weekday is None`. `test_portal_independent_source_has_no_portal`'s key set stays `{"request_id"}`.
- [ ] **Step 2: Failing icon test** in `tests/test_legacy_protocol.py`. `test_icon_is_minified`: the stamp's `icons[0].src` is at most 432 characters. The SVG parses with `xml.etree.ElementTree` and keeps its four shapes (`rect`, two `path`, `circle`) with their `d`, `fill`, `rx`, `cx/cy/r` and stroke values unchanged. The root keeps `viewBox="0 0 64 64"`.
- [ ] **Step 3: Run them.** Expected: the weekday tests FAIL (`Source` has no `now_weekday`), and the icon test FAILS at 494 chars.
- [ ] **Step 4: Implement.**
  - The SVG becomes one line, 302 bytes before its newline, with these changes: whitespace between tags removed, `width`/`height` dropped (`viewBox` stays), and `fill="none"` dropped from the stroke-only path, whose subpaths enclose no area. Exact text: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="12" fill="#1f4e79"/><path d="M10 18 22 14 42 20 54 16V46L42 50 22 44 10 48Z" fill="#f2efe6"/><path d="M22 14V44M42 20V50" stroke="#1f4e79" stroke-width="2"/><circle cx="32" cy="30" r="5" fill="#d9534f"/></svg>` plus one trailing newline, which prek's `end-of-file-fixer` requires. The newline leaves the base64 at 404 characters, so the URI is still 430.
  - Add the field and `weekday_of`.
  - The Time line gains, after the `now_local` sentence: "`source.now_weekday` is that time's day of the week (`Monday` … `Sunday`), absent with `now_local`; take weekdays from it, never from your own date arithmetic." `INSTRUCTIONS` is unchanged: it has 3 characters of headroom.
- [ ] **Step 5: Regenerate and measure.** Run `UPDATE_SNAPSHOTS=1 uv run pytest tests/test_contract.py`. `git diff --stat tests/snapshots/tools_list.json` must show only five `now_weekday` insertions. Then `uv run pytest tests/test_contract.py tests/test_budget.py tests/test_legacy_protocol.py -v -s` and the full gate.
  - Expected: framed modern `tools/list` 24,560 and legacy 23,944, both ≤ 24,576.
  - `test_envelope_reserve_covers_modern_overhead` still passes (overhead > 600, ≤ 1,024).
  - Seattle's recorded results differ only by `now_weekday`, and the replay tests pass. Fix any test that pins a whole `source` dict by adding the field.
  - Record the printed figures for Step 6.
- [ ] **Step 6: Docs.**
  - Decisions row "Weekday beside `now_local` (milestone 5)": before (3 of 6 task-03 answers mislabeled weekdays); after (`now_weekday`); why that name (`now_local_weekday` +190 B does not fit in 176 B); headroom after (16 B). *(Claude's call)*.
  - Decisions row "Icon minified, not by URL (milestone 5)": the four sizes above. The stamp goes from 666 to 602 B.
  - Design: Time gains the field; parity's permitted differences gain `now_weekday`; Byte budgets gets the new `tools/list` figure and stamp size.
  - CHANGELOG under Added: `source.now_weekday`, with "the tool surface changes: every output schema's `source` gains `now_weekday`". Under Changed: the icon is minified, and each modern result is 64 bytes smaller.
- [ ] **Step 7: Commit** `feat: add source.now_weekday and minify the served icon`.

---

### Task 3: Resource `size`; lifecycle `_meta` and `$schema` decided by bytes

**Files:**
- Modify: `src/opendata_atlas/mcp/resources.py` (`register_resources`).
- Test: `tests/test_reference_topics.py`.
- Modify: `docs/design.md` (Resources: a line on `size`; `atlas_get_reference`'s "resource `size` is milestone 5" note), `docs/decisions.md` (rows "Lifecycle `_meta`, resource `size`, `$schema`" and a new F8/F10 row), `CHANGELOG.md`.

**Interfaces:**
- Produces `class SizedResource(FunctionResource)`. It overrides `to_mcp_resource(self, **overrides) -> mcp.types.Resource` to return `super().to_mcp_resource(**overrides).model_copy(update={"size": len(self.fn().encode("utf-8"))})`. Register the six static resources (`capabilities`, `contributing`, and the `reference`, `portals`, `soql`, `errors` indexes) with `mcp.add_resource(SizedResource.from_function(...))`, using the current URIs, names, titles, descriptions and MIME types. FastMCP 4.1's `mcp.resource()` takes no `size`, and its `to_mcp_resource` drops it. Templates are unchanged.

- [ ] **Step 1: Failing tests.**
  - `test_static_resources_declare_their_byte_size`: for each of the six URIs in `resources/list`, `size == len(read_text.encode())`, where `read_text` comes from `resources/read`.
  - `test_resource_size_matches_read_under_allowlist`: run the same check for `opendata-atlas://portals` with `OPENDATA_ATLAS_PORTALS=seattle`. Clear the registry cache as `_clear_registry_cache` does. The size must be smaller than without the allowlist (known positive that the environment changes it).
  - `test_size_counts_utf8_bytes`: monkeypatch `CAPABILITIES` to `"é"`; `size == 2`.
- [ ] **Step 2: Run them.** Expected: FAIL, because `size` is absent.
- [ ] **Step 3: Implement** `SizedResource` and the registration. The `size` is computed on each `resources/list`, so it follows the environment.
- [ ] **Step 4: Run them and the gate.** Expected: PASS. `tests/snapshots/tools_list.json` is unchanged. `test_every_resource_has_a_tool_fallback` passes.
- [ ] **Step 5: Measure F8 and F10 on the branch.** Rerun the injection measure from "Measured before planning", now on the Task 2 head, and record each delta. Script: `/private/tmp/claude-501/-Users-bdc-projects-seattle-open-data/eaa96e21-62d3-4c8a-95e9-0767b5ab2bf4/scratchpad/m5/variants.py`, run with `PYTHONPATH=.` from `$WT`. Expected: about +195 B and +285 B against 16 B of headroom. Neither fits.
- [ ] **Step 6: Docs.**
  - The F8/F9/F10 row: F9 **Done**. F8 and F10 **Deferred**, citing `[9.tier-metadata]` and `[3.dialect]`: "do not fit (F8 +195 B, F10 +285 B for inputs alone, with 16 B of headroom after `now_weekday`). The preview tier stays stated in the capability summary (`Stability: preview`). Revisit when a surface change frees bytes, or at 1.0, when the tier changes."
  - CHANGELOG under Added: "static resources declare `size` (UTF-8 bytes of the body)".
- [ ] **Step 7: Commit** `feat: declare size on static resources`.

---

### Task 4: Give describe's place-stats phase the rest of the deadline

**Files:**
- Modify: `src/opendata_atlas/core/describe.py` (`describe`, `_describe` around line 194, new `_place_phase_budget`), `tests/http_fixtures.py` (`Replay`: a `{"delay": seconds}` override action).
- Create: `tests/test_describe_phases.py`, `tests/fixtures/http/describe_chicago_crimes_full.json` (recorded [LIVE]).
- Modify: `docs/design.md` (describe: one line on the phase budget), `docs/decisions.md` (row "Region values on describe `full` when the grouping times out"), `CHANGELOG.md`.

**Interfaces:**
- Consumes: Task 1's scrubbing `Recorder.save`.
- Produces:
  - `_RENDER_MARGIN_SECONDS = 1.0`;
  - `_place_phase_budget(deadline_at: float, now: float) -> float`, which returns `max(0.0, deadline_at - now - _LABEL_FETCH_TIMEOUT - _RENDER_MARGIN_SECONDS)`.
  - `describe` computes `deadline_at = anyio.current_time() + DESCRIBE_DEADLINE_SECONDS` and passes it to `_describe(…, deadline_at: float)`. Phase 2 runs under `anyio.move_on_after(_place_phase_budget(deadline_at, anyio.current_time()))` instead of `DESCRIBE_AGGREGATE_TIMEOUT_SECONDS`. Phase 1, `_PLACE_CONCURRENCY`, the label fetch and the 30 s whole-call deadline are unchanged, so the tool description ("fails with query_timeout after 30 s") stays true.
  - `Replay` override action `{"delay": float}`: sleep (`anyio.sleep`), then serve the recorded entry.

- [ ] **Step 1: [LIVE] Record the fixture.** Add `test_chicago_crimes_full_describe_has_every_place_field`, marked `@pytest.mark.soda_fixture("describe_chicago_crimes_full")`. It calls `describe(...)` on `data.cityofchicago.org` `ijzp-q8t2` with `detail="full"`, `sample_rows=0`. When `RECORDING`, it monkeypatches `DESCRIBE_DEADLINE_SECONDS = 120` and `DESCRIBE_AGGREGATE_TIMEOUT_SECONDS = 60`, so every grouping completes and is recorded. It asserts `len(place_fields) > 4` (more groupings than slots: the known positive for Step 3) and every `stats_status == "ok"`. Run `RECORD_FIXTURES=1 uv run pytest tests/test_describe_phases.py::test_chicago_crimes_full_describe_has_every_place_field`. Expected: PASS. The new file passes `scripts/scrub_fixtures.py --check`. Then `git restore src/opendata_atlas/portals/validation.json` if it changed.
- [ ] **Step 2: Failing tests.**
  - `test_slow_groupings_finish_within_the_deadline`: replay with `overrides={"$group": {"delay": 0.6}}`, and monkeypatch `DESCRIBE_DEADLINE_SECONDS=4.0`, `DESCRIBE_AGGREGATE_TIMEOUT_SECONDS=1.0`, `_LABEL_FETCH_TIMEOUT=0.5`, `_RENDER_MARGIN_SECONDS=0.25`. Expected result: every place field `stats_status == "ok"`. Under the old fixed cap, at 4 slots, the second and third rounds end past 1.0 s.
  - `test_place_phase_budget_never_negative`: `_place_phase_budget(10.0, 9.9) == 0.0`, and `_place_phase_budget(30.0, 2.0) == 22.0` with the default constants.
  - `test_slow_metadata_degrades_fields_not_the_call`: use a fake client whose `view` sleeps 2.5 s and whose groupings sleep 0.6 s, under the same scaled constants. The call returns (no `AtlasError`), and at least one field reads `stats_status == "timeout"`.
- [ ] **Step 3: Run them.** Expected: the first FAILS, with fields at `timeout`. The budget test FAILS (no function).
- [ ] **Step 4: Implement** the budget and the `delay` action.
- [ ] **Step 5: Run them, the describe suites and the gate.** Run `uv run pytest tests/test_describe_phases.py tests/test_review_m2.py tests/test_search_describe.py tests/test_freshness.py -v`, then the gate. Expected: PASS, with `test_deadline_does_not_strand_queued_coroutines` included. Seattle's recorded describes are unchanged.
- [ ] **Step 6: [LIVE] Verdict on the real dataset.** Run one in-process `atlas_describe_dataset {"portal": "chicago", "dataset_id": "ijzp-q8t2", "detail": "full"}`. Record the count of place fields at `ok` against the total, and whether `:@computed_region` ward and police-district fields carry `values` with labels. Save the counts (no values) to `docs/evidence/describe-phases-2026-10-19/chicago-crimes.json`. Expected: more than 6 of 11 fields `ok`. The row closes **Done** if every field is `ok`. Otherwise it closes **Done in part**, keeping the remaining fields' timing as the reason; widening further would break the 30 s deadline. No paid eval is run: the row says a later paid eval would confirm the effect on answers.
- [ ] **Step 7: Docs.** Update the decisions row, and add a design line: "the place-stats phase runs until the deadline less the label fetch (5 s) and a 1 s margin". CHANGELOG under Changed: "`detail: "full"` place statistics may use the time the earlier phase left. On Chicago Crimes, N of 11 place fields now report values (was 6)."
- [ ] **Step 8: Commit** `fix: let describe's place statistics use the rest of the deadline`.

---

### Task 5: Rehearse the release cut; choose the status word

**Files:**
- Create: `scripts/rehearse_release.py`.
- Modify: `tests/test_versioning.py`, `README.md:9` (status line), `docs/releasing.md` (the cut is the script's `--apply`), `docs/decisions.md` (rows "Release-cut test (milestone 2 carry-over)" and "Icon by URL, README status word, release-cut test"), `CHANGELOG.md`.

**Interfaces:**
- Produces, in `scripts/rehearse_release.py`:
  - `cut_changelog(text: str, version: str, day: str) -> str`: renames the first `## [Unreleased]` to `## [<version>] - <day>`. Raises `ValueError` when there is none. Adds no new Unreleased heading.
  - `version_check_program(workflow: str) -> str`: the `<<'PY' … PY` heredoc of the "pyproject, manifest, CHANGELOG (and the tag, if any) agree" step, verbatim and dedented.
  - `notes_awk_program(workflow: str) -> str`: the step's awk program, verbatim (moved from `tests/test_versioning.py::_release_notes_awk`).
  - `@dataclass Rehearsal(ok: bool, check_output: str, notes: str)`.
  - `rehearse(root: Path, version: str, day: str, work: Path) -> Rehearsal`: copies `pyproject.toml`, `manifest.json` and `CHANGELOG.md` to `work`, cuts the copy, runs the check program as `[sys.executable, "-", "v<version>"]` with the program on stdin, cwd `work`. It must not be `uv run`, which would try to sync the copied `pyproject.toml`, then runs the awk with `v=<version>`. `ok` is true when the check exits 0 and the notes are non-empty.
  - CLI: `uv run python scripts/rehearse_release.py [--version V] [--date YYYY-MM-DD] [--apply]`. The version defaults to pyproject's, the date to today. Without `--apply`, it prints `OK: …` and the notes' line count, and exits 0, or 1 on failure. `--apply` rehearses first, then writes the cut to `CHANGELOG.md`. That is the eventual one-liner; **this plan never runs `--apply` on the repo**.

- [ ] **Step 1: Failing tests** in `tests/test_versioning.py`:
  - Parametrize the CHANGELOG tests over `STATES = {"uncut": CHANGELOG, "cut": cut_changelog(CHANGELOG, "0.1.0", "2026-10-19")}`. `test_changelog_states_the_fork` reads `release_section(text)`: the first `## [X.Y.Z]` section when one exists, else `## [Unreleased]`. `test_release_notes_stop_before_parent_history` cuts only an uncut text.
  - `test_uncut_changelog_fails_the_workflow_check` (known positive; releasing.md Context): the extracted check program, run on an uncut copy, exits 1 and prints `latest CHANGELOG version None`.
  - `test_rehearsal_passes_on_a_cut_copy`: `rehearse(ROOT, "0.1.0", "2026-10-19", tmp_path).ok`. The notes contain "forked from seattle-open-data 0.2.0 at 26c6628" and not "seattle-open-data history". The repo's `CHANGELOG.md` is byte-identical before and after.
  - `test_rehearsal_rejects_a_mismatched_tag`: `rehearse(…, "0.1.1", …)` is not ok.
  - `test_readme_status_matches_capability_tier`: README's `**Status: <word>.**` equals the word after `Stability:` in `CAPABILITIES`.
- [ ] **Step 2: Run them.** Expected: FAIL. The script is missing, and README says `alpha` against `preview`.
- [ ] **Step 3: Implement** the script. Change README line 9 to `**Status: preview.**`, keeping its sentence. The pyproject classifier stays `Development Status :: 3 - Alpha`: trove has no "preview", and 3 is the pre-1.0 class.
- [ ] **Step 4: Run them and the gate.** Then run `uv run python scripts/rehearse_release.py --date 2026-10-19`. Expected: `OK: pyproject, manifest.json, latest CHANGELOG, git tag all agree on 0.1.0`, and `git status --short CHANGELOG.md` is empty.
- [ ] **Step 5: Reproduce the rest of `verify` locally.** Run `uv run python scripts/gen_manifest.py --check` and `uv run pytest tests/test_release_gate.py -v`. Expected: both exit 0. The drift run that refreshes `validation.json` is a release-time step (checklist), not run here.
- [ ] **Step 6: Docs.**
  - `docs/releasing.md` Rules: the cut is `uv run python scripts/rehearse_release.py --apply --date <YYYY-MM-DD>`, then commit.
  - Mark the decisions rows "Release-cut test" **Done** (the tests pass on both states), and mark the status-word part of the icon row **Done**: "preview, the capability summary's tier".
  - CHANGELOG under Changed: the README status reads preview.
- [ ] **Step 7: Commit** `feat: rehearse the release cut on a temp copy`.

---

### Task 6: Try it locally; build and inspect the artifacts

**Files:**
- Modify: `scripts/smoke_test.py` (modes `--checkout`, `--uvx WHEEL`; option `--live`), `scripts/build_bundle.py` (`REQUIRED` gains `portals/data.cityofchicago.org/portal.toml`), `tests/test_manifest.py`, `README.md` (new `## Try it locally` after Install).
- Create: `tests/test_readme.py`.

**Interfaces:**
- Produces, in `scripts/smoke_test.py`:
  - `checkout_command(root: Path) -> tuple[str, list[str], dict[str, str]]`, which returns `("uv", ["run", "--directory", str(root), "--frozen", "opendata-atlas"], {})`;
  - `uvx_command(wheel: Path, work: Path)`, which returns `("uvx", ["--from", str(wheel), "opendata-atlas"], {})`;
  - `LIVE_CALL = ("atlas_describe_dataset", {"portal": "seattle", "dataset_id": "kzjm-xkqj"})`. With `--live`, `check` makes this one call and requires `isError: false`. Without it, the smoke stays offline: handshake, `tools/list` against the snapshot, and the reference index.

- [ ] **Step 1: Failing tests.**
  - `test_wheel_and_sdist_ship_runtime_data_not_fixtures` (`tests/test_manifest.py`) builds both with `uv build --out-dir tmp_path`.
    - The wheel holds `assets/icon.svg`, `assets/contributing.md`, `portals/registry.json`, `portals/validation.json`, and `portals/<pack>/portal.toml` for `seattle` and `data.cityofchicago.org`. Known positive: `registry.json` is present.
    - Neither archive has a member containing `tests/`, `fixtures/`, `evals/` or `.curation/`.
  - `test_bundle_requires_every_pack`: `build_bundle.REQUIRED` holds each shipped pack's `portal.toml`.
  - `test_try_it_locally_matches_smoke` (`tests/test_readme.py`): the JSON block under `## Try it locally` parses. Its `command`/`args` equal `checkout_command(Path("/path/to/opendata-atlas"))` with the path placeholder. README's `claude mcp add` line for the checkout ends with the same argv.
- [ ] **Step 2: Run them.** Expected: the bundle and README tests FAIL. The archive test PASSES today (measured: 84 files each, no tests). Keep it as the regression pin.
- [ ] **Step 3: Implement** the modes, `REQUIRED`, and the README section. The section has three paths, each with a Claude Code `claude mcp add opendata-atlas -- …` command and one Claude Desktop `mcpServers` JSON snippet:
  - (a) checkout: `uv run --directory /path/to/opendata-atlas --frozen opendata-atlas`;
  - (b) a built wheel: `uv build`, then `uvx --from /path/to/dist/opendata_atlas-0.1.0-py3-none-any.whl opendata-atlas`;
  - (c) the bundle: `make mcpb`, then open `dist/opendata-atlas-0.1.0.mcpb` in Claude Desktop.

  Check the `claude mcp add` syntax with `claude mcp add --help` (free). Never run `claude mcp add`: it writes the user's configuration.
- [ ] **Step 4: Build and smoke every path.** Run each from `$WT`:
  - `uv build --out-dir dist`
  - `make mcpb`. Expected: `dist/opendata-atlas-0.1.0.mcpb: N files, all allowlisted`, and `git diff --exit-code manifest.json`.
  - `uv run python scripts/smoke_test.py --checkout .`
  - `uv run python scripts/smoke_test.py --wheel dist/*.whl`
  - `uv run python scripts/smoke_test.py --sdist dist/*.tar.gz`
  - `uv run python scripts/smoke_test.py --uvx dist/*.whl`
  - `uv run python scripts/smoke_test.py --bundle dist/*.mcpb`

  Expected: each prints `server started, 5 tools, reference index served`.
- [ ] **Step 5: [LIVE] One live call per path.** Rerun the checkout, uvx and bundle smokes with `--live`. That is three calls in all, each a describe summary of Fire 911. Expected: each passes. Record the seven outcomes (no values) in the task report.
- [ ] **Step 6: Run the gate.** Expected: PASS. `dist/` is git-ignored, so `git status --short` lists only the intended files.
- [ ] **Step 7: Commit** `feat: smoke-test local install paths and document trying the server`.

---

### Task 7: Port comparison, README and the release checklist

**Files:**
- Create: `docs/release-checklist.md`.
- Modify: `README.md`, `docs/design.md` (Constraints line 50: the port result), `docs/decisions.md` (new row "Port comparison (milestone 5)"), `CHANGELOG.md` (docs line).

**Interfaces:**
- Consumes: Tasks 1–6 for the back-port list and the README paths.

- [ ] **Step 1: Re-run the port comparison (read-only).** Fork revision `26c662858f4ef27bc5df0528e8233a80488e041e` (decisions row "Fork"). Run:
  - `git -C /Users/bdc/projects/seattle-open-data log --oneline 26c6628..HEAD`
  - `git -C /Users/bdc/projects/seattle-open-data log --oneline --all ^26c6628`
  - `git -C /Users/bdc/projects/seattle-open-data diff --quiet 26c6628 origin/perf/metadata-caching`
  - `git -C /Users/bdc/projects/seattle-open-data diff --quiet a8f59a2 origin/fix/prerelease-review`

  Expected, as measured at planning:
  - `main` has no commits after the fork.
  - `origin/perf/metadata-caching` (`61d7ec3`, `e21df71`) has a tree identical to `26c6628`, which squash-merged it (#25).
  - `origin/fix/prerelease-review` (`8bf79b5`, `79167c1`, `8524513`) has a tree identical to `a8f59a2`, which squash-merged it (#24), an ancestor of the fork.
  - The untracked `review-20261017.md` in that checkout is a review at the fork revision, not a fix.

  So there is **nothing to port, and nothing to close beyond these two branches**: each is closed with the reason "already in the fork as a squash merge". If any output differs, list each new commit and port it as its own `fix:` commit (test-first), or close it with a reason.
- [ ] **Step 2: Check the back-port candidates.** For each, confirm that seattle-open-data lacks it. Known positive: the same grep finds it in opendata-atlas.

  | Candidate | opendata-atlas | Check in seattle-open-data |
  | --- | --- | --- |
  | eval runner restricts tools (`--tools`) | `evals/run.py` | `grep -n '"--tools"' evals/run.py` |
  | per-session `--max-budget-usd` (ruling 74) | `evals/run.py` | `grep -n max-budget evals/run.py` |
  | strict argument parsing, `--help` free (ruling 55) | `evals/run.py` | `grep -n argparse evals/run.py` |
  | no `logging` capability or UI extension advertised | `mcp/server.py` | `grep -n 'logging/setLevel\|UI_EXTENSION' src/seattle_open_data/mcp/server.py` |
  | fixture identity scrub and guard (Task 1) | `scripts/scrub_fixtures.py` | `grep -rlE '@seattle\.gov' tests/fixtures \| wc -l` (planning: 20 files) |
  | `now_weekday` (Task 2), minified icon (Task 2), place-phase budget (Task 4) | as built | read the matching files |

  The planning run found every candidate missing there. The list goes in the checklist; seattle-open-data is not edited.
- [ ] **Step 3: Write `docs/release-checklist.md`.** Every item names who acts, the command or decision, and where its record lives:
  1. Token portability probe, which needs a token: `SOCRATA_APP_TOKEN=… uv run python scripts/feasibility/check_token.py`. The result goes in `docs/upstream-facts.md` and the "Token probe" row; `SOCRATA_APP_TOKENS` waits on it.
  2. Reserve `opendata-atlas` on PyPI (maintainer; design Constraints).
  3. Create `github.com/briandconnelly/opendata-atlas`, deciding first between a **fresh history** and a deliberate push of the existing one. Commits before Task 1 hold 76 email occurrences and 247 name values in `tests/fixtures/http/`. Count them with `git log --all -p -- tests/fixtures | grep -cE '@seattle\.gov'`, counting only. Then:
     - set up the `pypi` and `testpypi` environments, each with a required reviewer;
     - add a trusted publisher for `release.yml` on each index;
     - run the TestPyPI rehearsal (`workflow_dispatch`, `publish_to: testpypi`).
  4. Confirm the `AGENTS.md` paid-run rule (ruling 71: *Claude's call; maintainer to confirm*).
  5. Rule on the ruling 88 grade (row "Chicago pack knowledge gaps", **For the maintainer**). If both fresh task-03 grades are wrong, revert `ef2e9bf` with a new commit before release.
  6. Decide on the seattle-open-data back-ports: the table from Step 2.
  7. Bump prek's ruff pin from `v0.17.0` to the version `uv run ruff --version` prints (carry-over 4).
  8. Delete branch `curate/test-2026-10-18` or keep it (carry-over 2).
  9. Then follow `docs/releasing.md` in order: the drift run (`uv run pytest --run-integration -m integration`), committing `validation.json`, `tests/test_release_gate.py`, `scripts/rehearse_release.py --apply --date <day>`, the tag `v0.1.0`, the push, and the approval.
- [ ] **Step 4: README.**
  - Status: preview, from Task 5.
  - Name the curated portals: Seattle (`seattle`) and Chicago (`chicago`).
  - Replace the stale sentence "In this release every claim reports `validation: "unchecked"`; none is re-checked at runtime" with the runtime freshness behavior (the CHANGELOG "Runtime freshness" entry; `stale` after 180 days).
  - Mark the Install section's release paths "after the first release", pointing to Try it locally until then.
  - The Release section links `docs/release-checklist.md`.
  - The docs site's scope is the README plus `docs/` as they stand (no hosted site): one sentence.
  - Then run `uv run pytest tests/test_readme.py tests/test_issues_url.py -v`. Expected: PASS.
- [ ] **Step 5: Design and decisions.** Constraints line 50 gains: "Milestone 5 (2026-10-19): no seattle-open-data commit follows the fork; nothing to port (decisions row "Port comparison")". Add the row, carrying Steps 1–2's command outputs as counts and hashes. `CONTRIBUTING-portals.md` is unchanged, since no contributor command changed. Confirm with `git diff --stat docs/design -- CONTRIBUTING-portals.md src/opendata_atlas/assets/contributing.md`. Expected: empty.
- [ ] **Step 6: Run the gate and commit** `docs: add the release checklist, port comparison and try-it-locally README`.

---

### Task 8: Standards review and reconciliation

**Files:**
- Create: `docs/reviews/2026-10-19-m5-standards.md`.
- Modify: `docs/decisions.md`, `docs/design.md`, `CHANGELOG.md`, plus any file a Material finding fixes.

- [ ] **Step 1: Focused `agent-friendly-mcp` review** of the surface diff `docs/design..feat/release-prep`:
  - `source.now_weekday`: naming, absence semantics, `[3.strict-types]`;
  - resource `size`: `[4.triage-metadata]`;
  - the icon: serverInfo;
  - the describe phase budget: §7 deadlines stated in the description;
  - the deferred F8 and F10 rows: `[9.tier-metadata]`, `[3.dialect]`; check that their reasons hold.

  Then run `separating-context-from-constraints` on the changed served prose: the capability summary's Time line, and any changed tool or resource description. Write findings with severity and file:line.
- [ ] **Step 2: Fix every Material finding** test-first, one `fix:` commit each. A fix that would change `tools/list` must fit the 16 B of headroom or become a row instead. Minor findings go in the review file as Deferred, with a reason.
- [ ] **Step 3: Reconcile the deferred rows.** Mark each **Done** or **Deferred**, with its commit or reason:
  - icon/status/release-cut;
  - F8/F9/F10;
  - region values;
  - the milestone 5 surface items: (a) Done; (b) per Task 4; (c) Deferred, out of milestone 5 scope; (d) as below;
  - the Codex host: Deferred and documented. `codex exec --help` (codex-cli 0.163.0) lists no budget option, re-checked 2026-10-19. The Claude cap's overshoot stays unprobed, since a probe spends money;
  - release-cut;
  - fixture identities;
  - token probe: Deferred to the checklist;
  - "Name timing and hosting": GitHub hosting is still assumed, and the repo is created by the checklist.

  Add one row, "Milestone 5 reconciliation", listing each.
- [ ] **Step 4: Final measures and CHANGELOG.** Rerun `uv run pytest tests/test_contract.py::test_tools_list_within_byte_budget tests/test_reference_topics.py::test_instructions_fit_the_ruling_23_limit -s` and the measure script. Write the final framed `tools/list` (both eras), `INSTRUCTIONS` and stamp figures into design's Byte budgets. Check that `## [Unreleased]` is still the open heading (uncut) and that it lists every user-visible change from Tasks 1–7.
- [ ] **Step 5: Full verification.** Run the gate. Then:
  - `uv run python scripts/rehearse_release.py --date 2026-10-19`: OK.
  - `uv run python scripts/gen_manifest.py --check`: exit 0.
  - The Task 6 Step 4 smokes, offline: each passes.
  - The email scan over the branch's tracked files, known positive first: 0.
  - `git status --short`: empty after the commit.
  - `git log --oneline docs/design..feat/release-prep`: one commit per task, plus any fixes.
- [ ] **Step 6: Commit** `docs: milestone 5 standards review and reconciliation`.
