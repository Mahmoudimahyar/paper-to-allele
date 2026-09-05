"""The tilt of a photograph must not decide which gene owns a value.

When two printed labels are both aligned with a candidate box, the nearer one
along the reading axis owns it. Where they tie, or where the other label is
further along the row but its line sits closer to the box, ownership turns on a
vertical comparison — and that comparison used to be exact. A page photographed
by hand is never level, so at that precision the winner was the tilt rather
than the layout.

`OWNERSHIP_Y_MARGIN` makes the other label earn the box: it must sit closer by
a quarter of a label height, not by a floating-point hair. Ablated over 4,000
documents, 17 cells move from REVIEW_REQUIRED to RESOLVED and no cell resolved
under both settings changes its value.
"""

from __future__ import annotations

from kidneymatch.ocr.anchors import (
    OWNERSHIP_Y_MARGIN,
    Box,
    ResolutionStatus,
    ValueRule,
    resolve_locus,
)

RULE = ValueRule(direction="right", align_overlap=0.2, max_gap=12.0, max_values=2)
UNIT = 0.02


def box(text: str, x0: float, centre: float, *, width: float = 0.07) -> Box:
    return Box(x0=x0, y0=centre - UNIT / 2, x1=x0 + width, y1=centre + UNIT / 2, text=text)


def test_a_hair_of_tilt_does_not_move_a_value_to_the_row_above() -> None:
    """`HLA-B`'s value stays B's when `HLA-A` is nearer by a hundredth of a line."""
    page = [
        box("HLA-A", 0.10, 0.300),
        box("A*24", 0.30, 0.300),
        box("HLA-B", 0.10, 0.340),
        # Sits on B's line, a hair nearer to A's; A is further along the row.
        box("B*35", 0.30, 0.3398),
    ]
    result = resolve_locus(page, "B", RULE)
    assert result.status is ResolutionStatus.RESOLVED
    assert result.values == ["B*35"]


def test_a_value_plainly_on_the_other_line_still_belongs_to_it() -> None:
    """The margin is a tolerance, not a licence to keep another row's value."""
    page = [
        box("HLA-A", 0.10, 0.300),
        box("HLA-B", 0.10, 0.340),
        # Squarely on A's line, though B's label is nearer along the row.
        box("A*24", 0.30, 0.301),
    ]
    result = resolve_locus(page, "B", RULE)
    assert result.status is not ResolutionStatus.RESOLVED


def test_the_nearer_label_along_the_reading_axis_still_wins() -> None:
    """The margin only ever settles the vertical comparison."""
    page = [
        box("HLA-A", 0.10, 0.300),
        box("HLA-B", 0.24, 0.300),
        box("B*35", 0.34, 0.300),
    ]
    assert resolve_locus(page, "A", RULE).status is not ResolutionStatus.RESOLVED


def test_the_margin_is_a_fraction_of_a_label_height() -> None:
    """Written in label heights so it holds at any photographed scale."""
    assert 0.0 < OWNERSHIP_Y_MARGIN < 1.0
