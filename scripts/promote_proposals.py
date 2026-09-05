#!/usr/bin/env python3
"""Promote a decode PROPOSAL to a fact when an independent engine read the same.

`decode_pass.py` records a PROPOSAL for a cell the resolver refused because the
primary recognizer's text did not parse as an allele (`DQB1*OZ` for `DQB1*02`)
while the constrained decode read a valid value on all nine one-pixel offsets
with its digits intact. It never promotes one: a constrained decode turns ANY
crop into a grammatically valid allele, so on its own it is a guess wearing a
grammar. `confirm_pass.py --target proposals` then has PP-OCRv5 read the same
crop and judges it against the proposal. This script promotes exactly the cells
where the two agree.

Why that is a fact and not a best guess (ADR 0009 §7): the cell's locus came
from geometry and passed every gate before the parse (a label is not a value,
another anchor does not own the box, at most two candidates); the value is
admissible by construction (the decode's grammar is the IMGT first-field
vocabulary); and two independent recognizers read the same digits from the
same crop, which is the standard every RESOLVED cell is held to when its
confirmer agrees. Measured on the 187-cell labelled export: the pipeline's 4
proposals all equalled the reviewer's reading. The promoted fact is marked
`repaired`, its `source` names both engines, and its `reason` says what
happened, so the review pack shows it as a promotion and the golden gate can
score promotions apart.

Never on a LOW-quality page. Two engines that read the same digits from a
blurred crop share their failure, not their independence: of the two promotions
that landed on LOW pages before this gate, the one the reviewer had labelled was
wrong, and LOW pages split the decode twice as often as the rest (10 of 89
resolved cells against 5%). A promotion already made on such a page is
withdrawn to review by the same run.

Idempotent: a promoted cell is RESOLVED and no longer selected. Re-extraction
(`refresh_facts.py`) resets the cell to REVIEW_REQUIRED; run this again after.

Prints counts only. Output lands in gitignored `data/derived/facts.sqlite`.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kidneymatch.hla.vocabulary import FirstFieldVocabulary, load_vocabulary  # noqa: E402
from kidneymatch.ocr.confirm import Confirmation, confirm_value  # noqa: E402
from kidneymatch.ocr.glyphs import parse_allele_value  # noqa: E402

LOCI = ("A", "B", "C", "DRB1", "DQA1", "DQB1", "DPA1", "DPB1")
CONFIRMER = "ppocrv5/en-mobile-rec@proposal"
SOURCE = "decode+ppocrv5"
REASON = (
    "promoted: the primary text did not parse; the constrained decode read this value on "
    "all nine offsets with its digits intact, and PP-OCRv5 read the same from the same crop"
)
WITHHELD_REASON = (
    "promotion withheld: the constrained decode and PP-OCRv5 agree on a value the primary "
    "text did not parse, but the page is LOW quality, where the two share their failure"
)
# The quality band on which no proposal is promoted.
WITHHELD_BAND = "LOW"


def proposal_value(
    locus: str, reading: str, vocabulary: FirstFieldVocabulary | None = None
) -> str | None:
    """The proposal as a fact value, or None if it is not one this locus can hold.

    Admissibility is checked here again rather than trusted to the decode's
    grammar: the gate a resolved cell passes is the one a promoted cell passes.
    """
    vocabulary = vocabulary if vocabulary is not None else load_vocabulary()
    parts = [part for part in (reading or "").split() if part]
    if not 1 <= len(parts) <= 2:
        return None
    values: list[str] = []
    for part in parts:
        value = parse_allele_value(part)
        if value is None or value.locus_prefix not in (None, locus):
            return None
        if not vocabulary.covers(locus) or not vocabulary.is_admissible(locus, value.first_field):
            return None
        text = f"{locus}*{value.first_field}"
        if value.second_field:
            text += f":{value.second_field}"
        values.append(text)
    return " ".join(values)


def select_promotable(
    con: sqlite3.Connection, confirmer: str = CONFIRMER
) -> list[tuple[str, str, str]]:
    """(sha256, field, the proposal, the confirmer's reading) for every cell
    whose stored verdict says both engines agreed. The verdict was about the
    proposal stored WHEN it was judged; `promote` re-judges the confirmer's
    reading against the proposal it sees now, so a re-decoded cell is never
    promoted on a stale agreement."""
    placeholders = ",".join("?" * len(LOCI))
    return con.execute(
        "SELECT f.sha256, f.field, k.reading, c.reading FROM fact f "
        "JOIN document d ON d.sha256=f.sha256 AND d.extraction_version=f.extraction_version "
        "JOIN decode k ON k.sha256=f.sha256 AND k.field=f.field "
        "AND k.extraction_version=f.extraction_version "
        "JOIN confirmation c ON c.sha256=f.sha256 AND c.field=f.field "
        "AND c.extraction_version=f.extraction_version "
        f"WHERE f.status='REVIEW_REQUIRED' AND f.field IN ({placeholders}) "
        "AND f.reason LIKE '%does not parse%' "
        "AND (d.quality_band IS NULL OR d.quality_band != ?) "
        "AND k.verdict='PROPOSAL' AND k.decoder_version LIKE 'ctc-viterbi%' "
        "AND k.decoder_version NOT LIKE '%+frame%' "
        "AND c.confirmer_version=? AND c.verdict='CONFIRMED' "
        "ORDER BY f.sha256, f.field",
        (*LOCI, WITHHELD_BAND, confirmer),
    ).fetchall()


def withdraw_on_low_pages(con: sqlite3.Connection, *, dry_run: bool = False) -> int:
    """Promotions made on a LOW-quality page before the band gate existed go
    back to review, keeping their boxes; the reason says why."""
    rows = con.execute(
        "SELECT f.sha256, f.field FROM fact f JOIN document d ON d.sha256=f.sha256 "
        "AND d.extraction_version=f.extraction_version "
        "WHERE f.source=? AND f.status='RESOLVED' AND d.quality_band=?",
        (SOURCE, WITHHELD_BAND),
    ).fetchall()
    if rows and not dry_run:
        con.executemany(
            "UPDATE fact SET status='REVIEW_REQUIRED', value=NULL, repaired=0, "
            "second_allele='UNREAD', reason=?, source=NULL, stability='NOT_CHECKED' "
            "WHERE sha256=? AND field=? AND extraction_version='facts/v1'",
            [(WITHHELD_REASON, sha, field) for sha, field in rows],
        )
        con.commit()
    return len(rows)


def promote(facts_db: Path, *, dry_run: bool = False, confirmer: str = CONFIRMER) -> Counter[str]:
    con = sqlite3.connect(facts_db)
    tally: Counter[str] = Counter()
    updates: list[tuple[str, str, str, str, str]] = []
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    vocabulary = load_vocabulary()
    for sha, field, reading, confirmer_reading in select_promotable(con, confirmer):
        value = proposal_value(field, reading, vocabulary)
        if value is None:
            tally["proposal not a value of its locus"] += 1
            continue
        proposal = tuple(part for part in (reading or "").split() if part)
        if confirm_value(field, proposal, confirmer_reading or "", vocabulary) is not (
            Confirmation.CONFIRMED
        ):
            tally["confirmer's reading no longer matches the proposal"] += 1
            continue
        second = "READ" if len(value.split()) == 2 else "UNREAD"
        updates.append((value, second, sha, field, now))
        tally[f"promoted {field}"] += 1
    if not dry_run and updates:
        con.executemany(
            "UPDATE fact SET status='RESOLVED', value=?, repaired=1, second_allele=?, "
            "reason=?, source=?, stability='UNANIMOUS' "
            "WHERE sha256=? AND field=? AND extraction_version='facts/v1' "
            "AND status='REVIEW_REQUIRED'",
            [
                (value, second, REASON, SOURCE, sha, field)
                for value, second, sha, field, _ in updates
            ],
        )
        con.commit()
    withdrawn = withdraw_on_low_pages(con, dry_run=dry_run)
    if withdrawn:
        tally[f"withdrawn on {WITHHELD_BAND} pages"] += withdrawn
    con.close()
    return tally


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--dry-run", action="store_true", help="count, change nothing")
    args = parser.parse_args()
    if not args.facts.exists():
        print(f"missing {args.facts}")
        return 2
    tally = promote(args.facts, dry_run=args.dry_run)
    promoted = sum(n for key, n in tally.items() if key.startswith("promoted"))
    print(f"{'would promote' if args.dry_run else 'promoted'} {promoted:,} cells")
    for key, n in sorted(tally.items()):
        print(f"  {key:<40}{n:>8,}")
    if not args.dry_run:
        print("Each carries repaired=1, source=decode+ppocrv5 and a reason naming both engines.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
