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
(`kidneymatch.ocr.ink.column_regions`) — or, on the rows with no DRB1 pair,
the ruled grid does (`kidneymatch.ocr.lattice`: the row's two value cells, the
token identifying one of them and the other being the slot). The slot is cut
from the original image, in the level frame on a ROTATE page, and its ink is
measured with the table rulings removed (`ink_measure`). Then:

* BLANK — paper: the other genes are ABSENT, a positive finding with the
  blank region as its provenance box and `source=ink-certified`.
* INKED — something is printed there that no engine read: the other genes go
  to REVIEW_REQUIRED, the same policy as a printed label whose cell could not
  be read. Nothing is guessed from the ink.
* UNMEASURABLE — no paper level (a shadow, a stamp), no geometry to place
  the slot, or the read token itself measures under `CONTROL_FRACTION` (the
  page's print is beyond the measure): the cells stay as the row rule left them.

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
from kidneymatch.ocr.ink import (  # noqa: E402
    ColumnRegion,
    InkMeasure,
    classify,
    column_regions,
    ink_measure,
)
from kidneymatch.ocr.lattice import lattice_for, load_rulings  # noqa: E402
from kidneymatch.ocr.rulings import GEOMETRY_VERSION  # noqa: E402

INK_VERSION = "drbx-ink/v1"
SOURCE = "ink-certified"
GENES = ("DRB3", "DRB4", "DRB5")
ONE_TOKEN_REASON = "only one gene token read"
# The row rule's own words for the state a slot returns to when this pass can
# no longer measure it (`kidneymatch.ocr.drbx`).
ONE_TOKEN_FULL_REASON = "only one gene token read; the second column is unread or empty"
BLANK_REASON = (
    "the second slot of this row is paper: measured on the page with the rulings removed, "
    "in the column the DRB1 row above places it in"
)
INKED_REASON = (
    "the second slot of this row holds ink that no engine read; a printed gene the "
    "recognizer missed is a question for a person"
)

# The thresholds live in `kidneymatch.ocr.ink` (`BLANK_*`, `classify`) and are
# shared with `cell_ink_pass.py`; their calibration is recorded there.

# A gene cell this pass may write: the row rule's UNKNOWN, or one of its own
# earlier decisions (INKED to review, or ABSENT by ink).
OWN_CELL = (
    "(status='UNKNOWN' OR (status='REVIEW_REQUIRED' AND reason=?) "
    "OR (status='RESOLVED' AND value='ABSENT' AND source=?))"
)

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


def decide(measure: InkMeasure | None, control: InkMeasure | None = None) -> str:
    return classify(measure, control)


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
    for (
        sha,
        field,
        status,
        value,
        boxes,
        reason,
        source,
        repaired,
        anchor,
        rel_path,
        frame,
        tilt,
    ) in con.execute(
        "SELECT f.sha256, f.field, f.status, f.value, f.value_boxes, f.reason, f.source, "
        "f.repaired, f.anchor_box, d.rel_path, d.frame, d.tilt_deg "
        "FROM fact f JOIN document d ON d.sha256=f.sha256 "
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
                "repaired": False,
                "header": None,
            },
        )
        if anchor and row["header"] is None:
            row["header"] = json.loads(anchor)
        if value == "PRESENT" and boxes and status == "RESOLVED" and source != SOURCE:
            row["present"].append(json.loads(boxes)[0])  # type: ignore[union-attr]
            if repaired:
                row["repaired"] = True  # type: ignore[index]
        elif (
            (status == "UNKNOWN" and ONE_TOKEN_REASON in (reason or ""))
            or (status == "REVIEW_REQUIRED" and reason == INKED_REASON)
            or (status == "RESOLVED" and value == "ABSENT" and source == SOURCE)
        ):
            # A slot this pass decided before is re-judged with it: the measure
            # follows the evidence in both directions (a refined measure, a new
            # control), and a slot it can no longer measure goes back to the
            # row rule's own state.
            row["unknown"].append(field)  # type: ignore[union-attr]
    out = []
    for sha, row in rows.items():
        if len(row["present"]) == 1 and row["unknown"]:  # type: ignore[arg-type]
            # The DRB1 pair places the slot; without one the ruled grid may.
            row["drb1"] = drb1.get(sha)
            out.append(row)
    return out


def slot_from_lattice(
    sha: str, header: list[float] | None, gene: list[float], rulings: dict
) -> ColumnRegion | None:
    """The row's OTHER value cell, from the ruled grid.

    The header's right edge starts the value area; the vertical rulings that
    cross the row cut it into cells. Exactly two of them are the row's value
    columns — that is what the printed enumeration `DRB3/4/5` means — and the
    read token identifies one; the other is the slot. Which side the token sits
    on is READ from the grid, never assumed: a row whose token is in the second
    column has its empty slot to the LEFT. Anything else about the row (one
    cell, three, a token in none of them) places nothing, and the genes stay as
    the row rule left them.
    """
    if header is None:
        return None
    lattice = lattice_for(sha, rulings, None)
    if lattice is None:
        return None
    band = lattice.row_band((gene[0] + gene[2]) / 2, (gene[1] + gene[3]) / 2, gene[3] - gene[1])
    if band is None:
        return None
    edges = lattice.verticals_crossing(band, header[2])
    cells = [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]
    if len(cells) != 2:
        return None
    centre = (gene[0] + gene[2]) / 2
    holding = [i for i, (x0, x1) in enumerate(cells) if x0 <= centre <= x1]
    if len(holding) != 1:
        return None
    other = cells[1 - holding[0]]
    return ColumnRegion(1 - holding[0], (other[0], band.top, other[1], band.bottom), False)


def forget(con: sqlite3.Connection, sha: str, *, dry_run: bool = False) -> None:
    """Drop a measurement this run can no longer make (see `cell_ink_pass`)."""
    if dry_run:
        return
    con.execute(
        "DELETE FROM drbx_ink WHERE sha256=? AND extraction_version='facts/v1' AND ink_version=?",
        (sha, INK_VERSION),
    )


def run(
    facts_db: Path,
    export: Path,
    *,
    geometry_db: Path | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> Counter[str]:
    from PIL import Image

    con = sqlite3.connect(facts_db)
    con.executescript(SCHEMA)
    rows = select_rows(con)
    if limit:
        rows = rows[:limit]
    rulings = load_rulings(geometry_db, GEOMETRY_VERSION)
    tally: Counter[str] = Counter()
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    for row in rows:
        if row["repaired"]:
            # The lone token rests on the S-for-5 repair, which KI-026 measured
            # wrong often enough that a repaired slot certifies no absence on a
            # two-token row either. Ink says what is printed, not which gene.
            tally["the row's only token rests on the S-for-5 repair"] += 1
            forget(con, str(row["sha256"]), dry_run=dry_run)
            continue
        if row["drb1"]:
            regions = column_regions(row["drb1"], row["present"])  # type: ignore[arg-type]
            empty = [r for r in regions if not r.occupied]
            region = empty[0] if len(empty) == 1 else None
            placed_by = "the DRB1 pair"
        else:
            region = slot_from_lattice(
                str(row["sha256"]),
                row["header"],  # type: ignore[arg-type]
                row["present"][0],  # type: ignore[index]
                rulings,
            )
            placed_by = "the ruled grid"
        if region is None:
            tally["geometry does not place the token in one column"] += 1
            forget(con, str(row["sha256"]), dry_run=dry_run)
            continue
        tally[f"slot placed by {placed_by}"] += 1
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
        # The control: the token this row is known to hold, under the same measure.
        token = prepare_crop(image, row["present"][0], frame=frame, profile=RAW)  # type: ignore[index]
        control = ink_measure(np.asarray(token.pixels)) if token is not None else None
        decision = decide(measure, control)
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
                f"AND {OWN_CELL}",
                [
                    (
                        BLANK_REASON,
                        SOURCE,
                        json.dumps([list(region.box)]),
                        row["sha256"],
                        gene,
                        INKED_REASON,
                        SOURCE,
                    )
                    for gene in row["unknown"]  # type: ignore[union-attr]
                ],
            )
        elif decision == "INKED":
            con.executemany(
                "UPDATE fact SET status='REVIEW_REQUIRED', value=NULL, reason=?, source=NULL, "
                "value_boxes=? WHERE sha256=? AND field=? AND extraction_version='facts/v1' "
                f"AND {OWN_CELL}",
                [
                    (
                        INKED_REASON,
                        json.dumps([list(region.box)]),
                        row["sha256"],
                        gene,
                        INKED_REASON,
                        SOURCE,
                    )
                    for gene in row["unknown"]  # type: ignore[union-attr]
                ],
            )
        else:
            # Unmeasurable now: whatever this pass decided before is withdrawn
            # and the slot is what the row rule said.
            con.executemany(
                "UPDATE fact SET status='UNKNOWN', value=NULL, reason=?, source=NULL, "
                "value_boxes=NULL WHERE sha256=? AND field=? AND extraction_version='facts/v1' "
                "AND ((status='REVIEW_REQUIRED' AND reason=?) "
                "OR (status='RESOLVED' AND value='ABSENT' AND source=?))",
                [
                    (ONE_TOKEN_FULL_REASON, row["sha256"], gene, INKED_REASON, SOURCE)
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
    parser.add_argument("--geometry", type=Path, default=ROOT / "data/derived/geometry.sqlite")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true", help="measure and count, change nothing")
    args = parser.parse_args()
    if not args.facts.exists():
        print(f"missing {args.facts}")
        return 2
    tally = run(
        args.facts, args.export, geometry_db=args.geometry, limit=args.limit, dry_run=args.dry_run
    )
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
