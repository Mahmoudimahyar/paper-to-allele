#!/usr/bin/env python3
"""Withdraw the two strata that hold most of the pipeline's wrong values.

1,342 human labels over four rounds leave 14 contradicted HLA cells. They are
not spread out. They concentrate in two measurable strata, and each of these
gates sends one stratum to a person instead of publishing it.

**Gate 1 — a glyph-repaired value whose reading changes under jitter.**
Splitting every resolved value cell by whether it needed a glyph repair and by
what the decode's one-pixel jitter said about it:

    clean    / UNANIMOUS    260 labelled    1 wrong    0.4%    44,066 corpus cells
    repaired / UNANIMOUS     79 labelled    2 wrong    2.5%     9,655
    repaired / SPLIT         19 labelled    4 wrong   21.1%     1,467

A value that had to be repaired AND that the decoder could not hold steady is
wrong one time in five, against a trustworthy core wrong one time in 250. It
holds 4 of the 8 allele contradictions.

**Gate 2 — a DRB3/4/5 presence call from an add-on source on a page whose
grouped header the recognizer damaged.** The two add-on sources
(`drbx-reread+ppocrv6`, `ink-certified`) are reached only through the
damage-tolerant header regex. Split by whether a cleanly spelled header also
exists on the page:

    clean header   + add-on    37 labelled    0 wrong
    damaged header + add-on    20 labelled    5 wrong   25%     1,461 corpus cells

The price, measured and stated plainly: roughly three correct readings go to
review for every wrong one withdrawn, in both gates. The operator was shown
that trade (CV_RESEARCH s17, s18) and instructed that all eight items on the
list be resolved; a 21% and a 25% error rate are "ambiguous critical OCR",
which the constitution sends to REVIEW_REQUIRED rather than best-guessing.

Nothing is deleted. The reading moves to `raw`, the status becomes
REVIEW_REQUIRED, the reason names the gate, and the reviewer sees the value as
a proposal with its crop. Every row this touches is marked so the whole group
can be found and restored if the next round of labels says the rate has moved.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

EV = "facts/v1"
VALUE_LOCI = ("A", "B", "C", "DRB1", "DQA1", "DQB1", "DPA1", "DPB1")
DRBX_LOCI = ("DRB3", "DRB4", "DRB5")
ADDON_SOURCES = ("drbx-reread+ppocrv6", "ink-certified")
GATE_TAG = "precision-gate/v1"
REASON_SPLIT = (
    "withdrawn to review: this value needed a glyph repair and its reading changed under "
    "one-pixel jitter; measured wrong 21% of the time against 0.4% for a clean, steady read"
)
REASON_HEADER = (
    "withdrawn to review: a DRB3/4/5 call from a second-opinion source on a page whose "
    "grouped header only the damage-tolerant pattern reads; measured wrong 25% of the time"
)
# The grouped header spelled the way the form prints it, with no glyph damage.
# Anything the damage-tolerant `GROUPED_DRBX_HEADER` reaches that this does not
# is a header the recognizer got wrong somewhere.
CLEAN_HEADER = re.compile(
    r"^\s*(?:HLA[\s\-]*)?DRB\s*3\s*[/,]?\s*4\s*[/,]?\s*5\s*[:.\-]?\s*$", re.IGNORECASE
)


def pages_with_clean_header(ocr: sqlite3.Connection, shas: set[str]) -> set[str]:
    clean: set[str] = set()
    for sha, rel, texts_json in ocr.execute(
        "SELECT sha256, rel_path, texts_json FROM ocr_result WHERE n_boxes>0"
    ):
        if sha not in shas or "_thumb" in rel:
            continue
        if any(CLEAN_HEADER.match((t or "").strip()) for t in json.loads(texts_json or "[]")):
            clean.add(sha)
    return clean


def split_targets(con: sqlite3.Connection) -> list[str]:
    """(sha, field) keys of every resolved value that is repaired AND split."""
    placeholders = ",".join("?" * len(VALUE_LOCI))
    return [
        f"{sha}:{field}"
        for sha, field in con.execute(
            f"SELECT sha256, field FROM fact WHERE extraction_version=? AND status='RESOLVED' "
            f"AND field IN ({placeholders}) AND repaired=1 AND stability='SPLIT'",
            (EV, *VALUE_LOCI),
        )
    ]


def header_targets(con: sqlite3.Connection, ocr: sqlite3.Connection) -> list[str]:
    """(sha, field) keys of every add-on DRBX call on a page with no clean header."""
    placeholders = ",".join("?" * len(DRBX_LOCI))
    sources = ",".join("?" * len(ADDON_SOURCES))
    rows = con.execute(
        f"SELECT sha256, field FROM fact WHERE extraction_version=? AND status='RESOLVED' "
        f"AND field IN ({placeholders}) AND source IN ({sources})",
        (EV, *DRBX_LOCI, *ADDON_SOURCES),
    ).fetchall()
    clean = pages_with_clean_header(ocr, {sha for sha, _ in rows})
    return [f"{sha}:{field}" for sha, field in rows if sha not in clean]


def withdraw(con: sqlite3.Connection, keys: list[str], reason: str, *, dry_run: bool) -> int:
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    done = 0
    for key in keys:
        sha, field = key.split(":", 1)
        row = con.execute(
            "SELECT value, source FROM fact WHERE sha256=? AND field=? AND extraction_version=?",
            (sha, field, EV),
        ).fetchone()
        if row is None:
            continue
        value, source = row
        done += 1
        if dry_run:
            continue
        # The value is kept, as the proposal the reviewer sees; the source keeps
        # its provenance and gains the gate's tag so the group can be found.
        con.execute(
            "UPDATE fact SET status='REVIEW_REQUIRED', value=NULL, raw=COALESCE(raw, ?), "
            "reason=?, source=?, created_utc=? "
            "WHERE sha256=? AND field=? AND extraction_version=?",
            (value, reason, f"{source or 'OCR'}|{GATE_TAG}", now, sha, field, EV),
        )
    return done


def run(facts: Path, ocr_db: Path, *, dry_run: bool) -> Counter[str]:
    con = sqlite3.connect(facts)
    ocr = sqlite3.connect(f"file:{ocr_db.as_posix()}?mode=ro", uri=True)
    tally: Counter[str] = Counter()
    split = split_targets(con)
    tally["gate 1: repaired and split under jitter"] = withdraw(
        con, split, REASON_SPLIT, dry_run=dry_run
    )
    header = header_targets(con, ocr)
    tally["gate 2: DRB3/4/5 add-on call on a damaged header"] = withdraw(
        con, header, REASON_HEADER, dry_run=dry_run
    )
    con.commit()
    con.close()
    ocr.close()
    return tally


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--ocr", type=Path, default=ROOT / "data/derived/ocr_pass.sqlite")
    parser.add_argument("--dry-run", action="store_true", help="count, change nothing")
    args = parser.parse_args()
    tally = run(args.facts, args.ocr, dry_run=args.dry_run)
    print(f"{'would withdraw' if args.dry_run else 'withdrew'} to review:")
    for name, count in tally.items():
        print(f"  {name:<52}{count:>7,}")
    print(
        "Measured: about three correct readings deferred per wrong one withdrawn. Nothing is "
        "deleted; the value stays in `raw` and the reviewer sees it as a proposal."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
