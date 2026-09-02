"""Read the subject's role — donor or recipient — off the laboratory form.

`CLASS-001`'s hardest question, and the one the matching engine cannot be wrong
about: a recipient placed in the donor pool is offered to other recipients.

## Why the role must come from the image

It is not a property of whoever posted the picture. Brokers repost the same
report under both donor-offering and recipient-seeking text, 37% of messages are
forwards, and 21% of typing reports arrive with no caption at all. The form
itself prints the subject's role in its `نسبت` (relationship) field, and that
fact survives every repost, crop and forward.

Measured over the true originals: the printed field decides 42.5% of typing
reports on its own, captions add 38.1%, and where both exist they agree 98.6%.

## What a whole-document text search would do

Invert the role, at scale.

* **English is close to a coin flip.** 517 documents contain both "Donor" and
  "Recipient" — 26.1% of those containing the first and 48.3% of those
  containing the second. Judged against the printed Persian field, **142
  documents contain the English word "Recipient" while the form says DONOR**,
  and 75 the reverse. They are column headings ("Donor Name", "Recipient
  Frequency", 574 documents) and choice labels, not values. Only one English
  pattern is safe: a role word with `Status:` or `Donor/Recipient:` immediately
  to its left — 311 DONOR and 118 RECIPIENT documents, none carrying both
  value-forms and none conflicting with the Persian field.
* **Persian is safer, and the reason is measurable.** Among the 810 documents
  where the `نسبت` field LABEL itself is recognised, exactly one carries both
  role words. A pre-printed donor/recipient choice list would put both on all
  810. The Persian word is the field's VALUE.

So the rules here read a value out of a cell. Nothing is ever concluded from a
word appearing somewhere on a page.

## Tiers, and why the weakest one is not a finding

The `نسبت` label is only recognised on 810 documents, so anchoring to it cannot
be a gate — it is a confidence tier:

| tier | evidence | documents | contradicts recipient-only serology |
|---|---|---|---|
| A | value anchored to the `نسبت` label | 738 | 0 of 9 |
| B | value shares a row with other printed field labels | 4,091 | 0 of 19 |
| C | a bare role word somewhere on the page | 5,141 | **4 of 20 (20%)** |

Tier C is where burned-in advertisement text lives. It is a proposal until an
independent same-image signal or the caption agrees.

Right-to-left matters: the Persian value sits to the LEFT of its label (719 of
719 measured pairs), and the English value to the RIGHT of its label. Reading
the wrong way crosses into the neighbouring cell.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from kidneymatch.ocr.anchors import Box, ResolutionStatus


class Role(StrEnum):
    """The subject of the document.

    `UNKNOWN` covers both "no evidence" and "evidence we must not act on". The
    difference is carried by `ResolutionStatus`, never by inventing a third
    role: downstream, an unknown role must keep a record out of both pools.
    """

    DONOR = "DONOR"
    RECIPIENT = "RECIPIENT"
    UNKNOWN = "UNKNOWN"


class RoleTier(StrEnum):
    """How strongly the page says it, strongest first."""

    A_ANCHORED = "A_ANCHORED"
    EN_STATUS = "EN_STATUS"
    B_FORM_CONTEXT = "B_FORM_CONTEXT"
    C_BARE = "C_BARE"
    NONE = "NONE"


# --- Persian normalisation ------------------------------------------------
#
# Arabic and Persian letter forms that the recognizer emits interchangeably.
# Applied before matching so the alternations below stay readable.
_TRANSLATE = str.maketrans(
    {
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ة": "ه",
        "ۀ": "ه",
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ؤ": "و",
        "ئ": "ی",
    }
)
_STRIP = dict.fromkeys(
    [0x200C, 0x200D, 0x200E, 0x200F, 0x0640, *range(0x064B, 0x0653)],
    None,
)


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").translate(_STRIP).translate(_TRANSLATE)).strip()


# The recognizer's measured spellings. Canonical spelling is a MINORITY on both
# sides — 60.5% of donors and 52.8% of recipients — so dropping the variants
# would lose about 40% of the evidence.
_EHDA = r"(?:اهدا|اهد|هدا|امدا|احدا|اددا|ایدا|انیدا|ابدا|ددا|مدا)"
_KONANDE = r"ک\s?[نب]\s?[نب]?\s?[دذ]\s?[هة]?"
_DONOR = re.compile(_EHDA + r"\s?" + _KONANDE + r"|اهداکننده")
_DAHANDE = re.compile(r"^\s?[دذ]\s?ه\s?[نب]\s?[دذ]\s?[هة]\s?$")
_RECIPIENT = re.compile(r"[گک]\s?[یبنپتث]?\s?ر\s?[نب]?\s?[دذ]\s?[هة]")

# Halves of a phrase the recognizer splits across two boxes.
_KONANDE_ONLY = re.compile(r"^" + _KONANDE + r"(?:\s?(?:پیوند|پوند|یوند|پرند|پبوند|بیوند))?$")
_EHDA_ONLY = re.compile(r"^" + _EHDA + r"$")

# The relationship field's own label.
_NESBAT = re.compile(r"^(?:نس?[بپن]?ت)\s?[:：]?$")

# Other printed field labels. Sharing a row with one is evidence that a role
# word is a form cell rather than overlaid advertisement text.
_FORM_WORD = re.compile(
    r"^(?:مرک?[زر]\s?درم?ا?[نی]?ی?|مرکز|نام|نام\s?خانواد\s?گی|گروه|گروه\s?خونی"
    r"|کروه\s?خونی|پزشک|سن|جنس|تاریخ|شماره|سابقه|سابقه\s?پیوند|کاندید|ازمایشگاه"
    r"|نسبت)\s?[:：]?$"
)

# --- English --------------------------------------------------------------
_EN_DONOR = re.compile(r"^\(?[DO][o0][nm][o0]r\)?[.:,]?$", re.IGNORECASE)
_EN_RECIPIENT = re.compile(r"^\(?Rec[il1]p[il1]ent\)?[.:,]?$", re.IGNORECASE)
_EN_LABEL = re.compile(
    r"^(?:(?:Transplant(?:at)?[il1]on|Transplat[il1]on|Transplant)?\s*Status"
    r"|[DO][o0][nm][o0]r\s*[/\\|]\s*Rec[il1]p[il1]ent)[.:]?$",
    re.IGNORECASE,
)
_EN_FIELD_WORD = re.compile(
    r"^(?:Name|Number|Frequency|Relationship|ID|Age|Sex|Gender|Blood|Sample"
    r"|Patient'?s|Cells?|Type|Info(?:rmation)?)[.:]?$",
    re.IGNORECASE,
)

# Anchoring window, in label heights. Measured over 719 pairs: dx from -8.75
# (5th percentile) to -5.80 (95th), never positive.
_ANCHOR_DX = (-10.0, -4.0)
_ANCHOR_DY = 1.0
_ROW_BAND = 1.0
_JOIN_BAND = 0.7


@dataclass(frozen=True, slots=True)
class RoleToken:
    role: Role
    box: Box
    matched: str


@dataclass(frozen=True, slots=True)
class FormRoleReading:
    """What the printed form says, with provenance and a confidence tier."""

    role: Role
    status: ResolutionStatus
    tier: RoleTier = RoleTier.NONE
    tokens: list[RoleToken] = field(default_factory=list)
    anchor_box: Box | None = None
    reason: str = ""


@dataclass(frozen=True, slots=True)
class RoleDecision:
    """The document-level outcome after every source has been weighed."""

    role: Role
    is_finding: bool
    needs_review: bool
    source: str
    reason: str = ""


def _same_row(a: Box, b: Box, band: float = _ROW_BAND) -> bool:
    return abs(a.centre_y - b.centre_y) <= band * a.height


def _persian_tokens(boxes: list[Box]) -> list[RoleToken]:
    """Role words printed on the page, after rejoining split phrases."""
    tokens: list[RoleToken] = []
    seen: set[int] = set()

    for index, b in enumerate(boxes):
        text = normalise(b.text)
        if not text:
            continue
        # Donor is tested first: measured, no box matches both under this order.
        if _DONOR.search(text) or _DAHANDE.match(text):
            tokens.append(RoleToken(Role.DONOR, b, text))
            seen.add(index)
        elif _RECIPIENT.search(text):
            tokens.append(RoleToken(Role.RECIPIENT, b, text))
            seen.add(index)

    for index, b in enumerate(boxes):
        if index in seen:
            continue
        if not _KONANDE_ONLY.match(normalise(b.text)):
            continue
        # The `اهدا` half sits to the RIGHT: Persian reads right to left, so
        # looking left would join across a cell boundary.
        right = sorted(
            (
                o
                for o in boxes
                if o is not b and o.x0 >= b.x1 - 0.2 * b.height and _same_row(b, o, _JOIN_BAND)
            ),
            key=lambda o: o.x0,
        )
        if right and _EHDA_ONLY.match(normalise(right[0].text)):
            tokens.append(RoleToken(Role.DONOR, b, normalise(b.text)))
    return tokens


def _english_reading(boxes: list[Box]) -> tuple[Role, Box | None]:
    """The one safe English pattern: a value immediately right of its label.

    Everything else — a bare role word, a column heading — yields nothing.
    """
    for b in boxes:
        text = (b.text or "").strip()
        role = (
            Role.DONOR
            if _EN_DONOR.match(text)
            else Role.RECIPIENT
            if _EN_RECIPIENT.match(text)
            else None
        )
        if role is None:
            continue
        right = sorted(
            (o for o in boxes if o is not b and o.x0 >= b.x1 and _same_row(b, o)),
            key=lambda o: o.x0,
        )
        if right and _EN_FIELD_WORD.match((right[0].text or "").strip()):
            continue  # a column heading such as `Donor Name`
        left = sorted(
            (o for o in boxes if o is not b and o.x1 <= b.x0 and _same_row(b, o)),
            key=lambda o: -o.x1,
        )
        if left and _EN_LABEL.match((left[0].text or "").strip()):
            return role, left[0]
    return Role.UNKNOWN, None


def _tier_of(token: RoleToken, boxes: list[Box]) -> tuple[RoleTier, Box | None]:
    for b in boxes:
        if not _NESBAT.match(normalise(b.text)):
            continue
        dx = (token.box.centre_x - b.centre_x) / b.height
        dy = (token.box.centre_y - b.centre_y) / b.height
        if _ANCHOR_DX[0] <= dx <= _ANCHOR_DX[1] and abs(dy) <= _ANCHOR_DY:
            return RoleTier.A_ANCHORED, b
    for b in boxes:
        if b is token.box:
            continue
        if _FORM_WORD.match(normalise(b.text)) and _same_row(token.box, b):
            return RoleTier.B_FORM_CONTEXT, None
    return RoleTier.C_BARE, None


def read_form_role(persian_boxes: list[Box], latin_boxes: list[Box]) -> FormRoleReading:
    """Read the role printed on the form. Abstains wherever the page is unclear."""
    tokens = _persian_tokens(persian_boxes)
    roles = {t.role for t in tokens}
    english_role, english_label = _english_reading(latin_boxes)

    if len(roles) > 1:
        # 145 documents, none of them carrying a field anchor: overlaid
        # advertisement text mentioning both parties. Which subject the typing
        # belongs to is exactly what we cannot tell.
        return FormRoleReading(
            Role.UNKNOWN,
            ResolutionStatus.REVIEW_REQUIRED,
            tokens=tokens,
            reason="both role words are printed on this page",
        )

    if not roles:
        if english_role is not Role.UNKNOWN:
            return FormRoleReading(
                english_role,
                ResolutionStatus.RESOLVED,
                tier=RoleTier.EN_STATUS,
                anchor_box=english_label,
            )
        return FormRoleReading(
            Role.UNKNOWN, ResolutionStatus.UNKNOWN, reason="no role field read on this document"
        )

    role = next(iter(roles))
    if english_role is not Role.UNKNOWN and english_role is not role:
        # Two printed fields on one page disagreeing means neither is reliable.
        return FormRoleReading(
            Role.UNKNOWN,
            ResolutionStatus.REVIEW_REQUIRED,
            tokens=tokens,
            reason="the Persian and English role fields disagree",
        )

    best, anchor = RoleTier.C_BARE, None
    for token in tokens:
        tier, anchor_box = _tier_of(token, persian_boxes)
        if tier is RoleTier.A_ANCHORED:
            best, anchor = tier, anchor_box
            break
        if tier is RoleTier.B_FORM_CONTEXT and best is RoleTier.C_BARE:
            best = tier
    return FormRoleReading(
        role, ResolutionStatus.RESOLVED, tier=best, tokens=tokens, anchor_box=anchor
    )


_STRONG = (RoleTier.A_ANCHORED, RoleTier.EN_STATUS, RoleTier.B_FORM_CONTEXT)


def decide_document_role(
    form: FormRoleReading,
    *,
    caption_role: Role = Role.UNKNOWN,
    has_recipient_only_test: bool = False,
    sender_prior: Role = Role.UNKNOWN,
) -> RoleDecision:
    """Weigh every source. The printed field wins; nothing may override it.

    A caption may corroborate a weak reading or veto any reading, but it can
    never rename the person on the page: it is written by whoever posted the
    image, who is frequently a broker rather than the subject. A sender prior
    and a recipient-only test can propose, never conclude. ABO, age, sex and
    poster identity contribute nothing at all.
    """
    if form.status is ResolutionStatus.REVIEW_REQUIRED:
        return RoleDecision(Role.UNKNOWN, False, True, "FORM_FIELD", form.reason)

    if form.role is not Role.UNKNOWN:
        if has_recipient_only_test and form.role is Role.DONOR:
            # A panel-reactive-antibody or crossmatch result is a recipient's
            # test. On a donor form it means the page carries two subjects.
            return RoleDecision(
                Role.UNKNOWN, False, True, "FORM_FIELD", "donor form carries a recipient-only test"
            )
        if caption_role is not Role.UNKNOWN and caption_role is not form.role:
            return RoleDecision(
                Role.UNKNOWN, False, True, "FORM_FIELD", "the caption contradicts the printed field"
            )
        if form.tier in _STRONG:
            return RoleDecision(form.role, True, False, "FORM_FIELD")
        if caption_role is form.role:
            return RoleDecision(form.role, True, False, "FORM_FIELD+CAPTION")
        # Tier C alone: measured to contradict recipient-only serology 20% of
        # the time, against 0% for the anchored tiers. A proposal, not a fact.
        return RoleDecision(
            Role.UNKNOWN, False, True, "FORM_FIELD_WEAK", "a bare role word needs corroboration"
        )

    if has_recipient_only_test:
        return RoleDecision(Role.RECIPIENT, False, True, "RECIPIENT_ONLY_TEST")
    if caption_role is not Role.UNKNOWN:
        return RoleDecision(caption_role, False, True, "CAPTION")
    if sender_prior is not Role.UNKNOWN:
        # 31.4% of no-caption reports come from senders who post both roles.
        return RoleDecision(sender_prior, False, True, "SENDER_PRIOR")
    return RoleDecision(Role.UNKNOWN, False, False, "NONE", "no role evidence on this document")
