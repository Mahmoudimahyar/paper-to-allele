#!/usr/bin/env python3
"""Read the second allele out of the rest of the row, where one was bound and one was not.

4,788 RESOLVED HLA cells carry one value and `second_allele='UNREAD'`. A person
reading the same cells found two alleles on 19 of the 19 labelled ones, so this
is the largest single shape of loss the review measures that is not a refusal:
the cell is RESOLVED and half of it is missing.

Measured 2026-09-07 on those 19: the missing allele's text is nowhere in the
page's stored OCR on **14 of them**. The primary detector never drew a box
around it, so no binding rule could ever reach it — the fix has to be a fresh
READING of the part of the row the first value does not cover, which is what
this pass does. It never re-detects: the region comes from the page's own
rulings, exactly as `cell_ink_pass` cuts it.

**What this reaches, and what it does not.** On the same 19, the remainder of
the ruled row carries measurable ink on 2; on 7 it is blank, and on 5 the
rulings place no row at all while another 5 store no value box. So this pass is
not the answer to the partial-value loss — W3(a)'s target of 19 -> <= 8 is not
reachable this way, and `docs/ingestion/IMPLEMENTATION_PLAN_2026-09-07.md`
records that. What it IS, is the safe half: where the remainder does hold ink,
two engines reading it is better evidence than nobody reading it, and roughly
300 corpus cells are in that state.

The region is the ruled row around the locus label (`ocr/lattice`), from a gap
past the RIGHT edge of the bound value to the row's end. Three things then have
to hold before anything is written:

1. **the region must hold ink.** `ocr/ink` classifies it BLANK / INKED /
   UNMEASURABLE against the same thresholds `cell_ink_pass` uses, and only
   INKED goes on. A BLANK remainder is NOT recorded as a single-allele
   finding, and the measurement is why: on the 19 labelled cells a person read
   two alleles in, this region measures BLANK on 7 of the 9 it can measure at
   all. So the region is not where the second allele is on those forms, and
   "no ink here" cannot be turned into "one allele is printed". The mechanics
   are sound — this crop and this measure reproduce `cell_ink_pass`'s stored
   decision on 136 of 136 measurable cells — which is what makes the negative
   result trustworthy rather than a bug;
2. **two independent recognizers must read the same text.** PP-OCRv5 and
   PP-OCRv6 recognition on the same crop, exactly as `confirm_pass` uses them.
   One engine's reading of a crop nobody detected is a proposal, never a fact;
3. **the reading must be an admissible allele of THIS locus.** It parses under
   `glyphs.parse_allele_values`, its locus (printed prefix, or the cell's own
   locus for a bare number) matches the cell, and its first field is in the
   IMGT vocabulary the resolver uses. A reading naming another gene means the
   region ran into the next column and the cell is left alone.

The second allele is written into `second_allele` and appended to `value`, with
`source` gaining `|second-allele-reread/v1` so the whole group is one statement
to find, to review as its own stratum and to `--undo`.

`--dry-run` is the DEFAULT. Pass `--no-dry-run` to write.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cell_ink_pass import cell_region  # noqa: E402

from kidneymatch.hla.vocabulary import load_vocabulary  # noqa: E402
from kidneymatch.ocr.glyphs import parse_allele_values  # noqa: E402
from kidneymatch.ocr.ink import classify as classify_ink  # noqa: E402
from kidneymatch.ocr.ink import ink_measure  # noqa: E402
from kidneymatch.ocr.lattice import lattice_for, load_rulings  # noqa: E402

EV = "facts/v1"
TAG = "second-allele-reread/v1"
LOCI = ("A", "B", "C", "DRB1", "DQA1", "DQB1", "DPA1", "DPB1")
GEOMETRY_VERSION = "rulings/v3+lsd+sweep"
# A gap past the bound value, in label heights, so the crop cannot clip the
# value's own last glyph and read it as a new allele.
VALUE_GAP_HEIGHTS = 0.35
# Narrower than this and there is no room for an allele; the crop would be a
# sliver of the ruling.
MIN_REMAINDER_HEIGHTS = 1.5
REASON = (
    "the rest of this row was re-read: two independent recognizers agree it prints a second "
    "allele of this locus that no detector had boxed (W3(a), 2026-09-07)"
)


def targets(con: sqlite3.Connection, limit: int | None) -> list[tuple]:
    """RESOLVED cells with one value, no second allele, and boxes to measure from."""
    marks = ",".join("?" * len(LOCI))
    rows = con.execute(
        f"SELECT f.sha256, f.field, f.value, f.anchor_box, f.value_boxes, f.source, d.rel_path "
        f"FROM fact f JOIN document d ON d.sha256=f.sha256 "
        f"AND d.extraction_version=f.extraction_version "
        f"WHERE f.extraction_version=? AND f.field IN ({marks}) AND f.status='RESOLVED' "
        f"AND f.second_allele='UNREAD' AND f.anchor_box IS NOT NULL "
        f"AND f.value_boxes IS NOT NULL AND d.comparison_sheet=0 "
        f"ORDER BY f.sha256, f.field",
        (EV, *LOCI),
    ).fetchall()
    return rows if limit is None else rows[:limit]


def remainder_region(
    anchor: list[float], value_boxes: list[list[float]], lattice
) -> tuple[float, float, float, float] | None:
    """The part of the ruled row the bound value does not cover, or None.

    `cell_ink_pass.cell_region` gives the whole cell; this starts instead at the
    right edge of the value that was bound, so nothing already read can be read
    again.
    """
    cell = cell_region(anchor, lattice)
    if cell is None:
        return None
    height = anchor[3] - anchor[1]
    left = max(box[2] for box in value_boxes) + VALUE_GAP_HEIGHTS * height
    left = max(left, cell[0])
    if cell[2] - left < MIN_REMAINDER_HEIGHTS * height:
        return None
    return (left, cell[1], cell[2], cell[3])


def crop(image, region: tuple[float, float, float, float]):
    """The region as a greyscale array, in the stored image's own frame."""
    import numpy as np

    height, width = image.shape[:2]
    x0 = max(0, int(region[0] * width))
    y0 = max(0, int(region[1] * height))
    x1 = min(width, int(region[2] * width))
    y1 = min(height, int(region[3] * height))
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    return np.asarray(image[y0:y1, x0:x1])


def agreed_allele(readings: list[str], locus: str, vocabulary) -> tuple[str, str] | None:
    """The one allele every engine read, or None. Returns `(text, first_field)`.

    A bare number takes the cell's own locus, which geometry already decided; a
    printed prefix must name THIS locus, or the crop ran into another column.
    """
    # EVERY engine must have read something, and all of them the same thing.
    # Filtering the silent ones out first would let one engine's reading of a
    # crop no detector ever boxed become a fact on its own, which is exactly
    # what this pass may not do.
    stripped = [(text or "").strip() for text in readings]
    if len(stripped) < 2 or not all(stripped) or len(set(stripped)) != 1:
        return None
    text = stripped[0]
    values = parse_allele_values(text)
    if len(values) != 1:
        return None
    value = values[0]
    if value.locus_prefix is not None and value.locus_prefix != locus:
        return None
    if not vocabulary.covers(locus) or not vocabulary.is_admissible(locus, value.first_field):
        return None
    return f"{locus}*{value.first_field}", value.first_field


def run(
    facts: Path,
    export: Path,
    geometry: Path,
    *,
    dry_run: bool,
    limit: int | None,
    engines: list | None = None,
) -> Counter[str]:
    import numpy as np
    from PIL import Image as PilImage

    con = (
        sqlite3.connect(f"file:{facts.as_posix()}?mode=ro", uri=True)
        if dry_run
        else sqlite3.connect(facts)
    )
    rulings = load_rulings(geometry, GEOMETRY_VERSION, read_only=True)
    vocabulary = load_vocabulary()
    tally: Counter[str] = Counter()
    rows = targets(con, limit)
    tally["cells with one value and no second allele"] = len(rows)

    if engines is None and not dry_run:
        from confirm_pass import PPOCR_MODELS, build_ppocr_reader

        engines = [
            build_ppocr_reader(PPOCR_MODELS["ppocrv5"]),
            build_ppocr_reader(PPOCR_MODELS["ppocrv6"]),
        ]

    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    written = 0
    for sha, field, value, anchor_json, boxes_json, source, rel_path in rows:
        lattice = lattice_for(sha, rulings, None)
        if lattice is None:
            tally["no rulings placed this page's rows"] += 1
            continue
        try:
            anchor = json.loads(anchor_json)
            value_boxes = json.loads(boxes_json)
        except (TypeError, ValueError):
            tally["boxes are not readable"] += 1
            continue
        region = remainder_region(anchor, value_boxes, lattice)
        if region is None:
            tally["no room past the bound value for another allele"] += 1
            continue
        try:
            with PilImage.open(export / rel_path) as handle:
                image = np.asarray(handle.convert("L"))
        except (OSError, ValueError):
            tally["image not readable"] += 1
            continue
        patch = crop(image, region)
        if patch is None:
            tally["region too small to measure"] += 1
            continue
        decision = classify_ink(ink_measure(patch))
        if decision != "INKED":
            # BLANK here is NOT written back as a finding, and the measurement
            # is why. On the 19 labelled cells a person read two alleles in,
            # this region measures BLANK on 7 of the 9 it can measure at all —
            # so "no ink in the rest of the row" does not mean "one allele is
            # printed", and recording it as `second_allele=BLANK_MEASURED`
            # would assert a single-allele finding on cells that print two.
            # (The mechanics are not the problem: this crop and this measure
            # reproduce `cell_ink_pass`'s stored decision on 136 of 136
            # measurable cells.) The region is simply not where the second
            # allele is on those forms.
            tally[f"the rest of the row is {decision.lower()}"] += 1
            continue
        if engines is None:
            tally["INKED: a reading would be attempted"] += 1
            continue
        pil = PilImage.fromarray(patch)
        readings = [reader([pil])[0] for reader in engines]
        agreed = agreed_allele(readings, field, vocabulary)
        if agreed is None:
            tally["INKED but the two engines did not agree on one admissible allele"] += 1
            continue
        text, _first = agreed
        tally[f"second allele read: {field}"] += 1
        if dry_run:
            continue
        merged = " ".join(sorted([*(value or "").split(), text]))
        con.execute(
            "UPDATE fact SET value=?, second_allele='READ', reason=?, source=?, "
            "value_boxes=?, created_utc=? WHERE sha256=? AND field=? AND extraction_version=? "
            "AND second_allele='UNREAD'",
            (
                merged,
                REASON,
                f"{source}|{TAG}" if source else TAG,
                json.dumps([*value_boxes, list(region)]),
                now,
                sha,
                field,
                EV,
            ),
        )
        written += 1
        if written % 100 == 0:
            con.commit()
    if not dry_run:
        con.commit()
    tally["rows written"] = written
    return tally


def undo(con: sqlite3.Connection) -> int:
    """Take the second allele back off every cell this pass wrote."""
    rows = con.execute(
        "SELECT sha256, field, value, source, value_boxes FROM fact "
        "WHERE extraction_version=? AND source LIKE ?",
        (EV, f"%{TAG}"),
    ).fetchall()
    for sha, field, value, source, boxes_json in rows:
        parts = (value or "").split()
        boxes = json.loads(boxes_json or "[]")
        con.execute(
            "UPDATE fact SET value=?, second_allele='UNREAD', source=?, value_boxes=? "
            "WHERE sha256=? AND field=? AND extraction_version=?",
            (
                " ".join(parts[:-1]) or None,
                (source or "").replace(f"|{TAG}", "").replace(TAG, "") or None,
                json.dumps(boxes[:-1]) if len(boxes) > 1 else None,
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
    parser.add_argument("--export", type=Path, default=ROOT / "data/raw/ChatExport_2026-08-31")
    parser.add_argument("--geometry", type=Path, default=ROOT / "data/derived/geometry.sqlite")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-dry-run", action="store_true", help="write; the default only counts")
    parser.add_argument("--undo", action="store_true", help="remove every second allele this wrote")
    args = parser.parse_args()
    if args.undo:
        con = sqlite3.connect(args.facts)
        print(f"undone: {undo(con):,} cells back to one allele")
        return 0
    tally = run(
        args.facts,
        args.export,
        args.geometry,
        dry_run=not args.no_dry_run,
        limit=args.limit,
    )
    for key, count in tally.most_common():
        print(f"{count:>7,}  {key}")
    print("(dry run; nothing written)" if not args.no_dry_run else "written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
