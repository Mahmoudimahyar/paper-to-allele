"""Which way does this form read? Ask the page, do not assume.

The dominant layout on this corpus is a vertical stack of locus labels with the
values to the right of each, and the resolver assumes it. Some forms do not do
that. A reviewer labelling the pack wrote, of one page every Class I value of
which went unread: "This lab report has totally different structure. Instead of
writing the loci and then the alleles in front of it, it writes each allele in
the cell under the loci."

Read whole, that page prints `HLA-A`, `HLA-B` and `HLA-C` side by side on one
line, each with its value in the same column directly beneath. Nothing about
its glyphs says so; its geometry says so plainly, and the geometry is what the
reviewer described how to read:

    "first we need to know how much is the tilt of the image, in another word
    we need to know the slope. Then we need to find the loci names. Then we
    should detect the orientations of these loci names. Are they on the same
    row meaning if we draw a horizontal line with the same slope as other
    horizontal lines in the image, it can reach another loci name or we need to
    make the vertical line to achieve that? how about alleles, if we draw a
    horizontal line from the loci can we reach the respective alleles?"

That is this module, in that order. `ocr/rows.py` supplies the slope, `ocr/
anchors.py` supplies the locus names, and what follows asks two questions of
them:

1. **How are the loci themselves arranged?** Drawing a line at the page's own
   slope from one locus name, does it reach another? Then the loci are printed
   side by side and they are column HEADERS. Does it take a line down the
   page's own column lean instead? Then they are stacked and they are ROW
   labels.
2. **Where do the values sit?** From each locus name, is there something
   allele-shaped along its row, or under it in its column?

Both must agree before the direction changes, and `right` is what a page gets
whenever it does not say otherwise: it is the layout of the overwhelming
majority, and a form read the wrong way round binds one locus's value to
another, which is the worst failure this project can produce.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from kidneymatch.ocr.anchors import Box, locus_anchors
from kidneymatch.ocr.glyphs import parse_allele_values

Direction = Literal["right", "below"]

# Two locus labels are on one printed line when, after following the page's
# slope from one to the other, their centres sit within this many label heights.
ROW_TOLERANCE = 1.0
# ...and in one column when their x extents, after following the column's lean,
# still overlap by this share of the narrower label.
COLUMN_OVERLAP = 0.3
# How far along a row, and how far down a column, this module will look for a
# value. Both in label heights, and both deliberately generous: it is asking
# whether the form puts values there at all, not binding one.
VALUE_REACH = 30.0
VALUE_DROP = 8.0
# A page must print at least this many locus labels before its arrangement is
# evidence of anything, and at least this many pairs must share a line before
# the labels are called headers.
MIN_ANCHORS = 3
MIN_HEADER_PAIRS = 2


@dataclass(frozen=True, slots=True)
class Layout:
    """Which way a form reads, and the counts that decided it."""

    direction: Direction
    reason: str
    loci_sharing_a_row: int = 0
    loci_sharing_a_column: int = 0
    values_along_the_row: int = 0
    values_under_the_label: int = 0

    @property
    def is_default(self) -> bool:
        return self.direction == "right"


def _lift(row_slope: float, first: Box, second: Box) -> float:
    """How far the printed row has fallen between these two boxes."""
    return row_slope * (second.centre_x - first.centre_x)


def _drift(column_slope: float, first: Box, second: Box) -> float:
    """How far the printed column has leaned between these two boxes."""
    return column_slope * (second.centre_y - first.centre_y)


def share_a_row(first: Box, second: Box, row_slope: float = 0.0) -> bool:
    """Would a line at the page's slope, drawn from one, reach the other?

    They must also stand apart along the line: two boxes stacked on top of one
    another overlap in x, and whatever else they are, they are not side by side.
    """
    if min(first.x1, second.x1) - max(first.x0, second.x0) > 0:
        return False
    offset = abs(second.centre_y - _lift(row_slope, first, second) - first.centre_y)
    return offset <= ROW_TOLERANCE * max(first.height, second.height)


def share_a_column(first: Box, second: Box, column_slope: float = 0.0) -> bool:
    """Would a line down the page's own column lean reach the other?"""
    if abs(second.centre_y - first.centre_y) <= ROW_TOLERANCE * max(first.height, second.height):
        return False
    drift = _drift(column_slope, first, second)
    left, right = second.x0 - drift, second.x1 - drift
    overlap = min(first.x1, right) - max(first.x0, left)
    narrower = min(first.x1 - first.x0, right - left)
    return narrower > 0 and overlap / narrower >= COLUMN_OVERLAP


def value_along_the_row(anchor: Box, boxes: list[Box], row_slope: float = 0.0) -> bool:
    """Is anything allele-shaped to the right of this label, on its own line?"""
    return any(
        box is not anchor
        and box.x0 > anchor.x1
        and box.x0 - anchor.x1 <= VALUE_REACH * anchor.height
        and abs(box.centre_y - _lift(row_slope, anchor, box) - anchor.centre_y)
        <= ROW_TOLERANCE * anchor.height
        and parse_allele_values((box.text or "").strip())
        for box in boxes
    )


def value_under_the_label(anchor: Box, boxes: list[Box], column_slope: float = 0.0) -> bool:
    """Is anything allele-shaped below this label, in its own column?"""
    for box in boxes:
        if box is anchor or box.y0 <= anchor.y1:
            continue
        if box.y0 - anchor.y1 > VALUE_DROP * anchor.height:
            continue
        drift = _drift(column_slope, anchor, box)
        left, right = box.x0 - drift, box.x1 - drift
        overlap = min(anchor.x1, right) - max(anchor.x0, left)
        narrower = min(anchor.x1 - anchor.x0, right - left)
        if narrower <= 0 or overlap / narrower < COLUMN_OVERLAP:
            continue
        if parse_allele_values((box.text or "").strip()):
            return True
    return False


def reading_direction(
    boxes: list[Box], row_slope: float = 0.0, column_slope: float = 0.0
) -> Layout:
    """Which way this page prints its values, measured rather than assumed."""
    anchors = [box for _, box in locus_anchors(boxes)]
    if len(anchors) < MIN_ANCHORS:
        return Layout("right", f"only {len(anchors)} locus labels; too few to read a layout")

    rows = columns = 0
    for index, first in enumerate(anchors):
        for second in anchors[index + 1 :]:
            if share_a_row(first, second, row_slope):
                rows += 1
            elif share_a_column(first, second, column_slope):
                columns += 1

    along = sum(1 for anchor in anchors if value_along_the_row(anchor, boxes, row_slope))
    under = sum(1 for anchor in anchors if value_under_the_label(anchor, boxes, column_slope))

    counted = Layout(
        "right",
        "",
        loci_sharing_a_row=rows,
        loci_sharing_a_column=columns,
        values_along_the_row=along,
        values_under_the_label=under,
    )
    if rows >= MIN_HEADER_PAIRS and rows > columns and under > along:
        return Layout(
            "below",
            f"{rows} pairs of locus labels share a line against {columns} sharing a column, "
            f"and {under} labels have a value beneath them against {along} beside them: "
            "the labels are column headers",
            rows,
            columns,
            along,
            under,
        )
    return (
        Layout(
            "right",
            f"{columns} pairs of locus labels share a column against {rows} sharing a line; "
            "values are read along the row",
            rows,
            columns,
            along,
            under,
        )
        if counted
        else counted
    )
