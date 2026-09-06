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
CAPTION_ABO_VERSION = "caption-abo/v1"


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
# Measured on the archive: 179 documents with no role at all carry one of these
# spellings and nothing that contradicts it. `normalise` has already folded the
# Arabic yeh and kaf and stripped the zero-width non-joiner, so `گيرنده` and
# `اهدا‌کننده` arrive in one shape; what these add is the ezafe `ی`, the
# hamza, and `دهنده` standing on its own rather than only before `کلیه`.
#
# `اهدا کلیه` — "kidney donation" — is deliberately NOT here. It names an
# activity, not a person, and it rides in the group's own boilerplate; 93
# documents carry it, and reading it as "this person is a donor" would be a
# guess about whose report the photograph is.
_DONOR_WORD = re.compile(
    r"اهدا[ءیه]?\s?کننده|اهداکننده"
    r"|(?<![\u0600-\u06FF])دهنده"
    r"|\bdonor\b|\bdonat(?:e|es|ed|ing|ion)\b",
    re.IGNORECASE,
)
_RECIPIENT_WORD = re.compile(
    r"گیرنده|دریافت\s?کننده|کاند[یب]?د\s?پ[یب]?وند|بیمار\s?کلیوی|\brecipient\b",
    re.IGNORECASE,
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


# --- the blood group a caption states -----------------------------------------
#
# The reviewer: "Usually the role and the blood type will be present in the
# chat." They are, and the archive is 87% short of a laboratory-printed blood
# group (2,995 documents of 23,566), so the caption is the only place the rest
# of it exists.
#
# Two hazards govern this reader, and both come from the corpus rather than from
# caution in the abstract.
#
# **`A` and `B` are HLA loci.** Every caption here sits beside an HLA report, so
# a bare letter is the commonest token in the archive and means a gene far more
# often than a blood group. A letter alone therefore never states a group: it
# needs its own Rh sign (`A+`) or a blood-group word beside it.
#
# **A caption states as often what is WANTED as what is had** — the same
# inversion `read_caption_role` exists for. "گروه خونی A مثبت نیاز دارم" is a
# request from someone who is not group A. `_REQUEST` already knows those words,
# and a request refuses the reading rather than reversing it.

_BLOOD_GROUP_WORD = re.compile(
    r"گروه\s?خون[یي]?|گروه\s?خونی|\bblood\s*(?:group|type)\b|\bbg\b", re.IGNORECASE
)
# A group with its own sign: unambiguous enough to stand without a blood word.
# Not followed by a letter or digit, so `A+B` (both of two things) is not a group
# and `B+12` is not either.
_GROUP_SIGNED = re.compile(r"(?<![A-Za-z0-9])(AB|A|B|O)\s*([+\-])(?![A-Za-z0-9+\-])")
# A group beside a blood-group word, where the sign may be a Persian word.
_GROUP_BARE = re.compile(r"(?<![A-Za-z0-9])(AB|A|B|O)(?![A-Za-z0-9*])")
_POSITIVE_WORD = re.compile(r"مثبت|\bpos(?:itive)?\b", re.IGNORECASE)
_NEGATIVE_WORD = re.compile(r"منفی|منفي|\bneg(?:ative)?\b", re.IGNORECASE)
# How far from the blood-group word an unsigned letter may sit and still be its
# value. A caption is one line of shorthand; beyond this it is another sentence.
_NEAR_CHARS = 24


@dataclass(frozen=True, slots=True)
class CaptionAbo:
    """What the caption says about the blood group. Never a laboratory finding."""

    group: str | None
    rh: str  # "POSITIVE", "NEGATIVE" or "UNKNOWN"
    tier: CaptionTier
    matched: str = ""
    reason: str = ""


def _rh_from(text: str) -> str:
    positive, negative = _POSITIVE_WORD.search(text), _NEGATIVE_WORD.search(text)
    if positive and not negative:
        return "POSITIVE"
    if negative and not positive:
        return "NEGATIVE"
    return "UNKNOWN"


def read_caption_abo(text: str) -> CaptionAbo:
    """Read a blood group from a caption, or refuse.

    Refusal is the common answer, as it is for the role: a message naming two
    groups is a broker advertising two people, and a message asking for a group
    says nothing about the person whose report it carries.
    """
    if not text or not text.strip():
        return CaptionAbo(None, "UNKNOWN", CaptionTier.NONE)
    cleaned = normalise(text)

    found: list[tuple[str, str, str]] = []  # (group, rh, matched)
    for match in _GROUP_SIGNED.finditer(cleaned):
        group = "O" if match.group(1) == "0" else match.group(1)
        found.append((group, "POSITIVE" if match.group(2) == "+" else "NEGATIVE", match.group(0)))
    for word in _BLOOD_GROUP_WORD.finditer(cleaned):
        window = cleaned[word.end() : word.end() + _NEAR_CHARS]
        letter = _GROUP_BARE.search(window)
        if letter is None:
            continue
        signed = _GROUP_SIGNED.search(cleaned[word.end() : word.end() + _NEAR_CHARS])
        if signed is not None:
            continue  # already counted above, with its sign
        found.append((letter.group(1), _rh_from(window), word.group(0) + letter.group(0)))

    if not found:
        return CaptionAbo(None, "UNKNOWN", CaptionTier.NONE)
    groups = {group for group, _, _ in found}
    if len(groups) > 1:
        return CaptionAbo(
            None,
            "UNKNOWN",
            CaptionTier.REFUSED,
            reason=(
                "the caption names more than one blood group, so it describes more than one person"
            ),
        )
    rhs = {rh for _, rh, _ in found if rh != "UNKNOWN"}
    if len(rhs) > 1:
        return CaptionAbo(
            None,
            "UNKNOWN",
            CaptionTier.REFUSED,
            reason="the caption gives one group with both Rh signs",
        )
    if _REQUEST.search(cleaned):
        return CaptionAbo(
            None,
            "UNKNOWN",
            CaptionTier.REFUSED,
            matched=found[0][2],
            reason=(
                "the caption reads as a request for that blood group, not a statement of "
                "one, and a request describes someone else"
            ),
        )
    return CaptionAbo(
        next(iter(groups)),
        next(iter(rhs), "UNKNOWN"),
        CaptionTier.STATEMENT,
        matched=found[0][2],
    )
