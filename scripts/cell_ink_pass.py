#!/usr/bin/env python3
"""Measure the ink of every printed locus cell the row rules found empty. Records only.

24,187 HLA cells corpus-wide carry a readable locus label and no box the row
rules could bind ("anchor found but no box"), most of them DQA1 and C.
`OCR_SPEC.md` sends such a cell to review, because a printed label whose cell
could not be read is a failure a person must see. Whether it is a read failure
or an empty cell is a question about pixels, and this pass asks it — and only
asks it. **It writes no fact.**

Why it may not: `NOT_TESTED` is HA-009's status for a (family, locus) pair a
laboratory measurably never fills, decided by a person from a committed
statistic (`config/locus_testing_rates.json`). Turning a per-page ink
measurement into that status would retire ~15,000 review items on a
calibration measured on cells a quarter the width, and the adversarial review
of 2026-09-05 found several ways for a row-wide region to read as paper when
it is not (a value stacked under its label, a shadow removed as a ruling, a
row band spanning two printed rows). The measurement is worth having; the
authority to retire a review item is not this pass's to take.

So it fills `cell_ink`: the region measured, its ink, and BLANK / INKED /
UNMEASURABLE. That is the evidence a person needs to extend HA-009 per page,
and the signal the review queue can order by — a cell whose paper is measured
is a cheap confirmation, a cell with ink no engine boxed is a real miss.

The cell is the ruled row around the label (`kidneymatch.ocr.lattice`), from
the label's right edge to the row's end; its ink is measured with the table
rulings removed (`kidneymatch.ocr.ink`), and a page whose own label the
measure cannot see certifies nothing (the control).

Idempotent, and re-measures what it measured before. Prints counts only.
Needs the geometry file for the rulings.
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
from kidneymatch.ocr.ink import classify, ink_measure  # noqa: E402
from kidneymatch.ocr.lattice import lattice_for, load_rulings  # noqa: E402
from kidneymatch.ocr.rulings import GEOMETRY_VERSION  # noqa: E402

INK_VERSION = "cell-ink/v1"
LOCI = ("A", "B", "C", "DRB1", "DQA1", "DQB1", "DPA1", "DPB1")
EMPTY_REASON = "anchor found but no box"
# The cell starts this far right of the label, in label heights, so the
# label's own trailing punctuation is not counted as the cell's ink.
LABEL_GAP_HEIGHTS = 0.3

SCHEMA = """
CREATE TABLE IF NOT EXISTS cell_ink (
    sha256             TEXT NOT NULL,
    field              TEXT NOT NULL,
    extraction_version TEXT NOT NULL,
    ink_version        TEXT NOT NULL,
    region             TEXT NOT NULL,
    fraction           REAL,
    coverage           REAL,
    longest_run        INTEGER,
    paper              REAL,
    decision           TEXT NOT NULL,
    created_utc        TEXT NOT NULL,
    PRIMARY KEY (sha256, field, extraction_version, ink_version)
);
"""


def select_cells(con: sqlite3.Connection) -> list[tuple[str, str, list[float], str, str, float]]:
    """(sha256, field, anchor box, image path, frame, tilt) for every empty labelled cell."""
    placeholders = ",".join("?" * len(LOCI))
    return [
        (sha, field, json.loads(abox), rel, frame, tilt)
        for sha, field, abox, rel, frame, tilt in con.execute(
            "SELECT f.sha256, f.field, f.anchor_box, d.rel_path, d.frame, d.tilt_deg "
            "FROM fact f JOIN document d ON d.sha256=f.sha256 "
            "AND d.extraction_version=f.extraction_version "
            f"WHERE f.field IN ({placeholders}) AND f.extraction_version='facts/v1' "
            "AND f.status='REVIEW_REQUIRED' AND f.reason LIKE ? "
            "AND f.anchor_box IS NOT NULL ORDER BY f.sha256, f.field",
            (*LOCI, EMPTY_REASON + "%"),
        )
    ]


def cell_region(anchor: list[float], lattice) -> tuple[float, float, float, float] | None:  # type: ignore[no-untyped-def]
    """The ruled row around the label, from just right of the label to the row's end."""
    height = anchor[3] - anchor[1]
    band = lattice.row_band((anchor[0] + anchor[2]) / 2, (anchor[1] + anchor[3]) / 2, height)
    if band is None:
        return None
    left = anchor[2] + LABEL_GAP_HEIGHTS * height
    if band.right - left < 2 * height:
        return None  # no room for a value: the label fills the row
    return (left, band.top, band.right, band.bottom)


def forget(con: sqlite3.Connection, sha: str, field: str, *, dry_run: bool = False) -> None:
    """Drop a measurement this run can no longer make.

    A cell the rulings placed yesterday and cannot place today (a new geometry
    version, a re-extracted anchor) must not keep yesterday's answer: the table
    says what the CURRENT run measured, or says nothing.
    """
    if dry_run:
        return
    con.execute(
        "DELETE FROM cell_ink WHERE sha256=? AND field=? AND extraction_version='facts/v1' "
        "AND ink_version=?",
        (sha, field, INK_VERSION),
    )


def run(
    facts_db: Path,
    export: Path,
    geometry_db: Path | None,
    *,
    limit: int | None = None,
    dry_run: bool = False,
) -> Counter[str]:
    from PIL import Image

    con = sqlite3.connect(facts_db)
    con.executescript(SCHEMA)
    cells = select_cells(con)
    if limit:
        cells = cells[:limit]
    rulings = load_rulings(geometry_db, GEOMETRY_VERSION)
    tally: Counter[str] = Counter()
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    images: dict[str, np.ndarray | None] = {}
    for sha, field, anchor, rel_path, frame_name, tilt in cells:
        # The lattice and the region are in the stored frame, like the anchor:
        # the crop is cut from the stored image and levelled by `prepare_crop`.
        lattice = lattice_for(sha, rulings, None)
        if lattice is None:
            tally["no rulings for the page"] += 1
            forget(con, sha, field, dry_run=dry_run)
            continue
        region = cell_region(anchor, lattice)
        if region is None:
            tally["no ruled row around the label"] += 1
            forget(con, sha, field, dry_run=dry_run)
            continue
        if rel_path not in images:
            try:
                images[rel_path] = np.asarray(Image.open(export / rel_path).convert("L"))
            except OSError:
                images[rel_path] = None
        image = images[rel_path]
        if image is None:
            tally["image unreadable"] += 1
            continue
        frame = None
        if frame_name == "ROTATE" and tilt:
            from kidneymatch.ocr.geometry import PageFrame

            frame = PageFrame(float(tilt), int(image.shape[1]), int(image.shape[0]))
        crop = prepare_crop(image, region, frame=frame, profile=RAW)
        measure = ink_measure(np.asarray(crop.pixels)) if crop is not None else None
        # The control: the label itself, under the same measure.
        label = prepare_crop(image, anchor, frame=frame, profile=RAW)
        control = ink_measure(np.asarray(label.pixels)) if label is not None else None
        decision = classify(measure, control)
        tally[decision] += 1
        if dry_run:
            continue
        con.execute(
            "INSERT OR REPLACE INTO cell_ink VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                sha,
                field,
                "facts/v1",
                INK_VERSION,
                json.dumps(list(region)),
                measure.fraction if measure else None,
                measure.coverage if measure else None,
                measure.longest_run if measure else None,
                measure.paper if measure else None,
                decision,
                now,
            ),
        )
        if len(images) > 64:
            images.clear()
    con.commit()
    con.close()
    tally["cells examined"] = len(cells)
    return tally


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--export", type=Path, default=ROOT / "data/raw/ChatExport_2026-08-31")
    parser.add_argument("--geometry", type=Path, default=ROOT / "data/derived/geometry.sqlite")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true", help="measure and count, change nothing")
    args = parser.parse_args()
    if not args.facts.exists():
        print(f"missing {args.facts}")
        return 2
    tally = run(args.facts, args.export, args.geometry, limit=args.limit, dry_run=args.dry_run)
    verb = "measured" if args.dry_run else "decided"
    print(f"{verb} {tally.pop('cells examined', 0):,} empty labelled cells")
    for key, count in sorted(tally.items()):
        print(f"  {key:<40}{count:>8,}")
    print(
        "Recorded in cell_ink, and nothing else: a BLANK cell is a printed row this page "
        "left empty, an INKED one is a value no engine boxed. Both stay in review until a "
        "person extends HA-009 (see the module docstring)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
