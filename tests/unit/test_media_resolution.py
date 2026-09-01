from pathlib import Path

import pytest

from kidneymatch.domain.evidence import MediaQuality
from kidneymatch.ingestion.media import resolve_best_available_media

# Acceptance for MEDIA-001 selects on this marker: pytest --task MEDIA-001
pytestmark = pytest.mark.task("MEDIA-001")


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
