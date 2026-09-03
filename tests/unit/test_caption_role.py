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
