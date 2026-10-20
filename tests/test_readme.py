"""README's "Try it locally" commands are the ones `scripts/smoke_test.py` verified."""

from __future__ import annotations

import importlib.util
import json
import re
import shlex
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKOUT = Path("/path/to/opendata-atlas")
WHEEL = Path("/path/to/dist/opendata_atlas-0.1.0-py3-none-any.whl")


def _smoke():
    spec = importlib.util.spec_from_file_location("smoke_test", ROOT / "scripts" / "smoke_test.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _section() -> str:
    text = (ROOT / "README.md").read_text()
    match = re.search(r"^## Try it locally\n(.*?)(?=^## )", text, re.S | re.M)
    assert match, "README has a '## Try it locally' section"
    return match.group(1)


def _blocks(lang: str) -> list[str]:
    return re.findall(rf"^```{lang}\n(.*?)^```", _section(), re.S | re.M)


def _argv(command: str, args: list[str]) -> list[str]:
    """The command line, with path separators as the README writes them (`/`, on Windows too)."""
    return [command, *(a.replace("\\", "/") for a in args)]


def test_try_it_locally_matches_smoke():
    smoke = _smoke()
    command, args, env = smoke.checkout_command(CHECKOUT)
    assert env == {}
    uvx_command, uvx_args, uvx_env = smoke.uvx_command(WHEEL, Path("/unused"))
    assert uvx_env == {}

    servers = [json.loads(block)["mcpServers"]["opendata-atlas"] for block in _blocks("json")]
    assert [_argv(s["command"], s["args"]) for s in servers] == [
        _argv(command, args),
        _argv(uvx_command, uvx_args),
    ]

    adds = [
        shlex.split(line)
        for block in _blocks("bash")
        for line in block.splitlines()
        if line.startswith("claude mcp add ")
    ]
    assert [add[: add.index("--")] for add in adds] == [
        ["claude", "mcp", "add", "opendata-atlas"]
    ] * 2
    assert [add[add.index("--") + 1 :] for add in adds] == [
        _argv(command, args),
        _argv(uvx_command, uvx_args),
    ]


def test_try_it_locally_names_the_built_artifacts():
    """The wheel and bundle names in the section are the ones `uv build` and `make mcpb` write."""
    smoke = _smoke()
    version = json.loads((ROOT / "manifest.json").read_text())["version"]
    section = _section()
    assert WHEEL.name == f"opendata_atlas-{version}-py3-none-any.whl"
    assert f"dist/opendata-atlas-{version}.mcpb" in section
    assert smoke.LIVE_CALL == (
        "atlas_describe_dataset",
        {"portal": "seattle", "dataset_id": "kzjm-xkqj"},
    )


def test_readme_names_the_curated_portals():
    """The status line's curated portals are the registry's `curated` tier, by first alias."""
    from opendata_atlas.portals.registry import load_registry

    text = (ROOT / "README.md").read_text()
    match = re.search(r"(?:portal is|portals are) curated: ([^\n]*?)\.(?:\s|$)", text)
    assert match, "README names the curated portals ('... curated: Name (`alias`) ...')"
    named = re.findall(r"`([^`]+)`", match.group(1))
    curated = [
        e.identity.aliases[0] if e.identity.aliases else e.identity.id
        for e in load_registry().entries.values()
        if e.identity.tier == "curated"
    ]
    assert curated, "known positive: the registry declares a curated portal"
    assert sorted(named) == sorted(curated)
