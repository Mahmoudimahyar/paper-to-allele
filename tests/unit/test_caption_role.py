"""Reading a role claim out of the message a photograph was posted with.

The caption is written by whoever posted the image — very often a broker, not
the patient — so a caption may corroborate or veto the printed form field and
may never rename the person on the page. That precedence lives in
`decide_document_role`; this module only decides what the caption *says*.

The trap that governs the design: in this market the same word appears in both
directions. "اهدا کننده" is "donor", but "اهدا کننده نیاز دارم" is "I need a
donor" — written by a recipient. Getting that backwards would invert the role
on the documents where a caption is the only evidence, so anything that looks
like a request is refused rather than guessed.

Every string here is fabricated.
"""

from __future__ import annotations

import pytest

from kidneymatch.documents.caption import CaptionTier, read_caption_role
from kidneymatch.documents.role import Role

pytestmark = pytest.mark.task("HIST-002")


def role_of(text: str) -> Role:
    return read_caption_role(text).role


# --- plain statements -----------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "اهدا کننده کلیه هستم",  # "I am a kidney donor"
        "اهداکننده سالم ۲۸ ساله",  # "healthy donor, 28"
        "Donor, blood group O+",
    ],
)
def test_a_donor_statement_reads_as_donor(text: str) -> None:
    assert role_of(text) is Role.DONOR


@pytest.mark.parametrize(
    "text",
    [
        "گیرنده کلیه",  # "kidney recipient"
        "کاندید پیوند کلیه",  # "candidate for a kidney transplant"
        "Recipient waiting for transplant",
    ],
)
def test_a_recipient_statement_reads_as_recipient(text: str) -> None:
    assert role_of(text) is Role.RECIPIENT


def test_a_caption_with_no_role_word_says_nothing() -> None:
    claim = read_caption_role("گروه خونی O مثبت، تهران")
    assert claim.role is Role.UNKNOWN
    assert claim.tier is CaptionTier.NONE


def test_an_empty_caption_says_nothing() -> None:
    assert role_of("") is Role.UNKNOWN
    assert role_of("   ") is Role.UNKNOWN


# --- the inversion trap ---------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "اهدا کننده نیاز دارم",  # "I need a donor" — written by a RECIPIENT
        "به اهداکننده نیازمندیم",  # "we need a donor"
        "دنبال اهدا کننده کلیه میگردم",  # "I am looking for a kidney donor"
        "Looking for a donor urgently",
        "donor needed, blood group A",
    ],
)
def test_a_request_for_a_donor_is_refused_not_read_as_donor(text: str) -> None:
    """The word is "donor" and the writer is a recipient.

    Guessing the inversion would put a recipient's report in the donor pool,
    which is the single most damaging error this field can make. Refusing costs
    a review item; guessing costs a wrong match.
    """
    claim = read_caption_role(text)
    assert claim.role is Role.UNKNOWN
    assert claim.tier is CaptionTier.REFUSED
    assert "request" in claim.reason


@pytest.mark.parametrize(
    "text",
    [
        "گیرنده نیاز دارد",  # "needs a recipient"
        "Looking for a recipient",
    ],
)
def test_a_request_for_a_recipient_is_refused_too(text: str) -> None:
    assert read_caption_role(text).tier is CaptionTier.REFUSED


def test_both_roles_in_one_caption_is_refused() -> None:
    """A broker listing both sides in one post. Neither reading is safe."""
    claim = read_caption_role("اهدا کننده و گیرنده هر دو موجود است")
    assert claim.role is Role.UNKNOWN
    assert claim.tier is CaptionTier.REFUSED
    assert "both" in claim.reason


# --- what a claim carries -------------------------------------------------


def test_a_claim_records_which_phrase_produced_it() -> None:
    """Provenance: a role that cannot say what it was read from cannot be
    audited when it turns out to be wrong."""
    claim = read_caption_role("اهدا کننده کلیه هستم")
    assert claim.matched
    assert claim.tier is CaptionTier.STATEMENT


def test_a_caption_claim_is_never_marked_resolved() -> None:
    """It is evidence for `decide_document_role` to weigh, and that function
    alone decides. A claim that could call itself resolved would let the
    poster's opinion outrank the laboratory's own form."""
    fields = set(type(read_caption_role("Donor")).__dataclass_fields__)
    assert "resolved" not in fields
    assert "status" not in fields


def test_the_reader_never_looks_at_a_phone_number_or_a_price() -> None:
    """Compensation and contact details are separate domains, and the matching
    rules forbid reading compensation at all."""
    import inspect

    from kidneymatch.documents import caption

    source = inspect.getsource(caption)
    for forbidden in ("price", "toman", "rial", "قیمت", "تومان", "phone"):
        assert forbidden not in source.lower()


# --- spellings measured in the archive that the reader used to miss ---------
# 179 documents with no role carry one of these and nothing that contradicts
# it. The operator: "whenever you see something like اهدا کننده this means
# donner and whenever you see گیرنده or any other variations you should
# extract that the role is reciever."


@pytest.mark.parametrize(
    "text",
    [
        "اهدای کننده کلیه هستم",  # the ezafe ی between the two halves
        "اهداء کننده",  # the hamza spelling
        "اهدا کننده کلیه",
        "دهنده کلیه سالم",
        "دهنده هستم",  # `دهنده` alone: only `دهنده کلیه` matched
        "I want to donate my kidney",
    ],
)
def test_a_donor_says_so_in_more_than_one_spelling(text: str) -> None:
    assert read_caption_role(text).role is Role.DONOR


@pytest.mark.parametrize(
    "text",
    [
        "گیرنده کلیه",
        "گيرنده",  # Arabic yeh, normalised to Persian
        "کاندید پیوند کلیه",
        "کاندد پیوند",  # the recognizer's and the typist's slip
        "دریافت کننده",
    ],
)
def test_a_recipient_says_so_in_more_than_one_spelling(text: str) -> None:
    assert read_caption_role(text).role is Role.RECIPIENT


def test_kidney_donation_as_a_topic_is_not_a_person() -> None:
    """`اهدا کلیه` names an activity and rides in the group's own
    boilerplate. 93 documents carry it, and reading it as a role would be a
    guess about whose report the photograph is."""
    assert read_caption_role("اهدا کلیه").role is Role.UNKNOWN


def test_a_request_still_refuses_every_new_spelling() -> None:
    """Widening the vocabulary must not widen what is ASSERTED. "I need a
    kidney donor" names a donor and describes a recipient, and the reader's
    job is to notice that, not to resolve it."""
    for text in ("دهنده کلیه نیاز دارم", "دنبال اهدای کننده هستم", "looking for a donor"):
        claim = read_caption_role(text)
        assert claim.role is Role.UNKNOWN, text


def test_both_roles_in_one_caption_is_still_unreadable() -> None:
    assert read_caption_role("اهدای کننده و گیرنده").role is Role.UNKNOWN


# --- D1-b: a request elsewhere in the message does not veto a statement ------


def test_a_statement_stands_when_another_clause_asks_for_something() -> None:
    """ "My group is O+, looking for a donor" states O+; the request is about
    a donor, not about the group. It used to be refused as a request for O+."""
    from kidneymatch.documents.caption import CaptionTier, read_caption_abo

    claim = read_caption_abo("گروه خونی من O+ است، دنبال اهدا کننده هستم")
    assert claim.tier is CaptionTier.STATEMENT
    assert claim.group == "O"
    assert claim.rh == "POSITIVE"


def test_a_request_that_names_the_group_is_still_refused() -> None:
    """ "I need O+" describes someone else; the request word sits beside the group."""
    from kidneymatch.documents.caption import CaptionTier, read_caption_abo

    claim = read_caption_abo("نیازمند گروه خونی O+ هستم")
    assert claim.tier is CaptionTier.REFUSED
