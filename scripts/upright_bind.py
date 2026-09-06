#!/usr/bin/env python3
"""Bind the loci that only became readable once the page was turned upright.

`upright_pass.py` finds the 611 documents photographed sideways and re-reads
each at all four rotations, keeping one only when it beats every other OUTRIGHT
on named locus anchors. This binds values from that reading.

Every cell it can touch is currently `UNKNOWN` with reason "no anchor on this
document" — 0 of the 4,888 locus cells on these pages is RESOLVED — so nothing
the pipeline currently trusts can be disturbed.

**The stored page geometry is not used, and that is deliberate.** The frame, the
template family and the row slope in `geometry.sqlite` were all measured on the
sideways image. Rectifying an upright reading with a sideways frame, or lifting
its rows along a slope measured across the page's short axis, would place every
cell wrong. This pass therefore uses `DEFAULT_RULE` with no frame and no slope:
the generic rule, on boxes read from an image that is now the right way up.
`reading_direction` is still asked, because a rotated page can print its values
under the labels as readily as beside them.

Provenance travels with every fact — the anchor box and the value boxes, in the
UPRIGHT coordinate frame, plus `rotation` in the reason — because a reviewer
looking at a crop needs to know the pixels were taken from a turned image.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from extract_facts import DEFAULT_RULE  # noqa: E402
from page_ocr_bind import BELOW_RULE  # noqa: E402
from upright_pass import VERSION  # noqa: E402

from kidneymatch.hla.vocabulary import load_vocabulary  # noqa: E402
from kidneymatch.ocr.anchors import Box, ResolutionStatus, resolve_locus  # noqa: E402
from kidneymatch.ocr.layout import reading_direction  # noqa: E402

EV = "facts/v1"
LOCI = ("A", "B", "C", "DRB1", "DQA1", "DQB1", "DPA1", "DPB1")
SOURCE = "upright+rotated"
NO_ANCHOR = "no anchor on this document"


def unresolved(con: sqlite3.Connection, shas: set[str]) -> dict[str, list[str]]:
    """The loci these pages left unread for want of an anchor."""
    out: dict[str, list[str]] = defaultdict(list)
    placeholders = ",".join("?" * len(LOCI))
    for sha, field in con.execute(
        f"SELECT sha256, field FROM fact WHERE extraction_version=? AND field IN ({placeholders}) "
        "AND status != 'RESOLVED' AND reason = ?",
        (EV, *LOCI, NO_ANCHOR),
    ):
        if sha in shas:
            out[sha].append(field)
    return dict(out)


def run(facts_db: Path, upright_db: Path, *, dry_run: bool = False) -> Counter[str]:
    vocabulary = load_vocabulary()
    con = sqlite3.connect(facts_db)
    up = sqlite3.connect(f"file:{upright_db.as_posix()}?mode=ro", uri=True)
    readings = {
        sha: (rotation, json.loads(bj or "[]"), json.loads(tj or "[]"))
        for sha, rotation, bj, tj in up.execute(
            "SELECT sha256, rotation, boxes_json, texts_json FROM upright_result "
            "WHERE version=? AND verdict='UPRIGHT_FOUND'",
            (VERSION,),
        )
    }
    work = unresolved(con, set(readings))
    tally: Counter[str] = Counter()
    tally["pages turned upright"] = len(readings)
    tally["their cells left unread for want of an anchor"] = sum(len(v) for v in work.values())
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())

    for sha, loci in sorted(work.items()):
        rotation, geometry, texts = readings[sha]
        boxes = [Box(b[0], b[1], b[2], b[3], t) for b, t in zip(geometry, texts, strict=False)]
        if not boxes:
            continue
        # No frame and no slope: both were measured on the sideways image.
        layout = reading_direction(boxes, 0.0, 0.0)
        rule = BELOW_RULE if layout.direction == "below" else DEFAULT_RULE
        rule = replace(rule, row_slope=0.0, column_slope=0.0)
        tally[f"read {layout.direction}"] += 1
        for locus in loci:
            result = resolve_locus(boxes, locus, rule, vocabulary=vocabulary)
            if result.status is not ResolutionStatus.RESOLVED or not result.values:
                tally["turning the page settles nothing here either"] += 1
                continue
            tally[f"bound once upright: {locus}"] += 1
            if dry_run:
                continue
            con.execute(
                "UPDATE fact SET status='RESOLVED', value=?, reason=?, source=?, repaired=1, "
                "second_allele=?, anchor_box=?, value_boxes=?, created_utc=? "
                "WHERE sha256=? AND field=? AND extraction_version=?",
                (
                    " ".join(str(v) for v in result.values),
                    f"the photograph is {rotation} degrees off upright; turned, this page prints "
                    f"the label and its value, and no rotation but this one anchors any locus",
                    SOURCE,
                    result.second_allele.value if result.second_allele else None,
                    json.dumps(
                        [
                            result.anchor_box.x0,
                            result.anchor_box.y0,
                            result.anchor_box.x1,
                            result.anchor_box.y1,
                        ]
                    )
                    if result.anchor_box
                    else None,
                    json.dumps([[b.x0, b.y0, b.x1, b.y1] for b in result.value_boxes]),
                    now,
                    sha,
                    locus,
                    EV,
                ),
            )
        con.commit()
    con.close()
    up.close()
    return tally


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--upright", type=Path, default=ROOT / "data/derived/upright_pass.sqlite")
    parser.add_argument("--dry-run", action="store_true", help="count, change nothing")
    args = parser.parse_args()
    tally = run(args.facts, args.upright, dry_run=args.dry_run)
    print(f"{'would bind' if args.dry_run else 'bound'} loci from pages turned upright")
    for name, count in sorted(tally.items(), key=lambda kv: -kv[1]):
        if count:
            print(f"  {name[:64]:<66}{count:>7,}")
    print(
        "The stored frame, family and slope were measured on the sideways image and are "
        "deliberately not used; these are read with the generic rule on an upright page."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
