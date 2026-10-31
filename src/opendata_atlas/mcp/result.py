"""Tool results: `structuredContent` is the contract; `content[0]` is its serialized copy.

See [3.content-types].
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from fastmcp.tools import ToolResult
from mcp.types import TextContent

from opendata_atlas.core.budget import RESULT_LIMIT

if TYPE_CHECKING:
    from pydantic import BaseModel

    from opendata_atlas.core.errors import ErrorEnvelope


def _result(payload: dict[str, Any], *, is_error: bool) -> ToolResult:
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return ToolResult(
        content=[TextContent(type="text", text=text)],
        structured_content=payload,
        is_error=is_error,
    )


def success(model: BaseModel) -> ToolResult:
    return _result(model.model_dump(mode="json", exclude_none=True), is_error=False)


def failure(envelope: ErrorEnvelope) -> ToolResult:
    payload = envelope.to_wire()
    result = _result(payload, is_error=True)
    wire = {
        "content": [item.model_dump(mode="json", exclude_none=True) for item in result.content],
        "structuredContent": payload,
        "isError": True,
    }
    if len(json.dumps(wire, ensure_ascii=False, separators=(",", ":")).encode()) > RESULT_LIMIT:
        payload = {
            key: value
            for key, value in payload.items()
            if key in {"code", "message", "temporary", "retry_after_ms", "request_id"}
        }
        return _result(payload, is_error=True)
    return result
