# Seattle drift probes and first drift run, 2026-10-18

Cited from `docs/upstream-facts.md` (Seattle drift probes). Every request went to data.seattle.gov through `SodaClient.soql`, one at a time, with no token.

- `seattle-probes.json`: the ten probe queries of milestone 3 Task 2, each run once (`$query`), with the rows returned. Four place-field placeholder shares (`tazs-3rd5` and `ppi5-g2bj`, `sector` and `beat`), then for each of `kzjm-xkqj` `datetime`, `65db-xm6k` `date` and `33kz-ixgy` `cad_event_original_time_queued` the hourly counts on 2026-03-08 (the 2026 US spring-forward date) and over 2025.
- `fremont-reprobe.json`: the `65db-xm6k` spring-forward re-probe. The verbatim query returned an hour-2 group with no `n`. The raw rows from 01:00 to 03:00 show that the 02:00 row has no counts at all. The amended query, with `AND fremont_bridge IS NOT NULL`, returns no hour-2 group. The pack's probe is the amended query.
- `fire-types.json` (milestone 3 Task 5): four Fire 911 `kzjm-xkqj` queries, each run once:
  1. the top 20 response `type` values by row count;
  2. by year since 2020, Aid Response plus Medic Response rows (`med`) and all rows (`n`), superseded by 3;
  3. the same, with the five-type medical set of controller ruling 45;
  4. that set's share of all rows. Cited from `docs/upstream-facts.md` (Fire 911 response types).
- `report.json`: the report of the first drift run, `uv run pytest --run-integration -m integration tests/test_drift.py tests/test_live.py -v --drift-report docs/evidence/drift-2026-10-18/report.json` (22 passed, 17 s). It lists each claim's outcome, and each assertion's checker, request and detail.

All rows are aggregates (`ph`, `n`, `h`, `med`, `y`, response `type` counts) or hourly bicycle counts. None holds personal data.
