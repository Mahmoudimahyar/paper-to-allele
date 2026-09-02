"""Read the OCR pass as a corpus.

One definition of which stored rows are the corpus, imported by every script,
because the project has already been bitten by having several. The OCR pass's
own manifest disagreed with the analysis scripts about what a thumbnail is, and
9,581 thumbnail copies became 29% of the corpus (KI-009).

The stored pass is **immutable evidence**: rows are never deleted or rewritten,
including the thumbnail rows. Exclusion happens here, on read, where it can be
tested once.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from kidneymatch.ingestion.photos import QualityBand, is_thumbnail, quality_band
from kidneymatch.ocr.anchors import Box


@dataclass(frozen=True, slots=True)
class OcrDocument:
    """One source image and everything the pass recorded about it."""

    sha256: str
    rel_path: str
    boxes: list[Box]
    confidences: list[float]
    width: int | None
    height: int | None
    engine_version: str
    preproc_version: str
    error: str | None

    @property
    def quality_band(self) -> QualityBand:
        return quality_band(self.width, self.height)


def _boxes(sha: str, boxes_json: str, texts_json: str) -> list[Box]:
    raw = json.loads(boxes_json or "[]")
    texts = json.loads(texts_json or "[]")
    if len(raw) != len(texts):
        # Index alignment between geometry and text is the entire contract of
        # this table. If it ever breaks, every geometric rule reads another
        # box's text and silently binds values to the wrong locus. Refuse.
        raise ValueError(
            f"{sha}: {len(raw)} boxes but {len(texts)} texts; "
            "geometry and text are not index-aligned"
        )
    return [Box(b[0], b[1], b[2], b[3], t) for b, t in zip(raw, texts, strict=True)]


def read_corpus(
    db: Path,
    *,
    with_boxes_only: bool = False,
    engine_version: str | None = None,
    preproc_version: str | None = None,
) -> Iterator[OcrDocument]:
    """Yield the corpus documents, thumbnails excluded, in a stable order.

    Images the recognizer found no text in are still documents. They are the
    evidence that the corpus contains advertisements and screenshots as well as
    reports, and dropping them would make every rate a rate over the documents
    that happened to work.
    """
    con = sqlite3.connect(db)
    try:
        query = (
            "SELECT sha256, rel_path, width, height, boxes_json, texts_json, confs_json, "
            "engine_version, preproc_version, error FROM ocr_result"
        )
        where: list[str] = []
        params: list[str] = []
        if engine_version is not None:
            where.append("engine_version = ?")
            params.append(engine_version)
        if preproc_version is not None:
            where.append("preproc_version = ?")
            params.append(preproc_version)
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY sha256"

        for row in con.execute(query, params):
            sha, rel_path, width, height, boxes_json, texts_json, confs_json, eng, pre, error = row
            if is_thumbnail(rel_path):
                continue
            boxes = _boxes(sha, boxes_json, texts_json)
            if with_boxes_only and not boxes:
                continue
            yield OcrDocument(
                sha256=sha,
                rel_path=rel_path,
                boxes=boxes,
                confidences=json.loads(confs_json or "[]"),
                width=width,
                height=height,
                engine_version=eng,
                preproc_version=pre,
                error=error,
            )
    finally:
        con.close()
