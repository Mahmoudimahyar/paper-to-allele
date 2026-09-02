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
than `DRB1`) and refuses interior damage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from kidneymatch.ocr.glyphs import (
    AlleleValue,
    canonical_locus_label,
    looks_like_locus_label,
    parse_allele_value,
)

Direction = Literal["right", "below"]


class ResolutionStatus(StrEnum):
    """Outcome of trying to bind a value to one locus.

    `UNKNOWN` and `REVIEW_REQUIRED` are different states and must not be merged:
    UNKNOWN means the form does not report this locus at all, while
    REVIEW_REQUIRED means it does and we could not read it safely.
    """

    RESOLVED = "RESOLVED"
    UNKNOWN = "UNKNOWN"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


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
    max_gap: float
    max_values: int


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
    return [b for b in boxes if canonical_locus_label(b.text or "") == locus]


def _all_locus_anchors(boxes: list[Box]) -> list[tuple[str, Box]]:
    """Every box on the page that names any locus, with the locus it names."""
    out = []
    for box in boxes:
        named = canonical_locus_label(box.text or "")
        if named is not None:
            out.append((named, box))
    return out


def _aligned(anchor: Box, box: Box, rule: ValueRule) -> bool:
    """Do these two boxes sit on the same printed line (or column)?"""
    if rule.direction == "right":
        overlap = min(anchor.y1, box.y1) - max(anchor.y0, box.y0)
        shorter = min(anchor.height, max(box.y1 - box.y0, 1e-6))
    else:
        overlap = min(anchor.x1, box.x1) - max(anchor.x0, box.x0)
        shorter = min(max(anchor.x1 - anchor.x0, 1e-6), max(box.x1 - box.x0, 1e-6))
    return overlap / shorter >= rule.align_overlap


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
    limit = rule.max_gap * anchor.height

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
        if start - edge > limit:
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
    for locus, other in _all_locus_anchors(boxes):
        if other is anchor:
            continue
        # A label on a different line does not compete for this box, however
        # close it is along the reading axis. Without this the rule compared
        # every label on the page by x alone and refused 24,892 sound bindings.
        if not _aligned(other, candidate, rule):
            continue
        gap = _distance(other, candidate, rule.direction)
        if 0 <= gap < ours:
            return locus
    return None


def resolve_locus(
    boxes: list[Box],
    locus: str,
    rule: ValueRule,
    anchor_pattern: str | None = None,
) -> LocusResolution:
    """Bind values to `locus` using its printed label on this document.

    The locus is taken from the ANCHOR, never from the value's own text. A value
    token that happens to spell a different locus cannot retarget the binding —
    `OCR_SPEC.md` section 2: geometry decides the field, OCR decides the
    characters inside it. When the two disagree, neither wins: a human looks.
    """
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

    parsed: list[AlleleValue] = []
    for box in found:
        text = (box.text or "").strip()

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

        value = parse_allele_value(text)
        if value is None:
            return LocusResolution(
                locus,
                ResolutionStatus.REVIEW_REQUIRED,
                anchor_box=anchor,
                value_boxes=found,
                reason=f"candidate {text!r} does not parse as an allele value",
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

        parsed.append(value)

    return LocusResolution(
        locus,
        ResolutionStatus.RESOLVED,
        values=[value.text() for value in parsed],
        anchor_box=anchor,
        value_boxes=found,
        parsed_values=parsed,
    )
