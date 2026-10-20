# Contributing

Thanks for helping with opendata-atlas. This page covers running the server from source and the development checks. To contribute knowledge about a portal's datasets, see [CONTRIBUTING-portals.md](CONTRIBUTING-portals.md). The repository's working rules, for people and coding agents alike, are in [AGENTS.md](AGENTS.md); the design is in [docs/design.md](docs/design.md).

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

## Develop

From a checkout:

```bash
uv sync
uv run opendata-atlas                                     # run the server over stdio
uv run pytest
uv run prek run --all-files                               # lint, format, type check and other hooks
UPDATE_SNAPSHOTS=1 uv run pytest tests/test_contract.py   # after an intended tool-surface change
uv run pytest --run-integration -m integration            # live tests against Socrata portals
```

The evals run agent sessions against the server. Each task is a paid session, so run them only when the maintainer asks (see [AGENTS.md](AGENTS.md)). `uv run python evals/run.py --help` is free and shows the options; a run and its report look like this:

```bash
uv run python evals/run.py --host claude --portal seattle evals-out
uv run python evals/report.py evals-out --answers
```

## Pull requests

Work on a branch with a type prefix (`feat/`, `fix/`, `docs/`, ...), use [Conventional Commits](https://www.conventionalcommits.org/), and add a `CHANGELOG.md` entry under `## [Unreleased]` for every user-visible change.

## Releasing

Maintainers release by tag; [docs/releasing.md](docs/releasing.md) has the steps.
