"""Offline checks of the paid curation test's setup (tests/test_curation_skill.py)."""

from __future__ import annotations

from tests.test_curation_skill import (
    ALLOWED_TOOLS,
    RUN_VAR,
    child_env,
    claude_command,
    path_violations,
    tier_failure,
)


def test_child_env_drops_the_opt_in_variable():
    """Nothing the curating agent runs can start a nested, paid curation run."""
    base = {RUN_VAR: "1", "PATH": "/usr/bin", "ATLAS_CURATION_PORTAL": "x.example.gov"}
    assert RUN_VAR in base  # known positive: the variable is there to drop
    env = child_env(base)
    assert RUN_VAR not in env
    assert env == {"PATH": "/usr/bin", "ATLAS_CURATION_PORTAL": "x.example.gov"}


def test_claude_command_is_the_documented_one():
    command = claude_command("data.honolulu.gov")
    assert command[:3] == [
        "claude",
        "-p",
        "Curate data.honolulu.gov by following skills/curate-portal/SKILL.md.",
    ]
    assert command[command.index("--allowedTools") + 1] == ALLOWED_TOOLS
    assert command[command.index("--max-turns") + 1] == "200"
    assert command[command.index("--permission-mode") + 1] == "acceptEdits"
    assert "Bash(git push:*)" not in ALLOWED_TOOLS


def test_claude_command_caps_spend():
    """Ruling 74: the curation session is capped at $12 by the CLI itself."""
    command = claude_command("data.honolulu.gov")
    assert command.count("--max-budget-usd") == 1
    assert command[command.index("--max-budget-usd") + 1] == "12"


def test_claude_command_loads_no_mcp_servers():
    """Ruling 61: `--strict-mcp-config` with no `--mcp-config` restricts MCP servers only: the
    child loads no MCP server from another configuration, and the skill calls the server
    in-process. Plugins, skills, hooks, the user's CLAUDE.md and memory still load (ruling 65);
    whether claude.ai connectors are dropped is not yet probed."""
    command = claude_command("data.honolulu.gov")
    assert "--strict-mcp-config" in command
    assert "--mcp-config" not in command


def test_path_rule_allows_the_pack_paths_and_flags_others():
    pack = "data.honolulu.gov"
    allowed = [
        f"src/opendata_atlas/portals/{pack}/portal.toml",
        f"src/opendata_atlas/portals/{pack}/facts/6hui-dvrh.toml",
        f"evals/portals/{pack}.json",
        "src/opendata_atlas/portals/registry_overrides.toml",
        "src/opendata_atlas/portals/validation.json",
        "docs/decisions.md",
    ]
    assert path_violations(allowed, pack) == []
    foreign = [
        "src/opendata_atlas/portals/seattle/guides.py",
        "evals/portals/seattle.json",
        "src/opendata_atlas/portals/tiers.py",
        f"src/opendata_atlas/portals/{pack}x/portal.toml",
    ]
    assert path_violations(allowed + foreign, pack) == foreign


def test_tier_check_allows_at_most_profiled():
    """Ruling 64: the curating agent never promotes its own pack."""
    assert tier_failure("profiled") is None
    assert tier_failure("generic") is None
    assert tier_failure("curated") is not None  # known positive: run 2 declared this
