"""Ordering review work by what a decision buys.

Runs on a synthetic facts database; nothing here touches the archive.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.task("REVIEW-001")

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/review_queue.py"


def load():
    spec = importlib.util.spec_from_file_location("km_review_queue", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["km_review_queue"] = module
    spec.loader.exec_module(module)
    return module


def synthetic(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE fact (sha256, field, status, reason, stability, value);
        CREATE TABLE decode (sha256, field, verdict, jitter_readings);
        CREATE TABLE confirmation (sha256, field, verdict);
        """
    )
    # A: a document one cell short of a matchable record.
    for locus in ("B", "C", "DRB1", "DQB1"):
        con.execute(
            "INSERT INTO fact VALUES ('a', ?, 'RESOLVED', NULL, 'UNANIMOUS', 'x')", (locus,)
        )
    con.execute("INSERT INTO fact VALUES ('a', 'ROLE', 'RESOLVED', NULL, NULL, 'DONOR')")
    con.execute("INSERT INTO fact VALUES ('a', 'A', 'REVIEW_REQUIRED', 'no anchor', NULL, NULL)")
    # B: an unstable accepted value, split two ways.
    con.execute("INSERT INTO fact VALUES ('b', 'A', 'RESOLVED', NULL, 'SPLIT', 'A*11')")
    con.execute(
        "INSERT INTO decode VALUES ('b', 'A', 'SPLIT', ?)",
        (json.dumps({"0:11": 7, "0:17": 2}),),
    )
    # C: an accepted value a second reader disputes.
    con.execute("INSERT INTO fact VALUES ('c', 'A', 'RESOLVED', NULL, 'SPLIT', 'A*02')")
    con.execute("INSERT INTO confirmation VALUES ('c', 'A', 'CONTRADICTED')")
    # D: boxes on the row, refused.
    con.execute(
        "INSERT INTO fact VALUES ('d', 'A', 'REVIEW_REQUIRED', "
        "'3 candidate values exceeds max_values=2', NULL, NULL)"
    )
    # E: nothing to go on.
    con.execute("INSERT INTO fact VALUES ('e', 'A', 'REVIEW_REQUIRED', 'no anchor', NULL, NULL)")
    con.commit()
    con.close()


def tiers(items) -> dict[str, int]:
    return {item.sha256: item.tier for item in items}


def test_the_queue_is_ordered_by_what_a_decision_buys(tmp_path: Path) -> None:
    module = load()
    database = tmp_path / "facts.sqlite"
    synthetic(database)
    items = module.build(database, set())
    assigned = tiers(items)
    assert assigned["a"] == 1, "completes a matchable record"
    assert assigned["b"] == 2, "unstable reading"
    assert assigned["c"] == 3, "the readers disagree"
    assert assigned["d"] == 4, "boxes on the row"
    assert assigned["e"] == 5
    assert [item.tier for item in items] == sorted(item.tier for item in items)


def test_an_accepted_value_the_readers_dispute_is_review_work(tmp_path: Path) -> None:
    """It is in the database right now, and one of the two readers is wrong.
    Queueing only the refused cells would leave every disputed value unread."""
    module = load()
    database = tmp_path / "facts.sqlite"
    synthetic(database)
    items = module.build(database, set())
    disputed = [item for item in items if item.sha256 == "c"]
    assert disputed and disputed[0].status == "RESOLVED"


def test_a_cell_someone_already_read_is_not_queued_again(tmp_path: Path) -> None:
    """Two people spending an afternoon on the same rows is the cheapest
    mistake here to make and the easiest to avoid."""
    module = load()
    database = tmp_path / "facts.sqlite"
    synthetic(database)
    everything = module.build(database, set())
    already = {everything[0].cell_id}
    assert len(module.build(database, already)) == len(everything) - 1


def test_a_three_way_split_is_not_offered_as_a_choice(tmp_path: Path) -> None:
    """Two readings is a click. Three is a transcription, and pretending
    otherwise puts a reader in front of a control that cannot express what they
    can see."""
    module = load()
    assert module._two_way(json.dumps({"0:11": 5, "0:17": 3})) is True
    assert module._two_way(json.dumps({"0:11": 4, "0:17": 3, "0:13": 2})) is False
    assert module._two_way(None) is False
    assert module._two_way("{not json") is False


def test_the_queue_changes_no_fact(tmp_path: Path) -> None:
    """It orders work. Resolving a cell is a person's job."""
    body = SCRIPT.read_text(encoding="utf-8")
    for statement in ("UPDATE fact", "INSERT INTO fact", "DELETE FROM fact"):
        assert statement not in body
