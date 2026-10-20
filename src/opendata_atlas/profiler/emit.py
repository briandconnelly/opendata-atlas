"""Render profiler claims as draft pack files (docs/design.md: Knowledge packs).

Strings are written with `json.dumps(..., ensure_ascii=True)`, so every file is ASCII. JSON's
escapes are TOML's, except three that TOML forbids: a surrogate pair (TOML has `\\U` for
characters past the BMP), a lone surrogate (replaced with U+FFFD) and a raw DEL.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from opendata_atlas.portals.model import Claim, PortalIdentity

_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")
#: A `\uD8xx\uDCxx` escape from JSON, preceded by an even run of backslashes, so that it is an
#: escape and not escaped text such as a literal `\\ud83d`.
_SURROGATE_PAIR = re.compile(r"(?<!\\)((?:\\\\)*)\\u(d[89ab][0-9a-f]{2})\\u(d[c-f][0-9a-f]{2})")


def _scalars(s: str) -> str:
    """`s` with each surrogate pair joined and each lone or reversed surrogate as U+FFFD.

    Upstream JSON can carry a lone surrogate, which is no Unicode scalar value, so TOML has no
    escape for it.
    """
    out: list[str] = []
    i = 0
    while i < len(s):
        c = ord(s[i])
        if 0xD800 <= c <= 0xDBFF and i + 1 < len(s) and 0xDC00 <= ord(s[i + 1]) <= 0xDFFF:
            out.append(chr(0x10000 + ((c - 0xD800) << 10) + (ord(s[i + 1]) - 0xDC00)))
            i += 2
            continue
        out.append("�" if 0xD800 <= c <= 0xDFFF else s[i])
        i += 1
    return "".join(out)


def _string(s: str) -> str:
    out = json.dumps(_scalars(s), ensure_ascii=True).replace("\x7f", "\\u007f")

    def astral(m: re.Match[str]) -> str:
        hi, lo = int(m.group(2), 16), int(m.group(3), 16)
        return f"{m.group(1)}\\U{0x10000 + ((hi - 0xD800) << 10) + (lo - 0xDC00):08X}"

    return _SURROGATE_PAIR.sub(astral, out)


def _key(k: str) -> str:
    return k if _BARE_KEY.match(k) else _string(k)


def _value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int | float):
        return repr(v)
    if isinstance(v, str):
        return _string(v)
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, list):
        return "[" + ", ".join(_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{_key(k)} = {_value(x)}" for k, x in v.items()) + "}"
    raise TypeError(f"cannot render {type(v).__name__} as TOML")


def _lines(data: dict[str, Any]) -> list[str]:
    return [f"{_key(k)} = {_value(v)}" for k, v in data.items() if v is not None]


def render_claims(claims: list[Claim]) -> str:
    """`[[claim]]` tables, each with its `[[claim.evidence]]` and `[[claim.assertion]]`."""
    blocks: list[str] = []
    for c in claims:
        head = c.model_dump(
            exclude={"evidence", "assertion"}, exclude_none=True, exclude_defaults=True
        )
        head["scope"] = c.scope.model_dump(exclude_none=True)
        lines = ["[[claim]]", *_lines({"id": c.id, "kind": c.kind, **head})]
        for e in c.evidence:
            lines += ["", "[[claim.evidence]]", *_lines(e.model_dump(exclude_none=True))]
        for a in c.assertion:
            fields = {"checker": a.checker, "probe": a.probe, "params": a.params or None}
            lines += ["", "[[claim.assertion]]", *_lines(fields)]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n" if blocks else ""


def _portal_toml(identity: PortalIdentity) -> str:
    data = identity.model_dump(exclude_none=True)
    tables = {k: data.pop(k) for k in ("catalog_query", "jurisdiction") if k in data}
    lines = _lines(data)
    for name, table in tables.items():
        lines += ["", f"[{name}]", *_lines(table)]
    return "\n".join(lines) + "\n"


def pack_files(identity: PortalIdentity, claims: list[Claim]) -> dict[str, str]:
    """Relative path to file text: `portal.toml`, `facts/<dataset id>.toml` and, only when
    there are layer claims, `regions.toml`.

    `portal.toml` copies the registry identity, its current `tier` included: the profiler
    never promotes a tier.
    """
    header = "# Draft from atlas-profile: observations only. A reviewer adds interpretations.\n\n"
    files = {"portal.toml": _portal_toml(identity)}
    layers = [c for c in claims if c.kind == "region_layer"]
    if layers:
        files["regions.toml"] = header + render_claims(layers)
    by_dataset: dict[str, list[Claim]] = {}
    for c in claims:
        if c.kind == "region_layer":
            continue
        if c.scope.dataset is None:
            raise ValueError(f"claim {c.id} has no dataset scope")
        by_dataset.setdefault(c.scope.dataset, []).append(c)
    for dataset, group in by_dataset.items():
        files[f"facts/{dataset}.toml"] = header + render_claims(group)
    return files
