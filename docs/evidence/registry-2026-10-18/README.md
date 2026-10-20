# Registry build evidence, 2026-10-18

Raw outputs of `scripts/build_registry.py`, cited from `docs/upstream-facts.md` (Registry build). Run on 2026-10-18 UTC (2026-10-17 evening, Pacific), sequential GETs 0.2 s apart, 60 s timeout each, `User-Agent: opendata-atlas-registry/0`, no token. Every file is under 500 KB (the prek large-file limit), so none was reduced to a summary. Counts are live and drift.

Command (the full network run, 1,186 s wall clock):

```
uv run python scripts/build_registry.py --out src/opendata_atlas/portals/registry.json --evidence docs/evidence/registry-2026-10-18/ --titles 60
```

`network-run.log` is that run's stderr: one line per probe, the final counts, and `/usr/bin/time -p` (`real 1186.35`). Later runs reused this directory as a cache:

1. A re-probe of `weho.data.socrata.com`, whose first probe had a short read (`errors=1`, line 254 of the log).
2. A re-fetch of `titles.json` after `strings.company` was added to it.
3. A build with the first 50 overrides, which made no request.
4. Review fix round 1 (2026-10-18 04:05Z):

   ```
   uv run python scripts/build_registry.py --out <scratch> --evidence docs/evidence/registry-2026-10-18/ --overrides <none> --reprobe-views data.miamigov.com data.nhitc.org data.permits.performance.gov data.urbanaillinois.us performance.cityofdavenportiowa.com performance.cityofrc.us performance.providenceri.gov data.oxnard.org opendata.l-h.cat performance.austintexas.gov performance.seattle.gov
   ```

   This re-ran only `/api/views` on those eleven hosts, recording the exception class and final URL.
5. The final build with the revised overrides. Its only request was the title of performance.cityofcamas.us, which moved into the 60 largest.
6. Milestone 2 final review: a rebuild after adding "New York City" and "New York" to data.cityofnewyork.us's place names, with no request (`HTTPS_PROXY` pointed at a closed port; only `summary.json` and `registry.json` changed):

   ```
   uv run python scripts/build_registry.py --out src/opendata_atlas/portals/registry.json --evidence docs/evidence/registry-2026-10-18/ --today 2026-10-18
   ```

`summary.json` is from the last of these runs, so its `run_seconds` is the cached run's.

| File | Contents |
| --- | --- |
| `enumeration.json` | `enumerate_domains.method_b2` per region: requests, results seen, unique ids, domain growth per page, `exhausted`, and the catalog domains |
| `probes.jsonl` | One line per eligible catalog domain (`kind: enumerated`): `link` host counts from the first three `domains=` pages, every candidate (`params`, `resultSetSize`, pages read, `identity_matches`, top five `metadata.domain` values, whether the read was complete), the chosen `catalog_query`, the public host with the reason, the anonymous `/api/views.json?limit=1` status and whether it parsed as JSON, and `dataset_count` (`only=dataset`). Plus `pack:data.seattle.gov`, the counts of the pack's own query |
| `probes.retries.jsonl` | Superseded probe lines, each with `superseded_at` and `superseded_by` (`reprobe-views` or `retry`): the first-pass `/api/views` results of the eleven re-probed hosts. weho's superseded line predates this file and was not kept; the log line stands for it |
| `network-run.log` | stderr of the network run (see above) |
| `titles.json` | For the 60 largest portals (61 hosts: performance.cityofcamas.us joined after the drops) and every override: `strings.site_title` and `strings.company` from `/api/configurations.json?type=site_theme&defaultOnly=true&merge=true`, and the home page `<title>` (whitespace collapsed, HTML entities unescaped), with statuses and fetch times. The source cited by each comment in `registry_overrides.toml` |
| `summary.json` | Counts, the name-rule rejects, unresolved domains, the domain folded into a pack, `/api/views` 4xx drops, 5xx and transport-error keeps, 2xx non-JSON answers, public hosts that differ from catalog domains (none), duplicates (none), portals whose `catalog_query` is `search_context`, and the 50 largest by `catalog_size` |

No token or credential was used or recorded (`grep -ciE 'token|secret|password'` over every file here except this README, which names the pattern: 0 each; the same grep for `Tyler` finds 44 lines in `titles.json`).
