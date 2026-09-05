"""`extract_facts.run()` end to end on a synthetic OCR pass, with a page frame.

`extract()` is pure and well covered; `run()` is where the geometry file is
read, the frame chosen per document, and the document row written with its
named columns — none of which any test exercised. A wrong column order there
would mis-store the tilt on every document at run time and nowhere else.

Synthetic databases only; nothing here touches the corpus.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

from kidneymatch.ocr.anchors import Box
from kidneymatch.ocr.geometry import PageFrame
from kidneymatch.ocr.rulings import GEOMETRY_VERSION

pytestmark = pytest.mark.task("OCR-001")

ROOT = Path(__file__).resolve().parents[2]
WIDTH, HEIGHT = 1000, 1400
PHI = 12.0


def load(name: str):
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(f"km_{name}_run", ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def tilt(box: Box, phi_deg: float) -> Box:
    frame = PageFrame(theta_deg=phi_deg, width=WIDTH, height=HEIGHT)
    corners = [(box.x0, box.y0), (box.x1, box.y0), (box.x1, box.y1), (box.x0, box.y1)]
    moved = [frame.rotate_pixel(x * WIDTH, y * HEIGHT) for x, y in corners]
    xs = [p[0] / WIDTH for p in moved]
    ys = [p[1] / HEIGHT for p in moved]
    return Box(min(xs), min(ys), max(xs), max(ys), box.text)


ROW = [
    Box(0.10, 0.50, 0.18, 0.53, "HLA-DRB1"),
    Box(0.22, 0.50, 0.30, 0.53, "DRB1*15"),
    Box(0.52, 0.50, 0.60, 0.53, "DRB1*11"),
]


def ocr_pass_db(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """Two documents: one tilted (with a ROTATE row waiting for it), one level."""
    ocr_pass = load("ocr_pass")
    db = tmp_path / "ocr_pass.sqlite"
    conn = ocr_pass.connect(db)
    shas = {}
    for name, phi in (("tilted", PHI), ("level", 0.0)):
        boxes = [tilt(b, phi) if phi else b for b in ROW]
        sha = hashlib.sha256(name.encode()).hexdigest()
        shas[name] = sha
        conn.execute(
            "INSERT INTO ocr_result VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                sha,
                ocr_pass.ENGINE_VERSION,
                ocr_pass.PREPROC_VERSION,
                f"photos/{name}.jpg",
                WIDTH,
                HEIGHT,
                len(boxes),
                json.dumps([[b.x0, b.y0, b.x1, b.y1] for b in boxes]),
                json.dumps([b.text for b in boxes]),
                json.dumps([0.9] * len(boxes)),
                1.0,
                None,
                "t",
            ),
        )
    conn.commit()
    conn.close()
    return db, shas


def geometry_db(tmp_path: Path, sha: str) -> Path:
    db = tmp_path / "geometry.sqlite"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE page_geometry (sha256 TEXT, geometry_version TEXT, decision TEXT, "
        "theta_deg REAL)"
    )
    con.execute(
        "INSERT INTO page_geometry VALUES (?,?,?,?)", (sha, GEOMETRY_VERSION, "ROTATE", -PHI)
    )
    con.commit()
    con.close()
    return db


def test_run_levels_the_tilted_page_and_records_the_frame(tmp_path: Path) -> None:
    module = load("extract_facts")
    src, shas = ocr_pass_db(tmp_path)
    out = tmp_path / "facts.sqlite"
    rc = module.run(
        src,
        tmp_path / "no-persian.sqlite",
        tmp_path / "no-families.json",
        out,
        None,
        10,
        None,
        geometry_db(tmp_path, shas["tilted"]),
    )
    assert rc == 0

    con = sqlite3.connect(out)
    documents = {
        row[0]: row for row in con.execute("SELECT sha256, tilt_deg, frame, rel_path FROM document")
    }
    facts = {
        (row[0], row[1]): row
        for row in con.execute("SELECT sha256, field, status, value, value_boxes FROM fact")
    }
    con.close()

    tilted, level = shas["tilted"], shas["level"]
    assert documents[tilted][1] == pytest.approx(-PHI)
    assert documents[tilted][2] == "ROTATE"
    assert documents[tilted][3] == "photos/tilted.jpg"
    assert documents[level][1] == 0.0
    assert documents[level][2] == "identity"

    # The tilted page resolves both alleles only because of the frame, and its
    # provenance is the boxes as stored — the tilted hulls, not levelled ones.
    assert facts[(tilted, "DRB1")][2] == "RESOLVED", facts[(tilted, "DRB1")]
    assert facts[(tilted, "DRB1")][3] == "DRB1*15 DRB1*11"
    stored = [tilt(b, PHI) for b in ROW[1:]]
    assert json.loads(facts[(tilted, "DRB1")][4]) == [[b.x0, b.y0, b.x1, b.y1] for b in stored]
    assert facts[(level, "DRB1")][3] == "DRB1*15 DRB1*11"


def test_run_without_a_geometry_file_says_so_and_keeps_every_page_level(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = load("extract_facts")
    src, shas = ocr_pass_db(tmp_path)
    out = tmp_path / "facts.sqlite"
    assert (
        module.run(src, tmp_path / "none", tmp_path / "none.json", out, None, 10, None, None) == 0
    )
    assert "identity frame" in capsys.readouterr().out
    con = sqlite3.connect(out)
    frames = {row[0] for row in con.execute("SELECT frame FROM document")}
    con.close()
    assert frames == {"identity"}
