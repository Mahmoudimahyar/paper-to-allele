#!/usr/bin/env python3
"""Measure the geometry gate that stands between a widened header and the row.

Route (c) widens `GROUPED_DRBX_HEADER` to reach damage the strict pattern does
not, and a box only the widening reads counts as a header only where the page's
own geometry corroborates one (`drbx.find_grouped_headers`). That gate has to be
calibrated against headers we already believe: if it rejected the real thing, it
would be measuring something other than "where a header stands".

So this walks the pages whose header the STRICT pattern reads, applies the gate
to it, and writes what it found to a fixture the contract test re-checks. The
fixture holds geometry and form vocabulary only — box rectangles and the locus
each label canonicalises to. No page text, no document identifiers, nothing that
varies with the patient.

Read-only: every store is opened `mode=ro`.

    python scripts/drbx_header_calibration.py            # rewrite the fixture
    python scripts/drbx_header_calibration.py --print    # measure, write nothing
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

from extract_facts import frame_for, load_geometry  # noqa: E402
from page_ocr_bind import Document  # noqa: E402

from kidneymatch.ocr.anchors import Box, find_anchors, locus_anchors  # noqa: E402
from kidneymatch.ocr.drbx import (  # noqa: E402
    STRICT_GROUPED_DRBX_HEADER,
    _geometry_corroborates_header,
    _label_column_pitch,
)

FIXTURE = ROOT / "tests/fixtures/drbx_header_gate.json"
SCHEMA = "drbx-header-gate/v1"
# One page in this many is written to the fixture, so the committed file stays
# small while the contract test still re-runs the gate on real geometry. The
# fixture's job is to catch a regression in the gate, not to re-measure the
# corpus: the corpus counters below carry the calibration itself.
SAMPLE_EVERY = 40
# Normalised coordinates, rounded. 1e-5 of a page is a hundredth of a pixel on
# these photographs and three orders of magnitude under the gate's tolerances.
PLACES = 5


def _rect(box: Box) -> list[float]:
    return [round(value, PLACES) for value in (box.x0, box.y0, box.x1, box.y1)]


def page_rows(ocr: sqlite3.Connection):
    for sha, rel, boxes_json, texts_json, width, height in ocr.execute(
        "SELECT sha256, rel_path, boxes_json, texts_json, width, height FROM ocr_result "
        "WHERE n_boxes>0"
    ):
        if "_thumb" in rel:
            continue
        raw, texts = json.loads(boxes_json), json.loads(texts_json)
        if len(raw) != len(texts):
            continue
        yield (
            sha,
            [Box(b[0], b[1], b[2], b[3], t) for b, t in zip(raw, texts, strict=True)],
            (
                int(width or 1),
                int(height or 1),
            ),
        )


def measure(ocr_db: Path, geometry_db: Path) -> tuple[Counter[str], list[dict]]:
    ocr = sqlite3.connect(f"file:{ocr_db.as_posix()}?mode=ro", uri=True)
    geometry = load_geometry(geometry_db)
    tally: Counter[str] = Counter()
    sample: list[dict] = []
    try:
        for sha, boxes, (width, height) in page_rows(ocr):
            headers = [b for b in boxes if STRICT_GROUPED_DRBX_HEADER.match((b.text or "").strip())]
            if len(headers) != 1:
                tally["pages without exactly one strict header"] += 1
                continue
            frame = frame_for(Document(sha, width, height), geometry)
            if frame is not None:
                boxes = frame.rectify(boxes)[0]
                headers = [
                    b for b in boxes if STRICT_GROUPED_DRBX_HEADER.match((b.text or "").strip())
                ]
                if len(headers) != 1:
                    continue
            header = headers[0]
            tally["strict headers measured"] += 1
            applicable = (
                len(find_anchors(boxes, "DRB1")) == 1 and _label_column_pitch(boxes) is not None
            )
            passed = _geometry_corroborates_header(header, boxes)
            tally["the gate is applicable"] += int(applicable)
            tally["headers the gate passes"] += int(passed)
            tally["applicable headers the gate passes"] += int(applicable and passed)
            if tally["strict headers measured"] % SAMPLE_EVERY == 0:
                sample.append(
                    {
                        "header": _rect(header),
                        "labels": [
                            [locus, *_rect(box)]
                            for locus, box in locus_anchors(boxes)
                            if box is not header
                        ],
                        "applicable": applicable,
                        "passes": passed,
                    }
                )
    finally:
        ocr.close()
    return tally, sample


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ocr", type=Path, default=ROOT / "data/derived/ocr_pass.sqlite")
    parser.add_argument("--geometry", type=Path, default=ROOT / "data/derived/geometry.sqlite")
    parser.add_argument("--out", type=Path, default=FIXTURE)
    parser.add_argument("--print", action="store_true", help="measure and write no fixture")
    args = parser.parse_args()
    if not args.ocr.exists():
        print(f"missing {args.ocr}")
        return 2
    tally, sample = measure(args.ocr, args.geometry)
    measured = tally["strict headers measured"]
    for name, count in sorted(tally.items()):
        print(f"  {name:<48}{count:>9,}")
    if measured:
        rate = tally["headers the gate passes"] / measured
        print(f"  gate pass rate                                  {rate:>9.3%}")
        applicable = tally["the gate is applicable"]
        if applicable:
            of_applicable = tally["applicable headers the gate passes"] / applicable
            print(f"  ... of the headers it can be applied to         {of_applicable:>9.3%}")
    if args.print:
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "schema": SCHEMA,
                "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
                "generated_by": "python scripts/drbx_header_calibration.py",
                "note": (
                    "Geometry and form vocabulary only: box rectangles and the locus each "
                    "printed label canonicalises to, from pages whose grouped header the "
                    "strict pattern reads. No page text, no document identifiers."
                ),
                "sample_every": SAMPLE_EVERY,
                "corpus": {name: count for name, count in sorted(tally.items())},
                "rows": sample,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"wrote {args.out} ({len(sample):,} sampled pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
