#!/usr/bin/env python3
"""Generate the labelling tasks and crops for the golden corpus.

One task per (document, locus) cell, each with three pictures: the cell, the row
it sits on, and the whole page. A labeller decides from the cell, checks the row
when the cell is ambiguous, and opens the page when the row is not enough.

**The OCR proposal is not in the tasks file.** It goes to a separate
`hidden.json` that the labelling page never loads. A proposal shown beside a
blurry crop is an anchor: the labeller would be measuring their agreement with
the machine rather than reading the form, and the whole point of this corpus is
to be independent of it.

Crops are PHI and land in gitignored `data/review/golden/`.

Usage:
    uv run --frozen --extra hist --extra ocr python scripts/golden_tasks.py
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kidneymatch.hla.vocabulary import load_vocabulary  # noqa: E402
from kidneymatch.review.golden import LabelState, Resolution  # noqa: E402

SCHEMA_VERSION = "golden-tasks/v1"

LOCI = ("A", "B", "C", "DRB1", "DQA1", "DQB1", "DPA1", "DPB1")
GENES = ("DRB3", "DRB4", "DRB5")

# How much page to show around a cell, as a fraction of the page.
CELL_PAD_X = 0.02
CELL_PAD_Y = 0.012
PAGE_MAX_EDGE = 1400


def _crop(image, box: list[float], pad_x: float, pad_y: float, out: Path) -> None:
    width, height = image.size
    x0 = max(0, int((box[0] - pad_x) * width))
    y0 = max(0, int((box[1] - pad_y) * height))
    x1 = min(width, int((box[2] + pad_x) * width))
    y1 = min(height, int((box[3] + pad_y) * height))
    if x1 <= x0 or y1 <= y0:
        return
    image.crop((x0, y0, x1, y1)).save(out, quality=92)


def build(facts_db: Path, golden: Path, export: Path, out_dir: Path) -> int:
    from PIL import Image

    vocabulary = load_vocabulary()
    documents = json.loads(golden.read_text(encoding="utf-8"))["documents"]
    wanted = {d["sha256"]: d for d in documents}

    con = sqlite3.connect(facts_db)
    rows = list(
        con.execute(
            "SELECT sha256, field, status, value, anchor_box, value_boxes, rule_id, "
            "second_allele FROM fact WHERE extraction_version='facts/v1'"
        )
    )
    paths = dict(con.execute("SELECT sha256, rel_path FROM document"))
    con.close()

    crops_dir = out_dir / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)

    tasks: list[dict] = []
    hidden: dict[str, dict] = {}
    by_document: dict[str, list[tuple]] = {}
    for sha, field, status, value, anchor_box, value_boxes, rule_id, second in rows:
        if sha in wanted and field in (*LOCI, *GENES):
            by_document.setdefault(sha, []).append(
                (field, status, value, anchor_box, value_boxes, rule_id, second)
            )

    tally: Counter[str] = Counter()
    for sha, cells in sorted(by_document.items()):
        rel_path = paths.get(sha) or wanted[sha]["rel_path"]
        source = export / rel_path
        image = None
        if source.exists():
            try:
                image = Image.open(source).convert("RGB")
            except OSError:
                image = None

        page_name = f"{sha[:16]}_page.jpg"
        if image is not None and not (crops_dir / page_name).exists():
            page = image.copy()
            page.thumbnail((PAGE_MAX_EDGE, PAGE_MAX_EDGE))
            page.save(crops_dir / page_name, quality=85)

        for field, status, value, anchor_box, value_boxes, rule_id, second in sorted(
            cells, key=lambda c: c[0]
        ):
            cell_id = f"{sha[:16]}:{field}"
            anchor = json.loads(anchor_box) if anchor_box else None
            values = json.loads(value_boxes) if value_boxes else []

            cell_name = row_name = None
            if image is not None and anchor is not None:
                span = [
                    min([anchor[0], *[b[0] for b in values]]),
                    min([anchor[1], *[b[1] for b in values]]),
                    max([anchor[2], *[b[2] for b in values]]),
                    max([anchor[3], *[b[3] for b in values]]),
                ]
                cell_name = f"{sha[:16]}_{field}_cell.jpg"
                row_name = f"{sha[:16]}_{field}_row.jpg"
                _crop(image, span, CELL_PAD_X, CELL_PAD_Y, crops_dir / cell_name)
                _crop(
                    image,
                    [0.0, anchor[1], 1.0, anchor[3]],
                    0.0,
                    CELL_PAD_Y * 2,
                    crops_dir / row_name,
                )

            is_gene = field in GENES
            tasks.append(
                {
                    "cell_id": cell_id,
                    "sha256": sha,
                    "locus": field,
                    "kind": "presence" if is_gene else "allele",
                    "crops": {"cell": cell_name, "row": row_name, "page": page_name},
                    "states": [
                        state.value
                        for state in LabelState
                        if state is not LabelState.PRESENT_ONLY or is_gene
                    ],
                    "resolutions": [r.value for r in Resolution],
                    # A pick-list from the reference table, so a typed value
                    # outside it has to be a deliberate act.
                    "picklist": sorted(vocabulary.first_fields(field))[:60] if not is_gene else [],
                }
            )
            # The pipeline's own declaration of whether it read a second allele
            # (KI-015) rides along so the scorer can tell an honest partial read
            # from a value claimed complete. Still never loaded by the page.
            hidden[cell_id] = {
                "status": status,
                "locus": field,
                "value": value,
                "rule": rule_id,
                "second_allele": second,
            }
            tally[status] += 1

    (out_dir / "tasks.json").write_text(
        json.dumps(
            {
                "schema": SCHEMA_VERSION,
                "imgt_version": vocabulary.imgt_version,
                "n_tasks": len(tasks),
                "instructions": (
                    "Read the cell. Use the row when the cell is ambiguous and the page when "
                    "the row is not enough. Record what the FORM says, never what you expect. "
                    "If you cannot read it, say so: UNREADABLE is a real answer and a guess is "
                    "worse than none."
                ),
                "tasks": tasks,
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    # Never loaded by the labelling page.
    (out_dir / "hidden.json").write_text(
        json.dumps({"schema": "golden-hidden/v1", "cells": hidden}, indent=1) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    print(f"documents : {len(by_document):,}")
    print(f"tasks     : {len(tasks):,}")
    for status, count in tally.most_common():
        print(f"  pipeline {status:<18}{count:>6,}")
    accepted = tally["RESOLVED"]
    if accepted:
        print(f"\nzero failures over {accepted:,} accepted cells would bound false")
        print(f"acceptance at {3 / accepted:.3%} (rule of three, 95%).")
    print(f"\nwritten to {out_dir.relative_to(ROOT)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--golden", type=Path, default=ROOT / "data/derived/golden_sample.json")
    parser.add_argument("--export", type=Path, default=ROOT / "data/raw/ChatExport_2026-08-31")
    parser.add_argument("--out", type=Path, default=ROOT / "data/review/golden")
    args = parser.parse_args()
    for path in (args.facts, args.golden):
        if not path.exists():
            print(f"missing {path}")
            return 2
    return build(args.facts, args.golden, args.export, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
