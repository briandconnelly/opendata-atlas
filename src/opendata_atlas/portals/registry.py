"""The portal registry: every portal the server can serve, and the one context factory."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from typing import TYPE_CHECKING

from opendata_atlas.portals.loader import PORTALS_DIR, PackError, load_portal

# _Strict is shared within the portals package.
from opendata_atlas.portals.model import Pack, PortalContext, PortalIdentity, _Strict

REGISTRY_PATH = PORTALS_DIR / "registry.json"

if TYPE_CHECKING:
    from pathlib import Path

_TIER_ORDER = {"curated": 0, "profiled": 1, "generic": 2}


class RegistryEntry(_Strict):
    identity: PortalIdentity
    dataset_count: int | None = None
    catalog_size: int | None = None


@dataclass(frozen=True)
class Registry:
    version: str
    entries: dict[str, RegistryEntry]

    def by_alias(self, value: str) -> RegistryEntry | None:
        """Match a canonical id or an alias, case-insensitively."""
        needle = value.casefold()
        for entry in self.entries.values():
            if entry.identity.id.casefold() == needle:
                return entry
        for entry in self.entries.values():
            if any(a.casefold() == needle for a in entry.identity.aliases):
                return entry
        return None

    @property
    def ordered(self) -> list[RegistryEntry]:
        return sorted(
            self.entries.values(), key=lambda e: (_TIER_ORDER[e.identity.tier], e.identity.id)
        )


def context_for(identity: PortalIdentity, pack_dir: Path | None) -> PortalContext:
    """The only constructor of contexts outside tests."""
    if pack_dir is not None:
        ctx = load_portal(pack_dir)
        if ctx.identity.id != identity.id:
            raise PackError(
                f"{pack_dir}: pack identity {ctx.identity.id!r} does not match {identity.id!r}"
            )
        return ctx
    return PortalContext(identity=identity, pack=Pack(claims=[]))


def _read(path: Path, packs_dir: Path) -> Registry:
    try:
        raw = json.loads(path.read_text())
        parsed = [RegistryEntry.model_validate(x) for x in raw["entries"]]
        version = str(raw["version"])
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise PackError(f"{path}: <registry>: {e}") from e
    entries: dict[str, RegistryEntry] = {}
    for e in parsed:
        if e.identity.id in entries:
            raise PackError(f"{path}: duplicate portal id {e.identity.id!r}")
        entries[e.identity.id] = e
    for pack_toml in sorted(packs_dir.glob("*/portal.toml")):
        identity = load_portal(pack_toml.parent).identity
        old = entries.get(identity.id)
        entries[identity.id] = RegistryEntry(
            identity=identity,
            dataset_count=old.dataset_count if old is not None else None,
            catalog_size=old.catalog_size if old is not None else None,
        )
    _check_unique(entries)
    return Registry(version=version, entries=entries)


def _check_unique(entries: dict[str, RegistryEntry]) -> None:
    """Ids and aliases share one case-insensitive namespace."""
    owner: dict[str, str] = {}
    for entry in entries.values():
        ident = entry.identity
        for name in [ident.id, *ident.aliases]:
            key = name.casefold()
            if key in owner and owner[key] != ident.id:
                raise PackError(
                    f"registry: {name!r} of portal {ident.id!r} collides with portal {owner[key]!r}"
                )
            owner[key] = ident.id


@cache
def _default() -> Registry:
    return _read(REGISTRY_PATH, PORTALS_DIR)


def load_registry(path: Path | None = None, packs_dir: Path | None = None) -> Registry:
    """Registry JSON plus pack identities. Only the default-path call is cached."""
    if path is None and packs_dir is None:
        return _default()
    return _read(
        REGISTRY_PATH if path is None else path,
        PORTALS_DIR if packs_dir is None else packs_dir,
    )
