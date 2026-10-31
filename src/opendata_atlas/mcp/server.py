"""Server assembly and the failure boundary.

Every tool or resource failure leaves as the error envelope (docs/design.md: Errors).
"""

from __future__ import annotations

import base64
import logging
import sys
from importlib import resources
from typing import TYPE_CHECKING, Any

from fastmcp import FastMCP
from fastmcp.apps import UI_EXTENSION_ID
from fastmcp.exceptions import McpError, NotFoundError
from fastmcp.exceptions import ValidationError as FastMCPValidationError
from fastmcp.server.middleware import Middleware
from mcp.server import NotificationOptions
from mcp.types import Icon
from pydantic import ValidationError

from opendata_atlas import __version__
from opendata_atlas.constants import CACHE_TTL_SECONDS, SERVER_NAME, SERVER_TITLE
from opendata_atlas.core.context import new_request_id
from opendata_atlas.core.errors import (
    AtlasError,
    ErrorCode,
    ErrorDetails,
    Repair,
    from_validation_errors,
)
from opendata_atlas.core.reference import INSTRUCTIONS
from opendata_atlas.mcp.resources import register_resources
from opendata_atlas.mcp.result import failure
from opendata_atlas.mcp.tools import register_tools

if TYPE_CHECKING:
    from fastmcp.server.middleware import CallNext, MiddlewareContext

logger = logging.getLogger("opendata_atlas")

#: MCP folds resource-not-found into Invalid params; -32002 is retired [6.jsonrpc-code-allocation].
_INVALID_PARAMS = -32602
#: Server-defined resource failures sit outside the reserved JSON-RPC range.
_RESOURCE_FAILURE = -31000
#: A URI that names no readable resource, including one naming an unservable portal.
_NOT_FOUND_CODES = frozenset(
    {
        ErrorCode.REFERENCE_NOT_FOUND,
        ErrorCode.PORTAL_NOT_FOUND,
        ErrorCode.PORTAL_NOT_ENABLED,
        ErrorCode.PORTAL_RETIRED,
        ErrorCode.INVALID_ARGUMENT,
    }
)


def _find(exc: BaseException, kind: type[BaseException]) -> Any:
    """FastMCP wraps handler exceptions in ToolError; look through the cause chain."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        if isinstance(current, kind):
            return current
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return None


def _to_error(exc: BaseException, tool: str, arguments: dict[str, Any] | None) -> AtlasError:
    if (domain := _find(exc, AtlasError)) is not None:
        return domain
    # FastMCP raises its own ValidationError, caused by pydantic's, only for argument
    # validation. Pydantic errors from a handler body arrive wrapped in ToolError: server bugs.
    if isinstance(exc, FastMCPValidationError) and isinstance(exc.__cause__, ValidationError):
        return from_validation_errors(
            exc.__cause__.errors(include_url=False, include_input=False),
            tool=tool,
            arguments=arguments,
        )
    logger.exception("unexpected failure in %s", tool)
    return AtlasError(ErrorCode.INTERNAL_ERROR, "The server failed unexpectedly.")


def _unknown_tool(names: list[str] | None) -> AtlasError:
    """A `tools/call` naming no tool of this server: the caller's malformed call, so
    `invalid_argument` on `tools/call`'s `name`, never `internal_error`. The received name
    is not echoed [6.offending-value]; the server's own tool names are."""
    return AtlasError(
        ErrorCode.INVALID_ARGUMENT,
        "No tool by that name on this server.",
        details=ErrorDetails(
            field="name", reason="Unknown tool; call one of `candidates`.", candidates=names
        ),
        repair=Repair(
            next_step="read_capabilities",
            tool="atlas_get_reference",
            arguments={"topic": "capabilities"},
        ),
    )


class EnvelopeMiddleware(Middleware):
    async def on_call_tool(
        self, context: MiddlewareContext[Any], call_next: CallNext[Any, Any]
    ) -> Any:
        request_id = new_request_id()
        tool = context.message.name
        try:
            return await call_next(context)
        except Exception as exc:
            # FastMCP raises NotFoundError itself, unwrapped, when no tool has this name;
            # a handler's exceptions arrive wrapped in ToolError.
            if isinstance(exc, NotFoundError):
                ctx = context.fastmcp_context
                tools = await ctx.fastmcp.list_tools(run_middleware=False) if ctx else []
                error = _unknown_tool([t.name for t in tools] or None)
            else:
                error = _to_error(exc, tool, context.message.arguments)
            envelope = error.envelope
            envelope.request_id = request_id
            logger.info("request_id=%s tool=%s code=%s", request_id, tool, envelope.code.value)
            return failure(envelope)

    async def on_read_resource(
        self, context: MiddlewareContext[Any], call_next: CallNext[Any, Any]
    ) -> Any:
        request_id = new_request_id()
        uri = str(context.message.uri)
        try:
            return await call_next(context)
        except McpError:
            raise
        except Exception as exc:
            if (domain := _find(exc, AtlasError)) is not None:
                error = domain
                code = (
                    _INVALID_PARAMS
                    if error.envelope.code in _NOT_FOUND_CODES
                    else _RESOURCE_FAILURE
                )
            elif _find(exc, NotFoundError) is not None:
                error = AtlasError(
                    ErrorCode.REFERENCE_NOT_FOUND,
                    "No resource at this URI.",
                    details=ErrorDetails(field="uri", reason="Unknown URI."),
                    repair=Repair(
                        next_step="list_topics", tool="atlas_get_reference", arguments={}
                    ),
                )
                code = _INVALID_PARAMS
            else:
                logger.exception("unexpected failure reading %s", uri)
                error = AtlasError(ErrorCode.INTERNAL_ERROR, "The server failed unexpectedly.")
                code = _RESOURCE_FAILURE
            envelope = error.envelope
            envelope.request_id = request_id
            # `uri` is resources/read's only parameter, so it is the field whatever the handler
            # named; the tool fallback's `item_id` is not a parameter here [6.details-field].
            details = envelope.details
            if details is not None and (details.field or details.fields):
                details.field, details.fields = "uri", None
            # A portal failure carries its URI template instead: the URI holds the caller's value.
            envelope.resource_uri = envelope.resource_uri or uri
            raise McpError(
                code=code, message=envelope.message, data=envelope.to_jsonrpc_data()
            ) from exc


def _icons() -> list[Icon]:
    """The packaged SVG as a `data:` URI, so a client needs no second fetch."""
    svg = resources.files("opendata_atlas.assets").joinpath("icon.svg").read_bytes()
    src = "data:image/svg+xml;base64," + base64.b64encode(svg).decode("ascii")
    return [Icon(src=src, mime_type="image/svg+xml", sizes=["any"])]


def build_server() -> FastMCP:
    mcp = FastMCP(
        name=SERVER_NAME,
        icons=_icons(),
        instructions=INSTRUCTIONS,
        version=__version__,
        middleware=[EnvelopeMiddleware()],
        cache_ttl=CACHE_TTL_SECONDS,
        cache_scope="public",
    )
    register_tools(mcp)
    register_resources(mcp)
    _advertise_fixed_surface(mcp)
    return mcp


def _advertise_fixed_surface(mcp: FastMCP) -> None:
    """Advertise only what is served: no prompts, no listChanged [9.list-changed], no UI,
    no logging.

    FastMCP registers prompt and `logging/setLevel` handlers on every server (the SDK
    derives each capability from its handler; this server never sends a log message to
    the client), turns on every listChanged for
    legacy clients, and adds the `io.modelcontextprotocol/ui` extension to the modern
    capabilities unconditionally; this server serves no UI resource. The SDK has no
    public way to undo any of these, so this reaches into the low-level server. It also
    sets `serverInfo.title`, which FastMCP's constructor does not take.
    `tests/test_legacy_protocol.py` pins the result across FastMCP upgrades.
    """
    low_level = mcp._mcp_server
    low_level.title = SERVER_TITLE
    for method in ("prompts/list", "prompts/get", "logging/setLevel"):
        low_level._request_handlers.pop(method, None)
    low_level.notification_options = NotificationOptions()

    get_capabilities = low_level.get_capabilities

    def without_ui(*args: Any, **kwargs: Any) -> Any:
        capabilities = get_capabilities(*args, **kwargs)
        extensions = {
            name: settings
            for name, settings in (capabilities.extensions or {}).items()
            if name != UI_EXTENSION_ID
        }
        return capabilities.model_copy(update={"extensions": extensions or None})

    low_level.get_capabilities = without_ui  # ty: ignore[invalid-assignment]


def main() -> None:
    logging.basicConfig(
        stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(name)s %(message)s"
    )
    # FastMCP logs a traceback for every expected domain error; EnvelopeMiddleware logs the rest.
    logging.getLogger("fastmcp.server.server").setLevel(logging.CRITICAL)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    build_server().run(transport="stdio", show_banner=False)
