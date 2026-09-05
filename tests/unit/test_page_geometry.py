"""Rotate the geometry, not the pixels: the page frame the row rules run in.

Written before the implementation. `anchors.py` binds a value to its locus by
the printed ROW — vertical overlap with the label, or a centre band — and a
row on a tilted photograph is not a horizontal band. Measured on the
150-document review pack, 53 pages rotate by half a degree or more; the family
rule's second allele column (8-25 label heights to the right) leaves the band
at about 2-3 degrees and the DRB3/4/5 second column at about 1.4.

The frame straightens the STORED boxes — a rotation of their centres and a
de-inflation of their axis-aligned hulls — so every existing rule runs
unchanged on a level page, and provenance is restored to the boxes as stored.
No pixel moves here; pixels are rotated later, per crop, only where a page was
declared ROTATE.
"""

from __future__ import annotations

import math

import pytest

from kidneymatch.ocr.anchors import Box, ResolutionStatus, ValueRule, resolve_locus
from kidneymatch.ocr.drbx import GeneCall, resolve_grouped_drbx
from kidneymatch.ocr.geometry import PageFrame, restore, restore_drbx
from kidneymatch.ocr.rulings import rotation_matrix

pytestmark = pytest.mark.task("OCR-001")

WIDTH, HEIGHT = 1000, 1400

# The dominant form: the locus printed on every value, the second allele far
# along the row. `test_anchor_resolution.py`'s fixture, stretched to the row
# width the family rule actually reads.
LABEL = Box(0.10, 0.50, 0.18, 0.53, "DRB1")
FIRST = Box(0.22, 0.50, 0.30, 0.53, "DRB1*15")
SECOND = Box(0.70, 0.50, 0.78, 0.53, "DRB1*11")
OTHER_ROW = Box(0.22, 0.60, 0.30, 0.63, "DRB1*07")
FAMILY_RULE = ValueRule(
    direction="right",
    align_overlap=0.2,
    max_gap=None,
    max_values=2,
    centre_band=1.9,
    require_prefix=True,
)


def tilt(box: Box, phi_deg: float) -> Box:
    """What the detector returns for this box on a page whose content was
    rotated counter-clockwise by `phi_deg`: the axis-aligned hull of the
    rotated corners."""
    frame = PageFrame(theta_deg=phi_deg, width=WIDTH, height=HEIGHT)
    corners = [(box.x0, box.y0), (box.x1, box.y0), (box.x1, box.y1), (box.x0, box.y1)]
    moved = [frame.rotate_pixel(x * WIDTH, y * HEIGHT) for x, y in corners]
    xs = [p[0] / WIDTH for p in moved]
    ys = [p[1] / HEIGHT for p in moved]
    return Box(min(xs), min(ys), max(xs), max(ys), box.text)


def straightening(phi_deg: float) -> PageFrame:
    """The frame that undoes a counter-clockwise content rotation of `phi_deg`."""
    return PageFrame(theta_deg=-phi_deg, width=WIDTH, height=HEIGHT)


# --- the frame itself ---------------------------------------------------------


def test_the_identity_frame_returns_the_very_same_boxes() -> None:
    frame = PageFrame.identity(WIDTH, HEIGHT)
    boxes = [LABEL, FIRST]
    rectified, back = frame.rectify(boxes)
    assert rectified[0] is LABEL and rectified[1] is FIRST
    assert back[id(rectified[0])] is LABEL


def test_the_frame_rotates_points_exactly_as_the_pixel_transform_does() -> None:
    """Boxes and crops must never disagree about where the page went."""
    theta = 9.0
    frame = PageFrame(theta_deg=theta, width=WIDTH, height=HEIGHT)
    matrix, _, _ = rotation_matrix(WIDTH, HEIGHT, theta, expand=False)
    for x, y in ((100.0, 150.0), (900.0, 1300.0), (500.0, 700.0)):
        expected = matrix @ [x, y, 1.0]
        got = frame.rotate_pixel(x, y)
        assert math.dist(got, (float(expected[0]), float(expected[1]))) < 1e-6


@pytest.mark.parametrize("phi", [3.0, 7.0, 14.0, -5.0])
def test_rectifying_a_tilted_box_recovers_the_printed_box(phi: float) -> None:
    """Centre and size within a pixel or two: the hull of a rotated rectangle
    is inflated, and the frame de-inflates it rather than compounding it."""
    rectified = straightening(phi).rectify_box(tilt(SECOND, phi))
    assert rectified.centre_x * WIDTH == pytest.approx(SECOND.centre_x * WIDTH, abs=1.0)
    assert rectified.centre_y * HEIGHT == pytest.approx(SECOND.centre_y * HEIGHT, abs=1.0)
    assert (rectified.x1 - rectified.x0) * WIDTH == pytest.approx(
        (SECOND.x1 - SECOND.x0) * WIDTH, abs=2.0
    )
    assert (rectified.y1 - rectified.y0) * HEIGHT == pytest.approx(
        (SECOND.y1 - SECOND.y0) * HEIGHT, abs=2.0
    )
    assert rectified.text == SECOND.text


def test_a_hull_that_cannot_be_deinflated_is_left_alone() -> None:
    """A box narrower than its tilt allows is not a rotated rectangle; keep it."""
    odd = Box(0.50, 0.50, 0.505, 0.60, "|")  # 5 px wide, 140 px tall
    frame = PageFrame(theta_deg=-20.0, width=WIDTH, height=HEIGHT)
    rectified = frame.rectify_box(odd)
    assert (rectified.x1 - rectified.x0) * WIDTH == pytest.approx(5.0, abs=0.5)
    assert (rectified.y1 - rectified.y0) * HEIGHT == pytest.approx(140.0, abs=0.5)


# --- what it buys the row rules -----------------------------------------------


@pytest.mark.parametrize("phi", [12.0, 14.0])
def test_a_tilted_page_loses_its_second_allele_without_the_frame(phi: float) -> None:
    """The measured failure: the second column drifts out of the row band.

    On this fixture the family rule's centre band (1.9 inflated label heights)
    is crossed at about 10 degrees; the cases here sit clearly past it.
    """
    boxes = [tilt(b, phi) for b in (LABEL, FIRST, SECOND, OTHER_ROW)]
    result = resolve_locus(boxes, "DRB1", FAMILY_RULE)
    assert result.values != ["DRB1*15", "DRB1*11"]


@pytest.mark.parametrize("phi", [3.0, 7.0, 10.0, 14.0, -6.0])
def test_the_frame_restores_the_level_page_and_the_rules_run_unchanged(phi: float) -> None:
    boxes = [tilt(b, phi) for b in (LABEL, FIRST, SECOND, OTHER_ROW)]
    rectified, _ = straightening(phi).rectify(boxes)
    result = resolve_locus(rectified, "DRB1", FAMILY_RULE)
    assert result.status is ResolutionStatus.RESOLVED, result.reason
    assert result.values == ["DRB1*15", "DRB1*11"]


def test_provenance_is_restored_to_the_boxes_as_stored() -> None:
    """Facts point at the pixels the pass recorded, never at a derived frame."""
    phi = 8.0
    boxes = [tilt(b, phi) for b in (LABEL, FIRST, SECOND)]
    rectified, back = straightening(phi).rectify(boxes)
    result = restore(resolve_locus(rectified, "DRB1", FAMILY_RULE), back)
    assert result.anchor_box is boxes[0]
    assert [b is o for b, o in zip(result.value_boxes, boxes[1:], strict=True)] == [True, True]
    assert result.values == ["DRB1*15", "DRB1*11"]


def test_the_grouped_drbx_row_keeps_its_second_gene_on_a_tilted_page() -> None:
    """The DRB3/4/5 second column sits far along the row and is the first
    thing a tilt loses; with it gone the third gene cannot be called ABSENT."""
    header = Box(0.10, 0.50, 0.24, 0.53, "HLA-DRB3/4/5")
    gene_a = Box(0.40, 0.505, 0.46, 0.533, "DRB3")
    gene_b = Box(0.85, 0.505, 0.91, 0.533, "DRB4")
    phi = 5.0
    boxes = [tilt(b, phi) for b in (header, gene_a, gene_b)]
    without = {g: f.call for g, f in resolve_grouped_drbx(boxes).items()}
    assert without["DRB5"] is GeneCall.UNKNOWN  # the second token fell off the band

    rectified, back = straightening(phi).rectify(boxes)
    facts = resolve_grouped_drbx(rectified)
    assert facts["DRB3"].call is GeneCall.PRESENT
    assert facts["DRB4"].call is GeneCall.PRESENT
    assert facts["DRB5"].call is GeneCall.ABSENT
    restored = restore_drbx(facts["DRB4"], back)
    assert restored.header_box is boxes[0]
    assert restored.gene_box is boxes[2]


def test_a_level_page_is_untouched_by_a_level_frame() -> None:
    """theta = 0 must be byte-for-byte the pipeline of today."""
    boxes = [LABEL, FIRST, SECOND, OTHER_ROW]
    rectified, back = PageFrame.identity(WIDTH, HEIGHT).rectify(boxes)
    assert rectified == boxes
    result = restore(resolve_locus(rectified, "DRB1", FAMILY_RULE), back)
    assert result.anchor_box is LABEL
    assert result.values == ["DRB1*15", "DRB1*11"]
