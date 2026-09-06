"""The slope of the printed rows, and what it is for.

A photographed page is almost never level, and the anchor rule reads ROWS: it
decides that a value belongs to a locus because the two sit on the same printed
line. It tests that by comparing `y` against `y`, which is only the same
question when the page is level. On a page tilted three degrees a value half a
page-width to the right of its label sits about three label-heights off its
label's `y`, so the row test fails and the locus goes unread. That is the
failure a reviewer described as "all the boxes are situated incorrectly".

`rulings.py` already measures the answer. It finds the printed rulings with a
line-segment detector and takes the median angle of the horizontal family. What
it then does with that angle is a page-level decision — STRAIGHT, ROTATE or
UNCERTAIN — and rotating a whole page is a strong action, so it is hedged
behind several gates. Two of them throw a perfectly good measurement away:

* `MAX_MAD_DEG` refuses when the rulings scatter more than 1.5 degrees. A
  hand-held photograph has perspective, and under perspective the rulings
  genuinely fan: the scatter is a property of the camera, not evidence that
  the angle is wrong. One labelled page measured -3.19 degrees with a scatter
  of 2.02, was called UNCERTAIN, and lost every value cell on it;
* `MIN_FRAME_TILT_DEG` declines to rotate below 1.5 degrees, because at that
  size the rotation is a wash against the estimator's own error. True for
  moving pixels, and irrelevant here: a 1.3-degree slope still displaces the
  far end of a row by a label-height, which is enough to lose the second
  allele of a pair.

Grouping boxes into rows is not rotating a page. Nothing moves, no crop is
re-cut, and a slope that is wrong degrades to exactly the behaviour of before.
So the row test can use the measured slope whenever a slope was measured at
all, under the one check that actually bears on it: the rulings must not be
bimodal. Bimodality means a second grid, a frame edge or another form in the
photograph, and the median of two grids belongs to neither — `AGREEMENT_DEG`
and `MIN_AGREEMENT` are that check, and they stay.

The slope is returned in NORMALISED box coordinates. Boxes are normalised
independently in x and y, so a printed line of pixel slope `tan(theta)` has
normalised slope `tan(theta) * width / height`; forgetting the aspect ratio
tilts every correction by the shape of the page.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence

from kidneymatch.ocr.geometry import PageFrame
from kidneymatch.ocr.rulings import AGREEMENT_DEG, MIN_RULINGS

# A segment steeper than this is a column, not a row, and says nothing about
# the slope of the printed lines.
MAX_ROW_SEGMENT_DEG = 45.0
# Beyond this the page is not tilted, it is sideways or misdetected, and the
# row test should not be sheared by it. The geometry pass has its own sideways
# check; this is the floor under a single bad estimate.
MAX_ROW_SLOPE_DEG = 15.0
# The share of the horizontal rulings that must belong to the grid whose angle
# is used. The guard this replaces compared every ruling to the GLOBAL median
# and required 70% agreement, which refuses a page whose rulings hold one clear
# grid plus a frame edge: on a labelled page the reviewer marked "this image is
# tilted", 24 of 35 rulings agreed on -3.19 degrees, the other 11 sat near zero,
# and 69% missed the floor by one percentage point — so the page was read as
# level and every value cell on it was lost. The median of two grids is a line
# neither of them prints; the dominant cluster's median is a line one of them
# does. Requiring that cluster to hold three fifths keeps the case the guard
# exists for, where no grid dominates and nothing should be sheared.
MIN_ROW_CLUSTER = 0.6
# Below this fall per unit of page width the shear is smaller than the error in
# measuring it, and applying it only jostles marginal cells. Ablated over 3,000
# documents and eight loci, by the size of the measured slope:
#
#     slope          cells gained   lost   value changed
#     >= 0.030            42          1          6
#     0.015 - 0.030       31          5          8
#     0.008 - 0.015       23         10          4
#     0.004 - 0.008        6          8          1
#     < 0.004              6          8          2
#
# Above 0.008 the correction gains six cells for every one it loses; below it
# the two are level and the changes are noise. 0.008 is about half a degree on
# a page of the usual shape, which is the same reasoning `MIN_FRAME_TILT_DEG`
# applies to rotating pixels, measured again for this use.
MIN_ROW_SLOPE = 0.008


def segment_angles(
    segments: Sequence[Sequence[float]], frame: PageFrame | None = None
) -> list[float]:
    """The angle of each horizontal ruling, in degrees, in the frame boxes live in.

    Segments are stored in source pixels. When the extraction rectifies its
    boxes into a level frame, the rulings must be rectified by the same frame
    or the slope measured here describes a different page than the boxes do —
    and what is wanted then is the RESIDUAL slope the rotation did not remove,
    which is exactly what perspective leaves behind.
    """
    angles: list[float] = []
    for segment in segments:
        if len(segment) < 4:
            continue
        x0, y0, x1, y1 = (float(value) for value in segment[:4])
        if frame is not None and not frame.is_identity:
            x0, y0 = frame.rotate_pixel(x0, y0)
            x1, y1 = frame.rotate_pixel(x1, y1)
        dx, dy = x1 - x0, y1 - y0
        if abs(dx) <= abs(dy):
            continue  # a column
        angle = math.degrees(math.atan2(dy, dx))
        if abs(angle) <= MAX_ROW_SEGMENT_DEG:
            angles.append(angle)
    return angles


def page_slopes(
    segments: Sequence[Sequence[float]],
    width: int,
    height: int,
    frame: PageFrame | None = None,
) -> tuple[float, float] | None:
    """How the printed rows fall and how the printed columns lean.

    Both in normalised box coordinates, and they are not the same number. A
    page rotated by theta prints its rows along `(cos, sin)` and its columns
    along `(-sin, cos)`, so a row falls `tan(theta)` per unit of width and a
    column drifts `-tan(theta)` per unit of HEIGHT. Normalising x and y
    separately then scales them by opposite aspect ratios:

        row slope     = tan(theta) * width / height   (dy per dx)
        column slope  = -tan(theta) * height / width  (dx per dy)

    On a portrait page those differ by more than a factor of four, so a form
    whose values sit UNDER their label cannot borrow the row's number.

    `None` when the page printed no measurable grid or its rulings are bimodal.
    """
    if width <= 0 or height <= 0:
        return None
    angles = segment_angles(segments, frame)
    if len(angles) < MIN_RULINGS:
        return None
    dominant = dominant_angle(angles)
    if dominant is None or abs(dominant) > MAX_ROW_SLOPE_DEG:
        return None
    tangent = math.tan(math.radians(dominant))
    rows = tangent * (width / height)
    columns = -tangent * (height / width)
    return (
        rows if abs(rows) >= MIN_ROW_SLOPE else 0.0,
        columns if abs(columns) >= MIN_ROW_SLOPE else 0.0,
    )


def row_slope(
    segments: Sequence[Sequence[float]],
    width: int,
    height: int,
    frame: PageFrame | None = None,
) -> float | None:
    """How far a printed row falls per unit of width, in normalised coordinates.

    `None` when the page did not print enough rulings to measure, or when the
    ones it printed are bimodal so no angle describes the page. Zero means the
    rows are level enough that shearing them would cost more than it gains
    (`MIN_ROW_SLOPE`).
    """
    both = page_slopes(segments, width, height, frame)
    return None if both is None else both[0]


def dominant_angle(angles: Sequence[float]) -> float | None:
    """The angle of the grid most of these rulings belong to.

    Every ruling is offered as a centre, the one with the most neighbours
    within `AGREEMENT_DEG` wins, and the answer is the median of that
    neighbourhood rather than the centre itself. `None` when the winner does
    not hold `MIN_ROW_CLUSTER` of the rulings, which is the two-grid case: a
    second form, a frame edge or a stamp, where no angle describes the page.
    """
    if not angles:
        return None
    best: list[float] = []
    for centre in angles:
        near = [angle for angle in angles if abs(angle - centre) <= AGREEMENT_DEG]
        if len(near) > len(best):
            best = near
    if len(best) < MIN_RULINGS or len(best) / len(angles) < MIN_ROW_CLUSTER:
        return None
    return statistics.median(best)
