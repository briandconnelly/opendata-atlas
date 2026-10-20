# `skills/curate-portal/SKILL.md` audit (separating-context-from-constraints)

Target: `skills/curate-portal/SKILL.md` after Task 14 fix round 1 (rulings 63–65 and review Important 4). This replaces the pre-run audit. Surfaces, audited separately: the frontmatter `description` (compact) and the body (long-form: labelled `## Rules`, `## Steps`, `## Ending`, `## Context`).

## Pass 1: findings carried from the review and rulings, and where each now lives

| # | Rule | Location (before) | Quoted text | Why it failed | Severity | Fix |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | R5 | Rule 5 vs Ending 3 | "Never push" / "run `gh pr create`" | `gh pr create` needs the branch on a remote; the Ending could never succeed without breaking rule 5 | Material | Ruling 63: rules 9 "Never push" and 10 "Never open a PR"; the Ending prints the title and body for a human to push and open |
| 2 | R1 | Steps preamble | "never stage it"; "Do not create directories outside the repository" | Binding prohibitions outside Rules; the second is the run 1 lesson | Material | Rule 5 (never write or point output outside the repository), rule 6 (working files under `.curation/`); staging is rule 4. The preamble now only cites them |
| 3 | R1 | Step 4 | "set it from no other source" | Provenance constraint outside Rules | Material | Rule 21 |
| 4 | R1 | Step 3 | "never copy the values" | Prohibition outside Rules | Material | Covered by rule 19; step 3 cites it |
| 5 | R1 | Context, Fetching a page | "Quote the passage as the page has it" | A rule in Context | Material | Rule 21 (quoted exactly, HTML entities included); Context keeps only the fact that the output keeps entities |
| 6 | R3 | Step 12 | "Set `tier = \"curated\"` only when ..." | Self-graded promotion; the agent graded the tasks it wrote | Material | Ruling 64: rule 3 caps the tier at `profiled`; step 12 proposes `curated` with per-run grades for another reviewer to re-grade |
| 7 | R3 | Step 9 | "each prompt naming the place" | Allowed prompts that announce their trap | Material | Ruling 64: rules 22 and 23 |
| 8 | R4 | Rule 12 (old) | "Write `reviewed_by = \"claude\"` ... and never write a person's name ..." | Two independent obligations | Minor | Split into rules 18 and 19 |
| 9 | R3 | Rule 4 (old) | "a gap that needs engine code" | Whether a worked-around defect is logged was undecided | Minor | Author choice (a): rule 7 logs every engine defect; rule 8 stops only when the pack cannot be made right without engine code |
| 10 | R3 | Steps 3–6 | (no date rule) | `reviewed_at`/`observed_at` written on the local date against UTC evidence | Minor | Rule 20 and Context: Today's date |
| 11 | R3 | Step 6 | (no rule for computed-region fields) | After ruling 62, two valid ways to review one, neither named | Minor | Step 6 names both |

## Pass 2: re-audit of the final text, R1–R5

- R1: every binding prohibition is a numbered rule (1–25). Steps and Ending hold actions with checkable outcomes and cite the rules they rely on. Context holds only facts and literal commands (tool calls, page fetch, today's date, transcript format, names); no imperative constraint remains there. Rule 3's pointer "Step 12 says how to propose `curated`" and rule 4's "Rule 7 adds the only exception" are cross-references, not context; accepted.
- R2: every rule is "never", "only" or an unconditional imperative; no hedges.
- R3: each rule is checkable against tool calls, files, the commit or the printed PR text. Rule 22 is checkable on the eval file; rule 23 against the reviewed datasets and the tasks' prompts and `expect`.
- R4: one obligation per rule; rule 8 is one trigger with its action sequence; rule 12 is one obligation with its ordering and one stated exception.
- R5: pairs checked for reachable conflicts: rule 7 (decisions.md) vs rule 13 (no pack change after the evals): no conflict, decisions.md is not the pack. Rule 7 vs rule 12: finding 12 below, fixed. Rules 4 and 17 vs CONTRIBUTING's working-file rule (".curation/ or outside the repository"): both bind; `.curation/` satisfies both. Rule 3 vs CONTRIBUTING step 12: step 12 binds an agent to `profiled`; rule 17 makes rules 4, 7, 8 and 13 win where they differ.

| # | Rule | Location | Quoted text | Why it fails | Severity | Fix |
| --- | --- | --- | --- | --- | --- | --- |
| 12 | R5 | Rule 12 vs rule 7 | "Run the four checks ... after your last pack change" | A decisions.md row added after 11.2 is never prek-checked; re-running all four checks would re-run the paid evals | Material | Rule 12: 11.1 and 11.2 after the last change to any file; 11.3 after the last pack change |
| 13 | R3 | Rule 20 | "Write every `reviewed_at` and `observed_at`" | Could be read as rewriting the profiler's own `observed_at` on copied claims | Minor | "... you add" |

## Summary

Counts per rule (this round, both passes): R1 4, R3 7, R4 1, R5 2. Counts per severity: 13 findings, Material 8, Minor 5; all fixed. No safety note. Overall: the document now separates its 25 binding rules from steps and context; every prohibition the run or the review surfaced, including the run 1 lesson about writing outside the repository, is a numbered rule, and no Material finding is open.

## Fix round 2 (ruling 67): rule tensions found by the re-review

| # | Rule | Location | Quoted text | Why it failed | Severity | Fix |
| --- | --- | --- | --- | --- | --- | --- |
| 14 | R5 | Rule 4 vs rule 6 | "Change and stage only the path-rule paths" / "Write every working file ... under `.curation/`" | Writing a working file is a change outside the path-rule paths | Material | Rule 4: "Commit only the path-rule paths"; rule 6's `.curation/` files are never committed |
| 15 | R5 | Rules 7 → 12 → 13, step 11.1 | "Log every engine defect"; "run 11.1 and 11.2 after your last change to any file"; "Never change the pack after step 11.3 starts"; "rerun until it exits 0" | A defect first seen while grading 11.3 forces a decisions row (7), which forces an 11.1 rerun (12); a live drift failure on that rerun must be fixed (11.1) but cannot be (13): no legal move | Material | Rule 13 states the move: leave the pack unchanged, name the failing claim or line in the PR body, and do not propose `curated`. Steps 11.1 and 11.2 fix failures only before 11.3 starts; step 12's proposal requires that no check failed after it |
| 16 | R5 | Rule 15 vs step 11.2 | "Never run `tests/test_curation_skill.py`" / "`uv run pytest -q`" | The full suite collects the curation test (skipped without the opt-in variable, but still run) | Material | One approach, used in rule 12, step 11.2 and CONTRIBUTING step 11.2: `uv run pytest -q --ignore=tests/test_curation_skill.py` |

Re-check of every rule pair after the edit: rule 13's move is compatible with rule 8 (a stop after 11.3 changes no pack file and runs only 11.1 and 11.2), with rule 12 (reruns still happen; failures are reported, not fixed) and, through rule 17, with CONTRIBUTING steps 11.1 and 11.3 ("correct or remove", "fix the pack"), which rule 13 overrides for the agent. Rule 4's commit-only wording no longer conflicts with rules 5, 6 or 25. No reachable conflict remains. Totals including this round: 16 findings, 11 Material, 5 Minor, all fixed.
