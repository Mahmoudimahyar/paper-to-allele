"""Promotion of a decode PROPOSAL: only where an independent engine agreed.

Synthetic database only. The gate is the conjunction of three rows: a refused
fact ("does not parse"), a PROPOSAL from the axis-aligned decoder, and a
CONFIRMED verdict under the `@proposal` confirmer version.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.task("BOOT-001")

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/promote_proposals.py"


def load():
    spec = importlib.util.spec_from_file_location("km_promote_proposals", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["km_promote_proposals"] = module
    spec.loader.exec_module(module)
    return module


REFUSED = "candidate 'x' does not parse as an allele value"


def database(tmp_path: Path) -> Path:
    db = tmp_path / "facts.sqlite"
    con = sqlite3.connect(db)
    con.executescript(
        """
        CREATE TABLE fact (sha256, field, extraction_version, status, value, raw, repaired,
            second_allele, reason, rule_id, anchor_box, value_boxes, source, stability);
        CREATE TABLE decode (sha256, field, extraction_version, decoder_version, verdict, reading);
        CREATE TABLE confirmation (sha256, field, extraction_version, confirmer_version,
            verdict, reading, created_utc);
        CREATE TABLE document (sha256, extraction_version, quality_band);
        """
    )
    for sha in ("d1", "d2", "d3", "d4", "d5", "d6", "d7", "d9", "d10", "d11"):
        con.execute("INSERT INTO document VALUES (?, 'facts/v1', 'HIGH')", (sha,))
    con.execute("INSERT INTO document VALUES ('d8', 'facts/v1', 'LOW')")
    facts = [
        # confirmed pair: promoted
        ("d1", "DQB1", "REVIEW_REQUIRED", None, REFUSED, "family/FORM#0"),
        # confirmed single: promoted with its second allele declared unread
        ("d2", "A", "REVIEW_REQUIRED", None, REFUSED, "ADR0008/default-row-rule"),
        # contradicted: stays refused
        ("d3", "B", "REVIEW_REQUIRED", None, REFUSED, "family/FORM#1"),
        # no confirmation row at all: stays refused
        ("d4", "DRB1", "REVIEW_REQUIRED", None, REFUSED, "family/FORM#1"),
        # confirmed, but the proposal names another locus: never promoted
        ("d5", "C", "REVIEW_REQUIRED", None, REFUSED, "family/FORM#1"),
        # a star-less refusal (policy) with a confirmed proposal: not this gate's cell
        ("d6", "B", "REVIEW_REQUIRED", None, "candidate 'B35' names its locus without a star", "x"),
        # a resolved cell whose confirmer happens to carry an @proposal row: untouched
        ("d7", "A", "RESOLVED", "A*02 A*24", None, "family/FORM#0"),
        # confirmed, but on a LOW-quality page: withheld
        ("d8", "DQB1", "REVIEW_REQUIRED", None, REFUSED, "family/FORM#1"),
        # confirmed against an EARLIER proposal; the decode has since read differently
        ("d10", "A", "REVIEW_REQUIRED", None, REFUSED, "family/FORM#1"),
        # confirmed, but the proposal's family is not admissible for the locus
        ("d11", "A", "REVIEW_REQUIRED", None, REFUSED, "family/FORM#1"),
    ]
    for sha, field, status, value, reason, rule in facts:
        con.execute(
            "INSERT INTO fact VALUES (?,?,'facts/v1',?,?,NULL,0,'UNREAD',?,?,NULL,"
            "'[[0,0,1,1]]',NULL,'NOT_CHECKED')",
            (sha, field, status, value, reason, rule),
        )
    decodes = [
        ("d1", "DQB1", "ctc-viterbi/v1", "PROPOSAL", "DQB1*02 DQB1*05"),
        ("d1", "DQB1", "ctc-viterbi/v1+frame", "PROPOSAL", "DQB1*02 DQB1*05"),
        ("d2", "A", "ctc-viterbi/v1", "PROPOSAL", "A*24"),
        ("d3", "B", "ctc-viterbi/v1", "PROPOSAL", "B*35 B*51"),
        ("d4", "DRB1", "ctc-viterbi/v1", "PROPOSAL", "DRB1*11 DRB1*15"),
        ("d5", "C", "ctc-viterbi/v1", "PROPOSAL", "B*07"),
        ("d6", "B", "ctc-viterbi/v1", "PROPOSAL", "B*35"),
        ("d7", "A", "ctc-viterbi/v1", "UNANIMOUS", "A*02 A*24"),
        ("d8", "DQB1", "ctc-viterbi/v1", "PROPOSAL", "DQB1*03 DQB1*06"),
        ("d10", "A", "ctc-viterbi/v1", "PROPOSAL", "A*02 A*11"),
        ("d11", "A", "ctc-viterbi/v1", "PROPOSAL", "A*83"),
    ]
    con.executemany("INSERT INTO decode VALUES (?,?,'facts/v1',?,?,?)", decodes)
    confirmations = [
        ("d1", "DQB1", "ppocrv5/en-mobile-rec@proposal", "CONFIRMED", "DQB1*02 DQB1*05"),
        ("d2", "A", "ppocrv5/en-mobile-rec@proposal", "CONFIRMED", "A*24"),
        ("d3", "B", "ppocrv5/en-mobile-rec@proposal", "CONTRADICTED", "B*35 B*52"),
        ("d5", "C", "ppocrv5/en-mobile-rec@proposal", "CONFIRMED", "B*07"),
        ("d6", "B", "ppocrv5/en-mobile-rec@proposal", "CONFIRMED", "B*35"),
        ("d7", "A", "ppocrv5/en-mobile-rec@proposal", "CONFIRMED", "A*02 A*24"),
        ("d8", "DQB1", "ppocrv5/en-mobile-rec@proposal", "CONFIRMED", "DQB1*03 DQB1*06"),
        ("d10", "A", "ppocrv5/en-mobile-rec@proposal", "CONFIRMED", "A*02 A*24"),
        ("d11", "A", "ppocrv5/en-mobile-rec@proposal", "CONFIRMED", "A*83"),
    ]
    con.executemany("INSERT INTO confirmation VALUES (?,?,'facts/v1',?,?,?,'t')", confirmations)
    con.commit()
    con.close()
    return db


def test_only_a_confirmed_proposal_on_a_shape_refusal_is_promoted(tmp_path: Path) -> None:
    module = load()
    db = database(tmp_path)
    tally = module.promote(db)
    assert tally == {
        "promoted DQB1": 1,
        "promoted A": 1,
        "proposal not a value of its locus": 2,  # d5 names another locus, d11 is inadmissible
        "confirmer's reading no longer matches the proposal": 1,  # d10
    }
    con = sqlite3.connect(db)
    rows = {
        (sha, field): (status, value, repaired, second, source, stability)
        for sha, field, status, value, repaired, second, source, stability in con.execute(
            "SELECT sha256, field, status, value, repaired, second_allele, source, stability "
            "FROM fact"
        )
    }
    assert rows[("d1", "DQB1")] == (
        "RESOLVED",
        "DQB1*02 DQB1*05",
        1,
        "READ",
        "decode+ppocrv5",
        "UNANIMOUS",
    )
    assert rows[("d2", "A")] == ("RESOLVED", "A*24", 1, "UNREAD", "decode+ppocrv5", "UNANIMOUS")
    for key in (
        ("d3", "B"),
        ("d4", "DRB1"),
        ("d5", "C"),
        ("d6", "B"),
        ("d8", "DQB1"),
        ("d10", "A"),
        ("d11", "A"),
    ):
        assert rows[key][0] == "REVIEW_REQUIRED", key
    assert rows[("d7", "A")] == ("RESOLVED", "A*02 A*24", 0, "UNREAD", None, "NOT_CHECKED")
    reason = con.execute("SELECT reason FROM fact WHERE sha256='d1'").fetchone()[0]
    assert "promoted" in reason and "PP-OCRv5" in reason and "nine offsets" in reason


def test_promotion_is_idempotent_and_dry_run_changes_nothing(tmp_path: Path) -> None:
    module = load()
    db = database(tmp_path)
    before = sqlite3.connect(db).execute("SELECT status, value FROM fact ORDER BY 1, 2").fetchall()
    dry = module.promote(db, dry_run=True)
    assert sum(n for k, n in dry.items() if k.startswith("promoted")) == 2
    assert (
        sqlite3.connect(db).execute("SELECT status, value FROM fact ORDER BY 1, 2").fetchall()
        == before
    )
    module.promote(db)
    again = module.promote(db)
    assert sum(n for k, n in again.items() if k.startswith("promoted")) == 0


@pytest.mark.parametrize(
    ("locus", "reading", "expected"),
    [
        ("DQB1", "DQB1*02 DQB1*05", "DQB1*02 DQB1*05"),
        ("A", "24", "A*24"),  # the decode's grammar does not require the prefix
        # a second-field proposal is never CONFIRMED by `confirm_value`, which
        # compares first fields; it is a value of its locus all the same
        ("DRB1", "DRB1*11:01", "DRB1*11:01"),
        ("A", "A*83", None),  # 83 is not an A family in IMGT: inadmissible
        ("C", "B*07", None),  # names another locus
        ("A", "A*02 A*24 A*11", None),  # more than a locus can hold
        ("A", "", None),
        ("A", "ALL", None),
    ],
)
def test_the_proposal_becomes_a_value_of_its_locus_or_nothing(
    locus: str, reading: str, expected: str | None
) -> None:
    module = load()
    assert module.proposal_value(locus, reading) == expected


def test_a_promotion_on_a_low_quality_page_is_withheld_and_an_old_one_withdrawn(
    tmp_path: Path,
) -> None:
    """Two engines reading the same digits from a blurred crop share their
    failure: the one LOW-page promotion the reviewer had labelled was wrong."""
    module = load()
    db = database(tmp_path)
    con = sqlite3.connect(db)
    # a promotion made before the gate existed, on a LOW page
    con.execute(
        "INSERT INTO fact VALUES ('d9','A','facts/v1','RESOLVED','A*11',NULL,1,'UNREAD',?,"
        "'x',NULL,'[[0,0,1,1]]',?, 'UNANIMOUS')",
        (module.REASON, module.SOURCE),
    )
    con.execute("UPDATE document SET quality_band='LOW' WHERE sha256='d9'")
    con.commit()
    con.close()
    tally = module.promote(db)
    assert tally["withdrawn on LOW pages"] == 1
    assert "promoted DQB1" in tally and tally["promoted DQB1"] == 1  # d1 only, never d8
    con = sqlite3.connect(db)
    d8 = con.execute("SELECT status, value FROM fact WHERE sha256='d8'").fetchone()
    assert d8 == ("REVIEW_REQUIRED", None)
    d9 = con.execute(
        "SELECT status, value, source, repaired, reason FROM fact WHERE sha256='d9'"
    ).fetchone()
    assert d9[:4] == ("REVIEW_REQUIRED", None, None, 0)
    assert "withheld" in d9[4] and "LOW" in d9[4]
    assert module.promote(db)["withdrawn on LOW pages"] == 0, "withdrawal is idempotent"
