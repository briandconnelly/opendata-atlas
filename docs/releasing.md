# Releasing

On a `v<version>` tag, `.github/workflows/release.yml` verifies, builds, publishes to PyPI (after a maintainer's approval), and creates a GitHub Release. Its first job checks that `pyproject.toml`, `manifest.json`, the first `## [X.Y.Z]` heading in `CHANGELOG.md`, and the tag all name the same version. It then publishes that CHANGELOG section as the GitHub release notes. The section ends at the next `## [` heading.

## Rules

- Before cutting, set the new version in `pyproject.toml`, run `uv lock` and `uv run python scripts/gen_manifest.py`, set the same version in `plugins/opendata-atlas/` (`version` in `.claude-plugin/plugin.json` and `plugin.json`, the `opendata-atlas==<version>` pin in `.mcp.json` and `mcp.json`), set it in `CONTRIBUTING.md`'s "Try it locally" wheel and bundle paths and the README's status line, and commit them all; `tests/test_plugin.py` fails until the plugin files agree and `tests/test_readme.py` until the CONTRIBUTING paths do. The rehearsal fails while `v<version>` already exists as a tag.
- Before tagging, run `uv run pytest --run-integration -m integration` and commit the regenerated `src/opendata_atlas/portals/validation.json`; `tests/test_release_gate.py` must pass.
- Before tagging, cut the CHANGELOG with `uv run python scripts/rehearse_release.py --apply --date <YYYY-MM-DD>`, then commit. It first rehearses on a temp copy with the workflow's own version check and notes extraction (extracted from `release.yml`, not copied), then renames `## [Unreleased]` to `## [<version>] - <date>`. Without `--apply` it only rehearses and changes nothing.
- Keep `## [seattle-open-data history]` as the heading above seattle-open-data's entries. It is not a version, and it ends the release notes before the parent's history. `tests/test_versioning.py` runs the workflow's extraction on a cut CHANGELOG and checks this.
- Land the bump and the cut on `main` through a pull request, then tag the resulting `main` commit as `v<version>`, matching `pyproject.toml`. Only the maintainer tags. The workflow refuses a tag whose commit is not on `main`.

## Context

- The plugin marketplaces are read from `main`, so the plugin pins the new version as soon as the bump lands, before PyPI has it: until the release is published, installing or updating the plugin starts a server that `uvx` cannot resolve. Tag soon after the bump merges. Claude Code users get the release with `claude plugin update`, because the plugin version changed; Codex users get it with `codex plugin marketplace upgrade`.

- A manual run of the workflow after the version bump but before `## [Unreleased]` is renamed fails the "pyproject, manifest, CHANGELOG (and the tag, if any) agree" step, because the first versioned CHANGELOG heading still names the previous release. That failure is expected.
