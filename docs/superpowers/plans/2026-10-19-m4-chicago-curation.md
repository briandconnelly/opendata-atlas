# opendata-atlas Milestone 4: Chicago Through the Front Door — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take `data.cityofchicago.org` from `generic` to `curated` purely through `skills/curate-portal/SKILL.md`. The skill's output commit is merged after review. A reviewer other than the curating agent promotes the portal. The milestone opens with one engine fix, `pack_levels` region-layer mapping, and runs a bounded loop for any engine gap the curation exposes.

**Architecture:** This milestone is mostly orchestration.
- **Task 1** fixes `pack_levels` test-first, so the tier test and the portal summary agree with describe before any pack relies on them.
- **Task 2** makes every paid session's cost cap enforceable with `--max-budget-usd`.
- **Task 3** runs `tests/test_curation_skill.py` headless against Chicago. The produced `curate/test-<date>` branch is the deliverable: it is renamed `curate/chicago-run<N>`, reviewed as a PR (**Task 5**) and merged into `feat/chicago-curation`.
- **Task 4** handles engine gaps. It is a fixed-step template capped at 2 instances, with separate pre-merge and post-merge paths.
- **Task 6** runs the standards review and lands its fixes, before any final paid gate.
- **Task 7** promotes the portal. An independent reviewer re-grades the curating agent's 3 preserved eval runs, and 3 fresh runs on the merged pack serve as extra validation. The promotion is its own commit.
- **Task 8** re-runs the launch-scope evals.
- **Task 9** reconciles the docs.

*(Revised after an independent Codex review of the draft `f4e5726`. Rulings 74–83 are recorded in Task 9's decisions rows.)*

**Tech Stack:** Python ≥3.13, uv, FastMCP 4 on MCP SDK v2, pytest with the record/replay `tests/http_fixtures.py`; `claude -p` (Claude Code) for the curation run and the evals; git worktrees.

**Spec:** `docs/design.md`: Milestones item 4, Launch scope (`chicago`), Curation runbook, Per-portal eval tasks, Knowledge levels ("Who can review", ruling 64), Contribution path (promotion rule, ruling 58), Evals (wrong-portal guard, ambiguous place). Carry-over inputs, binding: `docs/superpowers/plans/2026-10-19-m4-carryover.md`. Scope rulings: the controller's milestone 4 scope file, items 1–7. Also read `AGENTS.md`, `docs/decisions.md`, `skills/curate-portal/SKILL.md`, `CONTRIBUTING-portals.md`, `tests/test_curation_skill.py` and `evals/run.py`.

**Scope notes:**
- **Out of scope.** Task 9 records each of these as a decisions row; none is planned:
  - the token probe (needs a maintainer token);
  - the fixture identity scrub (the maintainer's decision);
  - PyPI;
  - the release, bundle and docs site (milestone 5);
  - deleting branch `curate/test-2026-10-18` (the maintainer's call);
  - re-curating Honolulu.
- **Base:** `docs/design` HEAD (`722ebc6`, plus the commit that adds this plan). Work on `feat/chicago-curation` in the worktree `/Users/bdc/projects/opendata-atlas-m4`, called `$WT` below. Other agents may use the main checkout `/Users/bdc/projects/opendata-atlas`: never switch branches there. The repo has no remote: never push.
- **Paid steps** are marked **[PAID, background]** and **live, free steps** **[LIVE]**. Each paid step names its command, its cost cap, the expected outcome and what to do on failure. `<scratchpad>` is the executing session's scratchpad directory, as an absolute path. `<date>` is `date +%F` at the step's start; `<N>` is the curation run number (1–3).

## Global Constraints

- Gate for every task: `uv run pytest -q`, `uv run ruff check`, `uv run ruff format --check`, `uv run ty check`, `uv run prek run --all-files`. prek pins ruff v0.17.0, which missed a RUF007 that `uv run ruff check` caught, so the gate keeps both (carry-over).
- Commits: Conventional Commits, each ending with a blank line, then `🤖 Generated with Claude Code` and `Claude-Session: https://claude.ai/code/session_01CH7uTSKtTjy4NoHCYKFHyx` on the next line. Never commit to `docs/design` or `main`. Never push. Never rewrite history: no rebase, no amend of a commit already merged, no `reset --hard` on a branch with commits, no force.
- **Paid runs** (AGENTS.md; the maintainer's approval of this plan is the request): only the steps marked [PAID] start one. Each runs with `run_in_background`. Never set `ATLAS_RUN_CURATION` except in Task 3's run step. `--help` is the only probe of a paid command.
- **Milestone cap: $60. Every session is capped while it runs (ruling 74).** After Task 2:
  - the curation session runs with `--max-budget-usd 12`;
  - every eval session (`evals/run.py`, including the sessions the curating agent launches) runs with `--max-budget-usd 1`.

  Each paid step states its **worst case**: the number of sessions times the per-session cap. A curation run's worst case is $12 plus 4 × T × $1, where T is the number of tasks in the pack's eval file. The 4 covers the agent's 3 eval runs plus the test's 1.

  Before each paid step, check that the ledger total plus that step's worst case is at most $60. Otherwise, stop and report to the maintainer.

  | Step | Worst case | At T = 4 |
  | --- | --- | --- |
  | Task 3, one curation run | $12 + 4·T·$1 | $28 |
  | Task 7 Step 3, 3 fresh runs | 3·T·$1 | $12 |
  | Task 8 Steps 1–2 | 9·$1 + 6·$1 | $15 |

  At T = 4, the planned worst cases total $55. That leaves room for **one** curation run at its worst case. A second or third run may start only if the **recorded** ledger total plus its worst case is at most $60. Honolulu's real costs were far lower: $3.47 for the session, and about $0.12 per eval task.
- **No free unknowns (ruling 75).** Before a step runs, the ledger `docs/evidence/m4-costs.md` lists every expected session by its transcript path. Afterwards, each expected session needs a recorded `total_cost_usd`. A missing transcript, a transcript with no `result` event, or a result with no `total_cost_usd` is **unresolved spend**, and it blocks every further paid step until resolved.
  - Resolve it from the session's stderr. If no cost is found, record the session's full per-session cap.
  - Before resolving or retrying, confirm that no child `claude` process is still running, with `pgrep -fl "claude -p"`.
  - Check that instrument first: a background `sleep 30 &` must show up in `pgrep -fl sleep`.
- **Cost check.** For each expected transcript, this prints its cost, or `UNRESOLVED` and the reason:
  `cd /Users/bdc/projects/opendata-atlas-m4 && uv run python -c 'import sys; from pathlib import Path; from tests.test_curation_skill import result_event
for t in sys.argv[1:]:
    p = Path(t); r = result_event(p) if p.exists() else None
    c = r.get("total_cost_usd") if r else None
    print(t, c if c is not None else "UNRESOLVED: " + ("missing" if r is None else "no result" if not r else "no cost"))' TRANSCRIPT ...`
- **Never force (ruling 77).** Never run `git worktree remove --force`, `git branch -D` or `git clean`. Before removing a worktree:
  - `git -C <wt> status --porcelain --untracked-files=all`, ignoring `.curation/`, `.venv/` and `__pycache__/`, must print nothing;
  - `git -C <wt> stash list` must be empty.
  Only then run plain `git worktree remove <wt>`. A worktree holding any unique work is **kept**, and its path goes in the run's manifest.
- **Front door:** the Chicago pack's contents (`src/opendata_atlas/portals/<pack>/`, `evals/portals/<pack>.json`, and the agent's `validation.json` and `registry_overrides.toml` changes) come only from a curation run's commit. Nobody hand-edits them, with one exception: Task 7's promotion commit changes the `tier` line alone.
- `<pack>` is the pack directory the run produced: `summary.json` `pack`, by the skill's default the canonical id `data.cityofchicago.org`. `<portal id>` is `summary.json` `portal_id`.
- **Facts:** never report an upstream fact you did not probe. Label reviewer-reported facts `(review)` in `docs/upstream-facts.md`.
- **Personal data:** none in committed evidence, packs or PR text. Run the personal-data scan in each step that commits evidence, after first checking that the scan finds the known positive:
  - the scan: `grep -rnE '[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z.]{2,}|\(?[0-9]{3}\)?[-. ][0-9]{3}[-. ][0-9]{4}' PATHS`;
  - the known positive: the same command on `tests/fixtures/http/` lists at least one `@seattle.gov` address;
  - names cannot be grepped, so read for them.
- **`validation.json`:** after any drift run other than the curating agent's, run `git restore src/opendata_atlas/portals/validation.json` (AGENTS.md).
- When a design choice changes, update `docs/design.md` and add a row to `docs/decisions.md`. A choice this plan marks *(Claude's call)* gets that row in the task that makes it. Every user-visible change gets a CHANGELOG line under `## [Unreleased]`, which is 0.1.0's open section.
- **Seattle parity:** `pack_levels(SEATTLE_CONTEXT, today=date(2026, 10, 18))` stays `{'33kz-ixgy': 'reviewed', '65db-xm6k': 'none', '76t5-zqzr': 'none', 'kzjm-xkqj': 'reviewed', 'ppi5-g2bj': 'none', 'tazs-3rd5': 'none'}`. `tests/snapshots/tools_list.json` does not change: no task plans a surface change, so a snapshot diff is a defect unless a Task 4 instance names it.
- **Prose standard:** the implementer audits every agent-consumed prose surface its task changes with `separating-context-from-constraints`, and lists the findings in the task report.

## Review Focus

1. **`portal: "chicago"` once the identity moves into the pack.** Skill step 4 deletes the registry override that carries `aliases = ["chicago"]` and `place_names`. Expected: `chicago` still resolves to `data.cityofchicago.org`, and `atlas_find_portals {"query": "Chicago"}` returns it first. Checked in Task 5 Step 4; pinned by `test_chicago_alias_survives_the_pack` in Task 5 Step 8.
2. **Summary against describe on Chicago's real datasets.** A dataset with claims on only some of its computed-region columns under-counts its layers (carry-over caveat). Expected: for every dataset in the pack, `pack_levels` equals live describe's `knowledge.level`. Checked in Task 5 Step 4; a mismatch is an engine gap (Task 4).
3. **The Chicago portal summary within budget.** Expected: `atlas_get_reference {"topic": "portals", "item_id": "chicago"}` returns `isError: false`, and its tier matches `portal.toml`. Checked in Task 5 Step 4 and again after promotion in Task 7 Step 7.
4. **Chicago against Cook County.** Expected: "crimes in Chicago" queries Chicago, and "permits in Cook County" uses a distinct portal or asks. Covered by tasks 25 and 26 in Task 8.
5. **Seattle after the merge and the engine fixes.** Expected: Seattle's levels and answers are unchanged. Covered by Task 1's `test_pack_levels_seattle_unchanged` and Task 8's Seattle subset.

---

## File Structure

```
src/opendata_atlas/portals/knowledge.py        # pack_levels maps each dataset to its layers   (Task 1)
tests/test_curation_env.py, tests/test_evals.py # --max-budget-usd pins                         (Task 2)
src/opendata_atlas/portals/<pack>/             # from the curation commit only; tier line     (Tasks 5, 7)
evals/portals/<pack>.json                      # from the curation commit only                (Task 5)
tests/test_freshness.py                        # 3 synthetic pack_levels cases + Seattle      (Task 1)
tests/test_registry.py                         # chicago alias pin                            (Task 5)
docs/evidence/m4-costs.md                      # cost ledger                                  (Task 3 on)
docs/evidence/curation-chicago-<date>-run<N>/  # manifest.json, summary.json, diffstat, init check (Task 3)
docs/reviews/<date>-m4-chicago-pack.md         # pack review, committed before the merge      (Task 5)
evals/results/<date>-m4.md                     # promotion grades, launch-scope run           (Tasks 7, 8)
docs/reviews/<date>-m4-standards.md            # standards review                             (Task 6)
docs/design.md, docs/decisions.md, CHANGELOG.md, carry-over                                   (every task as needed)
```

---

### Task 1: Map each dataset to its own region layers in `pack_levels`

**Files:**
- Modify: `src/opendata_atlas/portals/knowledge.py:324-355` (`pack_levels` and its docstring).
- Test: `tests/test_freshness.py`. The new tests go after `test_stale_layer_lowers_the_summary_as_describe` and use its helpers `_with_claims`, `_claim` and `TODAY`.
- Modify: `docs/decisions.md` (the "Region layers in the offline summary (final review M-1)" row, plus a new row), `docs/design.md:96` (Knowledge levels), `CHANGELOG.md:26` (topic `portals` line).

**Interfaces:**
- Consumes: `dataset_knowledge(portal, dataset_id, knowledge_bearing, primary_time, *, layers, today) -> Knowledge`; `Pack.place_fields(dataset_id) -> dict[str, Claim]`.
- Produces: `pack_levels(portal: PortalContext, *, today: date) -> dict[str, KnowledgeLevel]`, with the same signature and new semantics. Tasks 5 and 7 rely on it through `tests/test_tiers.py` and topic `portals`.

- [ ] **Step 1: Worktree.** `git -C /Users/bdc/projects/opendata-atlas worktree add /Users/bdc/projects/opendata-atlas-m4 -b feat/chicago-curation docs/design`. Then `cd /Users/bdc/projects/opendata-atlas-m4 && uv sync && uv run pytest -q`. Expected: the suite passes on the base.

- [ ] **Step 2: Write the failing tests.** Each builds a context from Seattle plus synthetic claims for dataset `synt-0001`. The claims are built with `Claim.model_validate` on the fields of `docs/pack-examples/<kind>.toml`. A "fill observation" is the profiler's shape: a `place_field` with id `synt-0001-<column>-fill` and no interpretation. `A_COL = ":@computed_region_aaaa_1111"` maps to layer `aaaa-1111`. Every case also gives `synt-0001` a reviewed `unit_of_observation` claim and a reviewed `column_timezone` claim on `created_date`. "Describe" below means `dataset_knowledge(ctx, "synt-0001", [A_COL], "created_date", layers={A_COL: "aaaa-1111"}, today=TODAY).level`, which is what describe computes for a schema exposing `A_COL`.

```python
def test_pack_levels_ignores_layers_a_dataset_does_not_expose():
    # over-reach: A_COL fill observation; layer aaaa-1111 reviewed; layer bbbb-2222 an
    # unreviewed region_layer observation, exposed by dataset synt-0002's own fill claim
    assert pack_levels(ctx, today=TODAY)["synt-0001"] == "reviewed" == describe(ctx)


def test_pack_levels_counts_a_datasets_own_unreviewed_layer():
    # under-reach: A_COL fill observation; no aaaa-1111 layer claim; Seattle's layers reviewed
    assert pack_levels(ctx, today=TODAY)["synt-0001"] == "profiled" == describe(ctx)


def test_pack_levels_lets_a_reviewed_place_field_override_its_layer():
    # ruling 62: reviewed place_field on A_COL; layer aaaa-1111 an unreviewed observation
    assert pack_levels(ctx, today=TODAY)["synt-0001"] == "reviewed" == describe(ctx)


def test_pack_levels_seattle_unchanged():
    assert pack_levels(SEATTLE_CONTEXT, today=TODAY) == {
        "33kz-ixgy": "reviewed",
        "65db-xm6k": "none",
        "76t5-zqzr": "none",
        "kzjm-xkqj": "reviewed",
        "ppi5-g2bj": "none",
        "tazs-3rd5": "none",
    }
```

- [ ] **Step 3: Run them.** `uv run pytest tests/test_freshness.py -k pack_levels -v`. Expected: the three synthetic cases FAIL, reading `profiled`, `reviewed` and `profiled`. The Seattle case PASSES.

- [ ] **Step 4: Implement** the carry-over's smallest fix in `pack_levels`, for each dataset:
  - `own = [c for c in pack.place_fields(dataset_id) if c.startswith(":@computed_region_")]`;
  - `own_layers = {c: c.removeprefix(":@computed_region_").replace("_", "-") for c in own}`;
  - pass `places = [non-":" place-field columns] + own` and `layers=own_layers`;
  - only when `own` is empty, fall back to today's all-pack `layers` map, for both;
  - other `:` columns stay dropped.

  Rewrite the docstring to say this, naming the caveats: the fix relies on Socrata's column naming; a dataset with claims on only some of its computed-region columns under-counts its layers; the robust alternative is a `layer` in the scope of the profiler's fill claim.

- [ ] **Step 5: Run the tests.** `uv run pytest tests/test_freshness.py tests/test_tiers.py tests/test_reference_topics.py -v`. Expected: all PASS, `test_stale_layer_lowers_the_summary_as_describe` included. Then run the full gate.

- [ ] **Step 6: Correct the wording.**
  - The M-1 decisions row says the summary "can read lower than describe, never higher", which is false. Its note implies the profiler emits region-layer observations; it never emits `region_layer` claims (`profiler/profile.py`, `emit.py`). Restate both and end the row "(corrected in milestone 4 Task 1; next row)".
  - Add the new row: Topic "Region layers per dataset in `pack_levels` (M-1 follow-up)", the three cases and the caveats, Source "carry-over M-1, ruling 73, Claude, <date>" *(Claude's call)*.
  - Restate `docs/design.md:96`'s parenthesis and `CHANGELOG.md:26`'s "counting every region layer in the pack against every dataset, so … lowers the summary as it lowers describe" to the per-dataset rule.

- [ ] **Step 7: Commit.** `fix: map each dataset to its own region layers in pack_levels`

---

### Task 2: Enforceable per-session cost caps

**Files:**
- Modify: `tests/test_curation_skill.py` (`claude_command`), `evals/run.py` (`claude_command`).
- Test: `tests/test_curation_env.py`, `tests/test_evals.py`.
- Modify: `docs/decisions.md`, `CHANGELOG.md`, `CONTRIBUTING-portals.md` and its served copy `src/opendata_atlas/assets/contributing.md` (one sentence each on the caps), `docs/design.md` (Curation runbook and Per-portal eval tasks).

**Interfaces:**
- Produces: `CURATION_BUDGET_USD = 12` in `tests/test_curation_skill.py` and `EVAL_BUDGET_USD = 1` in `evals/run.py`. Each command carries `--max-budget-usd` with that value. The global cost rules rely on these numbers.

- [ ] **Step 1: Check the flag.** `claude --help | grep -A1 -- --max-budget-usd`. Expected: the flag is listed, with "only works with --print". Both commands already pass `-p`.
- [ ] **Step 2: Failing tests.**
  - `test_claude_command_caps_spend` (test_curation_env.py): `--max-budget-usd` is followed by `"12"`.
  - `test_eval_command_caps_spend` (test_evals.py): `--max-budget-usd` is followed by `"1"`, and the flag appears exactly once.
- [ ] **Step 3: Run them.** Expected: both FAIL (the flag is absent).
- [ ] **Step 4: Implement** both constants and flags.
- [ ] **Step 5: Run them and the gate.** Expected: PASS. `uv run python evals/run.py --help` exits 0, and no session launches; prove this with the fake-`claude` PATH check from milestone 3 (known positive: a direct call of the fake writes `LAUNCHED`).
- [ ] **Step 6: Docs.** Add a decisions row (ruling 74, with the per-session caps), a CHANGELOG line, and the CONTRIBUTING sentence. `tests/test_contributing.py` must pass.
- [ ] **Step 7: Commit** `feat: cap every paid session with --max-budget-usd`.

---

### Task 3: Chicago curation run `<N>`

Runs as N = 1. It runs again only when Task 4 or a Step 6 outcome sends it back, and never past N = 3.

**Files:**
- Create: `docs/evidence/m4-costs.md` (on the first run); `docs/evidence/curation-chicago-<date>-run<N>/` (`summary.json` written by the test, `diffstat.txt`, `init-check.json`, `costs.txt`).
- Local only, git-ignored: `evals/results/<date>-m4-curation-run<N>/`, a copy of the agent's `.curation/evals-1..3`.

**Interfaces:**
- Consumes: Task 1's commit (or the latest Task 4 commit) at `feat/chicago-curation` HEAD. The test branches from the HEAD of the checkout that holds it (`ROOT` = `$WT`), so commit everything before the run.
- Produces: branch `curate/chicago-run<N>` holding the agent's commit; `summary.json` with `pack`, `portal_id`, `declared_tier`, `base`, `failures` and `curation.final_message` (the PR body). Tasks 4–7 read these.
- Test facts (from `tests/test_curation_skill.py`), which this task relies on:
  - the test runs `git worktree add <tmp_path>/wt -b curate/test-<date.today()> HEAD` and never removes it;
  - a second run on the same day fails on the existing branch, hence Step 7's rename;
  - `<tmp_path>` is `<basetemp>/test_curation_skill_produces_a0`;
  - the transcript is `<tmp_path>/curation.transcript.jsonl` and the test's eval run is `<tmp_path>/evals/`;
  - the agent's runs are `<tmp_path>/wt/.curation/evals-{1,2,3}/`;
  - a `subprocess.TimeoutExpired` after 3 hours writes no `summary.json`, but the test prints `worktree <wt> on <branch> at <base>` first.

- [ ] **Step 1: Free pre-checks.**
  - `cd /Users/bdc/projects/opendata-atlas-m4 && git status --short`. Expected: empty.
  - Confirm that Chicago's pack directory does not exist on HEAD: `test ! -e src/opendata_atlas/portals/data.cityofchicago.org`. If it exists, the pack is already merged and this task must not run; see Task 4's post-merge path.
  - `uv run pytest --run-integration -m integration tests/test_curation_skill.py`. Expected: `1 skipped`, with no opt-in set.
  - Count Chicago's eval tasks. If the pack is not yet written, use T = 6, the skill's maximum. Then apply the cost gate (Global Constraints) and the count check: N ≤ 3.
  - Write the expected-session list to the ledger: the curation transcript, and `.curation/evals-{1,2,3}/*.transcript.jsonl` plus `evals/*.transcript.jsonl` for each eval task.
- [ ] **Step 2: [PAID, background] Curation run.**
  - Command: `cd /Users/bdc/projects/opendata-atlas-m4 && DATE=$(date +%F) && ATLAS_RUN_CURATION=1 ATLAS_CURATION_PORTAL=data.cityofchicago.org ATLAS_CURATION_EVIDENCE=/Users/bdc/projects/opendata-atlas-m4/docs/evidence/curation-chicago-$DATE-run<N> uv run pytest --run-integration -m integration tests/test_curation_skill.py -v -s --basetemp=<scratchpad>/m4/run<N> 2>&1 | tee <scratchpad>/m4/run<N>.log`
  - Cap: enforced per session (Task 2). The step's worst case is $12 + 4·T·$1.
  - Expected: `1 passed`, and `summary.json` with `failures: []`, `declared_tier: "profiled"` and `portal_id: "data.cityofchicago.org"`. The final message is the PR body, and it either proposes `curated` with per-run grades or names its gaps.
  - On failure: Step 7 classifies the outcome, but Steps 3–6 always run first, whatever the outcome.
- [ ] **Step 3: Recovery manifest (ruling 78).** Write this unconditionally, before anything else. Write `docs/evidence/curation-chicago-<date>-run<N>/manifest.json` with these fields (`mkdir -p` the directory first):
  - `run`, `base` and `branch`: from `summary.json` if it exists, else from the `worktree <wt> on <branch> at <base>` line in `run<N>.log`;
  - `worktree` (`<tmp_path>/wt`);
  - `transcript`;
  - `pytest_exit` (from the log);
  - `artifacts`: one entry per expected path, each `present` or `missing`;
  - `kept_worktree`: filled in at Step 8.
- [ ] **Step 4: Record the cost.** Run the cost check over every expected transcript in the ledger. Record each result, also writing `summary.json`'s `curation.total_cost_usd` and `num_turns` if they exist, into `costs.txt` and the ledger. Any `UNRESOLVED` line is unresolved spend (ruling 75), so resolve it before any further paid step. If the recorded total exceeds the step's worst case, stop and report after Step 8.
- [ ] **Step 5: Connector check.**
  - First check the instrument on two inputs:
    - **known negative:** `/Users/bdc/projects/opendata-atlas/evals/results/2026-10-18-m3/cross/25-wrong-portal.transcript.jsonl` must print `mcp_servers` naming only `opendata-atlas`;
    - **known positive:** a synthetic init line written to `<scratchpad>/m4/fake-init.jsonl`, with `"tools": ["Read", "mcp__claude_ai_Gmail__search"]` and `"mcp_servers": [{"name": "claude.ai Gmail", "status": "connected"}]`, must make the check **fail**.
  - Then run the check on the curation transcript and save its output as `init-check.json`. Expected: exactly one init event, an empty `mcp_servers`, no `mcp__` tool, and no `claude.ai` or `claude_ai` anywhere in the event. A missing init event, a malformed one, or more than one init event fails the check.
  - On failure: record it in `docs/decisions.md`, and stop and report before any further paid run.

  `cd /Users/bdc/projects/opendata-atlas-m4 && uv run python -c 'import json, sys
inits = [e for e in map(json.loads, open(sys.argv[1])) if e.get("type") == "system" and e.get("subtype") == "init"]
assert len(inits) == 1, f"{len(inits)} init events"
e = inits[0]; tools = [t for t in e.get("tools", []) if t.startswith("mcp__")]
out = {"mcp_servers": e.get("mcp_servers"), "mcp_tools": tools}
print(json.dumps(out))
bad = [s for s in (e.get("mcp_servers") or []) if s.get("name") != "opendata-atlas"] + [t for t in tools if not t.startswith("mcp__opendata-atlas__")]
assert not bad and "claude_ai" not in json.dumps(e) and "claude.ai" not in json.dumps(e), bad' TRANSCRIPT`

  (On the curation transcript, the expected `opendata-atlas` entries are absent too, so `mcp_servers` must be empty or null.)
- [ ] **Step 6: Keep the evidence.** Collect only what the manifest lists as present, and record every missing artifact in it.
  - `mkdir -p /Users/bdc/projects/opendata-atlas-m4/evals/results/<date>-m4-curation-run<N>/`, then copy each **present** `.curation/evals-<n>` directory into it. Check afterwards that the expected transcript files arrived.
  - If both `base` and `branch` are known, run `git -C /Users/bdc/projects/opendata-atlas-m4 diff --stat <base> <branch> > …/diffstat.txt`.
  - Never copy `.curation/report.json`: its `review_values` may hold personal data.
  - Run the personal-data scan over the evidence directory, known positive first.
- [ ] **Step 7: Classify the outcome and pick the next task.**

  | outcome | next |
  | --- | --- |
  | `1 passed` and no rule-8 stop in the PR body, whether or not it proposes `curated`. The reviewer's grades govern (Task 7). | Task 5 |
  | the PR body, or a new `docs/decisions.md` row on the branch, names an engine gap the pack cannot work around (skill rule 8) | Task 4 (pre-merge path), if fewer than 2 instances have run; otherwise stop and report |
  | infrastructure: an API error, `api_error_status` set, a budget stop, or a timeout with no gap named | Task 3 again, if N < 3 and the cost gate allows; otherwise stop and report |
  | a failure the skill already forbids: the path rule, a tier above `profiled`, a check failing on the pack, or personal data (agent variance) | Task 3 again once, if N < 3. The same failure twice is a skill defect: stop and report. |
  | the connector check failed (Step 5) | stop and report |
- [ ] **Step 8: Free the branch name; keep unique work.**
  - Run the never-force check (Global Constraints) on `<tmp_path>/wt`.
    - **Clean:** `git -C /Users/bdc/projects/opendata-atlas-m4 worktree remove <tmp_path>/wt`.
    - **Not clean:** keep the worktree, write its path to the manifest's `kept_worktree`, and stop and report if Step 7 routed to Task 3 again, because a second run would need the branch name.
  - If the branch exists, `git -C /Users/bdc/projects/opendata-atlas-m4 branch -m <branch> curate/chicago-run<N>`. (Renaming a branch that a kept worktree has checked out is allowed. Git updates the worktree.)
  - Expected: `git log --oneline -1 curate/chicago-run<N>` shows the agent's commit, or the base if the agent made none. `git worktree list` matches the manifest.
  - Never delete a run branch: unmerged runs stay for inspection.
- [ ] **Step 9: Commit** the evidence, the manifest and the ledger: `test: record chicago curation run <N>`.

---

### Task 4: Engine gap `<k>` (template; at most 2 instances, k = 1, 2)

One instance per engine gap. A gap arrives here from one of two places: Task 3 Step 7 (**pre-merge**), or from a reviewer or eval in Tasks 5, 7 or 8 (**pre-merge** if found in Task 5 before its merge, otherwise **post-merge**). Each instance is a separate task with its own reviewer. When a third gap appears, or the curation runs run out, stop and report to the maintainer, because "Chicago ships curated or the release waits" (design Launch scope).

**Files:**
- Create: `docs/evidence/engine-gap-<k>-<date>/repro.txt`.
- Modify: the engine module that owns the defect, and its test file (named in Step 2); `docs/decisions.md`; `CHANGELOG.md` when the change is user-visible; `docs/design.md` when a design choice changes.

**Interfaces:**
- Consumes: the gap. That is either the curating agent's `docs/decisions.md` row on `curate/chicago-run<N>` (`git show curate/chicago-run<N>:docs/decisions.md`) together with its PR body, or the reviewer's finding (Tasks 5, 7, 8) together with its evidence path.
- Produces: one `fix:` commit on `feat/chicago-curation`.

- [ ] **Step 1: Reproduce.** Write the smallest call that shows the defect: an in-process tool call (SKILL.md, Context: Tool calls) or a unit call, on Chicago live [LIVE] or on a recorded fixture. Save the command and its output to `repro.txt`, with personal data removed. Expected: the output shows the defect the gap describes. If it does not reproduce, record that and send the outcome back to its source task as agent variance (Task 3 Step 7) or as a closed finding.
- [ ] **Step 2: Write the failing test.** Put it in the test file of the module that owns the behavior. It runs offline, on a fixture recorded with `tests/http_fixtures.py`. Name it for the behavior (`test_<behavior>`), and have it assert the correct output for the repro's input.
- [ ] **Step 3: Run it.** `uv run pytest <file>::<test> -v`. Expected: FAIL, showing the repro's wrong value.
- [ ] **Step 4: Fix** it with the smallest engine change. Pack files are never touched.
- [ ] **Step 5: Run it and the gate.** Expected: the test PASSES, the full gate passes, and Seattle parity holds (Global Constraints). If `tools/list` changes, the change must be the intended surface change: regenerate with `UPDATE_SNAPSHOTS=1` and name it in the CHANGELOG. Any other change is a defect.
- [ ] **Step 6: Decisions row.** It is written by this task in every case, including a gap a reviewer found, which has no agent-written row.
  - Topic: "Engine gap <k> from Chicago curation (<short name>)".
  - Before: the defect, quoting the agent's row or the reviewer's finding.
  - After: the fix and its test.
  - Source: "<run branch or review file>, Claude, <date>".
  Add the CHANGELOG line and the design change if they apply.
- [ ] **Step 7: Commit** `fix: <behavior>`. Its own task reviewer gates it before the next step.
- [ ] **Step 8: Return. The path depends on where the gap came from (ruling 76).**
  - **Pre-merge** (Chicago's pack is absent on `feat/chicago-curation`): go to Task 3 with N + 1, subject to its counts and cost gate.
  - **Post-merge** (the pack is merged): never re-run curation, because the profiler refuses an existing pack directory (`profiler/cli.py` exits 2). The submitted pack stays as it is. Return to the step that found the gap, using **new** evidence directories with a `-postfix<k>` suffix:
    - Task 7 Steps 1–6, for a promotion or smoke gap;
    - Task 8 Steps 1–4, for a launch-eval gap.
    Any paid gate already recorded on code this fix changed is invalid (ruling 81) and is re-run on the return path.

---

### Task 5: Review the produced pack and merge it

The reviewer is a fresh agent. It never ran Task 3, and the curating agent is the headless `claude -p` child in any case. It reviews `curate/chicago-run<N>` from the last Task 3 run that routed here, as a PR would be reviewed.

**Files:**
- Create: `docs/reviews/<date>-m4-chicago-pack.md`.
- Modify by merge: the agent's commit (the pack, `evals/portals/<pack>.json`, `validation.json`, `registry_overrides.toml` and any `docs/decisions.md` rows).
- Test: `tests/test_registry.py` (alias pin, after the merge).
- Modify: `docs/design.md` (Curation runbook), `docs/decisions.md`.

**Interfaces:**
- Consumes: `curate/chicago-run<N>`; `summary.json`; `path_violations(paths, pack)` and `claim_summary(pack_dir)` from `tests/test_curation_skill.py`.
- Produces: the merge commit on `feat/chicago-curation`, which Task 7 evaluates.

- [ ] **Step 1: Review worktree.** `git -C /Users/bdc/projects/opendata-atlas-m4 worktree add <scratchpad>/m4/review-run<N> curate/chicago-run<N>`. Expected: the agent's commit is checked out there, and `$WT` keeps `feat/chicago-curation`.
- [ ] **Step 2: Mechanical checks.** Run each in the review worktree, and run each first on a known positive, listed in brackets:
  - **Path rule:** `git diff --name-only <base> HEAD` through `path_violations`. Expected `[]`. [A list holding `README.md` returns it.]
  - **Evidence for every reliability:** over `facts/*.toml` and `regions.toml`, every claim whose `interpretation` sets `reliability` has a non-empty `reason`, and evidence of kind `soql_probe`, `metadata_probe` or `document` (skill rule 1). Every reviewed claim has `reviewed_by = "claude"` (rule 18). [A temp copy of one facts file with a `reason` deleted is reported.]
  - **Personal data:** the scan over the pack, the eval file and `summary.json` `final_message`. Then read every sample value, guide and `expect` for names. [`tests/fixtures/http/`.]
  - **Tier:** `portal.toml` has `tier = "profiled"`; `jurisdiction` has the rule-21 comment (the page URL and the exact quoted passage); `timezone = "America/Chicago"`.
  - **Eval file:** the `covers` across tasks include `in_area`, `relative_date`, `misleading_field` and `not_published`. No `misleading_field` prompt names the column under test or its dataset (rule 22). When more than one dataset is reviewed, the tasks span at least 2 (rule 23). Every `expect` states PASS, PARTIAL and FAIL.
  - **Guides:** `summary.json` `checks.guide_examples.exit_code == 0`, and `checks.guide_examples.examples` is non-empty with every item `is_error: false`. Each guide's prose agrees with the claims it cites. [An examples list with one `is_error: true` item is reported.]
  - **Shared-file isolation (ruling 82).** Parse the base and branch versions of both shared files:
    - `registry_overrides.toml`: only the `data.cityofchicago.org` table may change or be removed, and every other table must be equal to the base.
    - `validation.json`, parsed as JSON: only `portals["data.cityofchicago.org"]` may differ, and every other portal's entries must be equal to the base.
    [Known positive: a temp copy with one Seattle entry's `outcome` changed is reported.]
- [ ] **Step 3: Offline gate in the review worktree.** `uv run pytest -q tests/test_packs.py tests/test_tiers.py tests/test_release_gate.py`. Expected: exit 0.
- [ ] **Step 4: [LIVE] Review Focus checks.** Run these in-process from the review worktree (SKILL.md, Context: Tool calls):
  - `atlas_find_portals {"query": "Chicago"}`: the first candidate's `id` is `data.cityofchicago.org`.
  - `atlas_describe_dataset {"portal": "chicago", "dataset_id": <id>}` for every dataset `pack_levels` returns: `knowledge.level` equals `pack_levels(...)[id]` at `freshness.today()`.
  - `atlas_get_reference {"topic": "portals", "item_id": "chicago"}`: `isError: false`, and the tier is `profiled`.
  - Expected: all three hold. A level mismatch is an engine gap (Task 4). An alias lost from the pack is a Material finding.
- [ ] **Step 5: Record the review** in `$WT` (never in the review worktree): `/Users/bdc/projects/opendata-atlas-m4/docs/reviews/<date>-m4-chicago-pack.md`. Record each check with its known positive and its result, the findings marked Material or Minor, the agent's own eval grades from the PR body, and the paths of the agent's preserved eval transcripts (Task 3 Step 6), which Task 7 needs. Commit it in `$WT` as a docs-only commit before the merge (ruling 79): `docs: record the chicago pack review`. The reviewed branch is unchanged.
  - A Material finding blocks the merge. If it is an engine gap, go to Task 4 (pre-merge path). If it is agent variance the skill already forbids, go to Task 3 again (if N < 3). Otherwise stop and report: hand-fixing the pack would break the front door.
  - Then remove the review worktree, after the never-force check: `git -C /Users/bdc/projects/opendata-atlas-m4 worktree remove <scratchpad>/m4/review-run<N>`.
- [ ] **Step 6: Merge.** All in `$WT`, which stays on `feat/chicago-curation`; nothing switches branches:

```bash
cd /Users/bdc/projects/opendata-atlas-m4
git status --short                                         # expect: empty
git merge-base --is-ancestor <base> feat/chicago-curation  # expect: exit 0 (the run branched from this line)
git log --oneline feat/chicago-curation..curate/chicago-run<N>   # expect: the agent's commit(s) only
git merge --no-ff curate/chicago-run<N> \
  -m "feat: merge the data.cityofchicago.org knowledge pack (curation run <N>)" \
  -m "🤖 Generated with Claude Code
Claude-Session: https://claude.ai/code/session_01CH7uTSKtTjy4NoHCYKFHyx"
```

  `--no-ff` keeps the skill's commit identifiable as the PR. On a conflict in `docs/decisions.md` only, keep both sets of rows (the branch's rows after this branch's), then `git add docs/decisions.md && git commit --no-edit`. On a conflict in any other path, run `git merge --abort` and stop and report.
- [ ] **Step 7: Verify the merge.** Run the full gate in `$WT`. Expected: it passes, and `git diff curate/chicago-run<N> HEAD -- src/opendata_atlas/portals/<pack> evals/portals/<pack>.json` is empty.
- [ ] **Step 8: Pin the alias.** Add `test_chicago_alias_survives_the_pack` to `tests/test_registry.py`: `load_registry().by_alias("chicago").identity.id == "data.cityofchicago.org"`, and that identity's `timezone == "America/Chicago"`. Expected: PASS on the merged tree. Known positive for the failure: in a tmp copy of `src/opendata_atlas/portals/` whose `<pack>/portal.toml` has `aliases` deleted, `load_registry(packs_dir=<tmp copy>).by_alias("chicago")` is `None`. Run it once in a scratch session and do not commit it.
- [ ] **Step 9: Docs.** Restate the Curation runbook's *(Claude's call)* "the produced pack is not merged" for milestone 4: Chicago's pack is merged after review. Add a decisions row (scope ruling 2) and a CHANGELOG `### Added` line: "The `data.cityofchicago.org` (alias `chicago`) knowledge pack, curated through the curate-portal skill."
- [ ] **Step 10: Commit** `test: pin the chicago alias`.

---

### Task 6: Standards review and fixes (before the final paid gates)

This runs after the merge and before Tasks 7 and 8, so that the paid gates evaluate the wording and behavior that ship (ruling 81).

**Files:**
- Create: `docs/reviews/<date>-m4-standards.md`.
- Modify: whatever the findings require. `AGENTS.md` and `skills/curate-portal/SKILL.md` change only if a run exposed a defect in them. Pack files never change (front door).

- [ ] **Step 1: `agent-friendly-mcp` focused route** on each served-surface change: Task 1 changes the levels in topic `portals`, and Task 2 changes the eval and curation commands; add any Task 4 change. Read `[1.spec-revision]` and the native-vs-convention rule. Read the touched sections in full, close over the ids they cite, and report everything else as `not-checked`. Re-derive the deferred milestone 3 minors only for files this milestone touched.
- [ ] **Step 2: `separating-context-from-constraints`** R1–R5 on the changed served prose and skill text: the `docs/design.md` sections that changed, plus `SKILL.md`, `CONTRIBUTING-portals.md` and its served copy if they changed.
- [ ] **Step 3: Fix** every Material finding. A behavior finding gets a failing-first regression test. Fix or list the Minors.
  - A skill defect a run exposed is fixed in `SKILL.md` and traced by hand against the run's transcript. It is never re-run in this milestone.
  - A fix that touches the engine paths Chicago's evals exercise (`core/query.py`, `core/describe.py`, `portals/knowledge.py`, notice text) must land here, before Task 7. After Task 7 starts, such a change invalidates the recorded gates (ruling 81).
  - Run the full gate, plus `tests/test_contributing.py` if CONTRIBUTING changed.
- [ ] **Step 4: Commit** `docs: record the milestone 4 standards review` (plus `fix:` commits for behavior fixes).

---

### Task 7: Independent promotion to `curated`

The reviewer is not the curating agent (ruling 64). **The promotion gate is the reviewer's re-grade of the curating agent's 3 preserved eval runs** (ruling 80). Three fresh runs on the merged pack are additional validation: they can block promotion, but they never replace the re-grade.

**Files:**
- Create or modify: `evals/results/<date>-m4.md` (section "Chicago promotion").
- Modify: `src/opendata_atlas/portals/<pack>/portal.toml` (the `tier` line only, in its own commit); `docs/decisions.md`.

**Interfaces:**
- Consumes: the merged pack; Task 5's review record, which holds the agent's grades and transcript paths; `evals/results/<date>-m4-curation-run<N>/`; `evals/run.py --portal <pack>`.
- Produces: `tier = "curated"`, which `tests/test_tiers.py` accepts.

- [ ] **Step 1: [LIVE] Smoke.** The design names a "live smoke test" without defining it. *(Claude's call: the smoke test is the scoped drift run plus Chicago's compatibility case. The decisions row is in Step 8.)*
  - `uv run pytest --run-integration -m integration tests/test_drift.py -k data.cityofchicago.org --ignore=tests/test_curation_skill.py -rA`
  - `uv run pytest --run-integration -m integration "tests/test_compat_live.py::test_portal_compat[data.cityofchicago.org]" -rA`
  - Then `git restore src/opendata_atlas/portals/validation.json`.
  - Expected (ruling 83): every selected case is reported as **PASSED**. An `XFAIL`, `XPASS` or `SKIPPED` is not a pass. Read the saved compatibility outcome for Chicago and confirm each operation the smoke definition promises: search, describe, query, page 2 and one error. Copy the outcome into the promotion evidence.
  - A data limitation, a drift failure or an xfail is a stop-and-report. The pack cannot be hand-fixed, and accepting a limitation is the maintainer's call.
  - Identity verification: the curation transcript shows `atlas-profile` exited 0, which means catalog identity was verified (it exits 3 otherwise). Quote that line in the record.
- [ ] **Step 2: Re-grade the curator's runs (the gate).** Grade every answer in the agent's 3 preserved runs (`evals/results/<date>-m4-curation-run<N>/evals-{1,2,3}/`) against the **submitted** `evals/portals/<pack>.json`, on substance, as PASS, PARTIAL or FAIL. Record a table (task × run), the transcript paths, the revision evaluated (the run branch's commit), and every task where the reviewer's grade differs from the agent's. If any of the 3 runs is missing from the manifest, the gate cannot be met: stop and report.
- [ ] **Step 3: [PAID, background] Three fresh runs on the merged pack.**
  - Command: `cd /Users/bdc/projects/opendata-atlas-m4 && DATE=$(date +%F) && for n in 1 2 3; do uv run python evals/run.py --portal <pack> evals/results/$DATE-m4-chicago-$n; done`
  - Cap: enforced per session. The worst case is 3·T·$1; apply the cost gate and list the expected sessions first.
  - Expected: one transcript per task in each run, each ending `type: "result"`, `subtype: "success"`.
  - On failure: if a transcript has `api_error_status` set, re-run that one task once into `-m4-chicago-<n>-retry` and record it. Any other unhealthy transcript grades FAIL. Unresolved spend blocks further steps.
- [ ] **Step 4: Restriction check,** as in milestone 3. First check the instrument on its known positive, the synthetic connector init from Task 3 Step 5. Then confirm that each `system/init` lists only the five `mcp__opendata-atlas__atlas_*` tools and the one server, and that no `tool_use` names another tool.
- [ ] **Step 5: Grade the fresh runs** in the same way as Step 2, and record their cost.
- [ ] **Step 6: Apply the promotion rule** (ruling 58): every task PASS in at least 2 of 3 runs, and FAIL in at most 1.
  - **Met by Step 2 and by Step 5:** continue to the promotion.
  - **Not met (either set):** read each failure first as a knowledge gap, then as an engine bug (design, Per-portal eval tasks).
    - An engine bug goes to Task 4 (post-merge path), if an instance remains. On return, Steps 1, 3, 4, 5 and 6 repeat once, inside the cost gate. Step 2's re-grade stands, because the curator's runs cannot be re-made.
    - A knowledge gap needs a pack change: stop and report with the grades. Chicago stays `profiled` and the release waits.
  - Never edit an `expect` without a maintainer ruling.
- [ ] **Step 7: Promote.** Commit the record first: `test: record chicago promotion grades`. Then:
  - set `tier = "curated"` in `portal.toml`;
  - run `uv run pytest -q tests/test_tiers.py`, expecting PASS;
  - run the full gate;
  - run `atlas_get_reference {"topic": "portals", "item_id": "chicago"}`, expecting `isError: false` and tier `curated`.
- [ ] **Step 8: Decisions rows:** the promotion (the reviewer, the grades file, both rule-58 results) and the smoke-test definition *(Claude's call)*.
- [ ] **Step 9: Commit,** separately: `feat: promote data.cityofchicago.org to curated`.

---

### Task 8: Launch-scope evals with Chicago curated

**Files:**
- Modify: `evals/results/<date>-m4.md` (section "Launch scope"), `docs/design.md` (Evals: a milestone 4 run line), `docs/evidence/m4-costs.md`.

**Interfaces:**
- Consumes: the promoted pack; baseline `evals/results/2026-10-18-m3.md`, where 01, 03, 14 and 30 and the cross-portal tasks 25, 26, 28, 29 and 31 are PASS.
- Gate: as in milestone 3. A task graded below its baseline is re-run twice, and the gate fails only if the task grades below baseline in at least 2 of 3 runs.

- [ ] **Step 1: [PAID, background] Cross-portal and Seattle subset.**
  - Command: `cd /Users/bdc/projects/opendata-atlas-m4 && DATE=$(date +%F) && uv run python evals/run.py evals/results/$DATE-m4/cross && uv run python evals/run.py --portal seattle evals/results/$DATE-m4/seattle 01-cold-start 03-fire-capitol-hill 14-crime-capitol-hill 30-stale-claim`
  - Cap: enforced per session. The worst case is 9 × $1. Apply the cost gate, and list the expected sessions first.
  - Expected: 9 healthy transcripts.
  - On failure: re-run an unhealthy transcript once. If over the cap, stop and report.
- [ ] **Step 2: [PAID, background] Re-runs.** Only for tasks graded below baseline: each runs twice more, into `evals/results/<date>-m4-rerun1/` and `-rerun2/`, with the same command restricted to its task id. Worst case: 6 × $1. Expected: healthy transcripts.
- [ ] **Step 3: Restriction check,** as in Task 7 Step 4.
- [ ] **Step 4: Grade and record:** the table against the baseline, the cost, the gate result and a design Evals line.
  - **Gate fails:** read the failure as in Task 7 Step 6. An engine bug goes to Task 4 (post-merge path) if an instance remains, and the failing tasks are then re-run under this task's caps. Otherwise stop and report.
  - **Late changes (ruling 81):** any commit after this task's paid runs that changes behavior or served prose invalidates the affected evals. Re-run them within the cost gate, or stop and report.
  - Task 25 must show the agent querying Chicago (Review Focus 4).
- [ ] **Step 5: Commit** `test: record the milestone 4 launch-scope eval run`.

---

### Task 9: Docs reconciliation

**Files:**
- Modify: `docs/superpowers/plans/2026-10-19-m4-carryover.md`, `docs/design.md`, `docs/decisions.md`, `CHANGELOG.md`.
- Docs only. A behavior change here would invalidate Task 8's gates (ruling 81). If one is needed, stop and report.

- [ ] **Step 1: Reconcile.**
  - Design Launch scope: `chicago` reads curated, with the date, the pack directory `<pack>` and the evidence paths.
  - Design Milestones item 4: done, citing the merge and promotion commits.
  - Design Curation runbook: the milestone 4 run (portal, runs used, cost).
  - The carry-over gets a "Reconciled" header like milestone 3's. Each item ends **Done** (task and commit) or **Deferred** (decisions row):
    - the `pack_levels` fix: Task 1;
    - the paid-run rule: Deferred, for the maintainer to confirm;
    - the skill's first end-to-end run: Task 3;
    - the reviewer promotion: Task 7;
    - the `--strict-mcp-config` observation: Task 3 Step 5;
    - `curate/test-2026-10-18`: Deferred, the maintainer's call;
    - fixture identities: Deferred;
    - the token probe: Deferred;
    - PyPI: Deferred;
    - the prek pin: Deferred, bump at release;
    - the deferred minors: Task 6 Step 1.
  - Add decisions rows for each out-of-scope item in the Scope notes, and one row recording the Codex plan review and rulings 74–83.
  - Read CHANGELOG `## [Unreleased]` end to end: one line per user-visible change in this milestone.
  - `git worktree list` matches the run manifests: the main checkout, `$WT`, and any worktree a manifest lists as `kept_worktree`. Every `curate/chicago-run<N>` branch is kept and listed.
- [ ] **Step 2: Commit** `docs: reconcile milestone 4 carry-over`.

---

## Done criteria

- The gate is clean on `feat/chicago-curation`, and `tests/snapshots/tools_list.json` is unchanged unless a Task 4 instance names the change.
- `pack_levels` matches describe in the three carry-over cases. Seattle's levels are unchanged.
- One curation run's commit is merged with `--no-ff` after a recorded review. At most 3 runs and at most 2 engine-gap tasks were used. Every run has evidence under `docs/evidence/curation-chicago-*`, and its connector check is recorded.
- `data.cityofchicago.org` declares `curated` in its own commit. A reviewer who did not do the curation re-graded the curator's 3 preserved runs, and the 3 fresh runs, and both sets met ruling 58. `tests/test_tiers.py` passes.
- The launch-scope gate is met on the final code: no behavior change landed after the gates recorded it. The ledger total is at most $60, with no unresolved spend.
- Task 6's reviews are recorded, with no open Material finding. Every carry-over item is Done or has a decisions row.

**Next:** milestone 5, Release.
