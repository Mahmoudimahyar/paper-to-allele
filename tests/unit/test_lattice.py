"""The printed table as a grid: rows between rulings, cells between verticals."""

from __future__ import annotations

import pytest

from kidneymatch.ocr.geometry import PageFrame
from kidneymatch.ocr.lattice import Lattice, RowBand

pytestmark = pytest.mark.task("OCR-001")

W, H = 1000, 1300
# A table: horizontal rulings every 60 px from y=200, spanning x 100..900;
# verticals at x = 100, 300, 600, 900 spanning y 200..500.
H_SEGS = [[100, y, 900, y] for y in range(200, 501, 60)]
V_SEGS = [[x, 200, x, 500] for x in (100, 300, 600, 900)]
LABEL_H = 25 / H


def lattice(frame: PageFrame | None = None) -> Lattice:
    return Lattice.from_segments(H_SEGS, V_SEGS, W, H, frame)


def test_a_point_between_two_rulings_gets_its_row() -> None:
    band = lattice().row_band(200 / W, 230 / H, LABEL_H)
    assert band is not None
    assert band.top == pytest.approx(200 / H) and band.bottom == pytest.approx(260 / H)
    assert band.contains_y(230 / H)
    assert band.left == pytest.approx(100 / W) and band.right == pytest.approx(900 / W)


def test_a_point_on_a_ruling_belongs_to_the_row_below_it() -> None:
    band = lattice().row_band(200 / W, 260 / H, LABEL_H)
    assert band is not None and band.top == pytest.approx(260 / H)


def test_the_rulings_must_span_the_point() -> None:
    assert lattice().row_band(950 / W, 230 / H, LABEL_H) is None, "past the table's right edge"
    assert lattice().row_band(200 / W, 100 / H, LABEL_H) is None, "above the table"
    assert lattice().row_band(200 / W, 600 / H, LABEL_H) is None, "below the table"


def test_a_band_out_of_scale_with_the_label_is_not_a_row() -> None:
    tall = Lattice.from_segments([[100, 200, 900, 200], [100, 500, 900, 500]], V_SEGS, W, H)
    assert tall.row_band(200 / W, 300 / H, LABEL_H) is None, "300 px for a 25 px label is a block"
    double = Lattice.from_segments([[100, 200, 900, 200], [100, 206, 900, 206]], V_SEGS, W, H)
    assert double.row_band(200 / W, 203 / H, LABEL_H) is None, "6 px is a double line"


def test_the_cell_to_the_right_is_between_the_next_two_verticals() -> None:
    band = RowBand(200 / H, 260 / H)
    assert lattice().verticals_crossing(band, 150 / W) == pytest.approx([300 / W, 600 / W, 900 / W])
    cell = lattice().cell_right_of(band, 350 / W)
    assert cell == pytest.approx((600 / W, 900 / W))
    assert lattice().cell_right_of(band, 700 / W) is None, "one vertical left: no cell"


def test_verticals_that_do_not_cross_the_band_do_not_count() -> None:
    band = RowBand(700 / H, 760 / H)  # below the table's verticals
    assert lattice().verticals_crossing(band) == []


def test_the_grid_is_levelled_with_the_page() -> None:
    """On a ROTATE page the boxes are rotated into the level frame; the rulings
    must go through the same rotation or the grid and the boxes disagree."""
    frame = PageFrame(3.0, W, H)
    levelled = lattice(frame)
    raw = lattice()
    assert levelled.horizontal[0].at != pytest.approx(raw.horizontal[0].at, abs=1e-6)
    x, y = frame.rotate_pixel(500, 200)
    assert levelled.horizontal[0].at == pytest.approx(y / H, abs=2e-3), (
        "the ruling's centre follows"
    )
    assert levelled.horizontal[0].start == pytest.approx(
        frame.rotate_pixel(100, 200)[0] / W, abs=1e-3
    )
