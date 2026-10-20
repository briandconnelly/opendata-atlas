# Milestone 6 cost ledger

Cap: $100 for the milestone (global constraints, ruling 74). Every session is capped while it runs: curation at `--max-budget-usd 12`, each eval session at `--max-budget-usd 1`. Each paid step lists its expected sessions by transcript path before it runs (ruling 75), and records each session's `total_cost_usd` afterwards. A missing transcript, a transcript with no `result` event, or a result with no cost is unresolved spend.

## Running total

| Step | Worst case | Recorded |
| --- | --- | --- |
| Task 3 run 1 (Everett curation) | $36 gated (T = 6); $24 at the actual T = 3 | $3.3416 |
| Task 3 run 2 (Everett curation) | $39.34 gated cumulative (T = 6); $24 at the actual T = 3 | $4.3570 |
| Task 3 run 1 (King County curation) | $43.70 gated cumulative (T = 6); $28 at the actual T = 4 | $3.8078 |
| Task 7 Step 3 (Everett fresh eval runs) | $20.51 gated cumulative (3 x T = 3 x $1 = $9) | $1.0428 |
| Task 8 Step 2 (launch-scope evals) | $25.55 gated cumulative (13 x $1) | $1.8702 |
| Task 8 Step 3 (task 32 runs 2 and 3) | $16.42 gated cumulative (2 x $1) | $0.2739 |
| **Total** | $100 cap | **$14.6933** |

## Task 3 run 1: Everett curation (2026-10-19)

Gate before the run: $0.00 recorded + $36 worst case ($12 + 4 x 6 x $1) = $36, at most $100. N = 1, at most 3.

`<tmp>` is `<scratchpad>/m6/everett-run1/test_curation_skill_produces_a0`, the test's `tmp_path`.

Expected sessions:

- the curation session: `<tmp>/curation.transcript.jsonl` (cap $12);
- the agent's eval runs, one session per eval task (cap $1 each): `<tmp>/wt/.curation/evals-1/*.transcript.jsonl`, `<tmp>/wt/.curation/evals-2/*.transcript.jsonl`, `<tmp>/wt/.curation/evals-3/*.transcript.jsonl`;
- the test's eval run, one session per eval task (cap $1 each): `<tmp>/evals/*.transcript.jsonl`.

The eval task ids are not known until the agent writes `evals/portals/<pack>.json`; after the run, each glob is expanded against that file's task ids, and a task id with no transcript is unresolved spend.

Actual T = 3 (`01-delta-last-month`, `02-westmont-2024`, `03-restaurant-inspections`). The agent stopped under skill rule 8 before step 11.3, so it launched no eval sessions: its transcript shows only `evals/run.py --help`, and `.curation/evals-{1,2,3}` do not exist. The expected agent-eval sessions are therefore none, and the three test-eval sessions below are the whole list.

Recorded costs (cost check, `total_cost_usd` of each transcript's last `result` event; full list in `docs/evidence/curation-everett-2026-10-19-run1/costs.txt`):

| Sessions | Count | Cost |
| --- | --- | --- |
| curation session (`summary.json`: 72 turns) | 1 | $2.9315 |
| agent eval runs `.curation/evals-{1,2,3}` | 0 | $0.0000 |
| test eval run `<tmp>/evals` (01 $0.1824, 02 $0.1405, 03 $0.0873) | 3 | $0.4101 |
| **Run 1 total** | 4 | **$3.3416** |

Unresolved spend: none. Every listed transcript has a `result` event with `total_cost_usd`; `pgrep -fl "claude -p"` showed no session still running.

## Task 3 run 2: Everett curation (2026-10-19)

Gate before the run: $3.3416 recorded + $36 worst case ($12 + 4 x 6 x $1) = $39.34, at most $100. N = 2, at most 3.

`<tmp>` is `<scratchpad>/m6/everett-run2/test_curation_skill_produces_a0`, the test's `tmp_path`.

Expected sessions:

- the curation session: `<tmp>/curation.transcript.jsonl` (cap $12);
- the agent's eval runs, one session per eval task (cap $1 each): `<tmp>/wt/.curation/evals-1/*.transcript.jsonl`, `<tmp>/wt/.curation/evals-2/*.transcript.jsonl`, `<tmp>/wt/.curation/evals-3/*.transcript.jsonl`;
- the test's eval run, one session per eval task (cap $1 each): `<tmp>/evals/*.transcript.jsonl`.

The eval task ids are not known until the agent writes `evals/portals/<pack>.json`; after the run, each glob is expanded against that file's task ids, and a task id with no transcript is unresolved spend.

Actual T = 3 (`01-port-gardner-last-month`, `02-gang-crimes-2025`, `03-restaurant-inspections`). The agent ran its eval runs three times (`.curation/evals-{1,2,3}`, 9 sessions) and the test ran them once more (3 sessions).

Recorded costs (cost check, `total_cost_usd` of each transcript's last `result` event; full list in `docs/evidence/curation-everett-2026-10-19-run2/costs.txt`):

| Sessions | Count | Cost |
| --- | --- | --- |
| curation session (`summary.json`: 83 turns) | 1 | $2.9569 |
| agent eval runs `.curation/evals-{1,2,3}` | 9 | $1.0363 |
| test eval run `<tmp>/evals` (01 $0.1427, 02 $0.1224, 03 $0.0987) | 3 | $0.3638 |
| **Run 2 total** | 13 | **$4.3570** |

Milestone total after run 2: $3.3416 + $4.3570 = $7.6986.

Unresolved spend: none. Every listed transcript has a `result` event with `total_cost_usd`; `pgrep -fl "claude -p"` showed no session still running.

## Task 3 run 1: King County curation (2026-10-19)

Gate before the run: $7.6986 recorded + $36 worst case ($12 + 4 x 6 x $1) = $43.70, at most $100. N = 1, at most 3.

`<tmp>` is `<scratchpad>/m6/king-county-run1/test_curation_skill_produces_a0`, the test's `tmp_path`.

Expected sessions:

- the curation session: `<tmp>/curation.transcript.jsonl` (cap $12);
- the agent's eval runs, one session per eval task (cap $1 each): `<tmp>/wt/.curation/evals-1/*.transcript.jsonl`, `<tmp>/wt/.curation/evals-2/*.transcript.jsonl`, `<tmp>/wt/.curation/evals-3/*.transcript.jsonl`;
- the test's eval run, one session per eval task (cap $1 each): `<tmp>/evals/*.transcript.jsonl`.

The eval task ids are not known until the agent writes `evals/portals/<pack>.json`; after the run, each glob is expanded against that file's task ids, and a task id with no transcript is unresolved spend.

Actual T = 4 (`01-jail-bookings-last-month`, `02-still-in-custody`, `03-ld43-2012-republican-president`, `04-traffic-collisions`). The agent ran its eval runs three times (`.curation/evals-{1,2,3}`, 12 sessions) and the test ran them once more (4 sessions).

Recorded costs (cost check, `total_cost_usd` of each transcript's last `result` event; full list in `docs/evidence/curation-king-county-2026-10-19-run1/costs.txt`):

| Sessions | Count | Cost |
| --- | --- | --- |
| curation session (`summary.json`: 52 turns) | 1 | $1.7478 |
| agent eval runs `.curation/evals-{1,2,3}` | 12 | $1.5023 |
| test eval run `<tmp>/evals` (01 $0.1116, 02 $0.1656, 03 $0.1142, 04 $0.1663) | 4 | $0.5577 |
| **Run 1 total** | 17 | **$3.8078** |

Milestone total after King County run 1: $7.6986 + $3.8078 = $11.5064.

Unresolved spend: none. Every listed transcript has a `result` event with `total_cost_usd`; `pgrep -fl "claude -p"` showed no session still running.

## Task 7 Step 3: Everett fresh eval runs (2026-10-19)

Gate before the runs: $11.5064 recorded + $9 worst case (3 runs x T = 3 x $1) = $20.5064, at most $100.

Command (in the background): `cd /Users/bdc/projects/opendata-atlas-m6 && DATE=$(date +%F) && for n in 1 2 3; do uv run python evals/run.py --portal data.everettwa.gov evals/results/$DATE-m6-everett-$n; done`, with `date +%F` = 2026-10-19. Each session is capped at `--max-budget-usd 1`.

Expected sessions (one per eval task per run, cap $1 each):

- `evals/results/2026-10-19-m6-everett-1/01-port-gardner-last-month.transcript.jsonl`
- `evals/results/2026-10-19-m6-everett-1/02-gang-crimes-2025.transcript.jsonl`
- `evals/results/2026-10-19-m6-everett-1/03-restaurant-inspections.transcript.jsonl`
- `evals/results/2026-10-19-m6-everett-2/01-port-gardner-last-month.transcript.jsonl`
- `evals/results/2026-10-19-m6-everett-2/02-gang-crimes-2025.transcript.jsonl`
- `evals/results/2026-10-19-m6-everett-2/03-restaurant-inspections.transcript.jsonl`
- `evals/results/2026-10-19-m6-everett-3/01-port-gardner-last-month.transcript.jsonl`
- `evals/results/2026-10-19-m6-everett-3/02-gang-crimes-2025.transcript.jsonl`
- `evals/results/2026-10-19-m6-everett-3/03-restaurant-inspections.transcript.jsonl`

An `api_error_status` transcript is re-run once into `evals/results/2026-10-19-m6-everett-<n>-retry/` (one more $1 session each, inside the gate: $20.5064 + 9 x $1 = $29.51 at the very worst).

Actual: 9 sessions, all present, each ending `type: "result"`, `subtype: "success"`, `api_error_status` null, so no retry ran. Recorded costs (cost check, `total_cost_usd` of each transcript's last `result` event; full list in `docs/evidence/promotion-everett-2026-10-19/fresh-costs.txt`, whose first line is the instrument's known positive, a missing path reported `UNRESOLVED: missing`):

| Run | 01 | 02 | 03 | Cost |
| --- | --- | --- | --- | --- |
| `2026-10-19-m6-everett-1` | $0.1314 | $0.1099 | $0.1525 | $0.3938 |
| `2026-10-19-m6-everett-2` | $0.1277 | $0.1029 | $0.0934 | $0.3241 |
| `2026-10-19-m6-everett-3` | $0.1262 | $0.1134 | $0.0854 | $0.3250 |
| **Step 3 total** | | | | **$1.0428** |

Milestone total after Task 7 Step 3 (Everett): $11.5064 + $1.0428 = $12.5492.

Unresolved spend: none. Every listed transcript has a `result` event with `total_cost_usd`; `pgrep -fl "claude -p"` showed no session still running (instrument checked first: a background `sleep 30` showed in `pgrep -fl sleep`).

## Task 8 Step 2: launch-scope eval run (2026-10-19)

Gate before the run: $12.5492 recorded + $13 worst case (6 cross + 4 Seattle + 3 Chicago sessions x $1) = $25.5492, at most $100.

Command (in the background): `cd /Users/bdc/projects/opendata-atlas-m6 && DATE=$(date +%F) && uv run python evals/run.py evals/results/$DATE-m6/cross && uv run python evals/run.py --portal seattle evals/results/$DATE-m6/seattle 01-cold-start 03-fire-capitol-hill 14-crime-capitol-hill 30-stale-claim && uv run python evals/run.py --portal data.cityofchicago.org evals/results/$DATE-m6/chicago`, with `date +%F` = 2026-10-19. Each session is capped at `--max-budget-usd 1`.

Expected sessions (cap $1 each):

- `evals/results/2026-10-19-m6/cross/25-wrong-portal.transcript.jsonl`
- `evals/results/2026-10-19-m6/cross/26-ambiguous-place.transcript.jsonl`
- `evals/results/2026-10-19-m6/cross/28-generic-text-place.transcript.jsonl`
- `evals/results/2026-10-19-m6/cross/29-multi-zone.transcript.jsonl`
- `evals/results/2026-10-19-m6/cross/31-knowledge-gap-offer.transcript.jsonl`
- `evals/results/2026-10-19-m6/cross/32-city-data-at-county.transcript.jsonl`
- `evals/results/2026-10-19-m6/seattle/01-cold-start.transcript.jsonl`
- `evals/results/2026-10-19-m6/seattle/03-fire-capitol-hill.transcript.jsonl`
- `evals/results/2026-10-19-m6/seattle/14-crime-capitol-hill.transcript.jsonl`
- `evals/results/2026-10-19-m6/seattle/30-stale-claim.transcript.jsonl`
- `evals/results/2026-10-19-m6/chicago/01-hyde-park-last-month.transcript.jsonl`
- `evals/results/2026-10-19-m6/chicago/02-austin-2001-2003.transcript.jsonl`
- `evals/results/2026-10-19-m6/chicago/03-crimes-yesterday.transcript.jsonl`

An `api_error_status` transcript is re-run once, into `evals/results/2026-10-19-m6/<set>-retry/` (one more $1 session each, inside the gate: $25.5492 + 13 x $1 = $38.55 at the very worst).

Actual: 13 sessions, all present, each ending `type: "result"`, `subtype: "success"`, `api_error_status` null, so no retry ran. Recorded costs (cost check, `total_cost_usd` of each transcript's last `result` event; full list in `docs/evidence/launch-evals-m6-2026-10-19/costs.txt`, whose first line is the instrument's known positive, a missing path reported `UNRESOLVED: missing`):

| Set | Sessions | Cost |
| --- | --- | --- |
| cross (25 $0.1319, 26 $0.1193, 28 $0.1350, 29 $0.1157, 31 $0.1320, 32 $0.1628) | 6 | $0.7968 |
| seattle (01 $0.0810, 03 $0.1304, 14 $0.1852, 30 $0.1761) | 4 | $0.5726 |
| chicago (01 $0.1884, 02 $0.1558, 03 $0.1566) | 3 | $0.5008 |
| **Step 2 total** | 13 | **$1.8702** |

Milestone total after Task 8 Step 2: $12.5492 + $1.8702 = $14.4194.

Unresolved spend: none. Every listed transcript has a `result` event with `total_cost_usd`; `pgrep -fl "claude -p"` showed no session still running (instrument checked first: a background `sleep 30` showed in `pgrep -fl sleep`).

## Task 8 Step 3: task 32 runs 2 and 3 (2026-10-19)

No task graded below its baseline in Step 2, so no baseline re-run is due. Task 32 has no baseline, and Step 5 requires it to PASS in at least 2 of its runs, which one run cannot show; it alone runs twice more, inside Step 3's budget (at most 6 x $1).

Gate before the runs: $14.4194 recorded + $2 worst case (2 sessions x $1) = $16.4194, at most $100.

Command (in the background): `cd /Users/bdc/projects/opendata-atlas-m6 && DATE=$(date +%F) && uv run python evals/run.py evals/results/$DATE-m6-rerun1/cross 32-city-data-at-county && uv run python evals/run.py evals/results/$DATE-m6-rerun2/cross 32-city-data-at-county`, with `date +%F` = 2026-10-19. Each session is capped at `--max-budget-usd 1`.

Expected sessions (cap $1 each):

- `evals/results/2026-10-19-m6-rerun1/cross/32-city-data-at-county.transcript.jsonl`
- `evals/results/2026-10-19-m6-rerun2/cross/32-city-data-at-county.transcript.jsonl`

An `api_error_status` transcript is re-run once, into `evals/results/2026-10-19-m6-rerun<n>-retry/cross/` (one more $1 session each: $16.4194 + 2 x $1 = $18.42 at the very worst).

Actual: 2 sessions, both present, each ending `type: "result"`, `subtype: "success"`, `api_error_status` null, so no retry ran. Recorded costs (cost check; in `docs/evidence/launch-evals-m6-2026-10-19/costs.txt` after the Step 2 lines):

| Run | 32 |
| --- | --- |
| `2026-10-19-m6-rerun1/cross` | $0.1290 |
| `2026-10-19-m6-rerun2/cross` | $0.1449 |
| **Step 3 total** | **$0.2739** |

Milestone total after Task 8 Step 3: $14.4194 + $0.2739 = $14.6933.

Unresolved spend: none. Both transcripts have a `result` event with `total_cost_usd`; `pgrep -fl "claude -p"` showed no session still running.
