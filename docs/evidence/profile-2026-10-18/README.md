# Profiler run, 2026-10-18

Cited from `docs/upstream-facts.md` (Profiler run on data.lacity.org). Every request went out one at a time, with no token.

| File | Contents |
| --- | --- |
| `order-probe.json` | `curl -s 'https://api.us.socrata.com/api/catalog/v1?domains=data.lacity.org&only=dataset&order=page_views_total&limit=3' -A opendata-atlas-profiler/0`, HTTP 200. Owner, creator, contact and `domain_metadata` identity fields are replaced with `<identity redacted>` (the `_redact` rule of `tests/test_compat_live.py`); nothing else is changed |
| `report.json` | The `--report` of `uv run atlas-profile data.lacity.org --datasets 5 --out docs/evidence/profile-2026-10-18/data.lacity.org --report docs/evidence/profile-2026-10-18/report.json` (exit 0, 43 s). `review_values` is empty, so the CLI printed no review list: every emitted value is in the shared placeholder vocabulary |
| `data.lacity.org/` | That run's draft pack: `portal.toml` (the registry identity, tier `generic`) and `facts/<dataset>.toml`. It loads with `load_portal`. It is not under `src/`, so the server does not serve it |
| `layer-columns.json` | The six 6rrh-rzua layer views (`GET https://data.lacity.org/api/views/<layer>.json`, one at a time, through `SodaClient`), reduced to each column's `fieldName` and `dataTypeName`. In each, the first text column is `_feature_id_string` |
| `recheck.json` | `drift.report_json` from a one-off script that loads the draft and runs `drift.check_claim` on each asserted claim in turn: 10 of 10 `passed` |

Three earlier runs that day were replaced, and their outputs were not kept. The first named `_feature_id_string` as every layer's candidate label column (before the label-column fix). The second wrote five `column_timezone` claims for date-only columns (before ruling 52). The third predates the review fixes (`review_values`, `error`, the date-only note's wording).

No personal data: the draft keeps only the values `X` and `-`, from categorical columns with at most 100 groups. Report notes name columns, not values. The email and phone scan of this directory prints nothing (the same pattern matches a known positive).
