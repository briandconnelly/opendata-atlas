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
| `portal` on reference topic `portals` (2026-10-30, #61) | Rejected, with a repair to the reference index | Accepted as a synonym for `item_id`; both together are `invalid_argument` | Critical review; maintainer chose the synonym |
| Topic `contributing` (2026-10-30, #62) | One 19 KB body, also the resource | Sectioned like `soql` and `errors`: `tiers`, `levels`, `validation`, `path`; the resource is the section index | Critical review |
| Lifecycle metadata and tool titles (2026-10-30, #66) | Deferred for bytes | Every tool, resource and template carries `_meta["opendata-atlas/lifecycle"]`; tools carry `title`; `tools/list` 24,515 of 24,576 bytes | Critical review; maintainer chose both |
