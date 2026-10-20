# Releasing

On a `v<version>` tag, `.github/workflows/release.yml` verifies, builds, publishes to PyPI (after a maintainer's approval), and creates a GitHub Release. Its first job checks that `pyproject.toml`, `manifest.json`, the first `## [X.Y.Z]` heading in `CHANGELOG.md`, and the tag all name the same version. It then publishes that CHANGELOG section as the GitHub release notes. The section ends at the next `## [` heading.

## Rules

- Before tagging, run `uv run pytest --run-integration -m integration` and commit the regenerated `src/opendata_atlas/portals/validation.json`; `tests/test_release_gate.py` must pass.
- Before tagging, cut the CHANGELOG with `uv run python scripts/rehearse_release.py --apply --date <YYYY-MM-DD>`, then commit. It first rehearses on a temp copy with the workflow's own version check and notes extraction (extracted from `release.yml`, not copied), then renames `## [Unreleased]` to `## [<version>] - <date>`. Without `--apply` it only rehearses and changes nothing.
- Keep `## [seattle-open-data history]` as the heading above seattle-open-data's entries. It is not a version, and it ends the release notes before the parent's history. `tests/test_versioning.py` runs the workflow's extraction on a cut CHANGELOG and checks this.
- Tag the commit that carries the renamed heading as `v<version>`, matching `pyproject.toml`.

## Context

- A manual run of the workflow before `## [Unreleased]` is renamed fails the "pyproject, manifest, CHANGELOG (and the tag, if any) agree" step, because the CHANGELOG has no versioned heading yet. That failure is expected.
