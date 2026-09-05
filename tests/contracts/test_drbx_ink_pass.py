"""The ink pass: a blank second slot certifies ABSENT; an inked one asks a person.

Synthetic pages and a synthetic facts database only.
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
SCRIPT = ROOT / "scripts/drbx_ink_pass.py"


def load():
    spec = importlib.util.spec_from_file_location("km_drbx_ink_pass", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["km_drbx_ink_pass"] = module
    spec.loader.exec_module(module)
    return module


# The synthetic form: 800x600, the DRB1 row at y=200 with two value boxes, the
# grouped row at y=260 with a token in the first column; the second column
# blank, inked, or shadowed per document.
DRB1_BOXES = [[0.30, 0.32, 0.40, 0.36], [0.60, 0.32, 0.70, 0.36]]
GENE_BOX = [[0.31, 0.42, 0.39, 0.46]]
ONE_TOKEN = "only one gene token read; the second column is unread or empty"


def page(second: str) -> Image.Image:
    image = Image.new("L", (800, 600), 245)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=18)
    for y in (180, 230, 290):
        draw.line([(80, y), (720, y)], fill=0, width=2)
    for x in (80, 220, 440, 720):
        draw.line([(x, 180), (x, 290)], fill=0, width=2)
    draw.text((100, 195), "HLA-DRB1", fill=0, font=font)
    draw.text((245, 195), "DRB1*11", fill=0, font=font)
    draw.text((485, 195), "DRB1*15", fill=0, font=font)
    draw.text((100, 250), "HLA-DRB3/4/5", fill=0, font=font)
    draw.text((250, 250), "DRB3", fill=0, font=font)
    if second == "inked":
        draw.text((490, 250), "DRB4", fill=0, font=font)
    elif second == "shadow":
        draw.rectangle([(440, 232), (720, 288)], fill=60)
    return image


def corpus(tmp_path: Path, module) -> tuple[Path, Path]:  # type: ignore[no-untyped-def]
    export = tmp_path / "export"
    export.mkdir()
    db = tmp_path / "facts.sqlite"
    con = sqlite3.connect(db)
    con.executescript(
        """
        CREATE TABLE document (sha256, extraction_version, rel_path, frame, tilt_deg);
        CREATE TABLE fact (sha256, field, extraction_version, status, value, reason, rule_id,
            value_boxes, source);
        """
    )
    for sha, second in (
        ("blank", "blank"),
        ("inked", "inked"),
        ("shadow", "shadow"),
        ("nodrb1", "blank"),
    ):
        page(second).save(export / f"{sha}.png")
        con.execute(
            "INSERT INTO document VALUES (?, 'facts/v1', ?, 'identity', 0.0)", (sha, f"{sha}.png")
        )
        if sha != "nodrb1":
            con.execute(
                "INSERT INTO fact VALUES (?, 'DRB1', 'facts/v1', 'RESOLVED', "
                "'DRB1*11 DRB1*15', '', "
                "'family/FORM#1', ?, NULL)",
                (sha, json.dumps(DRB1_BOXES)),
            )
        con.execute(
            "INSERT INTO fact VALUES (?, 'DRB3', 'facts/v1', 'RESOLVED', 'PRESENT', '', "
            "'GROUPED_DRBX/v1', ?, NULL)",
            (sha, json.dumps(GENE_BOX)),
        )
        for gene in ("DRB4", "DRB5"):
            con.execute(
                "INSERT INTO fact VALUES (?, ?, 'facts/v1', 'UNKNOWN', NULL, ?, 'GROUPED_DRBX/v1', "
                "NULL, NULL)",
                (sha, gene, ONE_TOKEN),
            )
    con.commit()
    con.close()
    return db, export


def facts(db: Path) -> dict[tuple[str, str], tuple]:
    con = sqlite3.connect(db)
    return {
        (sha, field): (status, value, source, reason, boxes)
        for sha, field, status, value, source, reason, boxes in con.execute(
            "SELECT sha256, field, status, value, source, reason, value_boxes FROM fact "
            "WHERE field IN ('DRB4','DRB5')"
        )
    }


def test_a_blank_slot_certifies_absence_with_the_region_as_provenance(tmp_path: Path) -> None:
    module = load()
    db, export = corpus(tmp_path, module)
    tally = module.run(db, export)
    assert tally["BLANK"] == 1 and tally["INKED"] == 1 and tally["UNMEASURABLE"] == 1
    assert tally["rows examined"] == 3, "the page without DRB1 geometry is never examined"
    rows = facts(db)
    for gene in ("DRB4", "DRB5"):
        status, value, source, reason, boxes = rows[("blank", gene)]
        assert (status, value, source) == ("RESOLVED", "ABSENT", module.SOURCE)
        assert "paper" in reason
        region = json.loads(boxes)[0]
        assert region[0] < 0.60 < 0.70 < region[2], "the second DRB1 column, widened"
    con = sqlite3.connect(db)
    ink = con.execute(
        "SELECT column_index, decision, fraction FROM drbx_ink WHERE sha256='blank'"
    ).fetchone()
    assert ink[0] == 1 and ink[1] == "BLANK" and ink[2] < module.BLANK_FRACTION


def test_an_inked_slot_no_engine_read_goes_to_review_never_to_a_gene(tmp_path: Path) -> None:
    module = load()
    db, export = corpus(tmp_path, module)
    module.run(db, export)
    rows = facts(db)
    for gene in ("DRB4", "DRB5"):
        status, value, source, reason, _ = rows[("inked", gene)]
        assert status == "REVIEW_REQUIRED" and value is None and source is None
        assert "no engine read" in reason


def test_a_shadowed_slot_and_a_page_without_geometry_are_left_alone(tmp_path: Path) -> None:
    module = load()
    db, export = corpus(tmp_path, module)
    module.run(db, export)
    rows = facts(db)
    for sha in ("shadow", "nodrb1"):
        for gene in ("DRB4", "DRB5"):
            status, value, source, reason, _ = rows[(sha, gene)]
            assert (status, value, source) == ("UNKNOWN", None, None), (sha, gene)
            assert reason == ONE_TOKEN


def test_the_pass_is_idempotent_and_dry_run_changes_nothing(tmp_path: Path) -> None:
    module = load()
    db, export = corpus(tmp_path, module)
    before = sqlite3.connect(db).execute("SELECT * FROM fact ORDER BY 1, 2").fetchall()
    dry = module.run(db, export, dry_run=True)
    assert dry["BLANK"] == 1
    assert sqlite3.connect(db).execute("SELECT * FROM fact ORDER BY 1, 2").fetchall() == before
    module.run(db, export)
    after = sqlite3.connect(db).execute("SELECT * FROM fact ORDER BY 1, 2").fetchall()
    again = module.run(db, export)
    assert again["rows examined"] == 1, "decided rows are no longer one-token UNKNOWN rows"
    assert sqlite3.connect(db).execute("SELECT * FROM fact ORDER BY 1, 2").fetchall() == after


def test_the_pass_never_writes_a_present_gene() -> None:
    """Ink says paper or not-paper. Which gene an inked slot holds is read by a
    recognizer or a person, never inferred here."""
    body = SCRIPT.read_text(encoding="utf-8")
    assert "'PRESENT'" not in body.split("def run(")[1]
