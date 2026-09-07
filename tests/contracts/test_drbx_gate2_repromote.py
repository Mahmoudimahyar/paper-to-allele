"""Which gate-2 DRB3/4/5 withdrawals come back, and which stay withdrawn.

The measured discriminator is the CELL's own token, not its page's: all three
errors among the 21 labelled withdrawals rest on a repaired token, and no cell
with a cleanly spelled call was wrong. Each test names a way this pass could
put back something untrue, and the round-trip is asserted exactly — a decision
a person may reverse has to be reversible.
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


def store(module) -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.executescript(
        """
        CREATE TABLE fact (sha256 TEXT, field TEXT, extraction_version TEXT, status TEXT,
            value TEXT, raw TEXT, reason TEXT, rule_id TEXT, source TEXT,
            created_utc TEXT DEFAULT '',
            PRIMARY KEY (sha256, field, extraction_version));
        """
    )
    return con


def withdrawn(con, module, sha, field, raw, *, source="drbx-reread+ppocrv6"):
    """A cell exactly as `precision_gates` gate 2 leaves it."""
    con.execute(
        "INSERT INTO fact (sha256, field, extraction_version, status, value, raw, reason, source) "
        "VALUES (?,?,?,'REVIEW_REQUIRED',NULL,?,?,?)",
        (sha, field, EV, raw, module.REASON_HEADER, f"{source}|{module.GATE_TAG}"),
    )


def drb1(con, sha, value):
    con.execute(
        "INSERT INTO fact (sha256, field, extraction_version, status, value) "
        "VALUES (?, 'DRB1', ?, 'RESOLVED', ?)",
        (sha, EV, value),
    )


def row(con, sha, field):
    return con.execute(
        "SELECT status, value, raw, reason, source FROM fact WHERE sha256=? AND field=?",
        (sha, field),
    ).fetchone()


def test_a_clean_call_comes_back_and_a_repaired_one_does_not() -> None:
    m = load("drbx_gate2_repromote")
    con = store(m)
    drb1(con, "p1", "DRB1*03 DRB1*15")  # expects DRB3 and DRB5
    withdrawn(con, m, "p1", "DRB3", "DRB3")  # clean token -> back as PRESENT
    withdrawn(con, m, "p1", "DRB4", "ABSENT")  # clean ABSENT -> back
    withdrawn(con, m, "p1", "DRB5", "DRBS")  # the S-for-5 repair -> stays
    tally = m.run(con, dry_run=True)
    assert tally["gate-2 DRB3/4/5 withdrawals"] == 3
    assert tally["withheld: the call rests on a repaired gene token"] == 1
    assert row(con, "p1", "DRB3")[0] == "REVIEW_REQUIRED", "a dry run wrote"

    m.run(con, dry_run=False)
    status, value, raw, reason, source = row(con, "p1", "DRB3")
    assert (status, value, raw) == ("RESOLVED", "PRESENT", "DRB3"), "the token is kept"
    assert source == f"drbx-reread+ppocrv6|{m.TAG}" and "does not rest on a repaired" in reason
    status, value, raw, _, _ = row(con, "p1", "DRB4")
    assert (status, value, raw) == ("RESOLVED", "ABSENT", None), (
        "an ABSENT had no raw before the withdrawal moved its value there"
    )
    assert row(con, "p1", "DRB5")[0] == "REVIEW_REQUIRED", "a repaired token was promoted"


def test_the_undo_restores_exactly_what_gate_two_wrote() -> None:
    m = load("drbx_gate2_repromote")
    con = store(m)
    drb1(con, "p1", "DRB1*03 DRB1*15")
    withdrawn(con, m, "p1", "DRB3", "DRB3")
    withdrawn(con, m, "p1", "DRB4", "ABSENT")
    before = {field: row(con, "p1", field) for field in ("DRB3", "DRB4")}
    m.run(con, dry_run=False)
    assert m.undo(con) == 2
    for field, was in before.items():
        assert row(con, "p1", field) == was, f"{field} did not round-trip"


def test_an_objecting_drb1_row_stops_the_whole_page() -> None:
    """`EXPECTED_GENE_ABSENT` is the wrong-ABSENT the gate exists for."""
    m = load("drbx_gate2_repromote")
    con = store(m)
    drb1(con, "p1", "DRB1*03 DRB1*03")  # expects DRB3
    withdrawn(con, m, "p1", "DRB3", "ABSENT")  # ... and the row calls it absent
    withdrawn(con, m, "p1", "DRB4", "ABSENT")
    tally = m.run(con, dry_run=True)
    assert tally["withheld: the DRB1 row objects (EXPECTED_GENE_ABSENT)"] == 2
    m.run(con, dry_run=False)
    assert row(con, "p1", "DRB3")[0] == "REVIEW_REQUIRED"
    assert row(con, "p1", "DRB4")[0] == "REVIEW_REQUIRED"


def test_silence_from_the_drb1_row_is_not_disagreement() -> None:
    """With no DRB1 read the check returns NOT_CHECKABLE, which must not stop it."""
    m = load("drbx_gate2_repromote")
    con = store(m)
    withdrawn(con, m, "p1", "DRB3", "DRB3")
    m.run(con, dry_run=False)
    assert row(con, "p1", "DRB3")[:2] == ("RESOLVED", "PRESENT")


def test_the_check_sees_the_row_that_would_stand_not_only_the_withdrawals() -> None:
    """A gene still RESOLVED on the page is part of the row being judged."""
    m = load("drbx_gate2_repromote")
    con = store(m)
    drb1(con, "p1", "DRB1*03 DRB1*03")  # one haplotype pair expecting DRB3
    con.execute(
        "INSERT INTO fact (sha256, field, extraction_version, status, value) "
        "VALUES ('p1','DRB3',?,'RESOLVED','ABSENT')",
        (EV,),
    )
    withdrawn(con, m, "p1", "DRB4", "ABSENT")
    tally = m.run(con, dry_run=True)
    assert tally["withheld: the DRB1 row objects (EXPECTED_GENE_ABSENT)"] == 1, (
        "the standing ABSENT on DRB3 is what the DRB1 row objects to"
    )


def test_only_gate_two_rows_are_touched() -> None:
    m = load("drbx_gate2_repromote")
    con = store(m)
    con.execute(
        "INSERT INTO fact (sha256, field, extraction_version, status, value, raw, reason, source) "
        "VALUES ('p1','DRB3',?,'REVIEW_REQUIRED',NULL,'DRB3','some other withdrawal','x|"
        + "precision-gate/v1')",
        (EV,),
    )
    con.execute(
        "INSERT INTO fact (sha256, field, extraction_version, status, value, raw, reason, source) "
        "VALUES ('p2','DRB4',?,'REVIEW_REQUIRED',NULL,'DRB4',?,'no-gate-tag')",
        (EV, m.REASON_HEADER),
    )
    tally = m.run(con, dry_run=False)
    assert tally["gate-2 DRB3/4/5 withdrawals"] == 0
    assert row(con, "p1", "DRB3")[0] == "REVIEW_REQUIRED"
    assert row(con, "p2", "DRB4")[0] == "REVIEW_REQUIRED"


def test_the_call_a_withdrawn_row_carried_is_read_from_its_raw() -> None:
    m = load("drbx_gate2_repromote")
    assert m.call_of("ABSENT") == "ABSENT"
    assert m.call_of("PRESENT") == "PRESENT"
    for token in ("DRB3", "DRB4", "DRB5", "DRB3/4", "DRB4,", "DRBS", "DR83"):
        assert m.call_of(token) == "PRESENT", token
    assert m.call_of("") is None
    assert m.call_of(None) is None
    assert m.call_of("47") is None
