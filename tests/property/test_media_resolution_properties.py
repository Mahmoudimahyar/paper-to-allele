"""Property-based tests for best-available media resolution.

The archive this will run against contains many images whose linked original is
simply absent, so the interesting cases are the ones where files are missing,
partially present, or named misleadingly. Those are what a property test
generates and a hand-written example tends to skip.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from kidneymatch.domain.evidence import MediaQuality
from kidneymatch.ingestion.media import resolve_best_available_media

# Filenames without path separators or characters that are illegal on Windows.
STEM = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), max_codepoint=122),
    min_size=1,
    max_size=12,
)
PRESENCE = st.sampled_from(["both", "original", "thumb", "neither"])


def _build(root: Path, stem: str, presence: str) -> tuple[str, str]:
    photos = root / "photos"
    photos.mkdir(exist_ok=True)
    original_rel = f"photos/{stem}.jpg"
    thumb_rel = f"photos/{stem}_thumb.jpg"
    if presence in ("both", "original"):
        (root / original_rel).write_bytes(b"original")
    if presence in ("both", "thumb"):
        (root / thumb_rel).write_bytes(b"thumb")
    return original_rel, thumb_rel


@given(stem=STEM, presence=PRESENCE)
def test_it_never_returns_a_path_that_does_not_exist(stem: str, presence: str) -> None:
    """The pipeline must not claim an asset it cannot open.

    Spec: "the pipeline MUST NOT block forever waiting for a nonexistent
    original" - and equally must not pretend one is there.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original, thumb = _build(root, stem, presence)
        resolved = resolve_best_available_media(root, original, thumb)
        if resolved is not None:
            assert resolved.path.is_file()


@given(stem=STEM, presence=PRESENCE)
def test_nothing_present_means_no_asset_rather_than_an_error(stem: str, presence: str) -> None:
    """A missing higher-resolution asset is evidence, not a failure."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original, thumb = _build(root, stem, presence)
        resolved = resolve_best_available_media(root, original, thumb)
        assert (resolved is None) == (presence == "neither")


@given(stem=STEM, presence=PRESENCE)
def test_a_thumbnail_is_never_reported_as_high_resolution(stem: str, presence: str) -> None:
    """Quality drives whether human review is mandatory before Gold.

    Over-reporting quality here would let a thumbnail-derived HLA value skip the
    review the constitution requires.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original, thumb = _build(root, stem, presence)
        resolved = resolve_best_available_media(root, original, thumb)
        if resolved is None:
            return
        if "_thumb" in resolved.path.name:
            assert resolved.quality is MediaQuality.THUMBNAIL_ONLY


@given(stem=STEM, presence=PRESENCE)
def test_the_original_wins_whenever_it_is_physically_present(stem: str, presence: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original, thumb = _build(root, stem, presence)
        resolved = resolve_best_available_media(root, original, thumb)
        if presence in ("both", "original"):
            assert resolved is not None
            assert resolved.path.name == f"{stem}.jpg"
            assert resolved.quality is MediaQuality.HIGH_RES_AVAILABLE


@given(stem=STEM, presence=PRESENCE)
def test_the_source_references_are_preserved_for_provenance(stem: str, presence: str) -> None:
    """Every derived fact must point back at what it came from."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original, thumb = _build(root, stem, presence)
        resolved = resolve_best_available_media(root, original, thumb)
        if resolved is not None:
            assert resolved.referenced_href == original
            assert resolved.referenced_thumbnail == thumb


@given(stem=STEM)
def test_a_missing_reference_is_tolerated(stem: str) -> None:
    """Real exports contain messages with only one of the two references."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _build(root, stem, "thumb")
        assert resolve_best_available_media(root, None, f"photos/{stem}_thumb.jpg") is not None
        assert resolve_best_available_media(root, None, None) is None
