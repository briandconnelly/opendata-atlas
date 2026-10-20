# opendata-atlas

[![CI](https://github.com/briandconnelly/opendata-atlas/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/briandconnelly/opendata-atlas/actions/workflows/ci.yml)
[![Python](https://img.shields.io/python/required-version-toml?tomlFilePath=https%3A%2F%2Fraw.githubusercontent.com%2Fbriandconnelly%2Fopendata-atlas%2Fmain%2Fpyproject.toml)](pyproject.toml)
[![License: MIT](https://img.shields.io/github/license/briandconnelly/opendata-atlas)](LICENSE)

Agent-friendly access to public [Socrata](https://dev.socrata.com/) open-data portals, as an [MCP](https://modelcontextprotocol.io/) server. It is read-only: it reads public datasets through each portal's SODA API and writes nothing.

**Status: preview.** Version 0.1.0 is on [PyPI](https://pypi.org/project/opendata-atlas/) and in [GitHub Releases](https://github.com/briandconnelly/opendata-atlas/releases/latest). The server holds a registry of public Socrata portals; `atlas_find_portals` lists them. Three portals are curated: Seattle (`seattle`), Chicago (`chicago`) and City of Everett (`everett`).

## Tools

| Tool | Purpose |
| --- | --- |
| `atlas_find_portals` | Find portals by place name, alias, portal name or host |
| `atlas_search_datasets` | Find a portal's datasets by topic |
| `atlas_describe_dataset` | Columns, row count, time coverage, place fields, geo columns, knowledge level |
| `atlas_query_dataset` | Bounded reads and aggregates (SoQL clauses or raw SoQL) |
| `atlas_get_reference` | Capability summary, SoQL help, portals, guides, error catalog |

## Choosing a portal

Every data tool takes a required `portal`: a portal id (its hostname, such as `data.seattle.gov`) or an alias (such as `seattle`). Without the id, call `atlas_find_portals` with a place name. It never picks for you: a city and its county are both candidates, told apart by `jurisdiction.level`, and the server's rules tell the agent to ask the user which one they mean unless the request names the level.

## Knowledge levels

Portals are tiered (`generic`, `profiled`, `curated`), but the tier never vouches for a dataset. `atlas_describe_dataset` reports a `knowledge` level for the dataset: `none` (nothing recorded), `profiled` (the profiler recorded observations that nobody reviewed) or `reviewed` (a contributor reviewed its unit of observation, place fields and primary time column). `atlas_query_dataset` adds a `knowledge_notice` when the dataset is not `reviewed`, or when your query uses a place or time column with no reviewed claim. Each `knowledge` also reports `validation`, what the claims' checks found when the drift run (`uv run pytest --run-integration -m integration`) last ran them: `passed`, `contradicted` or `inconclusive`, `unchecked` for a claim with no check, and `stale` when the checks last ran over 180 days ago by the server's clock. The server reads the recorded outcomes and runs no check itself. A stale claim stops vouching for the data: for example, a place field it reviewed as `ok` reports `unknown`, and `coverage_warnings` fire on it.

## Install

The server runs over stdio. The `uvx` commands below need [uv](https://docs.astral.sh/uv/).

**Claude Desktop:** download `opendata-atlas-<version>.mcpb` from the [latest release](https://github.com/briandconnelly/opendata-atlas/releases/latest) and open it with Claude Desktop.

**Claude Code:**

```bash
claude mcp add opendata-atlas -- uvx opendata-atlas
```

**Codex:**

```bash
codex mcp add opendata-atlas -- uvx opendata-atlas
```

**Any other MCP client:** run `uvx opendata-atlas` as a stdio server:

```json
{
  "mcpServers": {
    "opendata-atlas": { "command": "uvx", "args": ["opendata-atlas"] }
  }
}
```

## Try it locally

Three ways to run the server from a checkout, each over stdio. Each needs [uv](https://docs.astral.sh/uv/); path (c) also needs the `mcpb` CLI (`npm install -g @anthropic-ai/mcpb`). Replace `/path/to/opendata-atlas` with the absolute path of your checkout.

By default (`--scope local`), `claude mcp add` makes the server available only to you, in the current project. To use it in every project, add `--scope user`. For Claude Desktop, merge the snippet's `opendata-atlas` entry into `mcpServers` in `claude_desktop_config.json` (on macOS, `~/Library/Application Support/Claude/claude_desktop_config.json`), then restart Claude Desktop. If Claude Desktop cannot find `uv` or `uvx`, set `command` to the absolute path that `which uv` or `which uvx` prints.

**(a) From the checkout.** The server runs from your working tree, so edits take effect on the next start.

```bash
claude mcp add opendata-atlas -- uv run --directory /path/to/opendata-atlas --frozen opendata-atlas
```

```json
{
  "mcpServers": {
    "opendata-atlas": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/opendata-atlas", "--frozen", "opendata-atlas"]
    }
  }
}
```

**(b) From a built wheel.** Run `uv build` in the checkout; it writes the wheel and sdist to `dist/`. Replace `/path/to/dist` with the absolute path of that `dist/` directory.

```bash
claude mcp add opendata-atlas -- uvx --from /path/to/dist/opendata_atlas-0.1.0-py3-none-any.whl opendata-atlas
```

```json
{
  "mcpServers": {
    "opendata-atlas": {
      "command": "uvx",
      "args": ["--from", "/path/to/dist/opendata_atlas-0.1.0-py3-none-any.whl", "opendata-atlas"]
    }
  }
}
```

**(c) From the bundle (Claude Desktop only).** Run `make mcpb` in the checkout. Open `dist/opendata-atlas-0.1.0.mcpb` with Claude Desktop and follow its install prompt. The app token setting is optional: leave it blank to run without one.

To check a path without a client, run `scripts/smoke_test.py` from the checkout. It starts the server the same way and checks offline that it answers: `uv run python scripts/smoke_test.py --checkout .` for (a); after (b)'s `uv build`, `--uvx dist/opendata_atlas-0.1.0-py3-none-any.whl`; after (c)'s `make mcpb`, `--bundle dist/opendata-atlas-0.1.0.mcpb`. Add `--live` for one free live call to Seattle's portal.

## Configuration

- `SOCRATA_APP_TOKEN` (optional): a [Socrata application token](https://dev.socrata.com/docs/app-tokens.html), for example `claude mcp add opendata-atlas -e SOCRATA_APP_TOKEN=... -- uvx opendata-atlas`. The bundle asks for it in Claude Desktop's settings. A rejected token is reported as `app_token_rejected`, never silently dropped. Whether one token is accepted by every portal is unprobed.
- `OPENDATA_ATLAS_PORTALS` (optional): a comma-separated list of portal ids or aliases. Set, it limits the server to those portals; any other fails with `portal_not_enabled`. Unset or blank, every registered portal is served.

## Adding a missing portal

If a Socrata portal is not in the registry:

1. Add an entry for it to [`src/opendata_atlas/portals/registry_overrides.toml`](src/opendata_atlas/portals/registry_overrides.toml). The comments in the file and `docs/design.md` (Registry) describe the fields.
2. Open a pull request. `scripts/build_registry.py` rebuilds `registry.json` from the entries and fails unless the portal is eligible and its identity holds.

## Issues

Report bugs and gaps at [github.com/briandconnelly/opendata-atlas/issues](https://github.com/briandconnelly/opendata-atlas/issues).

## Develop

From a checkout:

```bash
uv sync
uv run opendata-atlas                                  # run the server over stdio
uv run pytest
uv run ruff check && uv run ruff format --check && uv run ty check
UPDATE_SNAPSHOTS=1 uv run pytest tests/test_contract.py   # after an intended tool-surface change
uv run pytest --run-integration -m integration            # live tests against Socrata portals
uv run python evals/run.py [--host claude|codex] <out_dir> [task_id ...]
uv run python evals/report.py <out_dir> --answers
```

To build the MCPB bundle locally: `make mcpb` (needs the `mcpb` CLI; see [Try it locally](#try-it-locally), path (c)).

## Release

Tag `vX.Y.Z` after bumping the version: the release workflow builds and smoke-tests the wheel, sdist, and `.mcpb`, publishes to PyPI after maintainer approval, and attaches all three to a GitHub Release. See [docs/releasing.md](docs/releasing.md) for the steps. The first release, 0.1.0, followed [docs/release-checklist.md](docs/release-checklist.md), which records the one-time setup and the TestPyPI rehearsal.

The documentation is this README and the files in [`docs/`](docs/), as they stand in the repository; there is no hosted docs site.

## License

MIT
