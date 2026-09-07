"""The corpus reader: one definition of which OCR rows are the corpus.

Written before the implementation. Four scripts each wrote their own version of
"select the documents", and the one that mattered — the OCR pass's manifest —
disagreed with the others about thumbnails (KI-009). A reader that every script
imports makes that class of drift impossible.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from kidneymatch.ingestion.photos import QualityBand
from kidneymatch.ocr.anchors import Box
from kidneymatch.ocr.store import OcrDocument, read_corpus

SCHEMA = """
CREATE TABLE ocr_result (
    sha256 TEXT, engine_version TEXT, preproc_version TEXT, rel_path TEXT,
    width INTEGER, height INTEGER, n_boxes INTEGER,
    boxes_json TEXT, texts_json TEXT, confs_json TEXT,
    elapsed_ms REAL, error TEXT, created_utc TEXT,
    PRIMARY KEY (sha256, engine_version, preproc_version)
);
"""


def write_row(
    con: sqlite3.Connection,
    sha: str,
    rel_path: str,
    boxes: list[list[float]],
    texts: list[str],
    width: int = 1280,
    height: int = 960,
    error: str | None = None,
) -> None:
    con.execute(
        "INSERT INTO ocr_result VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            sha,
            "e1",
            "p1",
            rel_path,
            width,
            height,
            len(boxes),
            json.dumps(boxes),
            json.dumps(texts),
            json.dumps([0.9] * len(texts)),
            1.0,
            error,
            "2026-09-02T00:00:00+00:00",
        ),
    )


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "ocr.sqlite"
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    write_row(con, "aaa", "photos/photo_1@x.jpg", [[0.1, 0.5, 0.2, 0.53]], ["DRB1"])
    write_row(
        con, "bbb", "photos/photo_1@x_thumb (2).jpg", [[0.1, 0.5, 0.2, 0.53]], ["DRB1"], 520, 390
    )
    write_row(con, "ccc", "photos/photo_2@x_thumb.jpg", [[0.1, 0.5, 0.2, 0.53]], ["DQB1"], 520, 390)
    write_row(con, "ddd", "photos/photo_3@x.jpg", [], [])
    con.commit()
    con.close()
    return path


def test_thumbnail_rows_are_excluded_from_the_corpus(db: Path) -> None:
    """The pass stored them; the corpus must not contain them.

    The rows stay in the database because a completed pass is immutable
    evidence. Excluding them is the reader's job, in one place.
    """
    assert {doc.sha256 for doc in read_corpus(db)} == {"aaa", "ddd"}


def test_boxes_are_returned_ready_to_resolve(db: Path) -> None:
    doc = next(d for d in read_corpus(db) if d.sha256 == "aaa")
    assert doc.boxes == [Box(0.1, 0.5, 0.2, 0.53, "DRB1")]
    assert doc.quality_band is QualityBand.HIGH
    assert doc.rel_path == "photos/photo_1@x.jpg"


def test_a_document_with_no_boxes_is_still_a_document(db: Path) -> None:
    """An image the OCR read nothing from is evidence of a non-report, not a gap.

    Dropping it would make the denominator of every rate the documents that
    happened to work, which is how a yield gets mistaken for an accuracy.
    """
    empty = next(d for d in read_corpus(db) if d.sha256 == "ddd")
    assert empty.boxes == []


def test_only_documents_with_boxes_when_asked(db: Path) -> None:
    assert {d.sha256 for d in read_corpus(db, with_boxes_only=True)} == {"aaa"}


def test_a_row_whose_boxes_and_texts_disagree_is_refused(tmp_path: Path) -> None:
    """Index alignment between boxes and texts is the whole contract.

    If they ever diverge, every geometric rule silently reads another box's
    text — a wrong-locus generator. Fail loudly instead of skipping quietly.
    """
    path = tmp_path / "bad.sqlite"
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    write_row(con, "eee", "photos/p.jpg", [[0.1, 0.5, 0.2, 0.53]], ["DRB1", "15"])
    con.commit()
    con.close()
    with pytest.raises(ValueError, match="eee"):
        list(read_corpus(path))


def test_rows_that_failed_ocr_are_reported_not_hidden(tmp_path: Path) -> None:
    path = tmp_path / "err.sqlite"
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    write_row(con, "fff", "photos/p.jpg", [], [], error="OSError: truncated")
    con.commit()
    con.close()
    docs = list(read_corpus(path))
    assert len(docs) == 1
    assert docs[0].error == "OSError: truncated"


def test_documents_arrive_in_a_stable_order(db: Path) -> None:
    """Two runs must sample and report identically, or no measurement repeats."""
    assert [d.sha256 for d in read_corpus(db)] == [d.sha256 for d in read_corpus(db)]


def test_the_document_carries_provenance_for_every_derived_fact(db: Path) -> None:
    doc: OcrDocument = next(iter(read_corpus(db)))
    assert doc.engine_version == "e1"
    assert doc.preproc_version == "p1"
