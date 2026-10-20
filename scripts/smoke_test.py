"""Start the server the way a user would, from a checkout or a built artifact, and check it answers.

- `--checkout DIR`: run the command README's "Try it locally" gives for a checkout.
- `--wheel PATH`: install the wheel into a fresh venv and run its console script.
- `--sdist PATH`: the same from the sdist, which builds it first, as an installer without a
  matching wheel would.
- `--uvx PATH`: run the wheel with `uvx --from`, as README's "Try it locally" does.
- `--bundle PATH`: unpack the .mcpb and run the command its manifest gives the host, with the
  app token left as the unexpanded placeholder a host passes when the user leaves it blank.

Each way the server must answer `server/discover` (the modern handshake), list exactly the tools
in `tests/snapshots/tools_list.json`, and serve the reference index. None of that touches the
network. `--live` adds one free live call, `LIVE_CALL`, which must not be an error.

Usage: uv run python scripts/smoke_test.py (--checkout . | --wheel dist/*.whl |
       --sdist dist/*.tar.gz | --uvx dist/*.whl | --bundle dist/*.mcpb) [--live]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "tests" / "snapshots" / "tools_list.json"
#: One free live call: a describe summary of Seattle's Fire 911 dataset.
LIVE_CALL = ("atlas_describe_dataset", {"portal": "seattle", "dataset_id": "kzjm-xkqj"})


def expected_tools() -> list[str]:
    return sorted(tool["name"] for tool in json.loads(SNAPSHOT.read_text())["tools"])


def checkout_command(root: Path) -> tuple[str, list[str], dict[str, str]]:
    return "uv", ["run", "--directory", str(root), "--frozen", "opendata-atlas"], {}


def uvx_command(wheel: Path, work: Path) -> tuple[str, list[str], dict[str, str]]:
    del work  # uvx keeps its own environment; the parameter matches the other builders
    return "uvx", ["--from", str(wheel), "opendata-atlas"], {}


def package_command(package: Path, work: Path) -> tuple[str, list[str], dict[str, str]]:
    venv = work / "venv"
    subprocess.run(["uv", "venv", "--quiet", str(venv)], check=True)
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run(
        ["uv", "pip", "install", "--quiet", "--python", str(python), str(package)], check=True
    )
    script = venv / ("Scripts/opendata-atlas.exe" if os.name == "nt" else "bin/opendata-atlas")
    return str(script), [], {}


def bundle_command(bundle: Path, work: Path) -> tuple[str, list[str], dict[str, str]]:
    unpacked = work / "bundle"
    zipfile.ZipFile(bundle).extractall(unpacked)
    config = json.loads((unpacked / "manifest.json").read_text())["server"]["mcp_config"]
    args = [arg.replace("${__dirname}", str(unpacked)) for arg in config["args"]]
    return config["command"], args, dict(config.get("env", {}))


async def check(
    command: str, args: list[str], env: dict[str, str], cwd: Path, *, live: bool = False
) -> list[str]:
    # A host starts the server outside any virtualenv; drop the one `uv run` set for this script.
    inherited = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    transport = StdioTransport(command=command, args=args, env={**inherited, **env}, cwd=str(cwd))
    async with Client(transport) as client:
        problems = []
        negotiated = client.protocol_version or ""
        if client.initialize_result is not None or not negotiated.startswith("2026"):
            problems.append(f"no server/discover: negotiated {negotiated!r}")
        tools = sorted(tool.name for tool in await client.list_tools())
        if tools != expected_tools():
            problems.append(f"tools {tools} != snapshot {expected_tools()}")
        index = await client.call_tool("atlas_get_reference", {}, raise_on_error=False)
        if index.is_error or not index.structured_content:
            problems.append(f"reference index failed: {index.content}")
        if live:
            name, arguments = LIVE_CALL
            result = await client.call_tool(name, arguments, raise_on_error=False)
            if result.is_error:
                problems.append(f"live call {name} failed: {result.content}")
        return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    kind = parser.add_mutually_exclusive_group(required=True)
    kind.add_argument("--checkout", type=Path, metavar="DIR")
    kind.add_argument("--wheel", type=Path)
    kind.add_argument("--sdist", type=Path)
    kind.add_argument("--uvx", type=Path, metavar="WHEEL")
    kind.add_argument("--bundle", type=Path)
    parser.add_argument("--live", action="store_true", help=f"also make the live call {LIVE_CALL}")
    opts = parser.parse_args()
    artifact: Path = (
        opts.checkout or opts.wheel or opts.sdist or opts.uvx or opts.bundle
    ).resolve()
    with tempfile.TemporaryDirectory() as tmp:
        if opts.checkout:
            command, args, env = checkout_command(artifact)
        else:
            build = bundle_command if opts.bundle else uvx_command if opts.uvx else package_command
            command, args, env = build(artifact, Path(tmp))
        problems = asyncio.run(check(command, args, env, Path(tmp), live=opts.live))
    if problems:
        print(f"{artifact.name}: FAILED")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    live = ", live call ok" if opts.live else ""
    tools = len(expected_tools())
    print(f"{artifact.name}: server started, {tools} tools, reference index served{live}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
