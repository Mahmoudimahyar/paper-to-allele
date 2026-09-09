"""Where a blood group came from decides what matching may do with it.

`MATCH-ABO-001`, `MATCH-001`. Policy: `docs/clinical/MATCHING_POLICY_V2.md`
section 5; `docs/agent-memory/KNOWN_ISSUES.md` KI-014.

The runner reads Gold, and Gold records a `source` for every blood group. The
mapping from that column onto `AboProvenance` is the only thing standing between
"this pair is cleared on a laboratory measurement" and "this pair is cleared on
a sentence somebody typed into a chat". It had a bug worth a test of its own.

The bug was not a wrong letter. The runner ignored the column entirely and
stamped every Gold group `PATIENT_REPORTED_ON_FORM`, reasoning from KI-014 that
the dominant letterhead disclaims its own blood-group field. That reasoning is
correct and is already applied at extraction
(`src/kidneymatch/documents/abo.py`: a printed group on a page carrying the
disclaimer is written `PATIENT_REPORTED_ON_FORM`, and only a page WITHOUT it
yields `LABORATORY_PRINTED`). Applying it a second time in the runner discarded
the 2,676 profiles whose group may clear a pair, and produced the confident and
false report that no pair in the archive could reach `RANKED`.

A double-applied safety rule looks exactly like a safe system from the outside.
That is what makes it worth pinning: the failure was silent, conservative in
direction, and wrong.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from kidneymatch.matching.abo import GROUPS, AboGate, AboProvenance, abo_gate

ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.task("MATCH-001")


def _runner() -> object:
    """Import `scripts/rank_matches.py` without running it."""
    spec = importlib.util.spec_from_file_location(
        "rank_matches", ROOT / "scripts" / "rank_matches.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["rank_matches"] = module
    spec.loader.exec_module(module)
    return module


#: Every `source` Gold actually writes for an ABO fact, and what it means here.
#: Measured on the 2026-09-08 build: 5,498 caption claims, 2,676 laboratory
#: printed, 618 patient reported, and no profile carrying more than one.
GOLD_SOURCES = {
    "LABORATORY_PRINTED": AboProvenance.LABORATORY_MEASURED,
    "PATIENT_REPORTED_ON_FORM": AboProvenance.PATIENT_REPORTED_ON_FORM,
    "CAPTION_CLAIM": AboProvenance.CAPTION_CLAIM,
}


@pytest.mark.parametrize(("source", "expected"), sorted(GOLD_SOURCES.items()))
def test_each_gold_source_maps_to_the_provenance_it_means(
    source: str, expected: AboProvenance
) -> None:
    """The three sources Gold writes, each mapped rather than assumed."""
    assert _runner().abo_provenance(source) is expected  # type: ignore[attr-defined]


def test_a_laboratory_printed_group_is_not_downgraded_a_second_time() -> None:
    """The regression, stated as its own claim.

    KI-014 is applied at extraction. A runner that applies it again cannot
    distinguish a disclaiming form from a laboratory report, and silently
    removes every pair's ability to be cleared.
    """
    got = _runner().abo_provenance("LABORATORY_PRINTED")  # type: ignore[attr-defined]
    assert got is AboProvenance.LABORATORY_MEASURED
    assert got is not AboProvenance.PATIENT_REPORTED_ON_FORM


@pytest.mark.parametrize("source", [None, "", "   ", "NOT_A_SOURCE", "LABORATORY_MEASURED_LATER"])
def test_an_unrecognised_source_is_unknown_and_cannot_clear(source: str | None) -> None:
    """A source the map does not know must not become the permissive one.

    Gold gaining a fourth source is a schema change, and the safe reading of one
    is UNKNOWN: it can still exclude a pair, and it can never clear one.
    """
    got = _runner().abo_provenance(source)  # type: ignore[attr-defined]
    assert got is AboProvenance.UNKNOWN
    decision = abo_gate("O", "A", donor_provenance=got, recipient_provenance=got)
    assert decision.gate is not AboGate.COMPATIBLE


@pytest.mark.parametrize("source", ["laboratory_printed", "  Laboratory_Printed  "])
def test_the_source_is_read_case_and_space_insensitively(source: str) -> None:
    """A stored value that differs only in casing or padding is the same fact.
    Reading it as UNKNOWN would silently stop clearing pairs it should clear."""
    assert (
        _runner().abo_provenance(source)  # type: ignore[attr-defined]
        is AboProvenance.LABORATORY_MEASURED
    )


def test_only_the_laboratory_provenance_can_clear_a_compatible_pair() -> None:
    """The asymmetry this mapping exists to serve, asserted end to end.

    Compatible letters on both sides, varied only by where they came from. A
    caption claim and a form report may exclude, never clear.
    """
    cleared = []
    for provenance in AboProvenance:
        decision = abo_gate("O", "A", donor_provenance=provenance, recipient_provenance=provenance)
        if decision.gate is AboGate.COMPATIBLE:
            cleared.append(provenance)
    assert cleared == [AboProvenance.LABORATORY_MEASURED]


def test_an_incompatible_pair_is_excluded_whatever_the_provenance() -> None:
    """The other half of the asymmetry: weak evidence still stops a pair.
    A caption claim that says AB into O is enough to refuse."""
    for provenance in AboProvenance:
        if provenance is AboProvenance.UNKNOWN:
            continue
        decision = abo_gate("AB", "O", donor_provenance=provenance, recipient_provenance=provenance)
        assert decision.gate is AboGate.INCOMPATIBLE, (
            f"a {provenance} group failed to exclude an incompatible pair"
        )


def test_the_map_covers_every_group_letter_without_touching_them() -> None:
    """Provenance and letter are independent. A mapping that quietly filtered
    letters would be a second, hidden gate."""
    runner = _runner()
    for letter in sorted(GROUPS):
        assert (
            abo_gate(
                letter,
                letter,
                donor_provenance=runner.abo_provenance("LABORATORY_PRINTED"),  # type: ignore[attr-defined]
                recipient_provenance=runner.abo_provenance("LABORATORY_PRINTED"),  # type: ignore[attr-defined]
            ).gate
            is AboGate.COMPATIBLE
        )
