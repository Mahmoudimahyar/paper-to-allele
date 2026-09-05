"""The confirm pass's three targets: which cells each reads, and how each judges.

Synthetic database and images only; the reader is injected, so no engine runs.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.task("BOOT-001")

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/confirm_pass.py"


def load():
    spec = importlib.util.spec_from_file_location("km_confirm_pass_targets", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["km_confirm_pass_targets"] = module
    spec.loader.exec_module(module)
    return module


BOX = json.dumps([[0.2, 0.2, 0.4, 0.3]])
TWO_BOXES = json.dumps([[0.2, 0.2, 0.4, 0.3], [0.5, 0.2, 0.7, 0.3]])


def corpus(tmp_path: Path, module) -> tuple[Path, Path]:  # type: ignore[no-untyped-def]
    from PIL import Image

    export = tmp_path / "export"
    export.mkdir()
    Image.new("L", (400, 300), 255).save(export / "page.jpg")
    db = tmp_path / "facts.sqlite"
    con = sqlite3.connect(db)
    con.executescript(module.SCHEMA)
    con.executescript(
        """
        CREATE TABLE document (sha256, rel_path);
        CREATE TABLE fact (sha256, field, extraction_version, status, value, reason,
            value_boxes, repaired);
        CREATE TABLE decode (sha256, field, extraction_version, decoder_version, verdict, reading);
        """
    )
    con.execute("INSERT INTO document VALUES ('doc', 'page.jpg')")
    rows = [
        # a resolved HLA cell: the default target
        ("doc", "A", "facts/v1", "RESOLVED", "A*02 A*24", None, TWO_BOXES),
        # a refused cell with a proposal: the proposals target, judged against the decode
        (
            "doc",
            "DQB1",
            "facts/v1",
            "REVIEW_REQUIRED",
            None,
            "candidate 'DQB1*OZ' does not parse as an allele value",
            TWO_BOXES,
        ),
        # a refused cell whose decode is SPLIT: never a proposal
        (
            "doc",
            "DRB1",
            "facts/v1",
            "REVIEW_REQUIRED",
            None,
            "candidate 'x' does not parse as an allele value",
            BOX,
        ),
        # a star-less refusal on an unmeasured form: a policy question, not read here
        (
            "doc",
            "B",
            "facts/v1",
            "REVIEW_REQUIRED",
            None,
            "candidate 'B35' names its locus without a star, and this form is not measured",
            BOX,
        ),
        # the DRB3/4/5 row: two present genes, one absent; DRB5 rests on the S->5 repair
        ("doc", "DRB3", "facts/v1", "RESOLVED", "PRESENT", None, BOX, 0),
        ("doc", "DRB5", "facts/v1", "RESOLVED", "PRESENT", None, BOX, 1),
        ("doc", "DRB4", "facts/v1", "RESOLVED", "ABSENT", None, None, 0),
    ]
    con.executemany(
        "INSERT INTO fact VALUES (?,?,?,?,?,?,?,?)",
        [row if len(row) == 8 else (*row, 0) for row in rows],
    )
    con.executemany(
        "INSERT INTO decode VALUES (?,?,?,?,?,?)",
        [
            ("doc", "DQB1", "facts/v1", "ctc-viterbi/v1+x", "PROPOSAL", "DQB1*02 DQB1*05"),
            ("doc", "DQB1", "facts/v1", "ctc-viterbi/v1+x+frame", "PROPOSAL", "DQB1*02 DQB1*05"),
            ("doc", "DRB1", "facts/v1", "ctc-viterbi/v1+x", "SPLIT", "DRB1*11"),
            ("doc", "A", "facts/v1", "ctc-viterbi/v1+x", "UNANIMOUS", "A*02 A*24"),
        ],
    )
    con.commit()
    con.close()
    return db, export


def test_each_target_selects_its_own_cells(tmp_path: Path) -> None:
    module = load()
    db, _ = corpus(tmp_path, module)
    con = sqlite3.connect(db)
    resolved = module.select_work(con, "resolved")
    proposals = module.select_work(con, "proposals")
    drbx = module.select_work(con, "drbx")
    assert [(r[1], r[2]) for r in resolved] == [("A", "A*02 A*24")]
    # one row per cell even though two decoder versions proposed: only the axis-aligned one
    assert [(r[1], r[2]) for r in proposals] == [("DQB1", "DQB1*02 DQB1*05")]
    assert sorted(r[1] for r in drbx) == ["DRB3", "DRB5"], "ABSENT has no box to read"
    with pytest.raises(ValueError):
        module.select_work(con, "everything")


def test_proposals_are_judged_against_the_decode_and_stored_apart(tmp_path: Path) -> None:
    module = load()
    db, export = corpus(tmp_path, module)

    def reader(images: list) -> list[str]:
        # one crop per value box: the second engine reads the proposal's digits
        return ["DQB1*02", "DQB1*05"][: len(images)]

    assert module.run(db, export, "", None, 10, "ppocrv5", "proposals", reader) == 0
    con = sqlite3.connect(db)
    rows = con.execute(
        "SELECT field, confirmer_version, verdict, reading FROM confirmation"
    ).fetchall()
    assert rows == [("DQB1", "ppocrv5/en-mobile-rec@proposal", "CONFIRMED", "DQB1*02 DQB1*05")]


def test_a_proposal_the_second_engine_reads_differently_is_contradicted(tmp_path: Path) -> None:
    module = load()
    db, export = corpus(tmp_path, module)
    assert (
        module.run(
            db, export, "", None, 10, "ppocrv5", "proposals", lambda images: ["DQB1*02", "DQB1*06"]
        )
        == 0
    )
    con = sqlite3.connect(db)
    assert con.execute("SELECT verdict FROM confirmation").fetchone() == ("CONTRADICTED",)


def test_gene_boxes_are_judged_by_name_and_stored_apart(tmp_path: Path) -> None:
    module = load()
    db, export = corpus(tmp_path, module)
    readings = iter(["DRB3", "DRB3"])  # the DRB5 box reads as DRB3: the repair was wrong

    def reader(images: list) -> list[str]:
        return [next(readings) for _ in images]

    assert module.run(db, export, "", None, 10, "ppocrv5", "drbx", reader) == 0
    con = sqlite3.connect(db)
    rows = dict(
        con.execute("SELECT field, verdict FROM confirmation WHERE confirmer_version LIKE '%@drbx'")
    )
    assert rows == {"DRB3": "CONFIRMED", "DRB5": "CONTRADICTED"}
    # the contradicted call rested on the S->5 repair: demoted, provenance kept
    status = dict(
        con.execute("SELECT field, status FROM fact WHERE field IN ('DRB3','DRB4','DRB5')")
    )
    assert status == {"DRB3": "RESOLVED", "DRB4": "RESOLVED", "DRB5": "REVIEW_REQUIRED"}
    demoted = con.execute(
        "SELECT value, repaired, value_boxes, reason FROM fact WHERE field='DRB5'"
    ).fetchone()
    assert demoted[0] is None and demoted[1] == 1 and demoted[2] == BOX
    assert "contradicted" in demoted[3]


def test_a_contradicted_clean_gene_token_stays_resolved(tmp_path: Path) -> None:
    """Without a repair the primary read the name outright; a disagreeing second
    engine is the review budget, not a demotion — as for every other cell."""
    module = load()
    db, export = corpus(tmp_path, module)
    readings = iter(["DRB4", "DRB5"])  # DRB3 (clean) read as DRB4; DRB5 (repaired) confirmed

    def reader(images: list) -> list[str]:
        return [next(readings) for _ in images]

    assert module.run(db, export, "", None, 10, "ppocrv5", "drbx", reader) == 0
    con = sqlite3.connect(db)
    status = dict(
        con.execute("SELECT field, status FROM fact WHERE field IN ('DRB3','DRB4','DRB5')")
    )
    assert status == {"DRB3": "RESOLVED", "DRB4": "RESOLVED", "DRB5": "RESOLVED"}
    verdicts = dict(
        con.execute("SELECT field, verdict FROM confirmation WHERE confirmer_version LIKE '%@drbx'")
    )
    assert verdicts == {"DRB3": "CONTRADICTED", "DRB5": "CONFIRMED"}


def test_rescore_leaves_the_target_verdicts_alone(tmp_path: Path) -> None:
    """A `@proposal` reading was judged against the decode's proposal, not the
    fact's value (the fact has none): re-judging it against the fact would
    flip every one of them to UNCONFIRMED."""
    module = load()
    db, export = corpus(tmp_path, module)
    module.run(
        db, export, "", None, 10, "ppocrv5", "proposals", lambda images: ["DQB1*02", "DQB1*05"]
    )
    module.run(db, export, "", None, 10, "ppocrv5", "drbx", lambda images: ["DRB3"] * len(images))
    assert module.rescore(db) == 0
    con = sqlite3.connect(db)
    verdicts = con.execute(
        "SELECT confirmer_version, verdict FROM confirmation ORDER BY 1"
    ).fetchall()
    assert ("ppocrv5/en-mobile-rec@proposal", "CONFIRMED") in verdicts
    assert ("ppocrv5/en-mobile-rec@drbx", "CONFIRMED") in verdicts
