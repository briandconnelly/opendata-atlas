"""Curated dataset guide types (docs/design.md: Knowledge packs). Each portal pack ships its own
`GUIDES` in `guides.py`; the engine reads them from `PortalContext.guides`."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from opendata_atlas.portals.freshness import STALE_AFTER_DAYS

if TYPE_CHECKING:
    from datetime import date


@dataclass(frozen=True)
class Example:
    question: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Guide:
    guide_id: str
    dataset_id: str
    title: str
    description: str
    body: str
    examples: tuple[Example, ...]
    #: Binding rules for this dataset, rendered ahead of the facts in `body`.
    rules: tuple[str, ...] = ()
    #: When the figures in `body` were probed; every shipped guide sets it (#21).
    observed_at: date | None = None

    def render(self, today: date | None = None) -> str:
        examples = "\n".join(
            f"- {e.question}\n  ```json\n  {json.dumps(e.arguments)}\n  ```" for e in self.examples
        )
        rules = "".join(f"- {rule}\n" for rule in self.rules)
        rules = f"## Rules\n{rules}\n" if rules else ""
        return (
            f"# {self.title} (`{self.dataset_id}`)\n\n{self._as_of(today)}{rules}"
            f"{self.body.strip()}\n\n## Example queries\n\n{examples}\n"
        )

    def _as_of(self, today: date | None) -> str:
        """When the figures were probed; past `STALE_AFTER_DAYS`, a prompt to re-check them."""
        if self.observed_at is None:
            return ""
        line = f"Figures observed {self.observed_at.isoformat()}"
        if today is not None and (today - self.observed_at).days > STALE_AFTER_DAYS:
            return (
                f"{line}, over {STALE_AFTER_DAYS} days ago: re-check counts and date ranges "
                "with a query before quoting them.\n\n"
            )
        return f"{line}; counts and recent dates change with the data.\n\n"
