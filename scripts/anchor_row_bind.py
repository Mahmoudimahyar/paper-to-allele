#!/usr/bin/env python3
"""Bind a value the cell rectangle missed but the anchor's own row still holds.

`prefix_bind.py` handles the page that labels NO row: there, the allele's
printed prefix is the only thing naming a gene, and the pass is fenced to loci
with no anchor anywhere so that geometry always gets first refusal.

This is the other half, and it is a stronger claim rather than a weaker one.
"anchor found but no box at all in its cell under this rule" is the second
largest refusal in the corpus — 23,986 cells. Most of it is blank paper, which
is HA-012's question and not this pass's. But on some pages the label was read,
the row is known, and the value is sitting on that row: what failed was the
CELL RECTANGLE the rule computed, not the reading.

So both signals must agree, and neither is trusted alone:

* the **row** comes from the printed anchor — geometry, exactly as the project
  requires, and the value must sit on it when followed at the page's own slope;
* the **locus** comes from the value's own printed prefix — nomenclature, the
  CV_RESEARCH s12 decision, which is what lets us tell `A*11` from the value in
  the next row down.

### What the first version got wrong

An adversarial review of that argument confirmed eleven defects, two of them
fatal to it, and the gates below exist because of them. They are recorded here
rather than in the history because the argument is the safety case:

**"On the anchor's row" was a stripe across the whole page.** There was no
distance cap and no direction. Measured on that version's own 458 binds: the
gap from the label ran to 69 anchor heights, 87% of bound boxes sat past the
`max_gap=20` the ordinary resolver enforces on the very same pages, and twelve
boxes were to the LEFT of their own label — which no rule in this pipeline
reads. `_candidates` explains exactly why the cap exists: "measuring both from
the anchor would need a max_gap large enough to also reach into the next
column, which is exactly how a value gets bound to the wrong locus."

**It published the case the project reserves for a human.** Two loci on one
printed band is a normal layout. With `HLA-A`'s own cell blank and `A*24`
sitting inside `HLA-B`'s printed cell, `resolve_locus` refuses that box with
"value names A but the anchor is B; geometry and text disagree" — the rule that
says when geometry and text disagree, neither wins. The first version resolved
it. Prefix agreement does not establish which cell a box came from.

### The gates

* the value must sit **to the right of the label** (`x0 > anchor.x1`), as
  `_candidates` and `resolve_in_row` both require;
* it must sit within **`MAX_GAP` anchor heights**, measured from the previous
  cell in the chain rather than from the anchor, exactly as `_candidates` does;
* it must not be **owned by a nearer label** (`_owned_by_another_anchor`).
  This is the gate whose absence let a value in another locus's cell through;
* exactly ONE anchor for the locus on the page. Two anchors mean two rows could
  own the value, which is the ambiguity `2 anchors found; cannot decide which
  row owns the value` already refuses, and this pass must not paper over it;
* the cell must have been refused for exactly the empty-cell reason. Any other
  refusal — too many candidates, an inadmissible field — is a different
  question and is left alone;
* a **star-less token on the row TAINTS the row** rather than being skipped
  past. `A24` parses with a prefix and `separator_missing`, and skipping it
  hid it from `MAX_VALUES` entirely, so a row of three tokens could bind two;
* the value must be admissible, and a locus may not take more values than it
  can have;
* a comparison sheet is refused outright — and the guard **fails CLOSED**: if
  the sheet query cannot run, no page is processed, because the alternative is
  binding the right gene of the wrong person;
* every fact records the boxes it was read from, so a reviewer sees the crop.

Every fact carries `source='anchor-row-prefix'` so the whole group can be found
and withdrawn if the decision is reversed.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from extract_facts import DEFAULT_RULE, frame_for, load_geometry, load_rulings  # noqa: E402
from page_ocr_bind import Document, slopes_for  # noqa: E402
from prefix_bind import ROW_TOLERANCE, page_boxes  # noqa: E402

from kidneymatch.hla.vocabulary import load_vocabulary  # noqa: E402
from kidneymatch.ocr.anchors import (  # noqa: E402
    Box,
    _owned_by_another_anchor,
    find_anchors,
)
from kidneymatch.ocr.glyphs import parse_allele_values  # noqa: E402

EV = "facts/v1"
LOCI = ("A", "B", "C", "DRB1", "DQA1", "DQB1", "DPA1", "DPB1")
SOURCE = "anchor-row-prefix"
MAX_VALUES = 2
# The same cap `DEFAULT_RULE` enforces on these very pages, in anchor heights
# and measured from the previous cell in the chain. A wider one reaches into
# the next column, which is how a value gets bound to the wrong locus.
MAX_GAP = 20.0
# The one refusal this pass answers. Every other refusal is a different
# question and is left to the pass that owns it.
EMPTY_CELL = "anchor found but no box at all in its cell under this rule"
REASON = (
    "the label was read and its row is known, but the cell rectangle held no box; this value "
    "sits on the anchor's own row and names this locus in its own printed prefix, so geometry "
    "and nomenclature agree (CV_RESEARCH s12)"
)


def on_the_anchors_row(
    boxes: list[Box], anchor: Box, locus: str, vocabulary, slope: float
) -> list[Box] | None:
    """Boxes on the anchor's row whose printed prefix names this locus.

    `None` whenever the evidence is not clean, so that silence is the default
    and a bind has to be earned.
    """
    on_row: list[Box] = []
    for box in boxes:
        if box is anchor:
            continue
        if box.x0 <= anchor.x1:
            continue  # nothing in this pipeline reads leftwards of a label
        values = parse_allele_values((box.text or "").strip())
        if not values:
            continue
        lift = slope * (box.centre_x - anchor.centre_x)
        if abs(box.centre_y - lift - anchor.centre_y) > ROW_TOLERANCE * max(
            anchor.height, box.height
        ):
            continue  # allele-shaped, but not on this row
        on_row.append(box)
    on_row.sort(key=lambda b: b.x0)

    claiming: list[Box] = []
    edge = anchor.x1
    for box in on_row:
        # Measured from the PREVIOUS cell, as `_candidates` does: a second
        # allele sits two gaps from the label, and a cap large enough to reach
        # it from the anchor is large enough to reach the next column.
        if box.x0 - edge > MAX_GAP * anchor.height:
            break
        edge = box.x1
        values = parse_allele_values((box.text or "").strip())
        if any(v.locus_prefix is None or v.locus_prefix.upper() != locus.upper() for v in values):
            continue  # a value for another gene, sitting on this row
        if any(v.separator_missing for v in values):
            # `A24` parses WITH a prefix. Skipping it hid it from MAX_VALUES,
            # so a row of three tokens could bind two. It taints the row.
            return None
        if _owned_by_another_anchor(box, anchor, boxes, DEFAULT_RULE) is not None:
            # A value inside another locus's printed cell. `resolve_locus`
            # sends this to a human; agreeing prefixes do not overrule that.
            return None
        if not vocabulary.covers(locus) or any(
            not vocabulary.is_admissible(locus, v.first_field) for v in values
        ):
            return None  # a claim the vocabulary refuses taints the row
        claiming.append(box)
    if not claiming:
        return None
    if sum(len(parse_allele_values((b.text or "").strip())) for b in claiming) > MAX_VALUES:
        return None
    return claiming


def empty_cells(con: sqlite3.Connection) -> dict[str, list[str]]:
    """Loci whose label was found but whose computed cell held no box."""
    out: dict[str, list[str]] = defaultdict(list)
    placeholders = ",".join("?" * len(LOCI))
    for sha, field in con.execute(
        f"SELECT sha256, field FROM fact WHERE extraction_version=? AND field IN ({placeholders}) "
        "AND status != 'RESOLVED' AND reason = ?",
        (EV, *LOCI, EMPTY_CELL),
    ):
        out[sha].append(field)
    return dict(out)


def comparison_sheets(con: sqlite3.Connection) -> set[str]:
    """Pages holding two people. Raises rather than returning an empty set.

    This guard is the only thing standing between the pass and binding the
    right gene of the WRONG PERSON, so it must not fail open. An empty set
    from a query that could not run is indistinguishable from a corpus with no
    comparison sheets in it, and the second is not true here: there are 450.
    """
    return {
        row[0]
        for row in con.execute(
            "SELECT sha256 FROM document WHERE extraction_version=? AND comparison_sheet=1",
            (EV,),
        )
    }


def run(facts: Path, ocr_db: Path, geometry_db: Path, *, dry_run: bool) -> Counter[str]:
    vocabulary = load_vocabulary()
    con = sqlite3.connect(facts)
    ocr = sqlite3.connect(f"file:{ocr_db.as_posix()}?mode=ro", uri=True)
    geometry = load_geometry(geometry_db)
    rulings = load_rulings(geometry_db)
    sheets = comparison_sheets(con)
    work = empty_cells(con)
    tally: Counter[str] = Counter()
    tally["pages with an anchored but empty cell"] = len(work)
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    for sha, loci in sorted(work.items()):
        if sha in sheets:
            tally["comparison sheet; a row cannot say whose value it is"] += len(loci)
            continue
        boxes, width, height = page_boxes(ocr, sha)
        if not boxes:
            continue
        document = Document(sha, width, height)
        frame = frame_for(document, geometry)
        if frame is not None:
            boxes = frame.rectify(boxes)[0]
        slope, _ = slopes_for(document, rulings, frame)
        taken: dict[str, list[Box]] = {}
        anchors_for: dict[str, Box] = {}
        for locus in loci:
            anchors = find_anchors(boxes, locus)
            if len(anchors) != 1:
                tally["not exactly one anchor; which row owns it is undecided"] += 1
                continue
            anchors_for[locus] = anchors[0]
            claimed = on_the_anchors_row(boxes, anchors[0], locus, vocabulary, slope)
            if claimed is None:
                tally["nothing on the anchor's row names this locus"] += 1
                continue
            taken[locus] = claimed
        # `prefix_bind` withdraws a box claimed by two loci. Here that check is
        # provably unreachable — a box binds only when EVERY value in it names
        # the locus being asked about, so one box cannot satisfy two — and dead
        # code that looks like a safety gate is worse than no gate at all.
        for locus, claimed in taken.items():
            values = [
                v.text() for box in claimed for v in parse_allele_values((box.text or "").strip())
            ]
            tally[f"bound from the anchor's own row: {locus}"] += 1
            if dry_run:
                continue
            # The boxes travel with the fact. Without them `cell_crop_box`
            # has nothing to crop and the review page shows the reader a
            # RESOLVED medical value with no pixels behind it — which is the
            # exact defect that made 50 of one round's 220 answers unusable.
            anchor_box = anchors_for[locus]
            con.execute(
                "UPDATE fact SET status='RESOLVED', value=?, raw=?, reason=?, source=?, "
                "repaired=1, second_allele=?, anchor_box=?, value_boxes=?, created_utc=? "
                "WHERE sha256=? AND field=? AND extraction_version=?",
                (
                    " ".join(values),
                    " ".join((box.text or "").strip() for box in claimed),
                    REASON,
                    SOURCE,
                    "READ" if len(values) > 1 else "UNREAD",
                    json.dumps([anchor_box.x0, anchor_box.y0, anchor_box.x1, anchor_box.y1]),
                    json.dumps([[b.x0, b.y0, b.x1, b.y1] for b in claimed]),
                    now,
                    sha,
                    locus,
                    EV,
                ),
            )
        con.commit()
    con.close()
    ocr.close()
    return tally


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--ocr", type=Path, default=ROOT / "data/derived/ocr_pass.sqlite")
    parser.add_argument("--geometry", type=Path, default=ROOT / "data/derived/geometry.sqlite")
    parser.add_argument("--dry-run", action="store_true", help="count, change nothing")
    args = parser.parse_args()
    tally = run(args.facts, args.ocr, args.geometry, dry_run=args.dry_run)
    print(f"{'would bind' if args.dry_run else 'bound'} values from the anchor's own row")
    for name, count in sorted(tally.items()):
        if count:
            print(f"  {name:<58}{count:>8,}")
    print(
        "The row is geometry's and the locus is the value's own prefix; a bind needs BOTH, and "
        "the cell must have been refused for holding no box at all."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
