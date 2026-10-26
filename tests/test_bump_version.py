"""`scripts/bump_version.py` rewrites every version site, or none (#30)."""

from __future__ import annotations

import importlib.util
import shutil
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("bump_version", ROOT / "scripts" / "bump_version.py")
assert _spec is not None
assert _spec.loader is not None
bump_version = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bump_version)

OLD = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]


def _copy(tmp_path: Path) -> Path:
    for path, *_ in bump_version.sites(OLD, "9.9.9"):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / path, tmp_path / path)
    return tmp_path


def test_bump_rewrites_every_site(tmp_path: Path):
    root = _copy(tmp_path)
    changed = bump_version.bump(root, "9.9.9")
    assert len(changed) == 7
    for path, before, after, count in bump_version.sites(OLD, "9.9.9"):
        text = (root / path).read_text()
        assert before not in text, path
        assert text.count(after) == count, path


def test_a_missing_site_writes_nothing(tmp_path: Path):
    root = _copy(tmp_path)
    readme = root / "README.md"
    readme.write_text(readme.read_text().replace(f"Version {OLD} is on", "Version is on"))
    before = (root / "pyproject.toml").read_text()
    with pytest.raises(SystemExit, match=r"README\.md"):
        bump_version.bump(root, "9.9.9")
    assert (root / "pyproject.toml").read_text() == before


@pytest.mark.parametrize("bad", ["1.2", "v1.2.3", OLD])
def test_bad_or_unchanged_versions_are_refused(tmp_path: Path, bad: str):
    with pytest.raises(SystemExit):
        bump_version.bump(_copy(tmp_path), bad)
