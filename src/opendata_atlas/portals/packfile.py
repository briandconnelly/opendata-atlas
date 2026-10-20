"""What the pack loader and the validation-state reader share: the portals directory, the
pack error, and model validation that names the file and field.

Its own module so `loader` can read validation state without an import cycle.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

PORTALS_DIR = Path(__file__).parent


class PackError(Exception):
    """A pack file is malformed. Read by operators, not agents."""


def validate_file[M: BaseModel](model: type[M], data: Any, path: Path) -> M:
    """`model.model_validate(data)`, with each error as `<path>: <field>: <message>`."""
    try:
        return model.model_validate(data)
    except ValidationError as e:
        parts = [
            f"{path}: {'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['msg']}"
            for err in e.errors()
        ]
        raise PackError("; ".join(parts)) from e
