"""Build the .mcpb bundle from an allowlisted staging copy, then verify the archive.

`mcpb pack` honors only .mcpbignore, not .gitignore, so packing the working tree can sweep in
eval transcripts or local credential files. Staging copies only what `uv run` needs.

Usage: uv run python scripts/build_bundle.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME_FILES = (
    "manifest.json",
    "pyproject.toml",
    "uv.lock",
    "README.md",
    "LICENSE",
    ".python-version",
    "icon.png",
    "icon-128.png",
)
RUNTIME_TREE = "src/opendata_atlas"
FIXED_REQUIRED = (
    *RUNTIME_FILES,
    f"{RUNTIME_TREE}/__init__.py",
    f"{RUNTIME_TREE}/mcp/server.py",
    f"{RUNTIME_TREE}/core/query.py",
    f"{RUNTIME_TREE}/assets/icon.svg",
    f"{RUNTIME_TREE}/assets/contributing.md",
    f"{RUNTIME_TREE}/portals/registry.json",
    f"{RUNTIME_TREE}/portals/registry_overrides.toml",
    f"{RUNTIME_TREE}/portals/validation.json",
)


def required_files(tree: Path) -> tuple[str, ...]:
    """The fixed runtime files plus each pack's `portal.toml` found under `tree/portals/`.

    Packs are derived, not listed, so a new-pack PR needs no edit to this script.
    """
    packs = sorted(p.parent.name for p in (tree / "portals").glob("*/portal.toml"))
    return (*FIXED_REQUIRED, *(f"{RUNTIME_TREE}/portals/{pack}/portal.toml" for pack in packs))


REQUIRED = required_files(ROOT / RUNTIME_TREE)
#: Runtime data beside the code: icon, served reference text, registry, portal packs. Anything
#: else is stray.
RUNTIME_SUFFIXES = (".py", ".json", ".toml", ".svg", ".md")


def allowed(name: str) -> bool:
    return name in RUNTIME_FILES or (
        name.startswith(RUNTIME_TREE + "/")
        and name.endswith(RUNTIME_SUFFIXES)
        and "__pycache__" not in name
    )


def main() -> int:
    version = json.loads((ROOT / "manifest.json").read_text())["version"]
    out = ROOT / "dist" / f"opendata-atlas-{version}.mcpb"
    out.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "bundle"
        stage.mkdir()
        for name in RUNTIME_FILES:
            shutil.copy2(ROOT / name, stage / name)
        shutil.copytree(
            ROOT / RUNTIME_TREE,
            stage / RUNTIME_TREE,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        subprocess.run(["mcpb", "validate", str(stage / "manifest.json")], check=True)
        subprocess.run(["mcpb", "pack", str(stage), str(out)], check=True)
    names = [n for n in zipfile.ZipFile(out).namelist() if not n.endswith("/")]
    stray = [n for n in names if not allowed(n)]
    if stray:
        print(f"bundle contains files outside the allowlist: {stray}")
        return 1
    missing = [n for n in REQUIRED if n not in names]
    if missing:
        print(f"bundle is missing runtime files: {missing}")
        return 1
    print(f"{out.relative_to(ROOT)}: {len(names)} files, all allowlisted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
