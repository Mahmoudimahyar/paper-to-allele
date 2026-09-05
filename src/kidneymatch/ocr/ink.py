"""Is a printed cell blank? Ink, measured on the page, not inferred.

The grouped DRB3/4/5 row (`drbx.py`) reads one gene token on 6,122 cells
corpus-wide and must then leave the other genes UNKNOWN: "the row printed one
gene" and "the row printed one gene and the other slot is empty" are different
claims, and calling the slot empty because nothing was READ there is wrong
5.9% of the time by the DRB1-concordance measurement. What separates the two
claims is pixels — an unread token is ink, an empty cell is paper — and this
module measures that, for a cell whose location is known from the form's own
structure (the DRB1 row directly above prints its two alleles in the same two
columns).

Nothing here decides a gene. It reports how much ink a region holds, with the
table rulings removed, so a pass can certify a slot BLANK against a threshold
calibrated on the columns that do hold a token. The paper level is the region's
own median; a region too dark to have a paper level (a photograph's shadow, a
stamp) is unmeasurable and stays UNKNOWN.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

# A pixel is ink when it is this much darker than the region's paper (0-255).
DARK_BELOW_PAPER = 60
# A row or column of the region that is this dark across its length is a
# table ruling, not text, and is removed before counting.
RULING_FRACTION = 0.6
# Below this paper level the region has no white to measure against.
MIN_PAPER = 120
# A column region is widened by this share of its width on each side, so a
# token printed a little off the DRB1 column still falls inside it.
COLUMN_MARGIN = 0.15
# The row band is the read token's box grown by this share of its height on
# each side.
ROW_MARGIN = 0.25
# A gene box covering at least this share of its own width inside a column
# region places the token in that column.
OCCUPIED_OVERLAP = 0.3


@dataclass(frozen=True, slots=True)
class InkMeasure:
    """What a region holds, after its rulings are removed."""

    fraction: float  # dark pixels over all pixels
    coverage: float  # share of pixel columns holding any dark pixel
    longest_run: int  # the longest run of consecutive inked pixel columns
    paper: float  # the region's median grey level


def ink_measure(gray: NDArray[np.uint8]) -> InkMeasure | None:
    """Measure the ink in a greyscale region; None when it cannot be measured."""
    if gray.ndim != 2 or gray.size < 100:
        return None
    paper = float(np.median(gray))
    if paper < MIN_PAPER:
        return None
    dark = gray < paper - DARK_BELOW_PAPER
    rulings_r = dark.mean(axis=1) > RULING_FRACTION
    rulings_c = dark.mean(axis=0) > RULING_FRACTION
    dark[rulings_r, :] = False
    dark[:, rulings_c] = False
    col_any = dark.any(axis=0)
    longest = best = 0
    for inked in col_any:
        best = best + 1 if inked else 0
        longest = max(longest, best)
    return InkMeasure(float(dark.mean()), float(col_any.mean()), int(longest), paper)


@dataclass(frozen=True, slots=True)
class ColumnRegion:
    """One value column of the grouped row, in normalised page coordinates."""

    column: int  # 0 or 1, left to right
    box: tuple[float, float, float, float]
    occupied: bool  # a read gene token sits in it


def column_regions(
    drb1_boxes: list[list[float]] | list[tuple[float, ...]],
    gene_boxes: list[list[float]] | list[tuple[float, ...]],
) -> list[ColumnRegion]:
    """The grouped row's two value columns, from the DRB1 row's two value boxes.

    The DRB1 row directly above prints its two alleles in the same two columns
    the grouped row uses for its gene names, so its resolved value boxes give
    the columns' x-extent; the row band comes from the gene token actually
    read. Two DRB1 boxes and at least one gene box are required, otherwise
    there is no geometry to measure in and the answer is no regions.
    """
    if len(drb1_boxes) != 2 or not gene_boxes:
        return []
    columns = sorted((tuple(float(v) for v in b) for b in drb1_boxes), key=lambda b: b[0])
    genes = [tuple(float(v) for v in b) for b in gene_boxes]
    y0 = min(g[1] for g in genes)
    y1 = max(g[3] for g in genes)
    pad = ROW_MARGIN * (y1 - y0)
    y0, y1 = max(0.0, y0 - pad), min(1.0, y1 + pad)
    regions: list[ColumnRegion] = []
    for index, column in enumerate(columns):
        width = column[2] - column[0]
        box = (
            max(0.0, column[0] - COLUMN_MARGIN * width),
            y0,
            min(1.0, column[2] + COLUMN_MARGIN * width),
            y1,
        )
        occupied = any(
            min(box[2], g[2]) - max(box[0], g[0]) > OCCUPIED_OVERLAP * (g[2] - g[0]) for g in genes
        )
        regions.append(ColumnRegion(index, box, occupied))
    return regions
