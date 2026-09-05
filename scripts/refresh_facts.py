#!/usr/bin/env python3
"""Re-extract the facts in place without forgetting what was already checked.

`extract_facts.py` writes every fact with `INSERT OR REPLACE`, and a replaced
row's `stability` falls back to NOT_CHECKED — by design: a re-extracted fact
has not been checked for stability. But the decode and confirm passes resume
by their OWN tables, keyed by (sha256, field), so after a re-extraction they
skip every cell they have seen before. Left there, an unchanged cell reads
NOT_CHECKED forever, and a cell whose value changed keeps a stability verdict
and a confirmation that were about a different reading.

This script does the re-extraction and then reconciles against a snapshot:

* a cell whose (status, value, boxes) are unchanged gets its stability back —
  the verdict was about exactly this reading;
* a cell whose reading changed loses its decode and confirmation rows, so the
  next `decode_pass.py` / `confirm_pass.py` examine it afresh.

The snapshot is kept beside the database. Output is PHI and stays under
gitignored `data/derived/`; the console prints counts only.

Usage:
    uv run --frozen --extra hist python scripts/refresh_facts.py
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))


def snapshot(facts: Path) -> Path:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    backup = facts.with_name(f"{facts.stem}.before-{stamp}{facts.suffix}")
    # Flush the WAL into the main file first, or the copy is stale.
    con = sqlite3.connect(facts)
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()
    shutil.copyfile(facts, backup)
    return backup


def reconcile(facts: Path, backup: Path, extraction_version: str = "facts/v1") -> Counter[str]:
    """Restore checks for unchanged cells; drop them for changed ones."""
    con = sqlite3.connect(facts)
    con.execute("ATTACH DATABASE ? AS before", (str(backup),))
    tally: Counter[str] = Counter()

    columns = {row[1] for row in con.execute("PRAGMA table_info(fact)")}
    if "stability" in columns:
        # The verdict was about exactly this reading: same status, value and
        # boxes. Anything else is a different reading and stays NOT_CHECKED.
        cur = con.execute(
            "UPDATE fact SET stability = ("
            "  SELECT b.stability FROM before.fact b"
            "  WHERE b.sha256 = fact.sha256 AND b.field = fact.field"
            "    AND b.extraction_version = fact.extraction_version"
            "    AND b.status = fact.status AND b.value IS fact.value"
            "    AND b.value_boxes IS fact.value_boxes)"
            " WHERE extraction_version = ? AND EXISTS ("
            "  SELECT 1 FROM before.fact b"
            "  WHERE b.sha256 = fact.sha256 AND b.field = fact.field"
            "    AND b.extraction_version = fact.extraction_version"
            "    AND b.status = fact.status AND b.value IS fact.value"
            "    AND b.value_boxes IS fact.value_boxes)",
            (extraction_version,),
        )
        tally["unchanged cells, stability restored"] = cur.rowcount

    changed = con.execute(
        "SELECT f.sha256, f.field FROM fact f LEFT JOIN before.fact b"
        "  ON b.sha256 = f.sha256 AND b.field = f.field"
        "  AND b.extraction_version = f.extraction_version"
        " WHERE f.extraction_version = ? AND ("
        "  b.sha256 IS NULL OR b.status != f.status OR b.value IS NOT f.value"
        "  OR b.value_boxes IS NOT f.value_boxes)",
        (extraction_version,),
    ).fetchall()
    tally["cells changed or new"] = len(changed)

    tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for table in ("decode", "confirmation"):
        if table not in tables:
            continue
        dropped = 0
        for sha, field in changed:
            dropped += con.execute(
                f"DELETE FROM {table} WHERE sha256 = ? AND field = ? AND extraction_version = ?",
                (sha, field, extraction_version),
            ).rowcount
        tally[f"{table} rows dropped for changed cells"] = dropped

    con.commit()
    con.execute("DETACH DATABASE before")
    con.close()
    return tally


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--src", type=Path, default=ROOT / "data/derived/ocr_pass.sqlite")
    parser.add_argument("--persian", type=Path, default=ROOT / "data/derived/persian_pass.sqlite")
    parser.add_argument(
        "--families", type=Path, default=ROOT / "data/derived/template_families.json"
    )
    parser.add_argument("--source", type=Path, default=ROOT / "data/derived/source.sqlite")
    parser.add_argument("--geometry", type=Path, default=ROOT / "data/derived/geometry.sqlite")
    parser.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args()

    import extract_facts  # noqa: PLC0415 - sibling script, not a package

    if not args.facts.exists():
        print(f"no facts database at {args.facts}; run scripts/extract_facts.py first")
        return 2
    backup = snapshot(args.facts)
    print(f"snapshot: {backup.name}")

    # A re-extraction replaces every row of the current version; the resume
    # set is emptied so that happens, and the snapshot is what makes it safe.
    con = sqlite3.connect(args.facts)
    con.execute(
        "DELETE FROM document WHERE extraction_version = ?", (extract_facts.EXTRACTION_VERSION,)
    )
    con.commit()
    con.close()

    rc = extract_facts.run(
        args.src,
        args.persian,
        args.families,
        args.facts,
        None,
        args.batch_size,
        args.source,
        args.geometry,
    )
    if rc != 0:
        print(f"extraction failed ({rc}); the snapshot {backup.name} is untouched")
        return rc

    tally = reconcile(args.facts, backup, extract_facts.EXTRACTION_VERSION)
    print("\nreconciled against the snapshot:")
    for key, count in tally.items():
        print(f"  {key:<44}{count:>9,}")
    print("\nnext: decode_pass.py and confirm_pass.py examine the changed cells.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
