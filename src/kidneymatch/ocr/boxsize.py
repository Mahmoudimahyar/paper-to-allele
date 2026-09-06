"""A value box that is not the size of its page's other value boxes.

The reviewer, on how to find a bad crop without reading it: "when we make
rectangle around the alleles to crop them, most of the time all of them should
have the same size, so the length and width should be almost the same for all of
them. so if we see one or two of them have unusually short length or very large
width we may want to assume that the shape is different."

That is right, and it is measurable. A laboratory prints its allele values in
one font at one size, so their boxes agree closely; a box that does not agree is
usually the detector's mistake rather than the printer's — two tokens merged
into one, a value clipped by a ruling, or a box stretched across rows.

Measured against the 561 human labels, on cells the pipeline did not abstain on:

    the cell's box is the usual size for its page    250 correct, 5% wrong
    the cell's box is unlike the page's others         6 correct, 25% wrong
    the page has no consistent value-box size at all  54 correct, 36% wrong

Five times the error rate, on a signal available before anything is read. The
third row is the larger group and a different finding: a page where fewer than
three boxes parse as an allele has no norm to compare against, and that page is
usually one the pipeline is failing on for other reasons.

The count is small (eight cells in the middle row), so nothing here REFUSES a
cell. It marks one, so that a reviewer sees it and the next round of labels can
say whether refusing would be right. A gate built on eight cells would cost six
correct readings to catch two wrong ones.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from kidneymatch.ocr.anchors import Box
from kidneymatch.ocr.glyphs import parse_allele_values

# A page needs this many boxes that parse as an allele before their median means
# anything. Below it there is no norm, and no box can be called unusual.
MIN_FOR_NORM = 3
# How far a box may sit from its page's median and still be ordinary. Height
# first, because a printed line's height is the most stable thing on the page;
# width is looser, since a two-field allele is legitimately wider than a
# first-field one.
MAX_HEIGHT_RATIO = 1.6
MIN_HEIGHT_RATIO = 0.6
MAX_WIDTH_RATIO = 2.2


@dataclass(frozen=True, slots=True)
class BoxNorm:
    """What a value box on this page usually measures."""

    height: float
    width: float
    counted: int

    def unusual(self, box: Box) -> str | None:
        """Why this box is not the size of its page's others, or None."""
        if self.height <= 0 or self.width <= 0:
            return None
        tall = box.height / self.height
        wide = (box.x1 - box.x0) / self.width
        if tall > MAX_HEIGHT_RATIO:
            return f"{tall:.1f}x the height of this page's other value boxes"
        if tall < MIN_HEIGHT_RATIO:
            return f"{tall:.1f}x the height of this page's other value boxes"
        if wide > MAX_WIDTH_RATIO:
            return f"{wide:.1f}x the width of this page's other value boxes"
        return None


def value_box_norm(boxes: Sequence[Box]) -> BoxNorm | None:
    """The median size of the boxes on this page that read as an allele.

    `None` when too few do. That is not a defect in the page — it is the
    pipeline saying it cannot read this one, which is a different problem and
    the one the third row of the table above counts.
    """
    heights: list[float] = []
    widths: list[float] = []
    for box in boxes:
        if not parse_allele_values((box.text or "").strip()):
            continue
        heights.append(box.height)
        widths.append(box.x1 - box.x0)
    if len(heights) < MIN_FOR_NORM:
        return None
    return BoxNorm(statistics.median(heights), statistics.median(widths), len(heights))


def odd_boxes(boxes: Sequence[Box], among: Sequence[Box]) -> list[tuple[Box, str]]:
    """Which of `among` are not the size of the page's other value boxes."""
    norm = value_box_norm(boxes)
    if norm is None:
        return []
    found = []
    for box in among:
        why = norm.unusual(box)
        if why is not None:
            found.append((box, why))
    return found
