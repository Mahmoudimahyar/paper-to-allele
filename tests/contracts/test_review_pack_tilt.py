"""The next review pack labels the page frame directly.

The extraction levels a page the rulings measured tilted 1.5 degrees or more
before binding its rows (`extract_facts.py --geometry`). Whether that helped
or hurt is what a labelled sample has to say, so the pack builder draws a
`tilted` stratum from `document.frame` and carries the tilt on each document.
A facts database from before the geometry pass has no such columns and must
still build a pack.

Synthetic databases only; nothing here touches the corpus.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.task("OCR-001")

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/review_pack.py"


def load():
    spec = importlib.util.spec_from_file_location("km_review_pack_tilt", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["km_review_pack_tilt"] = module
    spec.loader.exec_module(module)
    return module


def facts_db(tmp_path: Path, *, with_frame_columns: bool) -> Path:
    db = tmp_path / ("framed.sqlite" if with_frame_columns else "legacy.sqlite")
    con = sqlite3.connect(db)
    extra = ", tilt_deg REAL, frame TEXT" if with_frame_columns else ""
    con.executescript(
        f"""
        CREATE TABLE fact (sha256, field, extraction_version, status, value, raw, repaired,
            second_allele, reason, rule_id, anchor_box, value_boxes, source, engine_version,
            preproc_version, imgt_version, created_utc, stability);
        CREATE TABLE document (sha256, extraction_version, rel_path, quality_band, family,
            comparison_sheet, consistency, consistency_reason, n_facts, created_utc{extra});
        CREATE TABLE confirmation (sha256, field, extraction_version, confirmer_version,
            verdict, reading, created_utc);
        CREATE TABLE decode (sha256, field, extraction_version, decoder_version, verdict,
            reading, jitter_readings, grammar_cost, created_utc);
        """
    )
    for i in range(4):
        sha = hashlib.sha256(f"tilt fixture {i}".encode()).hexdigest()
        base = (
            sha,
            "facts/v1",
            f"photos/r{i}.jpg",
            "HIGH",
            "FORM#1",
            0,
            "CONSISTENT",
            None,
            3,
            "t",
        )
        if with_frame_columns:
            # Two levelled pages, one straight, one from before the pass ran.
            frame = [(-2.4, "ROTATE"), (3.1, "ROTATE"), (0.0, "identity"), (None, None)][i]
            con.execute("INSERT INTO document VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (*base, *frame))
        else:
            con.execute("INSERT INTO document VALUES (?,?,?,?,?,?,?,?,?,?)", base)
        for locus in ("A", "B", "DRB1"):
            con.execute(
                "INSERT INTO fact VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    sha,
                    locus,
                    "facts/v1",
                    "RESOLVED",
                    f"{locus}*11 {locus}*15",
                    None,
                    0,
                    "READ",
                    None,
                    "family",
                    "[0.1,0.5,0.2,0.53]",
                    "[[0.3,0.5,0.4,0.53]]",
                    "OCR",
                    "e",
                    "p",
                    "3620",
                    "t",
                    "UNANIMOUS",
                ),
            )
    con.commit()
    con.close()
    return db


def test_a_levelled_page_is_its_own_stratum(tmp_path: Path) -> None:
    module = load()
    con = sqlite3.connect(facts_db(tmp_path, with_frame_columns=True))
    docs = module.load_documents(con)
    con.close()
    tags = {doc.frame: module.tag_document(doc, tmp_path) for doc in docs.values()}
    assert "tilted" in tags["ROTATE"]
    assert "tilted" not in tags["identity"]
    assert "tilted" not in tags[None]
    rotated = [d for d in docs.values() if d.frame == "ROTATE"]
    assert sorted(d.tilt_deg for d in rotated) == [-2.4, 3.1]
    assert any(t == "tilted" for t, _, _ in module.STRATA)


def test_a_database_from_before_the_geometry_pass_still_loads(tmp_path: Path) -> None:
    """No frame columns: every page is unframed, and nothing raises."""
    module = load()
    con = sqlite3.connect(facts_db(tmp_path, with_frame_columns=False))
    docs = module.load_documents(con)
    con.close()
    assert len(docs) == 4
    assert all(doc.frame is None and doc.tilt_deg is None for doc in docs.values())
    assert all("tilted" not in module.tag_document(doc, tmp_path) for doc in docs.values())
