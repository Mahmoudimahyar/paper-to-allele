"""The empty-cell pass measures and records; it writes no fact.

`NOT_TESTED` is HA-009's per-(family, locus) status, decided by a person from a
committed statistic. A per-page ink measurement is evidence for that decision,
not the decision. Synthetic pages and databases only.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

pytestmark = pytest.mark.task("BOOT-001")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
SCRIPT = ROOT / "scripts/cell_ink_pass.py"

from kidneymatch.ocr.rulings import GEOMETRY_VERSION  # noqa: E402


def load():
    spec = importlib.util.spec_from_file_location("km_cell_ink_pass", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["km_cell_ink_pass"] = module
    spec.loader.exec_module(module)
    return module


# 800x600: the C row ruled at y=230..290 with the label at x=100..200 and the
# value cell running to x=720; the DQA1 row below it at y=290..350.
ANCHOR_C = [100 / 800, 240 / 600, 200 / 800, 280 / 600]
ANCHOR_DQA1 = [100 / 800, 300 / 600, 200 / 800, 340 / 600]
EMPTY = "anchor found but no box at all in its cell under this rule"


def page(dqa1_text: str | None, *, faint_labels: bool = False) -> Image.Image:
    image = Image.new("L", (800, 600), 245)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=18)
    for y in (230, 290, 350):
        draw.line([(80, y), (720, y)], fill=0, width=2)
    for x in (80, 220, 720):
        draw.line([(x, 230), (x, 350)], fill=0, width=2)
    ink = 200 if faint_labels else 0  # a faint label: beyond the measure
    draw.text((105, 250), "HLA-C", fill=ink, font=font)
    draw.text((105, 310), "HLA-DQA1", fill=ink, font=font)
    if dqa1_text:
        draw.text((300, 310), dqa1_text, fill=0, font=font)
    return image


def corpus(tmp_path: Path) -> tuple[Path, Path, Path]:
    export = tmp_path / "export"
    export.mkdir()
    page("DQA1*01").save(export / "inked.png")
    page(None).save(export / "unruled.png")
    page(None, faint_labels=True).save(export / "faint.png")
    db = tmp_path / "facts.sqlite"
    con = sqlite3.connect(db)
    con.executescript(
        """
        CREATE TABLE document (sha256, extraction_version, rel_path, frame, tilt_deg);
        CREATE TABLE fact (sha256, field, extraction_version, status, value, reason, rule_id,
            anchor_box, value_boxes, source);
        """
    )
    for sha in ("inked", "unruled", "faint"):
        con.execute(
            "INSERT INTO document VALUES (?, 'facts/v1', ?, 'identity', 0.0)", (sha, f"{sha}.png")
        )
        for field, anchor in (("C", ANCHOR_C), ("DQA1", ANCHOR_DQA1)):
            con.execute(
                "INSERT INTO fact VALUES (?, ?, 'facts/v1', 'REVIEW_REQUIRED', NULL, ?, "
                "'ADR0008/default-row-rule', ?, NULL, NULL)",
                (sha, field, EMPTY, json.dumps(anchor)),
            )
    con.commit()
    con.close()
    geometry = tmp_path / "geometry.sqlite"
    con = sqlite3.connect(geometry)
    con.execute(
        "CREATE TABLE page_geometry (sha256 TEXT, geometry_version TEXT, decision TEXT, "
        "theta_deg REAL, width INTEGER, height INTEGER, h_rulings_json TEXT, v_rulings_json TEXT)"
    )
    for sha in ("inked", "faint"):
        con.execute(
            "INSERT INTO page_geometry VALUES (?,?,?,?,?,?,?,?)",
            (
                sha,
                GEOMETRY_VERSION,
                "STRAIGHT",
                0.0,
                800,
                600,
                json.dumps([[80, y, 720, y] for y in (230, 290, 350)]),
                json.dumps([[x, 230, x, 350] for x in (80, 220, 720)]),
            ),
        )
    con.commit()
    con.close()
    return db, export, geometry


def facts(db: Path) -> dict[tuple[str, str], tuple]:
    con = sqlite3.connect(db)
    return {
        (sha, field): (status, source, reason, boxes)
        for sha, field, status, source, reason, boxes in con.execute(
            "SELECT sha256, field, status, source, reason, value_boxes FROM fact"
        )
    }


def test_the_measurement_is_recorded_and_no_fact_is_touched(tmp_path: Path) -> None:
    module = load()
    db, export, geometry = corpus(tmp_path)
    before = sqlite3.connect(db).execute("SELECT * FROM fact ORDER BY 1, 2").fetchall()
    tally = module.run(db, export, geometry)
    assert tally["BLANK"] == 1 and tally["INKED"] == 1
    assert tally["UNMEASURABLE"] == 2, "the faint page's labels are beyond the measure"
    assert tally["no rulings for the page"] == 2, "the unruled page's two cells"

    # every fact is exactly as the row rules left it
    assert sqlite3.connect(db).execute("SELECT * FROM fact ORDER BY 1, 2").fetchall() == before
    rows = facts(db)
    for key in rows:
        assert rows[key] == ("REVIEW_REQUIRED", None, EMPTY, None), key

    con = sqlite3.connect(db)
    measured = {
        (sha, field): (decision, region)
        for sha, field, decision, region in con.execute(
            "SELECT sha256, field, decision, region FROM cell_ink"
        )
    }
    assert measured[("inked", "C")][0] == "BLANK"
    assert measured[("inked", "DQA1")][0] == "INKED"
    assert measured[("faint", "C")][0] == "UNMEASURABLE"
    region = json.loads(measured[("inked", "C")][1])
    assert region[0] > ANCHOR_C[2], "the cell starts right of the label"
    assert region[2] == pytest.approx(720 / 800)
    assert region[1] == pytest.approx(230 / 600) and region[3] == pytest.approx(290 / 600)


def test_the_pass_is_idempotent_and_dry_run_records_nothing(tmp_path: Path) -> None:
    module = load()
    db, export, geometry = corpus(tmp_path)
    assert module.run(db, export, geometry, dry_run=True)["BLANK"] == 1
    con = sqlite3.connect(db)
    con.execute(module.SCHEMA)
    assert con.execute("SELECT COUNT(*) FROM cell_ink").fetchone()[0] == 0
    con.close()
    module.run(db, export, geometry)
    after = sqlite3.connect(db).execute("SELECT * FROM cell_ink ORDER BY 1, 2").fetchall()
    again = module.run(db, export, geometry)
    assert again["cells examined"] == 6, "the cells are still the row rules' review items"
    assert sqlite3.connect(db).execute("SELECT * FROM cell_ink ORDER BY 1, 2").fetchall() == after


def test_the_pass_writes_no_fact_at_all() -> None:
    """The authority to retire a review item belongs to HA-009 and a person."""
    body = SCRIPT.read_text(encoding="utf-8")
    assert "UPDATE fact" not in body
    assert "NOT_TESTED" not in body.split('"""', 2)[2], "not outside the docstring"


def test_a_measurement_this_run_cannot_make_is_withdrawn(tmp_path: Path) -> None:
    """Yesterday's answer for a cell the rulings no longer place would read as
    today's; the table says what the current run measured, or nothing."""
    module = load()
    db, export, geometry = corpus(tmp_path)
    module.run(db, export, geometry)
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM cell_ink").fetchone()[0] == 4
    con.close()
    empty = tmp_path / "no-geometry.sqlite"
    module.run(db, export, empty)
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM cell_ink").fetchone()[0] == 0
