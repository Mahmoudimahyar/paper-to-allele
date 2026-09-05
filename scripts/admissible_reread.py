#!/usr/bin/env python3
"""Re-read a value the vocabulary refused, and take the reading only if it holds.

SUPERSEDED by `scripts/reread_refused.py`, which applies exactly these gates to
both of the resolver's reading refusals rather than only to this one. Run that
one. This file stays because 744 facts carry
`source='admissible-reread+two-engine-agreement'` and a derived medical fact
must point back at the code that produced it; re-running it changes nothing,
because the cells it acts on are no longer REVIEW_REQUIRED.

`anchors.py` gate 5 refuses a value whose first field is not an allele family
of its locus. The gate is right to refuse — `A*83` is not a thing — but it
cannot repair, and the comment beside it names why: the recognizer's commonest
surviving error is a leading `0` read as `8` or `9`, and both readings are
clean digits, so no glyph repair and no geometric gate can see it. The cell
therefore ends REVIEW_REQUIRED holding a box nobody looks at again. There are
1,026 of them, and on the reviewer's 220 labels three are cells where a human
read the value without difficulty.

So this pass asks a second recognizer what the box says:

* every refused cell keeps its value boxes; each is re-read by TWO recognizers,
  PP-OCRv6 and PP-OCRv5-server, and both must state the same value. A single
  engine here would be one guess replacing another: the pixels already defeated
  one reader, and a second reader producing a family that merely exists is not
  evidence that it is the printed one. Agreement is;
* a reading is taken only when it PARSES as an allele value, is ADMISSIBLE for
  this locus, and DIFFERS from the first field the gate refused. The asymmetry
  is the whole argument: one reader produced a family that does not exist and
  two others agreed on one that does, from the same pixels;
* a reading carrying its own locus prefix must name this locus, exactly as
  gate 2 requires of a first reading. Geometry still owns the locus;
* a cell whose boxes do not all settle is resolved from the ones that did and
  declares its second allele UNREAD, which is a partial read rather than a
  claim of completeness.

Nothing is invented. A reading that is itself inadmissible, unparsable, equal
to the refused one, or prefixed for another locus leaves the cell exactly as
the gate left it, and a later run re-judges what an earlier one decided.
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

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kidneymatch.hla.vocabulary import load_vocabulary  # noqa: E402
from kidneymatch.ocr.crops import CONFIRMER_PADDED, prepare_crop  # noqa: E402
from kidneymatch.ocr.geometry import PageFrame  # noqa: E402
from kidneymatch.ocr.glyphs import parse_allele_value  # noqa: E402

LOCI = ("A", "B", "C", "DRB1", "DQA1", "DQB1", "DPA1", "DPB1")
REREAD_VERSION = "admissible-reread/v1+ppocrv6+ppocrv5"
SOURCE = "admissible-reread+two-engine-agreement"
REFUSED = re.compile(r"^'([^']*)' is not an allele family of")

RESOLVED_REASON = (
    "the family the vocabulary refused was a misread; two independent recognizers read this "
    "box as the same family, and that family exists for this locus"
)
PARTIAL_REASON = (
    "one box of this row re-read as an admissible family both recognizers agree on; the "
    "other did not settle, so the second allele is unread"
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS admissible_reread (
    sha256             TEXT NOT NULL,
    field              TEXT NOT NULL,
    extraction_version TEXT NOT NULL,
    reread_version     TEXT NOT NULL,
    refused            TEXT,
    readings           TEXT,
    readings_second    TEXT,
    taken              TEXT,
    created_utc        TEXT NOT NULL,
    PRIMARY KEY (sha256, field, extraction_version, reread_version)
);
"""


def admissible_reading(reading: str, locus: str, refused: str, vocabulary) -> str | None:
    """The value this reading states, or None when it settles nothing.

    Every condition here is one an original reading would have had to pass.
    """
    parsed = parse_allele_value((reading or "").strip())
    if parsed is None:
        return None
    if parsed.locus_prefix and parsed.locus_prefix.upper() != locus.upper():
        return None
    if parsed.first_field == refused:
        return None
    if not vocabulary.covers(locus) or not vocabulary.is_admissible(locus, parsed.first_field):
        return None
    return parsed.text()


def select_cells(con: sqlite3.Connection) -> list[dict[str, object]]:
    """Cells the vocabulary refused that still hold a box to re-read."""
    placeholders = ",".join("?" * len(LOCI))
    out: list[dict[str, object]] = []
    for sha, field, reason, boxes, rel, frame, tilt in con.execute(
        "SELECT f.sha256, f.field, f.reason, f.value_boxes, d.rel_path, d.frame, d.tilt_deg "
        "FROM fact f JOIN document d ON d.sha256=f.sha256 "
        "AND d.extraction_version=f.extraction_version "
        f"WHERE f.status='REVIEW_REQUIRED' AND f.field IN ({placeholders}) "
        "AND f.reason LIKE '%is not an allele family of%' AND f.value_boxes IS NOT NULL "
        "AND f.extraction_version='facts/v1' ORDER BY f.sha256, f.field",
        LOCI,
    ):
        found = REFUSED.match(reason or "")
        if not found:
            continue
        out.append(
            {
                "sha256": sha,
                "field": field,
                "refused": found.group(1),
                "boxes": json.loads(boxes),
                "rel": rel,
                "frame": frame,
                "tilt": tilt,
            }
        )
    return out


def run(
    facts_db: Path, export: Path, *, limit: int | None = None, dry_run: bool = False
) -> Counter[str]:
    from PIL import Image

    sys.path.insert(0, str(ROOT / "scripts"))
    from confirm_pass import (  # noqa: PLC0415
        PPOCR_MODEL,
        PPOCRV6_MODEL,
        build_ppocr_reader,
    )

    vocabulary = load_vocabulary()
    con = sqlite3.connect(facts_db)
    con.executescript(SCHEMA)
    cells = select_cells(con)
    if limit:
        cells = cells[:limit]
    tally: Counter[str] = Counter()
    if not cells:
        tally["cells examined"] = 0
        return tally
    read = build_ppocr_reader(PPOCRV6_MODEL)
    read_second = build_ppocr_reader(PPOCR_MODEL)
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    images: dict[str, object] = {}
    for cell in cells:
        rel = str(cell["rel"])
        if rel not in images:
            try:
                images[rel] = np.asarray(Image.open(export / rel).convert("L"))
            except OSError:
                images[rel] = None
        image = images[rel]
        if image is None:
            tally["image unreadable"] += 1
            continue
        frame = None
        if cell["frame"] == "ROTATE" and cell["tilt"]:
            frame = PageFrame(float(cell["tilt"]), int(image.shape[1]), int(image.shape[0]))
        crops = []
        for box in cell["boxes"]:  # type: ignore[union-attr]
            crop = prepare_crop(image, box, frame=frame, profile=CONFIRMER_PADDED)
            if crop is not None and crop.pixels.size:
                crops.append(Image.fromarray(crop.pixels))
        if not crops:
            tally["no crop"] += 1
            continue
        readings = read(crops)
        seconds = read_second(crops)
        taken = []
        for reading, second in zip(readings, seconds, strict=True):
            value = admissible_reading(
                reading, str(cell["field"]), str(cell["refused"]), vocabulary
            )
            agreed = admissible_reading(
                second, str(cell["field"]), str(cell["refused"]), vocabulary
            )
            # Both recognizers must arrive at the same admissible value. One
            # alone would only be trading the first reader's guess for another.
            if value is not None and value == agreed:
                taken.append(value)
        if not dry_run:
            con.execute(
                "INSERT OR REPLACE INTO admissible_reread VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    cell["sha256"],
                    cell["field"],
                    "facts/v1",
                    REREAD_VERSION,
                    cell["refused"],
                    json.dumps(list(readings)),
                    json.dumps(list(seconds)),
                    json.dumps(taken),
                    now,
                ),
            )
        if not taken:
            tally["the two readers do not agree; the refusal stands"] += 1
            continue
        complete = len(taken) == len(crops)
        where = "whole cell" if complete else "part of the cell"
        tally[f"re-read {where}: {len(taken)} value(s)"] += 1
        if dry_run:
            continue
        con.execute(
            "UPDATE fact SET status='RESOLVED', value=?, reason=?, source=?, repaired=1, "
            "second_allele=? WHERE sha256=? AND field=? AND extraction_version='facts/v1'",
            (
                " ".join(taken),
                RESOLVED_REASON if complete else PARTIAL_REASON,
                SOURCE,
                "READ" if complete else "UNREAD",
                cell["sha256"],
                cell["field"],
            ),
        )
        con.commit()
    con.commit()
    con.close()
    tally["cells examined"] = len(cells)
    return tally


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--export", type=Path, default=ROOT / "data/raw/ChatExport_2026-08-31")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true", help="read and count, change nothing")
    args = parser.parse_args()
    if not args.facts.exists():
        print(f"missing {args.facts}")
        return 2
    tally = run(args.facts, args.export, limit=args.limit, dry_run=args.dry_run)
    verb = "read" if args.dry_run else "rewrote"
    print(f"{verb} {tally.pop('cells examined', 0):,} refused cells")
    for key, count in sorted(tally.items()):
        print(f"  {key:<52}{count:>8,}")
    print(
        "A reading is taken only when it parses, is admissible for this locus, and differs "
        "from the family the gate refused."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
