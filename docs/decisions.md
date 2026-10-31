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
| `portal` on reference topic `portals` (2026-10-30, #61) | Rejected, with a repair to the reference index | Accepted as a synonym for `item_id`; both together are `invalid_argument` | Critical review; maintainer chose the synonym |
| Topic `contributing` (2026-10-30, #62) | One 19 KB body, also the resource | Sectioned like `soql` and `errors`: `tiers`, `levels`, `validation`, `path`; the resource is the section index | Critical review |
| Lifecycle metadata and tool titles (2026-10-30, #66) | Deferred for bytes | Every tool, resource and template carries `_meta["opendata-atlas/lifecycle"]`; tools carry `title`; `tools/list` 24,515 of 24,576 bytes | Critical review; maintainer chose both |
| Engine defects found while curating (2026-10-30, #71) | Logged as rows of this table, which is the design-change log | Named in the PR body only; no repository file | Critical review; maintainer's choice |
| Pack PRs and `CHANGELOG.md` (2026-10-30, #71) | The path rule forbade `CHANGELOG.md`, against `AGENTS.md`'s rule for user-visible changes | A pack PR adds one line under `## [Unreleased]` | Critical review; maintainer's choice |
| Curation stops and eval evidence (2026-10-30, #69, #70) | Steps 1 and 2 stopped with no outcome; eval runs reused `.curation/evals-1..3` | Every stop ends with an outcome (`preflight_failed`, `not_registered`, `needs_input`, `profiler_failed`); runs go under `.curation/<pack>-<date>-<n>/`, recorded in `outcome.json`, and `evals/run.py` refuses to overwrite a transcript | Critical review |
| Shared output-schema objects (2026-10-31, #66) | FastMCP inlined every `$ref`; `tools/list` 24,515 of 24,576 bytes | Output schemas keep a `$defs` entry for an object used more than once (3 in all), inline the rest, and expand to the old schemas exactly; input schemas stay inlined; 23,788 bytes | Critical review; Codex consult preferred this lossless option over dropping nested `additionalProperties: false` or loosening subtrees |
| NYC promoted to curated (maintainer, 2026-10-31) | `data.cityofnewyork.us` merged as `profiled` with 311 Service Requests (`erm2-nwe9`) reviewed and a guide (#78) | `curated`. Every task graded PASS in at least 2 of 3 eval runs, none FAIL (11 PASS, 1 PARTIAL), the curating agent's own grades; the maintainer accepted them in place of an independent re-grade, as for King County | #78; maintainer, 2026-10-31 |
| Region labels without stats (2026-10-31, #80) | A computed-region column lost its labels whenever its stats group-by timed out, though they come from the small layer table | Describe reads the layer's whole label map (at most 100 features) when stats fail and serves it as a new optional `layer_features`; `values` stays tied to the stats | Issue #80 (NYC 311 eval) |
| Large-table assertion probes (2026-10-31, #81) | Fill and share probes scanned whole tables and diurnal probes a year, so drift on tables of millions of rows timed out, with no retry | At 1,000,000 rows the profiler bounds fill and share probes to the primary time column's last 30 days and diurnal probes to 7; drift retries a temporary `query_timeout` once | Issue #81; implemented by Codex via amicus delegate; live profile of NYC 311 `erm2-nwe9` ran every bounded probe without a timeout (68 s) |
