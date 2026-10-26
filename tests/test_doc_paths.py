"""Repository paths the agent-facing docs name exist, so a rename cannot leave one stale."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = [
    "AGENTS.md",
    "CONTRIBUTING.md",
    "CONTRIBUTING-portals.md",
    "skills/curate-portal/SKILL.md",
    "docs/releasing.md",
    "docs/design.md",
    "docs/knowledge-tooling.md",
    "docs/upstream-facts.md",
]
#: A backticked path from the repository root; placeholders (`<pack>`) and globs are skipped.
_PATH = re.compile(r"`((?:src|tests|evals|scripts|skills|docs|plugins)/[^`<>*\s]+)`")


#: Paths a doc names as an illustration of a file a run would create.
ILLUSTRATIVE = {"evals/portals/data.honolulu.gov.json"}


def named_paths(text: str) -> set[str]:
    return {m.split("::")[0].rstrip("/") for m in _PATH.findall(text)} - ILLUSTRATIVE


@pytest.mark.parametrize("doc", DOCS)
def test_named_paths_exist(doc: str):
    text = (ROOT / doc).read_text(encoding="utf-8")
    missing = sorted(p for p in named_paths(text) if not (ROOT / p).exists())
    assert missing == [], f"{doc} names paths that do not exist: {missing}"


def test_a_stale_path_is_caught():
    """Known positive: the step 8 path #31's rename left behind (Copilot on #46)."""
    stale = "`src/opendata_atlas/portals/seattle/guides.py` is the model."
    assert named_paths(stale) == {"src/opendata_atlas/portals/seattle/guides.py"}
    assert not (ROOT / "src/opendata_atlas/portals/seattle/guides.py").exists()
