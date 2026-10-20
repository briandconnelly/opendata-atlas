# Release checklist

The maintainer's steps before and through the first release, `v0.1.0`. Milestone 5 built everything release-ready and published nothing; each step below is one the builders were not allowed to take, or a decision only the maintainer can make. Each step names who acts, what to run or decide, why, and where the result is recorded.

## Rules

- Work through the steps in order. Finish steps 1 to 10 before step 11: step 11 tags and publishes, and neither can be taken back.
- Record each outcome where its step says, in the same commit as any change it causes.
- Commit on the trunk: `docs/design` until step 5 creates `main`, then `main`.
- After step 5, push each new `main` commit (`git push origin main`) and wait for CI to pass on it before any step that needs it on GitHub: the TestPyPI rehearsal (step 11.5) and the tag (step 11.6). Push no branch but `main`.

## Branches

There is no remote and no `main` branch yet. The trunk is `docs/design` (the checkout at `~/projects/opendata-atlas`); milestone 5's work is on `feat/release-prep` until the maintainer merges it. `ci.yml` runs on pushes and pull requests to `main`, and the README's CI badge reads `branch=main`. `release.yml` runs on a pushed `v*` tag and on a manual run (`workflow_dispatch`), which uses the default branch unless given `--ref`.

## Steps

### 1. Try the server in Claude Desktop

- **Who:** maintainer.
- **Do:** follow README "Try it locally" in Claude Desktop twice: once with path (a)'s JSON snippet merged into `claude_desktop_config.json`, and once with path (c)'s bundle (`make mcpb`, then open `dist/opendata-atlas-0.1.0.mcpb`). In each, ask for something on Seattle's portal and confirm the five `atlas_*` tools answer.
- **If Desktop cannot find `uv`:** for the snippet, set `command` to the absolute path that `which uv` prints. The bundle's command is `uv` in `manifest.json` (`server.mcp_config`), and a user cannot edit it, so a bundle that fails this way needs a manifest fix before release.
- **Why:** Desktop's handling of the snippet and the bundle was never tested. Testing it would have changed the maintainer's Desktop configuration, which the builders were not allowed to touch. `scripts/smoke_test.py` starts the server the way the bundle does, but not inside Desktop.
- **Record:** a `docs/decisions.md` row "Claude Desktop trial"; a README fix if a path needed a workaround.

### 2. Decide the public history

- **Who:** maintainer.
- **Decide:** start `main` as a fresh history (one root commit holding `docs/design`'s tree), or as the existing history, kept on purpose. Step 5 carries out either.
- **Why:** commits before milestone 5 Task 1 (`301321f`) hold the people's names and emails that were later scrubbed from `tests/fixtures/http/`: 76 email occurrences and 247 name values. Every existing branch carries them. Count, never print:

  ```bash
  git log --all -p -- tests/fixtures | grep -cE '^\+.*@seattle\.gov'
  ```

  It prints 76. Without `^\+` it prints 152, because the scrub commit's removed lines match too.

  Those commits, and every commit before the milestone 5 final-review fixes, also hold Socrata account ids (21 distinct at `87e1664`), which resolve to public profiles that show a name (row "Fixture account ids (milestone 5 final review, ruling 95)"). The fresh history drops them too; a kept history keeps them.
- **Record:** `docs/decisions.md` row "Inherited fixture identities (milestone 4 carry-over)".

### 3. Probe token portability

- **Who:** maintainer, or any session that has a Socrata app token ([how to get one](https://dev.socrata.com/docs/app-tokens.html)).
- **Do:**

  ```bash
  SOCRATA_APP_TOKEN=... uv run python scripts/feasibility/check_token.py data.seattle.gov data.cityofchicago.org data.everettwa.gov
  ```

  Name every host to probe, at least the curated portals above. The script probes only the hosts it is given, and without a token it prints `token: unavailable` and exits 0.
- **Why:** whether one token is honored on every portal is unprobed (no token was available in milestones 0 to 5). `SOCRATA_APP_TOKENS` (a host-to-token map) waits on the result.
- **Record:** `docs/upstream-facts.md`, and a new "Token probe" row in `docs/decisions.md` that closes the milestone 4 carry-over row.

### 4. Decide how to hold the PyPI name

- **Who:** maintainer.
- **Decide:** whether to hold `opendata-atlas` on PyPI before step 11, or accept that the name can be taken until step 11's first upload creates the project.
- **Why:** an index search on 2026-10-17 found no collision, but only registration proves the name is free (design Constraints, Name). Reviewer-reported, not probed here: PyPI has no reservation other than a first upload, and the *pending* trusted publisher that step 5.6 adds does not hold the name. The builders do not hold the account.
- **Record:** design Constraints (Name).

### 5. Create `main` and the GitHub repository

- **Who:** maintainer, after step 2.
- **Do:**
  1. Merge the milestone into the trunk, if that has not been done: `git -C ~/projects/opendata-atlas merge feat/release-prep` (run where `docs/design` is checked out; on 2026-10-19 it fast-forwards).
  2. Create `main` by step 2's route.
     - **Fresh history.** `docs/design` is checked out in `~/projects/opendata-atlas`, so make a clean worktree and start an orphan branch there:

       ```bash
       git -C ~/projects/opendata-atlas worktree add --detach ~/projects/opendata-atlas-main docs/design
       cd ~/projects/opendata-atlas-main
       git checkout --orphan main docs/design
       git commit -m "chore: start the public history from docs/design"
       ```

       Check it before pushing: `git rev-list --count main` prints 1, `git rev-parse main^{tree}` equals `git rev-parse docs/design^{tree}`, and `git log -p main -- tests/fixtures | grep -cE '^\+.*@seattle\.gov'` prints 0. Work in this worktree from now on.
     - **Kept history.** In `~/projects/opendata-atlas`, where `docs/design` is checked out, create `main` and check it out, so later commits land on it:

       ```bash
       cd ~/projects/opendata-atlas
       git branch main docs/design
       git switch main
       ```

       `git branch --show-current` prints `main`. The step 2 count, run on `main` alone (`git log -p main -- tests/fixtures | grep -cE '^\+.*@seattle\.gov'`), prints 76. Work in this checkout from now on.
  3. Create the repository and add it as `origin`, pushing nothing. Run it in the checkout that has `main` checked out (`~/projects/opendata-atlas-main` for a fresh history, `~/projects/opendata-atlas` for a kept one): `gh repo create briandconnelly/opendata-atlas --public --source . --remote origin`. Without `--push`, `gh` pushes nothing; with `--push` it pushes local commits, so leave it off. The equivalent by hand is creating the empty repository on GitHub, then `git remote add origin git@github.com:briandconnelly/opendata-atlas.git`.
  4. Push `main` alone: `git push -u origin main`. Never `--all` or `--mirror`: the other branches hold the old history.
  5. Confirm on GitHub that `main` is the default branch and that CI ran and passed on the pushed commit (`gh run list --branch main`).
  6. In the repository settings, create the environments `pypi` and `testpypi`, each with a required reviewer. `release.yml` names both.
  7. On PyPI and on TestPyPI, add a pending trusted publisher for project `opendata-atlas`, repository `briandconnelly/opendata-atlas`, workflow `release.yml`, with environment `pypi` or `testpypi` to match.
- **Why:** the design assumes `github.com/briandconnelly/opendata-atlas` with network-enabled CI, and the release workflow publishes only through trusted publishing behind an approval.
- **Record:** design Constraints (the repository line).

### 6. Confirm the paid-run rule

- **Who:** maintainer.
- **Decide:** keep, change or drop the paid-run rule in `AGENTS.md` ("Start a paid run ... only when the maintainer asks").
- **Why:** Claude wrote it after a stray `--help` started paid eval sessions (ruling 71), and it is still marked *Claude's call; maintainer to confirm*.
- **Record:** `docs/decisions.md` row "Paid-run rule in `AGENTS.md` (ruling 71)".

### 7. Rule on the ruling 88 grade

- **Who:** maintainer.
- **Decide:** whether the two fresh task-03 answers that say yesterday will "probably" be near 600-650 deserve PASS (ruling 88) or PARTIAL.
- **Also confirm:** the controller's ruling that task 32 is graded PASS on substance (row "Task 32 graded on substance (milestone 6)").
- **Where the answers are:** `evals/results/2026-10-19-m4.md`, cited in the `docs/decisions.md` row "Chicago promoted to `curated`".
- **If both are PARTIAL:** the fresh set fails ruling 58, and Chicago's promotion is reverted before release, in one commit on `main`:
  1. `git revert --no-commit ef2e9bf` (it sets Chicago's `tier` back to `profiled`).
  2. In `README.md`'s status line, name Seattle and Everett: "Two portals are curated: Seattle (`seattle`) and City of Everett (`everett`)." `tests/test_readme.py` (`test_readme_names_the_curated_portals`) fails until it matches the registry's tiers.
  3. In `CHANGELOG.md` under `## [Unreleased]`, change the Chicago pack entry to say it ships `profiled`, and why.
  4. Run the gate (`uv run pytest -q`, `uv run ruff check`, `uv run ruff format --check`, `uv run ty check`, `uv run prek run --all-files`), then `git commit`.
- One flip still meets ruling 58.
- **Why:** the grade is borderline, and Chicago ships `curated` on it.
- **Record:** `docs/decisions.md` row "Chicago pack knowledge gaps for a future curation" (**For the maintainer**); after a revert, also `README.md` and `CHANGELOG.md`, in the revert commit.

### 8. Decide the seattle-open-data back-ports

- **Who:** maintainer.
- **Decide:** for each candidate, port it to seattle-open-data, open a `port` issue there, or leave it.
- **Why:** design Constraints say a fix in either repository gets an issue in the other. On 2026-10-19 seattle-open-data had no commit after the fork revision `26c6628`, so nothing came the other way (row "Port comparison (milestone 5)"). These went from opendata-atlas toward it, each checked missing there with a grep that finds it here. The fixture row is inverted: its grep finds identities, so 0 here and 20 there is the feature missing there.

  | Candidate | Here | Check | Here / there |
  | --- | --- | --- | --- |
  | Eval runner restricts the agent's tools (`--tools ""`) | `evals/run.py` | 1 | 1 / 0 |
  | Per-session `--max-budget-usd` (ruling 74) | `evals/run.py` | 2 | 2 / 0 |
  | Strict argument parsing; `--help` launches nothing (ruling 55) | `evals/run.py` | 3 | 2 / 0 |
  | No `logging` capability or UI extension advertised | `src/opendata_atlas/mcp/server.py` | 4 | 4 / 0 |
  | Fixture identity scrub and guard (milestone 5 Task 1 and final review) | `scripts/scrub_fixtures.py`, `tests/test_fixture_identities.py` | 5 | 0 / 20 files |
  | `source.now_weekday` (milestone 5 Task 2) | `src/opendata_atlas/` | 6 | 3 / 0 files |

  Run each check from the seattle-open-data checkout for "there" and from this checkout for "here". Here, check 4 reads `src/opendata_atlas/mcp/server.py` instead. On 2026-10-19 each printed the count in the table, in both checkouts.

  ```sh
  grep -c '"--tools"' evals/run.py                                                # 1
  grep -c max-budget evals/run.py                                                 # 2
  grep -c -e 'def parse_args' -e '"--help"' evals/run.py                          # 3
  grep -c -e logging/setLevel -e UI_EXTENSION src/seattle_open_data/mcp/server.py # 4
  grep -rlE '@seattle\.gov' tests/fixtures | wc -l                                # 5
  grep -rl --include='*.py' now_weekday src | wc -l                               # 6
  ```

  Not candidates: the minified icon (seattle-open-data serves no SVG icon) and the describe place-phase budget (not shipped, ruling 93).
- **Record:** a `port` issue per ported item in seattle-open-data, or a line in the "Port comparison (milestone 5)" row. seattle-open-data has no `port` label yet (reviewer-probed); create it first: `gh label create port --repo briandconnelly/seattle-open-data --description "Fix to port between seattle-open-data and opendata-atlas"`.

### 9. Bump prek's ruff pin

- **Who:** maintainer or a builder.
- **Do:** set `rev` for `ruff-pre-commit` in `prek.toml` from `v0.17.0` to `v` plus the version `uv run ruff --version` prints (0.17.1 on 2026-10-19), then run `uv run prek run --all-files`.
- **Why:** the old pin missed a RUF007 that `uv run ruff check` caught; the gate runs both until the pins agree (carry-over 4).
- **Record:** the commit message. It is not a user-visible change, so it needs no CHANGELOG line.

### 10. Delete or keep `curate/test-2026-10-18`

- **Who:** maintainer.
- **Decide:** delete the branch (`git branch -D curate/test-2026-10-18`; it is unmerged, so `-d` refuses) or keep it.
- **Why:** it holds the Honolulu pack (`c1acae5`), declared `curated` before ruling 64. It was evidence that the curation skill works, not a pack to ship (carry-over 2). A kept branch stays local: the Rules push `main` alone.
- **Record:** `docs/decisions.md` row "Milestone 4 carry-over reconciliation", item 2.

### 11. Release

- **Who:** maintainer.
- **Do:** follow `docs/releasing.md` in order:
  1. `uv run pytest --run-integration -m integration`, the drift run; commit the regenerated `src/opendata_atlas/portals/validation.json`.
  2. `uv run pytest tests/test_release_gate.py`; it must pass.
  3. `uv run python scripts/rehearse_release.py --apply --date <YYYY-MM-DD>`, then commit the cut CHANGELOG.
  4. Push `main` (`git push origin main`), carrying every commit made since step 5.4 pushed it; `git log --oneline origin/main..main` lists them, for example the records of steps 5 to 10 and the 11.1 and 11.3 commits. Wait for CI to pass on the pushed cut commit.
  5. Rehearse on TestPyPI from the pushed `main`: `gh workflow run release.yml --ref main -f publish_to=testpypi`, approve the `testpypi` deployment, and wait for it to pass. A run before the cut fails the version check (`docs/releasing.md`, Context), so this is the first useful rehearsal.
  6. Last, tag the pushed cut commit and push only the tag: `git tag v0.1.0 origin/main`, then `git push origin v0.1.0`.
  7. Approve the `pypi` environment's deployment when the release workflow asks.
- **Why:** the workflow checks that `pyproject.toml`, `manifest.json`, the CHANGELOG's first version heading and the tag agree, and publishes only after approval.
- **Record:** the tag, the GitHub Release, and the cut `CHANGELOG.md`.

### 12. After the release

- **Who:** maintainer or a builder.
- **Do:** remove "after the first release" from the README's Install section, and confirm `uvx opendata-atlas` and the Release's `.mcpb` work.
- **Record:** `CHANGELOG.md` under `## [Unreleased]`. The step 11.3 cut renamed that heading, so first re-add `## [Unreleased]` above `## [0.1.0] - <date>`.
