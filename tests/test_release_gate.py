"""The release gate: shipped validation state carries no contradicted or twice-unknown claim.

docs/design.md: Validation state and freshness (Release gate). Before tagging, run the drift
session and commit the regenerated `validation.json`.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from opendata_atlas.portals.drift import asserted_claims
from opendata_atlas.portals.validation import (
    ClaimCheck,
    ValidationFile,
    assertion_digest,
    gate_failures,
    load_validation,
)

if TYPE_CHECKING:
    from opendata_atlas.portals.checkers import Outcome

DAY = date(2026, 10, 18)
#: The assertion digest every `_file` entry records, and `_live` expects.
D = "0123456789ab"


def _file(**claims: tuple[Outcome, Outcome | None]) -> ValidationFile:
    return ValidationFile(
        portals={
            "p.example": {
                cid: ClaimCheck(
                    checked_at=DAY, outcome=o, previous_outcome=prev, assertion_digest=D
                )
                for cid, (o, prev) in claims.items()
            }
        }
    )


def _live(**portals: set[str]) -> dict[str, dict[str, str]]:
    """Asserted claim ids per portal (`p_example` names `p.example`), each with digest `D`."""
    return {p.replace("_", "."): dict.fromkeys(ids, D) for p, ids in portals.items()}


def _shipped_live() -> dict[str, dict[str, str]]:
    live: dict[str, dict[str, str]] = {}
    for portal, claim in asserted_claims():
        live.setdefault(portal.id, {})[claim.id] = assertion_digest(claim)
    return live


def test_shipped_validation_passes_the_gate():
    live = _shipped_live()
    assert live, "no asserted claims: the gate would pass on nothing"
    assert gate_failures(load_validation(), live) == []


def test_gate_catches_contradicted():
    failures = gate_failures(_file(a=("contradicted", "passed")), _live(p_example={"a"}))
    assert len(failures) == 1 and "p.example" in failures[0] and "a" in failures[0]
    assert "contradicted" in failures[0]


def test_gate_catches_inconclusive_twice():
    failures = gate_failures(_file(a=("inconclusive", "inconclusive")), _live(p_example={"a"}))
    assert len(failures) == 1 and "inconclusive" in failures[0]


def test_gate_allows_one_inconclusive():
    live = _live(p_example={"a", "b"})
    assert gate_failures(_file(a=("inconclusive", None), b=("inconclusive", "passed")), live) == []


def test_gate_catches_missing_entry():
    failures = gate_failures(
        _file(a=("passed", None)), _live(p_example={"a", "b"}, q_example={"c"})
    )
    assert len(failures) == 2
    assert any("p.example" in f and "b" in f and "no entry" in f for f in failures)
    assert any("q.example" in f and "c" in f and "no entry" in f for f in failures)


def test_gate_ignores_orphaned_entries():
    """Review Focus 3: an entry for a removed claim is pruned by the next run, not a failure."""
    file = _file(a=("passed", None), gone=("contradicted", "passed"))
    assert gate_failures(file, _live(p_example={"a"})) == []


def test_gate_catches_an_assertion_changed_since_its_check():
    """Final review M-3: a `passed` entry checked against other params no longer vouches."""
    failures = gate_failures(_file(a=("passed", None)), {"p.example": {"a": "fedcba987654"}})
    assert len(failures) == 1 and "p.example" in failures[0] and "a" in failures[0]
    assert "assertion changed" in failures[0]
    legacy = ValidationFile(
        portals={"p.example": {"a": ClaimCheck(checked_at=DAY, outcome="passed")}}
    )
    assert "assertion changed" in gate_failures(legacy, _live(p_example={"a"}))[0], (
        "an entry with no digest cannot vouch for the current assertion"
    )


def test_editing_a_shipped_assertion_fails_the_gate():
    """Known positive on the real packs: change one Seattle assertion's params, and only that
    claim fails, until a drift run checks it again."""
    portal, claim = next((p, c) for p, c in asserted_claims() if c.assertion[0].params)
    first = claim.assertion[0]
    key = next(iter(first.params))
    edited = claim.model_copy(
        update={"assertion": [first.model_copy(update={"params": {**first.params, key: "x"}})]}
    )
    assert assertion_digest(edited) != assertion_digest(claim)
    live = _shipped_live()
    live[portal.id][claim.id] = assertion_digest(edited)
    failures = gate_failures(load_validation(), live)
    assert failures == [f"{portal.id}: {claim.id}: assertion changed since its last check"]


def test_digest_reads_the_checked_request_not_the_prose():
    _, claim = asserted_claims()[0]
    probe = claim.probes[claim.assertion[0].probe]
    reworded = claim.model_copy(
        update={
            "evidence": [
                e.model_copy(update={"observation": "reworded"}) if e is probe else e
                for e in claim.evidence
            ]
        }
    )
    assert assertion_digest(reworded) == assertion_digest(claim)
    assert len(assertion_digest(claim)) == 12
