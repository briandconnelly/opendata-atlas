"""Codex CLI connects with the legacy initialize handshake (docs/host-captures); keep it working."""

from __future__ import annotations

import base64
import xml.etree.ElementTree as ET

import pytest
from fastmcp import Client

from opendata_atlas.core.reference import INSTRUCTIONS
from opendata_atlas.mcp.server import build_server
from tests.conftest import wire


async def test_legacy_handshake_serves_the_same_contract():
    async with Client(build_server(), mode="legacy") as legacy, Client(build_server()) as modern:
        assert legacy.initialize_result is not None
        assert not (legacy.protocol_version or "").startswith("2026")
        assert legacy.initialize_result.instructions == INSTRUCTIONS

        legacy_tools = wire(await legacy.list_tools_mcp())["tools"]
        modern_tools = wire(await modern.list_tools_mcp())["tools"]
        assert legacy_tools == modern_tools

        result = wire(
            await legacy.call_tool_mcp(
                "atlas_query_dataset",
                {"portal": "seattle", "dataset_id": "kzjm-xkqj", "mode": "soql"},
            )
        )
        assert result["isError"] is True
        assert result["structuredContent"]["code"] == "invalid_argument"


@pytest.mark.parametrize("mode", ["legacy", "modern"])
async def test_capabilities_advertise_a_fixed_surface_without_prompts(mode):
    """[9.list-changed]: the surface never changes in a process; there are no prompts."""
    kwargs = {"mode": "legacy"} if mode == "legacy" else {}
    async with Client(build_server(), **kwargs) as client:
        capabilities = client.server_capabilities.model_dump(exclude_none=True)
    assert "prompts" not in capabilities
    assert not capabilities["tools"].get("list_changed")
    assert not capabilities["resources"].get("list_changed")


@pytest.mark.parametrize("mode", ["legacy", "modern"])
async def test_server_info_has_title_and_icon(mode):
    kwargs = {"mode": "legacy"} if mode == "legacy" else {}
    async with Client(build_server(), **kwargs) as client:
        info = client.server_info
    assert info.name == "opendata-atlas"
    assert info.title == "Open Data Atlas"
    assert info.icons is not None and len(info.icons) == 1
    icon = info.icons[0]
    assert icon.mime_type == "image/svg+xml"
    assert icon.src.startswith("data:image/svg+xml;base64,")
    svg = base64.b64decode(icon.src.split(",", 1)[1]).decode()
    assert svg.lstrip().startswith("<svg")


SVG_NS = "{http://www.w3.org/2000/svg}"
ICON_SHAPES = [
    ("rect", {"width": "64", "height": "64", "rx": "12", "fill": "#1f4e79"}),
    ("path", {"d": "M10 18 22 14 42 20 54 16V46L42 50 22 44 10 48Z", "fill": "#f2efe6"}),
    ("path", {"d": "M22 14V44M42 20V50", "stroke": "#1f4e79", "stroke-width": "2"}),
    ("circle", {"cx": "32", "cy": "30", "r": "5", "fill": "#d9534f"}),
]


async def test_icon_is_minified():
    """The icon rides in every modern result's `_meta` stamp, so its bytes are paid per call."""
    async with Client(build_server()) as client:
        info = client.server_info
    assert info.icons is not None
    src = info.icons[0].src
    assert len(src) <= 432, len(src)
    root = ET.fromstring(base64.b64decode(src.split(",", 1)[1]).decode())
    assert root.tag == f"{SVG_NS}svg"
    assert root.get("viewBox") == "0 0 64 64"
    assert [(child.tag.removeprefix(SVG_NS), child.attrib) for child in root] == ICON_SHAPES


@pytest.mark.parametrize("mode", ["legacy", "modern"])
async def test_no_unserved_extensions_advertised(mode):
    """The server serves no UI resource, so it must not advertise the UI extension."""
    # The legacy case cannot regress: FastMCP never advertises the extension there (the SDK
    # strips `extensions` for pre-2026 eras). The modern case is the real check.
    kwargs = {"mode": "legacy"} if mode == "legacy" else {}
    async with Client(build_server(), **kwargs) as client:
        capabilities = client.server_capabilities.model_dump(exclude_none=True)
    assert "io.modelcontextprotocol/ui" not in capabilities.get("extensions", {})
