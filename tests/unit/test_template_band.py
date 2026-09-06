"""Placing a label the recognizer could not read, on a page with no ruling there.

`bind_in_lattice` places a virtual label from the form's template and reads the
row around it. It used to require a printed ruling at that spot and abstain
otherwise, which refused 2,439 cells whose template fit was inside
`MAX_TEMPLATE_RESIDUAL` — a good fit on a page that simply prints no line there.

The band now comes from the label's own height instead. Two measurements make
that safe rather than hopeful. The row pitch of these templates is a median
3.35 to 3.38 label heights, so a band of plus or minus 1.5 spans nine tenths of
one row and two adjacent bands never touch; and the path runs only under the
family rule, where every value carries its own locus prefix, so a value taken
from the wrong row names another locus and gate 2 refuses it.

What is refused outright is a placement the page's own grid contradicts: no
ruling around the LABEL is not evidence against it, but a ruling around the
VALUE that excludes the label is. Measured, 31 of 491 fell that way against 4
of the 1,698 the ruled path already binds.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from extract_facts import TEMPLATE_BAND_HEIGHTS, _grid_contradicts  # noqa: E402

from kidneymatch.ocr.anchors import Box  # noqa: E402
from kidneymatch.ocr.lattice import Lattice, RowBand, Ruling  # noqa: E402

LABEL_H = 0.01


def band_at(y: float) -> RowBand:
    half = TEMPLATE_BAND_HEIGHTS * LABEL_H
    return RowBand(y - half, y + half)


def rulings(*ys: float) -> Lattice:
    """A level printed grid with a ruling at each y, spanning the page."""
    return Lattice(tuple(Ruling(0.0, 1.0, y, y) for y in ys), ())


def value(x: float, y: float) -> Box:
    return Box(x0=x, y0=y - LABEL_H / 2, x1=x + 0.06, y1=y + LABEL_H / 2, text="A*24")


def test_a_page_with_no_grid_at_all_contradicts_nothing() -> None:
    """No ruling around the label is not evidence against the placement."""
    lattice = rulings()
    assert not _grid_contradicts(
        lattice, [value(0.40, 0.500)], 0.10, 0.500, LABEL_H, band_at(0.500)
    )


def test_a_row_that_contains_the_placed_label_agrees_with_it() -> None:
    lattice = rulings(0.490, 0.512)
    assert not _grid_contradicts(
        lattice, [value(0.40, 0.500)], 0.10, 0.500, LABEL_H, band_at(0.500)
    )


def test_a_row_around_the_value_that_excludes_the_label_refuses_it() -> None:
    """The page says this value belongs to a row the label is not on."""
    lattice = rulings(0.570, 0.595)
    candidate = value(0.40, 0.582)
    assert _grid_contradicts(lattice, [candidate], 0.10, 0.500, LABEL_H, RowBand(0.400, 0.600))


def test_a_box_outside_the_band_says_nothing_about_the_placement() -> None:
    """Only what the band would actually bind can contradict the band."""
    lattice = rulings(0.770, 0.795)
    assert not _grid_contradicts(
        lattice, [value(0.40, 0.780)], 0.10, 0.500, LABEL_H, band_at(0.500)
    )


def test_a_box_left_of_the_label_is_not_one_of_its_values() -> None:
    """The rule reads rightwards; what sits left of the label is another cell."""
    lattice = rulings(0.570, 0.595)
    left = value(0.02, 0.500)
    assert not _grid_contradicts(lattice, [left], 0.10, 0.500, LABEL_H, band_at(0.500))


def test_the_band_is_narrower_than_the_row_pitch_it_sits_in() -> None:
    """Measured pitch is 3.35-3.38 label heights; two bands must not touch."""
    assert 2 * TEMPLATE_BAND_HEIGHTS < 3.35
