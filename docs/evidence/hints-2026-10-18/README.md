# Zero-match hint probes, 2026-10-18

Cited from `docs/upstream-facts.md` (Text equality on padded values). Both requests went to data.lacity.org through `SodaClient.soql` (`$query`), one at a time, with no token.

- `lacity-hollywood.json` (milestone 3 Task 7): two queries on LAPD NIBRS Offenses `k7nn-b2ep`:
  1. `area_name` values matching `upper(area_name) like '%HOLLYWOOD%'`, grouped with counts: the padded `Hollywood` and `N Hollywood`;
  2. `count(*)` where `area_name = 'Hollywood'` (unpadded): one row, `n = "0"`;
  3. (fix round 1) `count(*)` where `upper(area_name) like '%O''BRIEN_%'`: a doubled quote inside a `like` pattern is accepted (200, `n = "0"`).

All rows are aggregates (`area_name` division names and counts). None holds personal data.
