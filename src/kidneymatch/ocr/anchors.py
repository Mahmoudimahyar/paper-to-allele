"""Bind an HLA value to a locus using the locus label printed on the document.

This is the code that decides which gene a value belongs to. Getting it wrong is
the worst failure this project can produce, so every ambiguous case abstains.

**Design (ADR 0007).** The template registry stores the RELATION between a
printed locus label and its value — a direction, row tolerance and maximum gap —
not absolute cell rectangles. The cell is located per document from that
document's own anchor.

Absolute rectangles were retired because they are unsafe even for a family that
looks perfect: within one clean family of 1,034 documents the printed `DRB4`
label occupies two different columns 0.285 apart, and the layout signature
cannot separate the variants. A single authored box there would bind the wrong
locus for roughly 40% of members, silently.

**What a shape audit found on 2026-09-02.** The relation was right; the rule was
aimed the wrong way and nothing checked what it bound. Of 2,977 `DRB1` bindings
the resolver called RESOLVED, only 185 were allele-shaped and **988 were the
next row's locus label**; `DPA1` and `DPB1` produced no real values at all
(KI-010). Yield metrics cannot see this — the resolver reported success every
time. Four gates now stand between a candidate box and a RESOLVED value:

1. **Value shape** — it must parse as an allele value (`glyphs.py`). A
   label-shaped token can never be a value, however damaged.
2. **Prefix consistency** — a value that names its own locus must agree with
   the anchor. Geometry still decides; disagreement means nobody knows.
3. **Nearest-anchor ownership** — a candidate closer to a different locus's
   label belongs to that label.
4. **Cardinality** — a locus has at most two alleles.

Anchors are found by `glyphs.canonical_locus_label`, which repairs the
recognizer's measured final-character confusions (`DRBI` is read 3.5x more often
than `DRB1`) and refuses interior damage. Where a form prints the Class I labels
as bare letters, which that matcher refuses and must go on refusing, the page's
own structure promotes them instead (`_bare_class_i_anchors`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Literal

from kidneymatch.hla.vocabulary import FirstFieldVocabulary, load_vocabulary
from kidneymatch.ocr.glyphs import (
    CLASS_I_LOCI,
    AlleleValue,
    canonical_locus_label,
    is_grouped_drbx_header,
    looks_like_locus_label,
    parse_allele_value,
)

Direction = Literal["right", "below"]

# Genes read by `drbx.py` from the grouped DRB3/4/5 header, never by this rule.
# Asking for them here bound neighbouring numbers as alleles on four documents,
# every value impossible for the gene (review W10).
GROUPED_DRBX_GENES = frozenset({"DRB3", "DRB4", "DRB5"})
# The combined header is not a locus anchor (drbx.py reads its row), but it
# owns that row the way any label does: a value nearer to it than to the
# locus label above belongs to the presence row, whatever it says.
GROUPED_DRBX_OWNER = "DRB3/4/5"
# A label box taller than this many times the page's typical label is the
# detector's, not the form's — stretched over a ruling or a neighbouring line —
# and a band measured in its height would reach the next row. No tolerance
# band is tried from such an anchor.
TALL_ANCHOR_RATIO = 1.5

# Loci this relation can legitimately read.
DEFAULT_LOCI: tuple[str, ...] = ("A", "B", "C", "DRB1", "DQA1", "DQB1", "DPA1", "DPB1")

# How much closer to another label's line a candidate must sit before that
# label takes it from the anchor that is nearer along the reading axis, as a
# fraction of a label height. Zero — the behaviour before this constant — makes
# the tilt of the photograph decide the owner.
OWNERSHIP_Y_MARGIN = 0.25

# A value is one line of text. Measured, 99.7% of legitimate values are 0.5-1.6
# label heights tall; a box several times taller is a detector blob spanning
# rows, and it is "aligned" with every row it crosses (review W3).
MAX_VALUE_HEIGHT_RATIO = 2.5

# Some forms print the Class I labels as bare letters (`A`, `B`, `C`).
# `canonical_locus_label` refuses them on purpose and must go on refusing: `A`
# is also a blood group, an initial, a list marker and a column heading, and a
# token that short cannot name a locus by what it says. Geometry can still say
# it is a label, which is the rule the constitution already states — the cell
# assigns the locus, never the text — so a bare letter anchors only where the
# page's own structure makes it one. On the reviewer's 220 labels this is the
# single largest cause of a locus never being looked for at all.
BARE_CLASS_I = re.compile(r"^([ABC])\s*[:.\-–—]?\s*$", re.IGNORECASE)
# Unambiguous locus labels the page must already print before any bare letter
# is read as one: two, so a single stray HLA word cannot make a table.
BARE_MIN_NAMED_LOCI = 2
# How far the letter's left edge may sit from the label column those labels
# form, in label heights.
BARE_COLUMN_SLACK = 2.0
# Bare letters standing in that column that make a table of their own. Two is
# enough: `A` over `B` in the label column of a form that also prints DRB1 and
# DQB1 is an HLA table, and a blood group is printed once, not stacked.
BARE_MIN_STACK = 2
# A lone letter is promoted only when a spelled-out label sits within this many
# label heights of its row, so it is demonstrably inside the same block. The
# stack does not need it: a real HLA table is eight rows tall, and the Class I
# rows sit that far above the Class II labels by design.
BARE_ROW_GAP = 4.0


class ResolutionStatus(StrEnum):
    """Outcome of trying to bind a value to one locus.

    `UNKNOWN` and `REVIEW_REQUIRED` are different states and must not be merged:
    UNKNOWN means the form does not report this locus at all, while
    REVIEW_REQUIRED means it does and we could not read it safely. `NOT_TESTED`
    is a third thing again: the form reports it, the cell is empty, and this
    laboratory never fills it.
    """

    RESOLVED = "RESOLVED"
    UNKNOWN = "UNKNOWN"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    # The form reports this locus, the cell is empty, and the laboratory
    # measurably never fills it (HA-009). A finding, not a failure: it is not a
    # mismatch and not a zero, and matching must read it as UNKNOWN with a
    # reason. It exists so that ~24,000 cells nobody can act on stay out of the
    # review queue without pretending they were never printed.
    NOT_TESTED = "NOT_TESTED"


class SecondAllele(StrEnum):
    """Whether this locus's second allele was read.

    A locus is diploid. One value in the cell does NOT mean homozygous: it means
    one value was read. Measured, the second allele sat just past the chain on
    6,597 cells, and 29-36% of resolved A/B/DRB1 cells carried a single value —
    far above any plausible homozygosity rate (KI-015). A consumer that read a
    one-element list as a genotype would miscount every mismatch, so the state
    is explicit and there is no way to get a list without it.
    """

    READ = "READ"
    UNREAD = "UNREAD"


@dataclass(frozen=True, slots=True)
class Box:
    """A recognized text box in normalized page coordinates."""

    x0: float
    y0: float
    x1: float
    y1: float
    text: str

    @property
    def height(self) -> float:
        return max(self.y1 - self.y0, 1e-6)

    @property
    def centre_y(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def centre_x(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass(frozen=True, slots=True)
class ValueRule:
    """Where the value sits relative to its label, in units of label height.

    Expressing tolerances in label heights rather than absolute coordinates is
    what lets one rule serve documents at 520 px and 1,280 px alike.

    The dominant layout on this corpus is a vertical stack of row labels with
    values to the right, so `direction="right"` with a wide `max_gap` is the
    sensible default. `below` remains available because DP rows on some forms
    are laid out differently; per-family rules are authored from evidence, not
    assumed (ADR 0007).

    `align_overlap` is the fraction of the SHORTER box's extent that must
    overlap across the direction of travel — vertical overlap for a rule
    reading rightwards. Centre distance was tried first and is wrong: measured
    over 15,631 documents, a `DRB1` value's centre sits 0.5 to 0.75 label
    heights ABOVE its label's centre while the two boxes still share 25-50% of
    their vertical extent. A centre tolerance loose enough to admit them also
    admits the neighbouring row; overlap separates the two cleanly and does not
    care that the recognizer boxed the value slightly higher.
    """

    direction: Direction
    align_overlap: float
    max_gap: float | None
    max_values: int

    # A per-family alternative to the overlap test, in anchor heights. A form's
    # rows sit a fixed pitch apart (3.8 anchor heights on the dominant
    # letterhead), so half that pitch is the natural band, and it admits values
    # boxed half a line above their label that the overlap test alone drops.
    # `None` keeps the overlap test as the only criterion.
    centre_band: float | None = None

    # Require a value to print its own locus. On the dominant form 99.9% of
    # values do, and demanding it is what makes reading the whole row band
    # without a distance cap safe: the second allele column sits 8-25 anchor
    # heights away, so a cap cuts it off, while a bare number anywhere on that
    # band could be anything. Forms that do not print the locus keep the
    # default, where a bare value is legitimate.
    require_prefix: bool = False

    # A tolerance for the overlap test, in anchor heights, used ONLY when the
    # overlap test finds nothing at all (or a single value with its partner
    # unread). Measured over the 11,140 default-rule documents: the nearest
    # allele-shaped box to a label whose cell read empty sits 1.0 anchor height
    # off its centre on 1,406 of 5,302 such cells — a photograph's drift, or a
    # label box the detector stretched over a ruling. Applied as a first
    # criterion, a band of 1.5 resolved 949 of them but also added candidates
    # to 799 cells that already resolved and refused them; as a fallback it
    # added 901 cells and 890 second alleles with 0 boxes bound to two loci and
    # no resolved cell changed — hence a fallback, never a widening. Every gate
    # runs under the widened alignment when the band is used, so a competing
    # label sees the same boxes the band does; a tall anchor gets no band.
    fallback_band: float | None = None


@dataclass(frozen=True, slots=True)
class LocusResolution:
    """The outcome, carrying provenance back to the pixels it came from."""

    locus: str
    status: ResolutionStatus
    values: list[str] = field(default_factory=list)
    anchor_box: Box | None = None
    value_boxes: list[Box] = field(default_factory=list)
    reason: str = ""
    parsed_values: list[AlleleValue] = field(default_factory=list)
    second_allele: SecondAllele = SecondAllele.UNREAD

    @property
    def repaired(self) -> bool:
        """True if any accepted value needed a glyph repair to be read."""
        return any(value.repaired for value in self.parsed_values)


def find_anchors(boxes: list[Box], locus: str, anchor_pattern: str | None = None) -> list[Box]:
    """Boxes whose text IS this locus's printed label.

    The default matcher is `glyphs.canonical_locus_label`, which repairs the
    measured final-character confusions and refuses interior damage. A template
    family MAY override it with a regex (ADR 0007 stores the relation per
    family), and the regex is then matched against the WHOLE stripped token —
    never searched within it. `\\bDRB1\\b` also matches the `DRB1` inside
    `DRB1*11`; measured on the real corpus that inflated apparent DRB1 presence
    by 5.18x and placed the locus wherever a patient value happened to sit.
    """
    if anchor_pattern is not None:
        compiled = re.compile(anchor_pattern, re.IGNORECASE)
        return [b for b in boxes if compiled.match((b.text or "").strip())]
    spelled = [b for b in boxes if canonical_locus_label(b.text or "") == locus]
    # A label spelled out always wins; the bare letter is only ever a fallback,
    # so a page printing `HLA-A` is never re-read from a stray `A` elsewhere.
    return spelled or _bare_class_i_anchors(boxes, locus)


def _named_locus_anchors(boxes: list[Box]) -> list[tuple[str, Box]]:
    """Every box whose TEXT names a locus, with the locus it names."""
    out = []
    for box in boxes:
        text = box.text or ""
        named = canonical_locus_label(text)
        if named is not None:
            out.append((named, box))
        elif is_grouped_drbx_header(text):
            out.append((GROUPED_DRBX_OWNER, box))
    return out


def _bare_class_i_column(boxes: list[Box]) -> dict[str, list[Box]]:
    """Bare `A`, `B` and `C` boxes the page's structure makes locus labels.

    Every condition is structural, so none of them requires believing the
    letter itself:

    1. the page already spells out at least `BARE_MIN_NAMED_LOCI` distinct
       locus labels, so it is an HLA table and not a page with a stray letter;
    2. the letter stands in the column those labels form;
    3. something allele-shaped sits to its right on its own row;
    4. it is one of `BARE_MIN_STACK` such letters stacked in that column, or
       else a spelled-out label sits within `BARE_ROW_GAP` of its row.

    The fourth is what separates a Class I block from a blood group: a group is
    printed once and a table prints `A` over `B`. Distance alone cannot do it,
    because on a real form the Class I rows sit six to nine label heights above
    the Class II labels, which is exactly where a stray letter also sits.
    """
    named = _named_locus_anchors(boxes)
    if len({name for name, _ in named} - {GROUPED_DRBX_OWNER}) < BARE_MIN_NAMED_LOCI:
        return {}
    lefts = sorted(box.x0 for _, box in named)
    heights = sorted(box.height for _, box in named)
    column = lefts[len(lefts) // 2]
    unit = heights[len(heights) // 2] or 1e-6

    standing: dict[str, list[tuple[Box, bool]]] = {}
    for box in boxes:
        found = BARE_CLASS_I.match((box.text or "").strip())
        if found is None or found.group(1).upper() not in CLASS_I_LOCI:
            continue
        if abs(box.x0 - column) > BARE_COLUMN_SLACK * unit:
            continue
        if not any(
            other.x0 > box.x1
            and abs(other.centre_y - box.centre_y) <= box.height
            and parse_allele_value((other.text or "").strip()) is not None
            for other in boxes
        ):
            continue
        beside = any(
            abs(box.centre_y - other.centre_y) <= BARE_ROW_GAP * unit for _, other in named
        )
        standing.setdefault(found.group(1).upper(), []).append((box, beside))

    if len(standing) >= BARE_MIN_STACK:
        return {letter: [box for box, _ in found] for letter, found in standing.items()}
    kept = {letter: [box for box, beside in found if beside] for letter, found in standing.items()}
    return {letter: found for letter, found in kept.items() if found}


def _bare_class_i_anchors(boxes: list[Box], locus: str) -> list[Box]:
    """The bare letters the page's structure promotes to this locus's label."""
    if locus not in CLASS_I_LOCI:
        return []
    return _bare_class_i_column(boxes).get(locus.upper(), [])


def _all_locus_anchors(boxes: list[Box]) -> list[tuple[str, Box]]:
    """Every box on the page that names any locus, with the locus it names.

    Includes the bare Class I letters the page's structure promotes, so that
    ownership and scale are judged against every label the form actually
    prints rather than only the ones spelled out in full.
    """
    out = _named_locus_anchors(boxes)
    claimed = {name for name, _ in out}
    for locus in sorted(CLASS_I_LOCI):
        if locus in claimed:
            continue
        out.extend((locus, box) for box in _bare_class_i_anchors(boxes, locus))
    return out


def _anchor_is_tall(anchor: Box, boxes: list[Box]) -> bool:
    """Is this label box out of scale with the page's other labels?"""
    heights = sorted(box.height for _, box in _all_locus_anchors(boxes) if box is not anchor)
    if len(heights) < 3:
        return False
    return anchor.height > TALL_ANCHOR_RATIO * heights[len(heights) // 2]


def _aligned(anchor: Box, box: Box, rule: ValueRule) -> bool:
    """Do these two boxes sit on the same printed line (or column)?"""
    if rule.direction == "right":
        overlap = min(anchor.y1, box.y1) - max(anchor.y0, box.y0)
        shorter = min(anchor.height, max(box.y1 - box.y0, 1e-6))
        centres = abs(box.centre_y - anchor.centre_y)
    else:
        overlap = min(anchor.x1, box.x1) - max(anchor.x0, box.x0)
        shorter = min(max(anchor.x1 - anchor.x0, 1e-6), max(box.x1 - box.x0, 1e-6))
        centres = abs(box.centre_x - anchor.centre_x)
    if overlap / shorter >= rule.align_overlap:
        return True
    return rule.centre_band is not None and centres <= rule.centre_band * anchor.height


def _distance(anchor: Box, box: Box, direction: Direction) -> float:
    if direction == "right":
        return box.x0 - anchor.x1
    return box.y0 - anchor.y1


def _candidates(boxes: list[Box], anchor: Box, rule: ValueRule) -> list[Box]:
    """Boxes positioned as this anchor's values, in reading order.

    Gaps are measured from the PREVIOUS cell in the chain, not from the anchor.
    A heterozygous locus prints two alleles, and the second one sits two gaps
    from the label; measuring both from the anchor would need a `max_gap` large
    enough to also reach into the next column, which is exactly how a value gets
    bound to the wrong locus.
    """
    limit = None if rule.max_gap is None else rule.max_gap * anchor.height

    def aligned(box: Box) -> bool:
        return _aligned(anchor, box, rule)

    if rule.direction == "right":
        ahead = sorted(
            (b for b in boxes if b is not anchor and b.x0 > anchor.x1 and aligned(b)),
            key=lambda b: b.x0,
        )
    else:
        ahead = sorted(
            (b for b in boxes if b is not anchor and b.y0 > anchor.y1 and aligned(b)),
            key=lambda b: b.y0,
        )

    found: list[Box] = []
    edge = anchor.x1 if rule.direction == "right" else anchor.y1
    for box in ahead:
        start = box.x0 if rule.direction == "right" else box.y0
        if limit is not None and start - edge > limit:
            break  # the chain is broken; anything further belongs to another cell
        found.append(box)
        edge = box.x1 if rule.direction == "right" else box.y1
    return found


def _owned_by_another_anchor(
    candidate: Box, anchor: Box, boxes: list[Box], rule: ValueRule
) -> str | None:
    """The locus of a label that owns this candidate more plausibly than ours.

    Two loci printed on one row band is a normal layout, and reading rightwards
    with a generous gap walks from one cell into the next. The nearest preceding
    label owns the value; anything else is a guess about which gene a patient's
    allele belongs to.
    """
    ours = _distance(anchor, candidate, rule.direction)
    ours_offset = abs(candidate.centre_y - anchor.centre_y)
    for locus, other in _all_locus_anchors(boxes):
        if other is anchor:
            continue
        # A label on a different line does not compete for this box, however
        # close it is along the reading axis. Without this the rule compared
        # every label on the page by x alone and refused 24,892 sound bindings.
        if not _aligned(other, candidate, rule):
            continue
        gap = _distance(other, candidate, rule.direction)
        if gap < 0:
            continue
        # Stacked labels share an x1, so horizontal distance alone cannot
        # separate them: a tall value overlapping two rows tied, and the strict
        # `<` let BOTH loci resolve it (review W3/W4). A tie is an ownership
        # conflict, and near-ties are decided by vertical proximity, which is
        # what actually distinguishes one printed row from the next.
        if abs(gap - ours) <= 1e-9:
            return locus
        if gap < ours:
            return locus
        # Our label is nearer along the reading axis, so the other one takes
        # the box only by being on a visibly different line — not by a
        # fraction of a pixel. A photographed page is never level, and at
        # 1e-9 the winner of this comparison is the page's tilt rather than
        # its layout: on the reviewer's labels two values were handed to the
        # locus printed above them on exactly this clause.
        margin = OWNERSHIP_Y_MARGIN * max(anchor.height, other.height)
        if abs(candidate.centre_y - other.centre_y) < ours_offset - margin:
            return locus
    return None


def _value_beyond_the_chain(
    boxes: list[Box], anchor: Box, found: list[Box], rule: ValueRule
) -> Box | None:
    """An allele-shaped box on this row, past where the chain stopped.

    The measured failure behind KI-015: in two-allele cells the gap to the
    second allele is median 15.3 label heights and max exactly 20.0 — the cap
    itself. On 6,597 single-allele cells the heterozygous partner sat just
    beyond, self-prefixed with the same locus 98-99% of the time. Resolving
    without it publishes half a genotype.
    """
    edge = found[-1] if found else anchor
    for box in boxes:
        if box is anchor or any(box is seen for seen in found):
            continue
        if not _aligned(anchor, box, rule):
            continue
        if _distance(edge, box, rule.direction) <= 0:
            continue
        text = (box.text or "").strip()
        if looks_like_locus_label(text) or parse_allele_value(text) is None:
            continue
        if _owned_by_another_anchor(box, anchor, boxes, rule) is not None:
            continue
        return box
    return None


def resolve_locus(
    boxes: list[Box],
    locus: str,
    rule: ValueRule,
    anchor_pattern: str | None = None,
    vocabulary: FirstFieldVocabulary | None = None,
) -> LocusResolution:
    """Bind values to `locus` using its printed label on this document.

    The locus is taken from the ANCHOR, never from the value's own text. A value
    token that happens to spell a different locus cannot retarget the binding —
    `OCR_SPEC.md` section 2: geometry decides the field, OCR decides the
    characters inside it. When the two disagree, neither wins: a human looks.
    """
    if locus in GROUPED_DRBX_GENES:
        # Presence typing, read by `drbx.py` from the grouped header. A caller
        # that asks here has a bug, and a quiet UNKNOWN would hide it.
        raise ValueError(
            f"{locus} is read from the grouped DRB3/4/5 row by kidneymatch.ocr.drbx, "
            "not by the generic value rule"
        )
    vocabulary = vocabulary if vocabulary is not None else load_vocabulary()
    anchors = find_anchors(boxes, locus, anchor_pattern)

    if not anchors:
        # The form does not print this locus. That is UNKNOWN, not a failure,
        # and it must never become a zero mismatch downstream.
        return LocusResolution(locus, ResolutionStatus.UNKNOWN, reason="no anchor on this document")

    if len(anchors) > 1:
        # Measured: DRB3 appears more than once in 17.7% of documents, usually as
        # the combined DRB3/4/5 header. We cannot tell which row owns the value.
        return LocusResolution(
            locus,
            ResolutionStatus.REVIEW_REQUIRED,
            anchor_box=anchors[0],
            reason=f"{len(anchors)} anchors found; cannot decide which row owns the value",
        )

    anchor = anchors[0]
    found = _candidates(boxes, anchor, rule)
    if (
        rule.fallback_band is not None
        and len(found) < rule.max_values
        and not _anchor_is_tall(anchor, boxes)
    ):
        # The overlap test read nothing, or one allele with its partner unread.
        # Once more within the tolerance band; the wider reading is kept only
        # when it contains everything the strict one found and no more boxes
        # than the locus can have, so a strict result is never made worse. The
        # gates run under the widened rule too: ownership by another label and
        # the partner-beyond-the-chain guard must see what the band sees.
        wide_rule = replace(rule, centre_band=rule.fallback_band)
        wide = _candidates(boxes, anchor, wide_rule)
        if (
            len(wide) > len(found)
            and len(wide) <= rule.max_values
            and all(any(box is seen for seen in wide) for box in found)
        ):
            strict = _bind(boxes, locus, rule, anchor, found, vocabulary)
            tolerant = _bind(boxes, locus, wide_rule, anchor, wide, vocabulary)
            # The wider reading stands only if it resolves; otherwise the strict
            # one is exactly what the rule said before the band existed.
            if tolerant.status is ResolutionStatus.RESOLVED:
                return tolerant
            return strict
    return _bind(boxes, locus, rule, anchor, found, vocabulary)


def _bind(
    boxes: list[Box],
    locus: str,
    rule: ValueRule,
    anchor: Box,
    found: list[Box],
    vocabulary: FirstFieldVocabulary,
) -> LocusResolution:
    """Run every gate over the candidate boxes of one anchor.

    The geometric gates run over EVERY box before any text is parsed, so a
    refusal for value shape ("does not parse") means every box in the cell sat
    where a value sits, named no label and belonged to no other anchor — which
    is what lets `promote_proposals.py` treat the decode's reading of those
    boxes as a value of this locus.
    """
    if not found:
        # The label is printed but nothing was read in its cell. That is
        # REVIEW_REQUIRED, not UNKNOWN, and the distinction is a policy in
        # `OCR_SPEC.md`: UNKNOWN means the form does not report this locus,
        # while a printed label we could not read is a failure a human must
        # see.
        #
        # It is tempting to call an empty cell "the laboratory did not type
        # this locus" and retire ~13,000 DPB1 items from the queue. Measured,
        # that would be wrong: DPB1 values on these forms sit 5-6 label heights
        # ABOVE the label, so an empty cell under a rightward rule means the
        # RULE is wrong for that family, not that the row is blank. Emitting
        # UNKNOWN there would convert a rule defect into silent data loss.
        #
        # A large count here is therefore a signal to author a per-family rule
        # (ADR 0007), which is exactly what review is for.
        return LocusResolution(
            locus,
            ResolutionStatus.REVIEW_REQUIRED,
            anchor_box=anchor,
            reason="anchor found but no box at all in its cell under this rule",
        )
    set_aside = 0
    if len(found) > rule.max_values and rule.require_prefix:
        # On a form that prints the locus on every value, a candidate that
        # names ANOTHER locus is the neighbouring row's value drifting into
        # this row's band on a hand-held photograph — never this cell's. It
        # is set aside before the count; a candidate that names no locus or
        # does not parse is kept, and the gates below refuse the cell as
        # before. Measured corpus-wide: 1,366 refused cells hold exactly two
        # values naming this locus beside one or two naming another. The
        # count set aside is recorded on the resolution.
        kept = [
            box
            for box in found
            if (value := parse_allele_value((box.text or "").strip())) is None
            or value.locus_prefix in (None, locus)
        ]
        set_aside = len(found) - len(kept)
        found = kept
    if len(found) > rule.max_values:
        # A locus has at most two alleles. More candidates means the row was
        # misread, and picking the nearest would be a guess.
        return LocusResolution(
            locus,
            ResolutionStatus.REVIEW_REQUIRED,
            anchor_box=anchor,
            value_boxes=found,
            reason=f"{len(found)} candidate values exceeds max_values={rule.max_values}",
        )
    # The geometric gates, for every box, before a single character is read.
    for box in found:
        text = (box.text or "").strip()
        if box.height > MAX_VALUE_HEIGHT_RATIO * anchor.height:
            # Not one line of text. Such a box overlaps several printed rows, so
            # it is "aligned" with every label it crosses and was bound twice.
            return LocusResolution(
                locus,
                ResolutionStatus.REVIEW_REQUIRED,
                anchor_box=anchor,
                value_boxes=found,
                reason=(
                    f"candidate is {box.height / anchor.height:.1f}x the label height; "
                    "not a single line of text"
                ),
            )
        if looks_like_locus_label(text):
            # Gate 1. The measured failure: 988 of 2,977 DRB1 bindings were the
            # next row's label, reported as this patient's allele.
            return LocusResolution(
                locus,
                ResolutionStatus.REVIEW_REQUIRED,
                anchor_box=anchor,
                value_boxes=found,
                reason=f"candidate {text!r} is a locus label, not a value",
            )
        owner = _owned_by_another_anchor(box, anchor, boxes, rule)
        if owner is not None:
            # Gate 3.
            return LocusResolution(
                locus,
                ResolutionStatus.REVIEW_REQUIRED,
                anchor_box=anchor,
                value_boxes=found,
                reason=f"candidate is closer to the {owner} label; another locus owns it",
            )
    # The text gates. A box that does not parse is noted and the OTHER boxes
    # are still put through every gate: a refusal for shape must mean that
    # nothing else on the row was wrong.
    parsed: list[AlleleValue] = []
    unparsed: str | None = None
    for box in found:
        text = (box.text or "").strip()
        value = parse_allele_value(text)
        if value is None:
            if unparsed is None:
                unparsed = text
            continue
        if value.separator_missing and not rule.require_prefix:
            # `B35` with no star. On a form measured to print `LOCUS*NN` on
            # 99.8-99.9% of its values (the family rule), that is the star the
            # recognizer did not read — 1,958 cells corpus-wide. On a form
            # nobody has measured, it may be a serological spelling, which
            # HLA_VALIDATION_SPEC s4 keeps apart from allele notation; a
            # human decides which it is.
            return LocusResolution(
                locus,
                ResolutionStatus.REVIEW_REQUIRED,
                anchor_box=anchor,
                value_boxes=found,
                reason=(
                    f"candidate {text!r} names its locus without a star, and this form is not "
                    "measured to print the locus on its values"
                ),
            )
        if rule.require_prefix and value.locus_prefix is None:
            # This family prints the locus on every value, so a bare number on
            # the row band is not one of its values. Without the distance cap
            # that this requirement replaces, accepting it would bind anything
            # on the line.
            return LocusResolution(
                locus,
                ResolutionStatus.REVIEW_REQUIRED,
                anchor_box=anchor,
                value_boxes=found,
                reason=(
                    f"this form prints the locus on every value, and {text!r} does not name one"
                ),
            )
        if value.locus_prefix is not None and value.locus_prefix != locus:
            # Gate 2. Geometry says one gene, the printed value says another.
            return LocusResolution(
                locus,
                ResolutionStatus.REVIEW_REQUIRED,
                anchor_box=anchor,
                value_boxes=found,
                reason=(
                    f"value names {value.locus_prefix} but the anchor is {locus}; "
                    "geometry and text disagree"
                ),
            )
        if not vocabulary.covers(locus):
            # An unchecked value must never be presented as a checked one.
            return LocusResolution(
                locus,
                ResolutionStatus.REVIEW_REQUIRED,
                anchor_box=anchor,
                value_boxes=found,
                reason=f"no first-field vocabulary for {locus}; cannot check the value",
            )
        if not vocabulary.is_admissible(locus, value.first_field):
            # Gate 5. The recognizer's commonest surviving error is a leading
            # `0` read as `8` or `9` (`A*83`, `DRB1*93`). Both readings are
            # clean digits, so no repair and no geometric gate can see it.
            return LocusResolution(
                locus,
                ResolutionStatus.REVIEW_REQUIRED,
                anchor_box=anchor,
                value_boxes=found,
                reason=(
                    f"{value.first_field!r} is not an allele family of {locus} "
                    f"in IMGT {vocabulary.imgt_version}"
                ),
            )
        parsed.append(value)
    if unparsed is not None:
        return LocusResolution(
            locus,
            ResolutionStatus.REVIEW_REQUIRED,
            anchor_box=anchor,
            value_boxes=found,
            reason=f"candidate {unparsed!r} does not parse as an allele value",
        )
    beyond = _value_beyond_the_chain(boxes, anchor, found, rule)
    if beyond is not None:
        return LocusResolution(
            locus,
            ResolutionStatus.REVIEW_REQUIRED,
            anchor_box=anchor,
            value_boxes=found,
            reason="an allele-shaped box sits on this row beyond the chain; "
            "the second allele may have been cut off",
        )
    return LocusResolution(
        locus,
        ResolutionStatus.RESOLVED,
        values=[value.text() for value in parsed],
        anchor_box=anchor,
        value_boxes=found,
        parsed_values=parsed,
        # One value read is not homozygosity: it is one value read.
        second_allele=SecondAllele.READ if len(parsed) >= 2 else SecondAllele.UNREAD,
        reason=(f"{set_aside} candidate(s) naming another locus set aside" if set_aside else ""),
    )


def resolve_in_row(
    boxes: list[Box],
    locus: str,
    rule: ValueRule,
    anchor: Box,
    band: tuple[float, float],
    vocabulary: FirstFieldVocabulary | None = None,
) -> LocusResolution:
    """Bind the values of one printed ROW: the space between two rulings.

    The candidates are every box whose centre lies in the band, right of the
    anchor, in reading order — the printed cell is the geometry, so there is
    no distance cap and no overlap test to pass. Every gate then runs exactly
    as it does for an anchored cell: a label is not a value, another label may
    own the box, the value must parse, name this locus on a form that prints
    the locus, and be admissible. The anchor may be a VIRTUAL box placed by the
    form's template where a label the recognizer could not read is printed;
    on the three known forms every value prints its locus, so a value in the
    wrong row refuses itself (gate 2) rather than binding.
    """
    vocabulary = vocabulary if vocabulary is not None else load_vocabulary()
    top, bottom = band
    found = sorted(
        (
            box
            for box in boxes
            if box is not anchor and box.x0 > anchor.x1 and top <= box.centre_y <= bottom
        ),
        key=lambda box: box.x0,
    )
    return _bind(boxes, locus, rule, anchor, found, vocabulary)


def enforce_exclusivity(results: dict[str, LocusResolution]) -> dict[str, LocusResolution]:
    """Withdraw every reading that shares a value box with another locus.

    One box cannot be two genes' values; when it happens both readings are
    withdrawn rather than one being preferred. Applied by `resolve_document`
    and again after any later binding (the ruled-row binding) adds readings.
    """
    owners: dict[int, list[str]] = {}
    for locus, result in results.items():
        if result.status is not ResolutionStatus.RESOLVED:
            continue
        for box in result.value_boxes:
            owners.setdefault(id(box), []).append(locus)
    contested = {locus for claims in owners.values() if len(claims) > 1 for locus in claims}
    out = dict(results)
    for locus in contested:
        out[locus] = LocusResolution(
            locus,
            ResolutionStatus.REVIEW_REQUIRED,
            anchor_box=results[locus].anchor_box,
            value_boxes=results[locus].value_boxes,
            reason="a value box on this document was bound by more than one locus",
        )
    return out


def resolve_document(
    boxes: list[Box],
    rule: ValueRule,
    loci: tuple[str, ...] = DEFAULT_LOCI,
    vocabulary: FirstFieldVocabulary | None = None,
) -> dict[str, LocusResolution]:
    """Resolve every locus on one document, enforcing exclusivity between them.

    The last line of defence. Each locus is resolved independently and with no
    memory of what another locus bound, so a box that passes every per-locus
    gate can still be claimed twice — measured, three boxes were RESOLVED under
    both DQA1 and DPA1. One box cannot be two genes' values, so when it happens
    both readings are withdrawn rather than one being preferred.
    """
    vocabulary = vocabulary if vocabulary is not None else load_vocabulary()
    results = {
        locus: resolve_locus(boxes, locus, rule, vocabulary=vocabulary)
        for locus in loci
        if locus not in GROUPED_DRBX_GENES
    }

    return enforce_exclusivity(results)
