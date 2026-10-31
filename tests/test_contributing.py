"""`CONTRIBUTING-portals.md` is served as topic `contributing`, names every step, and fits."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from opendata_atlas.core import reference_service
from opendata_atlas.core.budget import RESULT_LIMIT, payload_size
from opendata_atlas.core.reference import CONTRIBUTING

ROOT = Path(__file__).resolve().parent.parent
ROOT_COPY = ROOT / "CONTRIBUTING-portals.md"
SERVED = "src/opendata_atlas/assets/contributing.md"


def _served_bytes() -> bytes:
    return resources.files("opendata_atlas.assets").joinpath("contributing.md").read_bytes()


def test_served_copy_matches_root():
    assert _served_bytes() == ROOT_COPY.read_bytes(), (
        f"{SERVED} differs from CONTRIBUTING-portals.md: edit the root file, then copy it "
        f"(cp CONTRIBUTING-portals.md {SERVED})"
    )
    assert _served_bytes().decode("utf-8") == CONTRIBUTING


def test_contributing_names_every_step():
    for text in (
        # find or register the portal
        "atlas_find_portals",
        "registry_overrides.toml",
        # profile, and review the values the profiler lists (ruling 53)
        "uv run atlas-profile <host>",
        "review_values",
        # interpretations, evidence, guides
        "reviewed_by",
        "reviewed_at",
        "`document`",
        "guides.py",
        # eval tasks and their four covers
        "evals/portals/<pack>.json",
        "`in_area`",
        "`relative_date`",
        "`misleading_field`",
        "`not_published`",
        # checks
        "uv run pytest --run-integration -m integration tests/test_drift.py -k <portal id> "
        "--ignore=tests/test_curation_skill.py",
        "uv run python evals/run.py --portal <pack> <out>",
        "uv run python evals/run.py --help",
        "tests/test_tiers.py",
        # the promotion rule (ruling 58) and the precedence of the path rule (ruling 59)
        "every task grades PASS in at least 2 runs and FAIL in at most 1",
        "This rule wins over every check below",
        # the agent skill that follows this path
        "`skills/curate-portal/SKILL.md`",
        # an agent never pushes nor promotes its own pack (rulings 63, 64); eval-task rules
        "it never pushes",
        "proposes `curated`",
        "must not name the column under test",
        # the path rule
        "`src/opendata_atlas/portals/<pack>/`",
        "`evals/portals/<pack>.json`",
        "`src/opendata_atlas/portals/registry_overrides.toml`",
        "`src/opendata_atlas/portals/validation.json`",
    ):
        assert text in CONTRIBUTING, text
    assert "is not published in this release" not in CONTRIBUTING


def test_contributing_sections_cover_the_document_and_fit():
    """#62: every `## ` section is one item, in order, and each fits the result budget."""
    index = reference_service.read(None, "contributing", None)
    assert index.entries is not None
    bodies = [
        reference_service.read(None, "contributing", e.item_id).body or "" for e in index.entries
    ]
    preamble = CONTRIBUTING.split("\n## ", 1)[0].rstrip("\n")
    assert "\n\n".join([preamble, *bodies]) + "\n" == CONTRIBUTING
    for entry, body in zip(index.entries, bodies, strict=True):
        result = reference_service.read(None, "contributing", entry.item_id)
        size = payload_size(result)
        assert size >= len(body.encode()), "the measure counts the body"
        assert size <= RESULT_LIMIT, f"contributing/{entry.item_id} is {size} bytes"


def test_named_skill_exists():
    skill = (ROOT / "skills" / "curate-portal" / "SKILL.md").read_text(encoding="utf-8")
    assert skill.startswith("---\nname: curate-portal\n")
    assert '"curate <portal>"' in skill.split("\n---\n", 1)[0]
