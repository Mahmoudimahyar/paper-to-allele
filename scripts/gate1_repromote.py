#!/usr/bin/env python3
"""Re-promote the gate-1 withdrawals that two independent engines agree on.

`precision_gates.py` gate 1 withdrew 1,467 resolved HLA values to review because
each needed a glyph repair AND its reading changed under one-pixel jitter — a
class measured wrong 21% of the time against 0.4% for a clean, steady read.
That gate judged the primary engine's read alone. But every one of those cells
had already been re-read from the ORIGINAL image by three other engines
(`confirm_pass.py`), each on its own crop, and where two of those agree on a
value and none reads otherwise, the cell rests on independent evidence the gate
never weighed.

The operator's decision (D6-a, 2026-09-07): re-promote exactly that subset.

What "agree" means here — each clause is a gate, and `agreed_reading` is the
whole rule:

* at least TWO engine FAMILIES (`ppocrv5`, `ppocrv6`, `tesseract5`) returned
  CONFIRMED with an IDENTICAL, non-empty reading. A family's `@drbx` and
  `@proposal` variants are other passes judging other things and do not count;
* NO engine returned CONTRADICTED;
* no other engine offered a DIFFERENT non-empty reading. An UNCONFIRMED engine
  with nothing to say is an abstention; one with another reading is a dissent.

The restored value is the agreed reading, not the withdrawn primary read: the
withdrawal moved the primary's text into `raw` and the repaired value is gone,
and the agreed reading is what two engines actually saw. `source` drops the
gate's tag and gains `|gate1-repromote/v1`, so the group is findable, reviewable
as its own stratum, and withdrawable in one statement (`--undo`).

Measured on the live store, 2026-09-07: 1,467 gate-1 rows, of which 123 meet
all three gates. (An earlier count of 172 used a looser notion of "none
disagreeing" and is superseded by this one.)

`--dry-run` is the DEFAULT. Pass `--no-dry-run` to write.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from precision_gates import GATE_TAG, REASON_SPLIT  # noqa: E402

EV = "facts/v1"
TAG = "gate1-repromote/v1"
MIN_FAMILIES = 2
REASON = (
    "re-promoted from the gate-1 withdrawal: {n} independent engines read this same value "
    "from the cell and none read otherwise (D6-a, 2026-09-07)"
)


def family_of(confirmer_version: str) -> str | None:
    """`ppocrv5/en-mobile-rec` -> `ppocrv5`; a `@drbx` / `@proposal` variant -> None."""
    if "@" in confirmer_version:
        return None
    return confirmer_version.split("/", 1)[0]


def agreed_reading(verdicts: list[tuple[str, str, str | None]]) -> tuple[str, int] | None:
    """The value at least two engine families CONFIRMED identically, with no dissent.

    `verdicts` is `(confirmer_version, verdict, reading)` per engine. Returns
    `(reading, families)` only when every gate in the module docstring holds,
    else None.
    """
    confirmed: dict[str, set[str]] = defaultdict(set)  # reading -> families
    dissent = False
    others: list[str] = []
    for confirmer, verdict, reading in verdicts:
        family = family_of(confirmer)
        if family is None:
            continue
        text = (reading or "").strip()
        if verdict == "CONTRADICTED":
            dissent = True
        elif verdict == "CONFIRMED" and text:
            confirmed[text].add(family)
        elif text:
            others.append(text)
    if dissent or len(confirmed) != 1:
        return None
    ((reading, families),) = confirmed.items()
    if len(families) < MIN_FAMILIES:
        return None
    if any(other != reading for other in others):
        return None
    return reading, len(families)


def gate_one_rows(con: sqlite3.Connection) -> list[tuple[str, str, str | None]]:
    return con.execute(
        "SELECT sha256, field, source FROM fact WHERE extraction_version=? "
        "AND status='REVIEW_REQUIRED' AND source LIKE ? AND reason=?",
        (EV, f"%|{GATE_TAG}", REASON_SPLIT),
    ).fetchall()


def candidates(con: sqlite3.Connection) -> list[tuple[str, str, str | None, str, int]]:
    picks = []
    for sha, field, source in gate_one_rows(con):
        verdicts = con.execute(
            "SELECT confirmer_version, verdict, reading FROM confirmation "
            "WHERE sha256=? AND field=? AND extraction_version=?",
            (sha, field, EV),
        ).fetchall()
        agreed = agreed_reading(verdicts)
        if agreed is not None:
            picks.append((sha, field, source, agreed[0], agreed[1]))
    return picks


def run(con: sqlite3.Connection, *, dry_run: bool) -> Counter[str]:
    tally: Counter[str] = Counter()
    tally["gate-1 withdrawals"] = len(gate_one_rows(con))
    picks = candidates(con)
    tally["re-promoted"] = len(picks)
    for *_, families in picks:
        tally[f"agreed by {families} families"] += 1
    if dry_run:
        return tally
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    for sha, field, source, reading, families in picks:
        base = (source or "").replace(f"|{GATE_TAG}", "")
        con.execute(
            "UPDATE fact SET status='RESOLVED', value=?, reason=?, source=?, created_utc=? "
            "WHERE sha256=? AND field=? AND extraction_version=?",
            (
                reading,
                REASON.format(n=families),
                f"{base}|{TAG}" if base else TAG,
                now,
                sha,
                field,
                EV,
            ),
        )
    con.commit()
    return tally


def undo(con: sqlite3.Connection) -> int:
    """Put every re-promoted row back exactly as the gate left it."""
    rows = con.execute(
        "SELECT sha256, field, source FROM fact WHERE extraction_version=? AND source LIKE ?",
        (EV, f"%{TAG}"),
    ).fetchall()
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    for sha, field, source in rows:
        base = (source or "").replace(f"|{TAG}", "").replace(TAG, "")
        con.execute(
            "UPDATE fact SET status='REVIEW_REQUIRED', value=NULL, reason=?, source=?, "
            "created_utc=? WHERE sha256=? AND field=? AND extraction_version=?",
            (
                REASON_SPLIT,
                f"{base}|{GATE_TAG}" if base else f"OCR|{GATE_TAG}",
                now,
                sha,
                field,
                EV,
            ),
        )
    con.commit()
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--no-dry-run", action="store_true", help="write; the default only counts")
    parser.add_argument("--undo", action="store_true", help="withdraw every re-promoted row again")
    args = parser.parse_args()
    con = sqlite3.connect(args.facts)
    if args.undo:
        print(f"undone: {undo(con):,} rows back to the gate-1 withdrawal")
        return 0
    tally = run(con, dry_run=not args.no_dry_run)
    for key, count in tally.most_common():
        print(f"{count:>7,}  {key}")
    print("(dry run; nothing written)" if not args.no_dry_run else "written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
