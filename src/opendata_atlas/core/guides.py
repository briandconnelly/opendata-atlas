"""Curated dataset guide types (docs/design.md: Knowledge packs). Each portal pack ships its own
`GUIDES` in `guides.py`; the engine reads them from `PortalContext.guides`."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


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

    def render(self) -> str:
        examples = "\n".join(
            f"- {e.question}\n  ```json\n  {json.dumps(e.arguments)}\n  ```" for e in self.examples
        )
        rules = "".join(f"- {rule}\n" for rule in self.rules)
        rules = f"## Rules\n{rules}\n" if rules else ""
        return (
            f"# {self.title} (`{self.dataset_id}`)\n\n{rules}{self.body.strip()}\n\n"
            f"## Example queries\n\n{examples}\n"
        )
