"""Read ABO and Rh off the form, and reconcile them with the caption's claim.

Two measured findings shape every rule here.

**An ABO-shaped box is not a blood group.** `A+` and `O-` occur throughout these
pages — in serology tables, in footnotes, in advertisement text burned into the
image. A token is a blood group only when it sits in a cell located by a printed
field label. Shape alone may raise a review item; it may never produce a value.
Measured, 726 documents have an anchored cell that is empty while an ABO-shaped
box sits elsewhere on the page.

**On the dominant letterhead the printed blood group is patient-reported.** The
form prints, as boilerplate, "information regarding the blood group is based on
the attendee's own account, and the laboratory bears no responsibility for its
accuracy" — 2,928 documents, 97.7% of them carrying the Yekta marker. A value
from such a form is not a laboratory measurement, and its agreement with the
caption is not independent corroboration, because both claims can descend from
the same person's statement. `MATCH-ABO-001` must not treat it as a verified
blood group.

**Direction follows the script.** A Persian label's value sits to its LEFT; an
English label's to its RIGHT. Reading the wrong way crosses into another cell.
The blood group itself is written in Latin characters on a Persian form, so a
Persian-pass anchor routinely addresses a Latin-pass value box; both passes
store normalised coordinates in the same frame, which is what makes that legal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from kidneymatch.documents.role import normalise
from kidneymatch.ocr.anchors import Box


class AboStatus(StrEnum):
    RESOLVED = "RESOLVED"
    UNKNOWN = "UNKNOWN"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    CONFLICT = "CONFLICT"


class Rh(StrEnum):
    """Rh is a separate field with its own state.

    It is never synthesised, never defaulted to the population mode, and never
    copied from the caption into the image's claim.
    """

    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    UNKNOWN = "UNKNOWN"


class AboSource(StrEnum):
    LABORATORY_PRINTED = "LABORATORY_PRINTED"
    PATIENT_REPORTED_ON_FORM = "PATIENT_REPORTED_ON_FORM"
    CAPTION_CLAIM = "CAPTION_CLAIM"
    NONE = "NONE"


# Case-sensitive. `D` is the Rh(D) antigen rather than a blood group, and lower
# case is not this form's typography; 49 such boxes exist corpus-wide.
_VALUE_FORWARD = re.compile(r"^(AB|A|B|O|0)\s*([+\-])$")
_VALUE_REVERSED = re.compile(r"^([+\-])\s*(AB|A|B|O|0)$")  # right-to-left rendering
_LETTER_ONLY = re.compile(r"^(AB|A|B|O|0)$")
_SIGN_ONLY = re.compile(r"^[+\-]$")

# The footnote contains the same words as the field label, so it must be
# excluded or it anchors a cell over the page furniture beside it.
_DISCLAIMER = re.compile(r"براساس|بر اساس|شرح|مسئول|اطلاعات|آزمایشگاه|ازمایشگاه")
_KHOON = re.compile(r"^[خح]و?[نی]{1,2}ی?$")
_GROOH = re.compile(r"^[گک]رو[هه]$")

# `groups?` used to be accepted bare. The methods footnote on these forms reads
# "... alleles or groups of alleles ... PCR-SSP ...", which anchored a cell on
# 576 documents and resolved two of them. A field label carries punctuation or
# the word `Blood`; the prose plural never does.
_LABEL_LATIN = re.compile(
    r"(?i)^(?:b[l1i][o0]{1,2}d\s*gr[o0]up|b[l1i][o0]{1,2}d\s*type"
    r"|ab[o0]|ab[o0]/rh|b\.?\s?g\.?|rh|rhd)\s*[:;.\-/&]*$"
)
# A bare `Group` is a label only with punctuation, or with `Blood` to its left.
_LABEL_GROUP_WORD = re.compile(r"(?i)^gr[o0]up(?P<punctuation>\s*[:;.\-/&]+)?$")
_BLOOD_WORD = re.compile(r"(?i)^b[l1i][o0]{1,2}d[:;.\-/&]*$")

_MAX_LABEL_CHARS = 25
_MAX_GAP = 10.0  # anchor heights; measured p99 of the real gap is 9.36
_OVERLAP = 0.35
_SLACK = 0.30


def _is_persian_label(text: str) -> bool:
    normalised = normalise(text)
    if not normalised or len(normalised) > _MAX_LABEL_CHARS:
        return False  # a label is short; the disclaimer sentence is prose
    if _DISCLAIMER.search(normalised):
        return False
    words = [w for w in re.split(r"[\s:;.,()،؛]+", normalised) if w]
    if any(_KHOON.match(w) for w in words):
        return True
    return any(_GROOH.match(w) for w in words) and any(w[:1] in "خح" for w in words)


def _has_blood_word(text: str) -> bool:
    return any(_KHOON.match(w) for w in re.split(r"[\s:;.,()،؛]+", text) if w)


def has_printed_disclaimer(persian_boxes: list[Box]) -> bool:
    """Does this form disclaim its own blood-group field?

    The sentence is long and the recognizer splits it across boxes, so the
    disclaimer word and the blood word are often in different ones. Requiring
    both in a SINGLE box missed at least 27.5% of the Yekta pages that show the
    disclaimer, and 120 resolved readings were consequently labelled as
    laboratory measurements when the form disclaims them.
    """
    marked = [b for b in persian_boxes if _DISCLAIMER.search(normalise(b.text))]
    for b in marked:
        if _has_blood_word(normalise(b.text)):
            return True
        # Same printed line, wrapped into another box.
        for other in persian_boxes:
            if other is b:
                continue
            overlap = min(b.y1, other.y1) - max(b.y0, other.y0)
            shorter = min(b.height, max(other.y1 - other.y0, 1e-6))
            if overlap / shorter >= _OVERLAP and _has_blood_word(normalise(other.text)):
                return True
    return False


@dataclass(frozen=True, slots=True)
class AboReading:
    """What the form itself says, with provenance."""

    status: AboStatus
    group: str | None = None
    rh: Rh = Rh.UNKNOWN
    source: AboSource = AboSource.NONE
    anchor_box: Box | None = None
    value_box: Box | None = None
    raw_value: str | None = None
    repaired: bool = False
    reason: str = ""


@dataclass(frozen=True, slots=True)
class AboDecision:
    """The document-level outcome after the caption has been weighed."""

    status: AboStatus
    group: str | None
    rh: Rh
    source: AboSource
    agreed: bool = False
    independently_corroborated: bool = False
    subject_identity_questioned: bool = False
    reason: str = ""

    @property
    def is_verified(self) -> bool:
        """Never true here. Verification is a laboratory act, not a reading."""
        return False


def _is_group_word_label(box: Box, latin_boxes: list[Box]) -> bool:
    """A bare `Group` token: a field label, or the middle of a sentence?"""
    match = _LABEL_GROUP_WORD.match((box.text or "").strip())
    if not match:
        return False
    if match.group("punctuation"):
        return True
    left = sorted(
        (
            o
            for o in latin_boxes
            if o is not box and o.x1 <= box.x0 and (min(box.y1, o.y1) - max(box.y0, o.y0)) > 0
        ),
        key=lambda o: -o.x1,
    )
    return bool(left) and bool(_BLOOD_WORD.match((left[0].text or "").strip()))


def _parse(token: str) -> tuple[str, Rh, bool] | None:
    match = _VALUE_FORWARD.match(token)
    if match:
        letter, sign = match.group(1), match.group(2)
    else:
        match = _VALUE_REVERSED.match(token)
        if not match:
            return None
        sign, letter = match.group(1), match.group(2)
    # The only site where a digit zero becomes the letter O. The token has
    # already matched the full grammar inside an identified cell, so there is
    # no other reading available.
    return (
        "O" if letter == "0" else letter,
        Rh.POSITIVE if sign == "+" else Rh.NEGATIVE,
        letter == "0",
    )


def _cell(anchor: Box, boxes: list[Box], rightwards: bool) -> list[Box]:
    height = anchor.height
    slack = _SLACK * height
    limit = _MAX_GAP * height
    out = []
    for b in boxes:
        if b is anchor:
            continue
        overlap = min(anchor.y1, b.y1) - max(anchor.y0, b.y0)
        if overlap <= _OVERLAP * min(height, max(b.y1 - b.y0, 1e-6)):
            continue
        if rightwards:
            if b.x0 >= anchor.x1 - slack and (b.x0 - anchor.x1) <= limit:
                out.append(b)
        elif b.x1 <= anchor.x0 + slack and (anchor.x0 - b.x1) <= limit:
            out.append(b)
        elif b.x0 >= anchor.x0 - slack and b.x1 <= anchor.x1 + slack:
            # Persian is detected at line level, so the line box sometimes
            # swallows the Latin value that sits inside it.
            out.append(b)
    return out


def read_abo(persian_boxes: list[Box], latin_boxes: list[Box]) -> AboReading:
    """Read the blood group from its printed cell, or abstain."""
    everything = list(persian_boxes) + list(latin_boxes)
    anchors = [(b, False) for b in persian_boxes if _is_persian_label(b.text)]
    anchors += [
        (b, True)
        for b in latin_boxes
        if _LABEL_LATIN.match((b.text or "").strip()) or _is_group_word_label(b, latin_boxes)
    ]

    if not anchors:
        return AboReading(AboStatus.UNKNOWN, reason="no blood-group field label on this document")

    source = (
        AboSource.PATIENT_REPORTED_ON_FORM
        if has_printed_disclaimer(persian_boxes)
        else AboSource.LABORATORY_PRINTED
    )

    found: list[tuple[str, Rh, bool, Box, Box, str]] = []
    partial = ""
    for anchor, rightwards in anchors:
        cell = _cell(anchor, everything, rightwards)
        values = []
        for b in cell:
            token = (b.text or "").strip()
            parsed = _parse(token)
            if parsed:
                values.append((parsed, b, token))
        if len(values) > 1:
            return AboReading(
                AboStatus.REVIEW_REQUIRED,
                source=source,
                anchor_box=anchor,
                reason="more than one blood-group value in a single cell",
            )
        if values:
            (group, rh, repaired), vbox, raw = values[0]
            found.append((group, rh, repaired, anchor, vbox, raw))
            continue
        texts = [(b.text or "").strip() for b in cell]
        if any(_LETTER_ONLY.match(t) for t in texts) and any(_SIGN_ONLY.match(t) for t in texts):
            # 33 documents. Joining them could pair a letter with a sign that
            # belongs to a different field.
            partial = partial or "the group letter and the Rh sign are in separate boxes"
        elif any(_LETTER_ONLY.match(t) for t in texts):
            partial = partial or "a group letter with no Rh sign in its cell"
        elif any(_SIGN_ONLY.match(t) for t in texts):
            partial = partial or "an Rh sign with no group letter in its cell"

    distinct = {(g, rh) for g, rh, _, _, _, _ in found}
    if len(distinct) > 1:
        return AboReading(
            AboStatus.REVIEW_REQUIRED, source=source, reason="two cells report different groups"
        )
    if found:
        group, rh, repaired, anchor, vbox, raw = found[0]
        return AboReading(
            AboStatus.RESOLVED,
            group=group,
            rh=rh,
            source=source,
            anchor_box=anchor,
            value_box=vbox,
            raw_value=raw,
            repaired=repaired,
        )
    return AboReading(
        AboStatus.REVIEW_REQUIRED,
        source=source,
        anchor_box=anchors[0][0],
        reason=partial or "the blood-group field is printed but its cell could not be read",
    )


def reconcile_abo(
    image: AboReading, caption_claims: set[tuple[str, Rh]] | None = None
) -> AboDecision:
    """Weigh the image's claim against the caption's. Neither overwrites the other.

    They are separate facts about possibly different people: 37% of messages
    are forwards and brokers post other people's reports. A disagreement is
    therefore evidence about the LINK between the message and the document, not
    only about the blood group.
    """
    claims = caption_claims or set()
    single = next(iter(claims)) if len(claims) == 1 else None

    if image.status is AboStatus.RESOLVED and image.group:
        # A caption that gives the letter without the sign is the same claim at
        # lower precision, not a different blood group. Treating it as a
        # conflict raised the identity flag on captions that merely omitted the
        # Rh, which is most of them.
        contradicts = single is not None and (
            single[0] != image.group or (single[1] is not Rh.UNKNOWN and single[1] is not image.rh)
        )
        if contradicts:
            # Most plausibly the caption describes a different person. That
            # invalidates it as evidence for every field it carries — role,
            # name, contact — until a human resolves it.
            return AboDecision(
                AboStatus.CONFLICT,
                None,
                Rh.UNKNOWN,
                image.source,
                subject_identity_questioned=True,
                reason="the caption states a different blood group from the form",
            )
        agreed = single is not None and single[0] == image.group and single[1] is image.rh
        return AboDecision(
            AboStatus.RESOLVED,
            image.group,
            image.rh,
            image.source,
            agreed=agreed,
            # Agreement corroborates only if the two claims are independent.
            # Where the form disclaims its own field, they may not be.
            independently_corroborated=(
                agreed and image.source is not AboSource.PATIENT_REPORTED_ON_FORM
            ),
        )

    if single:
        return AboDecision(
            AboStatus.RESOLVED,
            single[0],
            single[1],
            AboSource.CAPTION_CLAIM,
            reason="claimed by the poster; not read from any document",
        )
    if image.status is AboStatus.REVIEW_REQUIRED:
        return AboDecision(
            AboStatus.REVIEW_REQUIRED, None, Rh.UNKNOWN, image.source, reason=image.reason
        )
    return AboDecision(AboStatus.UNKNOWN, None, Rh.UNKNOWN, AboSource.NONE)
