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

Nothing here decides a gene. It reports how much TEXT ink a region holds — dark
pixels in glyph-shaped components, with the table rulings removed — so a pass
can certify a slot BLANK against a threshold calibrated on the columns that
do hold a token. A dash, a placeholder line or a ruling of any tilt is not
glyph-shaped and is not ink here. The paper level is the region's
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
# Ink is counted only in connected components shaped like glyphs: at least
# this tall (a fixed floor, or this share of the region's height, whichever is
# larger) and not `LINE_ASPECT` times wider than tall. A printed dash is
# shorter; a ruling of any tilt, or a placeholder line in an empty cell, is
# far wider than it is tall. Measured on 23,719 empty labelled cells: 17,221
# read as INKED under the plain dark count, most of them under 1% ink with
# runs of 10-30 columns and no height — marks the detector rightly never boxed
# as text.
MIN_GLYPH_PX = 4
MIN_GLYPH_SHARE = 0.2
LINE_ASPECT = 8.0
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


def _text_components(dark, min_height: int, line_aspect: float):  # type: ignore[no-untyped-def]
    """Keep the dark pixels of components shaped like glyphs.

    A glyph's connected component is at least `min_height` tall and not
    line-shaped; a printed dash is shorter than that, and a ruling of any tilt
    is `line_aspect` times wider than it is tall. 8-connected flood fill over
    the dark pixels only, which are a small share of any region.
    """
    rows, cols = dark.shape
    keep = np.zeros_like(dark)
    seen = np.zeros_like(dark)
    ys, xs = np.nonzero(dark)
    for start_y, start_x in zip(ys.tolist(), xs.tolist(), strict=True):
        if seen[start_y, start_x]:
            continue
        stack = [(start_y, start_x)]
        seen[start_y, start_x] = True
        pixels = []
        while stack:
            y, x = stack.pop()
            pixels.append((y, x))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < rows and 0 <= nx < cols and dark[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
        py = [y for y, _ in pixels]
        px = [x for _, x in pixels]
        height = max(py) - min(py) + 1
        width = max(px) - min(px) + 1
        if height >= min_height and width < line_aspect * height:
            for y, x in pixels:
                keep[y, x] = True
    return keep


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
    dark = _text_components(
        dark, max(MIN_GLYPH_PX, int(MIN_GLYPH_SHARE * gray.shape[0])), LINE_ASPECT
    )
    col_any = dark.any(axis=0)
    longest = best = 0
    for inked in col_any:
        best = best + 1 if inked else 0
        longest = max(longest, best)
    return InkMeasure(float(dark.mean()), float(col_any.mean()), int(longest), paper)


# The blank thresholds, calibrated 2026-09-05 on 4,904 columns holding a read
# gene token: none measured under 0.005 ink (2 under 0.01, 4,847 at 0.05 or
# more) and 8 under 0.2 column coverage. A region is BLANK only when ALL three
# hold, each at least 2.5x under the least-inked read token. On the 2,674
# one-token DRB3/4/5 rows measured, 2,141 other columns sat under 0.001 ink
# and 2,192 under 0.05 coverage — paper — while 295 carried 0.02 or more: a
# token no engine read. Both labelled rows the reviewer marked ABSENT measured
# under 0.001.
BLANK_FRACTION = 0.002
BLANK_COVERAGE = 0.05
BLANK_RUN = 6
# Re-measured under the glyph-component filter on 2,806 read-token columns:
# 2,740 at 0.05 or more, 61 under 0.05, 2 under 0.02, 2 under 0.01 — and ONE
# under 0.001, a token too small or faint for the measure. So a slot is called
# paper only when the same measure sees the ink it knows is there on that page
# (the read token, or the label itself) at this much: below it the page's
# print is beyond the measure and the slot is UNMEASURABLE.
CONTROL_FRACTION = 0.005


def classify(measure: InkMeasure | None, control: InkMeasure | None = None) -> str:
    """BLANK (paper), INKED (something is printed there), or UNMEASURABLE.

    `control` is the measure of a region on the same page KNOWN to hold text
    (the read gene token, the locus label). When it is given and reads under
    `CONTROL_FRACTION`, the page's print is beyond this measure, and no slot on
    it may be called paper.
    """
    if measure is None:
        return "UNMEASURABLE"
    if control is not None and control.fraction < CONTROL_FRACTION:
        return "UNMEASURABLE"
    blank = (
        measure.fraction < BLANK_FRACTION
        and measure.coverage < BLANK_COVERAGE
        and measure.longest_run < BLANK_RUN
    )
    return "BLANK" if blank else "INKED"


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
