---
name: curate-portal
description: Use when asked to "curate <portal>" in a clone of the opendata-atlas repository, where <portal> is a registered Socrata portal's id, alias, host or place name, or to take a registered portal from generic to profiled (or improve an existing pack) through the contribution path in CONTRIBUTING-portals.md. Reads and follows the clone's own skills/curate-portal/SKILL.md, which ends in one knowledge-pack commit on a curate/ branch and the text of its PR, and can start paid eval runs. Outside a clone it does nothing.
---

# Curate a portal

The curation instructions live in the opendata-atlas repository, so that a run follows the version you have checked out, not the one this plugin was released with.

1. Find the repository root: `git rev-parse --show-toplevel`. If that fails, or the root has no `skills/curate-portal/SKILL.md`, or its `pyproject.toml` does not have `name = "opendata-atlas"`, stop: tell the user that curation runs in a clone of https://github.com/briandconnelly/opendata-atlas (its `CONTRIBUTING-portals.md` describes the contribution path), and do nothing else.
2. Otherwise, read `skills/curate-portal/SKILL.md` at that root in full, and follow it from the root in place of this file.
