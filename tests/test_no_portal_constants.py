"""The engine (`core/`) and the MCP layer (`mcp/`) hold no Seattle literals.

Portal facts and Seattle text live only in the pack, `portals/seattle/`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCANNED = [ROOT / "src/opendata_atlas/core", ROOT / "src/opendata_atlas/mcp"]
#: `seattle-open-data` is the upstream project's name, not Seattle text.
FORBIDDEN = re.compile(
    r"\bseattle\b(?!-open-data)|seattle\.gov|cos-data|America/Los_Angeles"
    r"|kzjm-xkqj|33kz-ixgy|tazs-3rd5",
    re.IGNORECASE,
)

# Files that may still hold forbidden literals, and why. Each must keep matching:
# remove the entry when the reason goes away.
ALLOWED: dict[str, str] = {}


def _hits(path: Path) -> list[int]:
    return [n for n, line in enumerate(path.read_text().splitlines(), 1) if FORBIDDEN.search(line)]


def _scanned() -> list[Path]:
    return sorted(p for root in SCANNED for p in root.rglob("*.py"))


def test_engine_and_mcp_layer_have_no_portal_literals():
    hits = [
        f"{p.relative_to(ROOT)}:{n}" for p in _scanned() if p.name not in ALLOWED for n in _hits(p)
    ]
    assert hits == []


def test_guard_scans_both_layers():
    names = {p.relative_to(ROOT).as_posix() for p in _scanned()}
    assert "src/opendata_atlas/core/reference.py" in names
    assert "src/opendata_atlas/mcp/tools.py" in names


@pytest.mark.parametrize(
    "line",
    [
        "Search Seattle's catalog.",
        "SEATTLE",
        "see data.Seattle.gov",
        'tz = "america/los_angeles"',
        "dataset KZJM-XKQJ",
    ],
)
def test_guard_catches_any_case(line):
    assert FORBIDDEN.search(line)


def test_guard_allows_the_upstream_project_name():
    assert not FORBIDDEN.search("as in `seattle-open-data` (`core/describe.py:264`)")


def test_allowlist_entries_still_needed():
    for name, reason in ALLOWED.items():
        matches = [p for root in SCANNED for p in root.rglob(name)]
        assert matches, f"allowlisted file {name} no longer exists; drop it from ALLOWED"
        assert any(_hits(p) for p in matches), (
            f"{name} has no forbidden literals; drop it from ALLOWED ({reason})"
        )
