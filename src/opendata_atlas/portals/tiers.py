"""The tier conditions decidable from a pack's contents (docs/design.md, Knowledge levels).

Identity verification, the live smoke test and passing evals are not decidable offline; the
promotion PR's CI runs them.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from opendata_atlas.portals.knowledge import pack_levels

if TYPE_CHECKING:
    from datetime import date
    from pathlib import Path

    from opendata_atlas.portals.model import PortalContext

#: The four kinds of eval task a curated portal's file must cover (design: Per-portal eval tasks).
COVERS = ("in_area", "relative_date", "misleading_field", "not_published")


def tier_violations(
    portal: PortalContext, pack_dir: Path, evals_dir: Path, *, today: date
) -> list[str]:
    """Each way `portal`'s declared tier fails its offline conditions; empty when it holds.

    `curated`: at least one dataset `reviewed` by `pack_levels` that has a guide, and
    `evals_dir / "<pack dir name>.json"` whose tasks' `covers` include all of `COVERS`.
    `profiled`: at least one claim. `generic` has no conditions.
    """
    tier = portal.identity.tier
    if tier == "profiled" and not portal.pack.claims:
        return ["profiled: the pack holds no claim; profile the portal or declare `generic`"]
    if tier != "curated":
        return []
    out: list[str] = []
    levels = pack_levels(portal, today=today)
    if not any(levels.get(g.dataset_id) == "reviewed" for g in portal.guides):
        out.append(
            "curated: no dataset is both `reviewed` (pack_levels) and has a guide in guides.py"
        )
    out.extend(_eval_violations(evals_dir / f"{pack_dir.name}.json"))
    return out


def _eval_violations(path: Path) -> list[str]:
    try:
        tasks = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return [f"curated: cannot read eval tasks {path.name}: {e}"]
    if not isinstance(tasks, list) or not all(_readable_task(t) for t in tasks):
        return [
            f"curated: cannot read eval tasks {path.name}: expected a list of tasks, "
            "each with an optional `covers` list of strings"
        ]
    covered = {c for task in tasks for c in task.get("covers", [])}
    missing = [c for c in COVERS if c not in covered]
    if missing:
        names = ", ".join(f"`{c}`" for c in missing)
        return [f"curated: no task in {path.name} covers {names}"]
    return []


def _readable_task(task: object) -> bool:
    """A task object whose `covers`, when present, is a list of strings."""
    if not isinstance(task, dict):
        return False
    covers = task.get("covers", [])
    return isinstance(covers, list) and all(isinstance(c, str) for c in covers)
