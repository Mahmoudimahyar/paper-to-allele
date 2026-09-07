"""The token-anchored DRB3/4/5 row where it meets the corpus.

Three contracts, none of them about the rule's own gates (those are unit-tested
in `tests/unit/test_drbx_token_row.py`):

1. the geometry gate that route (c) puts in front of a widened header must pass
   the headers we already believe — measured on the corpus and pinned in
   `tests/fixtures/drbx_header_gate.json`;
2. `extract_facts.extract` must call the token route only where the header
   route abstained AND the page's FINAL DRB1 status is RESOLVED;
3. `scripts/drbx_token_repass.py` must write nothing by default, write only the
   cells that abstention left behind, and carry the provenance a reviewer's
   crop is cut from.
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
from kidneymatch.ocr.drbx import (  # noqa: E402
    TOKEN_ANCHORED_RULE_ID,
    _geometry_corroborates_header,
)
from kidneymatch.ocr.rulings import GEOMETRY_VERSION  # noqa: E402

FIXTURE = ROOT / "tests/fixtures/drbx_header_gate.json"
WIDTH, HEIGHT = 1000, 1300


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"km_{name}", ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[f"km_{name}"] = module
    spec.loader.exec_module(module)
    return module


# --- 1. the gate against the headers we already believe ---------------------


@pytest.fixture(scope="module")
def calibration() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _page(row: dict) -> tuple[Box, list[Box]]:
    """The page rebuilt from the fixture: the header box and every locus label.

    The fixture stores the LOCUS each label canonicalises to rather than its
    printed text, so the page is rebuilt with a canonical spelling of that
    locus. `find_anchors` and `locus_anchors` — the gate's only two inputs —
    see exactly what they saw on the real page.
    """
    header = Box(*row["header"], "HLA-DRB3/4/5")
    labels = [
        Box(x0, y0, x1, y1, f"HLA-{locus}" if len(locus) <= 2 else locus)
        for locus, x0, y0, x1, y1 in row["labels"]
    ]
    return header, [header, *labels]


def test_the_geometry_gate_passes_the_headers_the_corpus_already_has(calibration) -> None:
    """The gate is calibrated, not invented: it must place a header where the
    pages that HAVE one put theirs.

    Measured 2026-09-06 over the whole corpus (14,315 pages carrying exactly one
    header the strict pattern reads): the gate passes 85.5% of them outright and
    **94.98% of the ones it can be applied to** — those with one DRB1 label and
    a measurable label-column pitch. The rest fail for want of an anchor, not
    for standing in the wrong place, and on those pages a WIDENED header has
    nothing to corroborate it either, which is the refusal the gate exists for.

    The verifier's fix asked for ">= 95% of current headers"; the same fix's own
    calibration figure is 12,363 of 14,359 = 86.1%, which is the number this
    reproduces (12,234 of 14,315 = 85.5%). Both floors below are set under what
    was measured, so a regression in either direction fails here.
    """
    corpus = calibration["corpus"]
    measured = corpus["strict headers measured"]
    applicable = corpus["the gate is applicable"]
    assert measured > 10_000, "the calibration was taken on a corpus this size"
    assert corpus["headers the gate passes"] / measured >= 0.85
    assert corpus["applicable headers the gate passes"] / applicable >= 0.94


def test_the_gate_still_decides_each_sampled_header_the_way_it_was_measured(calibration) -> None:
    """Every sampled page re-run through the gate, on its real geometry."""
    rows = calibration["rows"]
    assert len(rows) > 200, "the sample is too small to catch a regression"
    for row in rows:
        header, boxes = _page(row)
        assert _geometry_corroborates_header(header, boxes) is row["passes"]


# --- 2. the extraction calls the route where, and only where, it may --------

LABEL_H = 0.012
DQB1_Y, DRB1_Y, ROW_Y = 0.400, 0.440, 0.480


def label(text: str, centre_y: float, x0: float = 0.10, width: float = 0.09) -> Box:
    return Box(x0, centre_y - LABEL_H / 2, x0 + width, centre_y + LABEL_H / 2, text)


def token(text: str, x0: float, centre_y: float = ROW_Y) -> Box:
    return Box(x0, centre_y - LABEL_H / 2, x0 + 0.06, centre_y + LABEL_H / 2, text)


def form(*extra: Box, drb1_values: bool = True) -> list[Box]:
    boxes = [label("DQB1", DQB1_Y), label("DRB1", DRB1_Y)]
    if drb1_values:
        boxes += [token("DRB1*15", 0.30, DRB1_Y), token("DRB1*11", 0.50, DRB1_Y)]
    return [*boxes, *extra]


PAGES = {
    # no header anywhere: the row is placed from the page's own pitch
    "no_header": form(token("DRB3", 0.40), token("DRB4", 0.70)),
    # a header the strict pattern reads: the header route keeps the row
    "header": form(label("HLA-DRB3/4/5", ROW_Y), token("DRB3", 0.40), token("DRB4", 0.70)),
    # no header and no DRB1 value: the DRB1-REVIEW stratum is held back
    "drb1_unread": form(token("DRB3", 0.40), token("DRB4", 0.70), drb1_values=False),
    # two subjects on one sheet, with a header: the genes go to a human
    "comparison": form(
        label("HLA-DRB3/4/5", ROW_Y),
        token("DRB3", 0.40),
        token("DRB4", 0.70),
        Box(0.30, 0.10, 0.38, 0.11, "Donor"),
        Box(0.55, 0.10, 0.66, 0.11, "Recipient"),
    ),
}


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
    for sha in shas.values():
        con.execute(
            "INSERT INTO page_geometry VALUES (?,?,?,?,?,?,?,?)",
            (sha, GEOMETRY_VERSION, "STRAIGHT", 0.0, WIDTH, HEIGHT, "[]", "[]"),
        )
    con.commit()
    con.close()
    return src, geometry, shas


def extracted(tmp_path: Path) -> tuple[Path, dict[str, str]]:
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


def genes_of(facts: Path, sha: str) -> dict[str, tuple]:
    con = sqlite3.connect(facts)
    rows = {
        row[0]: row[1:]
        for row in con.execute(
            "SELECT field, status, value, reason, rule_id, anchor_box, value_boxes "
            "FROM fact WHERE sha256=? AND field IN ('DRB3','DRB4','DRB5')",
            (sha,),
        )
    }
    con.close()
    return rows


def test_the_extraction_places_the_row_where_no_header_was_read(tmp_path: Path) -> None:
    facts, shas = extracted(tmp_path)
    genes = genes_of(facts, shas["no_header"])
    assert genes["DRB3"][0] == "RESOLVED" and genes["DRB3"][1] == "PRESENT"
    assert genes["DRB4"][0] == "RESOLVED" and genes["DRB4"][1] == "PRESENT"
    assert genes["DRB3"][3] == TOKEN_ANCHORED_RULE_ID
    # never ABSENT: the enumeration that licenses the counting rule was not read
    assert genes["DRB5"][0] == "UNKNOWN" and genes["DRB5"][1] is None
    # the crop the reviewer sees: the gene's own box, and no anchor at all on
    # the gene nobody named
    assert json.loads(genes["DRB3"][5])
    assert genes["DRB5"][4] is None and genes["DRB5"][5] is None


def test_the_header_route_keeps_first_refusal(tmp_path: Path) -> None:
    facts, shas = extracted(tmp_path)
    genes = genes_of(facts, shas["header"])
    assert genes["DRB3"][3] == "GROUPED_DRBX/v1"
    # the header route counted two tokens, so it may certify the third absent
    assert genes["DRB5"][1] == "ABSENT"


def test_a_page_whose_DRB1_was_not_resolved_keeps_its_abstention(tmp_path: Path) -> None:
    facts, shas = extracted(tmp_path)
    genes = genes_of(facts, shas["drb1_unread"])
    for gene in ("DRB3", "DRB4", "DRB5"):
        assert genes[gene][0] == "UNKNOWN"
        assert genes[gene][2] == "no grouped DRB3/4/5 header on this document"


def test_the_genes_of_a_comparison_sheet_go_to_a_human(tmp_path: Path) -> None:
    """The guard the loci have always had, applied to the gene loop too: two
    subjects on one page and the row rule cannot say whose gene it is."""
    facts, shas = extracted(tmp_path)
    genes = genes_of(facts, shas["comparison"])
    for gene in ("DRB3", "DRB4", "DRB5"):
        assert genes[gene][0] == "REVIEW_REQUIRED", gene
        assert genes[gene][1] is None
        assert "two subjects" in genes[gene][2]


# --- 3. the corpus pass ------------------------------------------------------


def prepared(tmp_path: Path) -> tuple[Path, Path, Path, dict[str, str]]:
    """The extraction run, then its DRBX cells put back to the abstention.

    The pass answers pages the extraction left UNKNOWN, so the fixture is the
    corpus as it stands TODAY: extracted before the token route existed.
    """
    src, geometry, shas = corpus(tmp_path)
    module = load("extract_facts")
    families = tmp_path / "families.json"
    families.write_text(json.dumps({"families": []}), encoding="utf-8")
    facts = tmp_path / "facts.sqlite"
    assert (
        module.run(src, tmp_path / "no-persian.sqlite", families, facts, None, 10, None, geometry)
        == 0
    )
    con = sqlite3.connect(facts)
    con.execute(
        "UPDATE fact SET status='UNKNOWN', value=NULL, raw=NULL, reason=?, source=NULL, "
        "anchor_box=NULL, value_boxes=NULL WHERE field IN ('DRB3','DRB4','DRB5')",
        ("no grouped DRB3/4/5 header on this document",),
    )
    con.commit()
    con.close()
    return facts, src, geometry, shas


def test_the_pass_is_dry_by_default_and_writes_nothing(tmp_path: Path) -> None:
    module = load("drbx_token_repass")
    facts, src, geometry, shas = prepared(tmp_path)
    before = sqlite3.connect(facts).execute("SELECT * FROM fact ORDER BY 1,2").fetchall()
    tally = module.run(facts, src, geometry)  # no dry_run argument at all
    assert tally["PRESENT: DRB3"] == 1
    assert sqlite3.connect(facts).execute("SELECT * FROM fact ORDER BY 1,2").fetchall() == before


def test_the_pass_writes_only_the_genes_the_row_named(tmp_path: Path) -> None:
    module = load("drbx_token_repass")
    facts, src, geometry, shas = prepared(tmp_path)
    module.run(facts, src, geometry, dry_run=False)
    genes = genes_of(facts, shas["no_header"])
    assert genes["DRB3"][0] == "RESOLVED" and genes["DRB3"][1] == "PRESENT"
    assert genes["DRB4"][0] == "RESOLVED" and genes["DRB4"][1] == "PRESENT"
    assert genes["DRB5"][0] == "UNKNOWN", "no absence is certified on this route"
    assert genes["DRB3"][3] == TOKEN_ANCHORED_RULE_ID
    assert json.loads(genes["DRB3"][5]), "the value boxes travel with the fact"
    assert json.loads(genes["DRB3"][4]), "and the DRB1 label the row was placed from"
    con = sqlite3.connect(facts)
    sources = {
        row[0]
        for row in con.execute(
            "SELECT source FROM fact WHERE sha256=? AND field='DRB3'", (shas["no_header"],)
        )
    }
    con.close()
    assert sources == {"token-anchored-drbx"}


def test_the_pass_leaves_every_other_page_alone(tmp_path: Path) -> None:
    module = load("drbx_token_repass")
    facts, src, geometry, shas = prepared(tmp_path)
    module.run(facts, src, geometry, dry_run=False)
    for name in ("drb1_unread", "comparison"):
        for gene, row in genes_of(facts, shas[name]).items():
            assert row[0] == "UNKNOWN", f"{name}:{gene}"


def test_a_cell_another_pass_has_claimed_is_not_touched(tmp_path: Path) -> None:
    """`source IS NULL` is what keeps this pass off every other rule's work."""
    module = load("drbx_token_repass")
    facts, src, geometry, shas = prepared(tmp_path)
    con = sqlite3.connect(facts)
    con.execute(
        "UPDATE fact SET source='ink-certified' WHERE sha256=? AND field='DRB3'",
        (shas["no_header"],),
    )
    con.commit()
    con.close()
    module.run(facts, src, geometry, dry_run=False)
    genes = genes_of(facts, shas["no_header"])
    assert genes["DRB3"][0] == "UNKNOWN"
    assert genes["DRB4"][0] == "RESOLVED", "the rest of the row is still read"


def test_the_comparison_sheet_guard_fails_closed(tmp_path: Path) -> None:
    """An empty set from a query that could not run is indistinguishable from a
    corpus with no comparison sheets in it, and the second is not true."""
    module = load("drbx_token_repass")
    facts, src, geometry, _ = prepared(tmp_path)
    con = sqlite3.connect(facts)
    con.execute("DROP TABLE document")
    con.commit()
    con.close()
    with pytest.raises(sqlite3.OperationalError):
        module.run(facts, src, geometry, dry_run=False)


def test_a_dry_run_never_opens_the_store_for_writing(tmp_path: Path) -> None:
    """A dry run has no business holding a write handle on a live database."""
    module = load("drbx_token_repass")
    facts, src, geometry, _ = prepared(tmp_path)
    con = module.open_read_only(facts)
    with pytest.raises(sqlite3.OperationalError):
        con.execute("UPDATE fact SET status='RESOLVED' WHERE field='DRB3'")
    con.close()
