"""Declared tiers hold the conditions decidable from pack contents (docs/design.md, Knowledge
levels). Identity verification, the smoke test and the eval runs are live; the promotion PR's
CI runs them."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from opendata_atlas.portals import freshness
from opendata_atlas.portals.loader import SEATTLE, load_portal
from opendata_atlas.portals.registry import Registry, load_registry
from opendata_atlas.portals.tiers import COVERS, tier_violations
from tests.conftest import PORTALS_DIR

EVALS_DIR = Path(__file__).resolve().parent.parent / "evals" / "portals"


def _packs(packs_dir: Path = PORTALS_DIR) -> list[Path]:
    return sorted(d for d in packs_dir.iterdir() if (d / "portal.toml").is_file())


def _registry_only_violations(registry: Registry, pack_ids: set[str]) -> list[str]:
    return [
        f"{e.identity.id}: {e.identity.tier}"
        for e in registry.entries.values()
        if e.identity.id not in pack_ids and e.identity.tier != "generic"
    ]


def _copy_seattle(tmp_path: Path) -> Path:
    pack = tmp_path / "packs" / "seattle"
    shutil.copytree(SEATTLE, pack, ignore=shutil.ignore_patterns("__pycache__"))
    return pack


def _set_tier(pack: Path, tier: str) -> None:
    toml = pack / "portal.toml"
    text = toml.read_text()
    assert 'tier = "curated"' in text
    toml.write_text(text.replace('tier = "curated"', f'tier = "{tier}"'))


def test_shipped_packs_satisfy_their_tiers():
    packs = _packs()
    assert packs, "no shipped pack found"
    for pack in packs:
        portal = load_portal(pack)
        assert tier_violations(portal, pack, EVALS_DIR, today=freshness.today()) == [], pack.name


def test_seattle_copy_is_a_clean_baseline(tmp_path):
    """The synthetic packs below start from this copy, so each violation is the edit's."""
    pack = _copy_seattle(tmp_path)
    assert tier_violations(load_portal(pack), pack, EVALS_DIR, today=freshness.today()) == []


def test_curated_without_guide_violates(tmp_path):
    pack = _copy_seattle(tmp_path)
    (pack / "guides.py").unlink()
    violations = tier_violations(load_portal(pack), pack, EVALS_DIR, today=freshness.today())
    assert len(violations) == 1
    assert violations[0].startswith("curated:") and "guide" in violations[0]


@pytest.mark.parametrize("dropped", COVERS)
def test_curated_without_eval_coverage_violates(tmp_path, dropped):
    pack = _copy_seattle(tmp_path)
    evals = tmp_path / "evals"
    evals.mkdir()
    tasks = json.loads((EVALS_DIR / "seattle.json").read_text())
    for task in tasks:
        if "covers" in task:
            task["covers"] = [c for c in task["covers"] if c != dropped]
    (evals / "seattle.json").write_text(json.dumps(tasks))
    violations = tier_violations(load_portal(pack), pack, evals, today=freshness.today())
    assert len(violations) == 1
    assert violations[0].startswith("curated:") and f"`{dropped}`" in violations[0]


def test_curated_without_eval_file_violates(tmp_path):
    pack = _copy_seattle(tmp_path)
    empty = tmp_path / "evals"
    empty.mkdir()
    violations = tier_violations(load_portal(pack), pack, empty, today=freshness.today())
    assert len(violations) == 1
    assert violations[0].startswith("curated:") and "seattle.json" in violations[0]


def test_curated_with_unreadable_eval_file_violates(tmp_path):
    pack = _copy_seattle(tmp_path)
    evals = tmp_path / "evals"
    evals.mkdir()
    (evals / "seattle.json").write_text("{not json")
    violations = tier_violations(load_portal(pack), pack, evals, today=freshness.today())
    assert len(violations) == 1
    assert violations[0].startswith("curated:") and "seattle.json" in violations[0]


@pytest.mark.parametrize(
    "tasks",
    [
        {"id": "x"},
        [{"id": "x", "covers": "in_area"}],
        ["not a task"],
        [{"id": "x", "covers": [["in_area"]]}],
        [{"id": "x", "covers": [1]}],
    ],
    ids=["object", "covers-string", "task-string", "covers-entry-list", "covers-entry-number"],
)
def test_curated_with_malformed_eval_tasks_violates(tmp_path, tasks):
    """A `covers` string is not iterated letter by letter, and a `covers` entry that is not a
    string (even an unhashable list) is a violation, never a TypeError: the file is reported
    unreadable."""
    pack = _copy_seattle(tmp_path)
    evals = tmp_path / "evals"
    evals.mkdir()
    (evals / "seattle.json").write_text(json.dumps(tasks))
    violations = tier_violations(load_portal(pack), pack, evals, today=freshness.today())
    assert len(violations) == 1
    assert violations[0].startswith("curated: cannot read eval tasks seattle.json"), violations


def test_curated_with_only_stale_reviews_violates(tmp_path):
    """Levels come from `pack_levels` at `today`: a review whose checks went stale is gone."""
    pack = _copy_seattle(tmp_path)
    late = freshness.today().replace(year=freshness.today().year + 2)
    violations = tier_violations(load_portal(pack), pack, EVALS_DIR, today=late)
    assert any(v.startswith("curated:") and "reviewed" in v for v in violations)


def test_profiled_without_claims_violates(tmp_path):
    pack = _copy_seattle(tmp_path)
    _set_tier(pack, "profiled")
    shutil.rmtree(pack / "facts")
    (pack / "regions.toml").unlink(missing_ok=True)
    violations = tier_violations(load_portal(pack), pack, EVALS_DIR, today=freshness.today())
    assert len(violations) == 1
    assert violations[0].startswith("profiled:") and "claim" in violations[0]


def test_profiled_with_claims_holds(tmp_path):
    """A profiled pack needs no guide, review or eval file: only a claim."""
    pack = _copy_seattle(tmp_path)
    _set_tier(pack, "profiled")
    (pack / "guides.py").unlink()
    empty = tmp_path / "evals"
    empty.mkdir()
    assert tier_violations(load_portal(pack), pack, empty, today=freshness.today()) == []


def test_registry_only_portals_are_generic():
    registry = load_registry()
    pack_ids = {load_portal(d).identity.id for d in _packs()}
    assert len(registry.entries) > len(pack_ids), "the registry lists portals without a pack"
    assert _registry_only_violations(registry, pack_ids) == []


def test_registry_only_check_flags_a_declared_tier(tmp_path):
    """Known positive: a registry entry without a pack that declares `profiled` is flagged."""
    raw = json.loads((PORTALS_DIR / "registry.json").read_text())
    entry = next(e for e in raw["entries"] if e["identity"]["tier"] == "generic")
    entry["identity"]["tier"] = "profiled"
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(raw))
    no_packs = tmp_path / "packs"
    no_packs.mkdir()
    registry = load_registry(path, no_packs)
    # The registry file lists every pack's portal at its pack tier (Seattle and Chicago are
    # curated); their packs are absent here, so exclude them.
    pack_ids = {load_portal(d).identity.id for d in _packs()}
    flagged = _registry_only_violations(registry, pack_ids)
    assert flagged == [f"{entry['identity']['id']}: profiled"]
