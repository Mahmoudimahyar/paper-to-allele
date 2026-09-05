"""The ruled grid in the extraction: a template-placed label, a ruled-row cell.

Synthetic pages only. Three documents on one synthetic form: the DRB1 label
unreadable (placed by the template), the DRB1 label read but its values a full
line above it (bound in the ruled row), and the DRB1 row holding values that
name another locus (refused: geometry and text disagree). A fourth page has no
rulings and stays exactly as the row rule left it.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.task("OCR-001")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from kidneymatch.ocr.anchors import Box  # noqa: E402
from kidneymatch.ocr.rulings import GEOMETRY_VERSION  # noqa: E402

WIDTH, HEIGHT = 1000, 1300


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"km_{name}", ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[f"km_{name}"] = module
    spec.loader.exec_module(module)
    return module


# The form: four locus labels in a column, 4 label heights apart as on the real
# ones, DRB1 first so no row sits above it. Its row is ruled per page below.
LABELS = {"DRB1": 0.30, "A": 0.42, "B": 0.54, "C": 0.66}
FAMILY = {
    "family_id": "FORM#T",
    "label_positions": {locus: [0.14, y] for locus, y in LABELS.items()},
    "prints_locus_on_values": True,
    "n_documents": 100,
}


def label(locus: str, text: str | None = None) -> Box:
    y = LABELS[locus]
    return Box(0.10, y - 0.015, 0.18, y + 0.015, text if text is not None else f"HLA-{locus}")


def values(texts: tuple[str, str], dy: float = 0.0) -> list[Box]:
    y = LABELS["DRB1"] + dy
    return [
        Box(0.22, y - 0.015, 0.30, y + 0.015, texts[0]),
        Box(0.52, y - 0.015, 0.60, y + 0.015, texts[1]),
    ]


PAGES = {
    # the DRB1 label glyphs unreadable, the values in the ruled row
    "unread_label": [
        label("A"),
        label("B"),
        label("C"),
        label("DRB1", "DRE1"),
        *values(("DRB1*15", "DRB1*11")),
    ],
    # the label read, the values 2.2 label heights above it: outside the
    # family rule's 1.9-height centre band, inside the ruled row
    "drifted": [
        label("A"),
        label("B"),
        label("C"),
        label("DRB1"),
        *values(("DRB1*15", "DRB1*11"), dy=-0.065),
    ],
    # the same drift on a page with no form family: the ruled row has no
    # distance cap, so nothing is bound there
    "drifted_default": [label("DRB1"), *values(("DRB1*15", "DRB1*11"), dy=-0.065)],
    # the label unreadable and the row's values naming another locus
    "foreign": [
        label("A"),
        label("B"),
        label("C"),
        label("DRB1", "DRE1"),
        *values(("DQB1*03", "DQB1*05")),
    ],
    # no rulings stored for this page
    "unruled": [
        label("A"),
        label("B"),
        label("C"),
        label("DRB1", "DRE1"),
        *values(("DRB1*15", "DRB1*11")),
    ],
}


def h_segments(top: float, bottom: float) -> list[list[int]]:
    return [
        [50, int(top * HEIGHT), 950, int(top * HEIGHT)],
        [50, int(bottom * HEIGHT), 950, int(bottom * HEIGHT)],
    ]


RULINGS = {
    "unread_label": h_segments(0.270, 0.330),
    "foreign": h_segments(0.270, 0.330),
    "drifted": h_segments(0.220, 0.315),  # 3.2 label heights: one plausible row
    "drifted_default": h_segments(0.220, 0.315),
}
V_SEGMENTS = [[x, int(0.28 * HEIGHT), x, int(0.60 * HEIGHT)] for x in (50, 200, 450, 700, 950)]


def corpus(tmp_path: Path) -> tuple[Path, Path, Path, dict[str, str]]:
    ocr_pass = load("ocr_pass")
    src = tmp_path / "ocr_pass.sqlite"
    conn = ocr_pass.connect(src)
    shas = {}
    for name, boxes in PAGES.items():
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
    geometry = tmp_path / "geometry.sqlite"
    con = sqlite3.connect(geometry)
    con.execute(
        "CREATE TABLE page_geometry (sha256 TEXT, geometry_version TEXT, decision TEXT, "
        "theta_deg REAL, width INTEGER, height INTEGER, h_rulings_json TEXT, v_rulings_json TEXT)"
    )
    for name, sha in shas.items():
        if name not in RULINGS:
            continue
        con.execute(
            "INSERT INTO page_geometry VALUES (?,?,?,?,?,?,?,?)",
            (
                sha,
                GEOMETRY_VERSION,
                "STRAIGHT",
                0.0,
                WIDTH,
                HEIGHT,
                json.dumps(RULINGS[name]),
                json.dumps(V_SEGMENTS),
            ),
        )
    con.commit()
    con.close()
    families = tmp_path / "families.json"
    families.write_text(json.dumps({"families": [FAMILY]}), encoding="utf-8")
    return src, geometry, families, shas


def facts_of(out: Path, sha: str) -> dict[str, tuple]:
    con = sqlite3.connect(out)
    rows = {
        row[0]: row[1:]
        for row in con.execute(
            "SELECT field, status, value, reason, rule_id, anchor_box FROM fact WHERE sha256=?",
            (sha,),
        )
    }
    con.close()
    return rows


def test_the_grid_places_an_unreadable_label_and_recovers_a_drifted_row(tmp_path: Path) -> None:
    module = load("extract_facts")
    src, geometry, families, shas = corpus(tmp_path)
    out = tmp_path / "facts.sqlite"
    assert (
        module.run(src, tmp_path / "no-persian.sqlite", families, out, None, 10, None, geometry)
        == 0
    )

    placed = facts_of(out, shas["unread_label"])["DRB1"]
    assert placed[0] == "RESOLVED" and placed[1] == "DRB1*15 DRB1*11", placed
    assert "placed by the form's template (FORM#T)" in placed[2]
    assert placed[3] == "family/FORM#T+lattice"
    virtual = json.loads(placed[4])
    assert virtual[0] < 0.14 < virtual[2] and virtual[1] < 0.30 < virtual[3], (
        "the anchor is where the template puts the label"
    )

    drifted = facts_of(out, shas["drifted"])["DRB1"]
    assert drifted[0] == "RESOLVED" and drifted[1] == "DRB1*15 DRB1*11", drifted
    assert "bound in the ruled row" in drifted[2]
    assert drifted[3] == "family/FORM#T+lattice"

    # the other loci on the template page were read by the row rule as before
    assert facts_of(out, shas["unread_label"])["A"][3] == "family/FORM#T"


def test_a_row_whose_values_name_another_locus_is_refused_not_placed(tmp_path: Path) -> None:
    """The form prints the locus on every value: a template that put DRB1 on a
    DQB1 row would be caught by the values themselves (gate 2)."""
    module = load("extract_facts")
    src, geometry, families, shas = corpus(tmp_path)
    out = tmp_path / "facts.sqlite"
    module.run(src, tmp_path / "no-persian.sqlite", families, out, None, 10, None, geometry)
    foreign = facts_of(out, shas["foreign"])["DRB1"]
    assert foreign[0] != "RESOLVED"
    assert foreign[3] == "family/FORM#T", "nothing was bound, so no +lattice"


def test_without_rulings_the_page_is_exactly_the_row_rule_s(tmp_path: Path) -> None:
    module = load("extract_facts")
    src, geometry, families, shas = corpus(tmp_path)
    out = tmp_path / "facts.sqlite"
    module.run(src, tmp_path / "no-persian.sqlite", families, out, None, 10, None, geometry)
    unruled = facts_of(out, shas["unruled"])["DRB1"]
    assert unruled[0] == "UNKNOWN" and unruled[2] == "no anchor on this document"
    assert unruled[3] == "family/FORM#T"


def test_the_ruled_row_binds_nothing_on_a_form_that_does_not_print_the_locus(
    tmp_path: Path,
) -> None:
    """The row has no distance cap and no overlap test: on a form nobody has
    measured to print the locus on its values, a number anywhere in the band
    would bind. The value's own prefix is what corroborates the row."""
    module = load("extract_facts")
    src, geometry, families, shas = corpus(tmp_path)
    out = tmp_path / "facts.sqlite"
    module.run(src, tmp_path / "no-persian.sqlite", families, out, None, 10, None, geometry)
    row = facts_of(out, shas["drifted_default"])["DRB1"]
    assert row[0] == "REVIEW_REQUIRED"
    assert row[3] == "ADR0008/default-row-rule", "no +lattice"
