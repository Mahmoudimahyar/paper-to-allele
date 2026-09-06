#!/usr/bin/env python3
"""Read the WHOLE page with a detector, not our crops with a recognizer.

The pipeline detects text with OnnxTR `fast_base` and then asks PP-OCR to
re-read the crops that detector drew. Every second opinion the project has
bought so far has therefore been an opinion about the same boxes: if the
detector never drew a box, no recognizer was ever asked about it. The reviewer
put it plainly — "you are just feeding them the cropped image, what if we give
them the entire image? there are some OCR models that understand the structure
very well."

Measured on the page a reviewer marked "this lab report has totally different
structure": our detector produced 38 boxes and found `HLA-A` and `HLA-C` and
not `HLA-B`. PaddleOCR reading the whole page produced 31 text lines and found
all three, each one a column header with its value in the same column directly
underneath — which is the structure the note describes and the structure our
boxes could not show.

So this pass runs PP-OCRv5-server detection AND recognition over whole pages,
locally, and stores the lines in the frame `ocr_pass.sqlite` uses so that
`ocr/anchors.py` can be pointed at either store and asked the same question
(`scripts/vision_compare.py`). It is a measuring instrument: it writes no fact,
and the locus still comes from geometry rather than from any text.

Nothing leaves the machine. The models are the ones already vendored for the
confirmers, and the page never goes anywhere.

Usage:
    uv run --frozen --extra confirm python scripts/page_ocr_pass.py --pack
    uv run --frozen --extra confirm python scripts/page_ocr_pass.py \\
        --from-export <labels.json>
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

from vision_pass import (  # noqa: E402
    ALLOWED_OUTPUT_ROOT,
    documents_from_export,
    documents_from_pack,
)

# PP-OCRv6's detector does not run on this Paddle build (`oneDNN` refuses the
# attribute conversion), and v5-server is the best detector that does. The
# recognizer is matched to it rather than mixed, so the reading is one engine's.
DETECTION_MODEL = "PP-OCRv5_server_det"
RECOGNITION_MODEL = "PP-OCRv5_server_rec"
ENGINE_VERSION = f"paddleocr/{DETECTION_MODEL}+{RECOGNITION_MODEL}+wholepage"

SCHEMA = """
CREATE TABLE IF NOT EXISTS page_ocr_result (
    sha256          TEXT NOT NULL,
    engine_version  TEXT NOT NULL,
    rel_path        TEXT NOT NULL,
    width           INTEGER,
    height          INTEGER,
    n_boxes         INTEGER,
    boxes_json      TEXT,
    texts_json      TEXT,
    confs_json      TEXT,
    elapsed_ms      INTEGER,
    error           TEXT,
    created_utc     TEXT NOT NULL,
    PRIMARY KEY (sha256, engine_version)
);
"""


def build_engine():  # type: ignore[no-untyped-def]
    """Detection and recognition over a whole page, on the CPU, offline."""
    from paddleocr import PaddleOCR  # noqa: PLC0415

    return PaddleOCR(
        text_detection_model_name=DETECTION_MODEL,
        text_recognition_model_name=RECOGNITION_MODEL,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        enable_mkldnn=False,
        device="cpu",
    )


def read_page(
    engine, array, width: int, height: int
) -> tuple[list[list[float]], list[str], list[float]]:
    """Normalised boxes, their texts and their scores, in reading order."""
    boxes: list[list[float]] = []
    texts: list[str] = []
    scores: list[float] = []
    for result in engine.predict(input=array):
        polygons = result.get("rec_polys") if isinstance(result, dict) else None
        readings = result.get("rec_texts") if isinstance(result, dict) else None
        confidences = result.get("rec_scores") if isinstance(result, dict) else None
        for index, polygon in enumerate(polygons or []):
            xs = [float(point[0]) for point in polygon]
            ys = [float(point[1]) for point in polygon]
            if not xs or not ys or width <= 0 or height <= 0:
                continue
            box = [
                round(min(xs) / width, 6),
                round(min(ys) / height, 6),
                round(max(xs) / width, 6),
                round(max(ys) / height, 6),
            ]
            if box[2] <= box[0] or box[3] <= box[1]:
                continue
            boxes.append(box)
            texts.append(str((readings or [""] * (index + 1))[index] or ""))
            scores.append(float((confidences or [0.0] * (index + 1))[index] or 0.0))
    order = sorted(range(len(boxes)), key=lambda i: (boxes[i][1], boxes[i][0]))
    return (
        [boxes[i] for i in order],
        [texts[i] for i in order],
        [scores[i] for i in order],
    )


def run(
    documents: list[tuple[str, str]],
    export_dir: Path,
    out: Path,
    *,
    limit: int | None = None,
) -> Counter[str]:
    import numpy as np  # noqa: PLC0415
    from PIL import Image, UnidentifiedImageError  # noqa: PLC0415

    con = sqlite3.connect(out)
    con.executescript(SCHEMA)
    done = {
        row[0]
        for row in con.execute(
            "SELECT sha256 FROM page_ocr_result WHERE engine_version=? AND error IS NULL",
            (ENGINE_VERSION,),
        )
    }
    unread = [(sha, rel) for sha, rel in documents if sha not in done]
    work = unread if limit is None else (unread[:limit] if limit > 0 else [])
    tally: Counter[str] = Counter()
    tally["already read on an earlier run"] = len(documents) - len(unread)
    tally["held back by --limit"] = len(unread) - len(work)
    if not work:
        return tally
    engine = build_engine()
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    for index, (sha, rel) in enumerate(work, 1):
        path = export_dir / rel
        try:
            with Image.open(path) as image:
                width, height = image.size
                array = np.asarray(image.convert("RGB"))[:, :, ::-1]
        except (OSError, UnidentifiedImageError):
            tally["image unreadable"] += 1
            continue
        started = time.monotonic()
        try:
            boxes, texts, scores = read_page(engine, array, width, height)
            problem = None
        except Exception as failure:  # noqa: BLE001 - one page must not stop the pass
            boxes, texts, scores = [], [], []
            problem = f"{failure.__class__.__name__}: {failure}"[:200]
            tally[f"failed: {failure.__class__.__name__}"] += 1
        con.execute(
            "INSERT OR REPLACE INTO page_ocr_result VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                sha,
                ENGINE_VERSION,
                rel,
                width,
                height,
                len(boxes),
                json.dumps(boxes) if problem is None else None,
                json.dumps(texts) if problem is None else None,
                json.dumps([round(s, 4) for s in scores]) if problem is None else None,
                int((time.monotonic() - started) * 1000),
                problem,
                now,
            ),
        )
        con.commit()
        if problem is None:
            tally["pages read"] += 1
            tally["text lines"] += len(boxes)
        if index % 10 == 0 or index == len(work):
            print(f"  {index}/{len(work)} pages", flush=True)
    con.close()
    return tally


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--export", type=Path, default=ROOT / "data/raw/ChatExport_2026-08-31")
    parser.add_argument("--out", type=Path, default=ALLOWED_OUTPUT_ROOT / "page_ocr.sqlite")
    parser.add_argument("--pack-json", type=Path, default=ROOT / "data/review/hla_pack/pack.json")
    parser.add_argument("--from-export", type=Path, nargs="*", default=None)
    parser.add_argument("--pack", action="store_true", help="every document of the review pack")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    if not args.out.resolve().is_relative_to(ALLOWED_OUTPUT_ROOT.resolve()):
        print(
            f"--out must be under {ALLOWED_OUTPUT_ROOT.relative_to(ROOT).as_posix()}/, the "
            "ignored tree; this store holds the text of real report pages."
        )
        return 2
    documents: list[tuple[str, str]] = []
    failed: list[Path] = []
    if args.from_export:
        found, bad = documents_from_export(list(args.from_export), args.facts)
        documents += found
        failed += bad
    if args.pack:
        found, bad = documents_from_pack(args.pack_json, args.facts)
        documents += found
        failed += bad
    if failed:
        print("could not read, and the sample would have been silently smaller:")
        for path in failed:
            print(f"  {path}")
        return 2
    documents = sorted(set(documents))
    if not documents:
        print("no documents named: pass --from-export <labels.json> or --pack.")
        return 2
    print(f"reading {len(documents)} whole pages with {ENGINE_VERSION}")
    tally = run(documents, args.export, args.out, limit=args.limit)
    for name, count in sorted(tally.items()):
        if count:
            print(f"  {name:<52}{count:>8,}")
    print(f"stored in {args.out.name}; it is PHI, gitignored, and writes no fact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
