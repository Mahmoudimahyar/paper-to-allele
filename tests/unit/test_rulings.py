"""Page angle from the printed rulings, and when it may be trusted.

Written before the implementation. The reviewer's finding on the first 165
labels: the pipeline works in axis-aligned rectangles, and on a tilted
photograph its rows drift — the anchor rule loses the second allele column at
about 2-3 degrees and the DRB3/4/5 second column at about 1.4 (pipeline-map
arithmetic). Most reports draw a box around every value, so the rulings are the
most precise thing on the page to measure tilt from.

Two decisions the research settled, both pinned here:

* **Line segments, not morphological kernels.** A long horizontal kernel
  returns zero segments at 7.3 degrees, because a tilted ruling is not a
  horizontal run of pixels. `cv2.LineSegmentDetector` measured 9.4 ms per image
  and under 0.01 degrees of error on synthetic tables.
* **Never rotate on one estimator.** A wrong page angle silently mis-rows every
  cell on the page. The rulings angle must agree with an independent
  projection-profile sweep before a page is declared ROTATE; otherwise the page
  keeps the identity frame and is UNCERTAIN.

The angle convention is pinned by `test_rotating_by_the_estimate_straightens_the_page`:
`theta_deg` is the angle to hand to `rotate_image` to straighten the page.
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")
PIL = pytest.importorskip("PIL")

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from kidneymatch.ocr.rulings import (  # noqa: E402
    GeometryDecision,
    RulingEstimate,
    SweepEstimate,
    decide,
    detect_rulings,
    page_geometry,
    projection_sweep,
    rotate_image,
    rotation_matrix,
)

pytestmark = pytest.mark.task("OCR-001")


def ruled_table(
    width: int = 1000,
    height: int = 1300,
    rows: int = 12,
    cols: int = 4,
    with_text: bool = True,
    line: int = 3,
) -> Image.Image:
    """A synthetic ruled report: a table of boxed cells with locus-like text.

    Nothing here is a real report. The words are form furniture and shapes.
    """
    image = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(image)
    x0, y0, x1, y1 = 100, 200, width - 100, height - 200
    for r in range(rows + 1):
        y = y0 + (y1 - y0) * r // rows
        draw.line([(x0, y), (x1, y)], fill=0, width=line)
    for c in range(cols + 1):
        x = x0 + (x1 - x0) * c // cols
        draw.line([(x, y0), (x, y1)], fill=0, width=line)
    if with_text:
        font = ImageFont.load_default(size=26)
        loci = ["A", "B", "C", "DRB1", "DQA1", "DQB1", "DPA1", "DPB1", "DRB3/4/5", "X", "Y", "Z"]
        for r in range(rows):
            y = y0 + (y1 - y0) * r // rows + 14
            draw.text((x0 + 12, y), f"HLA-{loci[r % len(loci)]}", fill=0, font=font)
            draw.text((x0 + (x1 - x0) // cols + 24, y), "A*02", fill=0, font=font)
            draw.text((x0 + 2 * (x1 - x0) // cols + 24, y), "A*11", fill=0, font=font)
        draw.text((x0, 120), "AZMAYESHGAH LETTERHEAD", fill=0, font=font)
    return image


def text_only_page(width: int = 1000, height: int = 1300) -> Image.Image:
    image = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=24)
    for i in range(30):
        draw.text(
            (120, 150 + i * 34),
            "the quick brown fox jumps over the lazy dog 12 34 56",
            fill=0,
            font=font,
        )
    return image


def tilted(image: Image.Image, angle: float) -> Image.Image:
    """PIL rotates counter-clockwise for a positive angle."""
    return image.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255)


def gray(image: Image.Image):
    return np.asarray(image.convert("L"))


# --- the rulings angle ----------------------------------------------------


@pytest.mark.parametrize("angle", [0.0, 7.3, 14.0, -4.0, 2.0])
def test_the_rulings_angle_is_recovered_within_two_tenths_of_a_degree(angle: float) -> None:
    estimate = detect_rulings(gray(tilted(ruled_table(), angle)))
    assert estimate.n_horizontal >= 6, estimate
    assert estimate.theta_deg is not None
    # PIL rotated the content counter-clockwise by `angle`; the angle that
    # straightens it is the opposite rotation.
    assert estimate.theta_deg == pytest.approx(-angle, abs=0.2)


def test_the_two_ruling_families_agree_on_a_rotated_page() -> None:
    estimate = detect_rulings(gray(tilted(ruled_table(), 7.3)))
    assert estimate.n_vertical >= 3
    assert estimate.theta_vertical_deg is not None
    assert estimate.theta_vertical_deg == pytest.approx(estimate.theta_deg, abs=0.5)
    assert estimate.perspective_flag is False
    assert estimate.mad_horizontal_deg is not None and estimate.mad_horizontal_deg < 0.3


def test_rotating_by_the_estimate_straightens_the_page() -> None:
    """This pins the sign convention: `theta_deg` goes straight into `rotate_image`."""
    page = gray(tilted(ruled_table(), 9.0))
    first = detect_rulings(page)
    assert first.theta_deg is not None
    straight = rotate_image(page, first.theta_deg)
    second = detect_rulings(straight)
    assert second.theta_deg is not None
    assert abs(second.theta_deg) < 0.2


def test_segments_are_reported_in_source_pixels() -> None:
    """The analysis runs downscaled; consumers need the source frame."""
    page = gray(ruled_table(width=2400, height=3000))
    estimate = detect_rulings(page)
    assert 0 < estimate.scale < 1
    longest = max(estimate.horizontal, key=lambda s: s.length)
    # the table spans x 100..2300 in source pixels
    assert longest.length > 1800
    assert min(longest.x0, longest.x1) < 200 and max(longest.x0, longest.x1) > 2200


def test_a_page_without_rulings_yields_too_few_segments_to_trust() -> None:
    """Text lines are not straight edges; they must not masquerade as rulings."""
    estimate = detect_rulings(gray(tilted(text_only_page(), 5.0)))
    assert estimate.n_horizontal < 6


# --- the independent second estimator ---------------------------------------


def test_the_projection_sweep_agrees_with_the_rulings() -> None:
    page = gray(tilted(ruled_table(), 6.0))
    sweep = projection_sweep(page)
    assert sweep.theta_deg is not None
    assert sweep.theta_deg == pytest.approx(-6.0, abs=0.5)
    assert sweep.ratio >= 3.0


def test_the_projection_sweep_still_estimates_an_unruled_page() -> None:
    """Its value is being independent of the rulings: it works from the text."""
    sweep = projection_sweep(gray(tilted(text_only_page(), 4.0)))
    assert sweep.theta_deg is not None
    assert sweep.theta_deg == pytest.approx(-4.0, abs=0.7)


def test_a_blank_page_has_no_confidence() -> None:
    sweep = projection_sweep(np.full((1300, 1000), 255, dtype=np.uint8))
    assert sweep.ratio < 3.0


# --- the decision -------------------------------------------------------------


def rulings(
    theta: float | None,
    n: int = 8,
    mad: float = 0.1,
    theta_v: float | None = None,
    n_v: int = 4,
    perspective: bool = False,
) -> RulingEstimate:
    return RulingEstimate(
        theta_deg=theta,
        n_horizontal=n,
        n_vertical=n_v,
        mad_horizontal_deg=mad if theta is not None else None,
        mad_vertical_deg=0.1 if theta_v is not None else None,
        theta_vertical_deg=theta if theta_v is None and theta is not None else theta_v,
        perspective_flag=perspective,
        horizontal=(),
        vertical=(),
        scale=1.0,
    )


def sweep(theta: float | None, ratio: float = 5.0) -> SweepEstimate:
    return SweepEstimate(theta_deg=theta, ratio=ratio, max_score=1e6)


def test_a_page_is_never_rotated_on_one_estimator() -> None:
    """A wrong angle mis-rows every cell silently, so one opinion is not enough."""
    alone = decide(rulings(5.0), None)
    assert alone.decision is GeometryDecision.UNCERTAIN
    assert alone.theta_deg == 0.0


def test_two_agreeing_estimators_rotate() -> None:
    both = decide(rulings(5.0), sweep(5.4))
    assert both.decision is GeometryDecision.ROTATE
    assert both.theta_deg == pytest.approx(5.0)


def test_disagreeing_estimators_leave_the_page_uncertain() -> None:
    result = decide(rulings(5.0), sweep(0.2))
    assert result.decision is GeometryDecision.UNCERTAIN
    assert result.theta_deg == 0.0


def test_a_straight_page_is_straight_only_when_both_agree() -> None:
    assert decide(rulings(0.1), sweep(0.3)).decision is GeometryDecision.STRAIGHT
    # rulings say straight, the sweep says 5: something on this page is not the
    # page (a phone frame, a screen edge) — do not trust either.
    assert decide(rulings(0.1), sweep(5.0)).decision is GeometryDecision.UNCERTAIN


def test_too_few_or_scattered_rulings_are_not_evidence() -> None:
    assert decide(rulings(5.0, n=3), sweep(5.0)).decision is GeometryDecision.UNCERTAIN
    assert decide(rulings(5.0, mad=2.0), sweep(5.0)).decision is GeometryDecision.UNCERTAIN


def test_converging_verticals_do_not_veto_a_rotation_the_sweep_corroborates() -> None:
    """Horizontal rulings at 5 degrees and vertical ones at 1 is keystone.

    Measured on the 150-document pack, the verticals of a hand-held photograph
    drift a median 2.6 degrees across the page. The anchor rule reads ROWS, and
    rotating by the horizontal rulings levels them under keystone too, so the
    disagreement is carried as `perspective_flag` for a rectification step and
    is not a reason to leave the page tilted.
    """
    result = decide(rulings(5.0, theta_v=1.0), sweep(5.0))
    assert result.decision is GeometryDecision.ROTATE
    assert result.theta_deg == pytest.approx(5.0)


def test_a_low_confidence_sweep_does_not_corroborate() -> None:
    assert decide(rulings(5.0), sweep(5.0, ratio=1.5)).decision is GeometryDecision.UNCERTAIN


def test_the_calibrated_constants_are_pinned_at_their_boundaries() -> None:
    """Each threshold was measured on real photographs; a change by an order
    of magnitude must fail a test, not only rewrite a comment."""
    # scatter bound 1.5 deg
    assert decide(rulings(5.0, mad=1.4), sweep(5.0)).decision is GeometryDecision.ROTATE
    assert decide(rulings(5.0, mad=1.6), sweep(5.0)).decision is GeometryDecision.UNCERTAIN
    # straight below 0.5 deg
    assert decide(rulings(0.4), sweep(0.4)).decision is GeometryDecision.STRAIGHT
    assert decide(rulings(0.6), sweep(0.6)).decision is GeometryDecision.ROTATE
    # the sweep corroborates the rulings within 2 deg (v3; 1 deg refused
    # 1,231 pages whose sweep still vouched for the sign and size of the tilt)
    assert decide(rulings(5.0), sweep(6.9)).decision is GeometryDecision.ROTATE
    assert decide(rulings(5.0), sweep(7.2)).decision is GeometryDecision.UNCERTAIN
    # and the rotation applied is the rulings', never the sweep's
    assert decide(rulings(5.0), sweep(6.9)).theta_deg == 5.0
    # the sweep's confidence floor of 3
    assert decide(rulings(5.0), sweep(5.0, ratio=3.0)).decision is GeometryDecision.ROTATE
    assert decide(rulings(5.0), sweep(5.0, ratio=2.9)).decision is GeometryDecision.UNCERTAIN
    # the rulings' own agreement floor of 0.7 (calibrated on the v2 corpus rows:
    # 0.8 within 1 deg refused 6,772 pages already measured to a MAD under 1.5)
    assert (
        decide(replace(rulings(5.0), agreement_fraction=0.71), sweep(5.0)).decision
        is GeometryDecision.ROTATE
    )
    assert (
        decide(replace(rulings(5.0), agreement_fraction=0.69), sweep(5.0)).decision
        is GeometryDecision.UNCERTAIN
    )


def test_the_perspective_flag_itself_never_vetoes() -> None:
    """A mutant that refuses every flagged page passed the suite before this."""
    result = decide(rulings(5.0, perspective=True), sweep(5.0))
    assert result.decision is GeometryDecision.ROTATE
    assert result.rulings.perspective_flag is True


def test_a_second_grid_the_median_cannot_see_is_uncertain() -> None:
    """Six rulings at 5 degrees and four at 0: the MAD of that set is zero, so
    the scatter bound passes it, and rotating every box by 5 would mis-row the
    minority's cells. The agreement fraction sees what the MAD cannot."""
    mixed = RulingEstimate(
        theta_deg=5.0,
        n_horizontal=10,
        n_vertical=4,
        mad_horizontal_deg=0.0,
        mad_vertical_deg=0.1,
        theta_vertical_deg=5.0,
        perspective_flag=False,
        horizontal=(),
        vertical=(),
        scale=1.0,
        agreement_fraction=0.6,
    )
    result = decide(mixed, sweep(5.0))
    assert result.decision is GeometryDecision.UNCERTAIN
    assert "two grids" in result.reason
    fine = replace(mixed, agreement_fraction=0.9)
    assert decide(fine, sweep(5.0)).decision is GeometryDecision.ROTATE


def test_detect_rulings_reports_how_many_rulings_agree() -> None:
    estimate = detect_rulings(gray(tilted(ruled_table(), 7.3)))
    assert estimate.agreement_fraction is not None
    assert estimate.agreement_fraction >= 0.9


def test_a_sideways_page_is_not_levelled_by_its_columns() -> None:
    """Rotated a quarter turn, a form's many rows land in the vertical family
    and its few columns in the horizontal one; no angle from the columns
    levels the rows."""
    sideways = decide(rulings(0.2, n=6, n_v=20), sweep(0.2))
    assert sideways.decision is GeometryDecision.UNCERTAIN
    assert "sideways" in sideways.reason
    upright = decide(rulings(0.2, n=13, n_v=5), sweep(0.2))
    assert upright.decision is GeometryDecision.STRAIGHT


def test_a_blank_page_is_uncertain_end_to_end() -> None:
    result = page_geometry(np.full((1300, 1000), 255, dtype=np.uint8))
    assert result.decision is GeometryDecision.UNCERTAIN
    assert result.theta_deg == 0.0


def test_a_rotated_table_is_rotate_end_to_end() -> None:
    result = page_geometry(gray(tilted(ruled_table(), 7.3)))
    assert result.decision is GeometryDecision.ROTATE
    assert result.theta_deg == pytest.approx(-7.3, abs=0.2)


def test_a_straight_table_is_straight_end_to_end() -> None:
    result = page_geometry(gray(ruled_table()))
    assert result.decision is GeometryDecision.STRAIGHT
    assert result.theta_deg == 0.0


# --- perspective ------------------------------------------------------------


def test_a_keystoned_table_sets_the_perspective_flag() -> None:
    """Converging vertical rulings are not a rotation, and must say so."""
    page = gray(ruled_table())
    h, w = page.shape
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[80, 0], [w - 80, 0], [w, h], [0, h]])
    warped = cv2.warpPerspective(
        page, cv2.getPerspectiveTransform(src, dst), (w, h), borderValue=255
    )
    estimate = detect_rulings(warped)
    assert estimate.perspective_flag is True


# --- the shared transform -----------------------------------------------------


def test_rotation_matrix_and_rotate_image_share_one_transform() -> None:
    """A point mapped through the matrix lands where the pixels went."""
    page = np.full((600, 800), 255, dtype=np.uint8)
    cv2.circle(page, (650, 150), 6, 0, -1)
    theta = 11.0
    matrix, out_w, out_h = rotation_matrix(800, 600, theta, expand=True)
    rotated = rotate_image(page, theta, expand=True)
    assert rotated.shape == (out_h, out_w)
    ys, xs = np.nonzero(rotated < 128)
    found = (float(xs.mean()), float(ys.mean()))
    expected = matrix @ np.array([650.0, 150.0, 1.0])
    assert math.dist(found, (float(expected[0]), float(expected[1]))) < 1.5


def two_grids_page(second_angle: float, second_lines: int = 5) -> Image.Image:
    """Ten level rulings and `second_lines` rulings tilted by `second_angle`:
    a page carrying a second grid, as a frame or a stamp does."""
    image = Image.new("L", (1000, 1300), 255)
    draw = ImageDraw.Draw(image)
    for i in range(10):
        y = 200 + i * 60
        draw.line([(100, y), (900, y)], fill=0, width=3)
    for i in range(second_lines):
        y = 900 + i * 50
        dy = math.tan(math.radians(second_angle)) * 800
        draw.line([(100, y + dy / 2), (900, y - dy / 2)], fill=0, width=3)
    return image


def test_the_agreement_window_is_pinned_on_a_real_second_grid() -> None:
    """`AGREEMENT_DEG` is read by `detect_rulings`, not `decide`, so only an
    image can pin it: five of fifteen rulings 2.5 deg off the median sit inside
    the 3 deg window (agreement 1.0) and the page is judged; at 4 deg they sit
    outside it (agreement 0.67, under the 0.7 floor) and the page is refused as
    two grids, whatever the sweep says."""
    inside = page_geometry(gray(two_grids_page(2.5)))
    assert inside.rulings.agreement_fraction is not None
    assert inside.rulings.agreement_fraction >= 0.9
    assert "agree with the median" not in inside.reason
    outside = page_geometry(gray(two_grids_page(4.0)))
    assert outside.decision is GeometryDecision.UNCERTAIN
    assert "agree with the median" in outside.reason
