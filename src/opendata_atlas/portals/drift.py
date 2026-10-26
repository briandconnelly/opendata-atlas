"""The drift run: re-run every pack assertion live and merge the outcomes into validation.json.

docs/knowledge-tooling.md: Drift checks. `tests/test_drift.py` drives it; `tests/conftest.py`
writes the merged file at the end of the session.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

from opendata_atlas.core.errors import AtlasError
from opendata_atlas.portals.checkers import Outcome, run_check
from opendata_atlas.portals.loader import PORTALS_DIR, load_portal
from opendata_atlas.portals.model import SoqlProbe
from opendata_atlas.portals.validation import ClaimCheck, ValidationFile, assertion_digest

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path

    from opendata_atlas.core.http import SodaClient
    from opendata_atlas.portals.model import Claim, PortalContext


@dataclass
class AssertionResult:
    checker: str
    #: Index into the claim's probe evidence, as the assertion's `probe`.
    probe: int
    outcome: Outcome
    detail: str
    #: The SoQL text or the metadata path the probe sent.
    request: str


@dataclass
class ClaimResult:
    portal_id: str
    claim_id: str
    outcome: Outcome
    assertions: list[AssertionResult]
    #: `assertion_digest` of the claim as checked; the merge records it.
    digest: str | None = None


def asserted_claims(packs_dir: Path = PORTALS_DIR) -> list[tuple[PortalContext, Claim]]:
    """Every claim with at least one assertion, in every pack directory with a `portal.toml`."""
    out: list[tuple[PortalContext, Claim]] = []
    for directory in sorted(p for p in packs_dir.iterdir() if (p / "portal.toml").is_file()):
        portal = load_portal(directory)
        out.extend((portal, c) for c in portal.pack.claims if c.assertion)
    return out


async def check_claim(client: SodaClient, portal: PortalContext, claim: Claim) -> ClaimResult:
    """Run each probe the claim's assertions name, once and in order, then every assertion."""
    probes = claim.probes
    answers: dict[int, tuple[Any, str | None]] = {}
    for index in sorted({a.probe for a in claim.assertion}):
        probe = probes[index]
        try:
            if isinstance(probe, SoqlProbe):
                dataset = claim.scope.dataset or claim.scope.layer
                if dataset is None:
                    answers[index] = (None, "claim scope names no dataset or layer")
                    continue
                data = await client.soql(portal, dataset, {"$query": probe.query})
            else:
                url = f"https://{portal.identity.public_host}{probe.path}"
                data = await client.get_json(url, portal=portal)
        except AtlasError as e:
            answers[index] = (None, str(e.envelope.code))
        else:
            answers[index] = (data, None)

    results: list[AssertionResult] = []
    for a in claim.assertion:
        probe = probes[a.probe]
        request = probe.query if isinstance(probe, SoqlProbe) else probe.path
        data, error = answers[a.probe]
        if error is not None:
            outcome: Outcome = "inconclusive"
            detail = error
        else:
            checked = run_check(a.checker, a.typed_params, data)
            outcome, detail = checked.outcome, checked.detail
        results.append(AssertionResult(a.checker, a.probe, outcome, detail, request))
    outcome = _worst(r.outcome for r in results)
    return ClaimResult(portal.id, claim.id, outcome, results, assertion_digest(claim))


async def record_claim(
    client: SodaClient, portal: PortalContext, claim: Claim, results: list[ClaimResult]
) -> ClaimResult:
    """Run `check_claim` and append its result; an unexpected error is recorded, then re-raised.

    `check_claim` turns upstream failures into `inconclusive`. Anything else (a decoding error,
    a checker bug) would leave the claim unrecorded, and the merge would keep its old outcome as
    current. So the claim is recorded `inconclusive` first, with the exception type as detail.
    """
    try:
        result = await check_claim(client, portal, claim)
    except Exception as e:
        detail = f"{type(e).__name__}: {e}"
        failure = AssertionResult("check_claim", 0, "inconclusive", detail, "")
        digest = assertion_digest(claim)
        results.append(ClaimResult(portal.id, claim.id, "inconclusive", [failure], digest))
        raise
    results.append(result)
    return result


def _worst(outcomes: Iterable[Outcome]) -> Outcome:
    seen = set(outcomes)
    if "contradicted" in seen:
        return "contradicted"
    if "inconclusive" in seen or not seen:
        return "inconclusive"
    return "passed"


def merge_results(
    old: ValidationFile,
    results: Iterable[ClaimResult],
    today: date,
    live: Mapping[str, set[str]],
) -> ValidationFile:
    """Fold this run's results into the previous file.

    A result replaces its entry and moves the old outcome to `previous_outcome`. In a portal
    this run has results for, an entry it did not check is kept while its claim is still in a
    pack (`live`: portal id to asserted claim ids), and dropped once the claim is gone or
    renamed. A portal with no result in this run (a scoped run on another pack) keeps every
    entry unchanged, orphans included.
    """
    results = list(results)
    touched = {r.portal_id for r in results}
    merged: dict[str, dict[str, ClaimCheck]] = {}
    for portal_id, checks in old.portals.items():
        if portal_id not in touched:
            merged[portal_id] = dict(checks)
            continue
        kept = {cid: c for cid, c in checks.items() if cid in live.get(portal_id, set())}
        if kept:
            merged[portal_id] = kept
    for r in results:
        before = old.portals.get(r.portal_id, {}).get(r.claim_id)
        merged.setdefault(r.portal_id, {})[r.claim_id] = ClaimCheck(
            checked_at=today,
            outcome=r.outcome,
            previous_outcome=before.outcome if before else None,
            assertion_digest=r.digest,
        )
    return ValidationFile(portals=merged)


def report_json(results: list[ClaimResult]) -> dict[str, Any]:
    """The drift report: every claim's outcome with each assertion's request and detail."""
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "results": [
            {
                "portal": r.portal_id,
                "claim": r.claim_id,
                "outcome": r.outcome,
                "assertions": [asdict(a) for a in r.assertions],
            }
            for r in results
        ],
    }
