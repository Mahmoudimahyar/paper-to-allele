"""The one place a document becomes facts.

Until this script existed, `anchors`, `drbx`, `role`, `abo` and
`drbx_consistency` were imported by their own tests and by nothing else, and
every corpus figure in ADR 0008 came from a throwaway session script. These
tests pin what the assembled pipeline must do, especially the two gates that
need a whole page and so cannot live in any single rule.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from kidneymatch.hla.vocabulary import load_vocabulary
from kidneymatch.ocr.anchors import Box
from kidneymatch.ocr.store import OcrDocument

pytestmark = pytest.mark.task("BOOT-001")

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/extract_facts.py"


def load():
    spec = importlib.util.spec_from_file_location("km_extract_facts", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def at(x0: float, text: str, y0: float = 0.50, w: float = 0.06, h: float = 0.03) -> Box:
    return Box(x0=x0, y0=y0, x1=x0 + w, y1=y0 + h, text=text)


def document(boxes: list[Box], sha: str = "aaa") -> OcrDocument:
    return OcrDocument(
        sha256=sha,
        rel_path="photos/p.jpg",
        boxes=boxes,
        confidences=[],
        width=1280,
        height=960,
        engine_version="e1",
        preproc_version="p1",
        error=None,
    )


def facts(boxes: list[Box], persian: list[Box] | None = None) -> dict[str, dict]:
    module = load()
    rows, summary = module.extract(
        document(boxes), persian or [], load_vocabulary(), "2026-09-02T00:00:00+00:00"
    )
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
    out = {
        dict(zip(columns, row, strict=True))["field"]: dict(zip(columns, row, strict=True))
        for row in rows
    }
    out["_summary"] = summary
    return out


CLEAN_ROW = [at(0.10, "DRB1"), at(0.22, "11"), at(0.34, "15")]


def test_a_clean_locus_row_becomes_a_resolved_fact() -> None:
    result = facts(CLEAN_ROW)["DRB1"]
    assert result["status"] == "RESOLVED"
    assert result["value"] == "11 15"
    assert result["second_allele"] == "READ"


def test_every_fact_carries_provenance_to_its_boxes() -> None:
    """`OCR-001`: every accepted field has a source crop or bounding box."""
    result = facts(CLEAN_ROW)["DRB1"]
    assert json.loads(result["anchor_box"]) == [0.10, 0.50, 0.16, 0.53]
    assert len(json.loads(result["value_boxes"])) == 2


def test_every_fact_records_the_engine_and_reference_versions() -> None:
    """A value is only reproducible if what produced it is recorded."""
    result = facts(CLEAN_ROW)["DRB1"]
    assert result["engine_version"] == "e1"
    assert result["preproc_version"] == "p1"
    assert result["imgt_version"] == load_vocabulary().imgt_version


def test_a_comparison_sheet_sends_every_locus_to_review() -> None:
    """450 documents print `Donor | Recipient` as column headings and carry two
    people's typings side by side.

    Which column a value belongs to is exactly what a row-based rule cannot
    tell, so this page-level gate cannot live inside any single rule.
    """
    sheet = [*CLEAN_ROW, at(0.30, "Donor", y0=0.10), at(0.55, "Recipient", y0=0.10)]
    result = facts(sheet)
    assert result["DRB1"]["status"] == "REVIEW_REQUIRED"
    assert "two subjects" in result["DRB1"]["reason"]
    assert result["_summary"]["comparison_sheet"] == 1


def test_a_box_claimed_by_two_loci_withdraws_both_readings() -> None:
    """Each locus resolves with no memory of what another bound."""
    dqa1 = Box(x0=0.10, y0=0.700, x1=0.18, y1=0.720, text="DQA1")
    dpa1 = Box(x0=0.10, y0=0.640, x1=0.18, y1=0.660, text="DPA1")
    shared = Box(x0=0.30, y0=0.630, x1=0.36, y1=0.730, text="01")
    result = facts([dqa1, dpa1, shared])
    assert result["DQA1"]["status"] != "RESOLVED"
    assert result["DPA1"]["status"] != "RESOLVED"


def test_the_drbx_genes_come_from_the_grouped_row_not_the_locus_rule() -> None:
    header = Box(x0=0.10, y0=0.60, x1=0.24, y1=0.63, text="HLA-DRB3/4/5")
    boxes = [header, at(0.40, "DRB3", y0=0.605), at(0.70, "DRB4", y0=0.605)]
    result = facts(boxes)
    assert result["DRB3"]["value"] == "PRESENT"
    assert result["DRB5"]["value"] == "ABSENT"
    assert result["DRB3"]["rule_id"].startswith("GROUPED_DRBX")


def test_rh_is_recorded_even_when_unknown() -> None:
    """A missing Rh must be a stored UNKNOWN, not an absent row that a consumer
    could read as negative."""
    result = facts(CLEAN_ROW)["RH"]
    assert result["value"] == "UNKNOWN"


def test_an_unreadable_field_is_stored_with_its_reason() -> None:
    """The review queue is drawn from these rows, so the reason has to survive."""
    result = facts([at(0.10, "DRB1"), at(0.22, "83")])["DRB1"]
    assert result["status"] == "REVIEW_REQUIRED"
    assert "DRB1" in result["reason"]
    assert result["value"] is None


def test_the_document_summary_records_the_consistency_check() -> None:
    header = Box(x0=0.10, y0=0.60, x1=0.24, y1=0.63, text="HLA-DRB3/4/5")
    boxes = [*CLEAN_ROW, header, at(0.40, "DRB3", y0=0.605), at(0.70, "DRB5", y0=0.605)]
    assert facts(boxes)["_summary"]["consistency"] == "CONSISTENT"


def test_a_row_the_rules_cannot_read_yields_no_value_anywhere() -> None:
    result = facts([at(0.10, "DRB1")])
    assert all(
        row["value"] is None
        for field, row in result.items()
        if field not in ("_summary", "RH", "ROLE", "ABO")
    )


def test_the_run_is_resumable_and_versioned(tmp_path: Path) -> None:
    """A multi-hour pass that cannot resume restarts from zero after any
    interruption."""
    module = load()
    con = module.connect(tmp_path / "facts.sqlite")
    keys = [r[1] for r in con.execute("PRAGMA table_info(fact)") if r[5]]
    assert set(keys) == {"sha256", "field", "extraction_version"}
    document_keys = [r[1] for r in con.execute("PRAGMA table_info(document)") if r[5]]
    assert set(document_keys) == {"sha256", "extraction_version"}
    con.close()


def test_thumbnails_never_reach_the_facts_table() -> None:
    """The corpus reader is the only source, so KI-009 cannot recur here."""
    source = SCRIPT.read_text(encoding="utf-8")
    assert "read_corpus" in source
    assert "FROM ocr_result" not in source


def test_extraction_survives_a_column_a_later_pass_added() -> None:
    """`decode_pass.py` adds `stability` to the fact table.

    A positional INSERT breaks the moment it has, which is exactly when
    re-extraction matters most — after the corpus has been decoded and someone
    fixes the resolver. Measured: it failed with "table fact has 18 columns but
    17 values were supplied", so the insert names its columns.
    """
    body = SCRIPT.read_text(encoding="utf-8")
    assert "FACT_COLUMNS" in body
    assert "INSERT OR REPLACE INTO fact VALUES" not in body, "positional insert"
    assert "stability" not in body.split("FACT_COLUMNS = (")[1].split(")")[0], (
        "a re-extracted fact has not been checked for stability, and must fall back "
        "to the NOT_CHECKED default rather than claiming a verdict"
    )


def test_a_caption_reaches_the_role_decision_but_cannot_resolve_alone() -> None:
    """The poster is often a broker. `decide_document_role` lets a caption
    corroborate a weak printed field or veto any reading, and the extractor
    must hand it over rather than deciding for itself."""
    body = SCRIPT.read_text(encoding="utf-8")
    assert "caption_role=caption_role" in body
    assert "tier = 'STATEMENT'" in body, "a refused caption must say nothing"
