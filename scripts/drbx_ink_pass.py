#!/usr/bin/env python3
"""Certify the empty slot of a one-token DRB3/4/5 row by its ink, or send it to review.

The grouped row (`kidneymatch.ocr.drbx`) reads one gene token on 6,122 cells
corpus-wide and leaves the other two genes UNKNOWN, because "the row printed
one gene" and "the row printed one gene and the other slot is empty" are
different claims: calling the slot empty because nothing was READ there was
wrong 5.9% of the time by the DRB1-concordance measurement. The reviewer's
labels showed the same thing from the other side — eight of those UNKNOWN
cells were rows where the second slot really was empty and the human said
ABSENT.

What separates the two claims is pixels. The DRB1 row directly above prints
its two alleles in the same two columns the grouped row uses for its gene
names, so its resolved value boxes place the row's second slot on the page
(`kidneymatch.ocr.ink.column_regions`); the slot is cut from the original
image, in the level frame on a ROTATE page, and its ink is measured with the
table rulings removed (`ink_measure`). Then:

* BLANK — paper: the other genes are ABSENT, a positive finding with the
  blank region as its provenance box and `source=ink-certified`.
* INKED — something is printed there that no engine read: the other genes go
  to REVIEW_REQUIRED, the same policy as a printed label whose cell could not
  be read. Nothing is guessed from the ink.
* UNMEASURABLE — no paper level (a shadow, a stamp), or no DRB1 geometry to
  place the slot: the cells stay exactly as the row rule left them.

The thresholds are calibrated on the columns that DO hold a read token (see
`BLANK_*` below). Idempotent; re-extraction (`refresh_facts.py`) resets the
cells and this pass is run again after it. Prints counts only.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kidneymatch.ocr.crops import RAW, prepare_crop  # noqa: E402
from kidneymatch.ocr.geometry import PageFrame  # noqa: E402
from kidneymatch.ocr.ink import InkMeasure, column_regions, ink_measure  # noqa: E402

INK_VERSION = "drbx-ink/v1"
SOURCE = "ink-certified"
GENES = ("DRB3", "DRB4", "DRB5")
ONE_TOKEN_REASON = "only one gene token read"
BLANK_REASON = (
    "the second slot of this row is paper: measured on the page with the rulings removed, "
    "in the column the DRB1 row above places it in"
)
INKED_REASON = (
    "the second slot of this row holds ink that no engine read; a printed gene the "
    "recognizer missed is a question for a person"
)

# The blank thresholds, calibrated 2026-09-05 on 4,904 columns holding a read
# gene token: none measured under 0.005 ink (2 under 0.01, 4,847 at 0.05 or
# more) and 8 under 0.2 column coverage. A slot is BLANK only when ALL three
# hold, each at least 2.5x under the least-inked read token. On the 2,674
# one-token rows measured, 2,141 other columns sat under 0.001 ink and 2,192
# under 0.05 coverage — paper — while 295 carried 0.02 or more: a token no
# engine read, which is the population the 5.9% came from. Both labelled rows
# the reviewer marked ABSENT measured under 0.001.
BLANK_FRACTION = 0.002
BLANK_COVERAGE = 0.05
BLANK_RUN = 6

SCHEMA = """
CREATE TABLE IF NOT EXISTS drbx_ink (
    sha256             TEXT NOT NULL,
    extraction_version TEXT NOT NULL,
    ink_version        TEXT NOT NULL,
    column_index       INTEGER NOT NULL,
    region             TEXT NOT NULL,
    fraction           REAL,
    coverage           REAL,
    longest_run        INTEGER,
    paper              REAL,
    decision           TEXT NOT NULL,
    created_utc        TEXT NOT NULL,
    PRIMARY KEY (sha256, extraction_version, ink_version)
);
"""


def decide(measure: InkMeasure | None) -> str:
    if measure is None:
        return "UNMEASURABLE"
    blank = (
        measure.fraction < BLANK_FRACTION
        and measure.coverage < BLANK_COVERAGE
        and measure.longest_run < BLANK_RUN
    )
    return "BLANK" if blank else "INKED"


def select_rows(con: sqlite3.Connection) -> list[dict[str, object]]:
    """One-token grouped rows whose page has DRB1 geometry to place the slot."""
    drb1: dict[str, list[list[float]]] = {}
    for sha, boxes in con.execute(
        "SELECT sha256, value_boxes FROM fact WHERE field='DRB1' AND status='RESOLVED' "
        "AND extraction_version='facts/v1' AND value_boxes IS NOT NULL"
    ):
        parsed = json.loads(boxes)
        if len(parsed) == 2:
            drb1[sha] = parsed
    rows: dict[str, dict[str, object]] = {}
    placeholders = ",".join("?" * len(GENES))
    for sha, field, status, value, boxes, reason, rel_path, frame, tilt in con.execute(
        "SELECT f.sha256, f.field, f.status, f.value, f.value_boxes, f.reason, d.rel_path, "
        "d.frame, d.tilt_deg FROM fact f JOIN document d ON d.sha256=f.sha256 "
        "AND d.extraction_version=f.extraction_version "
        f"WHERE f.field IN ({placeholders}) AND f.extraction_version='facts/v1' "
        "AND f.rule_id='GROUPED_DRBX/v1' ORDER BY f.sha256",
        GENES,
    ):
        row = rows.setdefault(
            sha,
            {
                "sha256": sha,
                "rel_path": rel_path,
                "frame": frame,
                "tilt": tilt,
                "present": [],
                "unknown": [],
            },
        )
        if value == "PRESENT" and boxes and status == "RESOLVED":
            row["present"].append(json.loads(boxes)[0])  # type: ignore[union-attr]
        elif status == "UNKNOWN" and ONE_TOKEN_REASON in (reason or ""):
            row["unknown"].append(field)  # type: ignore[union-attr]
    out = []
    for sha, row in rows.items():
        if len(row["present"]) == 1 and row["unknown"] and sha in drb1:  # type: ignore[arg-type]
            row["drb1"] = drb1[sha]
            out.append(row)
    return out


def run(
    facts_db: Path, export: Path, *, limit: int | None = None, dry_run: bool = False
) -> Counter[str]:
    from PIL import Image

    con = sqlite3.connect(facts_db)
    con.executescript(SCHEMA)
    rows = select_rows(con)
    if limit:
        rows = rows[:limit]
    tally: Counter[str] = Counter()
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    for row in rows:
        regions = column_regions(row["drb1"], row["present"])  # type: ignore[arg-type]
        empty = [r for r in regions if not r.occupied]
        if len(empty) != 1:
            tally["geometry does not place the token in one column"] += 1
            continue
        region = empty[0]
        source = export / str(row["rel_path"])
        try:
            image = np.asarray(Image.open(source).convert("L"))
        except OSError:
            tally["image unreadable"] += 1
            continue
        height, width = image.shape[:2]
        frame = None
        if row["frame"] == "ROTATE" and row["tilt"]:
            frame = PageFrame(float(row["tilt"]), width, height)  # type: ignore[arg-type]
        crop = prepare_crop(image, region.box, frame=frame, profile=RAW)
        measure = ink_measure(np.asarray(crop.pixels)) if crop is not None else None
        decision = decide(measure)
        tally[decision] += 1
        if dry_run:
            continue
        con.execute(
            "INSERT OR REPLACE INTO drbx_ink VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                row["sha256"],
                "facts/v1",
                INK_VERSION,
                region.column,
                json.dumps(list(region.box)),
                measure.fraction if measure else None,
                measure.coverage if measure else None,
                measure.longest_run if measure else None,
                measure.paper if measure else None,
                decision,
                now,
            ),
        )
        if decision == "BLANK":
            con.executemany(
                "UPDATE fact SET status='RESOLVED', value='ABSENT', reason=?, source=?, "
                "value_boxes=? WHERE sha256=? AND field=? AND extraction_version='facts/v1' "
                "AND status='UNKNOWN'",
                [
                    (BLANK_REASON, SOURCE, json.dumps([list(region.box)]), row["sha256"], gene)
                    for gene in row["unknown"]  # type: ignore[union-attr]
                ],
            )
        elif decision == "INKED":
            con.executemany(
                "UPDATE fact SET status='REVIEW_REQUIRED', reason=?, value_boxes=? "
                "WHERE sha256=? AND field=? AND extraction_version='facts/v1' AND status='UNKNOWN'",
                [
                    (INKED_REASON, json.dumps([list(region.box)]), row["sha256"], gene)
                    for gene in row["unknown"]  # type: ignore[union-attr]
                ],
            )
        con.commit()
    con.close()
    tally["rows examined"] = len(rows)
    return tally


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--export", type=Path, default=ROOT / "data/raw/ChatExport_2026-08-31")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true", help="measure and count, change nothing")
    args = parser.parse_args()
    if not args.facts.exists():
        print(f"missing {args.facts}")
        return 2
    tally = run(args.facts, args.export, limit=args.limit, dry_run=args.dry_run)
    print(
        f"{'measured' if args.dry_run else 'decided'} "
        f"{tally.pop('rows examined', 0):,} one-token rows"
    )
    for key, count in sorted(tally.items()):
        print(f"  {key:<48}{count:>8,}")
    print(
        "BLANK certifies the other genes ABSENT with the blank region as provenance; INKED sends "
        "them to review; UNMEASURABLE leaves them as the row rule did."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
