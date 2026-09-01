from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kidneymatch.domain.evidence import MediaQuality


@dataclass(frozen=True, slots=True)
class ResolvedMedia:
    path: Path
    quality: MediaQuality
    referenced_href: str | None
    referenced_thumbnail: str | None


def resolve_best_available_media(
    export_root: Path,
    href: str | None,
    thumbnail_src: str | None,
) -> ResolvedMedia | None:
    """Return the best physically present asset without assuming a missing original exists."""
    candidates: list[tuple[str | None, MediaQuality]] = [
        (href, MediaQuality.HIGH_RES_AVAILABLE),
        (thumbnail_src, MediaQuality.THUMBNAIL_ONLY),
    ]
    seen: set[Path] = set()
    for relative, assumed_quality in candidates:
        if not relative:
            continue
        path = (export_root / relative).resolve()
        if path in seen:
            continue
        seen.add(path)
        if path.is_file():
            # If the href itself is a thumb, do not call it high-res.
            quality = MediaQuality.THUMBNAIL_ONLY if "_thumb" in path.name else assumed_quality
            return ResolvedMedia(path, quality, href, thumbnail_src)
    return None
