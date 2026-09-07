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
    AboRescue,
    AboSource,
    AboStatus,
    Rh,
    needs_corroboration,
    read_abo,
    reconcile_abo,
    rule_id_for,
)
from kidneymatch.ocr.anchors import Box
from kidneymatch.ocr.lattice import Lattice, Ruling

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


# --- fixes from the skeptical review -------------------------------------


def test_the_methods_footnote_word_groups_is_not_a_field_label() -> None:
    """The form prints "... alleles or groups of alleles ... PCR-SSP ...".

    `groups` there anchored a cell on 576 documents and resolved two of them.
    """
    prose = [
        box(0.05, "alleles", w=0.06),
        box(0.12, "or", w=0.02),
        box(0.15, "groups", w=0.05),
        box(0.21, "of", w=0.02),
        box(0.24, "alleles.", w=0.06),
        box(0.31, "A+", w=0.03),
    ]
    assert read_abo([], prose).group is None


def test_a_real_english_field_label_still_anchors() -> None:
    for label in ("Blood Group:", "Group:", "ABO", "Rh:"):
        reading = read_abo([], [box(0.20, label), box(0.33, "B+", w=0.05)])
        assert reading.group == "B", label


def test_a_bare_group_word_anchors_only_beside_the_word_blood() -> None:
    """`Group` with no colon is a field label when `Blood` precedes it, and
    prose otherwise."""
    assert (
        read_abo(
            [], [box(0.10, "Blood", w=0.05), box(0.16, "Group", w=0.05), box(0.23, "O+", w=0.04)]
        ).group
        == "O"
    )
    assert read_abo([], [box(0.16, "Group", w=0.05), box(0.23, "O+", w=0.04)]).group is None


def test_the_disclaimer_is_detected_across_a_wrapped_footnote() -> None:
    """The sentence is long and the recognizer splits it across boxes.

    Requiring one box to carry both the disclaimer word and the blood word
    missed at least 27.5% of the Yekta pages that show the disclaimer, so 120
    resolved readings were labelled as laboratory measurements.
    """
    first_half = Box(x0=0.10, y0=0.90, x1=0.48, y1=0.92, text="اطلاعات مربوط به گروه خونی")
    second_half = Box(x0=0.50, y0=0.90, x1=0.90, y1=0.92, text="براساس شرح حال مراجعه کننده بوده")
    reading = read_abo([FA_LABEL, box(0.48, "A+", w=0.05), first_half, second_half], [])
    assert reading.source is AboSource.PATIENT_REPORTED_ON_FORM


def test_a_caption_without_an_Rh_does_not_question_the_subjects_identity() -> None:
    """`A` and `A+` are the same claim about the group, stated to different
    precision. Treating that as a conflict raised the identity flag on captions
    that merely omitted the sign."""
    image = read_abo([FA_LABEL, box(0.48, "A+", w=0.05)], [])
    decision = reconcile_abo(image, caption_claims={("A", Rh.UNKNOWN)})
    assert decision.status is AboStatus.RESOLVED
    assert decision.group == "A"
    assert decision.subject_identity_questioned is False


def test_a_caption_with_a_different_letter_still_conflicts() -> None:
    image = read_abo([FA_LABEL, box(0.48, "A+", w=0.05)], [])
    decision = reconcile_abo(image, caption_claims={("B", Rh.UNKNOWN)})
    assert decision.status is AboStatus.CONFLICT


def test_a_caption_with_the_opposite_Rh_still_conflicts() -> None:
    image = read_abo([FA_LABEL, box(0.48, "A+", w=0.05)], [])
    decision = reconcile_abo(image, caption_claims={("A", Rh.NEGATIVE)})
    assert decision.status is AboStatus.CONFLICT


# --- one printed value detected twice --------------------------------------
#
# 1,113 documents reach the "more than one value in a single cell" branch, and
# 996 of them are ONE printed token that two engines each drew a box around:
# the Latin pass (onnxtr) and the Persian pass (easyocr) both see it, so the
# cell holds two boxes over the same ink. Refusing those cost 993 documents a
# blood group and 760 an Rh, for no safety: the two readings AGREE.
#
# Measured before shipping: 0 letter and 0 sign contradictions against 282
# independently-written chat claims, 6/6 against the reviewer's own answers,
# 14/14 against PP-OCRv5 whole-page and 14/14 against PP-OCRv6 — versus a 1.0%
# letter-error control for the readings the pipeline already ships. The
# genuinely different cells (117 of them) still go to a person.


FA_VALUE = box(0.48, "A+", w=0.05)


def overlapping(box: Box, text: str, *, shrink: float = 0.06) -> Box:
    """A second engine's box over the same printed ink: nearly the same
    rectangle, never exactly it."""
    dx = (box.x1 - box.x0) * shrink
    dy = (box.y1 - box.y0) * shrink
    return Box(x0=box.x0 + dx, y0=box.y0 + dy, x1=box.x1 - dx, y1=box.y1 - dy, text=text)


def test_two_engines_over_one_token_is_one_value() -> None:
    """The gate that does all the work: the parsed values must be identical."""
    latin = [FA_VALUE]
    persian = [FA_LABEL, overlapping(FA_VALUE, FA_VALUE.text)]
    reading = read_abo(persian, latin)
    assert reading.status is AboStatus.RESOLVED
    assert reading.group == "A"
    assert reading.rh is Rh.POSITIVE


def test_a_sign_disagreement_still_goes_to_a_person() -> None:
    """`A+` and `A-` over one piece of ink is the failure that would send a
    Rh-negative recipient into a positive pool. It must never collapse."""
    latin = [FA_VALUE]
    persian = [FA_LABEL, overlapping(FA_VALUE, "A-")]
    reading = read_abo(persian, latin)
    assert reading.status is AboStatus.REVIEW_REQUIRED
    assert "more than one blood-group value" in reading.reason


def test_a_letter_disagreement_still_goes_to_a_person() -> None:
    latin = [FA_VALUE]
    persian = [FA_LABEL, overlapping(FA_VALUE, "B+")]
    assert read_abo(persian, latin).status is AboStatus.REVIEW_REQUIRED


def test_two_separate_tokens_that_happen_to_agree_do_not_collapse() -> None:
    """Two subjects on one page can both be group A. Agreement is only evidence
    when the boxes are the SAME INK; boxes that do not overlap are two values."""
    second = Box(x0=0.62, y0=FA_VALUE.y0, x1=0.70, y1=FA_VALUE.y1, text="A+")
    reading = read_abo([FA_LABEL, second], [FA_VALUE])
    assert reading.status is AboStatus.REVIEW_REQUIRED


def test_one_engine_seeing_its_own_token_twice_is_not_corroboration() -> None:
    """A detector emitting two boxes over one token is an artefact, not a
    second opinion. Both boxes here come from the Latin pass."""
    latin = [FA_VALUE, overlapping(FA_VALUE, FA_VALUE.text)]
    assert read_abo([FA_LABEL], latin).status is AboStatus.REVIEW_REQUIRED


def test_a_collapsed_cell_records_both_boxes_it_agreed_on() -> None:
    """Provenance: a reviewer has to be able to see the agreement. Without the
    boxes the page shows a RESOLVED medical value with nothing behind it."""
    latin = [FA_VALUE]
    persian = [FA_LABEL, overlapping(FA_VALUE, FA_VALUE.text)]
    reading = read_abo(persian, latin)
    assert reading.value_box is not None
    assert len(reading.value_boxes) == 2
    assert reading.raw_value == FA_VALUE.text


def test_the_box_kept_is_the_one_whose_text_was_read() -> None:
    """`raw_value` and `value_box` must describe the same box. They used to be
    whichever engine the list happened to order first."""
    latin = [FA_VALUE]
    persian = [FA_LABEL, overlapping(FA_VALUE, FA_VALUE.text)]
    reading = read_abo(persian, latin)
    assert reading.value_box is not None
    assert reading.raw_value == reading.value_box.text


# --- the label in the spellings the recognizer actually produces -------------
#
# 9 of the reviewer's 50 ABO misses have the label present in a spelling the
# strict patterns miss. The pair route (s16 Tier 1) reads a damaged group word
# IMMEDIATELY followed by a damaged blood word; adjacency is the whole gate.


def test_a_damaged_pair_in_one_box_is_the_label() -> None:
    """`کروا خوتی`: neither half matches the strict pattern, both match the
    wide ones, and they are adjacent — the printed phrase, misread."""
    reading = read_abo([box(0.60, "کروا خوتی :"), box(0.48, "A+", w=0.05)], [])
    assert reading.status is AboStatus.RESOLVED
    assert reading.group == "A"


def test_either_damaged_half_alone_is_not_a_label() -> None:
    """A lone damaged word anchors nothing: `کرده` ("done") matches the wide
    group pattern and sits in prose on 364 of these pages."""
    for text in ("کروا", "خوتی", "کرده"):
        reading = read_abo([box(0.60, text), box(0.48, "A+", w=0.05)], [])
        assert reading.status is AboStatus.UNKNOWN, text


def test_the_verb_followed_by_prose_is_not_a_label() -> None:
    """`کرده است` — "has done" — is the collision the wide pattern invites, and
    the second word is not blood-shaped, so the pair route refuses it."""
    reading = read_abo([box(0.60, "کرده است"), box(0.48, "A+", w=0.05)], [])
    assert reading.status is AboStatus.UNKNOWN


def test_the_pair_route_still_refuses_the_disclaimer_sentence() -> None:
    """The letterhead's disclaimer contains the phrase and is prose; the length
    and disclaimer gates run before the pair route and still hold."""
    reading = read_abo([box(0.60, DISCLAIMER_FA, w=0.35), box(0.20, "A+", w=0.05)], [])
    assert reading.status is AboStatus.UNKNOWN


# --- the cell window: the value on the label's own ruled row -----------------
#
# CV_RESEARCH s19 item 1, two rules verified in sequence over 23,566 documents.
#
# The shipped window is a LINE: a box joins the cell only when it shares more
# than `_OVERLAP` (35%) of the shorter box's height with the label. That is
# right for the dominant layout and wrong wherever the recognizer's two passes
# draw their rectangles a third of a line apart — the Persian line box extends
# below its baseline, the Latin capitals sit above it. The value is then in the
# label's printed CELL and outside its box.
#
# Two rescues, and they are not equally evidenced. The counts below are what
# `read_abo` RETURNS over 23,485 documents in the raw frame; what the pipeline
# publishes is smaller, and the difference is `reconcile_abo`.
#
# **The ruled row (`AboRescue.BAND`).** Where the page prints a grid, the row
# between two rulings IS the cell, and a value inside it belongs to the label
# inside it. Measured: +42 readings, 0 lost, 0 values changed, and one labelled
# miss recovered that agrees with the human. The band is capped at
# `_MAX_BAND_HEIGHTS` because a taller band spans two printed rows, and a
# partial printed in the label's own cell refuses it — the route-only variant
# measured +43 before that gate, and 3 of those published over a contradiction.
#
# **The centre band on an unruled page (`AboRescue.CENTRE`).** No grid, so the
# cell is not geometrically defined and the rule rests on distance alone. It
# ships only behind six admission gates (side branch, above the centre, no
# ruling between, anchor scale, ownership, partial contradiction): +51 readings
# under the combined rule (+82 as a route-only variant, before the ruled row
# takes the pages it can locate), 1 lost — a cross-engine Rh sign disagreement
# the shipped code publishes on one engine's word and this rule sends to a
# person.
#
# NO HUMAN HAS CHECKED A SINGLE CENTRE RESCUE. Not one gain is a labelled
# document, which is why every rescued reading is marked in its provenance and
# the two routes get SEPARATE review strata (`abo_centre_rescue` and
# `abo_band_rescue` in `scripts/review_pack.py`): pooled under one tag, the
# centre route drew about two documents a pack and HA-019 needs twenty.


def ruled(*ys: float, x0: float = 0.0, x1: float = 1.0, vertical: tuple = ()) -> Lattice:
    """A page whose printed horizontal rulings are level and full width."""
    return Lattice(tuple(Ruling(x0, x1, y, y) for y in ys), vertical)


def offset_box(
    anchor: Box,
    text: str,
    offset: float,
    *,
    x0: float = 0.44,
    w: float = 0.05,
    h: float | None = None,
) -> Box:
    """A box whose centre sits `offset` ANCHOR heights above the anchor's centre.

    Negative offsets sit below. With equal heights the two boxes then share
    `1 - offset` of their extent, so 0.67 is the "overlap 0.33" case the
    proposal was written from: outside the 0.35 line test, inside the row.
    """
    height = anchor.height if h is None else h
    centre = anchor.centre_y - offset * anchor.height
    return Box(x0=x0, y0=centre - height / 2, x1=x0 + w, y1=centre + height / 2, text=text)


# The author's seven counterexamples, restated where the combined rule changes
# the answer: a page with no usable band falls through to the centre rescue,
# which is what "never ship CENTRE only" cuts both ways into.


def test_a_value_on_the_labels_ruled_row_is_read() -> None:
    """Overlap 0.33 — refused by the line test, inside the label's own row."""
    value = offset_box(FA_LABEL, "A+", 0.67)
    reading = read_abo([FA_LABEL], [value], lattice=ruled(0.29, 0.32))
    assert reading.status is AboStatus.RESOLVED
    assert (reading.group, reading.rh) == ("A", Rh.POSITIVE)
    assert reading.rescued is AboRescue.BAND
    assert reading.value_boxes == (value,)


def test_the_same_geometry_without_a_lattice_is_not_a_band_rescue() -> None:
    """The author proposed this as "still refused". Under the combined rule an
    unruled page is exactly the population the centre rescue serves, so the
    value is admitted — by the WEAKER route, and marked as such."""
    reading = read_abo([FA_LABEL], [offset_box(FA_LABEL, "A+", 0.67)], lattice=None)
    assert reading.rescued is AboRescue.CENTRE


def test_a_band_taller_than_two_label_heights_never_rescues() -> None:
    """A band that tall spans two printed rows, so it does not locate a cell.

    The token here is 0.9 label heights off: inside the row rule's absolute
    reach, outside the centre band, so nothing admits it.
    """
    reading = read_abo([FA_LABEL], [offset_box(FA_LABEL, "A+", 0.9)], lattice=ruled(0.28, 0.33))
    assert reading.status is AboStatus.REVIEW_REQUIRED
    assert reading.rescued is None


def test_a_band_of_exactly_two_label_heights_still_rescues() -> None:
    reading = read_abo([FA_LABEL], [offset_box(FA_LABEL, "A+", 0.67)], lattice=ruled(0.29, 0.33))
    assert reading.status is AboStatus.RESOLVED
    assert reading.rescued is AboRescue.BAND


def test_a_token_in_the_adjacent_row_is_refused() -> None:
    """0.9 label heights away and inside the absolute reach, but the ruling
    between them says it is another row's cell."""
    reading = read_abo([FA_LABEL], [offset_box(FA_LABEL, "A+", 0.9)], lattice=ruled(0.295, 0.325))
    assert reading.status is AboStatus.REVIEW_REQUIRED
    assert reading.rescued is None


def test_a_same_band_token_on_the_wrong_side_is_refused() -> None:
    """Direction follows the script and the rescue does not loosen it: a
    Persian label's value is to its LEFT."""
    wrong_side = offset_box(FA_LABEL, "A+", 0.67, x0=0.75)
    reading = read_abo([FA_LABEL], [wrong_side], lattice=ruled(0.29, 0.32))
    assert reading.group is None


def test_a_letter_alone_in_the_band_is_still_not_a_value() -> None:
    reading = read_abo([FA_LABEL], [offset_box(FA_LABEL, "A", 0.67)], lattice=ruled(0.29, 0.32))
    assert reading.status is AboStatus.REVIEW_REQUIRED
    assert reading.group is None
    assert reading.rh is Rh.UNKNOWN


def test_two_different_values_in_the_band_still_go_to_a_person() -> None:
    """Neither stands between the other and the label, so both are in the cell
    and the cell is doubled. Proximity does not settle a doubled cell."""
    reading = read_abo(
        [FA_LABEL],
        [offset_box(FA_LABEL, "A+", 0.67), offset_box(FA_LABEL, "B+", -0.67)],
        lattice=ruled(0.29, 0.33),
    )
    assert reading.status is AboStatus.REVIEW_REQUIRED
    assert reading.group is None


def test_a_value_the_line_rule_already_owns_stops_the_reach_past_it() -> None:
    """F4, and never-worse: the label's own line holds a value the pipeline
    resolves today, and the band reaches a second token further along the row.
    The nearer value is the label's, and the page keeps the answer it has."""
    on_the_line = box(0.48, "A+", w=0.05)
    further = offset_box(FA_LABEL, "B+", 0.67, x0=0.36)
    reading = read_abo([FA_LABEL], [on_the_line, further], lattice=ruled(0.29, 0.32))
    assert reading.status is AboStatus.RESOLVED
    assert reading.group == "A"
    assert reading.rescued is None


# F2. The loss definition. "Lost 0" was met by choosing the cap, not by the
# rule's merit: the nearest observed same-ink cross-engine SIGN disagreement
# sits in a band 2.08 label heights tall, 0.08h outside the cap. Where the two
# engines do collide, the rescue must take the page AWAY from the shipped
# single-engine sign rather than confirm it.


def test_a_same_ink_sign_disagreement_across_the_line_test_goes_to_review() -> None:
    """One engine's box reaches the label's line and the other's does not.

    Same ink (IoU 0.7), same letter, opposite sign. The shipped window sees
    only the box that reaches the line and publishes its sign; admitting the
    band makes the cell doubled, which is what a person must settle.
    """
    on_the_line = Box(x0=0.44, y0=0.2825, x1=0.49, y1=0.3115, text="A+")
    in_the_band = Box(x0=0.44, y0=0.2775, x1=0.49, y1=0.3065, text="A-")
    lattice = ruled(0.285, 0.322)
    assert read_abo([FA_LABEL], [on_the_line], lattice=lattice).status is AboStatus.RESOLVED
    reading = read_abo([FA_LABEL, in_the_band], [on_the_line], lattice=lattice)
    assert reading.status is AboStatus.REVIEW_REQUIRED
    assert "more than one blood-group value" in reading.reason


# F1. Thirteen of the 43 gains are one engine's box with nothing behind it.
# Corroboration decides whether the value is published or offered to a person.


def test_a_band_rescue_two_engines_agreed_on_is_published() -> None:
    """17 of the 43, including the one labelled recovery."""
    value = offset_box(FA_LABEL, "A+", 0.67)
    reading = read_abo([FA_LABEL, overlapping(value, "A+")], [value], lattice=ruled(0.29, 0.32))
    assert reading.rescued is AboRescue.BAND
    assert len(reading.value_boxes) == 2
    decision = reconcile_abo(reading)
    assert decision.status is AboStatus.RESOLVED
    assert decision.group == "A"


def test_an_uncorroborated_band_rescue_is_offered_to_a_person() -> None:
    """13 of the 43: one box, no caption, no second engine. The candidate and
    the anchor travel with the review item, which is more than today's generic
    "its cell could not be read" gives a reviewer."""
    value = offset_box(FA_LABEL, "A+", 0.67)
    reading = read_abo([FA_LABEL], [value], lattice=ruled(0.29, 0.32))
    decision = reconcile_abo(reading)
    assert decision.status is AboStatus.REVIEW_REQUIRED
    assert decision.group is None
    assert decision.rh is Rh.UNKNOWN
    assert "nothing corroborates it" in decision.reason
    assert reading.anchor_box is FA_LABEL
    assert reading.value_boxes == (value,)


def test_a_caption_agreeing_on_the_letter_publishes_the_band_rescue() -> None:
    """13 of the 43 are corroborated this way; the caption need not state an Rh."""
    reading = read_abo([FA_LABEL], [offset_box(FA_LABEL, "A+", 0.67)], lattice=ruled(0.29, 0.32))
    decision = reconcile_abo(reading, caption_claims={("A", Rh.UNKNOWN)})
    assert decision.status is AboStatus.RESOLVED
    assert (decision.group, decision.rh) == ("A", Rh.POSITIVE)


def test_a_caption_contradicting_a_band_rescue_still_conflicts() -> None:
    reading = read_abo([FA_LABEL], [offset_box(FA_LABEL, "A+", 0.67)], lattice=ruled(0.29, 0.32))
    decision = reconcile_abo(reading, caption_claims={("B", Rh.POSITIVE)})
    assert decision.status is AboStatus.CONFLICT
    assert decision.subject_identity_questioned is True


def test_a_value_on_the_labels_own_line_is_never_downgraded() -> None:
    """The rescue changes nothing about the readings the pipeline already
    ships: one engine, no caption, on the line -> RESOLVED as before."""
    reading = read_abo([FA_LABEL, FA_VALUE], [], lattice=ruled(0.29, 0.32))
    assert reading.rescued is None
    assert reconcile_abo(reading).status is AboStatus.RESOLVED


# What the ruled-row rule ADMITS. Each of these is a real shape the corpus
# contains or a construction the code path allows; they are pinned so that a
# later change to the window has to change a test rather than a number.


def test_an_HLA_shaped_token_in_the_band_is_admitted_as_a_blood_group() -> None:
    """`B-` is a blood group and an HLA locus letter with a dash. Geometry
    cannot separate them, so this is admitted — and, uncorroborated, it is
    exactly the class F1 sends to a person."""
    reading = read_abo([FA_LABEL], [offset_box(FA_LABEL, "B-", 0.67)], lattice=ruled(0.29, 0.32))
    assert (reading.group, reading.rh) == ("B", Rh.NEGATIVE)
    assert reconcile_abo(reading).status is AboStatus.REVIEW_REQUIRED


def test_a_second_subjects_value_eight_heights_along_the_row_is_admitted() -> None:
    """The window reaches `_MAX_GAP` (10) label heights along the row, which the
    shipped line rule does too. A page printing two people's groups on one row
    would bind the wrong one; measured, 0 of the 43 gains is a comparison
    sheet, and comparison sheets are refused upstream."""
    far = offset_box(FA_LABEL, "A+", 0.67, x0=0.39)
    assert FA_LABEL.x0 - far.x1 == pytest.approx(8 * FA_LABEL.height)
    reading = read_abo([FA_LABEL], [far], lattice=ruled(0.29, 0.32))
    assert reading.rescued is AboRescue.BAND
    assert reading.group == "A"


def test_a_tall_multi_line_anchor_stretches_the_absolute_reach() -> None:
    """The reach is one ANCHOR height, so a three-line Persian block reaches a
    whole printed line away. The centre rescue refuses out-of-scale anchors;
    the ruled row does not, because the ruling is the cell boundary."""
    tall = Box(x0=0.60, y0=0.28, x1=0.70, y1=0.34, text=GROUP_LABEL_FA)
    value = offset_box(tall, "A+", 0.75, h=0.02)
    reading = read_abo([tall], [value], lattice=ruled(0.25, 0.32))
    assert reading.rescued is AboRescue.BAND
    assert reading.group == "A"


def test_a_second_printed_line_inside_a_two_height_band_is_admitted() -> None:
    """A band may be two label heights tall and hold two printed lines. The
    value on the OTHER line is inside the row and is taken."""
    other_line = Box(x0=0.20, y0=0.2866, x1=0.30, y1=0.3066, text="نام بیمار")
    reading = read_abo(
        [FA_LABEL, other_line], [offset_box(FA_LABEL, "A+", 0.67)], lattice=ruled(0.29, 0.33)
    )
    assert reading.rescued is AboRescue.BAND


def test_the_absolute_reach_stops_just_past_one_label_height() -> None:
    """A token with NO vertical overlap at all is admitted while it is within
    one anchor height of the label's centre, and refused past it."""
    lattice = ruled(0.2975, 0.335)
    near = read_abo([FA_LABEL], [offset_box(FA_LABEL, "A+", -0.975)], lattice=lattice)
    far = read_abo([FA_LABEL], [offset_box(FA_LABEL, "A+", -1.05)], lattice=lattice)
    assert near.rescued is AboRescue.BAND
    assert far.rescued is None


def test_an_empty_cell_between_the_label_and_the_value_does_not_refuse() -> None:
    """4 of the 43 have two vertical rulings between label and value: one
    repeated form geometry with an EMPTY intermediate cell, and the shipped
    control shows the same 6% share, so it is the form and not a defect."""
    verticals = (Ruling(0.28, 0.34, 0.52, 0.52), Ruling(0.28, 0.34, 0.56, 0.56))
    reading = read_abo(
        [FA_LABEL],
        [offset_box(FA_LABEL, "A+", 0.67)],
        lattice=ruled(0.29, 0.32, vertical=verticals),
    )
    assert reading.rescued is AboRescue.BAND


def test_a_value_shaped_box_standing_between_them_refuses_the_rescue() -> None:
    """F4. Nothing may stand in a cell between the label and the value: if
    something does, the value is not the nearest thing the label owns."""
    between = Box(x0=0.52, y0=0.2866, x1=0.56, y1=0.3066, text="+")
    reading = read_abo(
        [FA_LABEL], [offset_box(FA_LABEL, "A+", 0.67), between], lattice=ruled(0.29, 0.32)
    )
    assert reading.rescued is None
    assert reading.status is AboStatus.REVIEW_REQUIRED


def test_the_inside_x_span_case_is_rescued_only_by_the_ruled_row() -> None:
    """A Persian line box swallows the Latin value that sits inside it — the
    shape of the one labelled miss this rule recovers. On a RULED page the row
    is the cell and the value is taken; with no row, the centre rescue refuses
    the inside-x-span branch outright (an HLA-row token across a ruling is what
    it admitted in the corpus)."""
    inside = offset_box(FA_LABEL, "A+", 0.67, x0=0.62)
    assert read_abo([FA_LABEL], [inside], lattice=ruled(0.29, 0.32)).rescued is AboRescue.BAND
    assert read_abo([FA_LABEL], [inside], lattice=None).status is AboStatus.REVIEW_REQUIRED


# --- the centre band, on pages that print no ruled row -----------------------
#
# The gates are what make this shippable, and each was measured on the 99
# ungated admissions: below the label centre 5, partial contradiction 7,
# ruling between 2-4, out-of-scale anchor 4, a nearer label owning the token 6,
# inside-x-span 1. What survives is +82 documents and one document LOST, which
# is the point of fix 7: the shipped code publishes an Rh sign a second engine
# contradicts, and this rule sends that page to a person instead.


def persian_page(*extra: Box) -> list[Box]:
    """Filler Persian boxes so the page has an ordinary label scale."""
    return [
        Box(x0=0.10, y0=y, x1=0.20, y1=y + 0.02, text="متن") for y in (0.60, 0.64, 0.68)
    ] + list(extra)


def test_a_value_just_above_an_unruled_label_is_read() -> None:
    """C6. Nothing else on the page: the intended case, and the only one no
    gate can distinguish from a wrong-line token."""
    value = offset_box(FA_LABEL, "A+", 0.67)
    reading = read_abo([FA_LABEL], [value], lattice=None)
    assert reading.status is AboStatus.RESOLVED
    assert (reading.group, reading.rh) == ("A", Rh.POSITIVE)
    assert reading.rescued is AboRescue.CENTRE
    assert reconcile_abo(reading).status is AboStatus.RESOLVED


def test_a_latin_label_takes_a_value_just_above_it_too() -> None:
    """C12. The rightwards branch, same reach."""
    reading = read_abo([], [EN_LABEL, offset_box(EN_LABEL, "AB+", 0.67, x0=0.33)], lattice=None)
    assert reading.status is AboStatus.RESOLVED
    assert (reading.group, reading.rh) == ("AB", Rh.POSITIVE)
    assert reading.rescued is AboRescue.CENTRE


def test_a_centre_rescue_is_never_downgraded_for_being_uncorroborated() -> None:
    """F1 downgrades the RULED-ROW route only. The centre route's own answer to
    "nothing corroborates this" is the `abo_centre_rescue` review stratum, not a
    per-document refusal: 82 documents with 35/35 caption agreement and zero
    human checks is a stratum-sized question, not a per-cell one."""
    reading = read_abo([FA_LABEL], [offset_box(FA_LABEL, "A+", 0.67)], lattice=None)
    assert len(reading.value_boxes) == 1
    assert reconcile_abo(reading).status is AboStatus.RESOLVED


def test_a_token_owned_by_a_nearer_label_on_its_own_line_is_refused() -> None:
    """C1. The line above prints another field, and its label is nearer to the
    token than ours with more of the token's height beside it."""
    other = Box(x0=0.52, y0=0.2866, x1=0.58, y1=0.3066, text="نام")
    reading = read_abo(
        persian_page(FA_LABEL, other), [offset_box(FA_LABEL, "O+", 0.67)], lattice=None
    )
    assert reading.status is AboStatus.REVIEW_REQUIRED
    assert reading.group is None


def test_a_same_ink_partner_does_not_buy_a_token_off_another_field() -> None:
    """C1c. Two engines agreeing tests INK, not LINE: both boxes sit on the
    other field's row, and the ownership gate refuses both."""
    other = Box(x0=0.52, y0=0.2866, x1=0.58, y1=0.3066, text="نام")
    token = offset_box(FA_LABEL, "O+", 0.67)
    reading = read_abo(
        persian_page(FA_LABEL, other, overlapping(token, "O+")), [token], lattice=None
    )
    assert reading.status is AboStatus.REVIEW_REQUIRED
    assert reading.group is None


def test_a_better_aligned_label_at_the_same_distance_takes_the_token() -> None:
    """C9b. Without the tie-break a two-letter field label on the line above
    walks through: it is no NEARER than ours, and the token is squarely on its
    line and only a third on ours."""
    other = Box(x0=0.60, y0=0.2866, x1=0.66, y1=0.3066, text="کد")
    reading = read_abo(
        persian_page(FA_LABEL, other), [offset_box(FA_LABEL, "A+", 0.67)], lattice=None
    )
    assert reading.status is AboStatus.REVIEW_REQUIRED
    assert reading.group is None


def test_ownership_holds_on_the_rightwards_side_too() -> None:
    """C9c. A Latin label reads to its right, so the competing label is the one
    between it and the token."""
    other = Box(x0=0.36, y0=0.2866, x1=0.42, y1=0.3066, text="Sex")
    reading = read_abo([], [EN_LABEL, other, offset_box(EN_LABEL, "A+", 0.67)], lattice=None)
    assert reading.status is AboStatus.REVIEW_REQUIRED
    assert reading.group is None


def test_an_out_of_scale_label_box_cannot_reach_the_next_line() -> None:
    """C1b. A 2.5-line Persian block reaching down at normal pitch. The reach
    is a fraction of the ANCHOR's height, so an over-large box buys itself a
    longer arm; the scale gate compares it against the page's own PERSIAN
    median, because a shipped Persian label runs 1.6x the Latin one."""
    tall = Box(x0=0.60, y0=0.28, x1=0.70, y1=0.33, text=GROUP_LABEL_FA)
    token = Box(x0=0.44, y0=0.265, x1=0.49, y1=0.285, text="A-")
    reading = read_abo(persian_page(tall), [token], lattice=None)
    assert reading.status is AboStatus.REVIEW_REQUIRED
    assert reading.group is None


def test_a_five_line_label_box_is_refused_by_the_same_gate() -> None:
    """C10. The two worst in the corpus ran 4.9x and 5.0x the page median."""
    line_box = Box(x0=0.55, y0=0.26, x1=0.75, y1=0.36, text=GROUP_LABEL_FA)
    token = Box(x0=0.35, y0=0.245, x1=0.40, y1=0.265, text="A+")
    reading = read_abo(persian_page(line_box), [token], lattice=None)
    assert reading.status is AboStatus.REVIEW_REQUIRED
    assert reading.group is None


def test_a_ruling_between_the_label_and_the_token_refuses_it() -> None:
    """C2. A reference range `0-5` split by the recognizer: `0-` parses as O
    NEGATIVE through the digit-zero repair. The page prints a ruling between
    that row and the label's, and the grid outranks the distance."""
    fragment = Box(x0=0.44, y0=0.2866, x1=0.49, y1=0.3066, text="0-")
    rest = Box(x0=0.395, y0=0.2866, x1=0.435, y1=0.3066, text="5")
    assert read_abo([FA_LABEL], [fragment, rest], lattice=None).group == "O"
    reading = read_abo([FA_LABEL], [fragment, rest], lattice=ruled(0.30))
    assert reading.status is AboStatus.REVIEW_REQUIRED
    assert reading.group is None


def test_a_token_below_the_label_centre_is_never_rescued() -> None:
    """C3. `B*` on the HLA row below, read as `B+` because `+` is one of the
    star variants. Shipped values sit ABOVE their label in 94-96% of resolved
    cells, and every below-centre rescue in the corpus was a ruling-crossing or
    a partial contradiction."""
    reading = read_abo([FA_LABEL], [offset_box(FA_LABEL, "B+", -0.67)], lattice=None)
    assert reading.status is AboStatus.REVIEW_REQUIRED
    assert reading.group is None


def test_a_latin_label_below_its_own_line_is_refused_too() -> None:
    """C11."""
    reading = read_abo([], [EN_LABEL, offset_box(EN_LABEL, "AB+", -0.67, x0=0.33)], lattice=None)
    assert reading.status is AboStatus.REVIEW_REQUIRED
    assert reading.group is None


def test_a_sign_in_the_cell_contradicting_the_rescued_token_refuses_it() -> None:
    """C5. 7 of the 9 corpus cases: the label's OWN cell holds a lone `-` and
    the rescued token says `+`. Publishing over that is best-guess acceptance
    of ambiguous critical OCR; the page keeps its partial review reason."""
    in_cell = Box(x0=0.44, y0=0.30, x1=0.47, y1=0.32, text="-")
    rescued = Box(x0=0.50, y0=0.2866, x1=0.55, y1=0.3066, text="B+")
    reading = read_abo([FA_LABEL], [in_cell, rescued], lattice=None)
    assert reading.status is AboStatus.REVIEW_REQUIRED
    assert reading.reason == "an Rh sign with no group letter in its cell"


def test_a_letter_in_the_cell_contradicting_the_rescued_token_refuses_it() -> None:
    """C5b. The same rule for the group letter."""
    in_cell = Box(x0=0.44, y0=0.30, x1=0.47, y1=0.32, text="A")
    rescued = Box(x0=0.50, y0=0.2866, x1=0.55, y1=0.3066, text="B+")
    reading = read_abo([FA_LABEL], [in_cell, rescued], lattice=None)
    assert reading.status is AboStatus.REVIEW_REQUIRED
    assert reading.reason == "a group letter with no Rh sign in its cell"


def test_a_partial_that_agrees_with_the_rescued_token_does_not_refuse_it() -> None:
    """The gate refuses CONTRADICTION, not company: a lone `+` in the cell and
    a rescued `B+` are the same claim, and the sign is not overridden."""
    in_cell = Box(x0=0.44, y0=0.30, x1=0.47, y1=0.32, text="+")
    rescued = Box(x0=0.50, y0=0.2866, x1=0.55, y1=0.3066, text="B+")
    reading = read_abo([FA_LABEL], [in_cell, rescued], lattice=None)
    assert reading.status is AboStatus.RESOLVED
    assert (reading.group, reading.rh) == ("B", Rh.POSITIVE)
    assert reading.rescued is AboRescue.CENTRE


def test_the_one_document_the_centre_rescue_costs_goes_to_a_person() -> None:
    """Fix 7, and the whole of "lost 1": a cell whose value the pipeline ships
    today on one engine's sign, with the other engine's box a third of a line
    up saying the opposite. The rescue makes the cell doubled, and a doubled
    cell is a question, not a value. Strict-never-worse is recorded in
    HUMAN_ACTIONS.md rather than decided here."""
    shipped = Box(x0=0.44, y0=0.30, x1=0.49, y1=0.32, text="A+")
    other_engine = Box(x0=0.50, y0=0.2866, x1=0.55, y1=0.3066, text="A-")
    assert read_abo([FA_LABEL], [shipped], lattice=None).status is AboStatus.RESOLVED
    reading = read_abo([FA_LABEL, other_engine], [shipped], lattice=None)
    assert reading.status is AboStatus.REVIEW_REQUIRED
    assert "more than one blood-group value" in reading.reason


@pytest.mark.parametrize(
    ("offset", "rescue"),
    [(0.60, None), (0.70, AboRescue.CENTRE), (0.80, "refused")],
)
def test_the_reach_the_centre_band_actually_opens(offset: float, rescue: object) -> None:
    """Why `_RESCUE_BAND` is 0.75 and why 0.50 would gain nothing.

    Two boxes of equal height share `1 - offset` of their extent, so anything
    closer than 0.65 anchor heights ALREADY passes the 0.35 line test and needs
    no rescue at all. The window this constant opens is (0.65h, 0.75h]; a 0.50h
    setting opens nothing. Measured over 23,485 documents, a 1.0h setting reads
    121 instead of 93 while the translated-anchor placebo's +1.0h reach rises
    from +10 to +24 and a second +1.5h leak appears — the extra yield is
    exactly the reach the control can see, which is why it stops here.
    """
    reading = read_abo([FA_LABEL], [offset_box(FA_LABEL, "A+", offset)], lattice=None)
    if rescue == "refused":
        assert reading.status is AboStatus.REVIEW_REQUIRED
    else:
        assert reading.status is AboStatus.RESOLVED
        assert reading.rescued is rescue


# --- the review's fixes: the band route's own gates, and the marker ---------
#
# A skeptical review measured three ways the shipped branch could put a wrong
# value, or a false sentence, into the facts store. Each is pinned below.


def test_a_sign_in_the_cell_contradicting_a_BAND_rescued_token_refuses_it() -> None:
    """The centre route refused this and the band route did not.

    Measured on the live corpus: 3 of the 45 band gains publish over a partial
    printed in the label's OWN cell that contradicts the rescued token — the
    same shape the centre route calls C5. A ruled row says which CELL the token
    is in; it says nothing about the `-` already printed in that cell.
    """
    in_cell = Box(x0=0.44, y0=0.30, x1=0.47, y1=0.32, text="-")
    rescued = Box(x0=0.50, y0=0.2866, x1=0.55, y1=0.3066, text="B+")
    lattice = ruled(0.29, 0.32)
    assert read_abo([FA_LABEL], [rescued], lattice=lattice).rescued is AboRescue.BAND
    reading = read_abo([FA_LABEL], [in_cell, rescued], lattice=lattice)
    assert reading.status is AboStatus.REVIEW_REQUIRED
    assert reading.rescued is None
    assert reading.reason == "an Rh sign with no group letter in its cell"


def test_a_letter_in_the_cell_contradicting_a_BAND_rescued_token_refuses_it() -> None:
    in_cell = Box(x0=0.44, y0=0.30, x1=0.47, y1=0.32, text="A")
    rescued = Box(x0=0.50, y0=0.2866, x1=0.55, y1=0.3066, text="B+")
    reading = read_abo([FA_LABEL], [in_cell, rescued], lattice=ruled(0.29, 0.32))
    assert reading.status is AboStatus.REVIEW_REQUIRED
    assert reading.reason == "a group letter with no Rh sign in its cell"


def test_a_caption_cannot_publish_a_POSITIVE_over_a_printed_minus() -> None:
    """The wrong-Rh path the gates did not stop.

    F1(b) corroborates the LETTER and publishes the SIGN unchallenged, so a
    caption saying "B" was enough to publish `B POSITIVE` over a lone `-`
    printed in the label's own cell — one engine's reading of a sign, against
    the form's own ink, on the strength of a claim that never mentioned Rh.
    Two of the three corpus cases are exactly this. The refusal now happens
    before reconciliation, where the cell is still visible.
    """
    in_cell = Box(x0=0.44, y0=0.30, x1=0.47, y1=0.32, text="-")
    rescued = Box(x0=0.50, y0=0.2866, x1=0.55, y1=0.3066, text="B+")
    reading = read_abo([FA_LABEL], [in_cell, rescued], lattice=ruled(0.29, 0.32))
    # No caller consults the caption for this page at all: there is no band
    # reading left to corroborate.
    assert needs_corroboration(reading) is False
    decision = reconcile_abo(reading, caption_claims={("B", Rh.UNKNOWN)})
    # And handed one anyway, the form publishes nothing: what comes back is the
    # poster's own claim, at the precision the poster stated it, with no Rh and
    # with `CAPTION_CLAIM` on it. `B POSITIVE` from the form is gone.
    assert decision.rh is Rh.UNKNOWN
    assert decision.source is AboSource.CAPTION_CLAIM
    assert decision.reason == "claimed by the poster; not read from any document"


def test_a_partial_that_agrees_does_not_refuse_a_band_rescue_either() -> None:
    """The gate refuses contradiction, not company — on both routes."""
    in_cell = Box(x0=0.44, y0=0.30, x1=0.47, y1=0.32, text="+")
    rescued = Box(x0=0.50, y0=0.2866, x1=0.55, y1=0.3066, text="B+")
    reading = read_abo([FA_LABEL], [in_cell, rescued], lattice=ruled(0.29, 0.32))
    assert reading.status is AboStatus.RESOLVED
    assert reading.rescued is AboRescue.BAND


def test_the_route_marks_the_PUBLISHED_box_not_any_box_in_the_cell() -> None:
    """8 pages were stamped `rescued` that no rule changed.

    The route was taken from any rescued box among the agreeing values, so a
    page whose published box passed the line test was marked — and carried the
    sentence "the value sits on the label's own ruled row rather than on its
    line", which is false about that page. It also diluted the withdrawal group
    and the review stratum with pages nobody needs to check.
    """
    # Two boxes over one printed token, 0.0007 apart: one clears the 0.35 line
    # test against the label and the other misses it by a hair, which is the
    # whole shape of the defect.
    on_the_line = Box(x0=0.50, y0=0.3125, x1=0.55, y1=0.3325, text="A+")
    other_engine = Box(x0=0.50, y0=0.3132, x1=0.55, y1=0.3332, text="A+")
    reading = read_abo([FA_LABEL, other_engine], [on_the_line], lattice=ruled(0.30, 0.33))
    assert reading.status is AboStatus.RESOLVED
    assert reading.value_box is on_the_line
    assert len(reading.value_boxes) == 2  # the rescue still buys corroboration
    assert reading.rescued is None
    assert reading.reason == ""
    assert rule_id_for(reading) == "abo/anchored-cell"
    # Alone, the same box IS a band rescue — so the geometry really does reach
    # the branch, and it is the PUBLISHED box that decides the marker.
    assert read_abo([FA_LABEL, other_engine], [], lattice=ruled(0.30, 0.33)).rescued is (
        AboRescue.BAND
    )


def test_the_band_reason_names_the_row_height_and_the_engine_count() -> None:
    """F3. A reason that does not say how tall the row was, or how many engines
    boxed the value, tells a reviewer nothing about what the admission turned
    on. The row here is 0.03 tall against a 0.02 label: 1.50 anchor heights."""
    value = offset_box(FA_LABEL, "A+", 0.67)
    reading = read_abo([FA_LABEL, overlapping(value, "A+")], [value], lattice=ruled(0.29, 0.32))
    assert reading.rescued is AboRescue.BAND
    assert reading.band_heights == pytest.approx(1.5)
    assert reading.engines == 2
    assert "1.50 anchor heights tall" in reading.reason
    assert "2 engines boxed the value" in reading.reason
    assert reconcile_abo(reading).reason == reading.reason


def test_the_uncorroborated_reason_names_the_row_and_the_single_engine() -> None:
    value = offset_box(FA_LABEL, "A+", 0.67)
    reading = read_abo([FA_LABEL], [value], lattice=ruled(0.29, 0.32))
    assert reading.engines == 1
    decision = reconcile_abo(reading)
    assert decision.status is AboStatus.REVIEW_REQUIRED
    assert "nothing corroborates it" in decision.reason
    assert "1.50 anchor heights tall" in decision.reason
    assert "1 engine boxed the value" in decision.reason


def test_the_centre_reason_carries_no_row_height_because_there_is_no_row() -> None:
    reading = read_abo([FA_LABEL], [offset_box(FA_LABEL, "A+", 0.67)], lattice=None)
    assert reading.rescued is AboRescue.CENTRE
    assert reading.band_heights is None
    assert "anchor heights tall" not in reading.reason
    assert "1 engine boxed the value" in reading.reason


def test_the_rule_id_is_where_the_group_is_found_and_withdrawn() -> None:
    """Every pass that publishes one of these writes this string; `rule_id LIKE
    'abo/anchored-cell+%'` is HA-019's withdrawal handle."""
    band = read_abo([FA_LABEL], [offset_box(FA_LABEL, "A+", 0.67)], lattice=ruled(0.29, 0.32))
    centre = read_abo([FA_LABEL], [offset_box(FA_LABEL, "A+", 0.67)], lattice=None)
    plain = read_abo([FA_LABEL, FA_VALUE], [], lattice=ruled(0.29, 0.32))
    assert rule_id_for(band) == "abo/anchored-cell+band"
    assert rule_id_for(centre) == "abo/anchored-cell+centre"
    assert rule_id_for(plain) == "abo/anchored-cell"


def test_needs_corroboration_is_the_single_engine_band_class_and_nothing_else() -> None:
    """What a caller must consult the caption for. A centre reading is not in
    it — the centre route is not published on a chat claim — and neither is a
    band reading two engines already agreed on."""
    value = offset_box(FA_LABEL, "A+", 0.67)
    lone_band = read_abo([FA_LABEL], [value], lattice=ruled(0.29, 0.32))
    two_engines = read_abo([FA_LABEL, overlapping(value, "A+")], [value], lattice=ruled(0.29, 0.32))
    centre = read_abo([FA_LABEL], [value], lattice=None)
    plain = read_abo([FA_LABEL, FA_VALUE], [], lattice=ruled(0.29, 0.32))
    assert needs_corroboration(lone_band) is True
    assert needs_corroboration(two_engines) is False
    assert needs_corroboration(centre) is False
    assert needs_corroboration(plain) is False
    unread = read_abo([FA_LABEL], [], lattice=ruled(0.29, 0.32))
    assert needs_corroboration(unread) is False
