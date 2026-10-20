from __future__ import annotations

import json
import tomllib
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from fastmcp import Client

from opendata_atlas.mcp.server import build_server
from opendata_atlas.portals.drift import ClaimResult, asserted_claims, merge_results, report_json
from opendata_atlas.portals.loader import SEATTLE, load_portal
from opendata_atlas.portals.model import (
    Claim,
    Interpretation,
    Jurisdiction,
    ManualObservation,
    PortalContext,
    Scope,
)
from opendata_atlas.portals.validation import VALIDATION_PATH, load_validation, write_validation

if TYPE_CHECKING:
    from collections.abc import Mapping

PORTALS_DIR = SEATTLE.parent
#: The Seattle pack as a context, for tests that call the engine directly.
SEATTLE_CONTEXT = load_portal(SEATTLE)
SEATTLE_IDENTITY_DICT: dict[str, Any] = tomllib.loads((SEATTLE / "portal.toml").read_text())


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-integration", action="store_true", help="run live tests against registered portals"
    )
    parser.addoption(
        "--drift-report",
        metavar="PATH",
        default=None,
        help="also write the drift run's report (claims, assertions, requests) to PATH",
    )


_DRIFT_RESULTS = pytest.StashKey[list[ClaimResult]]()


@pytest.fixture(scope="session")
def drift_results(pytestconfig: pytest.Config) -> list[ClaimResult]:
    """The drift run's results; `pytest_sessionfinish` writes them to validation.json."""
    return pytestconfig.stash.setdefault(_DRIFT_RESULTS, [])


def write_drift_report(results: list[ClaimResult], path: Path) -> None:
    """Write the drift report. It needs neither the old validation file nor the packs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report_json(results), indent=1) + "\n")


def write_drift_outputs(
    results: list[ClaimResult],
    validation_path: Path,
    *,
    live: Mapping[str, set[str]],
    today: date,
) -> None:
    """Merge `results` into the validation file at `validation_path`."""
    merged = merge_results(load_validation(validation_path), results, today, live)
    write_validation(merged, validation_path)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    results = session.config.stash.get(_DRIFT_RESULTS, [])
    if not results:
        return
    # The report first: a malformed validation.json or a pack that fails to load raises below
    # (naming the file), and must not take the session's results with it.
    report = session.config.getoption("--drift-report")
    if report:
        write_drift_report(results, Path(report))
    live: dict[str, set[str]] = {}
    for portal, claim in asserted_claims():
        live.setdefault(portal.id, set()).add(claim.id)
    write_drift_outputs(results, VALIDATION_PATH, live=live, today=datetime.now(UTC).date())


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-integration"):
        return
    skip = pytest.mark.skip(reason="needs --run-integration")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


class _CheckedClient(Client):
    """Asserts the repair rules on every repair, suggestion and hint a tool call emits: each
    validates against its tool's input schema (final review M-5) and meets the scope rule."""

    _schemas: dict[str, dict[str, Any]] | None = None

    async def call_tool_mcp(self, name: str, arguments: dict[str, Any], *args: Any, **kw: Any):
        from tests.repair_rules import assert_repair_callable

        result = await super().call_tool_mcp(name, arguments, *args, **kw)
        content = wire(result).get("structuredContent") or {}
        repairs = _repairs(content)
        if repairs:
            if self._schemas is None:
                listing = wire(await self.list_tools_mcp())
                self._schemas = {t["name"]: t["inputSchema"] for t in listing["tools"]}
            for repair in repairs:
                assert_repair_callable(repair, self._schemas)
        _check_repair_scope(name, arguments or {}, content)
        return result


def _repairs(content: dict[str, Any]) -> list[dict[str, Any]]:
    """The repair, suggestion and hints in a tool result's `structuredContent`."""
    repairs = [content[k] for k in ("repair", "suggestion") if isinstance(content.get(k), dict)]
    return repairs + [h for h in content.get("hints") or [] if isinstance(h, dict)]


def _check_repair_scope(tool: str, arguments: dict[str, Any], content: dict[str, Any]) -> None:
    from opendata_atlas.core.errors import AtlasError
    from opendata_atlas.portals.resolve import resolve_portal
    from tests.repair_rules import assert_repair_scope

    repairs = _repairs(content)
    if not repairs:
        return
    portal = arguments.get("portal")
    try:
        portal_id = resolve_portal(portal).id if isinstance(portal, str) else None
    except AtlasError:
        portal_id = None
    for repair in repairs:
        continued = repair.get("arguments", {})
        if repair.get("tool") == "atlas_get_reference" and "cursor" in continued:
            _check_cursor_continuation(arguments, continued)
            continue
        assert_repair_scope(repair, portal_id or "")


def _check_cursor_continuation(arguments: dict[str, Any], continued: dict[str, Any]) -> None:
    """A reference cursor repair continues the cursor's own walk (rulings 50, 51): the same
    cursor, its decoded topic and, for guides, its decoded portal; nothing else is exempt."""
    from opendata_atlas.core import cursor as cursors
    from opendata_atlas.core.errors import Repair

    assert continued["cursor"] == arguments.get("cursor"), continued
    restart = Repair(next_step="list_items", tool="atlas_get_reference", arguments={})
    state = cursors.decode(continued["cursor"], "reference", portal_id="*", restart=restart)
    assert continued.get("topic") == state["t"], continued
    if state["t"] == "guides":
        assert continued.get("portal") == state["p"], continued
    else:
        assert "portal" not in continued, continued


@pytest.fixture
async def client():
    async with _CheckedClient(build_server()) as c:
        yield c


def wire(model: Any) -> dict[str, Any]:
    """The JSON a client receives, not the SDK object."""
    return model.model_dump(mode="json", by_alias=True, exclude_none=True)


def compact_json(data: Any) -> str:
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


#: The JSON-RPC response frame around a tool result, with the widest id a client is likely to send.
JSONRPC_FRAME = '{"jsonrpc":"2.0","id":2147483647,"result":}'


def framed_size(result: dict[str, Any]) -> int:
    """Bytes the client receives for `result` (as `wire` returns it), JSON-RPC frame included."""
    return len(json.dumps(result, separators=(",", ":")).encode()) + len(JSONRPC_FRAME)


@pytest.fixture
async def tools_list(client) -> dict[str, Any]:
    return wire(await client.list_tools_mcp())


@pytest.fixture
async def input_schemas(tools_list) -> dict[str, dict[str, Any]]:
    return {t["name"]: t["inputSchema"] for t in tools_list["tools"]}


class _NoNetwork:
    async def handle_async_request(self, request):
        raise AssertionError(f"unit test tried to reach the network: {request.url}")


@pytest.fixture(autouse=True)
def no_network():
    from opendata_atlas.core import cache
    from opendata_atlas.core.http import SodaClient, set_client

    cache.clear()
    set_client(SodaClient(transport=_NoNetwork()))  # ty: ignore[invalid-argument-type]
    yield
    set_client(None)


@pytest.fixture
def soda(request, no_network):
    """Record or replay the HTTP fixture named by the test's `soda_fixture` marker."""
    from opendata_atlas.core.http import SodaClient, set_client
    from tests.http_fixtures import RECORDING, Recorder, Replay

    marker = request.node.get_closest_marker("soda_fixture")
    assert marker is not None, "use @pytest.mark.soda_fixture(name)"
    name, overrides = marker.args[0], marker.kwargs.get("overrides")
    transport = Recorder(name) if RECORDING and not overrides else Replay(name, overrides)
    set_client(SodaClient(transport=transport))
    yield transport
    set_client(None)
    if isinstance(transport, Recorder):
        transport.save()


def seattle_only_packs(tmp_path: Path) -> Path:
    """A packs directory holding a copy of Seattle's pack alone, for tests that list packs and
    must not change when a contributor adds another pack to the shipped directory."""
    import shutil

    packs = tmp_path / "seattle-only-packs"
    shutil.copytree(SEATTLE, packs / SEATTLE.name, ignore=shutil.ignore_patterns("__pycache__"))
    return packs


def with_identity(ctx: PortalContext, **updates: Any) -> PortalContext:
    """A copy of `ctx` whose identity has `updates` applied (a jurisdiction dict is validated)."""
    if isinstance(updates.get("jurisdiction"), dict):
        updates["jurisdiction"] = Jurisdiction.model_validate(updates["jurisdiction"])
    return replace(ctx, identity=ctx.identity.model_copy(update=updates))


def with_extra_claim(
    ctx: PortalContext, *, dataset: str, column: str, reliability: str
) -> PortalContext:
    """A copy of `ctx` whose pack also holds a reviewed neighborhood place_field claim."""
    claim = Claim(
        id=f"test.{dataset}.{column}",
        kind="place_field",
        scope=Scope(dataset=dataset, column=column),
        interpretation=Interpretation(reliability=reliability, kind="neighborhood"),  # ty: ignore[invalid-argument-type]
        reviewed_by="test",
        reviewed_at=date(2026, 10, 17),
        evidence=[
            ManualObservation(
                kind="manual_observation", note="test fixture", observed_at=date(2026, 10, 17)
            )
        ],
    )
    pack = ctx.pack.model_copy(update={"claims": [*ctx.pack.claims, claim]})
    return replace(ctx, pack=pack)


def with_unit(ctx: PortalContext, *, dataset: str, unit: str) -> PortalContext:
    """A copy of `ctx` whose pack also holds a reviewed unit_of_observation claim."""
    claim = Claim(
        id=f"test.{dataset}.unit",
        kind="unit_of_observation",
        scope=Scope(dataset=dataset),
        interpretation=Interpretation(unit=unit),
        reviewed_by="test",
        reviewed_at=date(2026, 10, 18),
        evidence=[
            ManualObservation(
                kind="manual_observation", note="test fixture", observed_at=date(2026, 10, 18)
            )
        ],
    )
    return replace(ctx, pack=ctx.pack.model_copy(update={"claims": [*ctx.pack.claims, claim]}))


@pytest.fixture(autouse=True)
def _pin_freshness_clock(monkeypatch: pytest.MonkeyPatch):
    """Runtime freshness reads this date: the shipped checks' date, so Seattle reads fresh."""
    from opendata_atlas.portals import freshness

    monkeypatch.setattr(freshness, "today", lambda: date(2026, 10, 18))


@pytest.fixture(autouse=True)
def _clear_registry_cache():
    from opendata_atlas.portals import registry, resolve, validation

    registry._default.cache_clear()
    validation._default.cache_clear()
    resolve._context.cache_clear()
    resolve._pack_dirs.cache_clear()
    resolve._parse_allowlist.cache_clear()
