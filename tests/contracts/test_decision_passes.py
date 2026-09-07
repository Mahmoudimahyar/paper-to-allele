"""Three passes that act on an operator's decision, and the gate each one keeps.

`gate1_repromote` restores a withdrawn value only on independent agreement;
`ink_drain` retires a review item only where the cell is measured blank; and
`sheet_abo_review` withdraws a printed blood group only from a page carrying two
people. Each test names a way the pass could assert something untrue, and each
pass must undo itself exactly — a decision a person may reverse has to be
reversible in one statement.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EV = "facts/v1"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def store() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.executescript(
        """
        CREATE TABLE fact (sha256 TEXT, field TEXT, extraction_version TEXT, status TEXT,
            value TEXT, raw TEXT, repaired INTEGER DEFAULT 0, second_allele TEXT, reason TEXT,
            rule_id TEXT, source TEXT, created_utc TEXT DEFAULT '',
            PRIMARY KEY (sha256, field, extraction_version));
        CREATE TABLE confirmation (sha256 TEXT, field TEXT, extraction_version TEXT,
            confirmer_version TEXT, verdict TEXT, reading TEXT, created_utc TEXT DEFAULT '');
        CREATE TABLE cell_ink (sha256 TEXT, field TEXT, extraction_version TEXT,
            ink_version TEXT, region TEXT, fraction REAL, coverage REAL, decision TEXT,
            created_utc TEXT DEFAULT '');
        CREATE TABLE document (sha256 TEXT, extraction_version TEXT, rel_path TEXT,
            comparison_sheet INTEGER DEFAULT 0, created_utc TEXT DEFAULT '');
        """
    )
    return con


def fact(con, sha, field, status, *, value=None, raw=None, reason=None, source=None):
    con.execute(
        "INSERT INTO fact (sha256, field, extraction_version, status, value, raw, reason, source) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (sha, field, EV, status, value, raw, reason, source),
    )


def row(con, sha, field):
    return con.execute(
        "SELECT status, value, raw, reason, source FROM fact WHERE sha256=? AND field=?",
        (sha, field),
    ).fetchone()


# --- gate-1 re-promotion --------------------------------------------------


def test_two_families_agreeing_and_nobody_dissenting_is_agreement() -> None:
    g = load("gate1_repromote")
    verdicts = [
        ("ppocrv5/en-mobile-rec", "CONFIRMED", "A*02 A*24"),
        ("tesseract5/psm7-alnum", "CONFIRMED", "A*02 A*24"),
        ("ppocrv6/medium-rec", "UNCONFIRMED", ""),
    ]
    assert g.agreed_reading(verdicts) == ("A*02 A*24", 2)


def test_one_contradiction_vetoes_however_many_agree() -> None:
    g = load("gate1_repromote")
    verdicts = [
        ("ppocrv5/en-mobile-rec", "CONFIRMED", "A*02 A*24"),
        ("ppocrv6/medium-rec", "CONFIRMED", "A*02 A*24"),
        ("tesseract5/psm7-alnum", "CONTRADICTED", "A*02 A*29"),
    ]
    assert g.agreed_reading(verdicts) is None


def test_an_unconfirmed_engine_with_a_different_reading_is_a_dissent() -> None:
    """Silence is an abstention; another value is not."""
    g = load("gate1_repromote")
    verdicts = [
        ("ppocrv5/en-mobile-rec", "CONFIRMED", "A*02 A*24"),
        ("ppocrv6/medium-rec", "CONFIRMED", "A*02 A*24"),
        ("tesseract5/psm7-alnum", "UNCONFIRMED", "A*02 A*21"),
    ]
    assert g.agreed_reading(verdicts) is None


def test_two_confirmers_of_one_family_are_one_witness() -> None:
    """`ppocrv5` on a different crop is not a second engine, and `@drbx` /
    `@proposal` variants judge other things and do not count at all."""
    g = load("gate1_repromote")
    assert g.agreed_reading([("ppocrv5/en-mobile-rec", "CONFIRMED", "B*35")]) is None
    assert (
        g.agreed_reading(
            [
                ("ppocrv5/en-mobile-rec", "CONFIRMED", "B*35"),
                ("ppocrv5/en-mobile-rec@proposal", "CONFIRMED", "B*35"),
                ("tesseract5/psm7-alnum@drbx", "CONFIRMED", "B*35"),
            ]
        )
        is None
    )


def test_two_families_confirming_different_text_is_not_agreement() -> None:
    g = load("gate1_repromote")
    verdicts = [
        ("ppocrv5/en-mobile-rec", "CONFIRMED", "A*02 A*24"),
        ("ppocrv6/medium-rec", "CONFIRMED", "A*02 A*24 "),  # trailing space is stripped
        ("tesseract5/psm7-alnum", "CONFIRMED", "A*02:01 A*24"),
    ]
    assert g.agreed_reading(verdicts) is None


def test_repromotion_restores_the_agreed_reading_and_undoes_exactly() -> None:
    g = load("gate1_repromote")
    con = store()
    fact(
        con,
        "s1",
        "A",
        "REVIEW_REQUIRED",
        raw="A'02 A*24",
        reason=g.REASON_SPLIT,
        source=f"OCR|{g.GATE_TAG}",
    )
    fact(
        con,
        "s2",
        "A",
        "REVIEW_REQUIRED",
        raw="A'02 A*24",
        reason=g.REASON_SPLIT,
        source=f"OCR|{g.GATE_TAG}",
    )
    fact(
        con,
        "s3",
        "A",
        "REVIEW_REQUIRED",
        raw="A'02",
        reason="some other withdrawal",
        source=f"OCR|{g.GATE_TAG}",
    )
    for sha in ("s1", "s2", "s3"):
        for engine, verdict in (("ppocrv5/x", "CONFIRMED"), ("ppocrv6/x", "CONFIRMED")):
            con.execute(
                "INSERT INTO confirmation VALUES (?,?,?,?,?,?,'')",
                (sha, "A", EV, engine, verdict if sha != "s2" else "CONTRADICTED", "A*02 A*24"),
            )
    tally = g.run(con, dry_run=True)
    assert tally["gate-1 withdrawals"] == 2 and tally["re-promoted"] == 1
    assert row(con, "s1", "A")[0] == "REVIEW_REQUIRED", "a dry run wrote"
    g.run(con, dry_run=False)
    status, value, raw, reason, source = row(con, "s1", "A")
    assert (status, value, raw) == ("RESOLVED", "A*02 A*24", "A'02 A*24")
    assert source == f"OCR|{g.TAG}" and "2 independent engines" in reason
    assert row(con, "s2", "A")[0] == "REVIEW_REQUIRED", "a contradicted cell was promoted"
    assert row(con, "s3", "A")[0] == "REVIEW_REQUIRED", "a gate-2 row was touched"
    assert g.undo(con) == 1
    assert row(con, "s1", "A") == (
        "REVIEW_REQUIRED",
        None,
        "A'02 A*24",
        g.REASON_SPLIT,
        f"OCR|{g.GATE_TAG}",
    )


# --- ink drain --------------------------------------------------------------


def test_only_a_blank_measured_row_rule_cell_is_drained() -> None:
    d = load("ink_drain")
    con = store()
    reason = "anchor found but no box at all in its cell"
    fact(con, "s1", "C", "REVIEW_REQUIRED", reason=reason)  # blank -> drained
    fact(con, "s2", "C", "REVIEW_REQUIRED", reason=reason)  # inked -> stays
    fact(con, "s3", "C", "REVIEW_REQUIRED", reason=reason)  # unmeasured -> stays
    fact(
        con, "s4", "C", "REVIEW_REQUIRED", reason="candidate 'Ca08' does not parse"
    )  # blank but another reason
    fact(
        con, "s5", "C", "RESOLVED", value="C*07", reason="row rule"
    )  # blank measure on a value: never
    for sha, decision in (("s1", "BLANK"), ("s2", "INKED"), ("s4", "BLANK"), ("s5", "BLANK")):
        con.execute(
            "INSERT INTO cell_ink VALUES (?,?,?,?,?,?,?,?,'')",
            (sha, "C", EV, "cell-ink/v1", "[0,0,1,1]", 0.001, 0.9, decision),
        )
    tally = d.run(con, dry_run=True)
    assert tally["blank printed cells in review"] == 1
    d.run(con, dry_run=False)
    status, value, _, reason_now, source = row(con, "s1", "C")
    assert status == "NOT_TESTED" and value is None and source == d.TAG
    assert reason_now.endswith(f"{d.WAS}{reason}") and "cell-ink/v1" in reason_now
    for sha, expected in (
        ("s2", "REVIEW_REQUIRED"),
        ("s3", "REVIEW_REQUIRED"),
        ("s4", "REVIEW_REQUIRED"),
        ("s5", "RESOLVED"),
    ):
        assert row(con, sha, "C")[0] == expected, sha
    assert d.run(con, dry_run=True)["blank printed cells in review"] == 0, "not idempotent"
    assert d.undo(con) == 1
    assert row(con, "s1", "C") == ("REVIEW_REQUIRED", None, None, reason, None)


# --- printed blood group on a comparison sheet ----------------------------


def test_only_the_printed_group_on_a_two_person_page_is_withdrawn() -> None:
    s = load("sheet_abo_review")
    con = store()
    con.execute("INSERT INTO document VALUES ('sheet', ?, 'a.jpg', 1, '')", (EV,))
    con.execute("INSERT INTO document VALUES ('single', ?, 'b.jpg', 0, '')", (EV,))
    fact(
        con,
        "sheet",
        "ABO",
        "RESOLVED",
        value="A",
        raw="A",
        reason="printed field",
        source=s.PRINTED,
    )
    fact(con, "sheet", "RH", "RESOLVED", value="POSITIVE", reason="printed field", source=s.PRINTED)
    fact(con, "sheet", "A", "RESOLVED", value="A*02", reason="row rule", source=None)
    fact(con, "sheet", "ROLE", "RESOLVED", value="DONOR", reason="caption", source="CAPTION_CLAIM")
    fact(con, "single", "ABO", "RESOLVED", value="O", reason="printed field", source=s.PRINTED)
    fact(con, "sheet2", "ABO", "RESOLVED", value="B", reason="caption", source="CAPTION_CLAIM")
    con.execute("INSERT INTO document VALUES ('sheet2', ?, 'c.jpg', 1, '')", (EV,))
    tally = s.run(con, dry_run=True)
    assert tally["documents"] == 1 and tally["ABO printed on a comparison sheet"] == 1
    s.run(con, dry_run=False)
    assert row(con, "sheet", "ABO") == (
        "REVIEW_REQUIRED",
        None,
        "A",
        s.REASON.format(value="A", old="printed field"),
        f"{s.PRINTED}|{s.TAG}",
    )
    assert row(con, "sheet", "RH")[:3] == ("REVIEW_REQUIRED", None, "POSITIVE")
    assert row(con, "sheet", "A")[0] == "RESOLVED", "an HLA cell was touched"
    assert row(con, "sheet", "ROLE")[0] == "RESOLVED"
    assert row(con, "single", "ABO")[0] == "RESOLVED", "a one-person page was touched"
    assert row(con, "sheet2", "ABO")[0] == "RESOLVED", (
        "a caption claim was touched (D1 decides those)"
    )
    assert s.undo(con) == 2
    assert row(con, "sheet", "ABO") == ("RESOLVED", "A", "A", "printed field", s.PRINTED)
    assert row(con, "sheet", "RH")[:2] == ("RESOLVED", "POSITIVE")
