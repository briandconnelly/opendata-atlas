"""The MCPB manifest is generated from pyproject and the live server; it must not drift."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _generator():
    spec = importlib.util.spec_from_file_location(
        "gen_manifest", ROOT / "scripts" / "gen_manifest.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manifest_matches_generator():
    gen = _generator()
    assert (ROOT / "manifest.json").read_text() == gen.render(gen.build_manifest())


def test_token_is_sensitive_and_optional():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    token = manifest["user_config"]["app_token"]
    assert token["sensitive"] is True and token["required"] is False
    assert manifest["server"]["mcp_config"]["env"] == {
        "SOCRATA_APP_TOKEN": "${user_config.app_token}"
    }


def test_manifest_icons_are_square_pngs_of_declared_size():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    sources = {icon["src"] for icon in manifest["icons"]}
    assert manifest["icon"] in sources
    for icon in manifest["icons"]:
        data = (ROOT / icon["src"]).read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n", icon["src"]
        width, height = int.from_bytes(data[16:20]), int.from_bytes(data[20:24])
        assert f"{width}x{height}" == icon["size"], icon["src"]


def _bundle_script():
    spec = importlib.util.spec_from_file_location(
        "build_bundle", ROOT / "scripts" / "build_bundle.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bundle_allowlist_admits_every_runtime_file():
    """The staged tree is a copy of src/opendata_atlas; data files must pass the stray check."""
    bundle = _bundle_script()
    tree = ROOT / bundle.RUNTIME_TREE
    staged = [
        p.relative_to(ROOT).as_posix()
        for p in tree.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    ]
    assert [name for name in staged if not bundle.allowed(name)] == []
    for name in (
        "assets/icon.svg",
        "assets/contributing.md",
        "portals/registry.json",
        "portals/registry_overrides.toml",
        "portals/seattle/portal.toml",
        # Final review M-2: without it every asserted claim reads unchecked, never stale.
        "portals/validation.json",
    ):
        required = f"{bundle.RUNTIME_TREE}/{name}"
        assert required in bundle.REQUIRED
        assert required in staged


#: The packs this release ships; each must reach every artifact.
PACKS = ("seattle", "data.cityofchicago.org")
#: Names no shipped archive may hold: test fixtures, evals, curation working files.
NOT_SHIPPED = ("tests/", "fixtures/", "evals/", ".curation/")


def test_wheel_and_sdist_ship_runtime_data_not_fixtures(tmp_path):
    """The wheel carries the packs and served data; neither archive carries test or eval files.

    Final review M-2 pinned `validation.json` in the wheel; this keeps that pin.
    """
    subprocess.run(["uv", "build", "--quiet", "--out-dir", str(tmp_path)], cwd=ROOT, check=True)
    (wheel,) = tmp_path.glob("*.whl")
    (sdist,) = tmp_path.glob("*.tar.gz")
    wheel_names = zipfile.ZipFile(wheel).namelist()
    with tarfile.open(sdist) as archive:
        sdist_names = archive.getnames()
    assert "opendata_atlas/portals/registry.json" in wheel_names, "known positive"
    assert any(n.endswith("src/opendata_atlas/portals/registry.json") for n in sdist_names)
    for name in (
        "assets/icon.svg",
        "assets/contributing.md",
        "portals/registry.json",
        "portals/validation.json",
        *(f"portals/{pack}/portal.toml" for pack in PACKS),
    ):
        assert f"opendata_atlas/{name}" in wheel_names, name
    for names in (wheel_names, sdist_names):
        assert [n for n in names if any(part in n for part in NOT_SHIPPED)] == []


def test_bundle_requires_every_pack():
    bundle = _bundle_script()
    tree = ROOT / bundle.RUNTIME_TREE
    shipped = sorted(p.parent.name for p in (tree / "portals").glob("*/portal.toml"))
    assert set(PACKS) <= set(shipped), "known positive: both curated packs are found"
    for pack in shipped:
        assert f"{bundle.RUNTIME_TREE}/portals/{pack}/portal.toml" in bundle.REQUIRED, pack


def test_bundle_requires_a_new_pack_without_a_script_edit(tmp_path):
    """A pack directory the script never heard of is required, so a pack PR needs no script edit."""
    bundle = _bundle_script()
    pack = tmp_path / "portals" / "data.example.gov"
    pack.mkdir(parents=True)
    (pack / "portal.toml").write_text("")
    (tmp_path / "portals" / "no-toml").mkdir()
    required = bundle.required_files(tmp_path)
    assert f"{bundle.RUNTIME_TREE}/portals/data.example.gov/portal.toml" in required
    assert not any("no-toml" in name for name in required)
    assert f"{bundle.RUNTIME_TREE}/portals/seattle/portal.toml" not in required
    assert set(bundle.required_files(ROOT / bundle.RUNTIME_TREE)) == set(bundle.REQUIRED)
