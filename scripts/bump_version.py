#!/usr/bin/env python
"""Set the project version everywhere `docs/releasing.md` lists, then relock and regenerate.

Edits `pyproject.toml`, both plugin manifests and both plugin MCP files, CONTRIBUTING's
"Try it locally" wheel and bundle paths, and the README's status line; then runs `uv lock` and
`scripts/gen_manifest.py`. Every edit must match the number of sites it expects, or nothing is
written. It does not touch `CHANGELOG.md`: cut that with `scripts/rehearse_release.py --apply`.

Usage:
    uv run python scripts/bump_version.py <X.Y.Z>
    uv run python scripts/bump_version.py <X.Y.Z> --no-lock    # edits only (tests use this)
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION = re.compile(r"\d+\.\d+\.\d+")
PLUGIN = Path("plugins/opendata-atlas")


def sites(old: str, new: str) -> list[tuple[Path, str, str, int]]:
    """(file, old text, new text, how many times it must occur)."""
    return [
        (Path("pyproject.toml"), f'version = "{old}"', f'version = "{new}"', 1),
        (PLUGIN / ".claude-plugin/plugin.json", f'"version": "{old}"', f'"version": "{new}"', 1),
        (PLUGIN / "plugin.json", f'"version": "{old}"', f'"version": "{new}"', 1),
        (PLUGIN / ".mcp.json", f"opendata-atlas=={old}", f"opendata-atlas=={new}", 1),
        (PLUGIN / "mcp.json", f"opendata-atlas=={old}", f"opendata-atlas=={new}", 1),
        (Path("CONTRIBUTING.md"), f"opendata_atlas-{old}-py3", f"opendata_atlas-{new}-py3", 3),
        (Path("CONTRIBUTING.md"), f"opendata-atlas-{old}.mcpb", f"opendata-atlas-{new}.mcpb", 2),
        (Path("README.md"), f"Version {old} is on", f"Version {new} is on", 1),
    ]


def bump(root: Path, new: str) -> list[Path]:
    """Rewrite every site under `root` from the current version to `new`; returns the files."""
    if not VERSION.fullmatch(new):
        raise SystemExit(f"bump_version: {new!r} is not X.Y.Z")
    old = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    if old == new:
        raise SystemExit(f"bump_version: the version is already {new}")
    texts: dict[Path, str] = {}
    for path, before, after, count in sites(old, new):
        text = texts.get(path) or (root / path).read_text(encoding="utf-8")
        found = text.count(before)
        if found != count:
            raise SystemExit(f"bump_version: {path}: {before!r} occurs {found} times, not {count}")
        texts[path] = text.replace(before, after)
    for path, text in texts.items():
        (root / path).write_text(text, encoding="utf-8")
    return sorted(texts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version")
    parser.add_argument("--no-lock", action="store_true", help="skip uv lock and gen_manifest")
    args = parser.parse_args()
    for path in bump(REPO_ROOT, args.version):
        print(f"updated {path}")
    if args.no_lock:
        return
    for command in (["uv", "lock"], [sys.executable, "scripts/gen_manifest.py"]):
        subprocess.run(command, cwd=REPO_ROOT, check=True)
    print("updated uv.lock and manifest.json; now cut CHANGELOG.md (docs/releasing.md)")


if __name__ == "__main__":
    main()
