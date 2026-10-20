# Task 32 probe, 2026-10-19

In-process tool calls (`skills/curate-portal/SKILL.md`, Context: Tool calls) on `feat/more-portals` at 2c4bbca, run 2026-10-19 about 20:27 Pacific (`now_local` 2026-10-19T20:27:32-07:00, so "last month" is September 2026). Short results only; no row values beyond city names and counts.

| Call | Arguments (abridged) | Result |
| --- | --- | --- |
| `atlas_find_portals` | `{"query": "Seattle"}` | `data.seattle.gov` (curated) only |
| `atlas_find_portals` | `{"query": "King County"}` | `data.kingcounty.gov` (profiled) only |
| `atlas_search_datasets` | `seattle`, "food establishment inspections" | no datasets; suggestion: browse, or say City of Seattle may not publish this data |
| `atlas_search_datasets` | `seattle`, "restaurant inspections", `asset_scope: "all"` | no datasets |
| `atlas_search_datasets` | `seattle`, "health inspection", `asset_scope: "all"` | no datasets |
| `atlas_search_datasets` | `seattle`, "food", `asset_scope: "all"` | 10 results (emergency food and meals, food-waste and food-security dashboards, farmers markets, P-Patch, street-use notices, public life, downtown activation); none is an inspection dataset |
| `atlas_search_datasets` | `seattle`, "inspection", `asset_scope: "all"` | Construction and Inspections datasets (permits, code compliance, rental registration); none is a food inspection dataset |
| `atlas_search_datasets` | `king-county`, "food establishment inspections" | `r878-4sxa` Food Establishment Inspection Data (dataset, queryable, updated 2026-10-19), plus food-business lists |
| `atlas_search_datasets` | `king-county`, same, `detail: "full"` | description: Health Department inspection results for food service establishments in King County, 2021 to the present; one row per violation, rows of one inspection share `inspection_serial_num` |
| `atlas_describe_dataset` | `king-county`, `r878-4sxa` | 109,999 rows; `inspection_date` (calendar_date) 2021-01-04..2026-10-17; text column `city`; no `place_fields`; knowledge level `none` |
| `atlas_query_dataset` | group by `city`, September 2026 | many King County cities (Seattle, Bellevue, Kent, Federal Way, ...), so the dataset is county-wide; Seattle appears as `SEATTLE` (607 inspections), `Seattle` (257) and `seattle` (4) |
| `atlas_query_dataset` | `upper(city) = 'SEATTLE'`, September 2026 | 1,487 rows, 868 distinct `inspection_serial_num`, 839 distinct businesses |
| `atlas_query_dataset` | same, by `inspection_type` | Routine Inspection/Field Review 708, Educational Inspection 123, Return Inspection 37 |
| `atlas_query_dataset` | all cities, September 2026 | 2,897 rows, 1,850 inspections |

Variant chosen: `32-city-data-at-county`. King County publishes a dataset that covers Seattle (food establishment inspections) and `data.seattle.gov` publishes none.
