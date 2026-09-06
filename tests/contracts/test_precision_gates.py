"""The two precision gates withdraw exactly their stratum, keep the evidence,
and can be run twice without touching anything the second time.

Each gate sends about three correct readings to review for every wrong one it
withdraws, so the tests here are about the gate touching ONLY what it says it
touches. A gate that reached one cell beyond its stratum would be paying that
price for nothing.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from precision_gates import (  # noqa: E402
    GATE_TAG,
    REASON_HEADER,
    REASON_SPLIT,
    run,
)

FACT_COLUMNS = (
    "sha256, field, extraction_version, status, value, raw, repaired, second_allele, reason, "
    "rule_id, anchor_box, value_boxes, source, engine_version, preproc_version, imgt_version, "
    "created_utc, stability"
)

SHA_CLEAN = "a" * 64  # page prints a clean grouped header
SHA_DAMAGED = "b" * 64  # page prints the header only in a damaged spelling


def fact(sha: str, field: str, *, repaired: int, stability: str, source: str | None) -> tuple:
    return (
        sha,
        field,
        "facts/v1",
        "RESOLVED",
        f"{field}*01 {field}*02",
        None,
        repaired,
        "READ",
        None,
        "row",
        None,
        None,
        source,
        "e",
        "p",
        "3620",
        "t",
        stability,
    )


def corpus(tmp_path: Path) -> tuple[Path, Path]:
    facts = tmp_path / "facts.sqlite"
    con = sqlite3.connect(facts)
    con.execute(f"CREATE TABLE fact ({FACT_COLUMNS})")
    rows = [
        # Gate 1 population and its neighbours.
        fact(SHA_CLEAN, "A", repaired=1, stability="SPLIT", source=None),  # withdrawn
        fact(SHA_CLEAN, "B", repaired=1, stability="UNANIMOUS", source=None),  # kept
        fact(SHA_CLEAN, "C", repaired=0, stability="SPLIT", source=None),  # kept
        fact(SHA_CLEAN, "DRB1", repaired=1, stability="DIGITS_LOST", source=None),  # kept
        # Gate 2 population and its neighbours.
        fact(SHA_CLEAN, "DRB3", repaired=0, stability="UNANIMOUS", source="ink-certified"),  # kept
        fact(SHA_DAMAGED, "DRB3", repaired=0, stability="UNANIMOUS", source="ink-certified"),
        fact(SHA_DAMAGED, "DRB4", repaired=0, stability="UNANIMOUS", source="drbx-reread+ppocrv6"),
        fact(
            SHA_DAMAGED, "DRB5", repaired=0, stability="UNANIMOUS", source=None
        ),  # core rule: kept
    ]
    con.executemany(f"INSERT INTO fact ({FACT_COLUMNS}) VALUES ({','.join('?' * 18)})", rows)
    con.commit()
    con.close()

    ocr = tmp_path / "ocr.sqlite"
    con = sqlite3.connect(ocr)
    con.execute("CREATE TABLE ocr_result (sha256, rel_path, n_boxes, texts_json)")
    con.executemany(
        "INSERT INTO ocr_result VALUES (?,?,?,?)",
        [
            (SHA_CLEAN, "photos/a.jpg", 2, json.dumps(["HLA-DRB3/4/5", "PRESENT"])),
            (SHA_DAMAGED, "photos/b.jpg", 2, json.dumps(["HLA-DR83/4S", "PRESENT"])),
            # A thumbnail row must not count as the page.
            (SHA_DAMAGED, "photos/b_thumb.jpg", 1, json.dumps(["HLA-DRB3/4/5"])),
        ],
    )
    con.commit()
    con.close()
    return facts, ocr


def status_of(facts: Path) -> dict[tuple[str, str], tuple]:
    con = sqlite3.connect(facts)
    out = {
        (sha, field): (status, value, raw, source, reason)
        for sha, field, status, value, raw, source, reason in con.execute(
            "SELECT sha256, field, status, value, raw, source, reason FROM fact"
        )
    }
    con.close()
    return out


def test_gate_one_withdraws_only_repaired_and_split(tmp_path: Path) -> None:
    facts, ocr = corpus(tmp_path)
    run(facts, ocr, dry_run=False)
    after = status_of(facts)
    assert after[(SHA_CLEAN, "A")][0] == "REVIEW_REQUIRED"
    for field in ("B", "C", "DRB1"):
        assert after[(SHA_CLEAN, field)][0] == "RESOLVED", field


def test_gate_two_withdraws_add_on_calls_only_where_no_clean_header_exists(tmp_path: Path) -> None:
    facts, ocr = corpus(tmp_path)
    run(facts, ocr, dry_run=False)
    after = status_of(facts)
    assert after[(SHA_CLEAN, "DRB3")][0] == "RESOLVED", "a clean header keeps the add-on call"
    assert after[(SHA_DAMAGED, "DRB3")][0] == "REVIEW_REQUIRED"
    assert after[(SHA_DAMAGED, "DRB4")][0] == "REVIEW_REQUIRED"
    assert after[(SHA_DAMAGED, "DRB5")][0] == "RESOLVED", "the core row rule is not an add-on"


def test_a_thumbnail_does_not_supply_the_clean_header(tmp_path: Path) -> None:
    """The damaged page's thumbnail row carries a clean spelling; it is not the
    page and must not rescue the call."""
    facts, ocr = corpus(tmp_path)
    run(facts, ocr, dry_run=False)
    assert status_of(facts)[(SHA_DAMAGED, "DRB3")][0] == "REVIEW_REQUIRED"


def test_the_evidence_is_kept_and_the_group_is_findable(tmp_path: Path) -> None:
    """Nothing is deleted: the reading moves to raw, the reason names the gate,
    and the source carries a tag so every withdrawn row can be found again."""
    facts, ocr = corpus(tmp_path)
    run(facts, ocr, dry_run=False)
    status, value, raw, source, reason = status_of(facts)[(SHA_CLEAN, "A")]
    assert value is None
    assert raw == "A*01 A*02"
    assert reason == REASON_SPLIT
    assert source.endswith(GATE_TAG)
    _, _, _, source2, reason2 = status_of(facts)[(SHA_DAMAGED, "DRB4")]
    assert reason2 == REASON_HEADER
    assert source2 == f"drbx-reread+ppocrv6|{GATE_TAG}"


def test_dry_run_changes_nothing_and_counts_the_same(tmp_path: Path) -> None:
    facts, ocr = corpus(tmp_path)
    before = status_of(facts)
    tally = run(facts, ocr, dry_run=True)
    assert status_of(facts) == before
    assert tally["gate 1: repaired and split under jitter"] == 1
    assert tally["gate 2: DRB3/4/5 add-on call on a damaged header"] == 2


def test_running_twice_touches_nothing_the_second_time(tmp_path: Path) -> None:
    """A withdrawn row is no longer RESOLVED, so it is outside both gates."""
    facts, ocr = corpus(tmp_path)
    run(facts, ocr, dry_run=False)
    once = status_of(facts)
    tally = run(facts, ocr, dry_run=False)
    assert status_of(facts) == once
    assert sum(tally.values()) == 0
