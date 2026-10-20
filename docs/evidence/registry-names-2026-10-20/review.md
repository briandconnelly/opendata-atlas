# Registry name review (milestone 6, Task 2)

The registry was rebuilt on 2026-10-20 (UTC) with the site-title name rule (`title_name` in `scripts/build_registry.py`), and each generated name was reviewed by hand. This page has the build, the diff check, every generated name with its verdict, and the surface checks. Date: the build's UTC date (registry version `2026-10-20-…`); local time was 2026-10-19 PDT.

## Build

The command, run with the enumeration and probes cached (no `--refresh`):

```
uv run python scripts/build_registry.py --out src/opendata_atlas/portals/registry.json --evidence docs/evidence/registry-2026-10-18/ --titles all
```

- First run: exit 0 after 671.3 s. It fetched the titles of every portal that had no `titles.json` record, so `titles.json` went from 61 records to 242: one per registry entry apart from the two packs, plus `performance.seattle.gov`, which was already cached.
- One fetch failed. `data.nhitc.org` has `site_theme_status: 0` and `home_status: 0`, and every title field is null, so it keeps its host. The cache keeps that record; only `--refresh` fetches it again.
- Two re-runs with the overrides below fetched nothing: the logs have no `title` lines and only the summary line.

## Diff check (Step 4)

The shipped `registry.json` compared with the one from before this task, by id:

```
version: 2026-10-18-90a6d6060a2d -> 2026-10-20-5bcfa38b2156
entries: 242 -> 242
dropped: []
added: []
changed fields: identity.name 97, identity.tier 1, and the Step 6 fields of data.everettwa.gov,
  data.kingcounty.gov (aliases, place_names, jurisdiction, timezone) and data.nj.gov (place_names,
  jurisdiction, timezone)
NON-NAME: data.cityofchicago.org identity.tier generic -> curated
```

The 97 name changes are the 99 generated names minus the 2 rejects, which keep the host name they already had.

### Chicago's tier (accepted by controller ruling 1)

- **Cause.** The committed `registry.json` was last built in milestone 2 (06a3c76). That was before the Chicago pack existed (5a2a9c8) and before Chicago was promoted to curated (ef2e9bf), and before Chicago's override was removed when its pack took over.
- **What the rebuild does.** This is the first rebuild since then, and it folds the entry into its pack:
  - `probes.jsonl` gains one live pack probe, `{"kind":"pack","id":"data.cityofchicago.org", ...}` (2026-10-20T00:58:51Z, `result_set_size` 2029, `errors` 0). `catalog_size` and `dataset_count` are unchanged.
  - In `summary.json`, `folded_into_pack` goes from 1 to 2 (it adds `"data.cityofchicago.org"`) and `overrides` goes from 50 to 49 before this task's overrides, 58 after.
  - Chicago leaves `top50_by_catalog_size`. That lets `data.nj.gov` (622) into the 50, and `top50_without_override` became `["data.nj.gov"]`.
- **Fix for the 50.** Override 51 covers `data.nj.gov` (controller ruling 2). After the rebuild, `summary.json` has `top50_without_override: []` and 50 entries in `top50_by_catalog_size`.
- **Served identity unchanged.** `load_registry` overlays each pack's identity at load time, so what the server serves does not change. Check:

  ```
  uv run python -c "
  from pathlib import Path
  from opendata_atlas.portals.registry import load_registry
  a=load_registry(Path('<scratchpad>/m6/registry-before.json'), None); b=load_registry(Path('src/opendata_atlas/portals/registry.json'), None)
  for i in ('data.cityofchicago.org','data.seattle.gov'):
      print(i, 'served identity equal:', a.entries[i]==b.entries[i], b.entries[i].identity.tier)"
  data.cityofchicago.org served identity equal: True curated
  data.seattle.gov served identity equal: True curated
  ```

- **Two tests changed.** They assumed Seattle was the only pack-backed entry in the registry file:
  - `tests/test_search_domain.py`: a pack record with a probed `identity` must have seen only that entry's `result_domain`.
  - `tests/test_tiers.py`: the known-positive test excludes the real pack ids.

## Counts

There are 242 entries: 2 packs, 46 that already had override names, and 194 portals the rule named:

- **Named from the title: 99.** Reviewed by hand:
  - **ok**: 93
  - **reject**: 2
  - **rename**: 4
- **No name: 95.** The title gives nothing usable, so the host stays:
  - 91 have only vendor defaults (`Tyler Data & Insights`, `Catalog | Tyler Data & Insights`);
  - `controllerdata.lacity.org` says only "Open Data";
  - `mischooldata.data.socrata.com` says only "Open Data Portal | Rally - Open Data Portal";
  - `opendata.fcgov.com` says "This site has moved";
  - `data.nhitc.org` failed to fetch.

Shipped names:

| Source | Portals |
| --- | --- |
| Generated | 90 |
| Override | 53 |
| Override, set to the host (reject) | 2 |
| Pack identity | 2 |
| Host | 95 |

Three of the 99 ok names are replaced by Step 6 and ruling 2 overrides: Everett, King County and New Jersey.

## Rejects and renames

| id | Generated name | Verdict | Reason |
| --- | --- | --- | --- |
| `healthdata.nj.gov` | Making Data Social | reject (host) | reads as the vendor's tagline (`site_company` is "Socrata"; not probed further); no title field names the owner |
| `cookcounty.data.socrata.com` | Cook County Open Data | reject (host) | As a name match, it ranks this 10-dataset site above `datacatalog.cookcountyil.gov` (523 datasets, override 41) for "Cook County" by id tie-break. It failed the pinned `test_shipped_registry_alias_and_county`. The title has no other part. As host, it still matches "Cook County" by host label, after the county's portals |
| `bythenumbers.sco.ca.gov` | Government Financial Reports | rename: California State Controller’s Office | Read as a vendor app's name, an inference (not probed) from the same string, as "Government Financial Reports App", heading two unrelated portals' titles; the owner is in the same title |
| `performance.franklintn.gov` | Government Financial Reports App | rename: FranklinForward: City's Strategic Plan Website | Read as a vendor app's name (inferred, not probed; see above) |
| `reports.cdp.net` | Government Financial Reports App | rename: CDP Performance Dashboard | Read as a vendor app's name (inferred, not probed; see above); `site_company` names the portal |
| `health.data.ny.gov` | State of New York | rename: New York State Department of Health | Identical to `data.ny.gov`'s name, so it reads as the state's general portal; `site_company` names the department |

Each of these is a `registry_overrides.toml` entry (52 to 57) with a comment quoting its `titles.json` record.

## Overrides added

- **51 `data.nj.gov`.** Name "New Jersey's Open Data Center" (its `site_company`), place `New Jersey`, state NJ, `America/New_York`. Ruling 2.
- **58 `data.everettwa.gov`.** Name "City of Everett", alias `everett`, places `Everett` and `Everett, WA`, city WA, `America/Los_Angeles`.
- **59 `data.kingcounty.gov`.** Name "King County", alias `king-county`, places `King County` and `King County, WA`, county WA, `America/Los_Angeles`. It has no "Seattle".

## Kept, with ranking notes

These names are their owner's own, so each is **ok**. Each still affects ranking, because a name match ties on tier and the tie goes to the id:

- "Buffalo" lists `covid19.buffalony.gov` ("Buffalo, NY") before `data.buffalony.gov` ("OpenData Buffalo").
- "Hawaii" lists `hidot-contracts.data.socrata.com` before `highways.hidot.hawaii.gov`. Both have the title "State of Hawaii Department of Transportation".
- Two Janesville portals are both "City of Janesville".

## Surface checks (Step 8, live, in-process client)

`atlas_find_portals {}`:

```
{"isError": false, "candidates[:3]": [{"id": "data.cityofchicago.org", "aliases": ["chicago"], "name": "City of Chicago", "tier": "curated", ...}, {"id": "data.seattle.gov", "aliases": ["seattle"], "name": "City of Seattle", "tier": "curated", ...}, {"id": "al-amcc.data.socrata.com", "name": "al-amcc.data.socrata.com", "tier": "generic", "dataset_count": 1}], "has_more": true, "count": 10}
```

The whole result is 4,716 bytes as JSON.

`atlas_find_portals {"query": "Everett"}`:

```
{"isError": false, "candidates": [{"id": "data.everettwa.gov", "aliases": ["everett"], "name": "City of Everett", "jurisdiction": {"level": "city", "country": "US", "region": "WA"}, "tier": "generic", "timezone": "America/Los_Angeles", "dataset_count": 122, "match": "alias"}], "has_more": false}
```

`atlas_search_datasets {"portal": "everett", "query": "permits"}`:

```
isError: false; 4 datasets: 3w3u-656c "Trakit Permits", c6k3-mamn "Permit First Review By Tier", 367s-q74n "Trakit Permits ADU", sp4j-mtnr "Underground Storage Tank Decommissioning"
source.portal: {"id": "data.everettwa.gov", "alias": "everett", "name": "City of Everett", "tier": "generic", "timezone": "America/Los_Angeles"}, retrieved_at 2026-10-20T01:16:16Z
```

## Every generated name

The table quotes the title fields as recorded in `titles.json`, with whitespace collapsed; a `\|` in a cell is the title's own ` | `.

| id | site_title | site_company | html_title | generated name | verdict | note |
| --- | --- | --- | --- | --- | --- | --- |
| `albany.data.socrata.com` | "Tyler Data & Insights" | "Tyler Data & Insights" | "Catalog \| City of Albany" | "City of Albany" | ok |  |
| `bronx.lehman.cuny.edu` | "Bronx Information Portal \| Lehman College" | "Lehman College" | "Lehman College Community Connect: Bronx Information Portal \| Bronx Information Portal \| Lehman College" | "Lehman College Community Connect: Bronx Information Portal" | ok |  |
| `bythenumbers.sco.ca.gov` | "Open Data Portal" | "Tyler Data & Insights" | "Government Financial Reports - California State Controller’s Office \| CA Local Government Financial Data" | "Government Financial Reports" | rename: California State Controller’s Office | "Government Financial Reports" reads as a vendor app's name, inferred (not probed) from the same string on performance.franklintn.gov and reports.cdp.net, not the owner (override 54) |
| `carsoncity.data.socrata.com` | "Performance Carson City Dashboard" | "Tyler Data & Insights" | "Performance Carson City Dashboard \| Performance Carson City Dashboard" | "Performance Carson City Dashboard" | ok |  |
| `celebratingcities.data.socrata.com` | "Open Data Portal" | "Tyler Data & Insights" | "Data \| Celebrating Cities \| Open Data Portal" | "Celebrating Cities" | ok |  |
| `cookcounty.data.socrata.com` | "Tyler Data & Insights" | "Tyler Data & Insights" | "Cook County Open Data" | "Cook County Open Data" | reject: name = host | would rank this 10-dataset site above datacatalog.cookcountyil.gov (523 datasets) for "Cook County", by id tie-break; failed `test_shipped_registry_alias_and_county` (override 53) |
| `corstat.coronaca.gov` | "Tyler Data & Insights" | "Tyler Data & Insights" | "Open Data Portal \| Corona Open Performance" | "Corona Open Performance" | ok |  |
| `covid19.buffalony.gov` | "Tyler Data & Insights" | "Tyler Data & Insights" | "COVID-19 \| Buffalo, NY" | "Buffalo, NY" | ok | ranks above data.buffalony.gov for "Buffalo" (both name matches; id tie-break); both are listed |
| `cthru.data.socrata.com` | "Tyler Data & Insights" | "Tyler Data & Insights" | "Catalog \| CTHRU" | "CTHRU" | ok |  |
| `dashboard.plano.gov` | "Tyler Data & Insights" | "Tyler Data & Insights" | "City of Plano \| Open Data Portal" | "City of Plano" | ok |  |
| `data.auburnwa.gov` | "Auburn Open Data" | "City of Auburn" | "Auburn Open Data \| Auburn Open Data" | "City of Auburn" | ok |  |
| `data.bloomington.in.gov` | "Tyler Data & Insights" | "Tyler Data & Insights" | "City of Bloomington Open Data" | "City of Bloomington Open Data" | ok |  |
| `data.brla.gov` | "Open Data BR" | "City of Baton Rouge" | "City of Baton Rouge - Open Data Portal \| Open Data BR" | "City of Baton Rouge" | ok |  |
| `data.bts.gov` | "Tyler Data & Insights" | "Tyler Data & Insights" | "BTS Data Inventory" | "BTS Data Inventory" | ok |  |
| `data.buffalony.gov` | "Rally - Open Data Portal" | "Tyler Data & Insights" | "Open Data Portal \| OpenData Buffalo" | "OpenData Buffalo" | ok |  |
| `data.cambridgema.gov` | "Open Data \| City of Cambridge" | "City of Cambridge" | "Open Data \| City of Cambridge \| Open Data Portal \| City of Cambridge" | "City of Cambridge" | ok |  |
| `data.cdp.net` | "CDP Open Data Portal" | "CDP Open Data Portal" | "CDP Open Data Portal \| CDP Open Data Portal" | "CDP Open Data Portal" | ok |  |
| `data.cincinnati-oh.gov` | "Tyler Data & Insights" | "Tyler Data & Insights" | "Cincinnati Open Data Portal \| Tyler Data & Insights" | "Cincinnati Open Data Portal" | ok |  |
| `data.cityofberkeley.info` | "Open Data \| City of Berkeley" | "City of Berkeley" | "City of Berkeley - Open Data Portal \| Open Data \| City of Berkeley" | "City of Berkeley" | ok |  |
| `data.cityofgainesville.org` | "Open Data Portal" | "City of Gainesville" | "Open Data Portal \| dataGNV \| Open Data" | "City of Gainesville" | ok |  |
| `data.cityoforlando.net` | "City of Orlando Open Data Portal" | "Tyler Data & Insights" | "City of Orlando Open Data Portal \| City of Orlando Open Data Portal" | "City of Orlando Open Data Portal" | ok |  |
| `data.countyofriverside.us` | "Riverside County Open Data" | "Tyler Data & Insights" | "Riverside County Open Data \| Riverside County Open Data" | "Riverside County Open Data" | ok |  |
| `data.cstx.gov` | "Open Data Portal" | "Tyler Data & Insights" | "College Station - Open Data \| CSTX Open Data" | "College Station" | ok |  |
| `data.datacenterresearch.org` | "Tyler Data & Insights" | "Tyler Data & Insights" | "The Data Center" | "The Data Center" | ok |  |
| `data.delaware.gov` | "Delaware Data - Delaware.gov: Official Website of the State of Delaware" | "Tyler Data & Insights" | "Delaware Data - Delaware.gov: Official Website of the State of Delaware \| Delaware Open Data Portal" | "Delaware Data" | ok |  |
| `data.energystar.gov` | "ENERGY STAR Certified Products \| US Environmental Protection Agency" | "data.energystar.gov" | "ENERGY STAR Product Finder API & Datasets \| EPA ENERGY STAR" | "ENERGY STAR Product Finder API & Datasets" | ok |  |
| `data.everettwa.gov` | "Tyler Data & Insights" | "Tyler Data & Insights" | "City of Everett Open Data" | "City of Everett Open Data" | ok | superseded by the Step 6 curation override "City of Everett" (58) |
| `data.framinghamma.gov` | "Rally - Open Data Portal" | "Tyler Data & Insights" | "Rally \| Open Data Portal \| Open Data Framingham" | "Open Data Framingham" | ok |  |
| `data.fultoncountyga.gov` | "Open Data Portal" | "Tyler Data & Insights" | "Fulton County Open Data" | "Fulton County Open Data" | ok |  |
| `data.honolulu.gov` | "Honolulu - Open Data Portal" | "Tyler Data & Insights" | "Honolulu - Open Data Portal \| Honolulu - Open Data Portal" | "Honolulu" | ok |  |
| `data.kcmo.org` | "Open Data \| data.kcmo.org" | "City of Kansas City, Mo." | "Open Data KC \| data.kcmo.org" | "City of Kansas City, Mo." | ok |  |
| `data.kingcounty.gov` | "King County \| Open Data" | "King County" | "King County \| Open Data" | "King County" | ok | Step 6 curation override keeps "King County" (59) |
| `data.macoupincountyil.gov` | "Open Data Portal" | "Macoupin County, IL" | "Macoupin Open Data Portal \| Open Data \| Macoupin County" | "Macoupin County" | ok |  |
| `data.marincounty.gov` | "County of Marin \| Open Data Portal" | "Tyler Data & Insights" | "County of Marin - Open Data Portal \| County of Marin Open Data Portal" | "County of Marin" | ok |  |
| `data.mmcp.ms.gov` | "Tyler Data & Insights" | "Tyler Data & Insights" | "Mississippi Medical Cannabis Program" | "Mississippi Medical Cannabis Program" | ok |  |
| `data.mo.gov` | "data.mo.gov \| State of Missouri Data Portal" | "data.mo.gov" | "Catalog \| data.mo.gov \| State of Missouri Data Portal" | "State of Missouri Data Portal" | ok |  |
| `data.modestogov.com` | "Tyler Data & Insights" | "Tyler Data & Insights" | "Modesto City View" | "Modesto City View" | ok |  |
| `data.montgomeryschoolsmd.org` | "MCPS - Open Data Portal" | "Tyler Data & Insights" | "MCPS - Open Data Portal \| MCPS - Open Data Portal" | "MCPS" | ok |  |
| `data.napacounty.gov` | "Tyler Data & Insights" | "Tyler Data & Insights" | "Napa County HHSA Open Data Portal" | "Napa County HHSA Open Data Portal" | ok |  |
| `data.nj.gov` | "Rally - Open Data Portal" | "New Jersey's Open Data Center" | "Open Data Portal \| NJOIT Open Data Center" | "NJOIT Open Data Center" | ok | superseded by the top-50 override "New Jersey's Open Data Center" (51, ruling 2) |
| `data.nola.gov` | "Data.NOLA.gov \| Enabling New Orleans" | "Data.NOLA.gov" | "Home - DataDriven - City of New Orleans" | "City of New Orleans" | ok |  |
| `data.norfolk.gov` | "Open Data Portal" | "Tyler Data & Insights" | "City of Norfolk Data \| Open Data Portal - City of Norfolk, VA Open Data" | "City of Norfolk Data" | ok |  |
| `data.oce.pr.gov` | "OCEPR - Open Data" | "Tyler Data & Insights" | "OCEPR - Open Data \| OCE Open Data" | "OCEPR" | ok |  |
| `data.orcities.org` | "Open Data Portal" | "League of Oregon Cities" | "LOC Open Data Portal \| Open Data Portal" | "LOC Open Data Portal" | ok |  |
| `data.princegeorgescountymd.gov` | "Tyler Data & Insights" | "Tyler Data & Insights" | "OpenPGC \| Open Data \| Tyler Data & Insights" | "OpenPGC" | ok |  |
| `data.providenceri.gov` | "Tyler Data & Insights" | "Tyler Data & Insights" | "Open Data \| City of Providence \| Open Data \| City of Providence" | "City of Providence" | ok |  |
| `data.readingpa.gov` | "Reading - Open Data Portal" | "Tyler Data & Insights" | "Open Reading \| Open Data Reading" | "Open Reading" | ok |  |
| `data.richmondgov.com` | "City of Richmond \| Open Data Portal" | "Tyler Data & Insights" | "Open Data Portal \| City of Richmond, Virginia \| Open Data Portal \| City of Richmond, Virginia" | "City of Richmond, Virginia" | ok |  |
| `data.roseville.ca.us` | "Open Data \| City of Roseville" | "City of Roseville" | "Roseville \| Open Data \| Open Roseville - City of Roseville" | "City of Roseville" | ok |  |
| `data.sandiegocounty.gov` | "Open Data Portal" | "San Diego County Data Portal" | "County of San Diego \| Open Data Portal \| Open Data Portal" | "County of San Diego" | ok |  |
| `data.smcgov.org` | "Open Data \| San Mateo County" | "San Mateo County Open Data" | "San Mateo \| Open Data \| Open San Mateo County" | "Open San Mateo County" | ok |  |
| `data.somervillema.gov` | "City of Somerville, MA" | "City of Somerville, MA" | "City of Somerville, MA" | "City of Somerville, MA" | ok |  |
| `data.sonomacounty.ca.gov` | "Open Data \| Sonoma County" | "Sonoma County" | "County of Sonoma \| Open Data \| Open Data \| Sonoma County" | "County of Sonoma" | ok |  |
| `data.sustainablesm.org` | "Santa Monica Sustainable City Plan" | "Tyler Data & Insights" | "Santa Monica Sustainable City Plan \| Santa Monica Sustainable City" | "Santa Monica Sustainable City Plan" | ok |  |
| `data.tompsc.com` | "Mount Pleasant, SC \| eMPower" | "Tyler Data & Insights" | "Mount Pleasant, SC \| eMPower \| Mount Pleasant, SC \| eMPower" | "Mount Pleasant, SC" | ok |  |
| `data.transportation.gov` | "Department of Transportation - Data Portal" | "Data.Transportation.gov" | "Department of Transportation - Open Data Portal \| Department of Transportation - Data Portal" | "Department of Transportation" | ok |  |
| `data.vermont.gov` | "Open Data \| State of Vermont" | "State of Vermont" | "Vermont \| Open Data \| Open Data \| State of Vermont" | "State of Vermont" | ok |  |
| `data.waterpointdata.org` | "Open Data Portal" | "Tyler Data & Insights" | "Water Point Data Exchange - Data \| WPDx \| The Water Point Data Exchange is the global platform for sharing water point data" | "Water Point Data Exchange" | ok |  |
| `data.wcad.org` | "Tyler Data & Insights" | "Tyler Data & Insights" | "WCAD Open Data" | "WCAD Open Data" | ok |  |
| `data.weho.org` | "Open Data \| City of West Hollywood" | "City of West Hollywood" | "Open Data \| West Hollywood \| Open Data \| City of West Hollywood" | "City of West Hollywood" | ok |  |
| `data.winnipeg.ca` | "Open Data \| City of Winnipeg" | "City of Winnipeg" | "Open Data Portal \| Open Data \| City of Winnipeg" | "City of Winnipeg" | ok |  |
| `dataacademy.maryland.gov` | "Tyler Data & Insights" | "Tyler Data & Insights" | "Data Academy" | "Data Academy" | ok |  |
| `datadiscovery.nlm.nih.gov` | "National Library of Medicine \| National Institutes of Health \| Open Data Portal" | "National Library of Medicine" | "Catalog \| National Library of Medicine \| National Institutes of Health \| Open Data Portal" | "National Library of Medicine" | ok |  |
| `datahub.usac.org` | "Tyler Data & Insights" | "Tyler Data & Insights" | "USAC \| Data Hub" | "USAC" | ok |  |
| `datainsights.encinitasca.gov` | "Tyler Data & Insights" | "Tyler Data & Insights" | "Encinitas Data & Insights \| City of Encinitas" | "City of Encinitas" | ok |  |
| `datamgmt.nassaucountyny.gov` | "Tyler Data & Insights" | "Tyler Data & Insights" | "Open Nassau (Internal)" | "Open Nassau (Internal)" | ok | "(Internal)" is in the owner's own title |
| `dubuque.data.socrata.com` | "Open Data Portal" | "Tyler Data & Insights" | "Open Data Portal \| Open Data Portal \| Dubuque, IA" | "Dubuque, IA" | ok |  |
| `educationtocareer.data.mass.gov` | "Tyler Data & Insights" | "E2C Hub" | "E2C Hub" | "E2C Hub" | ok |  |
| `fiscalfocus.pittsburghpa.gov` | "Tyler Data & Insights" | "Tyler Data & Insights" | "Fiscal Focus Pittsburgh" | "Fiscal Focus Pittsburgh" | ok |  |
| `fortlauderdale.data.socrata.com` | "City of Fort Lauderdale Police Department" | "City of Fort Lauderdale Police Department" | "City of Fort Lauderdale Police Department \| Performance Management \| City of Fort Lauderdale Police Department" | "City of Fort Lauderdale Police Department" | ok |  |
| `fusioncenter.nhit.org` | "Tyler Data & Insights" | "NHIT Data Fusion Center" | "NHIT Data Fusion Center®" | "NHIT Data Fusion Center®" | ok |  |
| `health.data.ny.gov` | "State of New York \| Open Data" | "New York State Department of Health \| Health Data NY" | "State of New York \| Open Data Health \| State of New York" | "State of New York" | rename: New York State Department of Health | "State of New York" is data.ny.gov's name (override 21); this is the Department of Health's portal (override 57) |
| `healthdata.nj.gov` | "Socrata \| Making Data Social" | "Socrata" | "Catalog \| Socrata \| Making Data Social" | "Making Data Social" | reject: name = host | reads as the vendor's tagline (`site_company` is "Socrata"; not probed further); no title field names the owner (override 52) |
| `hidot-contracts.data.socrata.com` | "Tyler Data & Insights" | "Tyler Data & Insights" | "State of Hawaii Department of Transportation" | "State of Hawaii Department of Transportation" | ok | same title as highways.hidot.hawaii.gov (override 20), same owner |
| `highlandsranch.data.socrata.com` | "Tyler Data & Insights" | "Tyler Data & Insights" | "Catalog \| Highlands Ranch Metro Area \| Socrata Data Cloud" | "Highlands Ranch Metro Area" | ok |  |
| `impact.stlouisco.com` | "Rally - Open Data Portal" | "Tyler Data & Insights" | "Impact STLCO \| Rally - Open Data Portal" | "Impact STLCO" | ok |  |
| `insights.cincinnati-oh.gov` | "Tyler Data & Insights" | "Tyler Data & Insights" | "CincyInsights" | "CincyInsights" | ok |  |
| `janesville.data.socrata.com` | "Tyler Data & Insights" | "Tyler Data & Insights" | "Park Place Performs! - City of Janesville" | "City of Janesville" | ok | same title as performance.ci.janesville.wi.us, same owner |
| `metroairports.data.socrata.com` | "MAC Sustainability" | "MAC Sustainability" | "MAC Sustainability \| Sustainability - Metro Airports" | "MAC Sustainability" | ok |  |
| `mi-treasury.data.socrata.com` | "Tyler Data & Insights" | "Tyler Data & Insights" | "Catalog \| MICommunity Financial Dashboard" | "MICommunity Financial Dashboard" | ok |  |
| `moreno-valley.data.socrata.com` | "Open Data \| City of Moreno Valley" | "City of Moreno Valley" | "Catalog \| Open Data \| City of Moreno Valley" | "City of Moreno Valley" | ok |  |
| `nyc-scgc.data.socrata.com` | "Tyler Data & Insights" | "Tyler Data & Insights" | "NYC SCGC" | "NYC SCGC" | ok |  |
| `opendata.cityofmesquite.com` | "Mesquite Texas \| Open Data Portal" | "Tyler Data & Insights" | "Mesquite Texas \| Open Data Portal \| Mesquite Texas \| Open Data Portal" | "Mesquite Texas" | ok |  |
| `opendata.clermontauditor.org` | "Tyler Data & Insights" | "Tyler Data & Insights" | "Open Data \| Clermont Auditor" | "Clermont Auditor" | ok |  |
| `opendata.fcc.gov` | "Data \| Federal Communications Commission" | "opendata.fcc.gov" | "Catalog \| Data \| Federal Communications Commission" | "Federal Communications Commission" | ok |  |
| `opendata.howardcountymd.gov` | "Open Data Portal" | "Tyler Data & Insights" | "Howard County - Open Data Portal \| Open Data Portal" | "Howard County" | ok |  |
| `opendata.rdw.nl` | "Open Data \| RDW" | "RDW" | "Open Data \| RDW \| Open Data \| RDW" | "RDW" | ok |  |
| `openperformance.edmonton.ca` | "City of Edmonton Citizen Dashboard" | "City of Edmonton Open Performance" | "Open Performance Landing Page \| City of Edmonton Open Performance" | "City of Edmonton Open Performance" | ok |  |
| `parkeronline.data.socrata.com` | "Tyler Data & Insights" | "Tyler Data & Insights" | "Catalog \| Town of Parker, CO - Finance Data Portal" | "Town of Parker, CO" | ok |  |
| `parksreporting.parks.ca.gov` | "Tyler Data & Insights" | "Tyler Technologies" | "California Parks Reporting Platform" | "California Parks Reporting Platform" | ok |  |
| `performance.ci.janesville.wi.us` | "Tyler Data & Insights" | "Tyler Data & Insights" | "Park Place Performs! - City of Janesville" | "City of Janesville" | ok | same title as janesville.data.socrata.com, same owner |
| `performance.cityofcamas.us` | "Open Data Portal" | "Tyler Data & Insights" | "Open Data Portal \| Camas Performance" | "Camas Performance" | ok |  |
| `performance.cookcountyil.gov` | "Tyler Data & Insights" | "Tyler Data & Insights" | "Cook County Performance" | "Cook County Performance" | ok |  |
| `performance.franklintn.gov` | "Tyler Data & Insights" | "Tyler Data & Insights" | "Government Financial Reports App \| FranklinForward: City's Strategic Plan Website" | "Government Financial Reports App" | rename: FranklinForward: City's Strategic Plan Website | "Government Financial Reports App" reads as a vendor app's name, inferred, not probed (override 55) |
| `policeview.johnscreekga.gov` | "Johns Creek Police Department \| Performance Management" | "Tyler Data & Insights" | "Johns Creek Police Department \| Performance Management \| Johns Creek Police Department \| Performance Management" | "Johns Creek Police Department" | ok |  |
| `ptsd-va.data.socrata.com` | "Tyler Data & Insights" | "Tyler Data & Insights" | "PTSD Repository" | "PTSD Repository" | ok |  |
| `reports.cdp.net` | "Tyler Data & Insights" | "CDP Performance Dashboard" | "Government Financial Reports App \| 2015 Live City Reporting" | "Government Financial Reports App" | rename: CDP Performance Dashboard | "Government Financial Reports App" reads as a vendor app's name, inferred, not probed (override 56) |
| `transparencyarchive.michigan.gov` | "MI Transparency - State Expenditures" | "Tyler Data & Insights" | "MI Transparency - State Expenditures \| MI Transparency - State Expenditures" | "MI Transparency" | ok |  |
| `www.thedatazone.ca` | "datazONE \| PVSC" | "Tyler Data & Insights" | "datazONE \| PVSC \| DatazONE \|" | "datazONE" | ok |  |
