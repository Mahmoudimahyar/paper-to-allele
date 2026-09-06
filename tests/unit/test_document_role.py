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
    is_comparison_sheet,
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


def test_a_bare_role_word_the_page_prints_alone_is_read() -> None:
    """The operator's instruction: "whenever you see something like اهدا کننده
    this means donor ... do not miss these obvious evidence."

    It used to be refused, on the ground that the weakest tier contradicts
    recipient-only serology 20% of the time. That measurement stands, but the
    contradiction it names is caught by its OWN gate two branches above, so
    refusing here charged the same evidence twice. Against the reviewer's 50
    labelled roles a bare word agrees 13 times and disagrees once.

    It resolves under a distinct source, `FORM_FIELD_BARE`, so the whole group
    can be found, stratified for review and withdrawn if that changes.
    """
    decision = decide_document_role(read_form_role([box(0.44, DONOR_WORD)], []))
    assert decision.role is Role.DONOR
    assert decision.is_finding is True
    assert decision.source == "FORM_FIELD_BARE"


def test_a_bare_word_is_still_refused_when_the_page_contradicts_it() -> None:
    """Every contradiction gate runs BEFORE the bare word is accepted, and each
    one still refuses. Reading a bare word is not the same as trusting it over
    evidence that disagrees."""
    bare = read_form_role([box(0.44, DONOR_WORD)], [])
    # A recipient's test on a donor form means the page carries two subjects.
    assert decide_document_role(bare, has_recipient_only_test=True).role is Role.UNKNOWN
    # The chat says the other thing.
    assert decide_document_role(bare, caption_role=Role.RECIPIENT).role is Role.UNKNOWN


def test_both_role_words_printed_is_still_ambiguous() -> None:
    """Two role words on one page is the case a bare reading must never
    resolve: which subject the typing belongs to is exactly what is unknown."""
    reading = read_form_role([box(0.44, DONOR_WORD), box(0.60, RECIPIENT_WORD)], [])
    decision = decide_document_role(reading)
    assert decision.role is Role.UNKNOWN
    assert decision.needs_review is True


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


# --- fixes from the skeptical review -------------------------------------

KARDE = "پیوند نکرده"  # "has not transplanted" — an ordinary past participle
GARDE = "گرده"  # how the recognizer sometimes renders the blood-group word
CANDIDATE = "کاندید پیوند"  # "transplant candidate" — a recipient
BOTH_IN_ONE_BOX = "اهدا کننده / گیرنده"  # a printed choice label, not a value


@pytest.mark.parametrize("text", [KARDE, GARDE, "اقدام کرده", "مراجعه کرده"])
def test_the_ordinary_verb_karde_is_not_a_recipient(text: str) -> None:
    """The recipient pattern made the `ن` optional, so it matched `کرده`
    ("done") and `گرده`.

    Measured: 2,062 documents matched on that stem, 61 of them promoted to a
    Tier-B *finding* with no corroboration, and 740 genuine donor forms were
    pushed into review as "both role words printed".
    """
    reading = read_form_role([box(0.44, text), box(0.60, MARKAZ)], [])
    assert reading.role is Role.UNKNOWN


@pytest.mark.parametrize("text", [RECIPIENT_WORD, RECIPIENT_MISREAD, "کبرنده", "کرنده", "گبرنده"])
def test_the_real_recipient_spellings_still_match(text: str) -> None:
    """The fix must not cost the measured variants: `کیرنده` alone is 1,658
    documents, more than the correct spelling."""
    assert read_form_role([box(0.44, text), LABEL], []).role is Role.RECIPIENT


def test_a_donor_form_is_no_longer_pushed_to_review_by_the_false_stem() -> None:
    reading = read_form_role([ANCHORED_DONOR, LABEL, box(0.20, KARDE, y0=0.70)], [])
    assert reading.role is Role.DONOR
    assert reading.status is ResolutionStatus.RESOLVED


def test_a_box_holding_both_role_words_is_a_label_not_a_donor_value() -> None:
    """It is a printed choice list. Donor was tested first, so it read DONOR."""
    reading = read_form_role([box(0.44, BOTH_IN_ONE_BOX)], [])
    assert reading.role is Role.UNKNOWN


def test_a_choice_label_does_not_become_a_finding_with_an_agreeing_caption() -> None:
    decision = decide_document_role(
        read_form_role([box(0.44, BOTH_IN_ONE_BOX)], []), caption_role=Role.DONOR
    )
    assert decision.is_finding is False


def test_transplant_candidate_is_recipient_evidence() -> None:
    """`کاندید پیوند` means the subject is waiting for a transplant.

    Measured: it co-occurs with a recipient phrase on 1,867 documents and with a
    donor phrase on 15, and 476 documents carry it with no other role evidence.
    """
    reading = read_form_role([box(0.44, CANDIDATE), box(0.60, MARKAZ)], [])
    assert reading.role is Role.RECIPIENT


def test_transplant_candidate_contradicting_a_donor_field_forces_review() -> None:
    reading = read_form_role([ANCHORED_DONOR, LABEL, box(0.20, CANDIDATE, y0=0.40)], [])
    assert reading.status is ResolutionStatus.REVIEW_REQUIRED


# --- W7: comparison sheets -----------------------------------------------


def test_a_page_printing_both_english_roles_as_column_headers_is_a_comparison_sheet() -> None:
    """503 documents print `Donor | Recipient` as column headings.

    They carry two people's typings side by side, and are the only path found by
    which two patients' alleles could enter one record.
    """
    assert is_comparison_sheet([box(0.30, "Donor"), box(0.55, "Recipient")]) is True


def test_a_page_with_one_role_word_is_not_a_comparison_sheet() -> None:
    assert is_comparison_sheet([box(0.30, "Donor"), box(0.55, "Name")]) is False


def test_role_words_on_different_rows_are_not_column_headers() -> None:
    assert is_comparison_sheet([box(0.30, "Donor"), box(0.55, "Recipient", y0=0.70)]) is False
