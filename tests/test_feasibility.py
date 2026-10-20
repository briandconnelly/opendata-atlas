"""Pure-function tests for the dev-only milestone 0 feasibility probes."""

import importlib.util
import sys
from pathlib import Path

PROBES = Path(__file__).resolve().parent.parent / "scripts" / "feasibility"


def _load(name: str):
    sys.path.insert(0, str(PROBES))
    try:
        spec = importlib.util.spec_from_file_location(name, PROBES / f"{name}.py")
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(PROBES))


is_eligible = _load("enumerate_domains").is_eligible
identity_matches = _load("check_identity").identity_matches


def test_is_eligible_rejects_demo_staging_internal_priv_but_accepts_data_socrata_subdomains():
    assert not is_eligible("mesa-az.demo.socrata.com")
    assert not is_eligible("internal-sandiegocounty.data.socrata.com")
    assert not is_eligible("priv-data.ojp.usdoj.gov")
    assert is_eligible("albany.data.socrata.com")
    assert not is_eligible("internal.open.piercecountywa.gov")
    assert not is_eligible("lombardia-scgc.demo.eu.socrata.com")
    assert not is_eligible("lombardia-staging.azure-westeurope-prod.socrata.com")
    assert is_eligible("gnb.socrata.com")
    assert is_eligible("data.cityofchicago.org")


def test_identity_matches_requires_every_result_on_expected_domain():
    ok = [[{"metadata": {"domain": "data.sf.gov"}}] * 3] * 3
    mixed = [[{"metadata": {"domain": "data.sf.gov"}}, {"metadata": {"domain": "data.sfgov.org"}}]]
    assert identity_matches(ok, "data.sf.gov")
    assert not identity_matches(mixed, "data.sf.gov")
    assert not identity_matches([], "data.sf.gov")
    assert not identity_matches([[]], "data.sf.gov")
