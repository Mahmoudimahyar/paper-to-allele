#!/usr/bin/env python3
"""Persian metadata pass over the HLA typing reports. Resumable.

Stage 4 of ADR 0006. The Latin pass (`ocr_pass.py`) used a Latin-only recognizer
whose output alphabet cannot represent Persian at all, so patient, laboratory and
date metadata are entirely absent from it. This pass fills that half.

Two decisions, both measured rather than assumed:

* **EasyOCR `fa` does its OWN detection.** Feeding it the boxes already stored by
  `ocr_pass.py` was tested and is 1.4x SLOWER (2,386 vs 1,688 ms) despite
  yielding 8.5% more Persian. Those boxes are word-level, from a Latin detector;
  Persian is cursive, and line-level regions are both cheaper and more faithful
  to connected script.
* **GPU.** Measured 686 ms/image on the GTX 1070 versus a Latin-only CPU
  alternative that cannot read Persian at all. torch must be a cu121/cu126 build:
  cu128 and later dropped Pascal sm_61.

Scope: documents that carry at least two unambiguous locus labels, i.e. the
typing reports. Advertisements and screenshots are not worth the GPU time.

ENVIRONMENT: needs `easyocr` and a Pascal-compatible torch. That is not in the
repo lockfile — torch requires the PyTorch index rather than PyPI. Run with an
environment that has it:

    <venv-with-easyocr>/python scripts/persian_pass.py

Output is PHI and lands in gitignored `data/derived/persian_pass.sqlite`.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kidneymatch.ocr.glyphs import canonical_locus_label  # noqa: E402
from kidneymatch.ocr.store import read_corpus  # noqa: E402

ENGINE_VERSION = "easyocr-fa+en/gpu"
PREPROC_VERSION = "v1-none"

DEFAULT_SRC = ROOT / "data/derived/ocr_pass.sqlite"
DEFAULT_DB = ROOT / "data/derived/persian_pass.sqlite"
DEFAULT_EXPORT = ROOT / "data/raw/ChatExport_2026-08-31"

PERSIAN_RE = re.compile(r"[؀-ۿ]")

SCHEMA = """
CREATE TABLE IF NOT EXISTS persian_result (
    sha256          TEXT NOT NULL,
    engine_version  TEXT NOT NULL,
    preproc_version TEXT NOT NULL,
    rel_path        TEXT NOT NULL,
    n_boxes         INTEGER,
    boxes_json      TEXT,
    texts_json      TEXT,
    confs_json      TEXT,
    persian_chars   INTEGER,
    elapsed_ms      REAL,
    error           TEXT,
    created_utc     TEXT NOT NULL,
    PRIMARY KEY (sha256, engine_version, preproc_version)
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.executescript(SCHEMA)
    return con


def targets(src: Path, min_loci: int) -> list[tuple[str, str]]:
    """Report documents, identified by unambiguous locus LABELS in the Latin pass.

    Read through the shared corpus reader, so thumbnail copies are excluded
    (KI-009) — 1,164 of them were processed by an earlier version of this
    selection — and labels are identified by `canonical_locus_label`, which
    matches whole tokens. The regex it replaces searched for a locus name
    anywhere in a token, so `DRB1*11` counted as a DRB1 label and inflated
    apparent presence 5.18x (ADR 0007).
    """
    out = []
    for doc in read_corpus(src, with_boxes_only=True):
        found = {
            locus
            for box in doc.boxes
            if (locus := canonical_locus_label(box.text or "")) is not None
        }
        if len(found) >= min_loci:
            out.append((doc.sha256, doc.rel_path))
    return sorted(out)


def run(src: Path, db: Path, export: Path, limit: int | None, batch: int, min_loci: int) -> int:
    import numpy as np
    from PIL import Image

    con = connect(db)
    done = {
        r[0]
        for r in con.execute(
            "SELECT sha256 FROM persian_result WHERE engine_version=? AND preproc_version=?",
            (ENGINE_VERSION, PREPROC_VERSION),
        )
    }
    work = [(s, r) for s, r in targets(src, min_loci) if s not in done]
    if limit:
        work = work[:limit]
    print(f"report documents to process: {len(work):,}  (already done {len(done):,})", flush=True)
    if not work:
        print("nothing to do")
        return 0

    import easyocr

    reader = easyocr.Reader(["fa", "en"], gpu=True, verbose=False)

    started = time.perf_counter()
    pending: list[tuple] = []
    processed = failed = 0

    for index, (sha, rel) in enumerate(work, 1):
        path = export / rel
        t0 = time.perf_counter()
        boxes: list = []
        texts: list[str] = []
        confs: list[float] = []
        error = None
        try:
            image = np.asarray(Image.open(path).convert("RGB"))
            height, width = image.shape[:2]
            for box, text, conf in reader.readtext(image):
                xs = [float(p[0]) / width for p in box]
                ys = [float(p[1]) / height for p in box]
                boxes.append(
                    [round(min(xs), 5), round(min(ys), 5), round(max(xs), 5), round(max(ys), 5)]
                )
                texts.append(text)
                confs.append(round(float(conf), 4))
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:300]
            failed += 1

        pending.append(
            (
                sha,
                ENGINE_VERSION,
                PREPROC_VERSION,
                rel,
                len(boxes),
                json.dumps(boxes, separators=(",", ":")),
                json.dumps(texts, ensure_ascii=False, separators=(",", ":")),
                json.dumps(confs, separators=(",", ":")),
                len(PERSIAN_RE.findall(" ".join(texts))),
                round((time.perf_counter() - t0) * 1000, 1),
                error,
                datetime.now(UTC).isoformat(timespec="seconds"),
            )
        )
        processed += 1

        if len(pending) >= batch or index == len(work):
            con.executemany(
                "INSERT OR REPLACE INTO persian_result VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", pending
            )
            con.commit()
            pending.clear()
            elapsed = time.perf_counter() - started
            rate = processed / elapsed
            print(
                f"  {processed:>7,}/{len(work):,}  {rate:5.2f} img/s  "
                f"elapsed {elapsed / 3600:5.2f} h  "
                f"eta {(len(work) - processed) / rate / 3600:5.2f} h  "
                f"failed {failed}",
                flush=True,
            )

    con.close()
    print(f"done: {processed:,} processed, {failed} failed")
    return 0


def status(db: Path) -> int:
    if not db.exists():
        print("no database yet")
        return 0
    con = connect(db)
    rows, errors, persian, ms = con.execute(
        "SELECT COUNT(*), SUM(error IS NOT NULL), SUM(persian_chars), AVG(elapsed_ms) "
        "FROM persian_result WHERE engine_version=? AND preproc_version=?",
        (ENGINE_VERSION, PREPROC_VERSION),
    ).fetchone()
    print(f"rows          : {rows or 0:,}")
    print(f"errors        : {errors or 0:,}")
    print(f"persian chars : {persian or 0:,}")
    print(f"mean ms/image : {ms or 0:.0f}")
    con.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--export", type=Path, default=DEFAULT_EXPORT)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--min-loci", type=int, default=2)
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if args.status:
        return status(args.db)
    if not args.src.exists():
        print(f"missing {args.src}; run scripts/ocr_pass.py first")
        return 2
    return run(args.src, args.db, args.export, args.limit, args.batch_size, args.min_loci)


if __name__ == "__main__":
    raise SystemExit(main())
