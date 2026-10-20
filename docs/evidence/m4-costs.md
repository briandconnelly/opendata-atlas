# Milestone 4 cost ledger

Cap: $60 for the milestone (global constraints, ruling 74). Every session is capped while it runs: curation at `--max-budget-usd 12`, each eval session at `--max-budget-usd 1`. Each paid step lists its expected sessions by transcript path before it runs (ruling 75), and records each session's `total_cost_usd` afterwards. A missing transcript, a transcript with no `result` event, or a result with no cost is unresolved spend.

## Running total

| Step | Worst case | Recorded |
| --- | --- | --- |
| Task 3 run 1 (Chicago curation) | $36 gated (T = 6); $24 at the actual T = 3 | $6.48 |
| Task 7 Step 3 (3 fresh Chicago eval runs) | $9 (T = 3) | $1.52 |
| Task 8 Step 1 (launch-scope evals, 9 sessions) | $9 | $1.28 |
| Task 8 Step 2 (re-runs) | $6 | not run: no task below baseline |
| **Total** | $60 cap | **$9.28** |

## Task 3 run 1: Chicago curation (2026-10-19)

Gate before the run: $0.00 recorded + $36 worst case ($12 + 4 × 6 × $1) = $36, at most $60. N = 1, at most 3.

`<tmp>` is `<scratchpad>/m4/run1/test_curation_skill_produces_a0`, the test's `tmp_path`.

Expected sessions:

- the curation session: `<tmp>/curation.transcript.jsonl` (cap $12);
- the agent's eval runs, one session per eval task (cap $1 each): `<tmp>/wt/.curation/evals-1/*.transcript.jsonl`, `<tmp>/wt/.curation/evals-2/*.transcript.jsonl`, `<tmp>/wt/.curation/evals-3/*.transcript.jsonl`;
- the test's eval run, one session per eval task (cap $1 each): `<tmp>/evals/*.transcript.jsonl`.

The eval task ids are not known until the agent writes `evals/portals/<pack>.json`; after the run, each glob is expanded against that file's task ids, and a task id with no transcript is unresolved spend.

Each glob expanded to the eval file's 3 task ids (`01-hyde-park-last-month`, `02-austin-2001-2003`, `03-crimes-yesterday`): 13 sessions in all. The curation transcript shows 9 eval launches (3 runs × 3 tasks, each once) plus one free `--help`, so no transcript was overwritten.

Recorded costs (cost check, `total_cost_usd` of each transcript's last `result` event; full list in `docs/evidence/curation-chicago-2026-10-19-run1/costs.txt`):

| Sessions | Count | Cost |
| --- | --- | --- |
| curation session (`summary.json`: `total_cost_usd` 4.2813, `num_turns` 105) | 1 | $4.2813 |
| agent eval runs `.curation/evals-{1,2,3}` | 9 | $1.6760 |
| test eval run `<tmp>/evals` | 3 | $0.5216 |
| **Run 1 total** | 13 | **$6.4789** |

Unresolved spend: none. Every expected transcript has a `result` event with `total_cost_usd`; `pgrep -fl "claude -p"` showed no session still running.

## Task 7 Step 3: three fresh Chicago eval runs (2026-10-19)

Gate before the run: $6.48 recorded + $9 worst case (3 runs × T = 3 tasks × $1) = $15.48, at most $60.

Command (the brief's, verbatim): `cd <worktree> && DATE=$(date +%F) && for n in 1 2 3; do uv run python evals/run.py --portal data.cityofchicago.org evals/results/$DATE-m4-chicago-$n; done`

Expected sessions (cap $1 each), 9 in all, `<n>` in 1, 2, 3:

- `evals/results/2026-10-19-m4-chicago-<n>/01-hyde-park-last-month.transcript.jsonl`
- `evals/results/2026-10-19-m4-chicago-<n>/02-austin-2001-2003.transcript.jsonl`
- `evals/results/2026-10-19-m4-chicago-<n>/03-crimes-yesterday.transcript.jsonl`

Recorded costs (cost check, `total_cost_usd` of each transcript's last `result` event; the check first printed `UNRESOLVED: missing` for a path that does not exist):

| Run | 01-hyde-park-last-month | 02-austin-2001-2003 | 03-crimes-yesterday | Run total |
| --- | --- | --- | --- | --- |
| 1 | $0.1800 | $0.1966 | $0.1624 | $0.5390 |
| 2 | $0.1932 | $0.1833 | $0.1423 | $0.5188 |
| 3 | $0.1238 | $0.1903 | $0.1495 | $0.4635 |
| **Step total** | | | | **$1.5214** |

Every transcript ends with a `result` event, `subtype: "success"`, `api_error_status` null; no retry was needed. Unresolved spend: none. `pgrep -fl "claude -p"` found no session still running (the instrument first showed a background `sleep 30`).

## Task 8 Step 1: launch-scope evals, cross-portal and Seattle subset (2026-10-19)

Gate before the run: $8.00 recorded + $9 worst case (9 sessions × $1) = $17, at most $60. With Step 2's worst case ($6) added, $23, also at most $60.

Command (the brief's, verbatim): `cd <worktree> && DATE=$(date +%F) && uv run python evals/run.py evals/results/$DATE-m4/cross && uv run python evals/run.py --portal seattle evals/results/$DATE-m4/seattle 01-cold-start 03-fire-capitol-hill 14-crime-capitol-hill 30-stale-claim`

Expected sessions (cap $1 each), 9 in all:

- `evals/results/2026-10-19-m4/cross/25-wrong-portal.transcript.jsonl`
- `evals/results/2026-10-19-m4/cross/26-ambiguous-place.transcript.jsonl`
- `evals/results/2026-10-19-m4/cross/28-generic-text-place.transcript.jsonl`
- `evals/results/2026-10-19-m4/cross/29-multi-zone.transcript.jsonl`
- `evals/results/2026-10-19-m4/cross/31-knowledge-gap-offer.transcript.jsonl`
- `evals/results/2026-10-19-m4/seattle/01-cold-start.transcript.jsonl`
- `evals/results/2026-10-19-m4/seattle/03-fire-capitol-hill.transcript.jsonl`
- `evals/results/2026-10-19-m4/seattle/14-crime-capitol-hill.transcript.jsonl`
- `evals/results/2026-10-19-m4/seattle/30-stale-claim.transcript.jsonl`

Recorded costs (cost check, `total_cost_usd` of each transcript's last `result` event; `docs/evidence/launch-evals-2026-10-19/costs.txt`; the check first printed `UNRESOLVED: missing` for a path that does not exist):

| Session | Cost |
| --- | --- |
| cross/25-wrong-portal | $0.1328 |
| cross/26-ambiguous-place | $0.1434 |
| cross/28-generic-text-place | $0.1330 |
| cross/29-multi-zone | $0.1652 |
| cross/31-knowledge-gap-offer | $0.1502 |
| seattle/01-cold-start | $0.0769 |
| seattle/03-fire-capitol-hill | $0.1286 |
| seattle/14-crime-capitol-hill | $0.1762 |
| seattle/30-stale-claim | $0.1765 |
| **Step total** | **$1.2827** |

Every transcript ends with a `result` event, `subtype: "success"`, `api_error_status` null; no health re-run was needed. Unresolved spend: none. `pgrep -fl "claude -p"` found no session still running (the instrument first showed a background `sleep 30`).

## Task 8 Step 2: re-runs

Not run. No task graded below its baseline, so no session was expected and none started.
