#!/usr/bin/env python3
"""Apply anchor-based locus resolution across the corpus and report the outcome.

Measures how often the ADR 0007 design resolves, abstains, or finds nothing —
per locus, over the real extracted geometry. Prints aggregates only.
"""

from __future__ import annotations

import argparse
import collections
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kidneymatch.ocr.anchors import Box, ResolutionStatus, ValueRule, resolve_locus  # noqa: E402

LOCI = ["DRB1", "DRB3", "DRB4", "DRB5", "DQA1", "DQB1", "DPA1", "DPB1"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / "data/derived/ocr_pass.sqlite")
    parser.add_argument("--direction", default="below", choices=["right", "below"])
    parser.add_argument("--same-row-tol", type=float, default=0.6)
    parser.add_argument("--max-gap", type=float, default=2.5)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    # Measured: "below" resolves 4-5x more than "right" on this corpus - these
    # forms are column-layout, with the value under its label.
    rule = ValueRule(args.direction, args.same_row_tol, args.max_gap, max_values=2)
    con = sqlite3.connect(args.db)
    query = "SELECT boxes_json, texts_json FROM ocr_result WHERE n_boxes>0"
    if args.limit:
        query += f" LIMIT {args.limit}"

    tally: dict[str, collections.Counter] = {loc: collections.Counter() for loc in LOCI}
    resolved_per_doc: collections.Counter = collections.Counter()
    docs = 0

    for boxes_json, texts_json in con.execute(query):
        raw = json.loads(boxes_json)
        texts = json.loads(texts_json)
        if len(raw) != len(texts):
            continue
        docs += 1
        boxes = [Box(b[0], b[1], b[2], b[3], t) for b, t in zip(raw, texts, strict=True)]
        n_resolved = 0
        for locus in LOCI:
            out = resolve_locus(
                boxes, locus=locus, anchor_pattern=rf"^(?:HLA[-\s]?)?{locus}$", rule=rule
            )
            tally[locus][out.status] += 1
            if out.status is ResolutionStatus.RESOLVED:
                n_resolved += 1
        resolved_per_doc[n_resolved] += 1
    con.close()

    print(f"documents: {docs:,}   rule: same_row_tol={args.same_row_tol} max_gap={args.max_gap}\n")
    print(
        f"{'locus':<8}{'resolved':>10}{'review':>9}{'unknown':>10}{'resolve rate of anchored':>26}"
    )
    for locus in LOCI:
        c = tally[locus]
        r = c[ResolutionStatus.RESOLVED]
        rev = c[ResolutionStatus.REVIEW_REQUIRED]
        unk = c[ResolutionStatus.UNKNOWN]
        anchored = r + rev
        rate = f"{100 * r / anchored:.1f}%" if anchored else "-"
        print(f"{locus:<8}{r:>10,}{rev:>9,}{unk:>10,}{rate:>26}")

    print("\nloci resolved per document:")
    for k in sorted(resolved_per_doc):
        if resolved_per_doc[k]:
            print(f"  {k}: {resolved_per_doc[k]:>7,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
