"""Print a digest of a knowledge pack and its eval file, the curate-portal skill's freeze record.

    uv run python scripts/pack_digest.py <pack> [--root DIR]

The digest covers every file under `src/opendata_atlas/portals/<pack>/` (bytecode caches
excluded) and `evals/portals/<pack>.json`, by path and content. The skill records it in
`.curation/outcome.json` when step 11.3 starts and checks it again before the commit, so a pack
change after the eval runs began is visible (skill rule 13); `tests/test_curation_skill.py`
recomputes it on the committed tree.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

PORTALS = Path("src/opendata_atlas/portals")


def _files(root: Path, pack: str) -> list[Path]:
    pack_dir = root / PORTALS / pack
    found = [
        p
        for p in pack_dir.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    ]
    eval_file = root / "evals" / "portals" / f"{pack}.json"
    return sorted([*found, eval_file] if eval_file.is_file() else found)


def pack_digest(root: Path, pack: str) -> str:
    """`sha256:<hex>` over each file's path relative to `root` and its bytes, in path order."""
    h = hashlib.sha256()
    for path in _files(root, pack):
        rel = path.relative_to(root).as_posix().encode()
        data = path.read_bytes()
        h.update(len(rel).to_bytes(8, "big") + rel + len(data).to_bytes(8, "big") + data)
    return f"sha256:{h.hexdigest()}"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("pack", help="the pack directory's name, e.g. data.kingcounty.gov")
    p.add_argument("--root", type=Path, default=Path(), help="repository root (default .)")
    args = p.parse_args()
    if not (args.root / PORTALS / args.pack).is_dir():
        p.error(f"no pack directory {PORTALS / args.pack} under {args.root}")
    print(pack_digest(args.root, args.pack))


if __name__ == "__main__":
    main()
