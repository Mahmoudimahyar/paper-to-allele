"""Page geometry from the printed rulings: how tilted a photographed report is.

Most laboratory reports in the archive draw a box around every value, so the
page carries hundreds of pixels of straight printed line in two families. Those
rulings are the most precise thing on the page to measure tilt from — far more
than the detector's word boxes, whose centres carry a 1-4 degree bias from the
form's own layout (label indentation, values boxed half a line above their
label; measured on 14,990 documents, `OCR-GEOM-001`).

## Two estimators, and why both are required

**Line segments, not morphology.** The textbook recipe — a long horizontal
kernel to isolate rulings — returns zero segments on a page tilted 7.3 degrees,
because a tilted ruling is not a horizontal run of pixels. `cv2.LineSegmentDetector`
follows gradients at any angle: measured 9.4 ms per image and under 0.01
degrees of error on synthetic tables (research skeptic, 2026-09-05).

**A projection-profile sweep as the second opinion.** Leptonica's `pixFindSkew`:
shear the binarised page through a range of angles and score how sharp the
horizontal projection becomes; the best angle is the tilt, and the max/min
score ratio is a confidence. It reads text lines and rulings alike, so it does
not share the segment detector's failure modes.

**A page is never rotated on one estimator.** A wrong angle would mis-row every
cell on the page silently — the exact failure `OCR_SPEC.md` s2 exists to
prevent — so ROTATE requires the two to agree within a degree, and anything
else keeps the identity frame and is reported UNCERTAIN with its reason.

## Convention

`theta_deg` is the angle that STRAIGHTENS the page when handed to
`rotate_image` (OpenCV's convention: positive is counter-clockwise on screen).
`rotation_matrix` returns the same transform for any consumer that moves
coordinates instead of pixels, so boxes and crops never disagree about where
the page went.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import numpy as np
from numpy.typing import NDArray

Image = NDArray[Any]

# The page is analysed at this width: rulings survive the downscale and the
# segment detector's cost is linear in pixels.
ANALYSIS_WIDTH = 1200

# A ruling is long. Text strokes and letter edges are segments too, and this is
# what separates them: a horizontal ruling spans a tenth of the page at least.
MIN_HORIZONTAL_FRACTION = 0.10
MIN_VERTICAL_FRACTION = 0.06

# Merging the detector's pieces into rulings. A piece shorter than this is
# noise; pieces within a quarter-degree and six analysis pixels of one line
# are that line; and the joined pieces must cover at least half its extent —
# a column of letter strokes lines up too, but sparsely.
MIN_PIECE_PX = 4.0
ANGLE_BUCKET_DEG = 0.25
OFFSET_BUCKET_PX = 6.0
MIN_COVERAGE = 0.5

# A segment belongs to the horizontal family within this many degrees of 0, or
# the vertical family within this many of 90. Wider than any tilt the corpus
# shows, narrower than the diagonal noise a photo produces.
FAMILY_TOLERANCE = 20.0

# The decision rule. Six long rulings is a printed table; fewer is a photo
# frame, a stamp edge or a crease. The scatter bound is calibrated on the
# 150-document review pack, not on synthetic tables: a rendered table scatters
# 0.001 degrees, a phone photograph of one a median 0.53 (lens, perspective,
# JPEG), and half a degree refused 79 of 150 real pages. At 1.5 the pages that
# remain refused are the ones where two grids or a frame edge are mixed in,
# and the projection sweep is what guards the rest.
MIN_RULINGS = 6
MAX_MAD_DEG = 1.5
STRAIGHT_BELOW_DEG = 0.5
AGREEMENT_DEG = 1.0

# Leptonica's confidence floor for the projection sweep: the best angle must
# score at least this many times the worst.
MIN_SWEEP_RATIO = 3.0

# Rulings whose angle drifts across the page are converging: perspective, not
# rotation. Flagged for a later rectification step, never corrected here, and
# never a reason to refuse the rotation — the rows are what the anchor rule
# reads, and rotating by the horizontal rulings levels them under keystone
# too. Measured on the pack: horizontal spread median 1.5 degrees across the
# page, vertical 2.6 (a hand-held phone converges the verticals), so the
# thresholds sit at about the top third of each.
PERSPECTIVE_SPREAD_H_DEG = 3.0
PERSPECTIVE_SPREAD_V_DEG = 5.0

# The sweep: coarse range and step, then a fine search to this floor.
SWEEP_RANGE_DEG = 15.0
SWEEP_STEP_DEG = 1.0
SWEEP_FLOOR_DEG = 0.01

# The version every stored decision is keyed by. Bump it when the estimators
# or the decision rule change; old rows stay. v2: the scatter bound calibrated
# on real photographs (1.5 deg) and the vertical family demoted from a veto to
# the perspective flag.
GEOMETRY_VERSION = "rulings/v2+lsd+sweep"


class GeometryDecision(StrEnum):
    """What the page's geometry licenses."""

    STRAIGHT = "STRAIGHT"
    ROTATE = "ROTATE"
    UNCERTAIN = "UNCERTAIN"


@dataclass(frozen=True, slots=True)
class Segment:
    """A straight printed line, in SOURCE pixel coordinates."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def length(self) -> float:
        return math.hypot(self.x1 - self.x0, self.y1 - self.y0)

    @property
    def centre(self) -> tuple[float, float]:
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)


@dataclass(frozen=True, slots=True)
class RulingEstimate:
    """The rulings' verdict on the page angle, with what it rests on."""

    theta_deg: float | None
    n_horizontal: int
    n_vertical: int
    mad_horizontal_deg: float | None
    mad_vertical_deg: float | None
    theta_vertical_deg: float | None
    perspective_flag: bool
    horizontal: tuple[Segment, ...]
    vertical: tuple[Segment, ...]
    scale: float


@dataclass(frozen=True, slots=True)
class SweepEstimate:
    """The projection sweep's verdict. `ratio` is its confidence."""

    theta_deg: float | None
    ratio: float
    max_score: float


@dataclass(frozen=True, slots=True)
class PageGeometry:
    """The decision, the angle it licenses (0 unless ROTATE), and the evidence."""

    decision: GeometryDecision
    theta_deg: float
    rulings: RulingEstimate
    sweep: SweepEstimate | None
    reason: str


def _empty(scale: float) -> RulingEstimate:
    return RulingEstimate(None, 0, 0, None, None, None, False, (), (), scale)


def _to_gray(image: Image) -> NDArray[np.uint8]:
    import cv2

    if image.ndim == 2:
        return image.astype(np.uint8, copy=False)
    if image.shape[2] == 4:
        return np.asarray(cv2.cvtColor(image, cv2.COLOR_RGBA2GRAY), dtype=np.uint8)
    return np.asarray(cv2.cvtColor(image, cv2.COLOR_RGB2GRAY), dtype=np.uint8)


def _analysis_frame(gray: NDArray[np.uint8], width: int) -> tuple[NDArray[np.uint8], float]:
    """The page at analysis size, and the factor that took it there. Never upscaled."""
    import cv2

    h, w = gray.shape[:2]
    scale = min(1.0, width / max(w, 1))
    if scale >= 1.0:
        return gray, 1.0
    small = cv2.resize(
        gray, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=cv2.INTER_AREA
    )
    return np.asarray(small, dtype=np.uint8), scale


def _mad(values: list[float], centre: float) -> float:
    return statistics.median(abs(v - centre) for v in values)


def _spread(values: list[float], positions: list[float]) -> float:
    """How much `values` change across `positions`, from a least-squares line."""
    n = len(values)
    if n < 3:
        return 0.0
    mp = sum(positions) / n
    mv = sum(values) / n
    sxx = sum((p - mp) ** 2 for p in positions)
    if sxx <= 1e-9:
        return 0.0
    slope = sum((p - mp) * (v - mv) for p, v in zip(positions, values, strict=True)) / sxx
    return abs(slope * (max(positions) - min(positions)))


def detect_rulings(image: Image, *, analysis_width: int = ANALYSIS_WIDTH) -> RulingEstimate:
    """Measure the page angle from its long straight printed lines."""
    import cv2

    gray = _to_gray(image)
    small, scale = _analysis_frame(gray, analysis_width)
    small = np.asarray(cv2.GaussianBlur(small, (3, 3), 0), dtype=np.uint8)
    h, w = small.shape[:2]

    detector = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD)
    lines = detector.detect(small)[0]
    if lines is None or len(lines) == 0:
        return _empty(scale)

    # The detector returns PIECES: every crossing breaks a ruling, so a table
    # of twelve rows yields vertical segments a twelfth of the table tall, and
    # a thick line arrives as its two edges. Pieces are sorted into the two
    # families here and merged into rulings before any length test.
    raw_h: list[tuple[float, float, float, float]] = []
    raw_v: list[tuple[float, float, float, float]] = []
    for x0, y0, x1, y1 in np.asarray(lines, dtype=np.float64).reshape(-1, 4):
        dx, dy = float(x1 - x0), float(y1 - y0)
        if math.hypot(dx, dy) < MIN_PIECE_PX:
            continue
        angle = math.degrees(math.atan2(dy, dx))
        if angle > 90:
            angle -= 180
        elif angle <= -90:
            angle += 180
        if abs(angle) <= FAMILY_TOLERANCE:
            if dx < 0:
                x0, y0, x1, y1 = x1, y1, x0, y0
            raw_h.append((float(x0), float(y0), float(x1), float(y1)))
        elif abs(abs(angle) - 90) <= FAMILY_TOLERANCE:
            if dy < 0:
                x0, y0, x1, y1 = x1, y1, x0, y0
            raw_v.append((float(x0), float(y0), float(x1), float(y1)))

    # A horizontal ruling oriented left to right has its slope as the
    # straightening angle: content rotated counter-clockwise slopes upward to
    # the right, and a clockwise rotation of that amount undoes it. A vertical
    # ruling oriented top to bottom leans its foot to the right under the same
    # rotation, so its straightening angle is minus the lean.
    horizontal = [
        (s, a)
        for s, a in _merge_collinear(raw_h, horizontal=True, width=w, height=h)
        if s.length >= MIN_HORIZONTAL_FRACTION * w
    ]
    vertical = [
        (s, -a)
        for s, a in _merge_collinear(raw_v, horizontal=False, width=w, height=h)
        if s.length >= MIN_VERTICAL_FRACTION * h
    ]
    if not horizontal:
        return _empty(scale)

    h_angles = [a for _, a in horizontal]
    v_angles = [a for _, a in vertical]
    theta = statistics.median(h_angles)
    mad_h = _mad(h_angles, theta)
    theta_v = statistics.median(v_angles) if v_angles else None
    mad_v = _mad(v_angles, theta_v) if theta_v is not None else None

    # Rulings whose angle trends across the page converge: that is keystone,
    # which a rotation cannot fix. Both families are checked.
    spread_h = _spread(h_angles, [s.centre[1] for s, _ in horizontal])
    spread_v = _spread(v_angles, [s.centre[0] for s, _ in vertical])
    perspective = spread_h > PERSPECTIVE_SPREAD_H_DEG or spread_v > PERSPECTIVE_SPREAD_V_DEG

    def source(s: Segment) -> Segment:
        return Segment(s.x0 / scale, s.y0 / scale, s.x1 / scale, s.y1 / scale)

    return RulingEstimate(
        theta_deg=theta,
        n_horizontal=len(horizontal),
        n_vertical=len(vertical),
        mad_horizontal_deg=mad_h,
        mad_vertical_deg=mad_v,
        theta_vertical_deg=theta_v,
        perspective_flag=perspective,
        horizontal=tuple(source(s) for s, _ in horizontal),
        vertical=tuple(source(s) for s, _ in vertical),
        scale=scale,
    )


def _merge_collinear(
    raw: list[tuple[float, float, float, float]], *, horizontal: bool, width: int, height: int
) -> list[tuple[Segment, float]]:
    """Pieces that lie on one line become one ruling, with its mean angle.

    Pieces are bucketed by angle and by where their line crosses the page's
    centre column (or row), neighbouring buckets are joined, and each group's
    extent is bridged end to end. A group must be mostly ink along that extent:
    a column of letter strokes lines up too, but sparsely, and is not a ruling.
    """
    pieces: dict[tuple[int, int], list[tuple[float, float, float, float, float, float]]] = {}
    for x0, y0, x1, y1 in raw:
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy)
        if horizontal:
            angle = math.degrees(math.atan2(dy, dx))
            offset = (y0 + y1) / 2 - math.tan(math.radians(angle)) * ((x0 + x1) / 2 - width / 2)
        else:
            angle = math.degrees(math.atan2(dx, dy))
            offset = (x0 + x1) / 2 - math.tan(math.radians(angle)) * ((y0 + y1) / 2 - height / 2)
        key = (round(angle / ANGLE_BUCKET_DEG), round(offset / OFFSET_BUCKET_PX))
        pieces.setdefault(key, []).append((x0, y0, x1, y1, angle, length))

    parent = {key: key for key in pieces}

    def find(key: tuple[int, int]) -> tuple[int, int]:
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    for key in list(pieces):
        for da in (-1, 0, 1):
            for do in (-1, 0, 1):
                other = (key[0] + da, key[1] + do)
                if other in pieces and other != key:
                    parent[find(other)] = find(key)

    grouped: dict[tuple[int, int], list[tuple[float, float, float, float, float, float]]] = {}
    for key, members in pieces.items():
        grouped.setdefault(find(key), []).extend(members)

    out: list[tuple[Segment, float]] = []
    for members in grouped.values():
        total = sum(m[5] for m in members)
        angle = sum(m[4] * m[5] for m in members) / total
        cx = sum((m[0] + m[2]) / 2 * m[5] for m in members) / total
        cy = sum((m[1] + m[3]) / 2 * m[5] for m in members) / total
        t = math.tan(math.radians(angle))
        if horizontal:
            lo = min(m[0] for m in members)
            hi = max(m[2] for m in members)
            segment = Segment(lo, cy + t * (lo - cx), hi, cy + t * (hi - cx))
        else:
            lo = min(m[1] for m in members)
            hi = max(m[3] for m in members)
            segment = Segment(cx + t * (lo - cy), lo, cx + t * (hi - cy), hi)
        if segment.length <= 0 or total / segment.length < MIN_COVERAGE:
            continue
        out.append((segment, angle))
    return out


def _ink(gray: NDArray[np.uint8]) -> NDArray[np.float32]:
    """Ink as 1.0 on a 0.0 page, under a threshold that survives phone lighting."""
    import cv2

    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 15
    )
    return np.asarray(binary, dtype=np.float32) / 255.0


def _sharpness(ink: NDArray[np.float32], shear_deg: float) -> float:
    """Leptonica's score: the horizontal projection's sharpness after a vertical shear."""
    import cv2

    h, w = ink.shape[:2]
    s = math.tan(math.radians(shear_deg))
    matrix = np.array([[1.0, 0.0, 0.0], [s, 1.0, -s * (w / 2)]], dtype=np.float64)
    sheared = cv2.warpAffine(ink, matrix, (w, h), flags=cv2.INTER_LINEAR, borderValue=0)
    rows = np.asarray(sheared, dtype=np.float64).sum(axis=1)
    return float(np.sum(np.diff(rows) ** 2))


def projection_sweep(
    image: Image,
    *,
    analysis_width: int = ANALYSIS_WIDTH,
    sweep_range: float = SWEEP_RANGE_DEG,
    step: float = SWEEP_STEP_DEG,
    floor: float = SWEEP_FLOOR_DEG,
) -> SweepEstimate:
    """The page angle from the sharpness of its horizontal projection.

    Coarse at a quarter of the analysis size, fine at half of it, as Leptonica
    does. Content rotated counter-clockwise by phi is flattened by shearing each
    column down by tan(phi) times its distance from the centre, so the best
    shear is phi and the straightening angle is minus it.
    """
    import cv2

    gray = _to_gray(image)
    small, _ = _analysis_frame(gray, analysis_width)
    ink = _ink(small)
    h, w = ink.shape[:2]
    coarse = np.asarray(
        cv2.resize(ink, (max(1, w // 4), max(1, h // 4)), interpolation=cv2.INTER_AREA),
        dtype=np.float32,
    )
    fine = np.asarray(
        cv2.resize(ink, (max(1, w // 2), max(1, h // 2)), interpolation=cv2.INTER_AREA),
        dtype=np.float32,
    )

    angles = [
        round(-sweep_range + i * step, 6) for i in range(int(round(2 * sweep_range / step)) + 1)
    ]
    scores = [_sharpness(coarse, a) for a in angles]
    best = max(scores)
    worst = min(scores)
    if best <= 0.0:
        return SweepEstimate(theta_deg=None, ratio=0.0, max_score=0.0)
    ratio = best / worst if worst > 0 else float("inf")
    centre = angles[scores.index(best)]

    # Fine search: ternary on the unimodal neighbourhood of the coarse winner.
    lo, hi = centre - step, centre + step
    while hi - lo > floor:
        m1 = lo + (hi - lo) / 3
        m2 = hi - (hi - lo) / 3
        if _sharpness(fine, m1) < _sharpness(fine, m2):
            lo = m1
        else:
            hi = m2
    shear = (lo + hi) / 2
    return SweepEstimate(theta_deg=-shear, ratio=ratio, max_score=best)


def decide(rulings: RulingEstimate, sweep: SweepEstimate | None) -> PageGeometry:
    """STRAIGHT, ROTATE, or UNCERTAIN — and only ROTATE moves anything.

    Every branch that is not ROTATE or STRAIGHT keeps the identity frame; the
    reason is recorded so a reviewer can see why a tilted page was left alone.
    """
    theta = rulings.theta_deg
    if theta is None or rulings.n_horizontal < MIN_RULINGS:
        return PageGeometry(
            GeometryDecision.UNCERTAIN,
            0.0,
            rulings,
            sweep,
            f"{rulings.n_horizontal} long horizontal rulings; at least {MIN_RULINGS} are needed",
        )
    if rulings.mad_horizontal_deg is not None and rulings.mad_horizontal_deg > MAX_MAD_DEG:
        return PageGeometry(
            GeometryDecision.UNCERTAIN,
            0.0,
            rulings,
            sweep,
            f"horizontal rulings scatter by {rulings.mad_horizontal_deg:.2f} deg; "
            "not one printed grid",
        )
    # The vertical family is deliberately not a veto. On a hand-held photograph
    # the verticals converge (measured median 2.6 degrees of drift across the
    # pack's pages), so they routinely disagree with the horizontals by more
    # than a degree while the rows are perfectly rotatable: the anchor rule
    # reads rows, and rotating by the horizontal rulings levels them under
    # keystone too. The disagreement is kept in `perspective_flag` for the
    # rectification step that will actually correct it.
    if sweep is None or sweep.theta_deg is None or sweep.ratio < MIN_SWEEP_RATIO:
        return PageGeometry(
            GeometryDecision.UNCERTAIN,
            0.0,
            rulings,
            sweep,
            "no independent estimate corroborates the rulings; "
            "a page is never rotated on one opinion",
        )
    if abs(sweep.theta_deg - theta) > AGREEMENT_DEG:
        return PageGeometry(
            GeometryDecision.UNCERTAIN,
            0.0,
            rulings,
            sweep,
            f"rulings say {theta:.2f} deg, the projection sweep says {sweep.theta_deg:.2f}; "
            "something on this page is not the page",
        )
    if abs(theta) < STRAIGHT_BELOW_DEG:
        return PageGeometry(
            GeometryDecision.STRAIGHT,
            0.0,
            rulings,
            sweep,
            "both estimators agree the page is straight",
        )
    return PageGeometry(
        GeometryDecision.ROTATE,
        theta,
        rulings,
        sweep,
        f"rulings and projection sweep agree on {theta:.2f} deg",
    )


def page_geometry(image: Image) -> PageGeometry:
    """Both estimators, then the decision. The one call a pass needs."""
    rulings = detect_rulings(image)
    sweep = projection_sweep(image)
    return decide(rulings, sweep)


def rotation_matrix(
    width: int, height: int, theta_deg: float, *, expand: bool = True
) -> tuple[NDArray[np.float64], int, int]:
    """The 2x3 affine that straightens the page, and the output size.

    One transform for pixels and coordinates alike. With `expand`, the canvas
    grows so no corner is clipped, and the translation carries the centre to
    the new centre.
    """
    import cv2

    matrix = np.asarray(
        cv2.getRotationMatrix2D((width / 2, height / 2), theta_deg, 1.0), dtype=np.float64
    )
    if not expand:
        return matrix, width, height
    cos = abs(matrix[0, 0])
    sin = abs(matrix[0, 1])
    out_w = int(round(height * sin + width * cos))
    out_h = int(round(height * cos + width * sin))
    matrix[0, 2] += out_w / 2 - width / 2
    matrix[1, 2] += out_h / 2 - height / 2
    return matrix, out_w, out_h


def rotate_image(
    image: Image, theta_deg: float, *, expand: bool = True, border: int = 255
) -> Image:
    """The page straightened by `theta_deg`, on a page-coloured canvas."""
    import cv2

    h, w = image.shape[:2]
    matrix, out_w, out_h = rotation_matrix(w, h, theta_deg, expand=expand)
    value: Any = border if image.ndim == 2 else (border, border, border)
    return np.asarray(
        cv2.warpAffine(
            image,
            matrix,
            (out_w, out_h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=value,
        )
    )
