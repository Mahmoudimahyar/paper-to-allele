"""The anchored review pack: which documents a person sees, and what leaves it.

Everything runs on a synthetic facts database and synthetic images built here;
nothing touches the corpus.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import subprocess
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
                # Two independent readers, as the corpus now has.
                for confirmer in ("tesseract5/psm7-alnum", "ppocrv5/en-mobile-rec"):
                    con.execute(
                        "INSERT INTO confirmation VALUES (?,?,?,?,?,?,?)",
                        (sha, locus, "facts/v1", confirmer, "CONFIRMED", "11", "t"),
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
    assert set(cell["suggestions"]) == {"pipeline", "tesseract5", "ppocrv5", "decode"}, (
        "every confirmer gets its own row; keying them together would show the "
        "reader whichever engine the database returned last"
    )
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


def test_the_page_never_reaches_the_network_and_records_anchoring() -> None:
    """The reports are the patients'. Nothing on this page may leave the
    machine, and an export from it says it was made with the suggestions
    visible, so it is never mistaken for a blind golden label.

    The check is on what the page LOADS, not on the characters `http`: the
    storage warning names a localhost address in prose, which fetches nothing.
    """
    page = PAGE.read_text(encoding="utf-8")
    assert "window.PACK" in page
    for reaching_out in ("fetch(", "XMLHttpRequest", "WebSocket", "navigator.sendBeacon"):
        assert reaching_out not in page
    for attribute in ('src="http', "src='http", 'href="http', "href='http", "@import"):
        assert attribute not in page
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


def test_an_export_from_the_page_scores_against_the_pack(tmp_path: Path) -> None:
    """The whole point of the pack, end to end.

    `HA-008` tells a person to label and hand the JSON to an agent, who scores
    it with `golden_score.py`. Three files have to agree on one shape for that
    to work — the page's export, the pack's `pipeline.json`, and the scorer —
    and they live apart, so this pins them together: a corrected cell must come
    back as a false acceptance, and the scorer must fail on it.
    """
    module = load()
    db, export = synthetic_corpus(tmp_path, n_docs=20)
    pack_dir = tmp_path / "pack"
    module.build_pack(db, export, pack_dir, 8, 1, PAGE)
    pack = json.loads((pack_dir / "pack.json").read_text(encoding="utf-8"))

    cells: dict[str, object] = {}
    corrected: str | None = None
    for document in pack["documents"]:
        for cell in document["cells"]:
            body = [p.split("*")[-1] for p in (cell["value"] or "").split() if p]
            if cell["status"] != "RESOLVED":
                state, alleles = "NOT_PRINTED", []
            elif cell["kind"] == "DRBX":
                state = "ABSENT" if cell["value"] == "ABSENT" else "PRESENT_ONLY"
                alleles = []
            elif corrected is None:
                corrected, state, alleles = cell["cell_id"], "VALUE", ["11", "16"]
            else:
                state, alleles = "VALUE", body
            cells[cell["cell_id"]] = {
                "locus": cell["locus"],
                "state": state,
                "alleles": alleles,
                "resolution": "FIRST_FIELD" if state == "VALUE" else None,
                "unsure": False,
            }
    assert corrected, "the fixture must contain a resolved cell to disagree with"
    labels = tmp_path / "labels_tester.json"
    labels.write_text(
        json.dumps(
            {"schema": "golden-labels/v1", "annotator": "tester", "anchored": True, "cells": cells}
        ),
        encoding="utf-8",
    )

    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(ROOT / "scripts/golden_score.py"),
            "--labels",
            str(labels),
            str(labels),
            "--hidden",
            str(pack_dir / "pipeline.json"),
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 1, "a false acceptance must fail the gate"
    assert corrected in result.stdout
    assert "FALSE ACCEPTANCE  : 1" in result.stdout


def test_the_pack_can_serve_itself(tmp_path: Path) -> None:
    """A browser may refuse `localStorage` to a page opened off the disk, and
    the labels live there. The page says so if it happens, but the pack also
    ships the one click that makes the question moot."""
    module = load()
    db, export = synthetic_corpus(tmp_path, n_docs=8)
    module.build_pack(db, export, tmp_path / "pack", 4, 1, PAGE)
    windows = (tmp_path / "pack/serve.cmd").read_bytes()
    assert b"http.server" in windows and b"127.0.0.1" in windows
    assert windows.startswith(b"@echo off\r\n"), "cmd.exe wants CRLF, and exactly one"
    assert b"\r\r" not in windows, "the platform translated the line endings twice"
    assert b"127.0.0.1" in (tmp_path / "pack/serve.sh").read_bytes()
    page = PAGE.read_text(encoding="utf-8")
    assert "storageWorks" in page, "and the page must still notice when it cannot save"


def test_the_page_preselects_the_state_the_refusal_reason_implies() -> None:
    """1,650 cells in a 150-document pack, and 850 of them are the pipeline
    saying it read nothing for a reason it already recorded.

    "no anchor on this document" means the form does not print that locus;
    "no box at all in its cell" means it does and the cell is empty. Making the
    reader pick that from a dropdown 850 times would cost the labelling its
    afternoon, and the reason is already in the pack.
    """
    page = PAGE.read_text(encoding="utf-8")
    assert "function defaultStateFor(cell)" in page
    assert "no anchor on this document" in page
    assert "no box at all" in page
    for state in ("NOT_PRINTED", "BLANK"):
        assert state in page.split("function defaultStateFor(cell)")[1].split("}")[0] or True
    body = page.split("function defaultStateFor(cell)")[1][:900]
    assert "'NOT_PRINTED'" in body and "'BLANK'" in body and "'VALUE'" in body
