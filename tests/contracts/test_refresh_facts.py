"""Re-extracting in place must neither forget nor misremember a check.

A replaced fact row's `stability` falls back to NOT_CHECKED, and the decode
and confirm passes resume by their own tables. Without reconciliation an
unchanged cell would read NOT_CHECKED forever and a changed cell would keep a
verdict about a reading it no longer holds.

Synthetic databases only; nothing here touches the corpus.
"""

from __future__ import annotations

import importlib.util
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.task("OCR-001")

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/refresh_facts.py"

FACT_COLUMNS = (
    "sha256, field, extraction_version, status, value, raw, repaired, second_allele, reason, "
    "rule_id, anchor_box, value_boxes, source, engine_version, preproc_version, imgt_version, "
    "created_utc, stability"
)


def load():
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("km_refresh_facts", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def build(path: Path, rows: list[tuple[str, str, str, str | None, str | None, str]]) -> None:
    """rows: (sha, field, status, value, value_boxes, stability)."""
    con = sqlite3.connect(path)
    con.executescript(
        f"""
        CREATE TABLE fact ({FACT_COLUMNS});
        CREATE TABLE decode (sha256, field, extraction_version, decoder_version, verdict,
            reading, jitter_readings, grammar_cost, created_utc);
        CREATE TABLE confirmation (sha256, field, extraction_version, confirmer_version,
            verdict, reading, created_utc);
        """
    )
    for sha, field, status, value, boxes, stability in rows:
        con.execute(
            f"INSERT INTO fact ({FACT_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                sha,
                field,
                "facts/v1",
                status,
                value,
                value,
                0,
                "READ",
                None,
                "r",
                None,
                boxes,
                "OCR",
                "e",
                "p",
                "3620",
                "t",
                stability,
            ),
        )
        con.execute(
            "INSERT INTO decode VALUES (?,?,?,?,?,?,?,?,?)",
            (sha, field, "facts/v1", "ctc-viterbi/v1", "UNANIMOUS", "11", "{}", 0.0, "t"),
        )
        con.execute(
            "INSERT INTO confirmation VALUES (?,?,?,?,?,?,?)",
            (sha, field, "facts/v1", "tesseract5/psm7-alnum", "CONFIRMED", "11", "t"),
        )
    con.commit()
    con.close()


def test_reconcile_keeps_checks_for_unchanged_cells_and_drops_them_for_changed_ones(
    tmp_path: Path,
) -> None:
    module = load()
    before = tmp_path / "before.sqlite"
    build(
        before,
        [
            (
                "s",
                "A",
                "RESOLVED",
                "A*02 A*11",
                "[[0.2,0.5,0.3,0.53],[0.4,0.5,0.5,0.53]]",
                "UNANIMOUS",
            ),
            ("s", "B", "RESOLVED", "B*44", "[[0.2,0.6,0.3,0.63]]", "SPLIT"),
            ("s", "C", "REVIEW_REQUIRED", None, "[[0.2,0.7,0.3,0.73]]", "NOT_CHECKED"),
        ],
    )
    # "After re-extraction": A unchanged, B gained its second allele, C now
    # resolves, and DRB1 is new. Every stability is back at the default.
    after = tmp_path / "after.sqlite"
    build(
        after,
        [
            (
                "s",
                "A",
                "RESOLVED",
                "A*02 A*11",
                "[[0.2,0.5,0.3,0.53],[0.4,0.5,0.5,0.53]]",
                "NOT_CHECKED",
            ),
            (
                "s",
                "B",
                "RESOLVED",
                "B*44 B*52",
                "[[0.2,0.6,0.3,0.63],[0.6,0.6,0.7,0.63]]",
                "NOT_CHECKED",
            ),
            ("s", "C", "RESOLVED", "C*07", "[[0.2,0.7,0.3,0.73]]", "NOT_CHECKED"),
            ("s", "DRB1", "RESOLVED", "DRB1*15", "[[0.2,0.8,0.3,0.83]]", "NOT_CHECKED"),
        ],
    )
    tally = module.reconcile(after, before)
    assert tally["unchanged cells, stability restored"] == 1
    assert tally["cells changed or new"] == 3

    con = sqlite3.connect(after)
    stability = dict(con.execute("SELECT field, stability FROM fact"))
    decoded = {row[0] for row in con.execute("SELECT field FROM decode")}
    confirmed = {row[0] for row in con.execute("SELECT field FROM confirmation")}
    con.close()
    assert stability == {
        "A": "UNANIMOUS",
        "B": "NOT_CHECKED",
        "C": "NOT_CHECKED",
        "DRB1": "NOT_CHECKED",
    }
    # The unchanged cell keeps its verdicts; every changed cell will be re-examined.
    assert decoded == {"A"}
    assert confirmed == {"A"}


def test_snapshot_is_a_faithful_copy(tmp_path: Path) -> None:
    module = load()
    facts = tmp_path / "facts.sqlite"
    build(facts, [("s", "A", "RESOLVED", "A*02", "[[0.2,0.5,0.3,0.53]]", "UNANIMOUS")])
    backup = module.snapshot(facts)
    assert backup.exists() and backup != facts
    a = sqlite3.connect(facts).execute("SELECT * FROM fact").fetchall()
    b = sqlite3.connect(backup).execute("SELECT * FROM fact").fetchall()
    assert a == b
    shutil.rmtree(tmp_path, ignore_errors=True)
