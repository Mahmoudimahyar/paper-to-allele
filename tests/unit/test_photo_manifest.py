"""Which files in a Telegram export are the corpus, and which are thumbnails.

Written before the implementation. This is the cheapest possible test and it
would have prevented the most expensive mistake in the project so far: the OCR
pass's manifest tested `endswith("_thumb.jpg")`, so 9,581 Windows-style copies
named `photo_N@date_thumb (2).jpg` entered the corpus as "unique originals".
They became 29% of the OCR pass, the entire apparent low-resolution tail, 1,164
Persian-pass rows, 373 template-family members and 54 of 199 golden-sample
documents — while their originals sat on disk unread (KI-009).

`DEDUPE-001` already says a renamed thumbnail must not be mistaken for an
original; nothing checked it against the export's real naming.
"""

from __future__ import annotations

import pytest

from kidneymatch.ingestion.photos import QualityBand, is_original_photo, quality_band

ORIGINAL = "photo_12345@31-08-2026_12-30-01.jpg"


@pytest.mark.parametrize(
    "name",
    [
        ORIGINAL,
        "photo_1@01-01-2020_00-00-00.jpg",
        # A copy of an ORIGINAL is still an original.
        "photo_12345@31-08-2026_12-30-01 (2).jpg",
    ],
)
def test_original_photos_are_in_the_corpus(name: str) -> None:
    assert is_original_photo(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "photo_12345@31-08-2026_12-30-01_thumb.jpg",
        # The regression. A suffix test lets every one of these through.
        "photo_12345@31-08-2026_12-30-01_thumb (2).jpg",
        "photo_12345@31-08-2026_12-30-01_thumb (17).jpg",
        "photo_12345@31-08-2026_12-30-01_thumb.JPG",
    ],
)
def test_no_thumbnail_spelling_is_ever_treated_as_an_original(name: str) -> None:
    """A thumbnail is identified by the `_thumb` marker anywhere in the name.

    Measured on the real export: 113,008 files match `_thumb (n).jpg` and every
    one has its original present. Reading them instead of their originals is
    silent data loss, not a duplicate.
    """
    assert is_original_photo(name) is False


@pytest.mark.parametrize("name", ["messages.html", "photo.png", "video.mp4", "photo_1.txt"])
def test_non_photo_files_are_not_in_the_corpus(name: str) -> None:
    assert is_original_photo(name) is False


@pytest.mark.parametrize("name", ["photo_1.jpeg", "photo_1.JPG", "photo_1.JPEG"])
def test_every_jpeg_spelling_counts_as_a_photo(name: str) -> None:
    """The export writes `.jpg`, but a missed photo is data loss.

    Erring towards including a file is safe here: the thumbnail test above is
    what protects the corpus, and it runs on every spelling.
    """
    assert is_original_photo(name) is True


@pytest.mark.invariant("DEDUPE-001", "missing higher-resolution asset is not treated as an error")
def test_a_thumbnail_is_still_recognised_when_its_original_is_absent() -> None:
    """Classification is a property of the NAME, not of what else exists.

    Whether the original is present decides `MediaQuality` (see
    `ingestion/media.py`); it must not decide whether the file is a thumbnail.
    Conflating the two is how a thumbnail became a corpus member.
    """
    assert is_original_photo("photo_9@01-01-2020_00-00-00_thumb.jpg") is False


# --- quality bands -------------------------------------------------------
#
# The bands exist so that a low-resolution critical field can be routed to
# mandatory review (`OCR-001`: "thumbnail critical field requires human
# review"). The corrected corpus is 90.0% >900 px, 9.7% 561-900 px and 0.4%
# <=560 px; the earlier "77% at ~520 px" was the thumbnail contamination.


@pytest.mark.parametrize(
    ("width", "height", "expected"),
    [
        (1280, 960, QualityBand.HIGH),
        (960, 1280, QualityBand.HIGH),  # portrait: the LONGEST edge decides
        (901, 100, QualityBand.HIGH),
        (900, 700, QualityBand.MID),
        (561, 100, QualityBand.MID),
        (560, 420, QualityBand.LOW),
        (100, 100, QualityBand.LOW),
    ],
)
def test_quality_band_uses_the_longest_edge(width: int, height: int, expected: QualityBand) -> None:
    assert quality_band(width, height) is expected


@pytest.mark.parametrize(("width", "height"), [(None, None), (0, 0), (None, 500), (500, None)])
def test_unmeasurable_dimensions_are_unknown_not_low(width: int | None, height: int | None) -> None:
    """An unreadable image is UNKNOWN.

    Calling it LOW would silently claim we measured something we did not, and
    calling it HIGH would skip the review gate. `AGENTS.md`: missing values are
    UNKNOWN, never a default.
    """
    assert quality_band(width, height) is QualityBand.UNKNOWN
