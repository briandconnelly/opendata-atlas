# Live compatibility suite evidence, 2026-10-18

Outputs of `tests/test_compat_live.py`, cited from `docs/upstream-facts.md` (Compatibility through the tools). Run on 2026-10-18 through the MCP tools over the in-process client, over milestone 0's 20 sample portals by registry id. The portals ran one after another, 0.5 s apart, with the engine's own deadlines, per-host limiter and User-Agent, and no token. It took 74 s.

Command:

```
COMPAT_EVIDENCE_DIR=docs/evidence/compat-2026-10-18 uv run pytest --run-integration -m integration tests/test_compat_live.py -v
```

- `outcomes.md` and `outcomes.json`: the per-portal outcome of each step and its kind: `ok`, `data` (a saved 2xx response explains it) or `engine`.
- `<portal>.json`, one file per portal: the steps, then every upstream exchange of the run in order, as step, URL, HTTP status and body.

How bodies are saved (`_saved_body` in `tests/test_compat_live.py`, tested offline by `tests/test_compat_evidence.py`):

- Query-step bodies (`query_p1`, `query_p2`, `forced`) are reduced to `row_count`, the row keys, and the SHA-256 of the body as received. Row values can be personal data, and every query-step outcome depends only on the row count.
- Every other body is redacted as follows:
  - `cachedContents` keeps only its counts (`null`, `not_null`, `non_null`, `cardinality`, `count`). `top`, `largest`, `smallest` and the other value statistics are dropped, because they are the column's own most frequent and extreme values, which can be names, addresses and phone numbers.
  - Owner, author, creator, submitter, reviewer, approval, grant and contact fields (`owner`, `tableAuthor`, `screenName`, `displayName`, `contact_email`, "Contact Name", "Telephone" and the like) are each replaced whole with `<identity redacted>`.
  - Discovery `classification.domain_metadata` items, `{key, value}` objects, lose their `value` to `<identity redacted>` when the key names an identity: its last `_` segment without hyphens is one of the keys above (`Common-Core_Contact-Email`), or its last word is contact, name, email, phone, telephone, address, postcode, owner or author (`Point-of-Contact_Postcode`).
  - Email addresses and US-style phone numbers in any remaining text are replaced with `<email redacted>` and `<phone redacted>`.
- A body over 64 KiB is summarized to its size, SHA-256, top-level keys and, for a view, its column field names, and then redacted the same way.

Free text such as a dataset description is kept after email and phone redaction. A name written in prose is not detected.

Every file is under 500 KB, the prek large-file limit. Catalog results and counts are live and drift. Camden's first "permits" result was `7hiv-3r9k` in one earlier full run that day and `eqq9-intm` (0 rows) in another. Neither earlier run is retained, because both held unredacted data. The suite now tries up to 3 queryable results, and `attempts` in each portal file records them.

The `domain_metadata` rule was added in the milestone 2 final review, after this run. The raw bodies were never kept, so the rule was applied offline to the saved bodies (`_redact` over each exchange's `body`): 60 items in 7 files changed, and nothing else. The `sha256` values are still those of the bodies as received. A scan of every JSON and JSONL file under `docs/evidence/` for `{key, value}` lists then found 428 items, all in this directory, and no identity-keyed item with an unredacted value.
