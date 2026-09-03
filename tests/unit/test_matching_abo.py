"""The ABO gate, and the asymmetry that governs it.

`MATCH-ABO-001`. Blood-group compatibility is universal biology, so this is the
one piece of matching that can be written while `HA-004` — which Iranian
histocompatibility practice applies — is still open.

The asymmetry: a wrong exclusion costs a missed match; a wrong clearance costs a
transfused incompatible kidney. So weak evidence may stop a pair and may never
clear one, and most of these tests are about that.
"""

from __future__ import annotations

import pytest

from kidneymatch.matching.abo import (
    AboGate,
    AboProvenance,
    abo_gate,
)

pytestmark = pytest.mark.task("MATCH-ABO-001")

MEASURED = AboProvenance.LABORATORY_MEASURED
REPORTED = AboProvenance.PATIENT_REPORTED_ON_FORM


def gate(donor, recipient, dp=MEASURED, rp=MEASURED):
    return abo_gate(donor, recipient, donor_provenance=dp, recipient_provenance=rp)


# --- the biology ----------------------------------------------------------


@pytest.mark.parametrize(
    ("donor", "recipient"),
    [
        ("O", "O"),
        ("O", "A"),
        ("O", "B"),
        ("O", "AB"),
        ("A", "A"),
        ("A", "AB"),
        ("B", "B"),
        ("B", "AB"),
        ("AB", "AB"),
    ],
)
def test_a_compatible_pair_measured_on_both_sides_clears(donor, recipient) -> None:
    assert gate(donor, recipient).gate is AboGate.COMPATIBLE


@pytest.mark.parametrize(
    ("donor", "recipient"),
    [("A", "O"), ("B", "O"), ("AB", "O"), ("A", "B"), ("B", "A"), ("AB", "A"), ("AB", "B")],
)
def test_an_incompatible_pair_is_stopped(donor, recipient) -> None:
    decision = gate(donor, recipient)
    assert decision.gate is AboGate.INCOMPATIBLE
    assert decision.blocks_pair is True


# --- the asymmetry --------------------------------------------------------


def test_a_patient_reported_group_may_exclude_a_pair(donor="A", recipient="O") -> None:
    """The dominant letterhead disclaims its own blood-group field on 2,928
    documents (KI-014). That is still enough to stop a pair: being wrong here
    costs a missed match."""
    decision = gate(donor, recipient, dp=REPORTED, rp=REPORTED)
    assert decision.gate is AboGate.INCOMPATIBLE


def test_a_patient_reported_group_may_never_clear_a_pair() -> None:
    """And this is why the disclaimer matters. Being wrong here puts an
    incompatible kidney into somebody."""
    decision = gate("O", "A", dp=REPORTED, rp=MEASURED)
    assert decision.gate is AboGate.UNKNOWN
    assert "laboratory measurement" in decision.reason
    assert decision.blocks_pair is False, "UNKNOWN sends the pair to a person, it does not stop it"


def test_one_unmeasured_side_is_enough_to_withhold_a_clearance() -> None:
    for donor_provenance, recipient_provenance in (
        (REPORTED, MEASURED),
        (MEASURED, REPORTED),
        (AboProvenance.CAPTION_CLAIM, MEASURED),
        (AboProvenance.UNKNOWN, MEASURED),
    ):
        assert gate("O", "A", dp=donor_provenance, rp=recipient_provenance).gate is AboGate.UNKNOWN


# --- missing data is UNKNOWN, never assumed -------------------------------


@pytest.mark.parametrize(("donor", "recipient"), [(None, "A"), ("O", None), (None, None)])
def test_a_missing_group_is_unknown_not_a_guess(donor, recipient) -> None:
    decision = gate(donor, recipient)
    assert decision.gate is AboGate.UNKNOWN
    assert decision.blocks_pair is False


@pytest.mark.parametrize(("donor", "recipient"), [("O+", "A"), ("", "A"), ("Z", "A"), ("O", "0")])
def test_something_that_is_not_a_blood_group_is_unknown(donor, recipient) -> None:
    """`O+` carries Rh, which is a different question; `0` is the digit the
    recognizer produces for the letter. Neither is an ABO group here."""
    assert gate(donor, recipient).gate is AboGate.UNKNOWN


def test_case_and_whitespace_do_not_change_a_verdict() -> None:
    assert gate(" o ", "ab").gate is AboGate.COMPATIBLE


# --- what the gate is for -------------------------------------------------


def test_every_decision_carries_its_reason() -> None:
    """A gate that stops a pair without saying why cannot be reviewed, and this
    one is allowed to stop pairs on patient-reported evidence."""
    for donor, recipient in (("A", "O"), ("O", "A"), (None, "A")):
        assert gate(donor, recipient).reason


def test_the_gate_reads_nothing_about_compensation() -> None:
    """`AGENTS.md`: the matching core may not import or query compensation.
    An ABO gate that could see an amount is a gate that could be bought."""
    import inspect

    from kidneymatch.matching import abo

    source = inspect.getsource(abo).lower()
    for forbidden in ("compensation", "amount", "price", "payment"):
        assert forbidden not in source
