"""Reading our own boxes again with a better engine, and the rules for using it.

The primary text of this whole corpus comes from `crnn_mobilenet_v3_small`,
which scored 14 of 67 labelled value cells on the engine bench against
PP-OCRv6-medium's 65. The obvious move is to swap it, and the measurement says
not to: on the same boxes and the same rule, v6 scores 68 of 160 against the
shipped 67. It wins 8 and loses 7, and four of the losses are cells where **it
lost a locus label we had**, because `glyphs.py`'s repairs are calibrated on our
recognizer's measured confusions and do nothing for another engine's.

So the readings are kept side by side and the union taken. These tests hold the
three rules that make that safe: our labels survive, a cell we already read is
never re-read, and half a genotype may only be completed, never contradicted.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from rerecognise_pass import completes, incomplete, keep_our_labels  # noqa: E402


def test_our_locus_labels_survive_the_second_reading() -> None:
    """`DRBI` is read 3.5x more often than `DRB1`, and our repair knows it."""
    ours = ["HLA-DRBI", "15", "HLA-DOBI", "03"]
    fresh = ["HLA-DRB!", "15:01", "HLA-D0B1", "03:01"]
    assert keep_our_labels(ours, fresh) == ["HLA-DRBI", "15:01", "HLA-DOBI", "03:01"]


def test_the_second_reading_supplies_every_text_that_is_not_a_label() -> None:
    ours = ["", "8*44", "gibberish"]
    fresh = ["HLA-B", "B*44", "B*35"]
    assert keep_our_labels(ours, fresh) == ["HLA-B", "B*44", "B*35"]


def test_a_label_we_could_not_read_is_taken_from_the_second_reading() -> None:
    """Ours names no locus here, so there is nothing of ours to protect."""
    assert keep_our_labels(["JILA-", "24"], ["HLA-A", "A*24"]) == ["HLA-A", "A*24"]


def test_readings_of_unequal_length_do_not_misalign_the_boxes() -> None:
    """A text taken from the wrong index would name the wrong box's content."""
    assert keep_our_labels(["HLA-A", "24", "02"], ["HLA-A", "A*24"]) == ["HLA-A", "A*24"]


def test_a_second_allele_may_be_added_to_a_half_read_pair() -> None:
    assert completes("A*24", ["A*24", "A*02"])


def test_a_reading_that_replaces_the_allele_we_had_is_not_a_completion() -> None:
    """Two alleles neither of which we read is a contradiction for a person."""
    assert not completes("A*24", ["A*11", "A*02"])


def test_a_single_allele_does_not_complete_anything() -> None:
    assert not completes("A*24", ["A*24"])
    assert not completes("A*24", ["A*02"])


def test_completing_a_cell_that_held_nothing_is_refused() -> None:
    """This path exists to finish a pair, not to fill an empty cell."""
    assert not completes(None, ["A*24", "A*02"])
    assert not completes("", ["A*24", "A*02"])


def facts_with(tmp_path: Path, rows: list[tuple[str, str, str, str | None]]) -> Path:
    path = tmp_path / "facts.sqlite"
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE fact (sha256 TEXT, field TEXT, extraction_version TEXT, status TEXT, "
        "value TEXT, second_allele TEXT, rule_id TEXT)"
    )
    con.executemany(
        "INSERT INTO fact VALUES (?,?,'facts/v1',?,'x',?,NULL)",
        rows,
    )
    con.commit()
    con.close()
    return path


def test_only_half_read_pairs_are_offered_for_completion(tmp_path: Path) -> None:
    """A complete reading is never re-read; an abstention is another pass's job."""
    sha = "a" * 64
    facts = facts_with(
        tmp_path,
        [
            (sha, "A", "RESOLVED", "UNREAD"),
            (sha, "B", "RESOLVED", "READ"),
            (sha, "C", "REVIEW_REQUIRED", None),
        ],
    )
    con = sqlite3.connect(facts)
    offered = incomplete(con, {sha})
    con.close()
    assert offered == {sha: ["A"]}


def test_a_document_the_pass_never_read_is_not_offered(tmp_path: Path) -> None:
    facts = facts_with(tmp_path, [("b" * 64, "A", "RESOLVED", "UNREAD")])
    con = sqlite3.connect(facts)
    assert incomplete(con, set()) == {}
    con.close()
