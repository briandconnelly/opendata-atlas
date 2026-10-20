"""Load a portal pack directory into a PortalContext."""

from __future__ import annotations

import importlib.util
import re
import sys
import tomllib
from typing import TYPE_CHECKING, Any

from opendata_atlas.core.guides import Guide
from opendata_atlas.portals.model import Claim, Pack, PortalContext, PortalIdentity
from opendata_atlas.portals.packfile import PORTALS_DIR, PackError, validate_file
from opendata_atlas.portals.validation import load_validation

if TYPE_CHECKING:
    from pathlib import Path

    from opendata_atlas.portals.validation import ValidationFile

__all__ = ["PORTALS_DIR", "SEATTLE", "PackError", "load_portal"]

SEATTLE = PORTALS_DIR / "seattle"


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise PackError(f"{path}: <toml>: {e}") from e


def _load_guides(path: Path, identity_id: str) -> tuple[Guide, ...]:
    # Portal ids hold dots; a dotted module name reads as a package path, so pickle and
    # import-by-name cannot find objects the pack defines.
    safe_id = re.sub(r"[^A-Za-z0-9_]", "_", identity_id)
    spec = importlib.util.spec_from_file_location(f"_pack_guides_{safe_id}_{abs(hash(path))}", path)
    if spec is None or spec.loader is None:
        raise PackError(f"{path}: <module>: cannot import")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(spec.name, None)
        raise PackError(f"{path}: guides: {exc}") from exc
    guides = getattr(module, "GUIDES", None)
    if not isinstance(guides, tuple) or not all(isinstance(g, Guide) for g in guides):
        raise PackError(f"{path}: GUIDES: must be a tuple of Guide")
    return guides


def load_portal(directory: Path, *, validation: ValidationFile | None = None) -> PortalContext:
    """The pack in `directory`, with its portal's entries from `validation`.

    `validation` None reads the shipped `validation.json` (`load_validation()`).
    """
    portal_path = directory / "portal.toml"
    identity = validate_file(PortalIdentity, _read_toml(portal_path), portal_path)

    claims: list[Claim] = []
    files = [directory / "regions.toml", *sorted((directory / "facts").glob("*.toml"))]
    for path in files:
        if not path.exists():
            continue
        data = _read_toml(path)
        extra = sorted(set(data) - {"claim"})
        if extra:
            raise PackError(f"{path}: {extra[0]}: unexpected key (pack files use [[claim]])")
        pack = validate_file(Pack, {"claims": data.get("claim", [])}, path)
        claims.extend(pack.claims)
    ids = [c.id for c in claims]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise PackError(f"{directory}: claims: duplicate claim ids {dupes}")

    guides_path = directory / "guides.py"
    guides = _load_guides(guides_path, identity.id) if guides_path.exists() else ()
    if validation is None:
        validation = load_validation()
    checks = validation.portals.get(identity.id, {})
    return PortalContext(
        identity=identity, pack=Pack(claims=claims), guides=guides, checks=dict(checks)
    )
