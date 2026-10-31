"""Reference resources (docs/design.md: Resources and their tool fallbacks).

Same content as `atlas_get_reference`; every resource has that tool as its fallback.
The template variables complete through `completion/complete` [4.template-completion].
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from fastmcp.resources import FunctionResource
from mcp.types import Completion, ResourceTemplateReference

from opendata_atlas.constants import LIFECYCLE_META, URI_SCHEME
from opendata_atlas.core import reference_service
from opendata_atlas.core.errors import AtlasError
from opendata_atlas.core.reference import CAPABILITIES, topics
from opendata_atlas.portals.registry import load_registry
from opendata_atlas.portals.resolve import allowed_ids, resolve_portal

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastmcp import FastMCP
    from fastmcp.server.completions import CompletionReference
    from mcp.types import CompletionArgument, CompletionContext, Resource

    from opendata_atlas.portals.model import PortalContext


def _topic_index(portal: PortalContext | None, topic: str) -> str:
    return json.dumps(
        reference_service.read(portal, topic, None, paged=False).model_dump(
            mode="json", exclude_none=True, exclude={"source"}
        )
    )


def _index_reader(topic: str) -> Callable[[], str]:
    # A default-argument lambda would be read as a URI template parameter.
    def read() -> str:
        return _topic_index(None, "index" if topic == "reference" else topic)

    return read


def _item(portal: PortalContext | None, topic: str, item_id: str) -> str:
    result = reference_service.read(portal, topic, item_id, paged=False)
    return result.body or ""


_PORTAL_URI = f"{URI_SCHEME}://portals/{{portal}}"
_GUIDES_URI = f"{_PORTAL_URI}/guides"
_GUIDE_URI = f"{_GUIDES_URI}/{{guide_id}}"
_PORTAL_TEMPLATES = frozenset({_PORTAL_URI, _GUIDES_URI, _GUIDE_URI})


_SECTION_URIS = {
    f"{URI_SCHEME}://{topic}/{{section_id}}": topic for topic in ("soql", "errors", "contributing")
}
#: The protocol's cap on one completion response; `total` and `hasMore` report the rest.
COMPLETION_MAX = 100


def _portal_names() -> list[str]:
    """Aliases, then canonical ids, each sorted: every name `{portal}` resolves to a portal."""
    allowed = allowed_ids()
    entries = [
        e
        for e in load_registry().entries.values()
        if e.identity.status == "active" and (allowed is None or e.identity.id in allowed)
    ]
    aliases = sorted(a for e in entries for a in e.identity.aliases)
    return aliases + sorted(e.identity.id for e in entries)


def _guide_ids(context: CompletionContext | None) -> list[str]:
    portal = (context.arguments or {}).get("portal") if context is not None else None
    if not portal:
        return []
    try:
        return [g.guide_id for g in resolve_portal(portal).guides]
    except AtlasError:
        return []


def complete(
    ref: CompletionReference, argument: CompletionArgument, context: CompletionContext | None
) -> Completion | None:
    """Prefix matches, case-insensitive, for `{portal}`, `{guide_id}` and `{section_id}`.

    `{guide_id}` needs `portal` among the context arguments; without a servable one it
    completes to nothing. Any other reference or argument gets an empty completion.
    """
    if not isinstance(ref, ResourceTemplateReference):
        return None
    if argument.name == "portal" and ref.uri in _PORTAL_TEMPLATES:
        names = _portal_names()
    elif argument.name == "guide_id" and ref.uri == _GUIDE_URI:
        names = _guide_ids(context)
    elif argument.name == "section_id" and ref.uri in _SECTION_URIS:
        names = [d.item_id for d in topics(None)[_SECTION_URIS[ref.uri]].documents]
    else:
        return None
    prefix = argument.value.casefold()
    matches = [n for n in names if n.casefold().startswith(prefix)]
    return Completion(
        values=matches[:COMPLETION_MAX],
        total=len(matches),
        has_more=len(matches) > COMPLETION_MAX,
    )


def _resolve(portal: str, template: str) -> PortalContext:
    """A portal failure on a resource names `uri` and reports the template, never the
    caller's value."""
    try:
        return resolve_portal(portal, field="uri")
    except AtlasError as exc:
        exc.envelope.resource_uri = template
        raise


class SizedResource(FunctionResource):
    """A static resource that declares `size`, the UTF-8 bytes `resources/read` returns.

    FastMCP 4.1's `mcp.resource()` takes no `size` and its `to_mcp_resource` drops one, so
    the listing computes it from the body on each `resources/list` and follows the environment.
    """

    def to_mcp_resource(self, **overrides: Any) -> Resource:
        return (
            super()
            .to_mcp_resource(**overrides)
            .model_copy(update={"size": len(self.fn().encode("utf-8"))})
        )


def register_resources(mcp: FastMCP) -> None:
    mcp.add_completion_handler(complete)

    def add_static(
        uri: str, name: str, title: str, description: str, mime_type: str, fn: Callable[[], str]
    ) -> None:
        mcp.add_resource(
            SizedResource.from_function(
                fn,
                uri,
                name=name,
                title=title,
                description=description,
                mime_type=mime_type,
                meta=LIFECYCLE_META,
            )
        )

    def capabilities() -> str:
        return CAPABILITIES

    add_static(
        f"{URI_SCHEME}://capabilities",
        "capabilities",
        "Capability summary",
        "What the server does and does not do, binding rules, and failure carriers. Read first.",
        "text/markdown",
        capabilities,
    )
    for topic, title, description in (
        (
            "reference",
            "Reference index",
            "Every reference topic except guides (see portals).",
        ),
        (
            "portals",
            "Portal index",
            "Curated and profiled portals, each linking its summary.",
        ),
        (
            "soql",
            "SoQL reference index",
            "Sections on syntax, filtering, aggregation, dates, geography, and paging.",
        ),
        (
            "errors",
            "Error catalog index",
            "The error envelope, codes by tool, and authentication repair.",
        ),
        (
            "contributing",
            "Contributing index",
            "Sections defining portal tiers, knowledge levels and validation, and the path for "
            "contributing a portal's pack.",
        ),
    ):
        add_static(
            f"{URI_SCHEME}://{topic}",
            f"{topic}-index",
            title,
            description,
            "application/json",
            _index_reader(topic),
        )

    @mcp.resource(
        f"{URI_SCHEME}://soql/{{section_id}}",
        name="soql-section",
        title="SoQL reference section",
        description="One SoQL section; ids are listed at opendata-atlas://soql.",
        mime_type="text/markdown",
        meta=LIFECYCLE_META,
    )
    def soql_section(section_id: str) -> str:
        return _item(None, "soql", section_id)

    @mcp.resource(
        f"{URI_SCHEME}://errors/{{section_id}}",
        name="errors-section",
        title="Error catalog section",
        description="One error-catalog section: envelope, codes, or authentication.",
        mime_type="text/markdown",
        meta=LIFECYCLE_META,
    )
    def errors_section(section_id: str) -> str:
        return _item(None, "errors", section_id)

    @mcp.resource(
        f"{URI_SCHEME}://contributing/{{section_id}}",
        name="contributing-section",
        title="Contributing section",
        description="One section of the contributing document: tiers, levels, validation, or path.",
        mime_type="text/markdown",
        meta=LIFECYCLE_META,
    )
    def contributing_section(section_id: str) -> str:
        return _item(None, "contributing", section_id)

    @mcp.resource(
        _PORTAL_URI,
        name="portal",
        title="Portal summary",
        description="Identity, tier, knowledge by dataset, and guide index; "
        "{portal} is a portal id or alias.",
        mime_type="text/markdown",
        meta=LIFECYCLE_META,
    )
    def portal_summary(portal: str) -> str:
        _resolve(portal, _PORTAL_URI)
        return _item(None, "portals", portal)

    @mcp.resource(
        _GUIDES_URI,
        name="guides-index",
        title="Dataset guide index",
        description="A portal's dataset guides; {portal} is a portal id or alias.",
        mime_type="application/json",
        meta=LIFECYCLE_META,
    )
    def guides_index(portal: str) -> str:
        return _topic_index(_resolve(portal, _GUIDES_URI), "guides")

    @mcp.resource(
        _GUIDE_URI,
        name="guide",
        title="Dataset guide",
        description="One dataset guide; ids are listed at opendata-atlas://portals/{portal}/guides.",
        mime_type="text/markdown",
        meta=LIFECYCLE_META,
    )
    def guide(portal: str, guide_id: str) -> str:
        return _item(_resolve(portal, _GUIDE_URI), "guides", guide_id)
