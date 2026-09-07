#!/usr/bin/env python3
"""Send the printed blood group on a two-person page to review.

66 documents are comparison sheets — one page printing a donor and a recipient
side by side — and carry a RESOLVED ABO and Rh read from the page's own printed
field. `fact` is keyed `(sha256, field, extraction_version)` with no subject,
so that value stands for the PAGE, and a blood group that belongs to one of two
people cannot be recorded for either (HA-018). The operator's decision (D4-b,
2026-09-07): those values go to REVIEW_REQUIRED, the value kept as the proposal
the reviewer sees, until a person reads the page or the model gains a subject.

Caption-claimed groups on the same pages are NOT touched here. A caption is a
statement about the poster, and what it may say about a two-person page was
decided separately (D1).

The old reason and the withdrawn value are kept inside the new reason and
`source` gains `|sheet-review/v1`, so `--undo` restores every row in one
statement and the review pack can show the group as its own stratum.

`--dry-run` is the DEFAULT. Pass `--no-dry-run` to write.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EV = "facts/v1"
TAG = "sheet-review/v1"
PRINTED = "LABORATORY_PRINTED"
FIELDS = ("ABO", "RH")
REASON = (
    "this page prints two subjects; a printed blood group cannot be attributed to one of "
    "them (HA-018, decision D4-b 2026-09-07); value was: {value}; was: {old}"
)
_UNDO = re.compile(r"value was: (?P<value>[^;]*); was: (?P<old>.*)$", re.S)


def candidates(con: sqlite3.Connection) -> list[tuple]:
    marks = ",".join("?" * len(FIELDS))
    return con.execute(
        f"SELECT f.sha256, f.field, f.value, f.reason FROM fact f "
        f"JOIN document d ON d.sha256=f.sha256 AND d.extraction_version=f.extraction_version "
        f"WHERE f.extraction_version=? AND d.comparison_sheet=1 AND f.field IN ({marks}) "
        f"AND f.status='RESOLVED' AND f.source=?",
        (EV, *FIELDS, PRINTED),
    ).fetchall()


def run(con: sqlite3.Connection, *, dry_run: bool) -> Counter[str]:
    tally: Counter[str] = Counter()
    picks = candidates(con)
    for _, field, *_ in picks:
        tally[f"{field} printed on a comparison sheet"] += 1
    tally["documents"] = len({sha for sha, *_ in picks})
    if dry_run:
        return tally
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    for sha, field, value, reason in picks:
        con.execute(
            "UPDATE fact SET status='REVIEW_REQUIRED', value=NULL, raw=COALESCE(raw, ?), "
            "reason=?, source=?, created_utc=? "
            "WHERE sha256=? AND field=? AND extraction_version=?",
            (
                value,
                REASON.format(value=value, old=reason or ""),
                f"{PRINTED}|{TAG}",
                now,
                sha,
                field,
                EV,
            ),
        )
    con.commit()
    return tally


def undo(con: sqlite3.Connection) -> int:
    """Put every withdrawn printed group back exactly as it was."""
    rows = con.execute(
        "SELECT sha256, field, reason FROM fact WHERE extraction_version=? AND source=?",
        (EV, f"{PRINTED}|{TAG}"),
    ).fetchall()
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    restored = 0
    for sha, field, reason in rows:
        found = _UNDO.search(reason or "")
        if not found:
            continue  # not this pass's wording; leave it for a person
        con.execute(
            "UPDATE fact SET status='RESOLVED', value=?, reason=?, source=?, created_utc=? "
            "WHERE sha256=? AND field=? AND extraction_version=?",
            (found.group("value"), found.group("old"), PRINTED, now, sha, field, EV),
        )
        restored += 1
    con.commit()
    return restored


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--no-dry-run", action="store_true", help="write; the default only counts")
    parser.add_argument("--undo", action="store_true", help="restore every withdrawn printed group")
    args = parser.parse_args()
    con = sqlite3.connect(args.facts)
    if args.undo:
        print(f"undone: {undo(con):,} printed groups restored")
        return 0
    tally = run(con, dry_run=not args.no_dry_run)
    for key, count in tally.most_common():
        print(f"{count:>7,}  {key}")
    print("(dry run; nothing written)" if not args.no_dry_run else "written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
