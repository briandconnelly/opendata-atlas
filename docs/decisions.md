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
