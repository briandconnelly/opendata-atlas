# opendata-atlas Milestone 6: Findable Portals, Everett and King County — Implementation Plan

> **Status: complete.** Historical plan, kept for provenance; do not execute it. Current design: [docs/design.md](../../design.md).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**
- Give every registry portal whose own site has a usable title a name taken from that title, so that `atlas_find_portals {"query": "Everett"}` finds `data.everettwa.gov`.
- Take `data.everettwa.gov` and `data.kingcounty.gov` from `generic` to `curated` through the front door, as milestone 4 did for Chicago.

**Architecture:**
- **Task 1** adds a deterministic `title_name` rule to the dev-only registry build. It runs offline, test-first.
- **Task 2** runs the build live with titles for every portal, and has every generated name reviewed. It also writes the Everett and King County overrides (aliases, place names, jurisdiction, timezone), which the curation skill moves into each pack.
- **Tasks 3–7** repeat milestone 4's front-door loop once per portal: curation run, engine-gap template, pack review and merge, standards review, independent promotion. Everett goes first, then King County.
- **Task 8** adds one cross-portal eval for the Seattle and King County overlap, then re-runs the launch-scope evals.
- **Task 9** reconciles the docs.

The matcher (`core/portals.py`) does not change, and nor does `tools/list`.

**Tech Stack:** Python ≥3.13, uv, FastMCP 4 on MCP SDK v2, pytest; `claude -p` (Claude Code) for the curation runs and evals; git worktrees.

**Spec:** `docs/design.md`, in these sections:
- Registry (step 4, "Generated metadata", which this milestone changes);
- Portal model, Identity;
- Launch scope;
- Curation runbook;
- Per-portal eval tasks;
- Knowledge levels ("Who can review", ruling 64);
- Contribution path (promotion rule, ruling 58);
- Evals.

Precedent: `docs/superpowers/plans/2026-10-19-m4-chicago-curation.md`; its rulings 74–83 bind here unchanged. Also read `AGENTS.md`, `docs/decisions.md`, `skills/curate-portal/SKILL.md`, `CONTRIBUTING-portals.md`, `tests/test_curation_skill.py` and `evals/run.py`.

**Scope notes:**
- **Why this milestone exists.** The maintainer asked for Everett's portal and was told there was no data for Everett. This was probed on 2026-10-19:
  - `data.everettwa.gov` is in the shipped registry, named only by its host. So are 193 other portals, `data.kingcounty.gov` among them.
  - `atlas_find_portals` returns nothing for "Everett" or "Everett, WA". It matches "everett wa" only because, with the space removed, that equals the host label `everettwa`.
  - `atlas_search_datasets {"portal": "data.everettwa.gov", "query": "permits"}` works.
- **Rejected alternatives** (Task 1 records them in a decisions row, *Claude's call*):
  - **Catalog `resource.attribution` as a fallback name source.** Probed on 7 title-less portals: it is empty on 6, and on `data.coloradosprings.gov` 2 of 16 results carry a person's name and job title.
  - **Matching a host label with its US-state suffix removed** (`kirklandwa` → `kirkland`). Simulated over the 95 portals with no usable title: 38 would gain a key, and some keys are junk (`capecor`, `cityofnam`, `va-c`). Single-word labels such as `atlanta` and `washoe` already match.
- **Out of scope** (Task 9 records each as a decisions row):
  - place names or a jurisdiction for portals with no override;
  - re-curating Honolulu or Chicago;
  - the milestone 5 release items: token, PyPI, ruling 96, publishing.
- **Base:** `docs/design` HEAD (`ab615d4`, plus the commit that adds this plan). Work on `feat/more-portals` in the worktree `/Users/bdc/projects/opendata-atlas-m6`, called `$WT` below. Never switch branches in `/Users/bdc/projects/opendata-atlas`. The repo has no remote: never push.
- **Step labels and placeholders:**
  - Paid steps are marked **[PAID, background]**, and live free steps **[LIVE]**.
  - `<scratchpad>` is the executing session's scratchpad, as an absolute path.
  - `<date>` is `date +%F` at the step's start.
  - `<slug>` is `everett` or `king-county`.
  - `<portal id>` is `data.everettwa.gov` or `data.kingcounty.gov`.
  - `<pack>` is the pack directory the run produced (`summary.json` `pack`; by default the canonical id).
  - `<N>` is the run number for that portal, 1–3.

## Global Constraints

- **Gate for every task:** `uv run pytest -q`, `uv run ruff check`, `uv run ruff format --check`, `uv run ty check` and `uv run prek run --all-files`. prek pins ruff v0.17.0, so the gate keeps both linters.
- **Commits:**
  - Use Conventional Commits.
  - Each commit message ends with a blank line, then `🤖 Generated with Claude Code`, then `Claude-Session: https://claude.ai/code/session_01CH7uTSKtTjy4NoHCYKFHyx` on the next line.
  - Never commit to `docs/design` or `main`.
  - Never push.
  - Never rewrite history: no rebase, no amend of a merged commit, no `reset --hard` on a branch with commits, no force.
- **Paid runs** (AGENTS.md):
  - The maintainer's approval of this plan is the request.
  - Only steps marked [PAID] start one, and each runs with `run_in_background`.
  - Set `ATLAS_RUN_CURATION` only in Task 3's run step.
  - `--help` is the only allowed probe of a paid command.
- **Milestone cap: $100.** Every session is capped while it runs (ruling 74):
  - a curation session runs with `--max-budget-usd 12`;
  - an eval session runs with `--max-budget-usd 1`. Both are already pinned by `tests/test_curation_env.py` and `tests/test_evals.py`.
- **Worst case per paid step.** Each paid step states its worst case: the number of sessions times the per-session cap. T is the number of tasks in that portal's eval file, or 6, the skill's maximum, before the file exists.

  | Step | Worst case | At T = 4 |
  | --- | --- | --- |
  | Task 3, one curation run (per portal) | $12 + 4·T·$1 | $28 |
  | Task 7 Step 3, 3 fresh runs (per portal) | 3·T·$1 | $12 |
  | Task 8 Steps 2–3 (6 cross + 4 Seattle + 4 Chicago, then up to 6 re-runs) | 20·$1 | $20 |

  - At T = 4, one run per portal totals $100 at worst.
  - Before each paid step, the **recorded** ledger total plus that step's worst case must be at most $100; otherwise stop and report.
  - Milestone 4's real cost was $9.28 for one portal.
- **No free unknowns (ruling 75).**
  - Before a paid step runs, `docs/evidence/m6-costs.md` lists every expected session by its transcript path.
  - Afterwards, each listed session needs a recorded `total_cost_usd`. A missing transcript, a transcript with no `result` event, or a result with no `total_cost_usd` is **unresolved spend**. It blocks every further paid step until resolved.
  - Resolve it from the session's stderr. If no cost is found there, record the full per-session cap.
  - Before resolving or retrying, check that no child is running with `pgrep -fl "claude -p"`. Check that instrument first: a background `sleep 30 &` must show up in `pgrep -fl sleep`.
- **Cost check:** this prints each transcript's cost, or `UNRESOLVED` and the reason:

  ```
  cd /Users/bdc/projects/opendata-atlas-m6 && uv run python -c 'import sys; from pathlib import Path; from tests.test_curation_skill import result_event
  for t in sys.argv[1:]:
      p = Path(t); r = result_event(p) if p.exists() else None
      c = r.get("total_cost_usd") if r else None
      print(t, c if c is not None else "UNRESOLVED: " + ("missing" if r is None else "no result" if not r else "no cost"))' TRANSCRIPT ...
  ```
- **Never force (ruling 77).** Never run `git worktree remove --force`, `git branch -D` or `git clean`.
  - Before removing a worktree, `git -C <wt> status --porcelain --untracked-files=all` (ignoring `.curation/`, `.venv/` and `__pycache__/`) and `git -C <wt> stash list` must both print nothing.
  - Only then run a plain `git worktree remove <wt>`.
  - A worktree with unique work is kept, and its path goes in the run's manifest.
- **Front door:**
  - A pack's contents come only from that portal's curation commit: `src/opendata_atlas/portals/<pack>/`, `evals/portals/<pack>.json`, and the agent's `validation.json` and `registry_overrides.toml` changes. Nobody hand-edits them.
  - One exception: Task 7's promotion commit changes the `tier` line, plus the README status line that `tests/test_readme.py` ties to it.
- **Facts:** never report an upstream fact that was not probed. Label reviewer-reported facts `(review)` in `docs/upstream-facts.md`.
- **Personal data:** none in committed evidence, packs or PR text.
  - The scan: `grep -rnE '[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z.]{2,}|\(?[0-9]{3}\)?[-. ][0-9]{3}[-. ][0-9]{4}' PATHS`.
  - Known positive, run first: the same command on `docs/evidence/scrub-known-positive/` must list a match. Task 2 Step 1 creates that file, because milestone 5 scrubbed `tests/fixtures/http/`.
  - Names cannot be grepped, so read for them.
- **`validation.json`:** after any drift run other than the curating agent's, run `git restore src/opendata_atlas/portals/validation.json`.
- **Docs:** when a design choice changes, update `docs/design.md` and add a `docs/decisions.md` row in the task that makes the choice. Every user-visible change gets a CHANGELOG line under `## [Unreleased]`, which is 0.1.0's open section.
- **Parity:**
  - `pack_levels(SEATTLE_CONTEXT, today=date(2026, 10, 18))` stays as `tests/test_freshness.py::test_pack_levels_seattle_unchanged` pins it.
  - Chicago stays `curated`.
  - `tests/snapshots/tools_list.json` does not change. A snapshot diff is a defect unless a Task 4 instance names it.
- **Prose standard:** the implementer audits every agent-consumed prose surface the task changes with `separating-context-from-constraints`, and lists the findings in the task report.

## Review Focus

1. **Finding the new portals by place.**
   - Expected: `atlas_find_portals` returns `data.everettwa.gov` first for "Everett", "Everett, WA" and `everett`, and `data.kingcounty.gov` first for "King County", "King County, WA" and `king-county`.
   - Pinned before curation by `test_shipped_registry_finds_everett_and_king_county` (Task 2), and after the merge by `test_<slug>_alias_survives_the_pack` (Task 5).
2. **Seattle and King County stay apart.**
   - Expected: "Seattle" returns `data.seattle.gov` and not `data.kingcounty.gov`, and "King County" does not return `data.seattle.gov`. A Seattle question that only King County's portal can answer says so rather than silently switching portals.
   - Pinned by `test_seattle_and_king_county_do_not_cross_match` (Task 2). Eval task 32 checks the agent's behavior (Task 8).
3. **A vendor default or generic title never becomes a name.**
   - Otherwise "open data" or "Tyler" would match about 150 portals by name, ahead of every place-name match.
   - Expected: no shipped name, casefolded, is in `GENERIC_TITLES`, and none equals its own host.
   - Pinned by `test_generated_names_skip_generic_parts` (Task 1) and `test_shipped_names_are_not_generic` (Task 2).
4. **The no-argument listing within budget after names get longer.**
   - Expected: `atlas_find_portals {}` returns `isError: false`, with curated portals first: Seattle, Chicago, and then Everett and King County once promoted.
   - Checked in Task 2 Step 6 and Task 7 Step 7.
5. **Hand-written names survive a rebuild.**
   - Expected: an override's `name`, and a pack's identity, beat the generated name.
   - Pinned by `test_override_name_beats_title_name` (Task 1).

---

## File Structure

```
scripts/build_registry.py                       # title_name, apply_title_names, --titles all       (Task 1)
tests/test_registry.py                          # rule tests; shipped-registry pins; alias pins      (Tasks 1, 2, 5)
src/opendata_atlas/portals/registry.json        # rebuilt                                            (Task 2)
src/opendata_atlas/portals/registry_overrides.toml  # Everett, King County; any rejected names       (Task 2)
docs/evidence/registry-2026-10-18/titles.json   # every portal's title (the cache; dated per record) (Task 2)
docs/evidence/registry-names-<date>/review.md   # the generated-name review                          (Task 2)
src/opendata_atlas/portals/<pack>/, evals/portals/<pack>.json  # curation commits only; tier line  (Tasks 5, 7)
docs/evidence/m6-costs.md                       # cost ledger                                        (Task 3 on)
docs/evidence/curation-<slug>-<date>-run<N>/    # manifest, summary, diffstat, init check           (Task 3)
docs/reviews/<date>-m6-<slug>-pack.md           # pack reviews                                       (Task 5)
docs/evidence/promotion-<slug>-<date>/          # smoke and re-grade                                 (Task 7)
evals/tasks.json                                # task 32                                            (Task 8)
evals/results/<date>-m6.md                      # grades                                             (Tasks 7, 8)
README.md, docs/design.md, docs/decisions.md, CHANGELOG.md                                          (as needed)
```

---

### Task 1: Generated names from site titles

**Files:**
- Modify: `scripts/build_registry.py` (new functions near `fetch_title`; `main` where titles are read, around lines 592–612; `--titles` argument; module docstring).
- Test: `tests/test_registry.py` (through the module's `br` loader).
- Modify: `docs/design.md` (Registry step 4), `docs/decisions.md`, `CHANGELOG.md`.

**Interfaces:**
- Produces:
  - `GENERIC_TITLES: frozenset[str]`;
  - `title_name(record: dict[str, Any], host: str) -> str | None`;
  - `apply_title_names(entries: dict[str, RegistryEntry], titles: dict[str, dict[str, Any]]) -> dict[str, RegistryEntry]`;
  - `--titles` accepts a positive integer or `all`.
- Task 2 runs the build with `--titles all`.

**The rule** (exact, from the 2026-10-19 probe of all 242 portals):
- **Fields:** read `html_title`, `site_title` and `site_company`, in that order. Collapse whitespace in each, then split it on ` | ` and on ` - `, ` – ` and ` — ` (a separator surrounded by whitespace).
- **Candidates:** a part is a candidate unless it is empty, or its casefold is in `GENERIC_TITLES`, or its casefold equals `host`, or it repeats an earlier candidate.
- `GENERIC_TITLES = {"catalog", "data", "data portal", "home", "open data", "open data portal", "performance management", "rally", "socrata", "socrata data cloud", "this site has moved", "tyler data & insights", "tyler technologies"}`.
- **Choice:** take the first candidate that matches `GOV` (case-insensitive); otherwise the first candidate; with no candidate, return `None`. The pattern is:

  ```
  GOV = ^(?:(?:city|town|village|county|state|commonwealth|city and county|district) of \S.*|.*\S county|.*, [A-Z]{2})$
  ```

- **Applying it:** `apply_title_names` replaces `identity.name` only when the title gives a name. It runs before `merge_overrides`, so an override's `name` wins, and pack identities still go on top.

- [ ] **Step 1: Worktree.**
  - `git -C /Users/bdc/projects/opendata-atlas worktree add /Users/bdc/projects/opendata-atlas-m6 -b feat/more-portals docs/design`
  - `cd /Users/bdc/projects/opendata-atlas-m6 && uv sync && uv run pytest -q`.
  - Expected: the suite passes on the base.
- [ ] **Step 2: Failing tests.** The records are copied from live titles on 2026-10-19.

```python
EVERETT = {"site_title": "Tyler Data & Insights", "site_company": "Tyler Data & Insights",
           "html_title": "City of Everett Open Data"}
KING = {"site_title": "King County | Open Data", "site_company": "King County",
        "html_title": "King County | Open Data"}
NOLA = {"site_title": "Data.NOLA.gov | Enabling New Orleans", "site_company": "Data.NOLA.gov",
        "html_title": "Home - DataDriven - City of New Orleans"}
MO = {"site_title": "data.mo.gov | State of Missouri Data Portal", "site_company": "data.mo.gov",
      "html_title": "Catalog | data.mo.gov | State of Missouri Data Portal"}
VENDOR = {"site_title": "Tyler Data & Insights", "site_company": "Tyler Data & Insights",
          "html_title": "Catalog | Tyler Data & Insights"}
MOVED = {"site_title": None, "site_company": None, "html_title": "This site has moved"}
ALBANY = {"site_title": "Tyler Data & Insights", "site_company": "Tyler Data & Insights",
          "html_title": "Catalog | City of Albany"}

def test_title_name_takes_the_sites_own_name():
    assert br.title_name(EVERETT, "data.everettwa.gov") == "City of Everett Open Data"
    assert br.title_name(KING, "data.kingcounty.gov") == "King County"
    assert br.title_name(ALBANY, "albany.data.socrata.com") == "City of Albany"

def test_title_name_prefers_a_government_name():
    assert br.title_name(NOLA, "data.nola.gov") == "City of New Orleans"

def test_generated_names_skip_generic_parts():
    assert br.title_name(MO, "data.mo.gov") == "State of Missouri Data Portal"
    assert br.title_name(VENDOR, "kirklandwa.data.socrata.com") is None
    assert br.title_name(MOVED, "opendata.fcgov.com") is None
    assert br.title_name({}, "x.data.socrata.com") is None

def test_override_name_beats_title_name():
    # build one enumerated entry (as test_override_updates_enumerated_entry_and_keeps_counts does),
    # apply_title_names with EVERETT, then merge_overrides with {"<id>": {"name": "Everett"}}
    assert merged["<id>"].identity.name == "Everett"
    # without the override, the title name stands, and counts are kept
    assert titled["<id>"].identity.name == "City of Everett Open Data"

def test_titles_all_is_accepted():
    # parse the --titles argument through main's parser helper: "all" and "5" are accepted; "0" and "x" exit 2
```

  For `test_titles_all_is_accepted`, factor the argument parser out of `main` as `build_parser() -> argparse.ArgumentParser`, so the test calls `br.build_parser().parse_args([...])`.
- [ ] **Step 3: Run them.** `uv run pytest tests/test_registry.py -k "title" -v`. Expected: FAIL, with `AttributeError` on `title_name`.
- [ ] **Step 4: Implement** the rule and `apply_title_names`.
  - In `main`, call `apply_title_names` before both `merge_overrides` calls. `--titles all` fetches the titles of every entry, and cached records in `titles.json` are reused as today.
  - Update the module docstring (step 4, and the `--titles` line).
- [ ] **Step 5: Run them and the gate.** Expected: PASS. `registry.json` is not regenerated in this task, so `git status` shows no change to it.
- [ ] **Step 6: Docs.**
  - Restate design Registry step 4:
    - `name` comes from the portal's own site title by the rule above, else the host;
    - `place_names`, `jurisdiction` and `timezone` still come only from overrides;
    - an override's `name` wins.
  - Add a decisions row, "Registry names from site titles (milestone 6)". It records the rule, the probe counts (99 of 194 unnamed portals get a name, 95 do not) and both rejected alternatives with their evidence (Scope notes). Mark it *Claude's call*.
  - Add a CHANGELOG `### Changed` line: "`atlas_find_portals` finds about 100 more portals by the name on their own site (e.g. "Everett")."
- [ ] **Step 7: Commit** `feat: name registry portals from their own site titles`.

---

### Task 2: [LIVE] Rebuild the registry, review the names, add Everett and King County

**Files:**
- Modify: `src/opendata_atlas/portals/registry.json`, `docs/evidence/registry-2026-10-18/titles.json` (and any other cache file the build rewrites), `src/opendata_atlas/portals/registry_overrides.toml`.
- Create: `docs/evidence/registry-names-<date>/review.md`, `docs/evidence/scrub-known-positive/positive.txt`.
- Test: `tests/test_registry.py`, `tests/test_find_portals.py`.
- Modify: `docs/decisions.md`, `CHANGELOG.md`.

**Interfaces:**
- Consumes: Task 1's rule and `--titles all`.
- Produces: shipped names, plus registry entries for `data.everettwa.gov` (alias `everett`) and `data.kingcounty.gov` (alias `king-county`) with place names, jurisdiction and timezone. Task 3's skill step 4 copies these into each pack.

- [ ] **Step 1: Known positive for the personal-data scan.** Write `docs/evidence/scrub-known-positive/positive.txt` with one line: `known positive: someone@example.org (555) 555-0100`. Expected: the scan lists both matches. Commit it with this task.
- [ ] **Step 2: Snapshot the current registry.** `cp src/opendata_atlas/portals/registry.json <scratchpad>/m6/registry-before.json`.
- [ ] **Step 3: [LIVE] Build.**
  - Command: `uv run python scripts/build_registry.py --out src/opendata_atlas/portals/registry.json --evidence docs/evidence/registry-2026-10-18/ --titles all 2>&1 | tee <scratchpad>/m6/build.log`. Use `run_in_background`, because about 180 titles at 2 requests each, 0.2 s apart, take several minutes.
  - The cached enumeration and probes are reused, with no `--refresh`. *(Claude's call: this keeps the diff to names. A re-enumeration is a separate registry refresh.)*
  - Expected: exit 0, and `titles.json` holds a record for every entry.
- [ ] **Step 4: Diff check.** Compare the two files by id.
  - Expected: the same set of ids, and every changed field is `identity.name`, apart from `version`.
  - Any other change, such as an entry added or dropped, a `catalog_query` or a count (for example from a retried probe), is listed in `review.md` with its cause from `build.log`.
  - Stop and report if an entry was dropped, or if a curated or pack entry changed.
- [ ] **Step 5: Review every generated name.** Write `review.md` as a table with these columns:
  - `id`;
  - the title fields;
  - the generated name;
  - verdict: **ok**, **reject**, or **rename** with the replacement, which must be a part of that portal's own title.

  A name is rejected when it would mislead `find_portals`: when it names a vendor or another organization's product rather than the portal's owner (Socrata's "Making Data Social" on `healthdata.nj.gov` is the expected first case), or when it is the site's move notice. Each reject or rename becomes a `registry_overrides.toml` entry in the header's style:
  - a comment quoting `titles.json`;
  - `name =`, with the host itself for a reject.

  Re-run the build, which reuses the cache, and repeat Step 4.
- [ ] **Step 6: Everett and King County overrides.** Read their records in `titles.json` first. Add both in the header's style (compare `["open.piercecountywa.gov"]`):

```toml
# N. titles.json["data.everettwa.gov"]: site_title="Tyler Data & Insights", site_company="Tyler Data & Insights", html_title="City of Everett Open Data"
# aliases and place names for curation (milestone 6); region from host everettwa.gov
# source: country US: geography (the named place lies there), not the title; region WA: host everettwa.gov
["data.everettwa.gov"]
name = "City of Everett"
aliases = ["everett"]
place_names = ["Everett", "Everett, WA"]
jurisdiction = { level = "city", country = "US", region = "WA" }
timezone = "America/Los_Angeles"

# N. titles.json["data.kingcounty.gov"]: site_title="King County | Open Data", site_company="King County", html_title="King County | Open Data"
# aliases and place names for curation (milestone 6)
# source: country US, region WA: geography (the named place lies there), not the title
["data.kingcounty.gov"]
name = "King County"
aliases = ["king-county"]
place_names = ["King County", "King County, WA"]
jurisdiction = { level = "county", country = "US", region = "WA" }
timezone = "America/Los_Angeles"
```

  - Update the header's coverage sentence. Aliases are now given to Chicago (milestone 2) and to Everett and King County (milestone 6, for curation).
  - Never add "Seattle" to King County's place names (Review Focus 2).
  - Re-run the build and repeat Step 4. The two entries now differ in these fields, as intended.
- [ ] **Step 7: Pins.** Add these tests:
  - `test_shipped_registry_finds_everett_and_king_county` (`tests/test_find_portals.py`, on the shipped registry): Review Focus 1's six queries each return the named portal first.
  - `test_seattle_and_king_county_do_not_cross_match`: "Seattle" candidates exclude `data.kingcounty.gov`, and "King County" candidates exclude `data.seattle.gov`.
  - `test_shipped_names_are_not_generic` (`tests/test_registry.py`): for every shipped entry, `name.casefold() not in br.GENERIC_TITLES`, and the name equals its host only when `br.title_name` of its `titles.json` record is `None`, or when an override sets it.
  - Run each against a known positive first:
    - a tmp registry copy in which Everett's `place_names` and alias are removed makes the first test fail on "Everett, WA";
    - a copy in which one name is set to `Tyler Data & Insights` makes the third test fail.

  Run these checks once and do not commit them.
- [ ] **Step 8: [LIVE] Surface checks** through the in-process client (SKILL.md, Context: Tool calls):
  - `atlas_find_portals {}`: `isError: false`, with `data.seattle.gov` and `data.cityofchicago.org` first;
  - `atlas_find_portals {"query": "Everett"}`;
  - `atlas_search_datasets {"portal": "everett", "query": "permits"}`: non-empty `datasets`.

  Record the outputs, trimmed, in `review.md`.
- [ ] **Step 9: Gate, docs, commit.**
  - Run the full gate. Expected: `tools_list.json` is unchanged.
  - Add a decisions row, "Registry rebuilt with title names (milestone 6)": the counts from `review.md`, the rejects, the two new overrides and their aliases (*Claude's call*: `king-county`, because `king` is ambiguous). Add the CHANGELOG line for the aliases.
  - Run the personal-data scan over `docs/evidence/registry-names-<date>/` and `titles.json`, known positive first.
  - Commit `feat: rebuild the registry with title names and add everett and king county`.

---

### Task 3: Curation run `<slug>` `<N>`

Runs first as (`everett`, 1). After Everett's pack is merged (Task 5), it runs as (`king-county`, 1). A portal runs again only when Task 4 or Step 7 sends it back, and never past N = 3 for that portal.

**Files:**
- Create: `docs/evidence/m6-costs.md` (on the first run), and `docs/evidence/curation-<slug>-<date>-run<N>/` holding `summary.json`, `manifest.json`, `diffstat.txt`, `init-check.json` and `costs.txt`.
- Local only (git-ignored): `evals/results/<date>-m6-<slug>-run<N>/`, a copy of the agent's `.curation/evals-1..3`.

**Interfaces:**
- Consumes: `feat/more-portals` HEAD, committed. The test branches from `ROOT`'s HEAD.
- Produces: branch `curate/<slug>-run<N>` holding the agent's commit, and `summary.json` with `pack`, `portal_id`, `declared_tier`, `base`, `failures` and `curation.final_message`.
- **Test facts** (`tests/test_curation_skill.py`):
  - the test runs `git worktree add <tmp_path>/wt -b curate/test-<date.today()> HEAD` and never removes it;
  - `<tmp_path>` is `<basetemp>/test_curation_skill_produces_a0`;
  - the transcript is `<tmp_path>/curation.transcript.jsonl`, and the test's own eval run is `<tmp_path>/evals/`;
  - the agent's runs are `<tmp_path>/wt/.curation/evals-{1,2,3}/`;
  - a timeout writes no `summary.json`, but the test first prints `worktree <wt> on <branch> at <base>`;
  - both portals may run on the same day, so Step 8's rename must free `curate/test-<date>` before the second run.

- [ ] **Step 1: Free pre-checks.**
  - `git status --short` in `$WT`. Expected: empty.
  - `test ! -e src/opendata_atlas/portals/<portal id>`. If it exists, the pack is merged: see Task 4's post-merge path.
  - `git branch --list curate/test-<date>`. Expected: empty.
  - `uv run pytest --run-integration -m integration tests/test_curation_skill.py`. Expected: `1 skipped`.
  - Apply the cost gate at T = 6, and the check N ≤ 3.
  - Write the expected-session list to the ledger: the curation transcript, plus `.curation/evals-{1,2,3}/*.transcript.jsonl` and `evals/*.transcript.jsonl` for each eval task.
- [ ] **Step 2: [PAID, background] Curation run.**
  - Command: `cd /Users/bdc/projects/opendata-atlas-m6 && DATE=$(date +%F) && ATLAS_RUN_CURATION=1 ATLAS_CURATION_PORTAL=<portal id> ATLAS_CURATION_EVIDENCE=/Users/bdc/projects/opendata-atlas-m6/docs/evidence/curation-<slug>-$DATE-run<N> uv run pytest --run-integration -m integration tests/test_curation_skill.py -v -s --basetemp=<scratchpad>/m6/<slug>-run<N> 2>&1 | tee <scratchpad>/m6/<slug>-run<N>.log`
  - Worst case: $12 + 4·T·$1.
  - Expected: `1 passed`, and `summary.json` with `failures: []`, `declared_tier: "profiled"` and `portal_id: "<portal id>"`.
  - Steps 3–6 always run, whatever the outcome.
- [ ] **Step 3: Recovery manifest (ruling 78).** Write it unconditionally, before anything else, as milestone 4 did: `run`, `base`, `branch`, `worktree`, `transcript`, `pytest_exit`, `artifacts` (each `present` or `missing`) and `kept_worktree`.
- [ ] **Step 4: Record the cost.** Run the cost check over every listed transcript, then write `costs.txt` and the ledger. Any `UNRESOLVED` line blocks further paid steps (ruling 75).
- [ ] **Step 5: Connector check.**
  - First run it on two known inputs:
    - known negative: `/Users/bdc/projects/opendata-atlas/evals/results/2026-10-18-m3/cross/25-wrong-portal.transcript.jsonl` (git-ignored, so present only in the main checkout) must pass, with `mcp_servers` naming only `opendata-atlas`;
    - known positive: `docs/evidence/launch-evals-2026-10-19/known-positive-connector-init.jsonl` must FAIL.
  - Then run it on the curation transcript and save the output as `init-check.json`. Expected: one init event, empty `mcp_servers`, no `mcp__` tool, and no `claude.ai` or `claude_ai` anywhere in it.
  - The check:

  ```
  uv run python -c 'import json, sys
  inits = [e for e in map(json.loads, open(sys.argv[1])) if e.get("type") == "system" and e.get("subtype") == "init"]
  assert len(inits) == 1, f"{len(inits)} init events"
  e = inits[0]; tools = [t for t in e.get("tools", []) if t.startswith("mcp__")]
  print(json.dumps({"mcp_servers": e.get("mcp_servers"), "mcp_tools": tools}))
  bad = [s for s in (e.get("mcp_servers") or []) if s.get("name") != "opendata-atlas"] + [t for t in tools if not t.startswith("mcp__opendata-atlas__")]
  assert not bad and "claude_ai" not in json.dumps(e) and "claude.ai" not in json.dumps(e), bad' TRANSCRIPT
  ```

  - On failure: add a decisions row, then stop and report.
- [ ] **Step 6: Keep the evidence.**
  - Copy each present `.curation/evals-<n>` into `evals/results/<date>-m6-<slug>-run<N>/`, and check that the transcripts arrived.
  - Write `diffstat.txt` with `git diff --stat <base> <branch>`.
  - Never copy `.curation/report.json`.
  - Run the personal-data scan over the evidence directory, known positive first.
- [ ] **Step 7: Classify the outcome and pick the next task.**

  | outcome | next |
  | --- | --- |
  | `1 passed`, and no rule-8 stop in the PR body | Task 5 for this portal |
  | the PR body or a new decisions row names an engine gap (skill rule 8) | Task 4, pre-merge path, if fewer than 2 instances have run in this milestone; else stop and report |
  | infrastructure: an API error, `api_error_status`, a budget stop, or a timeout with no gap named | Task 3 again, if N < 3 and the cost gate allows; else stop and report |
  | a failure the skill forbids: the path rule, a tier above `profiled`, a failing check, or personal data | Task 3 again once, if N < 3. The same failure twice is a skill defect: stop and report |
  | the connector check failed | stop and report |
- [ ] **Step 8: Free the branch name.**
  - Run the never-force check on `<tmp_path>/wt`. If it is clean, remove the worktree with `git -C $WT worktree remove <tmp_path>/wt`. Otherwise keep it and record it in `kept_worktree`.
  - Then `git -C $WT branch -m curate/test-<date> curate/<slug>-run<N>`.
  - Expected: `git log --oneline -1 curate/<slug>-run<N>` shows the agent's commit. Never delete a run branch.
- [ ] **Step 9: Commit** the evidence and the ledger: `test: record <slug> curation run <N>`.

---

### Task 4: Engine gap `<k>` (template; at most 2 instances in this milestone, across both portals)

Use milestone 4's Task 4 procedure unchanged (`docs/superpowers/plans/2026-10-19-m4-chicago-curation.md`, "Task 4: Engine gap"), with these substitutions:
- `$WT` is `/Users/bdc/projects/opendata-atlas-m6`;
- evidence goes in `docs/evidence/engine-gap-<k>-<date>/`;
- the decisions-row topic is "Engine gap <k> from <slug> curation (<short name>)".

The procedure, in order:
1. reproduce, saving `repro.txt` with personal data removed;
2. write a failing offline test, named for the behavior, in the owning module's test file;
3. run it and confirm it fails;
4. apply the smallest engine fix, never touching pack files;
5. run the test and the gate, and confirm Seattle and Chicago parity;
6. write the decisions row (and a CHANGELOG line or design change if one applies);
7. commit `fix: <behavior>`, gated by its own task reviewer;
8. return. **Pre-merge** (this portal's pack is absent): go to Task 3 with N + 1. **Post-merge:** never re-run curation. Go back to the step that found the gap, with `-postfix<k>` evidence directories. Any paid gate recorded on code the fix changed is re-run (ruling 81). A fix to an engine path Chicago or Seattle exercises also invalidates their launch evals, which Task 8 re-runs.

A third gap stops the milestone: report to the maintainer.

---

### Task 5: Review the `<slug>` pack and merge it

The reviewer is a fresh agent that never ran Task 3. It reviews `curate/<slug>-run<N>` from the last Task 3 run that routed here.

**Files:**
- Create: `docs/reviews/<date>-m6-<slug>-pack.md`.
- Modify by merge: the agent's commit.
- Test: `tests/test_registry.py`.
- Modify: `docs/decisions.md`, `CHANGELOG.md`, `docs/design.md` (Curation runbook).

**Interfaces:**
- Consumes: the run branch, `summary.json`, `path_violations(paths, pack)` and `claim_summary(pack_dir)`.
- Produces: the merge commit, which Task 7 evaluates.

- [ ] **Step 1: Review worktree.** `git -C $WT worktree add <scratchpad>/m6/review-<slug>-run<N> curate/<slug>-run<N>`.
- [ ] **Step 2: Mechanical checks.** Run each on its known positive (in brackets) first:
  - **Path rule:** `git diff --name-only <base> HEAD` through `path_violations` gives `[]`. [A list with `README.md` returns it.]
  - **Evidence:** every claim whose interpretation sets `reliability` has a non-empty `reason`, and evidence of kind `soql_probe`, `metadata_probe` or `document`. Every reviewed claim has `reviewed_by = "claude"`. [A tmp copy with one `reason` deleted is reported.]
  - **Personal data:** the scan over the pack, the eval file and the PR body, then a read of every sample value, guide and `expect` for names. [`docs/evidence/scrub-known-positive/`.]
  - **Identity:**
    - `tier = "profiled"`;
    - the alias (`everett` or `king-county`), place names, jurisdiction and `timezone = "America/Los_Angeles"` match Task 2's override;
    - `jurisdiction` carries the rule-21 comment (page URL and quoted passage), or the override's comment carried over;
    - the override table is gone from `registry_overrides.toml`.
  - **Eval file:**
    - the four `covers` kinds are present;
    - no `misleading_field` prompt names its column or its dataset;
    - when more than one dataset is reviewed, the tasks span at least 2;
    - every `expect` states PASS, PARTIAL and FAIL.
  - **Guides:** `checks.guide_examples.exit_code == 0`, `examples` is non-empty and every item has `is_error: false`, and each guide's prose agrees with the claims it cites.
  - **Shared-file isolation (ruling 82):** in `registry_overrides.toml`, only this portal's table may change or go; in `validation.json`, only `portals["<portal id>"]` may differ. [A tmp copy with a Seattle `outcome` changed is reported.]
- [ ] **Step 3: Offline gate in the review worktree.** `uv run pytest -q tests/test_packs.py tests/test_tiers.py tests/test_release_gate.py tests/test_find_portals.py`. Expected: exit 0. Review Focus 1–2 must still hold with the identity in the pack.
- [ ] **Step 4: [LIVE] checks**, in process:
  - `atlas_find_portals {"query": "<place>"}` has `<portal id>` first;
  - for each dataset `pack_levels` returns, describe's `knowledge.level` equals `pack_levels(...)[id]` at `freshness.today()`;
  - `atlas_get_reference {"topic": "portals", "item_id": "<slug>"}` returns `isError: false`, with tier `profiled`.

  A level mismatch is an engine gap (Task 4).
- [ ] **Step 5: Record the review** in `$WT`, never in the review worktree.
  - Include each check with its known positive and result, the findings marked Material or Minor, the agent's own eval grades, and the paths of the preserved eval transcripts.
  - Commit it before the merge (ruling 79): `docs: record the <slug> pack review`.
  - A Material finding blocks the merge. An engine gap goes to Task 4, pre-merge path; agent variance goes to Task 3 again (N < 3); anything else, stop and report.
  - Then remove the review worktree, after the never-force check.
- [ ] **Step 6: Merge**, in `$WT`:

```bash
cd /Users/bdc/projects/opendata-atlas-m6
git status --short                                        # expect: empty
git merge-base --is-ancestor <base> feat/more-portals     # expect: exit 0
git log --oneline feat/more-portals..curate/<slug>-run<N> # expect: the agent's commit(s) only
git merge --no-ff curate/<slug>-run<N> \
  -m "feat: merge the <portal id> knowledge pack (curation run <N>)" \
  -m "🤖 Generated with Claude Code
Claude-Session: https://claude.ai/code/session_01CH7uTSKtTjy4NoHCYKFHyx"
```

  On a conflict in `docs/decisions.md` only, keep both sets of rows and commit with `--no-edit`. On any other conflict, run `git merge --abort` and stop and report.
- [ ] **Step 7: Verify.**
  - Run the full gate.
  - `git diff curate/<slug>-run<N> HEAD -- src/opendata_atlas/portals/<pack> evals/portals/<pack>.json` is empty.
- [ ] **Step 8: Pin the alias.** Add `test_<slug with _>_alias_survives_the_pack` next to `test_chicago_alias_survives_the_pack`: `by_alias("<slug>")` resolves to `<portal id>`, with timezone `America/Los_Angeles`. Show the known positive (a tmp pack copy without `aliases` returns `None`) once, and do not commit it.
- [ ] **Step 9: Docs.**
  - Add a design Curation runbook line for the merge.
  - Add a decisions row.
  - Add a CHANGELOG `### Added` line: "The `<portal id>` (alias `<slug>`) knowledge pack, curated through the curate-portal skill."
- [ ] **Step 10: Commit** `test: pin the <slug> alias`. Then go to Task 3 for King County, or to Task 6 once both are merged.

---

### Task 6: Standards review and fixes (after both merges, before the final paid gates)

**Files:** Create `docs/reviews/<date>-m6-standards.md`. Fix whatever it finds. Pack files never change.

- [ ] **Step 1: `agent-friendly-mcp`, focused route** on the served-surface change: registry names in `atlas_find_portals` results and in topic `portals` (§2, §8 and §9), plus any Task 4 change.
  - Read `[1.spec-revision]` and the native-vs-convention rule first.
  - Read the touched sections in full, and close over the rule ids they cite.
  - Report every other section as `not-checked`.
- [ ] **Step 2: `separating-context-from-constraints`** R1–R5 on the changed prose: the design's Registry step 4 and Curation runbook, the overrides header, and `SKILL.md` or CONTRIBUTING if they changed.
- [ ] **Step 3: Fix** every Material finding, giving a behavior finding a failing-first test. Fix or list the Minors.
  - A skill defect a run exposed is fixed in `SKILL.md` and traced against the run's transcript. It is not re-run in this milestone.
  - A fix to `core/query.py`, `core/describe.py`, `portals/knowledge.py` or notice text lands here, before Task 7 (ruling 81).
- [ ] **Step 4: Commit** `docs: record the milestone 6 standards review`, plus a `fix:` commit for each behavior fix.

---

### Task 7: Independent promotion of `<slug>` to `curated`

This runs once per portal, Everett first. The reviewer is not the curating agent (ruling 64). **The gate is the reviewer's re-grade of the curator's 3 preserved runs** (ruling 80). The 3 fresh runs can block promotion, but they never replace the re-grade.

**Files:**
- Create: `docs/evidence/promotion-<slug>-<date>/`.
- Modify: `evals/results/<date>-m6.md` (section "<slug> promotion").
- Modify, in their own commit: `src/opendata_atlas/portals/<pack>/portal.toml` (the `tier` line only) and `README.md` (the status line's curated list).
- Modify: `docs/decisions.md`.

- [ ] **Step 1: [LIVE] Smoke.** This is milestone 4's definition: the drift run scoped to the portal, plus its compatibility case.
  - `uv run pytest --run-integration -m integration tests/test_drift.py -k <portal id> --ignore=tests/test_curation_skill.py -rA`
  - `uv run pytest --run-integration -m integration "tests/test_compat_live.py::test_portal_compat[<portal id>]" -rA`
  - Then `git restore src/opendata_atlas/portals/validation.json`.
  - `data.kingcounty.gov` is already in `tests/test_compat_live.py` `SAMPLE`, but `data.everettwa.gov` is not. For Everett, first append it to `SAMPLE` and commit `test: add everett to the live compatibility sample`.
  - Expected: every selected case is **PASSED** (ruling 83).
  - Quote `atlas-profile` exit 0 from the curation transcript as the identity verification.
- [ ] **Step 2: Re-grade the curator's runs (the gate).**
  - Grade every answer in `evals/results/<date>-m6-<slug>-run<N>/evals-{1,2,3}/` against the submitted eval file, as PASS, PARTIAL or FAIL.
  - Record a task × run table, the transcript paths, the revision, and every grade that differs from the agent's.
  - If any run is missing, stop and report.
- [ ] **Step 3: [PAID, background] Three fresh runs.**
  - Command: `cd $WT && DATE=$(date +%F) && for n in 1 2 3; do uv run python evals/run.py --portal <pack> evals/results/$DATE-m6-<slug>-$n; done`
  - Worst case: 3·T·$1. Apply the cost gate, and list the sessions first.
  - An `api_error_status` transcript is re-run once, into `-retry`. Any other unhealthy transcript is graded FAIL.
- [ ] **Step 4: Restriction check,** with the known-positive connector init first. Each `system/init` must list only the five `mcp__opendata-atlas__atlas_*` tools and one server, and no `tool_use` may name another tool.
- [ ] **Step 5: Grade the fresh runs** as in Step 2, and record their cost.
- [ ] **Step 6: Promotion rule (ruling 58).** Every task must be PASS in at least 2 of 3 runs, and FAIL in at most 1. Ruling 88 applies: a borderline task survives one flip and fails only if both doubtful runs are PARTIAL.
  - Met by both Step 2 and Step 5: promote.
  - Otherwise, read each failure first as a knowledge gap, then as an engine bug:
    - an engine bug goes to Task 4, post-merge path; on return, repeat Steps 1 and 3–6 once, inside the cost gate;
    - a knowledge gap means the portal stays `profiled`. Record the grades and continue with the other portal; this milestone does not wait on it.
  - Never edit an `expect` without a maintainer ruling.
- [ ] **Step 7: Promote.**
  - Commit the record first: `test: record <slug> promotion grades`.
  - Then set `tier = "curated"`, and add `<Name> (`<slug>`)` to the README status line's curated list.
  - Run `uv run pytest -q tests/test_tiers.py tests/test_readme.py` (expect PASS), then the full gate.
  - `atlas_get_reference {"topic": "portals", "item_id": "<slug>"}` returns tier `curated`, and `atlas_find_portals {}` lists it among the curated portals.
- [ ] **Step 8: Decisions row** for the promotion: the reviewer, the grades file, and both rule-58 results.
- [ ] **Step 9: Commit,** separately: `feat: promote <portal id> to curated`.

---

### Task 8: Seattle and King County eval, then launch-scope evals

**Files:**
- Modify: `evals/tasks.json` (task 32), `evals/results/<date>-m6.md` (section "Launch scope"), `docs/design.md` (Evals: a milestone 6 run line), `docs/evidence/m6-costs.md`.

- [ ] **Step 1: [LIVE] Probe, then write task 32.**
  - Search King County's catalog in process for a dataset that covers Seattle and that `data.seattle.gov` does not publish. The first candidate to check is restaurant or food-establishment inspections: `atlas_search_datasets` on both portals.
  - **If one exists:** task `32-city-data-at-county`, with the user's question about Seattle that only that dataset answers. Its `expect`:
    - PASS: says Seattle's portal does not publish it and uses King County's, stating that the data is county-wide and filtered to Seattle;
    - PARTIAL: uses King County without saying so;
    - FAIL: says no data exists, or invents a number.
  - **If none exists:** task `32-county-not-city`, "How many <a King County dataset's subject> were reported in King County last month?". Its `expect`:
    - PASS: uses `data.kingcounty.gov`, or asks;
    - FAIL: silently uses Seattle's portal.
  - Record the probe in the results file. The new task must validate under `tests/test_evals.py`.
  - Commit `test: add the seattle and king county eval task`.
- [ ] **Step 2: [PAID, background] Launch scope.**
  - Command: `cd $WT && DATE=$(date +%F) && uv run python evals/run.py evals/results/$DATE-m6/cross && uv run python evals/run.py --portal seattle evals/results/$DATE-m6/seattle 01-cold-start 03-fire-capitol-hill 14-crime-capitol-hill 30-stale-claim && uv run python evals/run.py --portal data.cityofchicago.org evals/results/$DATE-m6/chicago`
  - Worst case: (6 + 4 + Chicago's T) × $1. Apply the cost gate, and list the sessions first.
- [ ] **Step 3: [PAID, background] Re-runs,** only for tasks graded below baseline: each runs twice more, into `-rerun1/` and `-rerun2/`. The worst case is 6 × $1 in total.
- [ ] **Step 4: Restriction check,** as in Task 7 Step 4.
- [ ] **Step 5: Grade and record.**
  - The baselines are `evals/results/2026-10-18-m3.md` and the milestone 4 launch run (`docs/evidence/launch-evals-2026-10-19/`); task 32 is new and has no baseline.
  - The gate: a task fails only if it grades below baseline in at least 2 of 3 runs.
  - Task 32 must PASS in at least 2 of its runs; otherwise read it as Task 7 Step 6 does.
  - Late changes invalidate the affected evals (ruling 81).
- [ ] **Step 6: Commit** `test: record the milestone 6 launch-scope eval run`.

---

### Task 9: Docs reconciliation

Docs only. A behavior change here would invalidate Task 8 (ruling 81): if one is needed, stop and report.

- [ ] **Step 1: Reconcile.**
  - **Design Launch scope:** each new portal's status, with its pack directory and evidence paths. "Every other registered portal: generic" stays true of the rest.
  - **Design Milestones:** add item 6, "More portals", marked done, citing the merges and promotions.
  - **Design Curation runbook:** the milestone 6 runs (portal, runs used, cost).
  - **Design Evals:** the run line.
  - **Decisions:** add rows for each out-of-scope item in the Scope notes, and one row for the plan and its rulings.
  - **CHANGELOG:** read `## [Unreleased]` end to end; there is one line per user-visible change.
  - **Git state:** `git worktree list` matches the manifests, and every `curate/<slug>-run<N>` branch is kept and listed.
- [ ] **Step 2: Commit** `docs: reconcile milestone 6`.

---

## Done criteria

- **Gate:** clean on `feat/more-portals`. `tools_list.json` is unchanged unless a Task 4 instance names the change. Seattle parity holds, and Chicago is still `curated`.
- **Registry names:** every shipped portal whose title gives a usable name carries it, and none carries a generic name. `review.md` records every generated name with a verdict. "Everett", "Everett, WA", "King County" and "King County, WA" each find their portal first, and Seattle and King County do not cross-match.
- **Packs:** each portal's pack came from one curation commit, merged with `--no-ff` after a recorded review. At most 3 runs per portal and at most 2 engine-gap tasks in total were used.
- **Promotion:** each portal is either `curated`, in its own commit after a recorded independent re-grade and fresh runs that both met ruling 58, or `profiled`, with the grades recorded and its gaps in a decisions row.
- **Evals:** the launch-scope gate, task 32 included, is met on the final code.
- **Spend:** the ledger total is at most $100, with no unresolved spend.
- **Records:** Task 6's reviews are recorded, with no open Material finding.

**Next:** back to the milestone 5 release checklist (`docs/release-checklist.md`), when the maintainer is ready.
