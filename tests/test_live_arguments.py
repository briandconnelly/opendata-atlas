"""Offline: every tool call the live suites make validates against the published `inputSchema`.

The live suites run only with `--run-integration`, so a schema change could break them unseen.
This reads their source (AST) and checks each literal argument dict instead. A value computed at
run time (a portal or dataset id from the loop, a cursor from the previous page) is replaced by
a placeholder chosen by the argument it fills; module constants are read from the module.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path
from typing import Any

import jsonschema
import pytest

LIVE_MODULES = ["tests.test_live", "tests.test_compat_live"]
#: Run-time values, by the argument they fill (or, for `**name`, by the variable).
PLACEHOLDERS: dict[str, Any] = {
    "portal": "data.seattle.gov",
    "dataset_id": "abcd-1234",
    "cursor": "opaque-cursor",
}
SPREADS: dict[str, dict[str, Any]] = {
    "base": {"portal": PLACEHOLDERS["portal"], "dataset_id": PLACEHOLDERS["dataset_id"]},
}
#: Argument expressions that are not literal dicts, and where they are checked instead.
CHECKED_ELSEWHERE = {
    "example.arguments": "tests/test_guides.py::test_example_is_a_valid_query_call"
}
#: Literal calls each module makes today; fewer means the collector stopped seeing them.
MIN_CALLS = {"tests.test_live": 2, "tests.test_compat_live": 6}


class _Unresolved(Exception):
    pass


def _value(node: ast.expr, module: Any, key: str | None) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.List):
        return [_value(e, module, None) for e in node.elts]
    if isinstance(node, ast.Dict):
        return _dict(node, module)
    if isinstance(node, ast.Name) and hasattr(module, node.id):
        return getattr(module, node.id)
    if isinstance(node, ast.Name | ast.Subscript | ast.Attribute) and key in PLACEHOLDERS:
        return PLACEHOLDERS[key]
    raise _Unresolved(ast.unparse(node))


def _dict(node: ast.Dict, module: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in zip(node.keys, node.values, strict=True):
        if k is None:  # `**name`
            if not (isinstance(v, ast.Name) and v.id in SPREADS):
                raise _Unresolved(ast.unparse(v))
            out |= SPREADS[v.id]
        else:
            key = _value(k, module, None)
            out[key] = _value(v, module, key)
    return out


def _tool_calls(module_name: str) -> list[tuple[int, str, ast.expr]]:
    """(line, tool, arguments node) for `call_tool_mcp(tool, args)` and `_call(..., tool, args)`."""
    module = importlib.import_module(module_name)
    tree = ast.parse(Path(module.__file__ or "").read_text())
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "call_tool_mcp":
            tool, args = node.args[0], node.args[1]
        elif isinstance(func, ast.Name) and func.id == "_call" and len(node.args) == 5:
            tool, args = node.args[3], node.args[4]
        else:
            continue
        if isinstance(tool, ast.Constant) and isinstance(tool.value, str):
            found.append((node.lineno, tool.value, args))
    return found


CALLS = [(m, *call) for m in LIVE_MODULES for call in _tool_calls(m)]


@pytest.mark.parametrize(
    ("module_name", "line", "tool", "node"),
    CALLS,
    ids=[f"{m.rsplit('.', 1)[-1]}:{line}:{tool}" for m, line, tool, _ in CALLS],
)
def test_live_call_arguments_match_published_schema(input_schemas, module_name, line, tool, node):
    assert tool in input_schemas, f"{module_name}:{line} calls unknown tool {tool}"
    if not isinstance(node, ast.Dict):
        assert ast.unparse(node) in CHECKED_ELSEWHERE, f"{module_name}:{line}: not a literal dict"
        return
    try:
        arguments = _dict(node, importlib.import_module(module_name))
    except _Unresolved as exc:
        pytest.fail(f"{module_name}:{line}: add a placeholder for {exc}")
    jsonschema.validate(arguments, input_schemas[tool])


def test_collector_sees_every_live_call():
    counts = {m: sum(isinstance(c[3], ast.Dict) for c in CALLS if c[0] == m) for m in LIVE_MODULES}
    for module_name, minimum in MIN_CALLS.items():
        assert counts[module_name] >= minimum, (module_name, counts[module_name])
