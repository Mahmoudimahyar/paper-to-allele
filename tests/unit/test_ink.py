"""Ink on the page: blank cells are paper, unread tokens are ink, rulings are neither."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from kidneymatch.ocr.ink import ColumnRegion, column_regions, ink_measure

pytestmark = pytest.mark.task("OCR-001")


def cell(text: str | None, *, rulings: bool = True, paper: int = 245) -> np.ndarray:
    """A synthetic table cell, 120x40, optionally with a printed token and rulings."""
    image = Image.new("L", (120, 40), paper)
    draw = ImageDraw.Draw(image)
    if rulings:
        draw.line([(0, 0), (119, 0)], fill=0, width=2)
        draw.line([(0, 39), (119, 39)], fill=0, width=2)
        draw.line([(0, 0), (0, 39)], fill=0, width=2)
    if text:
        draw.text((30, 10), text, fill=0, font=ImageFont.load_default(size=18))
    return np.asarray(image)


def test_a_blank_cell_measures_as_paper_even_with_its_rulings() -> None:
    measure = ink_measure(cell(None))
    assert measure is not None
    assert measure.fraction < 0.002
    assert measure.coverage < 0.05
    assert measure.longest_run <= 2


def test_a_printed_token_measures_as_ink() -> None:
    measure = ink_measure(cell("DRB4"))
    assert measure is not None
    assert measure.fraction > 0.02
    assert measure.coverage > 0.2
    assert measure.longest_run >= 8  # the width of a glyph, not a speck


def test_rulings_alone_never_count_as_ink() -> None:
    with_rulings = ink_measure(cell(None, rulings=True))
    without = ink_measure(cell(None, rulings=False))
    assert with_rulings is not None and without is not None
    assert abs(with_rulings.fraction - without.fraction) < 0.001


def test_a_region_with_no_paper_level_is_unmeasurable() -> None:
    """A shadow or a stamp: nothing to measure against, so nothing is claimed."""
    assert ink_measure(cell(None, paper=90)) is None
    assert ink_measure(np.zeros((5, 5), dtype=np.uint8)) is None


def test_the_columns_come_from_the_drb1_row_and_the_band_from_the_token() -> None:
    drb1 = [[0.60, 0.40, 0.70, 0.43], [0.30, 0.40, 0.40, 0.43]]  # right box listed first
    gene = [[0.31, 0.50, 0.39, 0.53]]  # the read token sits in the left column
    regions = column_regions(drb1, gene)
    assert [r.column for r in regions] == [0, 1]
    assert regions[0].occupied is True and regions[1].occupied is False
    left, right = regions[0].box, regions[1].box
    assert left[0] < 0.30 < 0.40 < left[2], "widened by the margin on each side"
    assert right[0] < 0.60 < 0.70 < right[2]
    assert left[1] < 0.50 and left[3] > 0.53, "the band is the token's box grown by the margin"
    assert left[1] == right[1] and left[3] == right[3]


def test_a_pair_token_occupies_one_column_and_two_tokens_both() -> None:
    drb1 = [[0.30, 0.40, 0.40, 0.43], [0.60, 0.40, 0.70, 0.43]]
    both = column_regions(drb1, [[0.31, 0.50, 0.39, 0.53], [0.61, 0.50, 0.69, 0.53]])
    assert [r.occupied for r in both] == [True, True]
    one = column_regions(drb1, [[0.61, 0.50, 0.69, 0.53]])
    assert [r.occupied for r in one] == [False, True]


def test_without_two_drb1_boxes_there_is_no_geometry() -> None:
    assert column_regions([[0.3, 0.4, 0.4, 0.43]], [[0.31, 0.5, 0.39, 0.53]]) == []
    assert column_regions([[0.3, 0.4, 0.4, 0.43], [0.6, 0.4, 0.7, 0.43]], []) == []
    assert isinstance(
        column_regions([[0.3, 0.4, 0.4, 0.43], [0.6, 0.4, 0.7, 0.43]], [[0.31, 0.5, 0.39, 0.53]])[
            0
        ],
        ColumnRegion,
    )
