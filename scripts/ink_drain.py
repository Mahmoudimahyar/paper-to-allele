#!/usr/bin/env python3
"""Retire the review items whose printed cell is measured blank.

14,060 HLA cells corpus-wide carry a readable locus label, no box any row rule
could bind, and an ink measurement (`cell_ink_pass.py`, `cell-ink/v1`) that
says the cell is paper. `cell_ink_pass` deliberately wrote no fact: the
authority to retire a review item was a person's, not a measurement's. On the
labelled cells the measure was right 74 of 76 times, and the operator took the
decision (D3-a, 2026-09-07): an empty printed cell is NOT_TESTED — the status
HA-009 gives a (family, locus) a laboratory never fills — and it leaves the
review queue.

Gates, each the narrowest it can be:

* status REVIEW_REQUIRED with the row rules' own reason, `anchor found but no
  box…`: nothing another pass has touched, nothing that ever held a value;
* an ink row for the cell whose decision is BLANK. INKED and UNMEASURABLE stay
  in review, and so does a cell with no measurement at all;
* the old reason is kept inside the new one, and `source` gains `|ink-drain/v1`,
  so `--undo` restores every row in one statement and the review pack can show
  the group as its own stratum.

`--dry-run` is the DEFAULT. Pass `--no-dry-run` to write.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EV = "facts/v1"
TAG = "ink-drain/v1"
ROW_RULE_REASON = "anchor found but no box"
WAS = "; was: "


def candidates(con: sqlite3.Connection) -> list[tuple]:
    return con.execute(
        "SELECT f.sha256, f.field, f.reason, f.source, i.ink_version, i.fraction, i.coverage "
        "FROM fact f JOIN cell_ink i ON i.sha256=f.sha256 AND i.field=f.field "
        "AND i.extraction_version=f.extraction_version "
        "WHERE f.extraction_version=? AND f.status='REVIEW_REQUIRED' AND f.reason LIKE ? "
        "AND i.decision='BLANK' AND (f.source IS NULL OR f.source NOT LIKE ?)",
        (EV, f"{ROW_RULE_REASON}%", f"%{TAG}"),
    ).fetchall()


def drained_reason(
    old: str, ink_version: str, fraction: float | None, coverage: float | None
) -> str:
    ink = "n/a" if fraction is None else f"{fraction:.3f}"
    cov = "n/a" if coverage is None else f"{coverage:.2f}"
    return (
        f"printed label, cell measured blank ({ink_version}: ink {ink}, coverage {cov}); "
        f"drained by decision D3-a 2026-09-07, the measure right on 74 of 76 labelled cells"
        f"{WAS}{old}"
    )


def run(con: sqlite3.Connection, *, dry_run: bool) -> Counter[str]:
    tally: Counter[str] = Counter()
    picks = candidates(con)
    tally["blank printed cells in review"] = len(picks)
    for _, field, *_ in picks:
        tally[f"  {field}"] += 1
    if dry_run:
        return tally
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    for sha, field, reason, source, ink_version, fraction, coverage in picks:
        con.execute(
            "UPDATE fact SET status='NOT_TESTED', reason=?, source=?, created_utc=? "
            "WHERE sha256=? AND field=? AND extraction_version=?",
            (
                drained_reason(reason or "", ink_version, fraction, coverage),
                f"{source}|{TAG}" if source else TAG,
                now,
                sha,
                field,
                EV,
            ),
        )
    con.commit()
    return tally


def undo(con: sqlite3.Connection) -> int:
    """Put every drained row back into review with the reason it had."""
    rows = con.execute(
        "SELECT sha256, field, reason, source FROM fact WHERE extraction_version=? "
        "AND status='NOT_TESTED' AND source LIKE ?",
        (EV, f"%{TAG}"),
    ).fetchall()
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    for sha, field, reason, source in rows:
        old = (reason or "").split(WAS, 1)[1] if WAS in (reason or "") else ROW_RULE_REASON
        base = (source or "").replace(f"|{TAG}", "").replace(TAG, "")
        con.execute(
            "UPDATE fact SET status='REVIEW_REQUIRED', reason=?, source=?, created_utc=? "
            "WHERE sha256=? AND field=? AND extraction_version=?",
            (old, base or None, now, sha, field, EV),
        )
    con.commit()
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--no-dry-run", action="store_true", help="write; the default only counts")
    parser.add_argument("--undo", action="store_true", help="return every drained row to review")
    args = parser.parse_args()
    con = sqlite3.connect(args.facts)
    if args.undo:
        print(f"undone: {undo(con):,} rows back to review")
        return 0
    tally = run(con, dry_run=not args.no_dry_run)
    for key, count in tally.most_common():
        print(f"{count:>7,}  {key}")
    print("(dry run; nothing written)" if not args.no_dry_run else "written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
