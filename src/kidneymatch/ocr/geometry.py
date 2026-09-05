"""Rotate the geometry, not the pixels: the frame the row rules run in.

`anchors.py` and `drbx.py` bind a value to its locus by the printed ROW —
vertical overlap with the label, or a centre band a couple of label heights
wide. On a photograph tilted by theta, a row drifts by `tan(theta)` times its
length: the family rule's second allele column, 8-25 label heights to the
right, leaves the band at about 2-3 degrees, and the DRB3/4/5 second column at
about 1.4. Measured on the 150-document review pack, 53 pages rotate by half a
degree or more (`scripts/geometry_pass.py`).

The cheapest correct fix is to straighten the STORED boxes rather than the
pixels: rotate each box's centre by the page angle the rulings measured, and
give it back its printed size — the detector's axis-aligned hull of a rotated
rectangle is inflated by `w·sin(theta)` in height, and that inflation, not the
rotation, is what pushes long boxes past the tall-box gate and into the next
row. Every rule then runs unchanged on a level page, and nothing about WHAT
binds to WHAT is touched here: geometry still decides the locus, only the
geometry is now the page's rather than the camera's.

Provenance is restored afterwards. A fact points at the box the pass recorded,
in the frame the image is stored in; the rotation that was applied is recorded
beside it. Pixels are rotated later, per crop, and only for pages declared
ROTATE by two agreeing estimators (`rulings.py`).

The rotation is the same one `rulings.rotation_matrix` builds for pixels —
OpenCV's convention, positive counter-clockwise on screen — so a crop cut in
the straightened image and a box straightened here agree to the pixel.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from kidneymatch.ocr.anchors import Box, LocusResolution
from kidneymatch.ocr.drbx import DrbxFact

# Past this the hull-to-rectangle de-inflation is ill-conditioned, and no page
# in the corpus rotates so far (the pass's largest ROTATE angle is under 3).
MAX_DEINFLATE_DEG = 30.0


def _deinflate(width: float, height: float, theta_deg: float) -> tuple[float, float]:
    """The printed rectangle whose rotated hull has this size.

    A w x h rectangle rotated by phi has an axis-aligned hull of
    `W = w·cos + h·sin`, `H = w·sin + h·cos`; inverting gives the printed
    size. A hull that cannot have come from a rotated rectangle — thinner than
    its tilt allows — is left as it is rather than invented.
    """
    phi = abs(math.radians(theta_deg))
    if phi < 1e-9 or math.degrees(phi) > MAX_DEINFLATE_DEG:
        return width, height
    cos, sin = math.cos(phi), math.sin(phi)
    cos2 = math.cos(2 * phi)
    if cos2 <= 1e-9:
        return width, height
    w = (width * cos - height * sin) / cos2
    h = (height * cos - width * sin) / cos2
    if w <= 0 or h <= 0:
        return width, height
    return w, h


@dataclass(frozen=True, slots=True)
class PageFrame:
    """The rotation that levels a page, applied to boxes in page coordinates.

    `theta_deg` is the straightening angle in OpenCV's convention, exactly as
    `rulings.PageGeometry.theta_deg` reports it; `width` and `height` are the
    stored image's, because normalised coordinates rotate correctly only in
    pixel space.
    """

    theta_deg: float
    width: int
    height: int

    @classmethod
    def identity(cls, width: int, height: int) -> PageFrame:
        return cls(0.0, width, height)

    @property
    def is_identity(self) -> bool:
        return abs(self.theta_deg) < 1e-9

    def rotate_pixel(self, x: float, y: float) -> tuple[float, float]:
        """Where a pixel of the stored image lands on the level page."""
        cx, cy = self.width / 2, self.height / 2
        angle = math.radians(self.theta_deg)
        cos, sin = math.cos(angle), math.sin(angle)
        dx, dy = x - cx, y - cy
        return cos * dx + sin * dy + cx, -sin * dx + cos * dy + cy

    def rectify_box(self, box: Box) -> Box:
        """The box on the level page: rotated centre, printed size, same text."""
        if self.is_identity:
            return box
        width = (box.x1 - box.x0) * self.width
        height = (box.y1 - box.y0) * self.height
        cx, cy = self.rotate_pixel(box.centre_x * self.width, box.centre_y * self.height)
        w, h = _deinflate(width, height, self.theta_deg)
        return Box(
            (cx - w / 2) / self.width,
            (cy - h / 2) / self.height,
            (cx + w / 2) / self.width,
            (cy + h / 2) / self.height,
            box.text,
        )

    def rectify(self, boxes: list[Box]) -> tuple[list[Box], dict[int, Box]]:
        """Every box on the level page, index-aligned, plus the way back.

        The map is keyed by the identity of each rectified box: results refer
        to boxes by object, and provenance must name the box as stored.
        """
        if self.is_identity:
            return list(boxes), {id(box): box for box in boxes}
        rectified = [self.rectify_box(box) for box in boxes]
        return rectified, {id(new): old for new, old in zip(rectified, boxes, strict=True)}


def unrectify_box(frame: PageFrame, box: Box) -> Box:
    """A box measured on the LEVEL page, placed back on the stored one.

    The inverse of the rotation `rectify_box` applies, without its
    de-inflation: a box the pipeline drew itself on the level page (a label
    placed by a form's template) has the printed size already, so only its
    centre moves. Provenance must name the stored frame, whatever frame the
    box was computed in.
    """
    if frame.is_identity:
        return box
    inverse = PageFrame(-frame.theta_deg, frame.width, frame.height)
    cx, cy = inverse.rotate_pixel(box.centre_x * frame.width, box.centre_y * frame.height)
    half_w = (box.x1 - box.x0) / 2
    half_h = (box.y1 - box.y0) / 2
    return Box(
        cx / frame.width - half_w,
        cy / frame.height - half_h,
        cx / frame.width + half_w,
        cy / frame.height + half_h,
        box.text,
    )


def restore(resolution: LocusResolution, back: dict[int, Box]) -> LocusResolution:
    """The same outcome, with provenance pointing at the boxes as stored."""
    anchor = resolution.anchor_box
    return replace(
        resolution,
        anchor_box=None if anchor is None else back.get(id(anchor), anchor),
        value_boxes=[back.get(id(box), box) for box in resolution.value_boxes],
    )


def restore_drbx(fact: DrbxFact, back: dict[int, Box]) -> DrbxFact:
    """The same gene call, with provenance pointing at the boxes as stored."""
    header, gene = fact.header_box, fact.gene_box
    return replace(
        fact,
        header_box=None if header is None else back.get(id(header), header),
        gene_box=None if gene is None else back.get(id(gene), gene),
    )
