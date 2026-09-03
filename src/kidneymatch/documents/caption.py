"""What the message a photograph was posted with claims about its subject.

A caption is written by whoever posted the image, and in this archive that is
very often a broker rather than the patient. So a caption is *evidence*, never a
conclusion: `decide_document_role` weighs it, the printed form field outranks
it, and it can veto a weak reading but never rename the person on the page.

## The inversion that governs the design

The same word carries both roles depending on one verb:

* «اهدا کننده هستم» — "I am a donor" → the subject is a **donor**.
* «اهدا کننده نیاز دارم» — "I need a donor" → the writer is a **recipient**,
  and the word "donor" refers to someone they are looking for.

Reading the second as a donor claim would file a recipient's laboratory report
in the donor pool, which is the most damaging error this field can make. Intent
cannot be parsed reliably from a market's shorthand, so **any caption that looks
like a request is refused**. A refusal costs one review item; a guess costs a
wrong match.

The same applies to a caption naming both roles: a broker advertising both sides
in one post supports neither reading.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from kidneymatch.documents.role import Role, normalise

CAPTION_READER_VERSION = "caption-role/v1"


class CaptionTier(StrEnum):
    """Why the reader answered as it did."""

    STATEMENT = "STATEMENT"
    REFUSED = "REFUSED"
    NONE = "NONE"


@dataclass(frozen=True, slots=True)
class CaptionClaim:
    """What the caption says. Deliberately unable to call itself resolved."""

    role: Role
    tier: CaptionTier
    matched: str = ""
    reason: str = ""


# Role words, in the spellings a person types rather than the ones OCR produces.
# `role.py`'s patterns are tuned for a recognizer's misreadings of a printed
# form; a caption is typed, so these are separate and simpler on purpose.
_DONOR_WORD = re.compile(r"اهدا\s?کننده|اهداکننده|دهنده\s?کلیه|\bdonor\b", re.IGNORECASE)
_RECIPIENT_WORD = re.compile(
    r"گیرنده|دریافت\s?کننده|کاندید\s?پیوند|بیمار\s?کلیوی|\brecipient\b", re.IGNORECASE
)

# Words that turn a role word into a request for that role. Anything here makes
# the caption unreadable rather than readable-in-reverse: the reader's job is to
# notice the ambiguity, not to resolve it.
_REQUEST = re.compile(
    r"نیاز|نیازمند|لازم\s?دار|میخوا|می\s?خوا|دنبال|جویا|طالب|احتیاج|میگرد|می\s?گرد"
    r"|\bneed(?:ed|s|ing)?\b|\blooking\s+for\b|\bwanted\b|\bsearch(?:ing)?\s+for\b"
    r"|\brequire[ds]?\b",
    re.IGNORECASE,
)


def read_caption_role(text: str) -> CaptionClaim:
    """Read a role claim, or refuse.

    Refusal is the common answer by design. This archive's captions are
    advertisements, and an advertisement naming a role is as often a request for
    it as a statement of it.
    """
    if not text or not text.strip():
        return CaptionClaim(Role.UNKNOWN, CaptionTier.NONE)

    cleaned = normalise(text)
    donor = _DONOR_WORD.search(cleaned)
    recipient = _RECIPIENT_WORD.search(cleaned)

    if donor and recipient:
        return CaptionClaim(
            Role.UNKNOWN,
            CaptionTier.REFUSED,
            reason="the caption names both roles, so neither reading is supported",
        )
    if not donor and not recipient:
        return CaptionClaim(Role.UNKNOWN, CaptionTier.NONE)

    found = donor if donor is not None else recipient
    assert found is not None  # one of them matched, or we returned NONE above

    if _REQUEST.search(cleaned):
        return CaptionClaim(
            Role.UNKNOWN,
            CaptionTier.REFUSED,
            matched=found.group(0),
            reason=(
                "the caption reads as a request for that role, not a statement of it, "
                "and a request inverts the subject"
            ),
        )

    role = Role.DONOR if donor is not None else Role.RECIPIENT
    return CaptionClaim(role, CaptionTier.STATEMENT, matched=found.group(0))
