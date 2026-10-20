"""The Claude Code and Codex plugin, and the marketplaces that list it, must not drift."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "opendata-atlas"
SKILL = "skills/curate-portal/SKILL.md"
#: Each catalog, by the tool that reads it.
CATALOGS = {
    "claude-code": ROOT / ".claude-plugin" / "marketplace.json",
    "codex": ROOT / ".agents" / "plugins" / "marketplace.json",
}
#: Each plugin manifest and the MCP file the same tool reads beside it.
PACKAGES = {
    "claude-code": (PLUGIN / ".claude-plugin" / "plugin.json", PLUGIN / ".mcp.json"),
    "codex": (PLUGIN / "plugin.json", PLUGIN / "mcp.json"),
}


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]


def test_plugin_skill_matches_repository_skill():
    assert (PLUGIN / SKILL).read_bytes() == (ROOT / SKILL).read_bytes(), (
        f"plugins/opendata-atlas/{SKILL} differs from {SKILL}: edit the repository copy, "
        f"then copy it (cp {SKILL} plugins/opendata-atlas/{SKILL})"
    )


def test_plugin_ships_only_the_curate_portal_skill():
    assert sorted(p.name for p in (PLUGIN / "skills").iterdir()) == ["curate-portal"]


def test_every_version_and_server_pin_is_the_project_version():
    version = _version()
    for tool, (manifest, mcp) in PACKAGES.items():
        assert _json(manifest)["version"] == version, tool
        (server,) = _json(mcp)["mcpServers"].values()
        assert server["command"] == "uvx", tool
        assert server["args"] == [f"opendata-atlas=={version}"], tool
    for tool, catalog in CATALOGS.items():
        for entry in _json(catalog)["plugins"]:
            assert entry.get("version", version) == version, tool


def test_catalogs_list_the_plugin_by_its_manifest_name():
    names = {tool: _json(manifest)["name"] for tool, (manifest, _) in PACKAGES.items()}
    assert set(names.values()) == {"opendata-atlas"}, names
    for tool, catalog in CATALOGS.items():
        (entry,) = _json(catalog)["plugins"]
        assert entry["name"] == names[tool], tool
        source = entry["source"]
        path = source if isinstance(source, str) else source["path"]
        assert (ROOT / path).resolve() == PLUGIN, tool
