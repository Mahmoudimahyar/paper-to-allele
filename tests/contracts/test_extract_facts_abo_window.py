"""The blood-group cell window, end to end: the grid, the rule id, the stratum.

Synthetic pages only — a printed field label, one value box, and the rulings a
form draws around a row. Three pages: a ruled page whose value misses the
label's line, an unruled page with the same geometry, and a page whose value is
on the line and must be untouched.

What is under test is the WIRING, which is where this rule can go wrong without
any test noticing: `read_abo` must be handed the RAW-frame grid, the route the
value took must reach the fact row's `rule_id`, and an uncorroborated ruled-row
reading must arrive at the reviewer as a review item CARRYING THE CANDIDATE BOX
rather than as a value or as a bare refusal.
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
LABEL = Box(0.10, 0.30, 0.22, 0.32, "Blood Group:")
# 0.67 label heights above the label's centre: the two boxes share a third of
# their height, which the line test refuses and the printed row does not.
OFF_LINE = Box(0.26, 0.2866, 0.31, 0.3066, "A+")
ON_LINE = Box(0.26, 0.30, 0.31, 0.32, "A+")
PAGES = {
    "ruled_off_line": [LABEL, OFF_LINE],
    "unruled_off_line": [LABEL, OFF_LINE],
    "ruled_on_line": [LABEL, ON_LINE],
}
# A row 1.5 label heights tall around the label, holding both boxes.
RULINGS = {
    "ruled_off_line": [
        [50, int(0.29 * HEIGHT), 950, int(0.29 * HEIGHT)],
        [50, int(0.32 * HEIGHT), 950, int(0.32 * HEIGHT)],
    ],
}
RULINGS["ruled_on_line"] = RULINGS["ruled_off_line"]


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"km_{name}", ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[f"km_{name}"] = module
    spec.loader.exec_module(module)
    return module


def corpus(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
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
        if name in RULINGS:
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
                    json.dumps([]),
                ),
            )
    con.commit()
    con.close()
    return src, geometry, shas


def abo_of(out: Path, sha: str) -> tuple:
    con = sqlite3.connect(out)
    row = con.execute(
        "SELECT status, value, reason, rule_id, anchor_box, value_boxes FROM fact "
        "WHERE sha256=? AND field='ABO'",
        (sha,),
    ).fetchone()
    con.close()
    return row


@pytest.fixture(scope="module")
def extracted(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, str]]:
    tmp_path = tmp_path_factory.mktemp("abo_window")
    module = load("extract_facts")
    src, geometry, shas = corpus(tmp_path)
    families = tmp_path / "families.json"
    families.write_text(json.dumps({"families": []}), encoding="utf-8")
    out = tmp_path / "facts.sqlite"
    assert (
        module.run(src, tmp_path / "no-persian.sqlite", families, out, None, 10, None, geometry)
        == 0
    )
    return out, shas


def test_an_uncorroborated_ruled_row_value_reaches_the_reviewer_with_its_box(extracted) -> None:
    """One engine, no caption. The value is NOT published, and the review item
    carries the candidate box so the reviewer's crop lands on the value rather
    than on an empty cell."""
    out, shas = extracted
    status, value, reason, rule_id, anchor, value_boxes = abo_of(out, shas["ruled_off_line"])
    assert status == "REVIEW_REQUIRED"
    assert value is None
    assert "nothing corroborates it" in reason
    assert rule_id == "abo/anchored-cell+band"
    assert json.loads(anchor) == [LABEL.x0, LABEL.y0, LABEL.x1, LABEL.y1]
    assert json.loads(value_boxes) == [[OFF_LINE.x0, OFF_LINE.y0, OFF_LINE.x1, OFF_LINE.y1]]


def test_the_same_page_without_rulings_falls_to_the_centre_band(extracted) -> None:
    """No grid, so no cell is geometrically defined; the value is published on
    distance and direction alone, and the rule id says so."""
    out, shas = extracted
    status, value, _reason, rule_id, _anchor, value_boxes = abo_of(out, shas["unruled_off_line"])
    assert (status, value) == ("RESOLVED", "A")
    assert rule_id == "abo/anchored-cell+centre"
    assert json.loads(value_boxes) == [[OFF_LINE.x0, OFF_LINE.y0, OFF_LINE.x1, OFF_LINE.y1]]


def test_a_value_on_its_labels_line_is_read_exactly_as_before(extracted) -> None:
    out, shas = extracted
    status, value, _reason, rule_id, _anchor, _boxes = abo_of(out, shas["ruled_on_line"])
    assert (status, value) == ("RESOLVED", "A")
    assert rule_id == "abo/anchored-cell"


def test_every_rescued_reading_has_a_review_stratum() -> None:
    """A pass that asserts a value no person has checked must be samplable, and
    a document is pooled by its FIRST matching tag — so the stratum has to sit
    above the ones a rescued page would otherwise fall into."""
    review_pack = load("review_pack")
    names = [name for name, _, _ in review_pack.STRATA]
    assert "abo_band_rescue" in names
    assert names.index("abo_band_rescue") < names.index("abo_unreadable")

    def doc(rule_id: str) -> object:
        d = review_pack.Doc("a" * 64, "photos/x.jpg", "MID", None, False, None, None)
        d.abo = {"status": "RESOLVED", "value": "A", "source": "LABORATORY_PRINTED", "reason": ""}
        d.abo["rule_id"] = rule_id
        return d

    assert "abo_band_rescue" in review_pack.tag_document(doc("abo/anchored-cell+band"), Path("."))
    assert "abo_band_rescue" in review_pack.tag_document(doc("abo/anchored-cell+centre"), Path("."))
    assert "abo_band_rescue" not in review_pack.tag_document(doc("abo/anchored-cell"), Path("."))
