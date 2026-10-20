"""scripts/pack_digest.py: the curate-portal skill's freeze record (rule 13)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "pack_digest.py"
_spec = importlib.util.spec_from_file_location("pack_digest", SCRIPT)
assert _spec is not None and _spec.loader is not None
pack_digest_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pack_digest_module)
pack_digest = pack_digest_module.pack_digest

PACK = "data.example.gov"


def _tree(root: Path) -> Path:
    pack = root / "src" / "opendata_atlas" / "portals" / PACK
    (pack / "facts").mkdir(parents=True)
    (pack / "portal.toml").write_text('id = "data.example.gov"\n')
    (pack / "facts" / "abcd-1234.toml").write_text("[[claim]]\n")
    (pack / "guides.py").write_text("GUIDES = ()\n")
    (root / "evals" / "portals").mkdir(parents=True)
    (root / "evals" / "portals" / f"{PACK}.json").write_text("[]\n")
    return pack


def test_digest_is_stable(tmp_path):
    _tree(tmp_path)
    first = pack_digest(tmp_path, PACK)
    assert first.startswith("sha256:")
    assert pack_digest(tmp_path, PACK) == first


def test_a_pack_edit_changes_the_digest(tmp_path):
    """Known positive for the freeze check: a formatter's line wrap is a change."""
    pack = _tree(tmp_path)
    before = pack_digest(tmp_path, PACK)
    (pack / "guides.py").write_text("GUIDES = (\n)\n")
    assert pack_digest(tmp_path, PACK) != before


def test_an_eval_file_edit_changes_the_digest(tmp_path):
    _tree(tmp_path)
    before = pack_digest(tmp_path, PACK)
    (tmp_path / "evals" / "portals" / f"{PACK}.json").write_text('[{"id": "x"}]\n')
    assert pack_digest(tmp_path, PACK) != before


def test_a_renamed_file_changes_the_digest(tmp_path):
    pack = _tree(tmp_path)
    before = pack_digest(tmp_path, PACK)
    (pack / "facts" / "abcd-1234.toml").rename(pack / "facts" / "wxyz-9876.toml")
    assert pack_digest(tmp_path, PACK) != before


def test_bytecode_caches_are_ignored(tmp_path):
    pack = _tree(tmp_path)
    before = pack_digest(tmp_path, PACK)
    (pack / "__pycache__").mkdir()
    (pack / "__pycache__" / "guides.cpython-313.pyc").write_bytes(b"\0")
    assert pack_digest(tmp_path, PACK) == before


def test_cli_prints_the_digest(tmp_path):
    _tree(tmp_path)
    done = subprocess.run(
        [sys.executable, str(SCRIPT), PACK, "--root", str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert done.stdout.strip() == pack_digest(tmp_path, PACK)
