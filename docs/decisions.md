# Decisions

Why the design is the way it is. The current contract is in [design.md](design.md).

## Origin (2026-10-16)

The maintainer asked whether `seattle-open-data` could become a server for many places, as a new package "to be safe", supporting all Socrata portals and improving each one's specific knowledge over time. Claude drafted the design; Codex critiqued it via amicus.

## Log

Rows through 2026-10-25 are in [decisions/log-2026-10.md](decisions/log-2026-10.md).

Add a row for each design change, oldest first. Keep each cell to a sentence or two and the row under about 600 characters; put a longer argument in the PR, the issue, or a note under `docs/evidence/`, and link it from the Source cell.

| Topic | Before | After | Source |
| --- | --- | --- | --- |
| Agent-facing doc size (2026-10-25, project review) | `design.md` was 95 KB and this log 176 KB, with rows up to 3,454 characters (#35) | `design.md`'s Building knowledge section moved to `knowledge-tooling.md`; the log moved to `decisions/log-2026-10.md`, only relative links adjusted; new rows stay short | Project review (Claude and Codex), maintainer's choice of a lossless split, 2026-10-25 |
| Bounded validation feedback (2026-10-30) | Unknown keys appeared as published fields; field lists and failure results had no size guard | Unknown keys appear only in bounded reason text; feedback caps paths at 20 and names at 128 characters, reports omissions, and oversized failures keep the minimal envelope | #58 |
| Engine defects found while curating (2026-10-30, #71) | Logged as rows of this table, which is the design-change log | Named in the PR body only; no repository file | Critical review; maintainer's choice |
| Pack PRs and `CHANGELOG.md` (2026-10-30, #71) | The path rule forbade `CHANGELOG.md`, against `AGENTS.md`'s rule for user-visible changes | A pack PR adds one line under `## [Unreleased]` | Critical review; maintainer's choice |
| Curation stops and eval evidence (2026-10-30, #69, #70) | Steps 1 and 2 stopped with no outcome; eval runs reused `.curation/evals-1..3` | Every stop ends with an outcome (`preflight_failed`, `not_registered`, `needs_input`, `profiler_failed`); runs go under `.curation/<pack>-<date>-<n>/`, recorded in `outcome.json`, and `evals/run.py` refuses to overwrite a transcript | Critical review |
