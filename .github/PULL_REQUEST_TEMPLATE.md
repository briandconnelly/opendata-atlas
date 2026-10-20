## What and why

<!-- One or two sentences. Link the issue: "Closes #123". -->

## Checks

- [ ] `uv run prek run --all-files` and `uv run pytest` pass
- [ ] `CHANGELOG.md` entry for a user-visible change (see `AGENTS.md`)
- [ ] Tool-surface change: `tests/snapshots/tools_list.json` regenerated and noted in `CHANGELOG.md`
- [ ] Design change: `docs/design.md` updated and a `docs/decisions.md` row added
- [ ] Live or paid runs (drift, smoke test, evals): which ran, and their outcome
