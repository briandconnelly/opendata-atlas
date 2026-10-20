"""The drift run: every pack assertion, live. Run with --run-integration.

Each result is stashed; `pytest_sessionfinish` (tests/conftest.py) merges them into
`src/opendata_atlas/portals/validation.json`, and writes `--drift-report PATH` when given.
"""

from __future__ import annotations

import pytest

from opendata_atlas.core.http import SodaClient
from opendata_atlas.portals.drift import asserted_claims, record_claim

pytestmark = pytest.mark.integration

ASSERTED = asserted_claims()


@pytest.mark.parametrize(("portal", "claim"), ASSERTED, ids=[f"{p.id}:{c.id}" for p, c in ASSERTED])
async def test_claim_still_holds(portal, claim, drift_results):
    client = SodaClient()
    try:
        result = await record_claim(client, portal, claim, drift_results)
    finally:
        await client.aclose()
    assert result.outcome == "passed", result.assertions
