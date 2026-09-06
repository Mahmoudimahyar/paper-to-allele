"""Finding the pages that were photographed sideways, and turning them.

611 documents in this archive are a quarter turn off upright. None of their
4,888 locus cells is resolved, and none carries a single named locus anchor
against 83.9% of the corpus — so this is a population that can only gain.

The two ways this could go wrong are a metric that does not measure what it
claims, and a rotation chosen on thin evidence. Binding values from a wrongly
turned page reads every locus against the wrong row, which is the worst failure
available here, so the tests below pin both.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from upright_pass import MIN_BOXES, TALL_FRACTION, tall_fraction  # noqa: E402

# A landscape photograph: wider than it is tall.
WIDTH, HEIGHT = 2000, 1000


def test_the_metric_is_measured_in_pixels_not_in_fractions() -> None:
    """The trap this whole idea can die in.

    Stored geometry is normalised to 0-1, so comparing a box's normalised
    height with its normalised width compares a fraction of the page's height
    with a fraction of its width. On a 2000x1000 image an ordinary wide text
    box — 20% of the width, 3% of the height — reads as 0.20 vs 0.03 and looks
    correctly wide; but a box 4% wide and 5% tall is 80px by 50px, genuinely
    WIDER than it is tall, and the normalised comparison calls it tall.
    """
    box = [0.10, 0.10, 0.14, 0.15]  # 80px wide, 50px tall on this page
    assert box[3] - box[1] > box[2] - box[0]  # normalised: looks tall
    assert tall_fraction([box], WIDTH, HEIGHT) == 0.0  # in pixels: it is wide


def test_a_page_of_wide_text_boxes_is_upright() -> None:
    boxes = [[0.10, 0.10 + i * 0.05, 0.40, 0.12 + i * 0.05] for i in range(10)]
    assert tall_fraction(boxes, WIDTH, HEIGHT) == 0.0


def test_a_page_whose_text_runs_down_the_side_is_not_upright() -> None:
    """A quarter turn transposes every box: text that ran across now runs down."""
    boxes = [[0.10 + i * 0.05, 0.10, 0.12 + i * 0.05, 0.40] for i in range(10)]
    assert tall_fraction(boxes, HEIGHT, WIDTH) == 1.0


def test_a_page_with_no_boxes_is_not_called_sideways() -> None:
    """Silence is not evidence of rotation."""
    assert tall_fraction([], WIDTH, HEIGHT) == 0.0


def test_the_thresholds_are_the_measured_ones() -> None:
    """Both were measured, not chosen: the distribution is bimodal (592 of the
    611 selected sit above 0.8), and 8 boxes is the floor below which a page
    has not been read enough to say anything about its orientation."""
    assert TALL_FRACTION == 0.6
    assert MIN_BOXES == 8


def test_a_rotation_must_win_outright_before_anything_is_bound() -> None:
    """The dangerous half. A tie between two rotations, or no anchors at any
    rotation, must leave the page exactly where it was — binding a locus from a
    wrongly turned page reads every value against the wrong row."""
    source = (ROOT / "scripts/upright_pass.py").read_text(encoding="utf-8")
    assert "if best[0] == 0 or best[0] == runner[0]:" in source
    assert "ORIENTATION_SUSPECT" in source


def test_the_bind_refuses_the_geometry_measured_on_the_sideways_image() -> None:
    """The frame, the template family and the row slope were all measured
    before the page was turned. Rectifying an upright reading with a sideways
    frame would place every cell wrong."""
    source = (ROOT / "scripts/upright_bind.py").read_text(encoding="utf-8")
    assert "frame_for" not in source
    assert "load_geometry" not in source
    assert "row_slope=0.0" in source


def test_the_bind_only_touches_cells_that_never_had_an_anchor() -> None:
    """0 of the 4,888 cells on these pages is RESOLVED, and the pass must not
    be able to reach one that is."""
    source = (ROOT / "scripts/upright_bind.py").read_text(encoding="utf-8")
    assert "AND status != 'RESOLVED'" in source
    assert "AND reason = ?" in source
