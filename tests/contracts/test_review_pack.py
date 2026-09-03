"""The anchored review pack: which documents a person sees, and what leaves it.

Everything runs on a synthetic facts database and synthetic images built here;
nothing touches the corpus.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.task("BOOT-001")

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/review_pack.py"
PAGE = ROOT / "tools/hla_review.html"


def load():
    spec = importlib.util.spec_from_file_location("km_review_pack", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["km_review_pack"] = module  # slots dataclasses resolve names through it
    spec.loader.exec_module(module)
    return module


FACT_COLUMNS = (
    "sha256, field, extraction_version, status, value, raw, repaired, second_allele, reason, "
    "rule_id, anchor_box, value_boxes, source, engine_version, preproc_version, imgt_version, "
    "created_utc, stability"
)


def synthetic_corpus(tmp_path: Path, n_docs: int = 40) -> tuple[Path, Path]:
    """`n_docs` synthetic reports with every failure signal represented."""
    from PIL import Image, ImageDraw

    export = tmp_path / "export"
    (export / "photos").mkdir(parents=True)
    db = tmp_path / "facts.sqlite"
    con = sqlite3.connect(db)
    con.executescript(
        f"""
        CREATE TABLE fact ({FACT_COLUMNS});
        CREATE TABLE document (sha256, extraction_version, rel_path, quality_band, family,
            comparison_sheet, consistency, consistency_reason, n_facts, created_utc);
        CREATE TABLE confirmation (sha256, field, extraction_version, confirmer_version,
            verdict, reading, created_utc);
        CREATE TABLE decode (sha256, field, extraction_version, decoder_version, verdict,
            reading, jitter_readings, grammar_cost, created_utc);
        """
    )
    loci = ("A", "B", "C", "DRB1", "DQA1", "DQB1", "DPA1", "DPB1", "DRB3", "DRB4", "DRB5")
    for i in range(n_docs):
        sha = hashlib.sha256(f"synthetic report {i}".encode()).hexdigest()
        rel = f"photos/report_{i}.jpg"
        image = Image.new("RGB", (800, 600), "white")
        draw = ImageDraw.Draw(image)
        for row, locus in enumerate(loci):
            y = 40 + row * 40
            draw.text((40, y), f"HLA-{locus}", fill="black")
            draw.text((200, y), "11 15" if locus in loci[:8] else "PRESENT", fill="black")
        image.save(export / rel, quality=85)
        # Signals, one per document in rotation, so every stratum has members;
        # 8 and 9 carry no signal at all and are the clean controls.
        signal = i % 10
        band = "LOW" if signal == 1 else ("MID" if signal == 2 else "HIGH")
        consistency = "FORBIDDEN_GENE_PRESENT" if signal == 0 else "CONSISTENT"
        family = None if signal == 3 else "FORM#1"
        con.execute(
            "INSERT INTO document VALUES (?,?,?,?,?,?,?,?,?,?)",
            (sha, "facts/v1", rel, band, family, int(signal == 4), consistency, None, 8, "t"),
        )
        for row, locus in enumerate(loci):
            y0, y1 = (40 + row * 40) / 600, (60 + row * 40) / 600
            anchor = json.dumps([0.05, y0, 0.15, y1])
            boxes = json.dumps([[0.25, y0, 0.30, y1], [0.32, y0, 0.37, y1]])
            status, value = "RESOLVED", (f"{locus}*11 {locus}*15" if row < 8 else "PRESENT")
            if signal == 7 and locus == "A":
                status, value = "REVIEW_REQUIRED", None
            con.execute(
                f"INSERT INTO fact ({FACT_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    sha,
                    locus,
                    "facts/v1",
                    status,
                    value,
                    value,
                    int(signal == 5 and locus == "B"),
                    "UNREAD" if signal == 6 and locus == "C" else "READ",
                    "3 candidate values exceeds max_values=2" if status != "RESOLVED" else None,
                    "family",
                    anchor,
                    boxes,
                    "OCR",
                    "e",
                    "p",
                    "3620",
                    "t",
                    "UNANIMOUS" if status == "RESOLVED" else "NOT_CHECKED",
                ),
            )
            if row < 8:
                con.execute(
                    "INSERT INTO confirmation VALUES (?,?,?,?,?,?,?)",
                    (sha, locus, "facts/v1", "tess", "CONFIRMED", "11", "t"),
                )
                verdict = "UNANIMOUS"
                if signal == 7 and locus == "A":
                    verdict = "PROPOSAL"
                con.execute(
                    "INSERT INTO decode VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        sha,
                        locus,
                        "facts/v1",
                        "ctc-viterbi/v1",
                        verdict,
                        "11",
                        json.dumps({"0:11": 9}),
                        0.0,
                        "t",
                    ),
                )
        for fld, value in (("ROLE", "DONOR"), ("ABO", "O"), ("RH", "POSITIVE")):
            con.execute(
                f"INSERT INTO fact ({FACT_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    sha,
                    fld,
                    "facts/v1",
                    "RESOLVED",
                    value,
                    value,
                    0,
                    None,
                    None,
                    None,
                    None,
                    None,
                    "FORM_FIELD",
                    "e",
                    "p",
                    None,
                    "t",
                    "NOT_CHECKED",
                ),
            )
    con.commit()
    con.close()
    return db, export


def test_every_failure_signal_fills_its_own_stratum(tmp_path: Path) -> None:
    """A random sample would be nearly all easy cells; the pack draws from
    each signal the pipeline already emits, rarest first."""
    module = load()
    db, export = synthetic_corpus(tmp_path)
    counts = module.build_pack(db, export, tmp_path / "pack", 24, 1, PAGE)
    for tag in (
        "consistency_flag",
        "low_res",
        "mid_res",
        "default_rule",
        "comparison_sheet",
        "repaired_glyph",
        "unread_second",
        "proposal",
        "clean_control",
    ):
        assert counts[tag] >= 1, tag
    pack = json.loads((tmp_path / "pack/pack.json").read_text(encoding="utf-8"))
    assert pack["schema"] == "hla-review-pack/v1"
    assert pack["n_documents"] == 24


def test_a_document_lands_in_its_rarest_stratum_but_keeps_every_tag(tmp_path: Path) -> None:
    module = load()
    db, export = synthetic_corpus(tmp_path, n_docs=8)
    module.build_pack(db, export, tmp_path / "pack", 8, 1, PAGE)
    pack = json.loads((tmp_path / "pack/pack.json").read_text(encoding="utf-8"))
    flagged = next(d for d in pack["documents"] if d["consistency"] == "FORBIDDEN_GENE_PRESENT")
    assert flagged["primary_tag"] == "consistency_flag"
    assert flagged["tags"][0] == "consistency_flag"


def test_the_pack_is_deterministic_for_a_seed(tmp_path: Path) -> None:
    """Two people must be able to label the same documents."""
    module = load()
    db, export = synthetic_corpus(tmp_path)
    module.build_pack(db, export, tmp_path / "a", 20, 7, PAGE)
    module.build_pack(db, export, tmp_path / "b", 20, 7, PAGE)
    ids = lambda p: [d["id"] for d in json.loads((p / "pack.json").read_text("utf-8"))["documents"]]  # noqa: E731
    assert ids(tmp_path / "a") == ids(tmp_path / "b")


def test_cell_ids_and_the_pipeline_file_match_the_golden_conventions(tmp_path: Path) -> None:
    """`golden_score.py` reads labels and the pipeline's answers by cell id
    `<sha256[:16]>:<LOCUS>`; a pack that used any other id could not be scored."""
    module = load()
    db, export = synthetic_corpus(tmp_path, n_docs=8)
    module.build_pack(db, export, tmp_path / "pack", 4, 1, PAGE)
    pipeline = json.loads((tmp_path / "pack/pipeline.json").read_text(encoding="utf-8"))
    pack = json.loads((tmp_path / "pack/pack.json").read_text(encoding="utf-8"))
    for doc in pack["documents"]:
        for cell in doc["cells"]:
            assert cell["cell_id"] == f"{doc['sha256'][:16]}:{cell['locus']}"
            entry = pipeline["cells"][cell["cell_id"]]
            assert set(entry) == {"status", "locus", "value", "rule"}
            assert entry["status"] == cell["status"]


def test_every_engine_reading_travels_with_the_cell(tmp_path: Path) -> None:
    """The page shows what each engine read; a cell without them is a blind
    label, which is the other tool's job."""
    module = load()
    db, export = synthetic_corpus(tmp_path, n_docs=8)
    suggestions = tmp_path / "sugg"
    suggestions.mkdir()
    (suggestions / "newengine.json").write_text(
        json.dumps(
            {
                "engine": "newengine",
                "cells": {
                    hashlib.sha256(b"synthetic report 0").hexdigest()[:16] + ":A": "A*11 A*15"
                },
            }
        ),
        encoding="utf-8",
    )
    module.build_pack(db, export, tmp_path / "pack", 8, 1, PAGE, suggestions)
    pack = json.loads((tmp_path / "pack/pack.json").read_text(encoding="utf-8"))
    cell = next(c for d in pack["documents"] for c in d["cells"] if c["locus"] == "B")
    assert set(cell["suggestions"]) == {"pipeline", "tesseract", "decode"}
    assert cell["suggestions"]["decode"]["votes"] == {"0:11": 9}
    assert pack["engines"] == ["newengine"]
    assert (
        pack["suggestions"]["newengine"][
            hashlib.sha256(b"synthetic report 0").hexdigest()[:16] + ":A"
        ]
        == "A*11 A*15"
    )


def test_a_refused_cell_shows_the_row_not_nothing(tmp_path: Path) -> None:
    """The reader has to be able to see what the resolver refused."""
    module = load()
    db, export = synthetic_corpus(tmp_path, n_docs=8)
    module.build_pack(db, export, tmp_path / "pack", 8, 1, PAGE)
    pack = json.loads((tmp_path / "pack/pack.json").read_text(encoding="utf-8"))
    refused = [c for d in pack["documents"] for c in d["cells"] if c["status"] == "REVIEW_REQUIRED"]
    assert refused
    for cell in refused:
        assert cell["crop"] and (tmp_path / "pack" / cell["crop"]).exists()
        assert cell["suggestions"]["pipeline"]["reason"]


def test_the_page_is_self_contained_and_records_anchoring() -> None:
    """The pack opens from disk with no server, and an export from it says it
    was made with the suggestions visible, so it is never mistaken for a blind
    golden label."""
    page = PAGE.read_text(encoding="utf-8")
    assert "window.PACK" in page
    assert "fetch(" not in page and "http://" not in page and "https://" not in page
    assert "anchored: true" in page
    assert "golden-labels/v1" in page
    for decision in ("APPROVED", "EDITED", "ADDED"):
        assert decision in page
    for state in (
        "VALUE",
        "NOT_PRINTED",
        "BLANK",
        "UNREADABLE",
        "PRESENT_ONLY",
        "ABSENT",
        "NOT_A_REPORT",
    ):
        assert f"'{state}'" in page


def test_the_pack_directory_is_never_committable() -> None:
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/review/*" in ignore
