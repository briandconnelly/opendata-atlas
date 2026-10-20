# Feasibility evidence, 2026-10-17

Raw outputs of the milestone 0a and 0b probes in `scripts/feasibility/`, cited from `docs/upstream-facts.md`. Every file is under 500 KB, so none was reduced to summary fields. Counts are live and drift.

| File | Produced by |
| --- | --- |
| `domains.json` | `enumerate_domains.py` (summary, per-method results, domains by region, eligible list under the current rule) |
| `identity.json` | `check_identity.py` over the 20-host sample |
| `limit0.json` | `?limit=0` and `?limit=0&only=dataset` in both regions |
| `eu_scroll_without_initial_scroll_id.json` | EU scroll whose first request omits `scroll_id` |
| `data_socrata_com_hosts.json` | catalog count and `/api/views.json` status for four `*.data.socrata.com` hosts |
| `budget.json` | `budget_spike.py` (milestone 0b): today's and the hypothetical five-tool `tools/list` sizes |
| `compat.json` | `compat_run.py` over the 20-host sample (milestone 0b): search, describe, two query pages, forced `no_such_column` |
| `no_such_column_probe.json` | `no_such_column_probe.py` (milestone 0b): the engine's captured request and single-variable probes on LA, WA, SF |
| `fork_tools_list_size.txt` | `tests/test_contract.py` budget test run offline on `git archive` of `seattle-open-data` 26c6628 (command in the file) |

No token or credential was used or recorded.
