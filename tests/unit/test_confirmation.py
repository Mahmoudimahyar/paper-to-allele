"""Two engines must agree before a value is auto-accepted.

Written before the implementation. ADR 0006 requires unanimity across
architecturally INDEPENDENT recognizers, and measured this: a 2-of-3 majority
across neural engines was *worse* than unanimity (3.50% vs 4.50% false
acceptance), because engines sharing an architecture share their mistakes.

Tesseract is the independent one available here: a different era, a different
approach, and no shared training data with the neural recognizer. Measured on
300 resolved DRB1/DQB1 cells it agrees with the repaired reading on 86.3%;
11.3% are its abstentions on narrow crops and 1.7% are contradictions, every one
of which was Tesseract reading a family that does not exist for the locus.

That last fact drives the design: **the vocabulary gate applies to both
engines**, so a confirmer that produces an impossible family is not treated as
evidence against a possible one. It withholds confirmation rather than voting.
"""

from __future__ import annotations

import pytest

from kidneymatch.hla.vocabulary import load_vocabulary
from kidneymatch.ocr.confirm import Confirmation, confirm_value


@pytest.fixture(scope="module")
def vocabulary():
    return load_vocabulary()


def test_two_engines_reading_the_same_value_confirm_it(vocabulary) -> None:
    result = confirm_value("DRB1", ("11", "15"), "11 15", vocabulary)
    assert result is Confirmation.CONFIRMED


def test_a_different_reading_is_never_auto_accepted(vocabulary) -> None:
    """The two engines disagree about what the page says, so nobody knows."""
    result = confirm_value("DRB1", ("11", "15"), "11 13", vocabulary)
    assert result is Confirmation.CONTRADICTED


def test_order_is_not_part_of_the_reading(vocabulary) -> None:
    assert confirm_value("DRB1", ("11", "15"), "15 11", vocabulary) is Confirmation.CONFIRMED


def test_a_confirmer_that_read_nothing_withholds_rather_than_contradicts(vocabulary) -> None:
    """11.3% of cells are abstentions on narrow crops.

    An engine that could not read the crop is not evidence that the other engine
    is wrong; it is the absence of a second opinion.
    """
    assert confirm_value("DRB1", ("11",), "", vocabulary) is Confirmation.UNCONFIRMED


def test_a_confirmer_reading_an_impossible_family_withholds_rather_than_contradicts(
    vocabulary,
) -> None:
    """Every measured contradiction was Tesseract reading a family that does not
    exist for that locus. Counting those as evidence against a valid reading
    would make the confirmer worse than no confirmer."""
    assert confirm_value("DRB1", ("11",), "83", vocabulary) is Confirmation.UNCONFIRMED


def test_a_contradiction_between_two_possible_families_stands(vocabulary) -> None:
    """`DRB1*11` and `DRB1*13` both exist, so this is a real disagreement about
    the page and a human has to look."""
    assert confirm_value("DRB1", ("11",), "13", vocabulary) is Confirmation.CONTRADICTED


def test_a_partial_agreement_is_not_agreement(vocabulary) -> None:
    """One allele of a heterozygous pair confirms nothing about the pair."""
    assert confirm_value("DRB1", ("11", "15"), "11", vocabulary) is Confirmation.CONTRADICTED


def test_the_locus_prefix_is_stripped_before_comparing(vocabulary) -> None:
    """The confirmer reads characters; the locus came from geometry."""
    assert confirm_value("DRB1", ("11",), "DRB1*11", vocabulary) is Confirmation.CONFIRMED


def test_noise_that_parses_as_nothing_withholds(vocabulary) -> None:
    for reading in ("|||", "....", "Name"):
        assert confirm_value("DRB1", ("11",), reading, vocabulary) is Confirmation.UNCONFIRMED


def test_an_unvalidatable_locus_cannot_be_confirmed(vocabulary) -> None:
    """If the vocabulary cannot judge the confirmer's reading, agreement between
    two engines is agreement about characters and nothing more."""
    assert confirm_value("DRB9", ("11",), "11", vocabulary) is Confirmation.UNCONFIRMED


# --- what the confirmer is actually confirming ---------------------------


def test_a_damaged_locus_prefix_does_not_block_confirmation(vocabulary) -> None:
    """The confirmer confirms DIGITS. The locus came from geometry, and the
    primary pipeline already refused any value naming a different one.

    Measured, requiring the confirmer's prefix to parse threw away most of its
    opinions: 130 of 400 cells were withheld because Tesseract had rendered
    `DRB1*11` as `RB1*11` or `0R81*11`, where the digits were perfectly clear.
    """
    for reading in ("RB1*11", "0R81*11", "DRB!*11", "0RB1*11"):
        assert confirm_value("DRB1", ("DRB1*11",), reading, vocabulary) is Confirmation.CONFIRMED


def test_a_readable_prefix_naming_another_locus_still_contradicts(vocabulary) -> None:
    """A prefix the confirmer read clearly, and that names a different gene, is
    a real disagreement about the page rather than noise to be stripped."""
    result = confirm_value("DRB1", ("DRB1*11",), "DQB1*11", vocabulary)
    assert result is Confirmation.CONTRADICTED


def test_letter_noise_with_no_digits_withholds(vocabulary) -> None:
    """45 of 400 crops read as nothing and 130 as letters alone; neither is an
    opinion about the value."""
    for reading in ("aa", "DR", "B"):
        assert confirm_value("DRB1", ("DRB1*11",), reading, vocabulary) is Confirmation.UNCONFIRMED
