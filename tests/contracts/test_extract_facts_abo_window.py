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


@pytest.fixture(scope="module")
def extracted_with_captions(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, dict[str, str]]:
    """The same corpus, extracted with the messages the photographs were posted with.

    This is the half of F1 that was dead code: `reconcile_abo` publishes a
    ruled-row value boxed by ONE engine when a caption names the same letter,
    and no production caller passed it a caption, so the branch never fired and
    every single-box band reading went to review.
    """
    tmp_path = tmp_path_factory.mktemp("abo_window_captions")
    module = load("extract_facts")
    src, geometry, shas = corpus(tmp_path)
    families = tmp_path / "families.json"
    families.write_text(json.dumps({"families": []}), encoding="utf-8")
    source = tmp_path / "source.sqlite"
    con = sqlite3.connect(source)
    con.execute(
        "CREATE TABLE source_message (export_id TEXT, telegram_message_id INTEGER, raw_text TEXT)"
    )
    con.execute(
        "CREATE TABLE document_message (sha256 TEXT, export_id TEXT, "
        "telegram_message_id INTEGER, bundle_id TEXT)"
    )
    con.execute("INSERT INTO source_message VALUES ('e', 1, 'blood group A+')")
    con.execute("INSERT INTO document_message VALUES (?, 'e', 1, NULL)", (shas["ruled_off_line"],))
    con.commit()
    con.close()
    out = tmp_path / "facts.sqlite"
    assert (
        module.run(src, tmp_path / "no-persian.sqlite", families, out, None, 10, source, geometry)
        == 0
    )
    return out, shas


def test_a_caption_naming_the_same_letter_publishes_the_ruled_row_value(
    extracted_with_captions,
) -> None:
    """F1(b), end to end. The value is published as a FORM reading — the route
    in its rule id, the anchor and the candidate box in its provenance — not as
    the poster's claim, because the form is where it was read."""
    out, shas = extracted_with_captions
    status, value, reason, rule_id, anchor, value_boxes = abo_of(out, shas["ruled_off_line"])
    assert (status, value) == ("RESOLVED", "A")
    assert rule_id == "abo/anchored-cell+band"
    assert "own ruled row" in reason
    # F3: the reason says how tall the row was and how many engines saw it.
    assert "anchor heights tall" in reason
    assert "1 engine boxed the value" in reason
    assert json.loads(anchor) == [LABEL.x0, LABEL.y0, LABEL.x1, LABEL.y1]
    assert json.loads(value_boxes) == [[OFF_LINE.x0, OFF_LINE.y0, OFF_LINE.x1, OFF_LINE.y1]]
    con = sqlite3.connect(out)
    source = con.execute(
        "SELECT source FROM fact WHERE sha256=? AND field='ABO'", (shas["ruled_off_line"],)
    ).fetchone()[0]
    con.close()
    assert source != "CAPTION_CLAIM"


def test_the_caption_is_withheld_from_every_reading_that_does_not_need_it(
    extracted_with_captions,
) -> None:
    """The caption corroborates a ruled-row candidate and does nothing else.

    Handing `reconcile_abo` a caption on every page would let it resolve cells
    the form cannot read and raise conflicts `caption_pass.py` records instead
    — a much larger change than F1 asked for, on 8,057 documents.
    """
    module = load("extract_facts")
    source = (ROOT / "scripts" / "extract_facts.py").read_text(encoding="utf-8")
    assert "if caption_abo is not None and needs_corroboration(abo_reading)" in source
    assert module.load_caption_abo(None) == {}
    assert module.load_caption_abo(Path("no-such-source.sqlite")) == {}


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


def _stratum_doc(review_pack, rule_id: str) -> object:
    d = review_pack.Doc("a" * 64, "photos/x.jpg", "MID", None, False, None, None)
    d.abo = {
        "status": "RESOLVED",
        "value": "A",
        "source": "LABORATORY_PRINTED",
        "reason": "",
        "rule_id": rule_id,
    }
    return d


def test_every_rescued_reading_has_a_review_stratum() -> None:
    """A pass that asserts a value no person has checked must be samplable, and
    a document is pooled by its FIRST matching tag — so the stratum has to sit
    above the ones a rescued page would otherwise fall into.

    The two ROUTES are separate strata. Pooled under one tag the centre route
    drew about two documents into a 150-document pack while HA-019 asks for
    twenty before it may be promoted, and a quota cannot be aimed at half a
    pool.
    """
    review_pack = load("review_pack")
    names = [name for name, _, _ in review_pack.STRATA]
    for tag in ("abo_band_rescue", "abo_centre_rescue"):
        assert tag in names
        assert names.index(tag) < names.index("abo_unreadable")

    tag_of = review_pack.tag_document
    assert "abo_band_rescue" in tag_of(_stratum_doc(review_pack, "abo/anchored-cell+band"), Path())
    assert "abo_centre_rescue" in tag_of(
        _stratum_doc(review_pack, "abo/anchored-cell+centre"), Path()
    )
    # Neither route claims the other's documents, and an ordinary anchored read
    # is in no rescue stratum at all.
    assert "abo_centre_rescue" not in tag_of(
        _stratum_doc(review_pack, "abo/anchored-cell+band"), Path()
    )
    assert "abo_band_rescue" not in tag_of(
        _stratum_doc(review_pack, "abo/anchored-cell+centre"), Path()
    )
    plain = tag_of(_stratum_doc(review_pack, "abo/anchored-cell"), Path())
    assert "abo_band_rescue" not in plain
    assert "abo_centre_rescue" not in plain


def test_the_centre_quota_can_actually_reach_twenty_documents() -> None:
    """HA-019 blocks promotion until >= 20 centre-route documents are read.

    A quota that cannot deliver that at the DEFAULT pack size is a plan nobody
    executes, so the arithmetic `choose` performs is asserted here: one
    document per stratum first, then `round(room * weight / total) - 1` more.
    Measured on the live store at `--n 150`, this draws 21.
    """
    review_pack = load("review_pack")
    weights = {name: weight for name, weight, _ in review_pack.STRATA}
    total = sum(weights.values())
    n = 150
    room = n - len(review_pack.STRATA)
    drawn = 1 + max(0, round(room * weights["abo_centre_rescue"] / total) - 1)
    assert drawn >= 20, f"a default pack would draw {drawn} centre-route documents, not 20"


def test_the_uncorroborated_band_candidate_is_scored_by_no_pass_as_a_value(extracted) -> None:
    """The RH row of an unpublished band candidate must not carry a value.

    `reconcile_abo` returning REVIEW_REQUIRED means there is no group; a sign
    written beside it would be an Rh nothing read.
    """
    out, shas = extracted
    con = sqlite3.connect(out)
    status, value = con.execute(
        "SELECT status, value FROM fact WHERE sha256=? AND field='RH'",
        (shas["ruled_off_line"],),
    ).fetchone()
    con.close()
    assert status == "UNKNOWN"
    assert value == "UNKNOWN"


def test_the_repass_that_collapses_a_doubled_cell_writes_the_route(tmp_path: Path) -> None:
    """`abo_repass` publishes rescued readings too, and a published rescue with
    no marker is outside the withdrawal handle and outside the review stratum.

    Measured on the live store before this was fixed: 42 rows written from a
    rescued reading kept `rule_id='abo/anchored-cell'`, 4 of them documents
    only the rescue resolves.
    """
    abo_repass = load("abo_repass")
    from kidneymatch.documents.abo import AboReading, AboRescue, AboStatus, rule_id_for

    band = AboReading(AboStatus.RESOLVED, group="A", rescued=AboRescue.BAND)
    assert rule_id_for(band) == "abo/anchored-cell+band"
    assert rule_id_for(AboReading(AboStatus.RESOLVED, group="A")) == "abo/anchored-cell"
    # The pass writes what `rule_id_for` returns, in the same UPDATE as the
    # value, and the recognizer the boxes came from beside it: a row that says
    # the form printed the value must not keep the caption reader's version.
    source = (ROOT / "scripts" / "abo_repass.py").read_text(encoding="utf-8")
    assert "rule_id = rule_id_for(reading)" in source
    assert "engine_version=?, repaired=?, rule_id=?, anchor_box=?" in source
    assert "engines.get(sha)" in source
    assert abo_repass.EV == "facts/v1"


def test_the_acceptance_harness_gates_reach_not_only_leak() -> None:
    """Centre fix 9 gates "more than +2 admissions" — every extra admission.

    The harness gated only admissions of a DIFFERENT value, which is a weaker
    question than the one that was asked, and it passed shifts its own numbers
    fail. It must also run the two placebos that were pinned and never built:
    +-3.0h, and reading the cell on the wrong side of its label.
    """
    check = load("abo_window_check")
    assert set(check.TRANSLATIONS) >= {1.0, 1.5, 2.0, 3.0}
    source = (ROOT / "scripts" / "abo_window_check.py").read_text(encoding="utf-8")
    assert "if delta > PLACEBO_ALLOWANCE:" in source
    assert "REACH OVER THE ALLOWANCE" in source
    assert 'choices=("translated", "decoy", "direction")' in source
    assert hasattr(check, "Reversed")
