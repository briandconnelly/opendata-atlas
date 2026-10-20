# Upstream facts

Probed facts about Socrata that the design depends on. Seattle-specific facts live in `seattle-open-data/docs/upstream-facts.md` (at the fork revision 26c6628) and, as claims, in the Seattle pack (`src/opendata_atlas/portals/seattle/`).

Labels: **Verified** (run live by Claude, 2026-10-16 unless stated), **(review)** (reported by a reviewer, not re-run), **(brief)** (from research). Never add a fact you did not probe.

## Discovery API

- Verified: `GET https://api.us.socrata.com/api/catalog/v1/domains` returns HTTP 404 `{"error":"not found"}`, with or without `limit`.
- Verified: `GET https://api.us.socrata.com/api/catalog/v1/domains/data.cityofchicago.org/facets` returns per-facet counts (`datatypes`: dataset 920, filter 404, map 335, chart 153, ...; total 2,029).
- Verified: `GET https://api.eu.socrata.com/api/catalog/v1?limit=0` returns `resultSetSize` 10,000, so an EU catalog region exists alongside the US one.
- Verified: six catalog searches (`police`, `budget`, `311`, `crime`, `parks`, `employees`; `only=dataset`, `limit=1000` each) returned 179 distinct `metadata.domain` values, including demo, internal and sandbox domains (e.g. `*.demo.socrata.com`, `internal-*`). This is a sample, not an enumeration.

## Catalog identity varies by portal

`resultSetSize` with `limit=0`:

| public host | `domains=<host>` | `search_context=<host>` |
| --- | --- | --- |
| data.cityofchicago.org | 2,029 | 2,029 |
| data.cityofnewyork.us | 3,021 | 3,021 |
| data.kingcounty.gov | 539 | 539 |
| datahub.austintexas.gov | 2,287 | 2,287 |
| data.sf.gov | 5 | 1,225 |
| data.seattle.gov | 0 (`seattle-open-data` facts) | 699 |

- Verified: `search_context=data.sf.gov` results (first 50) all carry `metadata.domain` `data.sf.gov`; `domains=data.sfgov.org` returns 5.
- So the parameter that returns a portal's catalog differs per portal, and must be probed, not assumed.

## Milestone 0a feasibility probes (2026-10-17)

All **Verified** 2026-10-17 with the dev-only scripts in `scripts/feasibility/` (sequential GETs, 0.2 s apart, `User-Agent: opendata-atlas-feasibility/0`). Raw outputs are in `docs/evidence/feasibility-2026-10-17/` (see its README). Counts are live and drift.

### Enumerating domains

Command: `uv run python scripts/feasibility/enumerate_domains.py domains.json` (output: `docs/evidence/feasibility-2026-10-17/domains.json`). Each method paged at most 20 requests per region. `only=dataset` throughout, so a domain with no datasets does not appear.

- Verified: `GET {us,eu}/api/catalog/v1/domains` returns HTTP 404 in both regions.
- Verified: unfiltered `resultSetSize` is capped at 10,000 (`?limit=0` returns 10000 in the US and EU regions; re-probed 2026-10-17, saved as `docs/evidence/feasibility-2026-10-17/limit0.json`). With `only=dataset` the EU region reports 5,447, so the cap, not the true size, is shown whenever the catalog exceeds 10,000.
- Verified: offset paging (`limit=10000&offset=N`) stops at the second request in the US: `offset=10000` returns HTTP 400 `Sum of offset and limit cannot exceed 10000. Please use the deep scrolling API`. The first page returned 141 distinct `metadata.domain` values. This method is capped in the US. In the EU the first page was short (5,447 results, 12 domains), so it finished.
- Verified: **deep scrolling showed no cap on 2026-10-17.** `GET {region}/api/catalog/v1?only=dataset&limit=5000&scroll_id=<last resource.id of the previous page>`, with an **empty** `scroll_id=` on the first request, returns results sorted by id and ends with a page shorter than `limit`. US: 43,333 datasets in 9 scroll pages, ending on a short page of 3,333, all ids unique, 286 distinct domains. EU: 5,447 in 2 pages, 12 domains. Termination assumes a short page means the end; that is untested.
- Verified: a first request that omits `scroll_id` returns a relevance-ordered page. Continuing from its last id re-reads part of the catalog (EU: 3 pages of 5000, 5000 and 261 give 10,261 results for 5,429 unique ids; re-probed 2026-10-17, saved as `docs/evidence/feasibility-2026-10-17/eu_scroll_without_initial_scroll_id.json`), so the first request must send `scroll_id=`.
- Verified: the scroll totals reconcile with the per-domain counts. The sum of `resultSetSize` for `domains=<d>&only=dataset&limit=0` over the 286 US domains is 43,333, and over the 12 EU domains 5,447, equal to each region's scrolled total. This is internal consistency of one catalog index, not independent evidence of completeness.
- Verified: topic-word search (20 words, `limit=1000` each) found 217 US and 9 EU domains, so it is incomplete (the domain count was still growing at the last word). It is a fallback only.
- Verified: the two regions share no domain. The union is 298 domains; 263 pass the name-based eligibility rule (`is_eligible`: false for any host with a label equal to `demo`, a label containing `staging`, a name starting `internal`, or a name starting `priv-`; other `*.socrata.com` hosts are eligible, 110 of them `*.data.socrata.com`). The 35 ineligible are 26 with a `demo` label (including `*.demo.eu.socrata.com`), 5 `internal*`, 1 `priv-*` (`priv-data.ojp.usdoj.gov`) and 3 more `staging` hosts. The anonymous `/api/views` part of eligibility was run only for the 20-host sample, not for all 263. (An earlier rule that also dropped every `*.socrata.com` host gave 152 and was wrong; see the next fact.)
- Verified: `*.data.socrata.com` hosts are public portals. `GET https://api.us.socrata.com/api/catalog/v1?domains=<host>&only=dataset&limit=0` returned `resultSetSize` 5 for albany.data.socrata.com, 25 for fortlauderdale.data.socrata.com, 17 for siouxfalls.data.socrata.com and 6 for atlanta.data.socrata.com, and `GET https://<host>/api/views.json?limit=1` returned HTTP 200 on each (2026-10-17, curl; the controller re-probed the same counts, and a re-run by this task is saved as `docs/evidence/feasibility-2026-10-17/data_socrata_com_hosts.json`).
- Verified: **enumeration returns catalog domains, not public hosts.** `data.seattle.gov` is absent from the list; `cos-data.seattle.gov` (147 datasets) is present. Without `search_context`, those datasets carry `metadata.domain` `cos-data.seattle.gov` and `link` hosts on `cos-data.seattle.gov`; with `search_context=data.seattle.gov` the same datasets come back with domain and link rewritten to `data.seattle.gov`. The other 19 sample hosts all appear in the list under their own name.

### Identity (which Discovery parameters select a portal)

Command: `uv run python scripts/feasibility/check_identity.py <20 sample hosts>` (output: `docs/evidence/feasibility-2026-10-17/identity.json`). Per host: three pages of `limit=100` for `domains=<host>` and `search_context=<host>`, each also for up to three catalog `link` hosts. "Match" means every result's `metadata.domain` equals the parameter value (`identity_matches`).

- Verified: `domains=<host>` and `search_context=<host>` both match, with equal `resultSetSize`, for data.cityofchicago.org (2,029), data.cityofnewyork.us (3,021), data.kingcounty.gov (539), datahub.austintexas.gov (2,287), www.dallasopendata.com (1,087), data.nola.gov (298), data.montgomerycountymd.gov (955), data.wa.gov (2,178), data.texas.gov (1,485), data.cdc.gov (1,477), data.calgary.ca (933), www.datos.gov.co (10,000, the cap), data.oregon.gov (1,591), data.honolulu.gov (453), and, in the EU region, opendata.camden.gov.uk (871).
- Verified: data.seattle.gov: `domains` returns 0, `search_context` returns 699 and matches; no single `domains` value on the public host works.
- Verified: data.sf.gov: both match, but `domains` returns 5 and `search_context` 1,225 (without `only=dataset`), so they select different sets.
- Verified: data.lacity.org: `domains` 927 matches; `search_context` 1,274 does not, the first 300 results being 250 `data.lacity.org` and 50 `controllerdata.lacity.org`.
- Verified: datacatalog.cookcountyil.gov: `domains` 809 matches; `search_context` 976 does not (268 `datacatalog.cookcountyil.gov`, 32 `cookcounty.data.socrata.com`).
- Verified: data.ny.gov: `domains` 1,638 matches; `search_context` 5,364 does not (133 `data.ny.gov`, 92 `data.cityofnewyork.us`, 75 `health.data.ny.gov` in the first 300).
- Verified: for the 20 sample hosts, `search_context=<host>` is a superset of the portal and can include other domains, while `domains=<host>` is exact except where the public host is not the catalog domain (Seattle). No single parameter works for all 20, so the registry must store the exact parameters per portal.
- Verified: anonymous `GET https://<host>/api/views.json?limit=1` returns 200 for 19 of the 20 sample hosts and **500** for datacatalog.cookcountyil.gov (reproduced twice). `GET https://<host>/resource/<id>.json?$limit=1` returned 200 with one row on all 20 public hosts, using the first dataset id from each catalog result.

### App token

- Unprobed: whether one `SOCRATA_APP_TOKEN` is honored on every domain and region. No token was available when this task ran (2026-10-17): `uv run python scripts/feasibility/check_token.py data.seattle.gov` printed `token: unavailable` and exited 0. Nothing is claimed about token portability.
- Unprobed (no token available, 2026-10-18): milestone 2 Task 14 found `SOCRATA_APP_TOKEN` still unset, so token portability was not run on the 20 sample hosts or the EU host. Nothing is claimed. `check_token.py` now classifies each host as `accepted`, `rejected_token`, `forbidden_other`, `unavailable` or `transport_error`; the classes are covered offline with a mock transport, not against a live portal.

## Milestone 0b feasibility probes (2026-10-17)

### tools/list budget

Command: `uv run python scripts/feasibility/budget_spike.py docs/evidence/feasibility-2026-10-17/budget.json` (output: `budget.json`). Size is counted as `tests/test_contract.py` counts it: compact JSON of the wire `tools/list` result, UTF-8 bytes.

- Verified: today's four-tool `tools/list` is 15,230 bytes (2026-10-17; `tests/test_contract.py` prints the same figure; the fork point `seattle-open-data` 26c6628, measured the same way on 2026-10-17, gives 15,303, re-measured offline from `git archive 26c6628` and saved as `docs/evidence/feasibility-2026-10-17/fork_tools_list_size.txt`; the 73-byte difference comes from changes since the fork and was not isolated further). With a required `portal` property on each of the four tools (66-byte description) and `atlas_find_portals` (2,337 bytes, written per design Tools 1 at the existing density) the list is 18,250 bytes, 6,326 under the 24,576 budget. This measures a hypothetical list only; the served surface and `tests/snapshots/tools_list.json` are unchanged.

### Engine against other portals

Command: `uv run python scripts/feasibility/compat_run.py docs/evidence/feasibility-2026-10-17/identity.json docs/evidence/feasibility-2026-10-17/compat.json` (output: `compat.json`). Per host, with an empty pack, `catalog_query` the `domains=<host>` value (else `search_context=<host>`) that `identity_matches` accepted, and the plumbing timezone `UTC` (not a fact about any portal; no time claims are made): `search` for "permits", `describe` (detail full) on the first queryable result, `query` page 1 (page_size 20) and page 2 through the cursor, and `select=["no_such_column_xyz"]` expecting `no_such_column`. Sequential, 0.5 s between portals, the engine's own deadlines and User-Agent.

- Verified: data.seattle.gov, data.cityofchicago.org, data.cityofnewyork.us, data.kingcounty.gov, datahub.austintexas.gov, www.dallasopendata.com, data.nola.gov, datacatalog.cookcountyil.gov, data.montgomerycountymd.gov, data.texas.gov, data.cdc.gov, data.calgary.ca, www.datos.gov.co and data.honolulu.gov pass all five steps (1.4-4.5 s each).
- Verified: data.ny.gov, data.oregon.gov and opendata.camden.gov.uk have no second page because the first dataset is small (19, 3 and 0 rows; `$select=count(*)` returned 19, 3 and 0 on each). These are data, not engine, outcomes. Camden's dataset is empty (0 rows), so for it row handling and paging were not exercised; data.ny.gov and data.oregon.gov exercised one page of rows.
- Verified, not retained: for 8 of the 15 short-page datasets (per `compat.json`: the other 7 were Seattle, King County, NOLA, Texas, Calgary, datos.gov.co, SF), namely Chicago 1, Austin 3, Honolulu 3, NYC 19, CDC 19, Cook County 12, Montgomery County 14 and LA 5 rows on a page of 20 while more existed, the same `query.run` call with only the first two columns selected returned a full 20 rows on every one (2026-10-17, ad hoc call of `query.run`, `page_size=20`; the output was not retained and needs the network to reproduce). So the engine's byte fit trimmed the page, not the data. The other 7 were not checked this way.
- Verified: data.sf.gov with `domains=data.sf.gov` returns no result for "permits" (`domains` selects 5 assets; `search_context=data.sf.gov&q=permits` returned 83). This is a data and registry outcome, not an engine one: the engine used the parameters it was given. With `search_context` the run passes search, describe and both query pages.
- Verified: **engine gap.** The forced error returns `soql_syntax_error` (upstream `query.soql.invalid`) instead of `no_such_column` on data.lacity.org, data.wa.gov and data.sf.gov (`compat.json`; Seattle returns `no_such_column` in the same run). Command: `PYTHONPATH=scripts/feasibility uv run python scripts/feasibility/no_such_column_probe.py docs/evidence/feasibility-2026-10-17/no_such_column_probe.json` (output: `no_such_column_probe.json`, 2026-10-17). The engine's own request, captured at the transport, is `GET /api/views/<id>.json` (200) then `GET /resource/<id>.json?$select=no_such_column_xyz, :id&$order=:id&$limit=6`, which answers HTTP 400 `query.soql.invalid` with empty `data` on all three hosts (LA k5qd-jg2c, WA yccr-zbpr, SF i98e-djp9). Single-variable probes against the same datasets: `$select=no_such_column_xyz` alone and `$select=no_such_column_xyz, :id` both return `query.soql.no-such-column`; adding `$order=:id` returns `query.soql.invalid`, with or without `:id` in `$select`. So the `$order=:id` clause turns the specific code into the generic one on these portals, and the engine's request contains it (keyset paging orders by `:id`). Why those portals' backends answer this way was not probed.
- Verified: no failure was a transport error, a timeout or an exception; every outcome above is either `ok`, an engine error code or a data result.

## Registry build (2026-10-18)

All **Verified** 2026-10-18 (UTC) with `scripts/build_registry.py` (sequential GETs, 0.2 s apart, 60 s timeout, `User-Agent: opendata-atlas-registry/0`, no token). The network run was `uv run python scripts/build_registry.py --out src/opendata_atlas/portals/registry.json --evidence docs/evidence/registry-2026-10-18/ --titles 60`, which took 1,186 s wall clock (`network-run.log`, the run's stderr with `/usr/bin/time -p`). The other runs were cached re-runs over the same evidence, including `--reprobe-views` on the eleven hosts named below; `docs/evidence/registry-2026-10-18/README.md` lists them. Counts are live and drift.

- Verified: deep scrolling still showed no cap. US: 43,333 datasets in 9 pages, all ids unique, 286 domains. EU: 5,447 in 2 pages, 12 domains. Both ended on a short page (`enumeration.json`), the same totals as on 2026-10-17.
- Verified: of 298 catalog domains, 263 pass the milestone 0 name rule and 35 do not (`summary.json` `ineligible_by_name`). The non-production rule (design Registry step 2) drops 9 more: al-amcc-uat, budget-qa-reporting, dot-edpsandbox, integration-kcmo (added by the `integration` token in the final re-review), lafayettecsdgovla-train, newjerseysp-dev, newjerseysp-uat, va-cca-uat and vtmbl-reporting-uat, all `*.data.socrata.com` (`summary.json` `non_production`). That leaves 254.
- Verified: identity resolved for all 263 name-eligible domains. `weho.data.socrata.com` had a short read on its first probe (`errors=1` at line 254 of `network-run.log`) and resolved on the retry. For every domain, `domains=<catalog domain>` matched on all results of the first three pages.
- Verified: `search_context=<catalog domain>` matched and had the larger `resultSetSize` for 11 registered portals, so they get `search_context` (`summary.json` `chosen_search_context`; Seattle's pack query is the twelfth entry there). data.sf.gov: `domains` 5 and `search_context` 1,225, both matching, so its `catalog_query` is `{"search_context": "data.sf.gov"}`. Others with a large gap: open.piercecountywa.gov 45 vs 2,537, nnps-odp.data.socrata.com 4 vs 1,374, data.mesaaz.gov 41 vs 1,213, data.sandiegocounty.gov 2 vs 620.
- Verified: `search_context` still returns other domains for data.lacity.org (1,274; 50 of the first 300 on `controllerdata.lacity.org`), datacatalog.cookcountyil.gov (976; 32 on `cookcounty.data.socrata.com`) and data.ny.gov (5,364). Those keep `domains` (927, 809 and 1,638).
- Verified: **no catalog domain's `link` fields name another host.** Across the first three `domains=` pages of all 263 domains, every `link` host equals the catalog domain. So no public-host candidate came from links, and no public host differs from its catalog domain (`summary.json` `public_host_differs` is empty). This includes `cos-data.seattle.gov`, with 300 of 300 links on `cos-data.seattle.gov`. Seattle's public host `data.seattle.gov` comes from its pack, which also names `cos-data.seattle.gov` in its `catalog_query`, so that domain was folded into the pack entry. The pack's query returns 699 assets, 147 of them datasets.
- Verified: anonymous `GET https://<host>/api/views.json?limit=1` (`summary.json` `ineligible_by_views` and `kept_on_views_5xx_or_timeout`; the first pass of the eleven re-probed hosts is in `probes.retries.jsonl`):
  - HTTP 404, dropped: data.fortworthtexas.gov and stat.montgomerycountymd.gov.
  - HTTP 200 with a body that is not JSON, dropped. The final URL after redirects is off Socrata:
    - data.oxnard.org → `https://oxnardca.opengov.com/data`
    - opendata.l-h.cat → `https://seu-e.cat/ca/web/hospitaletdellobregat/dades-obertes`
    - performance.austintexas.gov → an `experience.arcgis.com` page
    - performance.seattle.gov → `https://www.seattle.gov/innovation-and-performance`
  - `httpx.ConnectError`, dropped: data.miamigov.com, data.permits.performance.gov, data.urbanaillinois.us, performance.cityofdavenportiowa.com, performance.cityofrc.us and performance.providenceri.gov. The first pass recorded only status 0 for these; the re-probe recorded the class.
  - Kept: data.nhitc.org (`httpx.ConnectTimeout`, a timeout); datacatalog.cookcountyil.gov and data.delaware.gov (HTTP 500); opendata.fcgov.com (HTTP 503). Cook County's 500 matches milestone 0, so code that serves Cook County must not rely on `/api/views.json` listing.
- Verified: the registry has 242 entries: 254 production domains, minus 1 folded into the Seattle pack, minus 12 dropped by `/api/views`, plus the pack entry. No two domains share a public host.
- Verified: on the 61 hosts in `titles.json` (the 60 largest at the first fetch, plus performance.cityofcamas.us when the drops moved it to 60th), `/api/configurations.json?type=site_theme&defaultOnly=true&merge=true` and the home page both returned HTTP 200, and the home page had a `<title>`. `strings.site_title` is empty on performance.fultoncountyga.gov, and performance.seattle.gov has neither `strings.site_title` nor `strings.company`. On many portals one or both theme strings are the vendor default `Tyler Data & Insights`. On data.bayareametro.gov, nnps-odp.data.socrata.com and hub.dati.lombardia.it all three fields are vendor defaults, so those have no override name.

## Query syntax accepted upstream (reviewed 2026-10-18)

- (review) data.seattle.gov and data.lacity.org accept a select `AS` alias in `$where`. Not re-run by Claude; the milestone 2 Task 8 reviewer ran it. The column pre-check therefore treats an alias as in scope in every clause.
- (review) data.seattle.gov accepts double-quoted string literals (`type = "Aid Response"`) and spaced `::` casts (`type :: text`). Not re-run by Claude.

## Text equality on padded values (milestone 3 Task 7, 2026-10-18)

Two queries on LAPD NIBRS Offenses `k7nn-b2ep`, data.lacity.org, each run once through `SodaClient.soql` (`$query`, no token), one after another. Rows: `docs/evidence/hints-2026-10-18/lacity-hollywood.json`.

- Verified: SoQL `upper()` and `like` work on the text column `area_name`. `SELECT area_name, count(*) AS n WHERE upper(area_name) like '%HOLLYWOOD%' GROUP BY area_name ORDER BY n DESC` returned two space-padded values, `"N Hollywood         "` (26,723 rows) and `"Hollywood           "` (26,653 rows).
- Verified: `SELECT count(*) AS n WHERE area_name = 'Hollywood'` (unpadded) returned one row, `{"n": "0"}`. An ungrouped `count(*)` of nothing is a single zero row, not an empty page, which is why the zero-match hint treats that row as empty.
- Verified (Task 7 fix round 1, a third query, run once): a `like` pattern containing a doubled quote is accepted. `SELECT count(*) AS n WHERE upper(area_name) like '%O''BRIEN_%'` answered 200 with `[{"n": "0"}]`, which is the repair's form for the literal `O''Brien_`.

## Seattle time columns without timezone claims (milestone 2 Task 9, 2026-10-18)

- Verified: `GET https://data.seattle.gov/api/views/ppi5-g2bj.json` (Use of Force) lists one time-typed column, `occured_date_time` (`calendar_date`, spelled so upstream). The pack has no timezone claim for it, so the dataset stays below `reviewed` despite its unit-of-observation claim.
- Verified: `GET https://data.seattle.gov/api/views/egc4-d24i.json` (Road Weather Information Stations) has columns `stationname`, `stationlocation`, `datetime` (`calendar_date`), `recordid`, `roadsurfacetemperature`, `airtemperature`; the pack has no claim on it (recorded in `tests/fixtures/http/query_knowledge.json`).

## Compatibility through the tools (milestone 2 Task 13, 2026-10-18)

Command: `COMPAT_EVIDENCE_DIR=docs/evidence/compat-2026-10-18 uv run pytest --run-integration -m integration tests/test_compat_live.py -v` (output: `docs/evidence/compat-2026-10-18/`, with `outcomes.md` as the table; 21 passed, 1 xfailed, 74 s). The suite calls the MCP tools through the in-process client, over milestone 0's 20 sample portals by registry id, with each portal's registry `catalog_query`. For each portal it runs:

- `atlas_search_datasets` (`query: "permits"`, falling back to a browse when no result is tabular);
- `atlas_describe_dataset` (`detail: "full"`) on the first queryable result;
- `atlas_query_dataset` page 1 (`page_size: 20`) and page 2 through the cursor. When a dataset is empty or fits one page, describe and query move to the next queryable result, up to 3 results in all;
- `select: ["no_such_column_xyz"]`.

The portals ran one at a time, 0.5 s apart, with no token. A spy transport recorded every request. Saved bodies are redacted as the evidence README describes.

- Verified: all 20 sample hosts are registry ids. None was dropped by the registry's eligibility rules.
- Verified: 19 portals pass every step: data.seattle.gov, data.sf.gov, data.cityofchicago.org, data.cityofnewyork.us, data.kingcounty.gov, datahub.austintexas.gov, www.dallasopendata.com, data.lacity.org, data.nola.gov, datacatalog.cookcountyil.gov, data.montgomerycountymd.gov, data.wa.gov, data.ny.gov, data.texas.gov, data.cdc.gov, data.calgary.ca, www.datos.gov.co, data.honolulu.gov and opendata.camden.gov.uk. Every one found its dataset with the "permits" query; none needed the browse fallback. Each used its first queryable result, except Camden, whose first result `eqq9-intm` has 0 rows (`count(*)` returned 0, page 1 returned `[]`). Camden passed on its second result, `7hiv-3r9k` (8,848 rows).
- Verified: on all 20, the forced unknown column returns `no_such_column`, and no `/resource` request was sent during that call. This includes data.lacity.org, data.wa.gov and data.sf.gov, which returned `soql_syntax_error` in milestone 0. The same spy recorded `/resource` requests in the describe and query steps of every portal.
- Verified: **data outcome.** On data.oregon.gov, all three queryable results tried fit one page: `5fni-sp3g`, `hi9g-m7ts` and `j3rx-7bui`, with `count(*)` of 3, 1 and 7. Each page 1 `$limit=21` request returned that many rows. So page 2 was not exercised on Oregon.
- Verified: Cook County's describe succeeded (HTTP 200 from `/api/views/6yjf-dfxs.json`). The HTTP 500 that Task 2 saw on `/api/views.json?limit=1` did not affect this run.
- Verified: no engine failure. No step returned an error envelope other than the forced `no_such_column`, and every upstream response in the run was HTTP 2xx.
- Verified: the byte fit still trims some pages well below 20 rows while more exist. Page 1 returned 1 row on Chicago `ydr8-5enu` and 3 on Austin `3syk-w9eu`. Paging continued in each case (`outcomes.json`).
- Verified: catalog order drifts between runs. Camden's first "permits" result was `7hiv-3r9k` in one full run on 2026-10-18 and `eqq9-intm` in another. Neither run's output is retained, because both held unredacted personal data. The candidate fallback above is how the suite absorbs this.

## Seattle drift probes (milestone 3 Task 2, 2026-10-18)

Each query ran once through `SodaClient.soql` (`$query`, no token), one at a time. Rows: `docs/evidence/drift-2026-10-18/seattle-probes.json` and `fremont-reprobe.json`. Each probe is now a `soql_probe` evidence entry with an assertion on its claim, and the first drift run passed all of them (`docs/evidence/drift-2026-10-18/report.json`).

- Verified: placeholder share, where a placeholder is null or one of `''`, `-`, `0`, `FK ERROR`, `NULL`, `OOJ`, `UNKNOWN`, `X`:
  - SPD Crime Data `tazs-3rd5` `sector`: 11,379 of 1,568,849 rows (0.0073);
  - SPD Crime Data `tazs-3rd5` `beat`: 11,387 of 1,568,849 (0.0073);
  - Use of Force `ppi5-g2bj` `sector`: 2,728 of 19,457 (0.1402);
  - Use of Force `ppi5-g2bj` `beat`: 2,147 of 19,457 (0.1103).
  Each claim's `share_by_group` `max` is the observed share rounded up to 0.01, plus 0.02: 0.03, 0.03, 0.17 and 0.14. All four claims keep reliability `ok`, as reviewed. The probe does not show whether Use of Force's 11-14% placeholder share is spread across years or concentrated in some of them.
- Verified: on 2026-03-08, the 2026 US spring-forward date, Fire 911 `kzjm-xkqj` `datetime` and SPD Call Data `33kz-ixgy` `cad_event_original_time_queued` have no rows at hour 2. Hours 1 and 3 have 18 and 16 rows (Fire 911), and 73 and 69 rows (SPD Call Data).
- Verified: on the same date, Fremont Bridge `65db-xm6k` (one row per hour) has a 02:00 row whose `fremont_bridge`, `fremont_bridge_nb` and `fremont_bridge_sb` are all null. Its 01:00 and 03:00 rows total 26 and 20. So `sum(fremont_bridge)` grouped by hour returns an hour-2 group with no `n`, which `dst_gap` reads as an unparseable count (`inconclusive`). The pack's probe adds `AND fremont_bridge IS NOT NULL`. That drops only the all-null group and leaves every hour's sum unchanged.
- Verified: over 2025, row counts by hour of day peak at hour 16 (Fire 911, 6,552 of 119,299) and hour 12 (SPD Call Data, 34,363 of 572,296). Fremont Bridge's `sum(fremont_bridge)` peaks at hour 8 (118,390), with a second peak at hour 17 (112,077). All 24 hours are populated in each. Each claim's `diurnal_peak` window is the observed peak hour ± 2.

## Fire 911 response types (milestone 3 Task 5, 2026-10-18)

Queries on Fire 911 `kzjm-xkqj`, each run once through `SodaClient.soql` (`$query`, no token), one after another. Rows: `docs/evidence/drift-2026-10-18/fire-types.json`. Entries 3 and 4 are the `soql_probe` evidence of claim `kzjm-xkqj-unit`. The first carries the claim's assertion, and its drift runs passed.

- Verified: over all rows, the largest `type` values are Aid Response (1,078,085 rows) and Medic Response (349,671), then Auto Fire Alarm (126,703).
- The medical set is five types, chosen by name only (controller ruling 45): Aid Response, Aid Response Yellow (46,020), Medic Response, "Medic Response, 7 per Rule" (17,313) and Automatic Medical Alarm (19,954). These are the top-20 types whose name has "Aid" or "Medic". Trans to AMR, Nurseline/AMR, Low Acuity Response and Triaged Incident are not in it, because calling them medical would be an inference. The probes list the set as `type IN (...)`, so a new upstream type cannot silently join it.
- Verified: since 2020-01-01, the medical set is more than half of each year's rows: 0.5941 (2020), 0.5759 (2021), 0.5902 (2022), 0.5877 (2023), 0.5671 (2024: 73,513 of 129,629, the lowest), 0.6229 (2025) and 0.6612 (2026 to date). The claim asserts `min = 0.5` over at least 6 years.
- Verified: over all rows, the medical set is 1,511,044 of 2,216,831 (0.6816). That supports the inherited guide's "about two thirds", so the guide is unchanged. Aid Response and Medic Response alone are 1,427,756 of those rows (0.644, from the first query).
- (review) The five are not every medical type. A reviewer's live query, `SELECT type, count(*) AS n WHERE upper(type) like '%AID%' OR upper(type) like '%MEDIC%' GROUP BY type ORDER BY n DESC LIMIT 100`, returned about 65 types. Beyond the five, plainly medical ones include "Medic Response- 7 per Rule" (8,559), "Medic Response- Overdose" (7,230), "Medic Response, 6 per Rule" (6,652) and "Hang-Up, Aid" (5,475), about 40k more rows in all. Some matches, such as "Mutual Aid, Engine", are not medical. Not re-run by Claude. The shares above are therefore lower bounds; controller ruling 46 keeps the five-type set, because a lower bound is the safe direction for a `min` assertion.
- Superseded: entry 2 is the first per-year probe, which counted only Aid Response and Medic Response (lowest year 2024, 0.5485). It is kept as a record.

## Profiler run on data.lacity.org (milestone 3 Task 11, 2026-10-18)

All **Verified** 2026-10-18 (UTC). Raw outputs are in `docs/evidence/profile-2026-10-18/` (see its README). Counts are live and drift.

- Verified: `GET https://api.us.socrata.com/api/catalog/v1?domains=data.lacity.org&only=dataset&order=page_views_total&limit=3` returns HTTP 200 with 3 results whose `resource.page_views.page_views_total` descend (821,305; 456,799; 433,489), and `resultSetSize` 361. So `order=page_views_total` is accepted and sorts descending. Saved, with owner and contact identities redacted, as `docs/evidence/profile-2026-10-18/order-probe.json`.
- Verified: `uv run atlas-profile data.lacity.org --datasets 5` exited 0 in 43 s (the run after review fix round 1; `review_values` empty, `error` null), one request at a time (`report.json`):
  - All 300 results on the 3 identity pages (`domains=data.lacity.org`) carry `metadata.domain` `data.lacity.org`.
  - The `/domains/data.lacity.org/facets` `datatypes` facet is a list entry `{"facet": "datatypes", "values": [{"value", "count"}, ...]}`; it counted filter 419, dataset 361, chart 63, map 55, href 16, story 6, visualization 5 and file 2.
  - The 5 flagships: 6rrh-rzua (Listing of Active Businesses), 2nrs-mtv8 (Crime Data from 2020 to 2024), dik5-hwp6 (LAX Parking Lots Current Status), 4ca8-mxuh (Addresses in the City of Los Angeles), 63jg-8b9z (Crime Data from 2010 to 2019).
  - 10 claims, all asserted. 6rrh-rzua has six computed-region columns with fill rates from 0.232 to 0.826. Every one of its layers has `_feature_id_string` as its first text column (re-probed: `layer-columns.json`), so the label-column rule skips feature-id columns; the candidates are `zcta5ce10`, `name` (twice), `slug`, `cnsld` and `spa_nm`. Both crime datasets have `X` and `-` in `vict_sex` and `vict_descent`.
  - Five time columns got spring-forward probes: 6rrh-rzua `location_start_date`, and `date_rptd` and `date_occ` in both crime datasets. In both probes (2026-03-08, and the last 365 days of data) every row of each is at hour 0: the values are dates stored at midnight. Each is noted "<col>: date-only; no timezone test applies.", with no `column_timezone` claim (ruling 52). dik5-hwp6's `min` and `max` were the same day, so it has no spring-forward day; 4ca8-mxuh has no time-typed column.
  - Most text columns had more than 100 groups and were skipped. None of the 5 has a padded categorical column.
- Verified: re-running `drift.check_claim` on the draft's 10 asserted claims, one at a time, gave `passed` for all 10 (`recheck.json`).

## Weekday numbering of `date_extract_dow` (milestone 5 standards review, 2026-10-19)

One SoQL query on Fire 911 `kzjm-xkqj` (`/resource/kzjm-xkqj.json`, no token), grouping 2026-10-11 to 2026-10-17 by `date_trunc_ymd(datetime)` and `date_extract_dow(datetime)`. Command and rows: `docs/evidence/standards-m5-2026-10-19/dow-probe.sh.txt` and `dow-probe.json`.

- Verified: `date_extract_dow` returns 0 for Sunday through 6 for Saturday, as a JSON string (`"0"`). Each of the 7 days matched its calendar weekday (2026-10-11, a Sunday, is `"0"`). Python's `date.weekday()` numbers Monday 0, so the two conventions differ by one day. The capability rule on weekdays and the `dates` topic give this numbering.
