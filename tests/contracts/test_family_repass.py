"""Applying the three no-family findings to a database, without re-extracting.

Written before the script. A full re-extraction resets every later pass, which
`docs/agent-memory/CURRENT.md` records as the commonest way this pipeline
loses cells, so the findings are applied to the pages they change and to
nothing else. What this test pins is what the pass must NOT do:

* never touch a RESOLVED cell;
* never touch a cell a later pass wrote (`source` is not null);
* never write anything at all under `--dry-run`, which is the default;
* write a distinct `source` per finding, so each group can be found,
  reviewed and withdrawn on its own evidence;
* carry the boxes, so the review page can crop what a person is being asked
  to check.

Synthetic geometry, fabricated allele values.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import sqlite3
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.task("OCR-001")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from kidneymatch.ocr.anchors import Box  # noqa: E402
from kidneymatch.ocr.geometry import PageFrame  # noqa: E402
from kidneymatch.ocr.rulings import GEOMETRY_VERSION  # noqa: E402

WIDTH, HEIGHT = 1000, 1300
ROW_ORDER = ("A", "B", "C", "DQB1", "DRB1", "DPB1", "DPA1", "DQA1")
PITCH = 0.06
LOCI = ("A", "B", "C", "DRB1", "DQA1", "DQB1", "DPA1", "DPB1")


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"km_{name}", ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[f"km_{name}"] = module
    spec.loader.exec_module(module)
    return module


def stack(lean: float = 0.0) -> list[Box]:
    return [
        Box(0.15 + lean * i, 0.20 + i * PITCH, 0.25 + lean * i, 0.225 + i * PITCH, f"HLA-{locus}")
        for i, locus in enumerate(ROW_ORDER)
    ]


FAMILIES = {
    "families": [
        {
            "family_id": name,
            "label_positions": {
                locus: [0.20 + lean * i, 0.2125 + i * PITCH] for i, locus in enumerate(ROW_ORDER)
            },
            "prints_locus_on_values": True,
            "n_documents": 100,
        }
        for name, lean in (("FORM#0", 0.0), ("FORM#1", 0.002))
    ]
}

# A page leaning between the two prototypes: the tie the clause now assigns.
TIE_PAGE = [
    *stack(lean=0.001),
    Box(0.40, 0.20, 0.50, 0.225, "A*01"),
    Box(0.60, 0.20, 0.70, 0.225, "A*02"),
    Box(0.40, 0.26, 0.50, 0.285, "B*07"),
]
# A page whose labels are column headers, each value beneath its own.
COLUMN_PAGE = [
    box
    for index, locus in enumerate(("A", "B", "C"))
    for box in (
        Box(0.15 + index * 0.25, 0.20, 0.27 + index * 0.25, 0.225, f"HLA-{locus}"),
        Box(0.15 + index * 0.25, 0.28, 0.27 + index * 0.25, 0.305, f"{locus}*01,*02"),
    )
]

# A page photographed at a tilt whose stack fits only once a label's boxed-apart
# `HLA-` is put back. Its STORED boxes are what a camera leaning by `TILT_DEG`
# would have recorded, so `PageFrame.rectify` lands the levelled page exactly on
# the straight stack the other fixtures use and the fit is the identity case's.
# What is left to test is then entirely the FRAME the provenance is written in.
TILT_DEG = 2.0


def photographed(box: Box, theta: float = TILT_DEG) -> Box:
    """The box a camera tilted by `theta` stores for this printed one.

    The inverse of `PageFrame.rectify_box`: the centre rotates the other way,
    and the size grows into the axis-aligned hull a detector draws around a
    rotated rectangle.
    """
    inverse = PageFrame(-theta, WIDTH, HEIGHT)
    cx, cy = inverse.rotate_pixel(box.centre_x * WIDTH, box.centre_y * HEIGHT)
    width, height = (box.x1 - box.x0) * WIDTH, (box.y1 - box.y0) * HEIGHT
    phi = abs(math.radians(theta))
    cos, sin = math.cos(phi), math.sin(phi)
    hull_w, hull_h = width * cos + height * sin, width * sin + height * cos
    return Box(
        (cx - hull_w / 2) / WIDTH,
        (cy - hull_h / 2) / HEIGHT,
        (cx + hull_w / 2) / WIDTH,
        (cy + hull_h / 2) / HEIGHT,
        box.text,
    )


PREFIX_Y = 0.20 + ROW_ORDER.index("DQB1") * PITCH
# The two halves of the one printed word `HLA-DQB1`, as the recognizer boxed
# them, on the LEVEL page. `PREFIX_PAGE` stores their photographed selves.
PREFIX_FRAGMENT_LEVEL = Box(0.15, PREFIX_Y, 0.19, PREFIX_Y + 0.025, "HLA-")
PREFIX_LABEL_LEVEL = Box(0.194, PREFIX_Y, 0.25, PREFIX_Y + 0.025, "DQB1")
PREFIX_PAGE = [
    photographed(box)
    for box in (
        *(
            Box(0.15, 0.20 + i * PITCH, 0.25, 0.225 + i * PITCH, f"HLA-{locus}")
            for i, locus in enumerate(ROW_ORDER)
            if locus != "DQB1"
        ),
        PREFIX_FRAGMENT_LEVEL,
        PREFIX_LABEL_LEVEL,
        Box(0.40, PREFIX_Y, 0.50, PREFIX_Y + 0.025, "DQB1*03"),
        Box(0.60, PREFIX_Y, 0.70, PREFIX_Y + 0.025, "DQB1*05"),
    )
]

PAGES = {"tie": TIE_PAGE, "column": COLUMN_PAGE, "prefix": PREFIX_PAGE}


def tilted_geometry(tmp_path: Path, shas: dict[str, str]) -> Path:
    """A geometry store declaring the prefix page ROTATE, and nothing else."""
    path = tmp_path / "geometry.sqlite"
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE page_geometry (sha256 TEXT, geometry_version TEXT, rel_path TEXT, "
        "width INTEGER, height INTEGER, decision TEXT, theta_deg REAL, "
        "h_rulings_json TEXT, v_rulings_json TEXT)"
    )
    con.execute(
        "INSERT INTO page_geometry VALUES (?,?,?,?,?,?,?,?,?)",
        (
            shas["prefix"],
            GEOMETRY_VERSION,
            "photos/prefix.jpg",
            WIDTH,
            HEIGHT,
            "ROTATE",
            TILT_DEG,
            None,
            None,
        ),
    )
    con.commit()
    con.close()
    return path


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
    families = tmp_path / "families.json"
    families.write_text(json.dumps(FAMILIES), encoding="utf-8")
    return src, families, tmp_path / "missing.sqlite", shas


SHEET_SHA = "f" * 64


def facts_db(tmp_path: Path, shas: dict[str, str]) -> Path:
    """A facts database in the state the corpus is in today: no family, and
    every HLA cell refused or unknown — plus two cells that must not move."""
    extract_facts = load("extract_facts")
    path = tmp_path / "facts.sqlite"
    con = extract_facts.connect(path)
    # A page the extraction marked as printing two people. The corpus has 450;
    # the guard refuses to run at all against a database holding none, so the
    # fixture holds one the way the real store does.
    con.execute(
        "INSERT INTO document (sha256, extraction_version, rel_path, quality_band, family, "
        "comparison_sheet, consistency, consistency_reason, n_facts, created_utc) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (SHEET_SHA, "facts/v1", "photos/sheet.jpg", "HIGH", None, 1, "NOT_CHECKABLE", "", 0, "t"),
    )
    for name, sha in shas.items():
        con.execute(
            "INSERT INTO document (sha256, extraction_version, rel_path, quality_band, family, "
            "comparison_sheet, consistency, consistency_reason, n_facts, created_utc) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (sha, "facts/v1", f"photos/{name}.jpg", "HIGH", None, 0, "NOT_CHECKABLE", "", 0, "t"),
        )
        for locus in LOCI:
            status, value, source = "REVIEW_REQUIRED", None, None
            if name == "tie" and locus == "B":
                # Already answered by a later pass: this pass must leave it be.
                status, value, source = "RESOLVED", "B*07 B*08", "reread-refused+two-engine"
            if name == "column" and locus == "C":
                # Refused, but a later pass owns the refusal.
                source = "page-ocr+wholepage"
            con.execute(
                f"INSERT INTO fact ({extract_facts.FACT_COLUMNS}) VALUES ({','.join('?' * 17)})",
                (
                    sha,
                    locus,
                    "facts/v1",
                    status,
                    value,
                    None,
                    0,
                    None,
                    "anchor found but no box at all in its cell under this rule",
                    "ADR0008/default-row-rule",
                    None,
                    None,
                    source,
                    "e",
                    "p",
                    "3620",
                    "t",
                ),
            )
    con.commit()
    con.close()
    return path


def read_facts(path: Path, sha: str) -> dict[str, tuple]:
    con = sqlite3.connect(path)
    rows = {
        row[0]: row[1:]
        for row in con.execute(
            "SELECT field, status, value, source, rule_id, value_boxes, reason "
            "FROM fact WHERE sha256=?",
            (sha,),
        )
    }
    con.close()
    return rows


def test_a_dry_run_changes_nothing(tmp_path: Path) -> None:
    module = load("family_repass")
    src, families, geometry, shas = corpus(tmp_path)
    facts = facts_db(tmp_path, shas)
    before = facts.read_bytes()
    tally, _, _ = module.run(
        facts, src, geometry, tmp_path / "no-persian.sqlite", families, dry_run=True
    )
    assert tally["cells family-tie would resolve"] >= 1
    assert tally["cells below-rule would resolve"] >= 1
    assert facts.read_bytes() == before, "a dry run must not write to the facts database"


def test_each_finding_writes_its_own_source_with_the_boxes(tmp_path: Path) -> None:
    module = load("family_repass")
    src, families, geometry, shas = corpus(tmp_path)
    facts = facts_db(tmp_path, shas)
    module.run(facts, src, geometry, tmp_path / "no-persian.sqlite", families, dry_run=False)

    tie = read_facts(facts, shas["tie"])["A"]
    assert tie[0] == "RESOLVED" and tie[1] == "A*01 A*02"
    assert tie[2] == "family-tie"
    assert tie[3].startswith("family/") and "(tie:" in tie[3]
    assert json.loads(tie[4]), "the crop the reviewer is shown"

    column = read_facts(facts, shas["column"])["A"]
    assert column[0] == "RESOLVED" and column[1] == "A*01 A*02"
    assert column[2] == "below-rule"
    assert column[3] == "ADR0008/below-rule"
    assert "column" in column[5]


def test_a_resolved_cell_and_a_later_pass_are_never_touched(tmp_path: Path) -> None:
    module = load("family_repass")
    src, families, geometry, shas = corpus(tmp_path)
    facts = facts_db(tmp_path, shas)
    module.run(facts, src, geometry, tmp_path / "no-persian.sqlite", families, dry_run=False)

    resolved = read_facts(facts, shas["tie"])["B"]
    assert resolved[0] == "RESOLVED" and resolved[2] == "reread-refused+two-engine"
    assert resolved[1] == "B*07 B*08", "this pass revises nothing another reader settled"

    later = read_facts(facts, shas["column"])["C"]
    assert later[0] == "REVIEW_REQUIRED" and later[2] == "page-ocr+wholepage"


def test_a_comparison_sheet_is_refused_outright(tmp_path: Path) -> None:
    module = load("family_repass")
    src, families, geometry, shas = corpus(tmp_path)
    facts = facts_db(tmp_path, shas)
    con = sqlite3.connect(facts)
    con.execute("UPDATE document SET comparison_sheet=1 WHERE sha256=?", (shas["tie"],))
    con.commit()
    con.close()
    tally, _, _ = module.run(
        facts, src, geometry, tmp_path / "no-persian.sqlite", families, dry_run=False
    )
    assert tally["comparison sheet; a rule cannot say whose value it is"] == 1
    assert read_facts(facts, shas["tie"])["A"][0] == "REVIEW_REQUIRED"


def test_the_comparison_sheet_guard_fails_closed(tmp_path: Path) -> None:
    """An empty set from a query that cannot run is indistinguishable from a
    corpus with no comparison sheets in it, and there are 450."""
    module = load("family_repass")
    src, families, geometry, shas = corpus(tmp_path)
    facts = facts_db(tmp_path, shas)
    con = sqlite3.connect(facts)
    con.execute("DROP TABLE document")
    con.commit()
    con.close()
    with pytest.raises(sqlite3.OperationalError):
        module.run(facts, src, geometry, tmp_path / "no-persian.sqlite", families, dry_run=True)


def test_the_comparison_sheet_guard_fails_closed_on_an_empty_result(tmp_path: Path) -> None:
    """The failure the dropped table does NOT exercise, and the likelier one.

    A query that RUNS and matches nothing returns the empty set, and the pass
    then reads all 450 two-subject sheets as one person's page each. That is
    the state of a database whose extraction has not written the
    `comparison_sheet` column yet, or wrote it at another extraction version —
    a partially-run or differently-versioned store, not a corrupt one.
    """
    module = load("family_repass")
    src, families, geometry, shas = corpus(tmp_path)
    facts = facts_db(tmp_path, shas)
    con = sqlite3.connect(facts)
    con.execute("UPDATE document SET comparison_sheet=0")
    con.commit()
    con.close()
    with pytest.raises(SystemExit, match="comparison_sheet"):
        module.run(facts, src, geometry, tmp_path / "no-persian.sqlite", families, dry_run=True)


def test_every_source_this_pass_writes_has_a_review_stratum() -> None:
    """A pass whose values no stratum draws is a pass nobody can check."""
    repass = load("family_repass")
    pack = load("review_pack")
    strata = {name for name, _, _ in pack.STRATA}
    for source in (repass.TIE, repass.LOO, repass.BELOW, repass.PREFIX):
        assert source.replace("-", "_") in strata, source


# --- the repaired box's way back to the page as STORED ---------------------
#
# A joined label box is built on the LEVELLED page and exists nowhere in the
# stored one, so it needs an entry in the way-back map or `geometry.restore`
# writes a levelled box into provenance and the review page crops the wrong
# part of a tilted photograph. The map `merge_prefix_fragments` returns for
# that purpose is keyed by `id()`, which makes it meaningful ONLY for boxes the
# caller kept alive: re-deriving it from a second call keys it on objects that
# are garbage before the loop runs, and CPython may hand one of those addresses
# to a live box later — a wrong crop that differs run to run.


def test_a_repaired_anchor_on_a_tilted_page_is_stored_in_the_stored_frame(tmp_path: Path) -> None:
    """The union of the two halves as PHOTOGRAPHED, not as levelled."""
    module = load("family_repass")
    src, families, _, shas = corpus(tmp_path)
    facts = facts_db(tmp_path, shas)
    module.run(
        facts,
        src,
        tilted_geometry(tmp_path, shas),
        tmp_path / "no-persian.sqlite",
        families,
        dry_run=False,
    )
    con = sqlite3.connect(facts)
    status, source, anchor = con.execute(
        "SELECT status, source, anchor_box FROM fact WHERE sha256=? AND field='DQB1'",
        (shas["prefix"],),
    ).fetchone()
    con.close()
    assert status == "RESOLVED" and source == "family-prefix"
    assert anchor, "a resolved medical value with no crop is the defect this pass exists after"

    fragment, label = photographed(PREFIX_FRAGMENT_LEVEL), photographed(PREFIX_LABEL_LEVEL)
    as_stored = [
        min(fragment.x0, label.x0),
        min(fragment.y0, label.y0),
        max(fragment.x1, label.x1),
        max(fragment.y1, label.y1),
    ]
    as_levelled = [
        min(PREFIX_FRAGMENT_LEVEL.x0, PREFIX_LABEL_LEVEL.x0),
        min(PREFIX_FRAGMENT_LEVEL.y0, PREFIX_LABEL_LEVEL.y0),
        max(PREFIX_FRAGMENT_LEVEL.x1, PREFIX_LABEL_LEVEL.x1),
        max(PREFIX_FRAGMENT_LEVEL.y1, PREFIX_LABEL_LEVEL.y1),
    ]
    assert json.loads(anchor) == pytest.approx(as_stored, abs=1e-9)
    # The failure this pins: the levelled box is a DIFFERENT crop of the
    # photograph, and the value boxes beside it are in the stored frame.
    assert json.loads(anchor) != pytest.approx(as_levelled, abs=1e-6)


def test_the_repair_hands_back_the_boxes_it_actually_built(tmp_path: Path) -> None:
    """Provenance is keyed by `id()`, so the map must describe LIVE boxes.

    A second `merge_prefix_fragments` call returns ids of joined boxes nobody
    holds: every one of them misses the page's own joined box, and the fix-up
    that reads it silently does nothing. This asserts the shape that cannot do
    that — every key of the returned map is the identity of a box the page is
    READ from, and the two halves are gone from that list.
    """
    module = load("family_repass")
    _, families, _, _ = corpus(tmp_path)
    prototypes, prefixed = module.load_families(families)
    boxes, _ = PageFrame(TILT_DEG, WIDTH, HEIGHT).rectify(PREFIX_PAGE)
    chosen = module.rule_for_page(boxes, [], PREFIX_PAGE, prototypes, prefixed, 0.0, 0.0, None)
    assert chosen is not None
    source, _, rule_id, _, read_from, sources = chosen
    assert source == module.PREFIX and "(prefix:DQB1)" in rule_id
    assert sources, "a repaired page reports what each joined box was made of"
    live = {id(box) for box in read_from}
    assert set(sources) <= live, "a key that names no live box restores nothing"
    for merged_id, (label_box, fragment) in sources.items():
        assert id(label_box) not in live and id(fragment) not in live
        joined = next(box for box in read_from if id(box) == merged_id)
        assert joined.x0 == pytest.approx(min(label_box.x0, fragment.x0))
        assert joined.x1 == pytest.approx(max(label_box.x1, fragment.x1))
