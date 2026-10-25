from __future__ import annotations

from opendata_atlas.mcp.schema import compact_output_schema, compact_schema


def test_collapses_optional_union_and_drops_titles():
    schema = {
        "title": "Args",
        "type": "object",
        "properties": {
            "title": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "default": None,
                "title": "Title",
                "description": "d",
            },
        },
    }
    assert compact_schema(schema) == {
        "type": "object",
        "properties": {"title": {"type": "string", "description": "d"}},
    }


def test_keeps_real_unions():
    schema = {"anyOf": [{"type": "string"}, {"type": "integer"}]}
    assert compact_schema(schema) == schema


def test_keeps_non_null_defaults():
    assert compact_schema({"type": "integer", "default": 0}) == {"type": "integer", "default": 0}


def test_output_schema_drops_defaults_and_types_fixed_by_enum_or_const():
    """#25: result schemas carry no `default`, nor a `type` beside `enum` or `const`."""
    schema = {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["ok", "timeout"], "default": "ok"},
            "origin": {"type": "string", "const": "cached_metadata", "default": "cached_metadata"},
            "type": {"type": "string"},
            "default": {"type": "integer"},
        },
    }
    assert compact_output_schema(schema) == {
        "type": "object",
        "properties": {
            "status": {"enum": ["ok", "timeout"]},
            "origin": {"const": "cached_metadata"},
            "type": {"type": "string"},
            "default": {"type": "integer"},
        },
    }


def test_published_output_schemas_carry_no_default_or_pinned_type(tools_list):
    def walk(node):
        if isinstance(node, dict):
            assert "default" not in node, node
            if "enum" in node or "const" in node:
                assert "type" not in node, node
            for key, value in node.items():
                if key in ("properties", "$defs"):
                    for sub in value.values():
                        walk(sub)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for tool in tools_list["tools"]:
        walk(tool["outputSchema"])
