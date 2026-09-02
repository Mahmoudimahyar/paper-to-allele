"""Reading the subject's role — donor or recipient — off the laboratory form.

Written before the implementation, from a measured design (session artefact
`design_role.md`, computed on the true originals of both OCR passes).

**Why this must come from the image.** The role is not a property of whoever
posted the picture. Brokers repost the same report under both donor and
recipient text, 37% of messages are forwards, and 21% of typing reports arrive
with no caption at all. The form itself prints the subject's role, and that fact
survives every repost.

**The failure this file exists to prevent.** A whole-document text search for
the words "donor" and "recipient" inverts the role at scale:

* In English it is close to a coin flip. 517 documents contain BOTH words —
  26.1% of those containing "Donor" and 48.3% of those containing "Recipient".
  Judged against the printed Persian field, there are **142 documents where the
  English word "Recipient" appears but the form says DONOR**, and 75 the other
  way. The words are column headers ("Donor Name", "Recipient Frequency") and
  choice labels, not values.
* In Persian it is much safer but not free: 145 documents carry both words.
  Decisively, among the 810 documents where the `نسبت` (relationship) field
  LABEL is recognised, exactly **one** carries both — a pre-printed choice list
  would put both on all 810. So the Persian word is the value.

The rules below therefore read a value out of a cell, never a word out of a
page, and abstain wherever the two readings could disagree.
"""

from __future__ import annotations

import pytest
from kidneymatch.documents.role import (
    Role,
    RoleTier,
    decide_document_role,
    read_form_role,
)

from kidneymatch.ocr.anchors import Box, ResolutionStatus

# Form boilerplate, printed on every copy of these laboratory forms.
NESBAT = "نسبت :"  # "relationship:" — the field label
MARKAZ = "مرکز درمانی :"  # "treatment centre:" — a neighbouring field label
DONOR_WORD = "اهدا کننده"  # "donor"
DONOR_MISREAD = "امدا کنده"  # the same word as EasyOCR reads it, 482 documents
RECIPIENT_WORD = "گیرنده"  # "recipient"
RECIPIENT_MISREAD = "کیرنده"  # 1,658 documents — commoner than the correct form


def box(x0: float, text: str, y0: float = 0.23, w: float = 0.09, h: float = 0.02) -> Box:
    return Box(x0=x0, y0=y0, x1=x0 + w, y1=y0 + h, text=text)


# The value sits to the LEFT of its label: Persian reads right to left.
# Measured over 719 anchored pairs, dx/label-height was negative 719 times.
LABEL = box(0.60, NESBAT, w=0.06)
ANCHORED_DONOR = box(0.44, DONOR_WORD)
ANCHORED_RECIPIENT = box(0.44, RECIPIENT_WORD)


# --- reading the Persian field -------------------------------------------


@pytest.mark.parametrize(
    "text",
    [DONOR_WORD, "اهداکننده", DONOR_MISREAD, "هدا کننده", "مدا کننده", "اددا کننده", "دهنده"],
)
def test_the_measured_donor_spellings_are_read(text: str) -> None:
    """Canonical spelling is a MINORITY: 60.5% of donor documents.

    Dropping the recognizer's variants loses about 40% of donors.
    """
    reading = read_form_role([box(0.44, text), LABEL], [])
    assert reading.role is Role.DONOR


@pytest.mark.parametrize(
    "text", [RECIPIENT_WORD, RECIPIENT_MISREAD, "کبرنده", "کرنده", "گبرنده", "گیرند ه"]
)
def test_the_measured_recipient_spellings_are_read(text: str) -> None:
    """Canonical spelling is 52.8% of recipient documents."""
    reading = read_form_role([box(0.44, text), LABEL], [])
    assert reading.role is Role.RECIPIENT


def test_both_role_words_never_produce_a_role() -> None:
    """145 documents carry both. Measured, none of them has a field anchor.

    They are overlaid advertisement text at the foot of the page, not a form
    variant — but the pipeline cannot tell which subject the typing belongs to,
    so it must not choose.
    """
    reading = read_form_role([box(0.44, DONOR_WORD), box(0.20, RECIPIENT_WORD, y0=0.75)], [])
    assert reading.role is Role.UNKNOWN
    assert reading.status is ResolutionStatus.REVIEW_REQUIRED


def test_a_document_with_no_role_word_is_absent_not_unknown_role() -> None:
    reading = read_form_role([box(0.44, MARKAZ)], [])
    assert reading.role is Role.UNKNOWN
    assert reading.status is ResolutionStatus.UNKNOWN


# --- the tiers -----------------------------------------------------------


def test_a_value_anchored_to_its_field_label_is_the_strongest_tier() -> None:
    reading = read_form_role([ANCHORED_DONOR, LABEL], [])
    assert reading.tier is RoleTier.A_ANCHORED
    assert reading.anchor_box == LABEL


def test_a_value_to_the_RIGHT_of_the_label_is_never_anchored() -> None:
    """Persian is right-to-left: the value precedes its label on the page.

    Measured 719 of 719 anchored pairs with the value to the left. A match on
    the right is a different field's value, or the label of something else.
    """
    to_the_right = box(0.70, DONOR_WORD)
    reading = read_form_role([to_the_right, LABEL], [])
    assert reading.tier is not RoleTier.A_ANCHORED


def test_a_role_word_sharing_a_row_with_form_labels_is_the_middle_tier() -> None:
    """The `نسبت` label is only recognised on 810 documents, so the anchor is a
    confidence tier rather than a gate. Sitting among other printed field
    labels is weaker evidence that this is a form cell, but still evidence."""
    reading = read_form_role([box(0.44, DONOR_WORD), box(0.60, MARKAZ)], [])
    assert reading.tier is RoleTier.B_FORM_CONTEXT
    assert reading.role is Role.DONOR


def test_a_bare_role_word_is_the_weakest_tier() -> None:
    reading = read_form_role([box(0.44, DONOR_WORD)], [])
    assert reading.tier is RoleTier.C_BARE


def test_a_split_donor_phrase_is_rejoined() -> None:
    """The recognizer splits `اهدا | کننده پیوند` across two boxes.

    Rejoining adds 317 documents. The `اهدا` half is to the RIGHT of the
    `کننده` half, because Persian reads right to left; looking left would join
    across a cell boundary.
    """
    left_half = box(0.40, "کننده پیوند")
    right_half = box(0.52, "اهدا", w=0.05)
    reading = read_form_role([left_half, right_half], [])
    assert reading.role is Role.DONOR


def test_a_fragment_with_nothing_to_its_right_is_not_a_role() -> None:
    reading = read_form_role([box(0.40, "کننده پیوند")], [])
    assert reading.role is Role.UNKNOWN


# --- the English field, which is dangerous -------------------------------


def test_a_bare_english_role_word_yields_nothing() -> None:
    """The measured coin flip.

    Of 1,070 documents containing the English word `Recipient`, only 300 carry
    Persian form evidence, and it splits 150 RECIPIENT / 142 DONOR. A bare
    English role word carries no information about the subject.
    """
    reading = read_form_role([], [box(0.30, "Recipient")])
    assert reading.role is Role.UNKNOWN
    assert reading.status is ResolutionStatus.UNKNOWN


def test_an_english_column_header_yields_nothing() -> None:
    """`Donor Name` is a table heading, on 574 documents."""
    reading = read_form_role([], [box(0.30, "Donor"), box(0.40, "Name")])
    assert reading.role is Role.UNKNOWN


def test_an_english_value_after_a_status_label_is_read() -> None:
    """The one safe English pattern: 311 DONOR and 118 RECIPIENT documents,
    zero carrying both value-forms, and zero conflicts with the Persian field.

    English is left-to-right, so its value sits to the RIGHT of its label —
    the mirror of the Persian rule, and for the same reason.
    """
    reading = read_form_role([], [box(0.20, "Status:"), box(0.32, "Donor")])
    assert reading.role is Role.DONOR
    assert reading.tier is RoleTier.EN_STATUS


def test_an_english_value_after_a_choice_label_is_read() -> None:
    reading = read_form_role([], [box(0.20, "Donor/Recipient:"), box(0.38, "Recipient")])
    assert reading.role is Role.RECIPIENT


def test_persian_and_english_disagreeing_forces_review() -> None:
    """Two printed fields on one page disagreeing means neither can be trusted."""
    reading = read_form_role(
        [ANCHORED_DONOR, LABEL], [box(0.20, "Status:"), box(0.32, "Recipient")]
    )
    assert reading.status is ResolutionStatus.REVIEW_REQUIRED
    assert reading.role is Role.UNKNOWN


# --- the document decision -----------------------------------------------


def test_an_anchored_field_is_a_finding() -> None:
    decision = decide_document_role(read_form_role([ANCHORED_RECIPIENT, LABEL], []))
    assert decision.role is Role.RECIPIENT
    assert decision.is_finding is True


def test_an_uncorroborated_weak_reading_is_not_a_finding() -> None:
    """Measured: the weakest tier contradicts recipient-only serology in 20% of
    cases, against 0% for the two anchored tiers. It is a proposal at most."""
    decision = decide_document_role(read_form_role([box(0.44, DONOR_WORD)], []))
    assert decision.role is Role.UNKNOWN
    assert decision.is_finding is False


def test_a_weak_reading_corroborated_by_the_caption_becomes_a_finding() -> None:
    decision = decide_document_role(
        read_form_role([box(0.44, DONOR_WORD)], []), caption_role=Role.DONOR
    )
    assert decision.role is Role.DONOR
    assert decision.is_finding is True


def test_a_caption_may_veto_the_form_but_never_override_it() -> None:
    """A caption is written by whoever posted the image, who is often not the
    subject. It can raise a doubt; it cannot rename the person on the page."""
    decision = decide_document_role(
        read_form_role([ANCHORED_DONOR, LABEL], []), caption_role=Role.RECIPIENT
    )
    assert decision.role is Role.UNKNOWN
    assert decision.needs_review is True


def test_a_donor_form_carrying_recipient_only_tests_goes_to_review() -> None:
    """A panel-reactive-antibody or crossmatch result is a recipient's test.

    On a page whose form says donor, that means the page carries two subjects.
    """
    decision = decide_document_role(
        read_form_role([ANCHORED_DONOR, LABEL], []), has_recipient_only_test=True
    )
    assert decision.role is Role.UNKNOWN
    assert decision.needs_review is True


def test_a_recipient_only_test_alone_is_a_proposal_not_a_finding() -> None:
    decision = decide_document_role(read_form_role([], []), has_recipient_only_test=True)
    assert decision.role is Role.RECIPIENT
    assert decision.is_finding is False


def test_a_sender_prior_can_never_become_a_finding() -> None:
    """31.4% of no-caption reports come from senders who post both roles."""
    decision = decide_document_role(read_form_role([], []), sender_prior=Role.DONOR)
    assert decision.is_finding is False


@pytest.mark.parametrize("prior", [Role.DONOR, Role.RECIPIENT])
def test_no_prior_may_override_a_printed_field(prior: Role) -> None:
    decision = decide_document_role(read_form_role([ANCHORED_DONOR, LABEL], []), sender_prior=prior)
    assert decision.role is Role.DONOR


def test_nothing_at_all_is_an_unknown_role_candidate() -> None:
    decision = decide_document_role(read_form_role([], []))
    assert decision.role is Role.UNKNOWN
    assert decision.is_finding is False
