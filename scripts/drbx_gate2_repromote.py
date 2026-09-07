#!/usr/bin/env python3
"""Give back the DRB3/4/5 calls gate 2 withdrew for a neighbour's damage.

`precision_gates.py` gate 2 withdraws EVERY DRB3/4/5 second-opinion call on a
page whose grouped header only the damage-tolerant pattern reads — 1,461 cells
on 614 pages. The argument was sound and the measurement behind it was real: a
header whose printed final `5` reads as a `3` certifies ABSENT for a gene the
form never enumerated, and a clinical negative may not rest on a glyph
substitution.

But the gate is charged per PAGE and the damage is per CELL. Measured against
the 21 of these cells a person has read (W2(c), 2026-09-07):

* **18 were right and 3 were wrong**, and all three wrong ones are cells whose
  own call rests on a damaged gene token — `DRBS` read for DRB5, `DR83` for
  DRB3. Not one cell with a cleanly spelled call was wrong.
* Requiring the whole PAGE to be free of damaged tokens would drop 18 to 12,
  and requiring the DRB1 check to positively agree would drop it to 16. Neither
  excludes a single error the token test does not already exclude.

So the rule here is the token test, plus an objection the project already
knows how to raise:

1. **the cell's own call must not rest on a damaged gene token.** `DRBS` and
   `DR83` are the S-for-5 and 8-for-B repairs, and a repair is not evidence on
   a page whose header was never cleanly read;
2. **the DRB1 <-> DRB3/4/5 check must not object.** It is asked about the row
   as it would stand AFTER this pass — the page's surviving RESOLVED genes plus
   the re-promotions — and only `FORBIDDEN_GENE_PRESENT` and
   `EXPECTED_GENE_ABSENT` stop a page. `NOT_CHECKABLE` does not: the check is
   silent whenever DRB1 was not read, and silence is not disagreement. It
   objects on 10 of the 1,117 cells that pass the token test, and an
   `EXPECTED_GENE_ABSENT` is precisely the wrong-ABSENT the gate exists for.

Yield, measured read-only on the live store: **1,107 cells on 553 pages** (844
ABSENT, 263 PRESENT). Withheld: 344 cells resting on a damaged token, 10 the
consistency check objects to.

The restore is exact. Gate 2 moved the value into `raw` where `raw` was empty
and left the gene token there where it was not, so an ABSENT comes back with
`raw` NULL and a PRESENT keeps the token it was read from — the state a full
re-extraction produces. `source` loses `|precision-gate/v1` and gains this
pass's tag, so the group is one statement to find, to review as its own
stratum, and to `--undo`.

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
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from precision_gates import GATE_TAG, REASON_HEADER  # noqa: E402

from kidneymatch.hla.drbx_consistency import ConsistencyOutcome, check_drb1_drbx  # noqa: E402

EV = "facts/v1"
TAG = "drbx-gate2-repromote/v1"
GENES = ("DRB3", "DRB4", "DRB5")
# The repairs. A call resting on one of these stays withdrawn: `DRBS` is the
# S-for-5 repair and `DR83` the 8-for-B one, and both of the measured errors
# among the 21 labelled withdrawals are `DRBS`.
DAMAGED_TOKENS = frozenset({"DRBS", "DR83"})
# Only an objection stops a page. Silence (NOT_CHECKABLE, which is what the
# check returns when DRB1 was not read) is not disagreement.
OBJECTIONS = frozenset(
    {
        ConsistencyOutcome.FORBIDDEN_GENE_PRESENT,
        ConsistencyOutcome.EXPECTED_GENE_ABSENT,
    }
)
REASON = (
    "re-promoted from the gate-2 withdrawal: this call does not rest on a repaired gene "
    "token, and the DRB1 row does not contradict the resulting DRB3/4/5 row "
    "(W2(c), 2026-09-07)"
)


def call_of(raw: str | None) -> str | None:
    """What this withdrawn cell asserted: PRESENT, ABSENT, or nothing legible.

    A withdrawn ABSENT carries `ABSENT` in `raw` because the withdrawal moved
    the value there; a withdrawn PRESENT carries the gene token it was read
    from, because `raw` already held that and the withdrawal kept it.
    """
    text = (raw or "").strip()
    if text == "ABSENT":
        return "ABSENT"
    if text == "PRESENT" or text.upper().startswith("DR") or text in DAMAGED_TOKENS:
        return "PRESENT"
    return None


def withdrawn_rows(con: sqlite3.Connection) -> list[tuple[str, str, str, str]]:
    marks = ",".join("?" * len(GENES))
    return con.execute(
        f"SELECT sha256, field, raw, source FROM fact WHERE extraction_version=? "
        f"AND field IN ({marks}) AND status='REVIEW_REQUIRED' AND reason=? AND source LIKE ?",
        (EV, *GENES, REASON_HEADER, f"%|{GATE_TAG}"),
    ).fetchall()


def drb1_first_fields(con: sqlite3.Connection) -> dict[str, list[str]]:
    return {
        sha: [part.split("*")[-1].split(":")[0] for part in (value or "").split() if part]
        for sha, value in con.execute(
            "SELECT sha256, value FROM fact WHERE extraction_version=? AND field='DRB1' "
            "AND status='RESOLVED'",
            (EV,),
        )
    }


def standing_calls(con: sqlite3.Connection, shas: set[str]) -> dict[str, dict[str, str]]:
    """The DRB3/4/5 calls that already stand on each page, withdrawals aside."""
    if not shas:
        return {}
    out: dict[str, dict[str, str]] = defaultdict(dict)
    marks = ",".join("?" * len(GENES))
    shamarks = ",".join("?" * len(shas))
    for sha, field, value in con.execute(
        f"SELECT sha256, field, value FROM fact WHERE extraction_version=? "
        f"AND field IN ({marks}) AND status='RESOLVED' AND sha256 IN ({shamarks})",
        (EV, *GENES, *shas),
    ):
        if value in ("PRESENT", "ABSENT"):
            out[sha][field] = value
    return out


def candidates(
    con: sqlite3.Connection,
) -> tuple[list[tuple[str, str, str, str, str]], Counter[str]]:
    """Every withdrawal this pass would restore, and why the rest are withheld.

    Returned rows are `(sha, field, raw, source, restored_value)`.
    """
    tally: Counter[str] = Counter()
    rows = withdrawn_rows(con)
    tally["gate-2 DRB3/4/5 withdrawals"] = len(rows)

    per_page: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for sha, field, raw, _source in rows:
        text = (raw or "").strip()
        call = call_of(text)
        if call is None:
            tally["withheld: the withdrawn call is not legible"] += 1
            continue
        if text in DAMAGED_TOKENS:
            tally["withheld: the call rests on a repaired gene token"] += 1
            continue
        per_page[sha].append((field, text, call))
    drb1 = drb1_first_fields(con)
    standing = standing_calls(con, set(per_page))
    sources = {(sha, field): source for sha, field, _, source in rows}

    picks: list[tuple[str, str, str, str, str]] = []
    for sha, cells in sorted(per_page.items()):
        # The row as it WOULD stand: what already survives on the page, plus
        # what this pass would put back. Asking about anything else would check
        # a row that never exists.
        row = dict(standing.get(sha, {}))
        for field, _, call in cells:
            row[field] = call
        present = {gene for gene, call in row.items() if call == "PRESENT"}
        absent = {gene for gene, call in row.items() if call == "ABSENT"}
        outcome = check_drb1_drbx(drb1.get(sha, []), present, absent).outcome
        if outcome in OBJECTIONS:
            tally[f"withheld: the DRB1 row objects ({outcome.value})"] += len(cells)
            continue
        for field, text, call in cells:
            picks.append((sha, field, text, sources[(sha, field)], call))
            tally[f"re-promoted: {call}"] += 1
    tally["pages re-promoted"] = len({sha for sha, *_ in picks})
    return picks, tally


def run(con: sqlite3.Connection, *, dry_run: bool) -> Counter[str]:
    picks, tally = candidates(con)
    if dry_run:
        return tally
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    for sha, field, raw, source, call in picks:
        base = (source or "").replace(f"|{GATE_TAG}", "")
        # An ABSENT had no `raw` before the withdrawal moved its value there;
        # a PRESENT keeps the gene token it was read from. Either way this is
        # the row a full re-extraction writes.
        restored_raw = None if raw == call else raw
        con.execute(
            "UPDATE fact SET status='RESOLVED', value=?, raw=?, reason=?, source=?, "
            "created_utc=? WHERE sha256=? AND field=? AND extraction_version=?",
            (call, restored_raw, REASON, f"{base}|{TAG}" if base else TAG, now, sha, field, EV),
        )
    con.commit()
    return tally


def undo(con: sqlite3.Connection) -> int:
    """Withdraw every re-promoted cell again, exactly as gate 2 left it."""
    rows = con.execute(
        "SELECT sha256, field, value, raw, source FROM fact WHERE extraction_version=? "
        "AND source LIKE ?",
        (EV, f"%{TAG}"),
    ).fetchall()
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    for sha, field, value, raw, source in rows:
        base = (source or "").replace(f"|{TAG}", "").replace(TAG, "")
        con.execute(
            "UPDATE fact SET status='REVIEW_REQUIRED', value=NULL, raw=COALESCE(?, ?), "
            "reason=?, source=?, created_utc=? "
            "WHERE sha256=? AND field=? AND extraction_version=?",
            (
                raw,
                value,
                REASON_HEADER,
                f"{base}|{GATE_TAG}" if base else GATE_TAG,
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
    parser.add_argument("--undo", action="store_true", help="withdraw every re-promoted cell again")
    args = parser.parse_args()
    con = sqlite3.connect(args.facts)
    if args.undo:
        print(f"undone: {undo(con):,} cells back to the gate-2 withdrawal")
        return 0
    tally = run(con, dry_run=not args.no_dry_run)
    for key, count in tally.most_common():
        print(f"{count:>7,}  {key}")
    print("(dry run; nothing written)" if not args.no_dry_run else "written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
