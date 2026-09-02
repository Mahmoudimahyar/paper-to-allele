from pathlib import Path

import pytest

from kidneymatch.domain.evidence import MediaQuality
from kidneymatch.ingestion.media import resolve_best_available_media

# Acceptance for MEDIA-001 selects on this marker: pytest --task MEDIA-001
pytestmark = pytest.mark.task("MEDIA-001")


@pytest.mark.invariant("DEDUPE-001", "missing higher-resolution asset is not treated as an error")
def test_thumbnail_is_used_when_linked_higher_quality_file_is_absent(tmp_path: Path) -> None:
    (tmp_path / "photos").mkdir()
    thumb = tmp_path / "photos/report_thumb.jpg"
    thumb.write_bytes(b"thumb")

    resolved = resolve_best_available_media(
        tmp_path,
        "photos/report.jpg",
        "photos/report_thumb.jpg",
    )

    assert resolved is not None
    assert resolved.path == thumb.resolve()
    assert resolved.quality is MediaQuality.THUMBNAIL_ONLY


def test_a_reference_repeated_in_both_slots_is_only_tried_once(tmp_path: Path) -> None:
    """Some exports point href and the thumbnail at the same missing file.

    The candidate must not be probed twice, and a degenerate reference must
    still resolve to "no asset" rather than an error.
    """
    (tmp_path / "photos").mkdir()
    same = "photos/only_reference.jpg"

    assert resolve_best_available_media(tmp_path, same, same) is None

    (tmp_path / same).write_bytes(b"present")
    resolved = resolve_best_available_media(tmp_path, same, same)
    assert resolved is not None
    assert resolved.quality is MediaQuality.HIGH_RES_AVAILABLE


def test_href_is_preferred_only_when_it_physically_exists(tmp_path: Path) -> None:
    (tmp_path / "photos").mkdir()
    original = tmp_path / "photos/report.jpg"
    original.write_bytes(b"best")
    (tmp_path / "photos/report_thumb.jpg").write_bytes(b"thumb")

    resolved = resolve_best_available_media(
        tmp_path, "photos/report.jpg", "photos/report_thumb.jpg"
    )

    assert resolved is not None
    assert resolved.path == original.resolve()
    assert resolved.quality is MediaQuality.HIGH_RES_AVAILABLE
