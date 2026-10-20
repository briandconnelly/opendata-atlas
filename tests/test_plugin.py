"""The Claude Code and Codex plugin, and the marketplaces that list it, must not drift."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "opendata-atlas"
SKILL = "skills/curate-portal"
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


def _frontmatter(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8").split("---\n")[1])


def test_plugin_skill_follows_the_clones_skill():
    """A copy would freeze at the plugin's release; the stub reads the clone's file instead."""
    stub = PLUGIN / SKILL / "SKILL.md"
    assert _frontmatter(stub)["name"] == _frontmatter(ROOT / SKILL / "SKILL.md")["name"]
    text = stub.read_text(encoding="utf-8")
    assert f"`{SKILL}/SKILL.md`" in text
    assert 'name = "opendata-atlas"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '`name = "opendata-atlas"`' in text
    assert sorted(
        p.relative_to(PLUGIN / SKILL).as_posix() for p in (PLUGIN / SKILL).rglob("*")
    ) == [
        "SKILL.md",
        "agents",
        "agents/openai.yaml",
    ]


def test_codex_starts_curate_portal_only_when_named():
    """It commits and can start paid eval runs, so Codex must not pick it on its own."""
    path = PLUGIN / SKILL / "agents" / "openai.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert config["policy"]["allow_implicit_invocation"] is False
    assert "$curate-portal" in config["interface"]["default_prompt"]


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
