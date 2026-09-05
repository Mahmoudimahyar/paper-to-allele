"""One place cuts every crop, and it cuts today's crops byte for byte.

Written before the implementation. The recognizers are brittle to framing —
the primary lost 56 points on a 0.4% pad (`OCR_MODEL_SURVEY_2026-09-03.md`
§3) — so a change to how a crop is cut is a change to what the engines read,
and it must be (a) reproducible, (b) ablated against the labelled cells before
it ships, and (c) invertible, so a reviewer can see which source pixels a
reading came from.

Three profiles reproduce what the passes cut today, exactly:
`RAW` is `decode_pass.crop()`, `CONFIRMER_PADDED` is the PP-OCRv5 confirmer's
per-box crop, `TESSERACT` its threefold upscale. The new ones — an upright
crop on a page the rulings declared ROTATE, and a glyph-height discipline —
are what the ablation compares them with.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from kidneymatch.ocr.crops import (  # noqa: E402
    CONFIRMER_PADDED,
    RAW,
    TESSERACT,
    UPRIGHT_GLYPHS,
    CropProfile,
    prepare_crop,
)
from kidneymatch.ocr.geometry import PageFrame  # noqa: E402
from kidneymatch.ocr.rulings import rotate_image  # noqa: E402

pytestmark = pytest.mark.task("OCR-001")

ROOT = Path(__file__).resolve().parents[2]


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(f"km_{name}", ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def noise_page(width: int = 640, height: int = 480, seed: int = 7):
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)


# --- today's crops, byte for byte ------------------------------------------


def legacy_decode_crop(image, box: list[float], dx: int, dy: int):
    """`decode_pass.crop()` as it was before it delegated here, verbatim.

    Kept inline so this test cannot become a tautology: the script now calls
    `prepare_crop`, and comparing the two would prove nothing.
    """
    height, width = image.shape[:2]
    x0 = max(0, min(width - 2, int(box[0] * width) + dx))
    y0 = max(0, min(height - 2, int(box[1] * height) + dy))
    x1 = max(x0 + 2, min(width, int(box[2] * width) + dx))
    y1 = max(y0 + 2, min(height, int(box[3] * height) + dy))
    return image[y0:y1, x0:x1]


@pytest.mark.parametrize(
    ("box", "dx", "dy"),
    [
        ([0.10, 0.20, 0.30, 0.25], 0, 0),
        ([0.10, 0.20, 0.30, 0.25], 1, -1),
        ([0.00, 0.00, 0.05, 0.02], -1, -1),  # clipped at the top-left corner
        ([0.97, 0.98, 1.00, 1.00], 1, 1),  # clipped at the bottom-right corner
        ([0.500, 0.500, 0.501, 0.501], 0, 0),  # degenerate: the floor of two pixels
    ],
)
def test_the_raw_profile_is_decode_pass_crop(box: list[float], dx: int, dy: int) -> None:
    page = noise_page()
    expected = legacy_decode_crop(page, box, dx, dy)
    result = prepare_crop(page, box, profile=RAW, dx=dx, dy=dy)
    assert result is not None
    assert result.pixels.shape == expected.shape
    assert np.array_equal(result.pixels, expected)


def test_the_confirmer_padded_profile_is_confirm_pass_per_box_crop() -> None:
    confirm_pass = load_script("confirm_pass")
    page = noise_page()
    height, width = page.shape[:2]
    box = [0.31, 0.42, 0.37, 0.46]
    bx0 = max(0, int((box[0] - confirm_pass.PAD_X) * width))
    by0 = max(0, int((box[1] - confirm_pass.PAD_Y) * height))
    bx1 = min(width, int((box[2] + confirm_pass.PAD_X) * width))
    by1 = min(height, int((box[3] + confirm_pass.PAD_Y) * height))
    expected = page[by0:by1, bx0:bx1]
    result = prepare_crop(page, box, profile=CONFIRMER_PADDED)
    assert result is not None
    assert np.array_equal(result.pixels, expected)
    assert CONFIRMER_PADDED.pad_x == confirm_pass.PAD_X
    assert CONFIRMER_PADDED.pad_y == confirm_pass.PAD_Y


def test_the_tesseract_profile_upscales_threefold_like_confirm_pass() -> None:
    confirm_pass = load_script("confirm_pass")
    page = noise_page()
    box = [0.31, 0.42, 0.37, 0.46]
    padded = prepare_crop(page, box, profile=CONFIRMER_PADDED)
    result = prepare_crop(page, box, profile=TESSERACT)
    assert padded is not None and result is not None
    assert TESSERACT.upscale == confirm_pass.UPSCALE
    assert result.pixels.shape[0] == padded.pixels.shape[0] * confirm_pass.UPSCALE
    assert result.pixels.shape[1] == padded.pixels.shape[1] * confirm_pass.UPSCALE
    assert result.scale == pytest.approx(3.0)


# --- the crop on a tilted page ---------------------------------------------


def tilted_page(phi: float = 8.0, rect=(200, 300, 400, 330)):
    """A long black rectangle on white, then the page rotated by `phi`
    (counter-clockwise on screen) as a camera would have. Returns the page and
    the detector's box for the rectangle: the hull of its rotated corners."""
    width, height = 640, 480
    page = np.full((height, width), 255, dtype=np.uint8)
    x0, y0, x1, y1 = rect
    page[y0:y1, x0:x1] = 0
    rotated = rotate_image(page, phi, expand=False, border=255)
    frame = PageFrame(theta_deg=phi, width=width, height=height)
    corners = [frame.rotate_pixel(x, y) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    xs = [c[0] for c in corners]
    ys = [c[1] for c in corners]
    hull = [min(xs) / width, min(ys) / height, max(xs) / width, max(ys) / height]
    return rotated, hull, PageFrame(theta_deg=-phi, width=width, height=height)


def fill_ratio(gray) -> float:
    ink = gray < 128
    ys, xs = np.nonzero(ink)
    if not len(xs):
        return 0.0
    area = (xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1)
    return float(ink.sum()) / float(area)


def test_a_crop_on_a_rotate_page_comes_out_upright() -> None:
    """The axis-aligned slice of a tilted rectangle is half empty; the upright
    crop is the rectangle. The engines read what they were trained on."""
    page, hull, frame = tilted_page()
    slanted = prepare_crop(page, hull, profile=RAW)
    upright = prepare_crop(page, hull, frame=frame, profile=RAW)
    assert slanted is not None and upright is not None
    assert fill_ratio(slanted.pixels) < 0.75
    assert fill_ratio(upright.pixels) > 0.93
    assert upright.rotated is True and slanted.rotated is False


def test_a_crop_pixel_maps_back_to_the_source_pixel_it_came_from() -> None:
    """Provenance: a reviewer must be able to see which pixels were read."""
    page, hull, frame = tilted_page()
    for profile in (RAW, TESSERACT, UPRIGHT_GLYPHS):
        for use_frame in (None, frame):
            result = prepare_crop(page, hull, frame=use_frame, profile=profile)
            assert result is not None
            ys, xs = np.nonzero(result.pixels < 128)
            cu, cv = float(xs.mean()), float(ys.mean())
            sx, sy = result.to_source(cu, cv)
            ys2, xs2 = np.nonzero(page < 128)
            assert abs(sx - xs2.mean()) < 1.5, (profile.name, use_frame is not None)
            assert abs(sy - ys2.mean()) < 1.5, (profile.name, use_frame is not None)


# --- glyph-height discipline -----------------------------------------------


def test_a_small_crop_is_upscaled_to_the_target_height_and_a_large_one_is_not() -> None:
    page = noise_page()
    small = prepare_crop(page, [0.10, 0.10, 0.20, 0.125], profile=UPRIGHT_GLYPHS)  # 12 px tall
    assert small is not None
    inner = small.pixels.shape[0] - 2 * UPRIGHT_GLYPHS.border_px
    assert inner >= UPRIGHT_GLYPHS.target_glyph_px
    assert small.scale > 1.0
    large = prepare_crop(page, [0.10, 0.10, 0.30, 0.20], profile=UPRIGHT_GLYPHS)  # 48 px tall
    assert large is not None
    assert large.scale == pytest.approx(1.0)


def test_the_border_is_the_crop_edge_colour_not_black() -> None:
    page = np.full((300, 400, 3), 240, dtype=np.uint8)
    page[100:130, 100:200] = 0
    result = prepare_crop(page, [0.25, 0.33, 0.50, 0.44], profile=CropProfile("b", border_px=8))
    assert result is not None
    assert result.pixels.shape[0] == 33 + 16 and result.pixels.shape[1] == 100 + 16
    assert int(result.pixels[0, 0, 0]) >= 200  # background, not padding-black


def test_a_degenerate_box_yields_nothing() -> None:
    page = noise_page()
    assert prepare_crop(page, [0.5, 0.5, 0.5, 0.5], profile=CONFIRMER_PADDED) is None
