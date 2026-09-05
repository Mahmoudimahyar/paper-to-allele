"""Crops for recognition: one place cuts them, so every engine reads the same thing.

The recognizers are brittle to framing. The primary engine lost 56 points on a
crop padded by 0.4% of the page (`OCR_MODEL_SURVEY_2026-09-03.md` §3), the
PP-OCRv5 confirmer contradicted the pipeline on half the cells when its crop
spanned two alleles instead of one (KI-019), and Tesseract measured worse with
more than a few pixels of padding. Until now each pass cut its own crop with
its own arithmetic, which is how a benchmark ends up describing a different
task from production.

This module owns the arithmetic. Three profiles reproduce today's crops byte
for byte — `RAW` (the decode pass), `CONFIRMER_PADDED` (PP-OCRv5),
`TESSERACT` — so switching a pass to this module changes nothing until a
profile is deliberately changed and ablated against the labelled cells.

Two things are new, both gated:

* **An upright crop on a tilted page.** Where the geometry pass declared the
  photograph ROTATE, the crop is cut in the level frame through the same
  rotation the page frame applies to boxes, so the engine sees upright text
  rather than an axis-aligned slice half full of the neighbouring row.
* **Glyph-height discipline.** A crop whose glyphs are a dozen pixels tall is
  scaled so they land where the recognizers are happiest (24–32 px); nothing
  is ever downscaled, and no pixel is synthesized — interpolation only, per
  `MVP_PLAN_REVIEW_2026-09-01.md` §3.1.

Every result maps back: `to_source` names the source pixel a crop pixel came
from, so a reviewer can see exactly what was read.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from kidneymatch.ocr.anchors import Box
from kidneymatch.ocr.geometry import PageFrame

Image = NDArray[Any]


@dataclass(frozen=True, slots=True)
class CropProfile:
    """How an engine wants its crop cut. Each field is a measured choice."""

    name: str
    # Padding as a fraction of the page, the unit the passes used.
    pad_x: float = 0.0
    pad_y: float = 0.0
    # A fixed upscale factor (Tesseract's threefold), or a target height the
    # crop is scaled UP to reach — never down.
    upscale: float = 1.0
    target_glyph_px: int | None = None
    # Background-coloured border after scaling; Tesseract's own guidance.
    border_px: int = 0


# `decode_pass.crop()`: the stored box, integer-truncated, never degenerate.
RAW = CropProfile("raw")
# `confirm_pass`: the confirmer's per-value-box crop, padded by the fractions
# that measured best for Tesseract (10-30 px of padding made it WORSE).
CONFIRMER_PADDED = CropProfile("confirmer-padded", pad_x=0.004, pad_y=0.006)
# `confirm_pass` for Tesseract: the same crop, three times larger.
TESSERACT = CropProfile("tesseract", pad_x=0.004, pad_y=0.006, upscale=3.0)
# The research's crop discipline for the CRNN: glyphs at 24-32 px, a small
# background border so the receptive field does not end on the crop edge.
# Ablate before adopting: the primary engine is exact-box sensitive.
UPRIGHT_GLYPHS = CropProfile("upright-glyphs", target_glyph_px=32, border_px=6)


@dataclass(frozen=True, slots=True)
class CropResult:
    """The pixels, and everything needed to point back at the page."""

    pixels: Image
    profile: str
    scale: float
    rotated: bool
    x0: int
    y0: int
    x1: int
    y1: int
    border: int
    frame: PageFrame | None

    def to_source(self, u: float, v: float) -> tuple[float, float]:
        """The source-image pixel a crop pixel came from."""
        lx = (u - self.border) / self.scale + self.x0
        ly = (v - self.border) / self.scale + self.y0
        if self.frame is None or self.frame.is_identity:
            return lx, ly
        # The crop was cut in the level frame; undo that rotation.
        back = PageFrame(-self.frame.theta_deg, self.frame.width, self.frame.height)
        return back.rotate_pixel(lx, ly)


def _rectangle(
    box: list[float] | tuple[float, ...],
    width: int,
    height: int,
    profile: CropProfile,
    dx: int,
    dy: int,
) -> tuple[int, int, int, int]:
    """`decode_pass.crop()`'s arithmetic, with the confirmer's padding folded in.

    Integer truncation and the two-pixel floor are kept exactly: the primary
    engine's reading changes when the box moves by one pixel, and this is the
    box it has always been given.
    """
    x0 = max(0, min(width - 2, int((box[0] - profile.pad_x) * width) + dx))
    y0 = max(0, min(height - 2, int((box[1] - profile.pad_y) * height) + dy))
    x1 = max(x0 + 2, min(width, int((box[2] + profile.pad_x) * width) + dx))
    y1 = max(y0 + 2, min(height, int((box[3] + profile.pad_y) * height) + dy))
    return x0, y0, x1, y1


def _edge_colour(crop: Image) -> Any:
    ring = np.concatenate(
        [
            crop[0].reshape(-1, *crop.shape[2:]),
            crop[-1].reshape(-1, *crop.shape[2:]),
            crop[:, 0].reshape(-1, *crop.shape[2:]),
            crop[:, -1].reshape(-1, *crop.shape[2:]),
        ]
    )
    median = np.median(ring, axis=0)
    if crop.ndim == 2:
        return int(median)
    return tuple(int(v) for v in np.atleast_1d(median))


def prepare_crop(
    image: Image,
    box: list[float] | tuple[float, ...],
    *,
    frame: PageFrame | None = None,
    profile: CropProfile = RAW,
    dx: int = 0,
    dy: int = 0,
) -> CropResult | None:
    """Cut the crop an engine will read, in the frame the page is level in."""
    import cv2

    if box[2] <= box[0] or box[3] <= box[1]:
        return None
    height, width = image.shape[:2]
    rotated = frame is not None and not frame.is_identity

    if rotated:
        assert frame is not None
        level = frame.rectify_box(Box(box[0], box[1], box[2], box[3], ""))
        rect = (level.x0, level.y0, level.x1, level.y1)
    else:
        rect = (box[0], box[1], box[2], box[3])
    x0, y0, x1, y1 = _rectangle(rect, width, height, profile, dx, dy)
    w, h = x1 - x0, y1 - y0

    if rotated:
        assert frame is not None
        # dst (u, v) -> source pixel: undo the page rotation of (x0 + u, y0 + v).
        undo = cv2.getRotationMatrix2D((width / 2, height / 2), -frame.theta_deg, 1.0)
        shift = np.array([[1.0, 0.0, x0], [0.0, 1.0, y0], [0.0, 0.0, 1.0]])
        mapping = np.asarray(undo, dtype=np.float64) @ shift
        crop = np.asarray(
            cv2.warpAffine(
                image,
                mapping,
                (w, h),
                flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                borderMode=cv2.BORDER_REPLICATE,
            )
        )
    else:
        crop = np.ascontiguousarray(image[y0:y1, x0:x1])

    scale = float(profile.upscale)
    if profile.target_glyph_px is not None and crop.shape[0] < profile.target_glyph_px:
        scale = max(scale, profile.target_glyph_px / crop.shape[0])
    if scale != 1.0:
        new_w = max(2, int(round(crop.shape[1] * scale)))
        new_h = max(int(math.ceil(crop.shape[0] * scale)), profile.target_glyph_px or 0)
        # The realised scale, so `to_source` stays exact after rounding.
        scale = new_h / crop.shape[0]
        crop = np.asarray(cv2.resize(crop, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4))

    if profile.border_px:
        b = profile.border_px
        crop = np.asarray(
            cv2.copyMakeBorder(crop, b, b, b, b, cv2.BORDER_CONSTANT, value=_edge_colour(crop))
        )

    return CropResult(
        pixels=crop,
        profile=profile.name,
        scale=scale,
        rotated=rotated,
        x0=x0,
        y0=y0,
        x1=x1,
        y1=y1,
        border=profile.border_px,
        frame=frame if rotated else None,
    )
