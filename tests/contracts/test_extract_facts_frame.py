"""The extraction runs its row rules in the page frame the geometry pass declared.

A photograph tilted by a few degrees drifts its second allele column out of
the row band; the geometry pass measures the tilt from the printed rulings and,
when two estimators agree, declares ROTATE. This pins how the extraction uses
that: the stored boxes are levelled before any rule runs, provenance is
restored to the boxes as stored, the tilt is recorded on the document, and
without a ROTATE decision nothing changes at all.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

from kidneymatch.hla.vocabulary import load_vocabulary
from kidneymatch.ocr.anchors import Box
from kidneymatch.ocr.geometry import PageFrame
from kidneymatch.ocr.rulings import GEOMETRY_VERSION
from kidneymatch.ocr.store import OcrDocument

pytestmark = pytest.mark.task("OCR-001")

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/extract_facts.py"
WIDTH, HEIGHT = 1000, 1400


def load():
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("km_extract_facts_frame", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def tilt(box: Box, phi_deg: float) -> Box:
    """The detector's axis-aligned hull of this box on a page whose content
    was rotated counter-clockwise by `phi_deg`."""
    frame = PageFrame(theta_deg=phi_deg, width=WIDTH, height=HEIGHT)
    corners = [(box.x0, box.y0), (box.x1, box.y0), (box.x1, box.y1), (box.x0, box.y1)]
    moved = [frame.rotate_pixel(x * WIDTH, y * HEIGHT) for x, y in corners]
    xs = [p[0] / WIDTH for p in moved]
    ys = [p[1] / HEIGHT for p in moved]
    return Box(min(xs), min(ys), max(xs), max(ys), box.text)


# The dominant form: locus printed on every value, second allele far along the
# row. The default rule (no family recognised) caps the chain at 20 label
# heights, so the second value is kept inside that on the level page.
ROW = [
    Box(0.10, 0.50, 0.18, 0.53, "HLA-DRB1"),
    Box(0.22, 0.50, 0.30, 0.53, "DRB1*15"),
    Box(0.52, 0.50, 0.60, 0.53, "DRB1*11"),
    Box(0.10, 0.60, 0.18, 0.63, "HLA-DQB1"),
    Box(0.22, 0.60, 0.30, 0.63, "DQB1*03"),
]
PHI = 12.0


def document(boxes: list[Box], sha: str = "tilted") -> OcrDocument:
    return OcrDocument(
        sha256=sha,
        rel_path="photos/p.jpg",
        boxes=boxes,
        confidences=[],
        width=WIDTH,
        height=HEIGHT,
        engine_version="e1",
        preproc_version="p1",
        error=None,
    )


def by_field(rows: list[tuple]) -> dict[str, dict]:
    columns = [
        "sha256",
        "field",
        "extraction_version",
        "status",
        "value",
        "raw",
        "repaired",
        "second_allele",
        "reason",
        "rule_id",
        "anchor_box",
        "value_boxes",
        "source",
        "engine_version",
        "preproc_version",
        "imgt_version",
        "created_utc",
    ]
    return {row[1]: dict(zip(columns, row, strict=True)) for row in rows}


def test_a_rotate_frame_levels_the_page_and_provenance_stays_as_stored() -> None:
    module = load()
    tilted = [tilt(b, PHI) for b in ROW]
    doc = document(tilted)
    vocabulary = load_vocabulary()

    # Without a frame, the tilted page loses the far allele.
    rows, summary = module.extract(doc, [], vocabulary, "2026-09-05T00:00:00+00:00")
    before = by_field(rows)["DRB1"]
    assert before["value"] != "DRB1*15 DRB1*11"
    assert summary["frame"] == "identity" and summary["tilt_deg"] == 0.0

    # With the frame the geometry pass would give it, both alleles bind.
    frame = PageFrame(theta_deg=-PHI, width=WIDTH, height=HEIGHT)
    rows, summary = module.extract(doc, [], vocabulary, "2026-09-05T00:00:00+00:00", frame=frame)
    after = by_field(rows)["DRB1"]
    assert after["status"] == "RESOLVED", after["reason"]
    assert after["value"] == "DRB1*15 DRB1*11"
    assert after["second_allele"] == "READ"
    assert summary["frame"] == "ROTATE"
    assert summary["tilt_deg"] == pytest.approx(-PHI)

    # Provenance names the boxes the pass STORED, not the levelled ones.
    assert json.loads(after["anchor_box"]) == [
        tilted[0].x0,
        tilted[0].y0,
        tilted[0].x1,
        tilted[0].y1,
    ]
    assert json.loads(after["value_boxes"]) == [
        [b.x0, b.y0, b.x1, b.y1] for b in (tilted[1], tilted[2])
    ]


def test_only_a_rotate_decision_moves_anything(tmp_path: Path) -> None:
    module = load()
    geometry = tmp_path / "geometry.sqlite"
    con = sqlite3.connect(geometry)
    con.execute(
        "CREATE TABLE page_geometry (sha256 TEXT, geometry_version TEXT, decision TEXT, "
        "theta_deg REAL)"
    )
    con.executemany(
        "INSERT INTO page_geometry VALUES (?,?,?,?)",
        [
            ("rot", GEOMETRY_VERSION, "ROTATE", -3.5),
            ("slight", GEOMETRY_VERSION, "ROTATE", -0.9),
            ("straight", GEOMETRY_VERSION, "STRAIGHT", 0.0),
            ("unsure", GEOMETRY_VERSION, "UNCERTAIN", 0.0),
            ("old", "rulings/v0", "ROTATE", -9.0),
        ],
    )
    con.commit()
    con.close()

    loaded = module.load_geometry(geometry)
    assert set(loaded) == {"rot", "slight", "straight", "unsure"}, (
        "another version's rows are not this one's"
    )
    assert module.frame_for(document(ROW, "rot"), loaded) == PageFrame(-3.5, WIDTH, HEIGHT)
    # Measured: under 1.5 degrees the frame gained and lost cells in equal
    # numbers on the pack's tilted pages; the extraction leaves those alone.
    assert module.frame_for(document(ROW, "slight"), loaded) is None
    assert module.frame_for(document(ROW, "straight"), loaded) is None
    assert module.frame_for(document(ROW, "unsure"), loaded) is None
    assert module.frame_for(document(ROW, "unseen"), loaded) is None
    assert module.load_geometry(tmp_path / "missing.sqlite") == {}


def test_a_level_page_with_the_identity_frame_is_unchanged() -> None:
    module = load()
    vocabulary = load_vocabulary()
    plain, _ = module.extract(document(ROW), [], vocabulary, "t")
    framed, summary = module.extract(
        document(ROW), [], vocabulary, "t", frame=PageFrame.identity(WIDTH, HEIGHT)
    )
    assert plain == framed
    assert summary["frame"] == "identity"


def test_the_document_table_carries_the_frame(tmp_path: Path) -> None:
    """Older databases gain the columns; the insert names them."""
    module = load()
    con = module.connect(tmp_path / "facts.sqlite")
    columns = {row[1] for row in con.execute("PRAGMA table_info(document)")}
    assert {"tilt_deg", "frame"} <= columns
    con.close()
    # A database created before the columns existed is migrated on connect.
    legacy = tmp_path / "legacy.sqlite"
    old = sqlite3.connect(legacy)
    old.execute(
        "CREATE TABLE document (sha256 TEXT NOT NULL, extraction_version TEXT NOT NULL, "
        "rel_path TEXT NOT NULL, quality_band TEXT, family TEXT, comparison_sheet INTEGER, "
        "consistency TEXT, consistency_reason TEXT, n_facts INTEGER, created_utc TEXT, "
        "PRIMARY KEY (sha256, extraction_version))"
    )
    old.commit()
    old.close()
    con = module.connect(legacy)
    columns = {row[1] for row in con.execute("PRAGMA table_info(document)")}
    assert {"tilt_deg", "frame"} <= columns
    con.close()
