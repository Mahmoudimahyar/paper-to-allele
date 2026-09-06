#!/usr/bin/env python3
"""Read the pages that were photographed sideways.

**611 documents in this archive are not upright.** They were found by a metric
that costs nothing, because it is already in `ocr_pass.sqlite`: the fraction of
detected boxes whose PIXEL height exceeds their pixel width. Latin and Persian
text boxes are wide; on a page rotated a quarter turn they are tall. Over the
23,357 documents with at least 8 boxes, `tallfrac >= 0.6` selects 611, and the
distribution is bimodal rather than a judgement call — 592 of them are above
0.8, and moving the threshold to 0.5 or 0.7 gives 621 or 599.

The separation is total: **0 of the 611 carry a single named locus anchor**,
against 83.9% of the corpus. All 4,888 of their locus cells are UNKNOWN with
reason "no anchor on this document", and none is RESOLVED, so nothing that is
currently trusted can be disturbed by re-reading them.

Three independent measurements confirm the pages are ROTATED rather than merely
unreadable — a distinction that matters, because only the first is fixable:

    ruling orientation   flagged pages are vertical-dominant on 87.7% of ruled
                         pages, median vertical share 0.784; the corpus is 6.4%
                         and 0.240 — exactly the swap a quarter turn predicts
    box aspect           median pixel height/width 2.25 on flagged pages
                         against 0.39 on a matched sample; 1/0.39 = 2.56
    re-reading           rotating and re-running detection recovers anchors

**What this is worth, measured, not assumed.** On 40 flagged documents read at
all four rotations with the pipeline's own models, 24 (60%) produce a strict
winner and 16 (40%) yield zero anchors at every rotation and stay unreadable.
Extrapolated with the corpus's own anchor-count-to-resolved-cell curve (mean
3.31 resolved cells per anchored document), that is about **1,002 newly
resolved cells** — not the 4,888 the reason strings suggest, and the difference
is the whole point of measuring. Most cells on these pages hold nothing to
recover: on the single flagged page a human has labelled, the reviewer found a
value in 2 of 11 cells.

The dangerous half of this idea is picking a rotation on thin evidence: bind
values from a wrongly-rotated page and every locus is read against the wrong
row. So the winner must beat every other rotation OUTRIGHT on named locus
anchors. A tie, or zero anchors everywhere, writes nothing and leaves the page
where it was.

Resumable by its own table, because the box this runs on powers off under
sustained load.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from kidneymatch.ocr.anchors import Box, locus_anchors  # noqa: E402

VERSION = "upright/v1"
# A page whose boxes are mostly taller than they are wide is not upright.
# Measured bimodal: 592 of the 611 selected sit above 0.8.
TALL_FRACTION = 0.6
MIN_BOXES = 8
ROTATIONS = (90, 180, 270)

SCHEMA = """
CREATE TABLE IF NOT EXISTS upright_result (
    sha256        TEXT NOT NULL,
    version       TEXT NOT NULL,
    rotation      INTEGER,
    n_anchors     INTEGER NOT NULL,
    runner_up     INTEGER NOT NULL,
    n_boxes       INTEGER NOT NULL,
    width         INTEGER,
    height        INTEGER,
    boxes_json    TEXT,
    texts_json    TEXT,
    confs_json    TEXT,
    verdict       TEXT NOT NULL,
    elapsed_ms    REAL,
    created_utc   TEXT NOT NULL,
    PRIMARY KEY (sha256, version)
)
"""


def tall_fraction(boxes: list[list[float]], width: int, height: int) -> float:
    """How many boxes are taller than wide, in PIXELS.

    The stored geometry is normalised to 0-1, so comparing the two directly
    would compare a fraction of the width with a fraction of the height and
    mean nothing. This is the step that makes the metric a measurement.
    """
    if not boxes:
        return 0.0
    tall = 0
    for b in boxes:
        if (b[3] - b[1]) * height > (b[2] - b[0]) * width:
            tall += 1
    return tall / len(boxes)


def sideways(ocr: sqlite3.Connection) -> list[tuple[str, str]]:
    """Documents whose boxes say the photograph is not upright."""
    found: list[tuple[str, str]] = []
    for sha, rel, bj, width, height in ocr.execute(
        "SELECT sha256, rel_path, boxes_json, width, height FROM ocr_result WHERE n_boxes>=?",
        (MIN_BOXES,),
    ):
        if "_thumb" in rel:
            continue
        boxes = json.loads(bj or "[]")
        if tall_fraction(boxes, int(width or 1), int(height or 1)) >= TALL_FRACTION:
            found.append((sha, rel))
    return found


def read_at(det, rec, image) -> dict:
    """Detect and recognise one already-rotated image."""
    height, width = image.shape[:2]
    out = det([image])
    raw = out[0]["words"] if isinstance(out[0], dict) else out[0]
    boxes, crops = [], []
    for box in raw:
        x0, y0, x1, y1 = (float(v) for v in box[:4])
        px0, px1 = int(x0 * width), int(x1 * width)
        py0, py1 = int(y0 * height), int(y1 * height)
        if px1 <= px0 + 2 or py1 <= py0 + 2:
            continue
        boxes.append([round(x0, 5), round(y0, 5), round(x1, 5), round(y1, 5)])
        crops.append(image[py0:py1, px0:px1])
    texts: list[str] = []
    confs: list[float] = []
    if crops:
        for text, conf in rec(crops):
            texts.append(text)
            confs.append(round(float(conf), 4))
    return {
        "width": width,
        "height": height,
        "boxes": boxes,
        "texts": texts,
        "confs": confs,
    }


def anchors_in(reading: dict) -> int:
    """How many named locus labels this reading finds."""
    boxes = [
        Box(b[0], b[1], b[2], b[3], t)
        for b, t in zip(reading["boxes"], reading["texts"], strict=False)
    ]
    return len(locus_anchors(boxes))


def run(export: Path, ocr_db: Path, out_db: Path, limit: int | None) -> int:
    import numpy as np
    from ocr_pass import build_models
    from PIL import Image

    ocr = sqlite3.connect(f"file:{ocr_db.as_posix()}?mode=ro", uri=True)
    con = sqlite3.connect(out_db)
    con.executescript(SCHEMA)
    done = {
        r[0] for r in con.execute("SELECT sha256 FROM upright_result WHERE version=?", (VERSION,))
    }
    work = [(sha, rel) for sha, rel in sideways(ocr) if sha not in done]
    print(f"{len(work):,} sideways documents to read ({len(done):,} already done)", flush=True)
    if limit:
        work = work[:limit]
    if not work:
        return 0

    det, rec = build_models()
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    won = suspect = 0
    for i, (sha, rel) in enumerate(work, 1):
        path = export / rel
        if not path.exists():
            continue
        started = time.perf_counter()
        original = Image.open(path).convert("RGB")
        readings: dict[int, dict] = {0: read_at(det, rec, np.asarray(original))}
        for angle in ROTATIONS:
            readings[angle] = read_at(det, rec, np.asarray(original.rotate(-angle, expand=True)))
        scored = sorted(
            ((anchors_in(r), angle, r) for angle, r in readings.items()),
            key=lambda t: (-t[0], t[1]),
        )
        best, runner = scored[0], scored[1]
        # The winner must beat every other rotation OUTRIGHT. A tie is not
        # evidence, and binding a locus from a wrongly-rotated page reads every
        # value against the wrong row.
        if best[0] == 0 or best[0] == runner[0]:
            verdict, rotation, reading = "ORIENTATION_SUSPECT", None, None
            suspect += 1
        else:
            verdict, rotation, reading = "UPRIGHT_FOUND", best[1], best[2]
            won += 1
        con.execute(
            "INSERT OR REPLACE INTO upright_result (sha256, version, rotation, n_anchors, "
            "runner_up, n_boxes, width, height, boxes_json, texts_json, confs_json, verdict, "
            "elapsed_ms, created_utc) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                sha,
                VERSION,
                rotation,
                best[0],
                runner[0],
                len(reading["boxes"]) if reading else 0,
                reading["width"] if reading else None,
                reading["height"] if reading else None,
                json.dumps(reading["boxes"], separators=(",", ":")) if reading else None,
                json.dumps(reading["texts"], ensure_ascii=False, separators=(",", ":"))
                if reading
                else None,
                json.dumps(reading["confs"], separators=(",", ":")) if reading else None,
                verdict,
                round((time.perf_counter() - started) * 1000, 1),
                now,
            ),
        )
        con.commit()
        if i % 20 == 0:
            print(f"  {i:,}/{len(work):,}  upright found {won:,}, suspect {suspect:,}", flush=True)
    con.close()
    ocr.close()
    print(f"read {len(work):,}: {won:,} found an upright rotation, {suspect:,} stayed suspect")
    print(
        "A rotation is taken only when it beats every other OUTRIGHT on named locus anchors; "
        "nothing is bound from a page whose orientation is a guess."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", type=Path, default=ROOT / "data/raw/ChatExport_2026-08-31")
    parser.add_argument("--ocr", type=Path, default=ROOT / "data/derived/ocr_pass.sqlite")
    parser.add_argument("--out", type=Path, default=ROOT / "data/derived/upright_pass.sqlite")
    parser.add_argument("--limit", type=int, default=None, help="stop after N documents")
    args = parser.parse_args()
    return run(args.export, args.ocr, args.out, args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
