"""Run the server over stdio and record every request a host sends (milestone 1 exit test d).

Usage: python scripts/capture_server.py [--validation PATH] <capture.jsonl>

`--validation PATH` serves the claims' validation state from PATH instead of the shipped
`validation.json` (an eval fixture, e.g. a stale claim); a relative PATH is read from the
working directory.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from fastmcp.server.middleware import Middleware

from opendata_atlas.mcp.server import build_server
from opendata_atlas.portals import validation


class Capture(Middleware):
    def __init__(self, path: Path) -> None:
        self.path = path

    def _write(self, record: dict[str, Any]) -> None:
        with self.path.open("a") as fh:
            fh.write(json.dumps(record, default=str) + "\n")

    async def on_request(self, context: Any, call_next: Any) -> Any:
        record: dict[str, Any] = {"t": time.time(), "method": context.method}
        try:
            record["params"] = context.message.model_dump(
                mode="json", by_alias=True, exclude_none=True
            )
        except Exception as exc:  # Capture must never break the server.
            record["capture_error"] = repr(exc)
        try:
            result = await call_next(context)
        except BaseException as exc:
            record["raised"] = type(exc).__name__
            self._write(record)
            raise
        if context.method == "tools/list":
            record["tools"] = [_dump(t) for t in result]
        self._write(record)
        return result


def _dump(tool: Any) -> Any:
    mcp_tool = tool.to_mcp_tool() if hasattr(tool, "to_mcp_tool") else tool
    return mcp_tool.model_dump(mode="json", by_alias=True, exclude_none=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the server over stdio and record requests.")
    parser.add_argument("capture", type=Path, help="JSONL file to append requests to")
    parser.add_argument("--validation", type=Path, help="validation file to serve instead")
    args = parser.parse_args()
    if args.validation is not None:
        if not args.validation.is_file():
            parser.error(f"--validation: no such file: {args.validation}")
        validation.set_override(args.validation.resolve())
    server = build_server()
    server.add_middleware(Capture(args.capture))
    server.run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()
