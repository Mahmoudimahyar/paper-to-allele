"""Bind an HLA value to a locus using the locus label printed on the document.

This is the code that decides which gene a value belongs to. Getting it wrong is
the worst failure this project can produce, so every ambiguous case abstains.

**Design (ADR 0007).** The template registry stores the RELATION between a
printed locus label and its value — an anchor pattern plus a direction, row
tolerance and maximum gap — not absolute cell rectangles. The cell is located per
document from that document's own anchor.

Absolute rectangles were retired because they are unsafe even for a family that
looks perfect: within one clean family of 1,034 documents the printed `DRB4`
label occupies two different columns 0.285 apart, and the layout signature cannot
separate the variants. A single authored box there would bind the wrong locus for
roughly 40% of members, silently.

Anchoring per document is stricter than that, not looser: the geometry is
re-established from the page in front of us rather than inherited from a family
average that may not apply to this member.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

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
    """

    direction: Direction
    same_row_tol: float
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


def find_anchors(boxes: list[Box], anchor_pattern: str) -> list[Box]:
    """Boxes whose text IS the locus label.

    The pattern is matched against the whole stripped token, never searched
    within it. `\\bDRB1\\b` also matches the `DRB1` inside `DRB1*11`; measured on
    the real corpus that inflated apparent DRB1 presence by 5.18x and placed the
    locus wherever a patient-specific value happened to sit.
    """
    compiled = re.compile(anchor_pattern, re.IGNORECASE)
    return [b for b in boxes if compiled.match((b.text or "").strip())]


def _candidates(boxes: list[Box], anchor: Box, rule: ValueRule) -> list[Box]:
    """Boxes positioned as this anchor's values, in reading order.

    Gaps are measured from the PREVIOUS cell in the chain, not from the anchor.
    A heterozygous locus prints two alleles, and the second one sits two gaps
    from the label; measuring both from the anchor would need a `max_gap` large
    enough to also reach into the next column, which is exactly how a value gets
    bound to the wrong locus.
    """
    tolerance = rule.same_row_tol * anchor.height
    limit = rule.max_gap * anchor.height

    def aligned(box: Box) -> bool:
        if rule.direction == "right":
            return abs(box.centre_y - anchor.centre_y) <= tolerance
        return abs(box.centre_x - anchor.centre_x) <= tolerance

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


def resolve_locus(
    boxes: list[Box],
    locus: str,
    anchor_pattern: str,
    rule: ValueRule,
) -> LocusResolution:
    """Bind values to `locus` using its printed label on this document.

    The locus is taken from the ANCHOR, never from the value's own text. A value
    token that happens to spell a different locus cannot retarget the binding —
    `OCR_SPEC.md` section 2: geometry decides the field, OCR decides the
    characters inside it.
    """
    anchors = find_anchors(boxes, anchor_pattern)

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
        # The label is printed but no value was read in range. Distinct from
        # UNKNOWN: the locus IS reported, we simply could not read it.
        return LocusResolution(
            locus,
            ResolutionStatus.REVIEW_REQUIRED,
            anchor_box=anchor,
            reason="anchor found but no value box within the rule's range",
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

    return LocusResolution(
        locus,
        ResolutionStatus.RESOLVED,
        values=[(b.text or "").strip() for b in found],
        anchor_box=anchor,
        value_boxes=found,
    )
