#!/usr/bin/env python3
"""Detection + recognition pass over unique archive images, resumable.

Implements stages 0-2 of ADR 0006. It extracts TEXT and its BOX GEOMETRY. It
deliberately does **not** assign an HLA locus: locus assignment needs the
template registry, which needs the golden corpus, which OCR-001 is blocked on.
This pass is what unblocks that work by producing the text and geometry needed
to classify documents, discover template families, and stratify-sample the
golden set from the HLA stratum rather than from raw noise.

Design points that matter:

* **Content-addressed and idempotent.** Results are keyed by the image SHA-256
  plus the engine and preprocessing versions. Re-running skips completed work,
  so an interrupted multi-hour run resumes where it stopped.
* **Single process.** Measured: worker pools make this SLOWER (4.36 img/s at one
  worker, 3.48 at sixteen) because ONNX Runtime already threads internally.
* **Commits every batch.** A crash loses at most one batch, not the run.
* **Output is PHI.** It is written under `data/derived/`, which is gitignored,
  and no recognized text is ever printed to the console.

Usage:
    python scripts/ocr_pass.py --limit 200          # smoke test
    python scripts/ocr_pass.py                      # full corpus, resumable
    python scripts/ocr_pass.py --status             # progress only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Bump either version to invalidate cached rows and force a re-read.
ENGINE_VERSION = "onnxtr0.9.0/fast_base+crnn_mobilenet_v3_small"
PREPROC_VERSION = "v1-none"

DEFAULT_EXPORT = ROOT / "data/raw/ChatExport_2026-08-31"
DEFAULT_DB = ROOT / "data/derived/ocr_pass.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS ocr_result (
    sha256           TEXT NOT NULL,
    engine_version   TEXT NOT NULL,
    preproc_version  TEXT NOT NULL,
    rel_path         TEXT NOT NULL,
    width            INTEGER,
    height           INTEGER,
    n_boxes          INTEGER,
    boxes_json       TEXT,
    texts_json       TEXT,
    confs_json       TEXT,
    elapsed_ms       REAL,
    error            TEXT,
    created_utc      TEXT NOT NULL,
    PRIMARY KEY (sha256, engine_version, preproc_version)
);
CREATE INDEX IF NOT EXISTS idx_ocr_created ON ocr_result(created_utc);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    # WAL keeps the file readable while a long run is in progress.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    return conn


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_original_photo(name: str) -> bool:
    """True for an original photo file; False for any thumbnail.

    The export writes `photo_N@date_thumb.jpg` next to each original AND, when
    the same thumbnail is written again, Windows-style copies named
    `photo_N@date_thumb (2).jpg`. A suffix test on `_thumb.jpg` let 9,581 of
    those copies through as "originals" and they became 29% of the OCR pass,
    the whole "low-resolution tail", and 54 of 199 golden-sample documents.
    Every one of them has its original on disk. Test on the substring.
    """
    return name.endswith(".jpg") and "_thumb" not in name


def unique_originals(export: Path) -> list[tuple[str, Path]]:
    """(sha256, path) for one representative of each distinct original photo."""
    photos = export / "photos"
    seen: dict[str, Path] = {}
    with os.scandir(photos) as it:
        for entry in it:
            if not entry.is_file() or not is_original_photo(entry.name):
                continue
            digest = sha256_file(Path(entry.path))
            seen.setdefault(digest, Path(entry.path))
    return sorted(seen.items(), key=lambda kv: kv[0])


def completed(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT sha256 FROM ocr_result WHERE engine_version=? AND preproc_version=?",
        (ENGINE_VERSION, PREPROC_VERSION),
    )
    return {r[0] for r in rows}


def build_models():
    from onnxtr.models import detection_predictor, recognition_predictor

    det = detection_predictor("fast_base", batch_size=1)
    rec = recognition_predictor("crnn_mobilenet_v3_small", batch_size=64)
    return det, rec


def process_one(det, rec, path: Path) -> dict:
    import numpy as np
    from PIL import Image

    started = time.perf_counter()
    image = np.asarray(Image.open(path).convert("RGB"))
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
        # Normalized coordinates: they stay valid if the image is later rescaled,
        # and they are what template geometry will be expressed in.
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
        "n_boxes": len(boxes),
        "boxes_json": json.dumps(boxes, separators=(",", ":")),
        "texts_json": json.dumps(texts, ensure_ascii=False, separators=(",", ":")),
        "confs_json": json.dumps(confs, separators=(",", ":")),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        "error": None,
    }


def run(export: Path, db_path: Path, limit: int | None, batch_size: int) -> int:
    conn = connect(db_path)
    print(f"indexing unique originals under {export.name} ...", flush=True)
    work = unique_originals(export)
    done = completed(conn)
    todo = [(d, p) for d, p in work if d not in done]
    if limit:
        todo = todo[:limit]

    print(f"unique originals : {len(work):,}")
    print(f"already complete : {len(done):,}")
    print(f"to process       : {len(todo):,}")
    if not todo:
        print("nothing to do")
        return 0

    det, rec = build_models()
    started = time.perf_counter()
    processed = failed = 0
    pending: list[tuple] = []

    for index, (digest, path) in enumerate(todo, 1):
        try:
            row = process_one(det, rec, path)
        except Exception as exc:  # a bad JPEG must not kill a multi-hour run
            row = {
                "width": None,
                "height": None,
                "n_boxes": 0,
                "boxes_json": "[]",
                "texts_json": "[]",
                "confs_json": "[]",
                "elapsed_ms": 0.0,
                "error": f"{type(exc).__name__}: {exc}"[:300],
            }
            failed += 1

        pending.append(
            (
                digest,
                ENGINE_VERSION,
                PREPROC_VERSION,
                str(path.relative_to(export)).replace("\\", "/"),
                row["width"],
                row["height"],
                row["n_boxes"],
                row["boxes_json"],
                row["texts_json"],
                row["confs_json"],
                row["elapsed_ms"],
                row["error"],
                datetime.now(UTC).isoformat(timespec="seconds"),
            )
        )
        processed += 1

        if len(pending) >= batch_size or index == len(todo):
            conn.executemany(
                "INSERT OR REPLACE INTO ocr_result VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", pending
            )
            conn.commit()
            pending.clear()
            elapsed = time.perf_counter() - started
            rate = processed / elapsed
            remaining = (len(todo) - processed) / rate if rate else 0
            print(
                f"  {processed:>7,}/{len(todo):,}  "
                f"{rate:5.2f} img/s  "
                f"elapsed {elapsed / 3600:5.2f} h  "
                f"eta {remaining / 3600:5.2f} h  "
                f"failed {failed}",
                flush=True,
            )

    conn.close()
    print(f"done: {processed:,} processed, {failed} failed")
    return 0


def status(db_path: Path, export: Path) -> int:
    if not db_path.exists():
        print("no database yet")
        return 0
    conn = connect(db_path)
    total, errors, boxes, ms = conn.execute(
        "SELECT COUNT(*), SUM(error IS NOT NULL), SUM(n_boxes), AVG(elapsed_ms) "
        "FROM ocr_result WHERE engine_version=? AND preproc_version=?",
        (ENGINE_VERSION, PREPROC_VERSION),
    ).fetchone()
    print(f"rows            : {total or 0:,}")
    print(f"errors          : {errors or 0:,}")
    print(f"text boxes      : {boxes or 0:,}")
    print(f"mean ms/image   : {ms or 0:.0f}")
    conn.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", type=Path, default=DEFAULT_EXPORT)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=250)
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    if args.status:
        return status(args.db, args.export)
    if not args.export.exists():
        print(f"export not found: {args.export}")
        return 2
    return run(args.export, args.db, args.limit, args.batch_size)


if __name__ == "__main__":
    raise SystemExit(main())
