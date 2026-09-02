"""Reading ABO and Rh off the form, and reconciling it with the caption.

Written before the implementation, from a measured design (session artefact
`design_abo.md`).

Two findings shape every rule here.

**An ABO-shaped box is not a blood group.** `A+` and `O-` appear all over these
pages — in serology tables, footnotes and burned-in advertisement text. The
value is only a blood group when it sits in a cell identified by a printed
field label. Shape alone may raise a review item and may never produce a value.

**On the dominant letterhead the printed blood group is patient-reported.** The
form itself prints, as boilerplate, "information regarding the blood group is
based on the attendee's own account, and the laboratory bears no responsibility
for its accuracy" — measured on 2,928 documents, 97.7% of which carry the Yekta
marker. So a printed ABO on that family is not a laboratory measurement, and
agreement with the caption is not independent corroboration: both claims can
descend from the same person's statement.
"""

from __future__ import annotations

import pytest
from kidneymatch.documents.abo import (
    AboSource,
    AboStatus,
    Rh,
    read_abo,
    reconcile_abo,
)

from kidneymatch.ocr.anchors import Box

GROUP_LABEL_FA = "گروه خونی :"  # "blood group:" — the printed field label
DISCLAIMER_FA = "اطلاعات مربوط به گروه خونی براساس شرح حال مراجعه کننده بوده"


def box(x0: float, text: str, y0: float = 0.30, w: float = 0.10, h: float = 0.02) -> Box:
    return Box(x0=x0, y0=y0, x1=x0 + w, y1=y0 + h, text=text)


# Persian reads right to left: the value sits to the LEFT of its label.
FA_LABEL = box(0.60, GROUP_LABEL_FA)
EN_LABEL = box(0.20, "Blood Group:")


# --- the cell must be identified by an anchor ----------------------------


def test_a_value_in_an_anchored_cell_is_read() -> None:
    reading = read_abo([FA_LABEL, box(0.48, "A+", w=0.05)], [])
    assert reading.status is AboStatus.RESOLVED
    assert reading.group == "A"
    assert reading.rh is Rh.POSITIVE


def test_an_ABO_shaped_box_with_no_anchor_is_never_a_blood_group() -> None:
    """These tokens appear in serology tables and in burned-in advertisements.

    Measured: 726 documents have an anchor whose cell is empty while an
    ABO-shaped box sits elsewhere on the page. Reading that box would be a
    guess about which field it belongs to.
    """
    reading = read_abo([box(0.10, "A+", w=0.05)], [])
    assert reading.status is AboStatus.UNKNOWN
    assert reading.group is None


def test_a_shaped_box_outside_the_cell_does_not_rescue_an_empty_cell() -> None:
    reading = read_abo([FA_LABEL, box(0.05, "A+", y0=0.80, w=0.05)], [])
    assert reading.status is AboStatus.REVIEW_REQUIRED
    assert reading.group is None


def test_a_value_to_the_RIGHT_of_a_persian_label_is_not_its_value() -> None:
    reading = read_abo([FA_LABEL, box(0.75, "A+", w=0.05)], [])
    assert reading.group is None


def test_an_english_label_takes_its_value_to_the_right() -> None:
    reading = read_abo([], [EN_LABEL, box(0.33, "B+", w=0.05)])
    assert reading.status is AboStatus.RESOLVED
    assert reading.group == "B"


def test_a_persian_anchor_may_address_a_latin_value_box() -> None:
    """Both passes store boxes in the same normalised frame.

    The blood group is written in Latin characters on a Persian form, so the
    label comes from one pass and the value from the other.
    """
    reading = read_abo([FA_LABEL], [box(0.48, "AB-", w=0.05)])
    assert reading.status is AboStatus.RESOLVED
    assert reading.group == "AB"
    assert reading.rh is Rh.NEGATIVE


def test_the_footnote_that_also_says_blood_group_is_not_an_anchor() -> None:
    """The disclaimer sentence contains the same words as the field label."""
    footnote = Box(x0=0.10, y0=0.90, x1=0.90, y1=0.92, text=DISCLAIMER_FA)
    reading = read_abo([footnote, box(0.05, "A+", y0=0.90, w=0.04)], [])
    assert reading.group is None


# --- the 0 -> O repair ---------------------------------------------------


def test_a_zero_is_read_as_O_inside_the_cell() -> None:
    """Measured: `O` is recognised as the digit `0` in 2,804 ABO boxes.

    That is why blood group O looked under-represented at 12% when the Iranian
    population rate is near a third.
    """
    reading = read_abo([FA_LABEL, box(0.48, "0+", w=0.05)], [])
    assert reading.group == "O"
    assert reading.repaired is True


def test_the_raw_token_survives_the_repair() -> None:
    reading = read_abo([FA_LABEL, box(0.48, "0+", w=0.05)], [])
    assert reading.raw_value == "0+"


@pytest.mark.parametrize("text", ["D+", "Q+", "8+", "o+", "6-"])
def test_lookalikes_that_are_not_ABO_letters_are_refused(text: str) -> None:
    """`D` is the Rh(D) antigen, not a blood group, and lower case is not this
    form's typography. 49 such boxes exist corpus-wide."""
    reading = read_abo([FA_LABEL, box(0.48, text, w=0.05)], [])
    assert reading.group is None


# --- Rh is never synthesised ---------------------------------------------


def test_a_letter_with_no_sign_leaves_Rh_unknown_and_needs_review() -> None:
    """487 documents. Rh must never default to positive, the population mode."""
    reading = read_abo([FA_LABEL, box(0.48, "A", w=0.03)], [])
    assert reading.status is AboStatus.REVIEW_REQUIRED
    assert reading.rh is Rh.UNKNOWN


def test_a_sign_with_no_letter_is_never_published() -> None:
    reading = read_abo([FA_LABEL, box(0.48, "+", w=0.02)], [])
    assert reading.status is AboStatus.REVIEW_REQUIRED
    assert reading.group is None


def test_a_letter_and_a_sign_in_separate_boxes_are_not_joined() -> None:
    """33 documents — too few to justify a join rule that could pair a letter
    with a sign belonging to a different field."""
    reading = read_abo([FA_LABEL, box(0.48, "A", w=0.03), box(0.44, "+", w=0.02)], [])
    assert reading.status is AboStatus.REVIEW_REQUIRED


def test_two_different_values_in_one_cell_require_review() -> None:
    reading = read_abo([FA_LABEL, box(0.48, "A+", w=0.05), box(0.40, "B+", w=0.05)], [])
    assert reading.status is AboStatus.REVIEW_REQUIRED
    assert reading.group is None


def test_two_cells_that_disagree_require_review() -> None:
    second = box(0.60, GROUP_LABEL_FA, y0=0.50)
    reading = read_abo(
        [FA_LABEL, box(0.48, "A+", w=0.05), second, box(0.48, "B+", y0=0.50, w=0.05)], []
    )
    assert reading.status is AboStatus.REVIEW_REQUIRED


# --- the printed disclaimer changes the evidential class -----------------


def test_the_printed_disclaimer_marks_the_value_patient_reported() -> None:
    """The dominant letterhead disclaims its own blood-group field.

    A value carrying that boilerplate can never satisfy a requirement for a
    laboratory-verified ABO, however clearly it was read.
    """
    disclaimer = Box(x0=0.10, y0=0.90, x1=0.90, y1=0.92, text=DISCLAIMER_FA)
    reading = read_abo([FA_LABEL, box(0.48, "A+", w=0.05), disclaimer], [])
    assert reading.status is AboStatus.RESOLVED
    assert reading.source is AboSource.PATIENT_REPORTED_ON_FORM


def test_without_the_disclaimer_the_value_is_laboratory_printed() -> None:
    reading = read_abo([FA_LABEL, box(0.48, "A+", w=0.05)], [])
    assert reading.source is AboSource.LABORATORY_PRINTED


# --- reconciliation with the caption -------------------------------------


def test_agreement_corroborates_but_does_not_verify() -> None:
    image = read_abo([FA_LABEL, box(0.48, "A+", w=0.05)], [])
    decision = reconcile_abo(image, caption_claims={("A", Rh.POSITIVE)})
    assert decision.group == "A"
    assert decision.agreed is True
    assert decision.is_verified is False


def test_agreement_is_not_corroboration_when_the_form_is_patient_reported() -> None:
    """Both claims may descend from the same person's statement."""
    disclaimer = Box(x0=0.10, y0=0.90, x1=0.90, y1=0.92, text=DISCLAIMER_FA)
    image = read_abo([FA_LABEL, box(0.48, "A+", w=0.05), disclaimer], [])
    decision = reconcile_abo(image, caption_claims={("A", Rh.POSITIVE)})
    assert decision.independently_corroborated is False


def test_a_conflict_publishes_no_value_and_questions_the_caption() -> None:
    """A caption stating a different blood group most plausibly describes a
    DIFFERENT person — a broker posting someone else's report.

    The flag therefore lands on the link between the message and the document,
    invalidating that caption as evidence for every field it carries, not just
    for ABO.
    """
    image = read_abo([FA_LABEL, box(0.48, "A+", w=0.05)], [])
    decision = reconcile_abo(image, caption_claims={("B", Rh.POSITIVE)})
    assert decision.group is None
    assert decision.status is AboStatus.CONFLICT
    assert decision.subject_identity_questioned is True


def test_an_ambiguous_caption_never_picks_one_claim() -> None:
    image = read_abo([FA_LABEL, box(0.48, "A+", w=0.05)], [])
    decision = reconcile_abo(image, caption_claims={("A", Rh.POSITIVE), ("B", Rh.NEGATIVE)})
    assert decision.group == "A"
    assert decision.agreed is False


def test_a_caption_only_claim_is_never_labelled_lab_derived() -> None:
    decision = reconcile_abo(read_abo([], []), caption_claims={("O", Rh.NEGATIVE)})
    assert decision.group == "O"
    assert decision.source is AboSource.CAPTION_CLAIM
    assert decision.is_verified is False


def test_no_evidence_at_all_is_unknown() -> None:
    decision = reconcile_abo(read_abo([], []), caption_claims=set())
    assert decision.status is AboStatus.UNKNOWN
    assert decision.group is None
