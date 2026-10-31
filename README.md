# opendata-atlas

[![CI](https://github.com/briandconnelly/opendata-atlas/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/briandconnelly/opendata-atlas/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/opendata-atlas)](https://pypi.org/project/opendata-atlas/)
[![Python](https://img.shields.io/python/required-version-toml?tomlFilePath=https%3A%2F%2Fraw.githubusercontent.com%2Fbriandconnelly%2Fopendata-atlas%2Fmain%2Fpyproject.toml)](pyproject.toml)
[![License: MIT](https://img.shields.io/github/license/briandconnelly/opendata-atlas)](LICENSE)

Let your AI assistant answer questions with public government data. opendata-atlas connects an assistant such as Claude or Codex to the open-data portals that cities, counties, states and other public agencies publish on [Socrata](https://dev.socrata.com/). Your assistant can find the right portal and dataset, check what its columns mean, and answer with counts, trends and records drawn from the data itself.

It is an [MCP](https://modelcontextprotocol.io/) server, the standard way to give AI assistants new tools. It only reads public data and never changes anything on a portal.

**Status: preview.** Version 0.2.0 is on [PyPI](https://pypi.org/project/opendata-atlas/) and in [GitHub Releases](https://github.com/briandconnelly/opendata-atlas/releases/latest). Your assistant can search every portal in the server's registry of public Socrata portals. Six portals are curated: Seattle (`seattle`), Chicago (`chicago`), City of Everett (`everett`), King County (`king-county`), NYC Open Data (`data.cityofnewyork.us`) and Los Angeles (`los-angeles`).

## What you can ask

Once the server is connected, ask your assistant questions like these:

- "Where can I find Seattle's real-time fire 911 call data, and how current is it?"
- "How many bikes have crossed the Fremont Bridge this month?"
- "How many crimes were reported in Chicago's Hyde Park community area last month?"
- "Show me recent restaurant health inspection results for Everett, WA."
- "How many jail bookings were there in King County last month?"

Answers come from the live portal, so they change as the data does.

## Install

You need an MCP client that can start a local server, such as Claude Desktop, Claude Code or Codex. The `uvx` commands below also need [uv](https://docs.astral.sh/uv/); the server runs on Python 3.13 or later, which uv installs for you if needed. No account or API key is required.

**Claude Desktop:** download `opendata-atlas-<version>.mcpb` from the [latest release](https://github.com/briandconnelly/opendata-atlas/releases/latest) and open it with Claude Desktop.

**Claude Code**, as a plugin:

```bash
claude plugin marketplace add briandconnelly/opendata-atlas
claude plugin install opendata-atlas@opendata-atlas
```

**Codex**, as a plugin:

```bash
codex plugin marketplace add briandconnelly/opendata-atlas
codex plugin add opendata-atlas@opendata-atlas
```

The plugin adds the server, pinned to the latest release, and the `curate-portal` skill, which contributors use in a clone of this repository to add a portal ([CONTRIBUTING-portals.md](CONTRIBUTING-portals.md)). The skill follows the clone's own `skills/curate-portal/SKILL.md`, so a run uses the instructions you have checked out, and does nothing outside a clone. Codex starts it only when you name it (`$curate-portal`). To pick up a new release, run `claude plugin update opendata-atlas@opendata-atlas` or `codex plugin marketplace upgrade opendata-atlas`.

To add only the server instead, in Claude Code:

```bash
claude mcp add opendata-atlas -- uvx opendata-atlas
```

This makes the server available to you in the current project. To use it in every project, add `--scope user` after `add`. In Codex:

```bash
codex mcp add opendata-atlas -- uvx opendata-atlas
```

**Any other MCP client:** run `uvx opendata-atlas` as a stdio server. Most clients take an entry like this in their configuration file:

```json
{
  "mcpServers": {
    "opendata-atlas": { "command": "uvx", "args": ["opendata-atlas"] }
  }
}
```

To set up Claude Desktop this way instead of with the bundle, merge the `opendata-atlas` entry into `mcpServers` in `claude_desktop_config.json` (on macOS, `~/Library/Application Support/Claude/claude_desktop_config.json`), then restart Claude Desktop. If it cannot find `uvx`, set `command` to the absolute path that `which uvx` prints.

To check the connection, ask your assistant "Which open-data portals can you search for Seattle?"

## Portals and data quality

**Finding a portal.** Name the place you mean, and your assistant looks up its portal. When a place has more than one, such as a city and its county, the assistant asks which you mean unless your question already says. Each portal also has an id (its hostname, such as `data.seattle.gov`), and many have a short alias (such as `seattle`).

**Curated portals.** Every registered portal can be searched and queried. On a curated portal, contributors have also reviewed key datasets: what one row stands for, which columns hold places, and which time column to count by. Most portals have no such review, and even on a curated one, many datasets don't.

**Knowledge levels.** For each dataset, the server tells your assistant how much reviewed knowledge it has (`reviewed`, `profiled` or `none`). When a question depends on a column nobody has reviewed, or on a review that has gone stale, the result carries a caveat that your assistant should pass on to you. [CONTRIBUTING-portals.md](CONTRIBUTING-portals.md#knowledge-levels) defines the levels exactly.

## Limitations

- **Public Socrata data only.** The server reads public datasets on portals in its registry. It cannot read private datasets or query other platforms. ArcGIS layers listed in a portal's catalog show up in search, but cannot be queried.
- **Bounded reads.** A query returns records a page at a time, and at most 10,000 rows in total. Counts, sums and other summaries can still cover a whole dataset of any size.
- **No geocoding or forecasting.** The server cannot turn an address into coordinates, and it reports what the data says rather than predicting.
- **Data quality is the publisher's.** Coverage, freshness and accuracy vary by portal and dataset.

## Configuration

No configuration is required. Two optional environment variables change the defaults:

- `SOCRATA_APP_TOKEN`: a [Socrata application token](https://dev.socrata.com/docs/app-tokens.html), for example `claude mcp add opendata-atlas -e SOCRATA_APP_TOKEN=... -- uvx opendata-atlas`. The bundle asks for it in Claude Desktop's settings. The Claude Code plugin passes `SOCRATA_APP_TOKEN` and `OPENDATA_ATLAS_PORTALS` through from the environment Claude Code starts in; the Codex plugin passes neither. To set them in Codex, remove the plugin first (`codex plugin remove opendata-atlas@opendata-atlas`), then add the server with `codex mcp add opendata-atlas -e SOCRATA_APP_TOKEN=... -- uvx opendata-atlas`; with both installed, the plugin's server keeps running with no token and no allowlist. If a portal rejects the token, the server reports `app_token_rejected` rather than silently dropping it. A token may not be accepted by every portal.
- `OPENDATA_ATLAS_PORTALS`: limits the server to the portals you list, by id or alias, separated by commas (for example, `seattle,chicago`). Any other portal fails with `portal_not_enabled`. Names that match no portal are ignored, so a list in which nothing matches blocks every portal. Unset or blank, every registered portal is served.

## Tools and reference

The server gives your assistant five tools:

| Tool | Purpose |
| --- | --- |
| `atlas_find_portals` | Find portals by place name, alias, portal name or host |
| `atlas_search_datasets` | Find a portal's datasets by topic |
| `atlas_describe_dataset` | A dataset's columns, row count, time coverage, place and map columns, and knowledge level |
| `atlas_query_dataset` | Read records or compute summaries, in SoQL, Socrata's SQL-like query language |
| `atlas_get_reference` | Built-in help: capability summary, SoQL help, portals, guides, error catalog |

The same reference material is also served as MCP resources, for clients that browse them:

| Resource | Contents |
| --- | --- |
| `opendata-atlas://reference` | Index of the reference topics |
| `opendata-atlas://capabilities` | Capability summary: what the server does and does not do, rules, semantics, failures |
| `opendata-atlas://portals` | Curated and profiled portals (`atlas_find_portals` searches every registered portal) |
| `opendata-atlas://portals/{portal}` | One portal: identity, tier, knowledge by dataset, guide index |
| `opendata-atlas://portals/{portal}/guides`, `.../guides/{guide_id}` | A portal's guides, and one guide |
| `opendata-atlas://soql`, `opendata-atlas://soql/{section_id}` | SoQL reference: syntax, filtering, aggregation, dates, geography, paging |
| `opendata-atlas://errors`, `opendata-atlas://errors/{section_id}` | Error catalog |
| `opendata-atlas://contributing`, `opendata-atlas://contributing/{section_id}` | Tier, knowledge-level and validation definitions, and how to contribute portal knowledge |

The `{portal}`, `{section_id}` and `{guide_id}` parameters support completion.

## Help and contributing

- **Bugs and questions:** open an issue at [github.com/briandconnelly/opendata-atlas/issues](https://github.com/briandconnelly/opendata-atlas/issues).
- **A portal is missing:** open an issue with the portal's address. To add it yourself, add an entry to [`registry_overrides.toml`](src/opendata_atlas/portals/registry_overrides.toml) (its comments and [`docs/design.md`](docs/design.md#registry) describe the fields) and open a pull request; `scripts/build_registry.py` checks that the portal is eligible and its identity holds.
- **Portal knowledge:** [CONTRIBUTING-portals.md](CONTRIBUTING-portals.md) describes how to review a portal's datasets.
- **Code:** [CONTRIBUTING.md](CONTRIBUTING.md) covers running from source and the test suite. Maintainers release with [docs/releasing.md](docs/releasing.md).

The rest of the documentation lives in [`docs/`](docs/); there is no hosted docs site.

## License

[MIT](LICENSE)
