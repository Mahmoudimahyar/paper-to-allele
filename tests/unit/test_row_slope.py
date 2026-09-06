"""Rows are read along the slope the page prints them at.

A reviewer labelling the pack wrote, against a page every value cell of which
was lost: "This image is tilted and the system failed to recognize that and all
the boxes are situated incorrectly. The system must identify the lines and the
slope of the lines and immediately identify that an image is tilted and draw
its boxes for each loci with that slope."

The slope was measured on that page. `rulings.py` read -3.19 degrees from 35
printed rulings, and the page-level decision threw the number away because the
rulings scattered more than `MAX_MAD_DEG`. Scatter is what perspective does to
a hand-held photograph; it is not evidence that the angle is wrong. These tests
pin the separation: measuring a slope is not rotating a page, so the row test
may use a measurement the rotation declines to act on — and the one thing that
does invalidate the measurement, two grids in one photograph, still refuses.
"""

from __future__ import annotations

import math
from dataclasses import replace

from kidneymatch.ocr.anchors import (
    Box,
    ResolutionStatus,
    ValueRule,
    resolve_locus,
)
from kidneymatch.ocr.geometry import PageFrame
from kidneymatch.ocr.rows import (
    MIN_ROW_SLOPE,
    dominant_angle,
    row_slope,
    segment_angles,
)

WIDTH, HEIGHT = 1000, 1000  # square, so a pixel slope is a normalised slope


def ruling(y: float, degrees: float, *, x0: float = 100.0, span: float = 800.0):
    """One printed ruling, in source pixels, at this angle."""
    return [x0, y, x0 + span, y + span * math.tan(math.radians(degrees))]


def test_a_level_page_measures_no_slope() -> None:
    segments = [ruling(100 + 50 * i, 0.0) for i in range(10)]
    assert row_slope(segments, WIDTH, HEIGHT) == 0.0


def test_a_tilted_page_measures_its_tilt() -> None:
    segments = [ruling(100 + 50 * i, -3.0) for i in range(10)]
    measured = row_slope(segments, WIDTH, HEIGHT)
    assert measured is not None
    assert math.isclose(measured, math.tan(math.radians(-3.0)), abs_tol=1e-6)


def test_scatter_alone_does_not_refuse_the_measurement() -> None:
    """Perspective fans the rulings; that is the camera, not a second grid."""
    segments = [ruling(100 + 50 * i, -3.0 + 0.4 * i) for i in range(10)]
    measured = row_slope(segments, WIDTH, HEIGHT)
    assert measured is not None
    assert measured < -MIN_ROW_SLOPE


def test_two_grids_refuse_the_measurement() -> None:
    """A second form or a frame edge: the median belongs to neither of them."""
    segments = [ruling(100 + 40 * i, -6.0) for i in range(6)]
    segments += [ruling(400 + 40 * i, 6.0) for i in range(6)]
    assert row_slope(segments, WIDTH, HEIGHT) is None


def test_the_dominant_grid_wins_over_a_minority_of_stragglers() -> None:
    """24 rulings at -3 and 11 near zero is a tilted page with a frame edge."""
    angles = [-3.2] * 24 + [0.05] * 11
    dominant = dominant_angle(angles)
    assert dominant is not None
    assert math.isclose(dominant, -3.2, abs_tol=0.1)


def test_a_slope_too_small_to_matter_is_reported_as_level() -> None:
    """Below the floor the shear is smaller than the error in measuring it."""
    tiny = math.degrees(math.atan(MIN_ROW_SLOPE / 2))
    segments = [ruling(100 + 50 * i, tiny) for i in range(10)]
    assert row_slope(segments, WIDTH, HEIGHT) == 0.0


def test_too_few_rulings_measure_nothing() -> None:
    assert row_slope([ruling(100, -3.0), ruling(150, -3.0)], WIDTH, HEIGHT) is None
    assert row_slope([], WIDTH, HEIGHT) is None


def test_columns_are_not_rows() -> None:
    """A vertical ruling says nothing about the slope of the printed lines."""
    vertical = [[500.0, 100.0, 505.0, 900.0] for _ in range(10)]
    assert row_slope(vertical, WIDTH, HEIGHT) is None


def test_the_aspect_ratio_is_carried_into_normalised_coordinates() -> None:
    """Boxes are normalised in x and y separately; a square page is the only
    one where a pixel slope is already a box slope."""
    segments = [ruling(100 + 50 * i, -3.0) for i in range(10)]
    tall = row_slope(segments, 500, 1000)
    square = row_slope(segments, 1000, 1000)
    assert tall is not None and square is not None
    assert math.isclose(tall, square * 0.5, rel_tol=1e-6)


def test_a_rectified_page_reports_only_what_the_rotation_left_behind() -> None:
    """On a rotated page the boxes are levelled, so the rulings must be too."""
    segments = [ruling(100 + 50 * i, -3.0) for i in range(10)]
    frame = PageFrame(theta_deg=-3.0, width=WIDTH, height=HEIGHT)
    residual = row_slope(segments, WIDTH, HEIGHT, frame)
    assert residual == 0.0
    assert segment_angles(segments, frame)


ROW_RULE = ValueRule(direction="right", align_overlap=0.25, max_gap=30.0, max_values=2)
UNIT = 0.01


def sloped_page(slope: float) -> list[Box]:
    """A label at the left and its two values across a row that falls."""

    def box(text: str, x0: float) -> Box:
        top = 0.500 + slope * (x0 - 0.10)
        return Box(x0=x0, y0=top, x1=x0 + 0.07, y1=top + UNIT, text=text)

    return [box("HLA-B", 0.10), box("B*35", 0.40), box("B*51", 0.70)]


def test_a_value_on_a_tilted_row_is_lost_without_the_slope() -> None:
    """The failure the reviewer saw: the row test compares y against y."""
    page = sloped_page(-0.05)
    assert resolve_locus(page, "B", ROW_RULE).status is not ResolutionStatus.RESOLVED


def test_the_same_value_is_bound_when_the_row_is_read_along_its_slope() -> None:
    page = sloped_page(-0.05)
    result = resolve_locus(page, "B", replace(ROW_RULE, row_slope=-0.05))
    assert result.status is ResolutionStatus.RESOLVED
    assert result.values == ["B*35", "B*51"]


def test_a_level_page_is_unaffected_by_carrying_a_zero_slope() -> None:
    page = sloped_page(0.0)
    flat = resolve_locus(page, "B", ROW_RULE)
    zero = resolve_locus(page, "B", replace(ROW_RULE, row_slope=0.0))
    assert flat.status is ResolutionStatus.RESOLVED
    assert flat.values == zero.values
