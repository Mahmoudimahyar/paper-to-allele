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

**The cell is not the label's box.** The window was a LINE — 35% of the shorter
box's height had to overlap the label's — and the two engines do not draw their
rectangles on the same line, so a value can be the only thing in the label's
printed cell and still be refused. Two rescues now cover that, and they rest on
different evidence, which is why they are marked differently (`AboRescue`).

Every count below is a READING count from `scripts/abo_window_check.py` over
23,485 documents in the raw frame — what `read_abo` returns, not what the
pipeline publishes. The two are not the same, and the difference is the whole
point of `reconcile_abo`, so the published counts are given beside them.

* **BAND** — on a page that rules a grid, the row between two rulings IS the
  cell. 42 documents gain a reading. A band-only reading is NOT published on
  its own word: it needs two engines over the same ink, or a caption naming the
  same letter, and otherwise goes to a person carrying its candidate box.
  Once both repasses have run the live store holds 42 rows marked BAND — 29
  published (13 of them new, 12 of them rows a caption alone had answered and
  the form is now credited for) and 13 review items with a crop. The band says
  which CELL the token is in and nothing more, so a partial already printed in
  that cell — a lone `-` against a rescued `+` — refuses it, exactly as on the
  centre route;
* **CENTRE** — on a page that rules nothing, only distance and direction place
  the value, so the reach is 0.75 label heights ABOVE the label's centre and
  six gates stand in front of it. 51 documents gain a reading; the live store
  holds 38 rows marked CENTRE, 31 of them newly published. NO PERSON HAS
  CHECKED ONE OF THESE; the `abo_centre_rescue` review stratum exists to get
  twenty of them read, and until that happens HA-019 blocks resting a match on
  one.

A page carries a route only when the box the value is READ FROM was admitted by
it. A page whose published box passed the line test is not marked even when the
other engine's box needed rescuing: nothing about that page changed, and
marking it would put it in the withdrawal group and in a reviewer's queue for
no reason.

Both cost one document: a cell whose sign the pipeline publishes today on one
engine's word, with the other engine's box a third of a line away saying the
opposite. That page now goes to a person, which is the correct answer and a
worse yield number.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from enum import StrEnum

from kidneymatch.documents.role import normalise
from kidneymatch.ocr.anchors import Box
from kidneymatch.ocr.lattice import Lattice, RowBand


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


class AboRescue(StrEnum):
    """How a value box entered the cell when it missed the label's own line.

    `BAND` is the label's printed row: where the page rules a grid, the space
    between two rulings IS the cell, and a value inside it belongs to the label
    inside it. `CENTRE` is a page that rules nothing, where only distance and
    direction place the value; it carries six admission gates and NO HUMAN HAS
    EVER CHECKED ONE OF ITS READINGS, which is what the `abo_centre_rescue`
    review stratum exists to fix.

    The route is set from the box the value is READ FROM, and it travels into
    the fact row's `rule_id` (`rule_id_for`). That string is the only handle
    the group has once the row is written, so a pass that publishes one of
    these and does not write it puts a value beyond withdrawal.
    """

    BAND = "BAND"
    CENTRE = "CENTRE"


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
# The recognizer's damaged spellings of the same two words. Neither may anchor
# ALONE — `کرده` ("done") matches the wide group pattern and appears in prose on
# 364 of these pages. What licenses them is ADJACENCY: the group word
# immediately followed by the blood word, inside one box, reconstructs the
# printed phrase `گروه خونی`. Measured (CV_RESEARCH s16): 194 net new blood
# groups; 0 contradictions against 80 independent chat claims; 15/15 identical
# to the strict reading on pages both anchor; a size-matched non-label decoy
# used as the anchor returns a value on 1 of 275.
_GROOH_WIDE = re.compile(r"^[گکذ]ر[ودرء]?[هءا0]$")
_KHOON_WIDE = re.compile(r"^[خحغ][ودر]?[نیلفتثز]{1,2}[یرم]?$")

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

# How much two boxes must overlap to be one printed token rather than two
# values. Measured on the 996 collapsible cells, every pair clears 0.5 but one.
_MIN_IOU = 0.5
_MAX_LABEL_CHARS = 25
_MAX_GAP = 10.0  # anchor heights; measured p99 of the real gap is 9.36
_OVERLAP = 0.35
_SLACK = 0.30

# --- the cell window (CV_RESEARCH s19 item 1) -------------------------------
#
# `_OVERLAP` is a test against the label's LINE, and the two recognizers do not
# draw their rectangles on the same line: a Persian line box runs below its
# baseline while the Latin capitals sit above it, so a value can share less
# than a third of its height with its own label and still be the only thing in
# the label's printed cell. Measured over 23,485 documents in the raw frame,
# that costs 42 readings on ruled pages and a further 51 on unruled ones. (The
# route-ONLY variants measured 43 and 82; the shipped rule consults the ruled
# row FIRST, so a page with a usable band never reaches the centre branch and
# the two numbers do not add up to the combined one.)
#
# A band taller than this spans two printed rows and locates no cell. The cap
# is NOT a collision-free boundary: the nearest observed same-ink cross-engine
# SIGN disagreement sits in a band 2.08 anchor heights tall — 0.08h outside,
# about 1.6 px at the median 20 px label. 2.0 was chosen as the loosest setting
# that lost nothing, which is a fitted constant, not a measured margin. That is
# why a band-only reading has to be corroborated before it is published.
#
# It is also why the translated-anchor placebo says nothing about this route
# below 2.0h: a label moved 1.0h is still inside its own printed row, and a
# rule whose cell IS the row must find the same cell there. Measured, the
# +-1.0h shifts cost +202 and +10 extra admissions against a +2 allowance,
# while +-1.5h, +-2.0h and +-3.0h cost +1, 0 and +1. The gate that fails there
# is recorded and decided in HA-019, not redefined in the harness.
_MAX_BAND_HEIGHTS = 2.0
# How far along its own row a value may sit from the label's centre.
_ROW_REACH = 1.0
# With no ruled row, how far ABOVE the label's centre a value may sit. Boxes of
# equal height that fail the line test are already 0.65 heights apart, so this
# opens the window (0.65h, 0.75h]. Measured over 23,485 documents, widening it
# to 1.0h reads 121 documents instead of 93 — 28 further centre admissions —
# and the translated-anchor placebo sees it: the +1.0h reach goes from +10 to
# +24 and a second +1.5h leak appears. The yield is bought with reach the
# control can detect, which is why the reach stops here. Values sit above their
# label in 94-96% of resolved cells, and every below-centre rescue in the
# corpus was a ruling-crossing or a partial contradiction.
_RESCUE_BAND = 0.75
# The reach is a fraction of the ANCHOR's height, so an over-large label box
# buys itself a longer arm. Measured against the page's PERSIAN median: a
# shipped Persian label runs 1.6x the Latin median, which would refuse ordinary
# labels. Refuses 4 of 99, including line boxes at 4.9x and 5.0x.
_MAX_ANCHOR_SCALE = 1.5
# How much better aligned a competing label must be to own the token when it is
# no nearer to it than the anchor is.
_ALIGNMENT_TIE_BREAK = 0.25

BAND_RESCUE_REASON = "the value sits on the label's own ruled row rather than on its line"
CENTRE_RESCUE_REASON = (
    "the value box was admitted by the 0.75 label-height centre band; this page rules no row "
    "around the field"
)
UNCORROBORATED_RESCUE_REASON = (
    "a value sits on the label's ruled row but not on its line; one engine read it and nothing "
    "corroborates it"
)


def _measured(reason: str, band_heights: float | None, engines: int) -> str:
    """The reason with the two measurements a reviewer needs to judge it.

    A ruled-row reason that does not say how tall the row was, or how many
    engines boxed the value, tells a reviewer nothing about how far the rule
    reached or what stood behind the reading. Both are what the admission
    actually turned on, so both are written next to it (s19 item 1, F3).
    """
    parts = []
    if band_heights is not None:
        parts.append(f"the row is {band_heights:.2f} anchor heights tall")
    if engines:
        parts.append(f"{engines} engine{'s' if engines != 1 else ''} boxed the value")
    return f"{reason} ({'; '.join(parts)})" if parts else reason


def _is_persian_label(text: str) -> bool:
    normalised = normalise(text)
    if not normalised or len(normalised) > _MAX_LABEL_CHARS:
        return False  # a label is short; the disclaimer sentence is prose
    if _DISCLAIMER.search(normalised):
        return False
    words = [w for w in re.split(r"[\s:;.,()،؛]+", normalised) if w]
    if any(_KHOON.match(w) for w in words):
        return True
    if any(_GROOH.match(w) for w in words) and any(w[:1] in "خح" for w in words):
        return True
    # The pair route: a damaged group word directly followed by a damaged blood
    # word. Either half alone is refused above and stays refused here.
    return any(
        (_GROOH.match(a) or _GROOH_WIDE.match(a)) and _KHOON_WIDE.match(b)
        for a, b in zip(words, words[1:], strict=False)
    )


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
    # Every box the value was read from. Normally one; two when a single
    # printed token was detected by both engines and they agreed.
    value_boxes: tuple[Box, ...] = ()
    raw_value: str | None = None
    repaired: bool = False
    # Set when the PUBLISHED value box missed the label's own line and was
    # admitted by the ruled row or the centre band instead. It travels into the
    # fact row's `rule_id` so the group can be found, sampled and withdrawn.
    # A page whose published box passed the line test is NOT marked, even when
    # the other engine's box needed rescuing: the value is one the strict window
    # already reads, and marking it would put a page no rule changed into the
    # withdrawal group and into the review stratum.
    rescued: AboRescue | None = None
    # How tall the label's ruled row was, in anchor heights, when the band
    # admitted the value; None on every other route. How many engines boxed the
    # published value. Both are written into the reason, because they are what
    # the admission turned on and a reviewer cannot judge it without them.
    band_heights: float | None = None
    engines: int = 0
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


def rule_id_for(reading: AboReading) -> str:
    """The rule's identity, including how the value box entered the cell.

    Every pass that publishes an ABO fact writes this, because it is the only
    handle the group has once the row is written: `rule_id LIKE
    'abo/anchored-cell+%'` finds every rescued reading, which is how the group
    is sampled into a review pack and, if the labels turn against it, withdrawn.
    """
    return "abo/anchored-cell" + (f"+{reading.rescued.value.lower()}" if reading.rescued else "")


def needs_corroboration(reading: AboReading) -> bool:
    """Would `reconcile_abo` refuse to publish this reading on its own word?

    True for exactly the class F1 sends to a person: a value admitted by the
    label's ruled ROW, boxed by one engine only. Callers use it to decide
    whether the caption is worth reading for this document at all — the caption
    enters `reconcile_abo` HERE as corroboration and nowhere else, because
    weighing a chat claim against a printed form is `scripts/caption_pass.py`'s
    job and this is not that.
    """
    return (
        reading.status is AboStatus.RESOLVED
        and reading.rescued is AboRescue.BAND
        and len(reading.value_boxes) < 2
    )


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


def _ruling_between(lattice: Lattice | None, anchor: Box, b: Box) -> bool:
    """Does the page rule a line between the label and the token?

    Read at the token's own x, not at the ruling's middle: a ruling across a
    page tilted a degree moves half a row's height end to end.
    """
    if lattice is None:
        return False
    low, high = sorted((anchor.centre_y, b.centre_y))
    return any(r.spans(b.centre_x) and low < r.at_x(b.centre_x) < high for r in lattice.horizontal)


def _blocked_in_band(
    anchor: Box, b: Box, boxes: list[Box], band: RowBand, on_the_line: list[Box]
) -> bool:
    """Does anything stand in a cell between the label and the value?

    The row rule reaches ten label heights along a row, which can cross an
    intervening cell. Measured, the 4 corpus cases with two vertical rulings
    between label and token have an EMPTY cell between them; if one did not,
    the value nearest the label would not be this one.

    A parseable token blocks only when it is on the label's OWN LINE, where the
    shipped rule already owns it — that keeps this rule from taking a page the
    pipeline resolves today. Two tokens that both need rescuing do not settle
    each other by proximity: that cell is doubled, and a doubled cell is a
    question for a person.
    """
    if b.x1 <= anchor.x0:
        low, high = b.x1, anchor.x0
    elif b.x0 >= anchor.x1:
        low, high = anchor.x1, b.x0
    else:
        return False  # the value sits inside the label's own x-span
    strict = {id(box) for box in on_the_line}
    for other in boxes:
        if other is anchor or other is b:
            continue
        if not (low <= other.x0 and other.x1 <= high):
            continue
        if not band.contains_y(other.centre_y):
            continue
        text = (other.text or "").strip()
        if _parse(text):
            if id(other) in strict:
                return True
            continue
        if (
            _LETTER_ONLY.match(text)
            or _SIGN_ONLY.match(text)
            or _is_persian_label(text)
            or _LABEL_LATIN.match(text)
        ):
            return True
    return False


def _owned_by_a_nearer_label(anchor: Box, token: Box, boxes: list[Box]) -> bool:
    """Is some other field's label the one this token belongs to?

    The mainline binder refuses a candidate that sits closer to a different
    label (`ocr/anchors.py`, nearest-anchor ownership). `_cell` has no such
    rule, which is survivable while the window is the label's own line and is
    not once it reaches the line above. The tie-break is what stops a two-letter
    field label on that line from walking through on distance alone.
    """
    label_right = anchor.centre_x > token.centre_x
    anchor_gap = (anchor.x0 - token.x1) if label_right else (token.x0 - anchor.x1)
    anchor_overlap = max(min(anchor.y1, token.y1) - max(anchor.y0, token.y0), 0.0)
    reach = _MAX_GAP * token.height
    for other in boxes:
        if other is anchor or other is token:
            continue
        text = (other.text or "").strip()
        if not text or _parse(text) or not any(ch.isalpha() for ch in text):
            continue
        gap = (other.x0 - token.x1) if label_right else (token.x0 - other.x1)
        if gap < 0 or gap > reach:
            continue
        overlap = min(other.y1, token.y1) - max(other.y0, token.y0)
        if overlap <= _OVERLAP * min(other.height, token.height):
            continue
        if gap < anchor_gap and overlap > anchor_overlap:
            return True
        if (
            gap <= anchor_gap + _ALIGNMENT_TIE_BREAK * token.height
            and overlap > anchor_overlap + _ALIGNMENT_TIE_BREAK * token.height
        ):
            return True
    return False


def _contradicts_the_cell(token: Box, strict_texts: list[str]) -> bool:
    """Does the label's OWN cell already say something else?

    Seven of the nine corpus cases where the cell holds a partial are a lone
    `-` in the cell against a rescued `+`. Publishing over that is best-guess
    acceptance of ambiguous critical OCR; the page keeps its partial reason and
    goes to a person.
    """
    parsed = _parse((token.text or "").strip())
    if parsed is None:
        return False
    letter, rh, _ = parsed
    sign = "+" if rh is Rh.POSITIVE else "-"
    for text in strict_texts:
        if _SIGN_ONLY.match(text) and text != sign:
            return True
        match = _LETTER_ONLY.match(text)
        if match and ("O" if match.group(1) == "0" else match.group(1)) != letter:
            return True
    return False


def _cell(
    anchor: Box,
    boxes: list[Box],
    rightwards: bool,
    band: RowBand | None = None,
    lattice: Lattice | None = None,
    persian_median: float | None = None,
) -> tuple[list[Box], dict[int, AboRescue]]:
    """The boxes in this label's cell, and how any of them got there.

    The horizontal window — direction, `_SLACK`, `_MAX_GAP`, the inside-x-span
    branch — is unchanged by either rescue. Only the vertical test is loosened,
    and only for boxes that would otherwise be dropped: the strict reading is
    computed first and always comes first in the result, so the value the
    pipeline ships today is still the one it reads.
    """
    height = anchor.height
    slack = _SLACK * height
    limit = _MAX_GAP * height
    if band is not None and band.height > _MAX_BAND_HEIGHTS * height:
        # Two printed rows, not a cell. The page is then treated as unruled for
        # this anchor, which is what makes the centre rescue reachable.
        band = None
    strict: list[Box] = []
    candidates: list[tuple[Box, bool, float]] = []
    for b in boxes:
        if b is anchor:
            continue
        if rightwards:
            if not (b.x0 >= anchor.x1 - slack and (b.x0 - anchor.x1) <= limit):
                continue
            inside_span = False
        elif b.x1 <= anchor.x0 + slack and (anchor.x0 - b.x1) <= limit:
            inside_span = False
        elif b.x0 >= anchor.x0 - slack and b.x1 <= anchor.x1 + slack:
            # Persian is detected at line level, so the line box sometimes
            # swallows the Latin value that sits inside it.
            inside_span = True
        else:
            continue
        overlap = min(anchor.y1, b.y1) - max(anchor.y0, b.y0)
        if overlap > _OVERLAP * min(height, max(b.y1 - b.y0, 1e-6)):
            strict.append(b)
        else:
            candidates.append((b, inside_span, overlap))

    rescued: dict[int, AboRescue] = {}
    if not candidates:
        return strict, rescued
    strict_texts = [(b.text or "").strip() for b in strict]
    for b, inside_span, overlap in candidates:
        offset = anchor.centre_y - b.centre_y  # positive: the token sits ABOVE
        if band is not None:
            if (
                band.contains_y(b.centre_y)
                and abs(offset) <= _ROW_REACH * height
                and not _blocked_in_band(anchor, b, boxes, band, strict)
                # The row says which CELL the token is in; it says nothing
                # about a partial already printed in that cell. Measured, 3 of
                # the 45 band gains publish over a lone `-` or a lone letter on
                # the label's own line that contradicts the rescued token, and
                # 2 of those would publish a POSITIVE Rh over a printed `-` as
                # soon as a caption corroborates the letter. That is best-guess
                # acceptance of ambiguous critical OCR, so the band route
                # refuses it exactly as the centre route does.
                and not _contradicts_the_cell(b, strict_texts)
            ):
                rescued[id(b)] = AboRescue.BAND
            continue
        if inside_span or overlap <= 0:
            continue
        if not 0 < offset <= _RESCUE_BAND * height:
            continue
        if _ruling_between(lattice, anchor, b):
            continue
        if persian_median is not None and height > _MAX_ANCHOR_SCALE * persian_median:
            continue
        if _owned_by_a_nearer_label(anchor, b, boxes):
            continue
        if _contradicts_the_cell(b, strict_texts):
            continue
        rescued[id(b)] = AboRescue.CENTRE
    return strict + [b for b, _, _ in candidates if id(b) in rescued], rescued


def _iou(a: Box, b: Box) -> float:
    """How much two boxes overlap, as intersection over union."""
    x0, y0 = max(a.x0, b.x0), max(a.y0, b.y0)
    x1, y1 = min(a.x1, b.x1), min(a.y1, b.y1)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    overlap = (x1 - x0) * (y1 - y0)
    union = (a.x1 - a.x0) * (a.y1 - a.y0) + (b.x1 - b.x0) * (b.y1 - b.y0) - overlap
    return overlap / union if union > 0 else 0.0


def _one_token_read_twice(
    values: list[tuple[tuple[str, Rh, bool], Box, str]], persian: set[int]
) -> bool:
    """Is this cell ONE printed value that both engines boxed, rather than two?

    1,113 documents reach the multi-value branch and 996 of them are this: the
    Latin pass and the Persian pass each drew a rectangle around the same ink,
    so the cell holds two boxes and one value. Refusing them cost 993 documents
    a blood group and 760 an Rh for no safety, because the two readings agree.

    Three gates, and the first does all the work:

    1. **the parsed values must be identical.** Measured, this rejects 117 of
       the 1,113 — including every sign disagreement, which is the dangerous
       one: an `A-` read as `A+` would put a Rh-negative recipient in a
       positive pool. Same-ink cross-engine disagreement runs at 10.5%, and
       this gate catches all of it;
    2. **the boxes must be the same ink**, `_MIN_IOU` overlap against the
       first. Two agreeing values in different places are two values — a page
       with two subjects can print group A twice, and that is not corroboration
       about either of them;
    3. **the boxes must come from two different engines.** One detector
       emitting two rectangles over one token is an artefact, not a second
       opinion.

    Conditional on all three, measured before shipping: 0 letter and 0 sign
    contradictions against 282 independently written chat claims, 6/6 against
    the reviewer's own answers, 14/14 against PP-OCRv5 read whole-page and
    14/14 against PP-OCRv6. The control for what the pipeline ALREADY ships is
    10 letter errors in 1,003 (1.0%), so the collapsed readings are measurably
    no worse than the ones already trusted. The 95% upper bound is 1.06%, not
    zero, which is why the genuinely different cells still go to a person.
    """
    if len({(parsed[0], parsed[1]) for parsed, _, _ in values}) > 1:
        return False
    first = values[0][1]
    if any(_iou(first, box) < _MIN_IOU for _, box, _ in values[1:]):
        return False
    engines = {id(box) in persian for _, box, _ in values}
    return len(engines) > 1


def read_abo(
    persian_boxes: list[Box], latin_boxes: list[Box], lattice: Lattice | None = None
) -> AboReading:
    """Read the blood group from its printed cell, or abstain.

    `lattice` is the page's printed grid in the frame the BOXES are in. Callers
    that rectify a tilted page for the HLA rules must still pass the RAW-frame
    lattice here, because these boxes are the stored ones: the levelled grid
    against raw boxes reads a different row on the 1,591 ROTATE pages.
    """
    everything = list(persian_boxes) + list(latin_boxes)
    # Which engine drew each box, by identity: the Persian pass (easyocr) and
    # the Latin pass (onnxtr) are independent in vendor, detector and
    # recognizer, which is what makes their agreement worth anything.
    from_persian = {id(b) for b in persian_boxes}
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

    # The scale gate compares a label box against the PERSIAN pass's own boxes:
    # a shipped Persian label runs 1.6x the Latin median, so the Latin one
    # would refuse ordinary labels.
    persian_median = statistics.median([b.height for b in persian_boxes]) if persian_boxes else None

    found: list[
        tuple[str, Rh, bool, Box, Box, str, tuple[Box, ...], AboRescue | None, float | None, int]
    ] = []
    partial = ""
    for anchor, rightwards in anchors:
        band = (
            lattice.row_band(anchor.centre_x, anchor.centre_y, anchor.height)
            if lattice is not None
            else None
        )
        cell, rescued = _cell(
            anchor,
            everything,
            rightwards,
            band=band,
            lattice=lattice,
            persian_median=persian_median,
        )
        values = []
        for b in cell:
            token = (b.text or "").strip()
            parsed = _parse(token)
            if parsed:
                values.append((parsed, b, token))
        if len(values) > 1 and not _one_token_read_twice(values, from_persian):
            return AboReading(
                AboStatus.REVIEW_REQUIRED,
                source=source,
                anchor_box=anchor,
                reason="more than one blood-group value in a single cell",
            )
        if values:
            (group, rh, repaired), vbox, raw = values[0]
            # The route of the box the value is READ FROM, not of any box in
            # the cell. `_cell` returns the strict boxes first, so a page whose
            # published box passed the line test has no route and is not marked
            # — the strict window already reads that value, and stamping it
            # would put an unchanged page into the withdrawal group and into
            # the review stratum. Measured, that over-marked 8 pages.
            route = rescued.get(id(vbox))
            boxes_agreed = tuple(b for _, b, _ in values)
            # Every box that agreed travels with the fact, so a reviewer can
            # see the agreement rather than take it on trust.
            found.append(
                (
                    group,
                    rh,
                    repaired,
                    anchor,
                    vbox,
                    raw,
                    boxes_agreed,
                    route,
                    (band.height / anchor.height if route is AboRescue.BAND and band else None),
                    len({id(b) in from_persian for b in boxes_agreed}),
                )
            )
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

    distinct = {(g, rh) for g, rh, _, _, _, _, _, _, _, _ in found}
    if len(distinct) > 1:
        return AboReading(
            AboStatus.REVIEW_REQUIRED, source=source, reason="two cells report different groups"
        )
    if found:
        group, rh, repaired, anchor, vbox, raw, boxes, route, band_heights, engines = found[0]
        return AboReading(
            AboStatus.RESOLVED,
            group=group,
            rh=rh,
            source=source,
            anchor_box=anchor,
            value_box=vbox,
            value_boxes=boxes,
            raw_value=raw,
            repaired=repaired,
            rescued=route,
            band_heights=band_heights,
            engines=engines,
            reason=(
                ""
                if route is None
                else _measured(BAND_RESCUE_REASON, band_heights, engines)
                if route is AboRescue.BAND
                else _measured(CENTRE_RESCUE_REASON, None, engines)
            ),
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
        if image.rescued is AboRescue.BAND and len(image.value_boxes) < 2 and single is None:
            # The band says which CELL the value is in; it says nothing about
            # whether the value was read correctly. 13 of the 43 documents this
            # rule reaches are one engine's box with no second engine over the
            # same ink and no caption, and the safety evidence for that class
            # is nil — every independent agreement measured (17 captions, 1
            # human) lies in the other two classes. So the candidate goes to a
            # person WITH its box, which is more than the generic refusal it
            # replaces gave a reviewer.
            return AboDecision(
                AboStatus.REVIEW_REQUIRED,
                None,
                Rh.UNKNOWN,
                image.source,
                reason=_measured(UNCORROBORATED_RESCUE_REASON, image.band_heights, image.engines),
            )
        agreed = single is not None and single[0] == image.group and single[1] is image.rh
        return AboDecision(
            AboStatus.RESOLVED,
            image.group,
            image.rh,
            image.source,
            agreed=agreed,
            reason=image.reason,
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
