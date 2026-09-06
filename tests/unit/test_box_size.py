"""A value box that is not the size of its page's other value boxes.

The reviewer's suggestion, and it measures out: on the 561 human labels, a cell
whose box is the usual size for its page is wrong 5% of the time, and one whose
box is unlike the others is wrong 25% of the time. Five times the rate, from a
signal available before anything is read.

Nothing here refuses a cell. The middle group is eight cells, and a gate built
on eight would cost six correct readings to catch two wrong ones. It marks the
box so a reviewer sees it and the next round of labels can settle whether a gate
is right — which is the same discipline every other threshold in this pipeline
was set by.
"""

from __future__ import annotations

import math

from kidneymatch.ocr.anchors import Box
from kidneymatch.ocr.boxsize import (
    MIN_FOR_NORM,
    odd_boxes,
    value_box_norm,
)

HEIGHT = 0.010
WIDTH = 0.060


def value(text: str, index: int, *, height: float = HEIGHT, width: float = WIDTH) -> Box:
    top = 0.10 + index * 0.04
    return Box(x0=0.30, y0=top, x1=0.30 + width, y1=top + height, text=text)


def page(count: int = 5) -> list[Box]:
    """A form printing its alleles in one font, as a laboratory does."""
    texts = ["A*24", "A*02", "B*35", "B*51", "C*04", "DRB1*15", "DQB1*03"]
    return [value(texts[i % len(texts)], i) for i in range(count)]


def test_a_page_of_evenly_printed_values_has_a_norm() -> None:
    norm = value_box_norm(page())
    assert norm is not None
    assert math.isclose(norm.height, HEIGHT, abs_tol=1e-9)
    assert math.isclose(norm.width, WIDTH, abs_tol=1e-9)
    assert norm.counted == 5


def test_a_page_with_too_few_readable_values_has_no_norm() -> None:
    """No norm is not a verdict on a box; it is the pipeline failing to read."""
    assert value_box_norm(page(MIN_FOR_NORM - 1)) is None
    assert value_box_norm([]) is None


def test_labels_and_prose_are_not_part_of_the_norm() -> None:
    """Only boxes that read as an allele say how big a value box is here."""
    mixed = [*page(3), value("HLA-DRB1", 9, height=0.05), value("REPORTED BY", 10, width=0.4)]
    norm = value_box_norm(mixed)
    assert norm is not None
    assert math.isclose(norm.height, HEIGHT, abs_tol=1e-9)
    assert norm.counted == 3


def test_a_box_the_usual_size_is_not_unusual() -> None:
    norm = value_box_norm(page())
    assert norm is not None
    assert norm.unusual(value("A*11", 9)) is None


def test_a_box_stretched_across_rows_is_unusual() -> None:
    norm = value_box_norm(page())
    assert norm is not None
    why = norm.unusual(value("A*11", 9, height=HEIGHT * 2.5))
    assert why is not None
    assert "height" in why


def test_a_box_too_short_to_be_a_line_is_unusual() -> None:
    norm = value_box_norm(page())
    assert norm is not None
    assert norm.unusual(value("A*11", 9, height=HEIGHT * 0.4)) is not None


def test_a_box_wide_enough_to_hold_two_values_is_unusual() -> None:
    norm = value_box_norm(page())
    assert norm is not None
    why = norm.unusual(value("A*11", 9, width=WIDTH * 3))
    assert why is not None
    assert "width" in why


def test_a_two_field_allele_is_wider_without_being_unusual() -> None:
    """`A*24:02` is legitimately longer than `A*24`; the width gate must not
    call every fully-typed value a defect."""
    norm = value_box_norm(page())
    assert norm is not None
    assert norm.unusual(value("A*24:02", 9, width=WIDTH * 1.8)) is None


def test_odd_boxes_names_only_the_ones_that_are_odd() -> None:
    boxes = page()
    stretched = value("A*11", 9, height=HEIGHT * 3)
    ordinary = value("B*07", 10)
    found = odd_boxes([*boxes, stretched, ordinary], [stretched, ordinary])
    assert [box for box, _ in found] == [stretched]


def test_a_page_without_a_norm_calls_nothing_odd() -> None:
    """Silence, not a guess: with no norm there is nothing to be unlike."""
    assert odd_boxes(page(2), [value("A*11", 9, height=HEIGHT * 5)]) == []
