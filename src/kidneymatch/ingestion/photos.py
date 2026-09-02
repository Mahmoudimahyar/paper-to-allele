"""What counts as a corpus photo, and how good it is.

One definition, imported by every pass and every analysis script, because the
project has already paid for having two.

**The mistake this module exists to prevent.** A Telegram HTML export writes, for
each photo, an original `photo_N@date.jpg` and a thumbnail `photo_N@date_thumb.jpg`
— and, when the same thumbnail is written more than once, Windows-style copies
`photo_N@date_thumb (2).jpg`. The OCR pass's manifest excluded thumbnails with
`name.endswith("_thumb.jpg")`, which matches the first spelling and not the
second. 9,581 thumbnail copies therefore entered the corpus as unique originals:
29% of the OCR pass, the whole apparent low-resolution tail, 1,164 Persian-pass
rows, 373 template-family members and 54 of 199 golden-sample documents. Every
one of them had its original sitting unread on disk.

That is silent data loss rather than duplication, and no yield metric could show
it — the pass reported 33,147 successes.
"""

from __future__ import annotations

from enum import StrEnum

# The export's marker for a reduced-size copy. It appears before the extension
# and before any copy counter, so membership is the only safe test.
THUMBNAIL_MARKER = "_thumb"

PHOTO_SUFFIXES = (".jpg", ".jpeg")

# Longest-edge boundaries, in pixels.
#
# Measured over the 23,566 true unique originals: 90.0% above 900 px, 9.7%
# between 561 and 900, 0.4% at or below 560. HA-003 asks a human to set the
# threshold that forces mandatory review; these bands are the measurement
# vocabulary for that decision, not the decision itself.
LOW_MAX_EDGE = 560
MID_MAX_EDGE = 900


class QualityBand(StrEnum):
    """Resolution band of a source image.

    `UNKNOWN` is a real outcome, not a gap to be filled: an image whose
    dimensions could not be read has not been measured, and treating it as LOW
    would claim a measurement we do not have while treating it as HIGH would
    skip the review gate `OCR-001` requires for low-resolution critical fields.
    """

    HIGH = "HIGH"
    MID = "MID"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


def is_thumbnail(name: str) -> bool:
    """True if the file name marks a reduced-size copy, in any spelling."""
    return THUMBNAIL_MARKER in name.lower()


def is_original_photo(name: str) -> bool:
    """True for a full-size photo of the archive; False for thumbnails and non-photos.

    This is a property of the NAME alone. Whether a better file exists elsewhere
    decides `MediaQuality` (`ingestion/media.py`); it must never decide whether
    a file is a thumbnail, because a thumbnail whose original is missing is
    still a thumbnail.
    """
    lowered = name.lower()
    return lowered.endswith(PHOTO_SUFFIXES) and not is_thumbnail(lowered)


def quality_band(width: int | None, height: int | None) -> QualityBand:
    """Resolution band from the longest edge.

    The longest edge is the right measure because these are photographs of a
    printed page in either orientation; the short edge would classify the same
    document differently depending on how the phone was held.

    BOTH dimensions must be known. With only one, the longest edge is a lower
    bound, not a measurement: a 500 px height says nothing about whether the
    width is 400 or 4,000. Reporting a band from a lower bound would put a real
    measurement and a guess into the same field.
    """
    if not width or not height or width <= 0 or height <= 0:
        return QualityBand.UNKNOWN
    longest = max(width, height)
    if longest <= LOW_MAX_EDGE:
        return QualityBand.LOW
    if longest <= MID_MAX_EDGE:
        return QualityBand.MID
    return QualityBand.HIGH
