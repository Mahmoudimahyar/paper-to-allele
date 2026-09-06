"""Boxes read off the whole page, and the rules for letting them bind a cell.

Every second opinion the pipeline had before this one was an opinion about OUR
boxes: a recognizer re-reading the crop our detector drew. It cannot help a
cell whose box was never drawn, which the reviewer put as "you are just feeding
them the cropped image, what if we give them the entire image?".

Measured on the 160 labelled non-DRB3/4/5 cells through the identical binding
rule, our detector is correct on 67 and a whole-page read on 63, and they
disagree in both directions: the whole page is right on 7 cells ours misses and
ours is right on 11 the whole page misses. Neither dominates, so the pass takes
the union. These tests pin the two halves of that: the geometry that comes back
from a page read, and the rule that our own reading is never overwritten.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from page_ocr_bind import LOCI, unresolved  # noqa: E402
from page_ocr_pass import read_page  # noqa: E402


class FakeEngine:
    """Stands in for PaddleOCR: returns what its pipeline returns."""

    def __init__(self, polygons, texts, scores=None):
        self.payload = {
            "rec_polys": polygons,
            "rec_texts": texts,
            "rec_scores": scores if scores is not None else [0.9] * len(texts),
        }

    def predict(self, input):  # noqa: A002 - the library's own keyword
        return [self.payload]


def box(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def test_a_polygon_becomes_a_normalised_box() -> None:
    engine = FakeEngine([box(100, 200, 300, 260)], ["HLA-A"])
    boxes, texts, _ = read_page(engine, None, 1000, 1000)
    assert boxes == [[0.1, 0.2, 0.3, 0.26]]
    assert texts == ["HLA-A"]


def test_a_rotated_polygon_becomes_its_enclosing_rectangle() -> None:
    """The rest of the pipeline speaks axis-aligned boxes and nothing else."""
    tilted = [[100, 200], [300, 190], [305, 250], [105, 260]]
    boxes, _, _ = read_page(FakeEngine([tilted], ["HLA-B"]), None, 1000, 1000)
    assert boxes == [[0.1, 0.19, 0.305, 0.26]]


def test_lines_come_back_in_reading_order() -> None:
    """Top to bottom, then left to right: the order the row rules walk in."""
    engine = FakeEngine(
        [box(600, 500, 700, 540), box(100, 100, 200, 140), box(100, 500, 200, 540)],
        ["third", "first", "second"],
    )
    _, texts, _ = read_page(engine, None, 1000, 1000)
    assert texts == ["first", "second", "third"]


def test_a_degenerate_polygon_is_dropped_with_its_text() -> None:
    """A dropped box must drop its word, or every later box names the wrong one."""
    engine = FakeEngine([box(100, 100, 100, 100), box(200, 200, 300, 240)], ["dropped", "kept"])
    boxes, texts, _ = read_page(engine, None, 1000, 1000)
    assert texts == ["kept"]
    assert len(boxes) == len(texts)


def test_a_page_with_no_text_reads_as_nothing_rather_than_failing() -> None:
    boxes, texts, scores = read_page(FakeEngine([], []), None, 1000, 1000)
    assert (boxes, texts, scores) == ([], [], [])


def test_a_page_of_unknown_size_yields_nothing() -> None:
    """Dividing by a zero dimension would put every box at the origin."""
    boxes, _, _ = read_page(FakeEngine([box(10, 10, 20, 20)], ["x"]), None, 0, 0)
    assert boxes == []


def facts_with(tmp_path: Path, rows: list[tuple[str, str, str]]) -> Path:
    path = tmp_path / "facts.sqlite"
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE fact (sha256 TEXT, field TEXT, extraction_version TEXT, status TEXT, "
        "rule_id TEXT)"
    )
    con.executemany(
        "INSERT INTO fact VALUES (?,?,'facts/v1',?,NULL)",
        [(sha, field, status) for sha, field, status in rows],
    )
    con.commit()
    con.close()
    return path


def test_only_cells_the_pipeline_left_unresolved_are_offered() -> None:
    """Our own reading always stands; the whole page is a fallback, not a rival."""
    import tempfile

    with tempfile.TemporaryDirectory() as name:
        tmp = Path(name)
        facts = facts_with(
            tmp,
            [
                ("a" * 64, "A", "RESOLVED"),
                ("a" * 64, "B", "REVIEW_REQUIRED"),
                ("a" * 64, "C", "UNKNOWN"),
            ],
        )
        con = sqlite3.connect(facts)
        offered = unresolved(con, {"a" * 64})
        con.close()
    assert sorted(offered["a" * 64]) == ["B", "C"]


def test_a_document_the_whole_page_pass_never_read_is_not_offered() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as name:
        facts = facts_with(Path(name), [("b" * 64, "A", "REVIEW_REQUIRED")])
        con = sqlite3.connect(facts)
        assert unresolved(con, set()) == {}
        con.close()


def test_the_grouped_drbx_genes_are_not_offered() -> None:
    """DRB3/4/5 come from the grouped row rule, never from this one."""
    assert "DRB3" not in LOCI
    assert "DRB4" not in LOCI
    assert "DRB5" not in LOCI
