"""Shrink generated JSON Schemas to the portable subset agents receive.

See [2.compact-baseline] and [3.portable-schema].
"""

from __future__ import annotations

import json
from typing import Any

_DROP = frozenset({"title"})


def compact_schema(schema: Any) -> Any:
    """Drop titles and `default: null`, and collapse `anyOf: [X, null]` to X.

    Optional parameters are declared `T | None = None` in Python so omission and
    an explicit null mean the same thing; agents should only ever see `T`.
    """
    if isinstance(schema, list):
        return [compact_schema(item) for item in schema]
    if not isinstance(schema, dict):
        return schema

    out: dict[str, Any] = {}
    for key, value in schema.items():
        if key in _DROP and isinstance(value, str):
            continue
        if key == "default" and value is None:
            continue
        if key in ("properties", "$defs", "patternProperties"):
            # Keys here are property names, not schema keywords: a property may be named "title".
            out[key] = {name: compact_schema(sub) for name, sub in value.items()}
        else:
            out[key] = compact_schema(value)

    any_of = out.get("anyOf")
    if isinstance(any_of, list):
        non_null = [s for s in any_of if s != {"type": "null"}]
        if len(non_null) == 1 and len(non_null) < len(any_of):
            merged = {k: v for k, v in out.items() if k != "anyOf"}
            return {**non_null[0], **merged}
    return out


def compact_output_schema(schema: Any) -> Any:
    """`compact_schema`, then drop what a result schema never uses (#25): `default`, which only
    describes omitted input, and `type` beside `enum` or `const`, which already fix the value.

    Input schemas keep both: a planner reads `type` when it writes arguments. A `$defs` entry
    the schema references once is inlined; one it references more than once stays a local,
    non-recursive `$ref`, so a repeated object is published once (#66).
    """
    return _trim_output(compact_schema(share_repeated_defs(schema)))


def share_repeated_defs(schema: dict[str, Any]) -> dict[str, Any]:
    """Inline every `$defs` entry used once in the fully expanded schema; keep the rest.

    Uses are counted after expanding every reference, so a definition nested in one that is
    inlined counts each time its parent appears. The result expands back to exactly the
    fully inlined schema.
    """
    defs: dict[str, Any] = schema.get("$defs", {})
    if not defs:
        return schema
    uses: dict[str, int] = dict.fromkeys(defs, 0)

    def count(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                count(item)
        elif isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                name = ref.removeprefix("#/$defs/")
                uses[name] += 1
                count(defs[name])
            for key, value in node.items():
                if key != "$defs":
                    count(value)

    count(schema)
    kept = {name for name, n in uses.items() if n > 1}

    def inline(node: Any) -> Any:
        if isinstance(node, list):
            return [inline(item) for item in node]
        if not isinstance(node, dict):
            return node
        out = {k: inline(v) for k, v in node.items() if k != "$defs"}
        ref = out.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            name = ref.removeprefix("#/$defs/")
            if name not in kept:
                siblings = {k: v for k, v in out.items() if k != "$ref"}
                return {**inline(defs[name]), **siblings}
        return out

    out = inline(schema)
    if kept:
        out["$defs"] = {name: inline(defs[name]) for name in sorted(kept)}
    # Every surviving reference must name a kept definition.
    assert all(f'"#/$defs/{n}"' not in json.dumps(out) for n in set(defs) - kept)
    return out


def _trim_output(schema: Any) -> Any:
    if isinstance(schema, list):
        return [_trim_output(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    pinned = "enum" in schema or "const" in schema
    out: dict[str, Any] = {}
    for key, value in schema.items():
        if key == "default" or (key == "type" and pinned):
            continue
        if key in ("properties", "$defs", "patternProperties"):
            out[key] = {name: _trim_output(sub) for name, sub in value.items()}
        else:
            out[key] = _trim_output(value)
    return out
