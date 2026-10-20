"""Replace people's names, emails and account ids in recorded fixtures with placeholders.

    uv run python scripts/scrub_fixtures.py [--check] [PATHS...]

Rewrites each JSON file under PATHS (default `tests/fixtures/`) in place, in the
format `tests/http_fixtures.Recorder.save` writes; a file without identities is
left untouched. With `--check`, rewrites nothing and exits 1 if any identity is
left. Output gives counts per kind, never values.

The guard reads the person fields in IDENTITY_KEYS, the value of every Discovery
`{key, value}` metadata pair whose key names an identity (`identity_metadata_key`,
such as `Common-Core_Contact-Name`), any email-shaped text, and Socrata account ids:
every 4x4 in a string inside an ACCOUNT_HOLDERS object, at any depth (an `id`, a team
member's `id`, the user path in a `profileImageUrl*`), or in a holder's own string value
(`rowsUpdatedBy`). Each distinct account id becomes one `fixt-NNNN`, numbered after the
highest placeholder already present. Request keys of a
fixture are scrubbed too; `Replay` scrubs its lookup key the same way. Free-text
row values, such as a business name in a permit row, are not person fields, and
it does not read them.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

IDENTITY_KEYS: frozenset[str] = frozenset(
    {"displayName", "screenName", "display_name", "Contact Name"}
)
PLACEHOLDER_NAME = "Fixture Person"
#: No `@`, so any email the scan finds is a real leak.
PLACEHOLDER_EMAIL = "redacted-email"
#: The Global Constraints email scan, as a regex.
EMAIL: re.Pattern[str] = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z.]{2,}")
#: Keys whose object, at any depth, or whose string value names a Socrata account by its 4x4.
ACCOUNT_HOLDERS: frozenset[str] = frozenset(
    k.casefold()
    for k in (
        "owner",
        "tableAuthor",
        "author",
        "creator",
        "submitter",
        "reviewer",
        "contact",
        "rowsUpdatedBy",
    )
)
#: A Socrata 4x4, the shape of both dataset and account ids, alone or in a URL path.
FOUR_BY_FOUR: re.Pattern[str] = re.compile(
    r"(?<![A-Za-z0-9-])[a-z0-9]{4}-[a-z0-9]{4}(?![A-Za-z0-9-])"
)
#: An account-id placeholder; still a 4x4, so the shape a reader expects is kept.
PLACEHOLDER_ID: re.Pattern[str] = re.compile(r"fixt-(\d{4})")

#: Metadata keys naming a person or account, compared case-folded with spaces and
#: underscores removed. Shared with the compat evidence redactor (ruling 25).
ACCOUNT_KEYS: frozenset[str] = frozenset(
    k.replace(" ", "").replace("_", "").casefold()
    for k in (
        "owner",
        "tableAuthor",
        "creator",
        "submitter",
        "reviewer",
        "approvals",
        "grants",
        "rowsUpdatedBy",
        "screenName",
        "displayName",
        "display_name",
        "contact_email",
        "Contact Email",
        "Contact Name",
        "Contact Information",
        "Point of Contact",
        "Data Owner",
        "Dataset Owner",
        "Telephone",
        "profileImageUrlLarge",
        "profileImageUrlMedium",
        "profileImageUrlSmall",
    )
)
#: Final words of a Discovery `domain_metadata` key that name a person or their contact details.
IDENTITY_WORDS: frozenset[str] = frozenset(
    ("contact", "name", "email", "phone", "telephone", "address", "postcode", "owner", "author")
)
_KEY_WORD = re.compile(r"[-_\s]+")

DEFAULT_PATHS = (Path(__file__).resolve().parent.parent / "tests" / "fixtures",)


def identity_key(key: str) -> bool:
    """A metadata key in ACCOUNT_KEYS, ignoring case, spaces and underscores."""
    return key.replace(" ", "").replace("_", "").casefold() in ACCOUNT_KEYS


def identity_metadata_key(key: str) -> bool:
    """A `{key, value}` metadata key such as `Common-Core_Contact-Email` that names an identity.

    Its last `_` segment without hyphens (`ContactEmail`) is an identity key, or its last
    `_`/`-` word (`Email`) is an identity word, compared case-insensitively.
    """
    if identity_key(key.rsplit("_", 1)[-1].replace("-", "")):
        return True
    return _KEY_WORD.split(key.strip())[-1].casefold() in IDENTITY_WORDS


def is_metadata_pair(value: dict[str, Any]) -> bool:
    return set(value) == {"key", "value"} and isinstance(value["key"], str)


def _identity_pair(node: dict[str, Any]) -> bool:
    return is_metadata_pair(node) and identity_metadata_key(node["key"])


def _embedded_json(text: str) -> dict[str, Any] | list[Any] | None:
    if text.lstrip()[:1] not in ("{", "["):
        return None
    try:
        parsed = json.loads(text)
    except ValueError:
        return None
    return parsed if isinstance(parsed, (dict, list)) else None


def _is_name(key: str, value: Any) -> bool:
    return key in IDENTITY_KEYS and isinstance(value, str) and value != ""


def _holder(key: str) -> bool:
    return key.casefold() in ACCOUNT_HOLDERS


def _placeholder_numbers(node: Any) -> list[int]:
    if isinstance(node, dict):
        return [n for key, value in node.items() for n in _placeholder_numbers([key, value])]
    if isinstance(node, list):
        return [n for item in node for n in _placeholder_numbers(item)]
    if isinstance(node, str):
        embedded = _embedded_json(node)
        if embedded is not None:
            return _placeholder_numbers(embedded)
        match = PLACEHOLDER_ID.fullmatch(node)
        return [int(match.group(1))] if match else []
    return []


class AccountIds:
    """Gives each distinct account id one `fixt-NNNN` placeholder; keeps no record on disk."""

    def __init__(self, start: int = 1) -> None:
        self._placeholders: dict[str, str] = {}
        self._next = start

    @classmethod
    def after(cls, *nodes: Any) -> AccountIds:
        """Number new placeholders after the highest one already in `nodes`."""
        return cls(1 + max((n for node in nodes for n in _placeholder_numbers(node)), default=0))

    def __call__(self, account_id: str) -> str:
        if PLACEHOLDER_ID.fullmatch(account_id):
            return account_id
        if account_id not in self._placeholders:
            self._placeholders[account_id] = f"fixt-{self._next:04d}"
            self._next += 1
        return self._placeholders[account_id]


def scrub(node: Any, ids: AccountIds | None = None) -> Any:
    """Return a copy of `node` with names, emails and account ids replaced by placeholders.

    Pass one `ids` across several files to map an account id to the same placeholder in
    each; by default, new placeholders are numbered after those already in `node`.
    """
    return _scrub(node, AccountIds.after(node) if ids is None else ids, in_account=False)


def _scrub(node: Any, ids: AccountIds, in_account: bool) -> Any:
    if isinstance(node, dict):
        if _identity_pair(node):
            value = node["value"]
            return {"key": node["key"], "value": PLACEHOLDER_NAME if value else value}
        return {
            _scrub(key, ids, False): _scrub_field(key, value, ids, in_account)
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [_scrub(item, ids, in_account) for item in node]
    if isinstance(node, str):
        return _scrub_text(node, ids, in_account)
    return node


def _scrub_field(key: str, value: Any, ids: AccountIds, in_account: bool) -> Any:
    if _is_name(key, value):
        return PLACEHOLDER_NAME
    return _scrub(value, ids, in_account or _holder(key))


def _scrub_text(text: str, ids: AccountIds, in_account: bool) -> str:
    embedded = _embedded_json(text)
    if embedded is None:
        text = EMAIL.sub(PLACEHOLDER_EMAIL, text)
        return FOUR_BY_FOUR.sub(lambda m: ids(m.group()), text) if in_account else text
    cleaned = _scrub(embedded, ids, in_account)
    if cleaned == embedded:
        return text
    return json.dumps(cleaned, separators=(",", ":"), ensure_ascii=False)


def find_identities(node: Any) -> Counter[str]:
    """Count identities left in `node` per kind (`email`, `account_id`, or the identity key).

    Counts only; never values.
    """
    return +_find(node, in_account=False)


def _find(node: Any, in_account: bool) -> Counter[str]:
    found: Counter[str] = Counter()
    if isinstance(node, dict) and _identity_pair(node):
        if node["value"] and node["value"] != PLACEHOLDER_NAME:
            found[node["key"]] += 1
    elif isinstance(node, dict):
        for key, value in node.items():
            found += _find(key, False)
            if _is_name(key, value):
                if value != PLACEHOLDER_NAME:
                    found[key] += 1
            else:
                found += _find(value, in_account or _holder(key))
    elif isinstance(node, list):
        for item in node:
            found += _find(item, in_account)
    elif isinstance(node, str):
        found += _find_text(node, in_account)
    return found


def _find_text(text: str, in_account: bool) -> Counter[str]:
    embedded = _embedded_json(text)
    if embedded is not None:
        return _find(embedded, in_account)
    found: Counter[str] = Counter({"email": len(EMAIL.findall(text))})
    if in_account:
        ids = FOUR_BY_FOUR.findall(text)
        found["account_id"] += sum(not PLACEHOLDER_ID.fullmatch(i) for i in ids)
    return found


def _files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        files.extend(sorted(path.rglob("*.json")) if path.is_dir() else [path])
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true", help="rewrite nothing; exit 1 if any is left"
    )
    parser.add_argument("paths", nargs="*", type=Path, default=list(DEFAULT_PATHS))
    args = parser.parse_args(argv)
    total: Counter[str] = Counter()
    loaded = [(path, json.loads(path.read_text())) for path in _files(args.paths)]
    # One mapping for the whole run: an account id gets the same placeholder in every file.
    ids = AccountIds.after(*(data for _, data in loaded))
    for path, data in loaded:
        found = find_identities(data)
        if not found:
            continue
        total += found
        print(f"{path}: {dict(sorted(found.items()))}")
        if not args.check:
            path.write_text(json.dumps(scrub(data, ids), indent=1, sort_keys=True) + "\n")
    verb = "left" if args.check else "scrubbed"
    print(f"{verb}: {dict(sorted(total.items()))}")
    return 1 if args.check and total else 0


if __name__ == "__main__":
    sys.exit(main())
