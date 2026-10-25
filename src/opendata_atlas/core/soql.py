"""SoQL text the engine writes itself (docs/design.md: Tools 4)."""

from __future__ import annotations

import re

_PLAIN = re.compile(r"[a-z_][a-z0-9_]*")
#: SoQL and SQL keywords. LAPD's `group` column fails unquoted with `query.compiler.malformed`
#: and works backtick-quoted (probed 2026-10-25); quoting a non-keyword is harmless, so this
#: errs wide.
_KEYWORDS = frozenset(
    {"select", "from", "where", "group", "by", "having", "order", "limit", "offset", "search"}
    | {"join", "left", "right", "full", "inner", "outer", "cross", "on", "union", "intersect"}
    | {"minus", "except", "all", "as", "and", "or", "not", "is", "null", "in", "like", "ilike"}
    | {"between", "asc", "desc", "nulls", "first", "last", "true", "false", "case", "when"}
    | {"then", "else", "end", "distinct", "exists", "with", "lateral"}
)


def identifier(name: str) -> str:
    """A schema field name as SoQL reads it: backtick-quoted unless plain and not a keyword.

    System fields (`:id`, `:@computed_region_...`) are left as they are.
    """
    if name.startswith(":") or (_PLAIN.fullmatch(name) and name not in _KEYWORDS):
        return name
    return f"`{name}`"
