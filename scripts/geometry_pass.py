#!/usr/bin/env python3
"""Page geometry over the archive: how tilted each report is, and whether that
may be trusted. Resumable.

The pipeline binds a value to its locus by the printed row, and a printed row
on a tilted photograph is not a horizontal band: measured on the first 165
anchored labels, the second allele column drifts out of the row test at about
2-3 degrees. This pass measures the tilt from the page's own rulings
(`kidneymatch.ocr.rulings`) and records a decision per document — STRAIGHT,
ROTATE with an angle, or UNCERTAIN with the reason — that `extract_facts.py`
consumes to rectify the stored boxes before the row rules run.

Nothing here touches `ocr_pass.sqlite`, and nothing rotates a pixel: the pass
writes numbers and the rulings' coordinates. Pixels are rotated later, per crop,
only for documents this pass declared ROTATE.

Design points shared with `ocr_pass.py`:

* **Keyed by content and version.** `(sha256, geometry_version)`; a changed
  estimator gets a new version string and re-reads, the old rows stay.
* **Batch-committed and resumable.** A crash loses at most one batch.
* **Counts only on the console.** The output is geometry, not text, but the
  discipline is the same: nothing about an individual document is printed.

Usage:
    python scripts/geometry_pass.py --pack data/review/hla_pack   # the pack's documents first
    python scripts/geometry_pass.py --limit 500                    # then a slice of the corpus
    python scripts/geometry_pass.py --status
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from kidneymatch.ocr.rulings import PageGeometry, page_geometry  # noqa: E402

# v2: the scatter bound calibrated on real photographs (1.5 deg) and the
# vertical family demoted from a veto to the perspective flag.
GEOMETRY_VERSION = "rulings/v2+lsd+sweep"

DEFAULT_EXPORT = ROOT / "data/raw/ChatExport_2026-08-31"
DEFAULT_DB = ROOT / "data/derived/geometry.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS page_geometry (
    sha256            TEXT NOT NULL,
    geometry_version  TEXT NOT NULL,
    rel_path          TEXT NOT NULL,
    width             INTEGER,
    height            INTEGER,
    decision          TEXT NOT NULL,
    theta_deg         REAL NOT NULL,
    n_horizontal      INTEGER,
    n_vertical        INTEGER,
    mad_horizontal    REAL,
    mad_vertical      REAL,
    theta_rulings     REAL,
    theta_vertical    REAL,
    perspective_flag  INTEGER NOT NULL DEFAULT 0,
    sweep_theta       REAL,
    sweep_ratio       REAL,
    sweep_max         REAL,
    h_rulings_json    TEXT,
    v_rulings_json    TEXT,
    reason            TEXT,
    elapsed_ms        REAL,
    error             TEXT,
    created_utc       TEXT NOT NULL,
    PRIMARY KEY (sha256, geometry_version)
);
CREATE INDEX IF NOT EXISTS idx_geometry_decision ON page_geometry(geometry_version, decision);
"""

COLUMNS = (
    "sha256, geometry_version, rel_path, width, height, decision, theta_deg, n_horizontal, "
    "n_vertical, mad_horizontal, mad_vertical, theta_rulings, theta_vertical, perspective_flag, "
    "sweep_theta, sweep_ratio, sweep_max, h_rulings_json, v_rulings_json, reason, elapsed_ms, "
    "error, created_utc"
)


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    return conn


def completed(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT sha256 FROM page_geometry WHERE geometry_version=?", (GEOMETRY_VERSION,)
    )
    return {r[0] for r in rows}


def _segments_json(segments: tuple) -> str:
    # Source-pixel coordinates to one decimal; a ruled page holds a few dozen.
    return json.dumps(
        [[round(s.x0, 1), round(s.y0, 1), round(s.x1, 1), round(s.y1, 1)] for s in segments],
        separators=(",", ":"),
    )


def analyse(path: Path) -> dict[str, object]:
    """One document's geometry, as a row. Never returns or prints any text."""
    import numpy as np
    from PIL import Image

    started = time.perf_counter()
    with Image.open(path) as opened:
        gray = np.asarray(opened.convert("L"))
    height, width = gray.shape[:2]
    result: PageGeometry = page_geometry(gray)
    rulings = result.rulings
    sweep = result.sweep
    return {
        "width": int(width),
        "height": int(height),
        "decision": result.decision.value,
        "theta_deg": float(result.theta_deg),
        "n_horizontal": rulings.n_horizontal,
        "n_vertical": rulings.n_vertical,
        "mad_horizontal": rulings.mad_horizontal_deg,
        "mad_vertical": rulings.mad_vertical_deg,
        "theta_rulings": rulings.theta_deg,
        "theta_vertical": rulings.theta_vertical_deg,
        "perspective_flag": int(rulings.perspective_flag),
        "sweep_theta": None if sweep is None else sweep.theta_deg,
        "sweep_ratio": None if sweep is None else sweep.ratio,
        "sweep_max": None if sweep is None else sweep.max_score,
        "h_rulings_json": _segments_json(rulings.horizontal),
        "v_rulings_json": _segments_json(rulings.vertical),
        "reason": result.reason,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        "error": None,
    }


def _failed(error: str) -> dict[str, object]:
    return {
        "width": None,
        "height": None,
        "decision": "UNCERTAIN",
        "theta_deg": 0.0,
        "n_horizontal": 0,
        "n_vertical": 0,
        "mad_horizontal": None,
        "mad_vertical": None,
        "theta_rulings": None,
        "theta_vertical": None,
        "perspective_flag": 0,
        "sweep_theta": None,
        "sweep_ratio": None,
        "sweep_max": None,
        "h_rulings_json": None,
        "v_rulings_json": None,
        "reason": "the image could not be analysed",
        "elapsed_ms": None,
        "error": error,
    }


def pack_documents(pack_dir: Path) -> set[str]:
    """The full SHA-256 of every document in a review pack."""
    payload = json.loads((pack_dir / "pack.json").read_text(encoding="utf-8"))
    return {str(d["sha256"]) for d in payload["documents"] if d.get("sha256")}


def run(
    export: Path,
    db_path: Path,
    limit: int | None,
    batch_size: int,
    only: set[str] | None = None,
) -> int:
    from ocr_pass import unique_originals  # noqa: PLC0415 - sibling script, not a package

    conn = connect(db_path)
    print(f"indexing unique originals under {export.name} ...", flush=True)
    work = unique_originals(export)
    done = completed(conn)
    todo = [(d, p) for d, p in work if d not in done and (only is None or d in only)]
    if limit:
        todo = todo[:limit]
    print(
        f"{len(work):,} unique originals, {len(done):,} done, {len(todo):,} to analyse", flush=True
    )

    tally: Counter[str] = Counter()
    pending: list[tuple] = []
    started = time.perf_counter()
    for n, (digest, path) in enumerate(todo, 1):
        try:
            row = analyse(path)
        except Exception as error:  # noqa: BLE001 - one bad image must not stop a multi-hour run
            row = _failed(f"{type(error).__name__}: {error}"[:200])
        tally[str(row["decision"]) if not row["error"] else "ERROR"] += 1
        pending.append(
            (
                digest,
                GEOMETRY_VERSION,
                path.relative_to(export).as_posix(),
                *[
                    row[k]
                    for k in (
                        "width",
                        "height",
                        "decision",
                        "theta_deg",
                        "n_horizontal",
                        "n_vertical",
                        "mad_horizontal",
                        "mad_vertical",
                        "theta_rulings",
                        "theta_vertical",
                        "perspective_flag",
                        "sweep_theta",
                        "sweep_ratio",
                        "sweep_max",
                        "h_rulings_json",
                        "v_rulings_json",
                        "reason",
                        "elapsed_ms",
                        "error",
                    )
                ],
                datetime.now(UTC).isoformat(timespec="seconds"),
            )
        )
        if len(pending) >= batch_size:
            conn.executemany(
                f"INSERT OR REPLACE INTO page_geometry ({COLUMNS}) VALUES ({','.join('?' * 23)})",
                pending,
            )
            conn.commit()
            pending.clear()
            rate = n / max(time.perf_counter() - started, 1e-6)
            print(f"  {n:,}/{len(todo):,}  {rate:.1f} img/s  {dict(tally)}", flush=True)
    if pending:
        conn.executemany(
            f"INSERT OR REPLACE INTO page_geometry ({COLUMNS}) VALUES ({','.join('?' * 23)})",
            pending,
        )
        conn.commit()
    conn.close()
    elapsed = time.perf_counter() - started
    print(f"analysed {len(todo):,} in {elapsed:.0f}s: {dict(tally)}")
    return 0


def status(db_path: Path) -> int:
    if not db_path.exists():
        print("no geometry pass yet")
        return 0
    conn = connect(db_path)
    rows = conn.execute(
        "SELECT decision, COUNT(*), AVG(elapsed_ms) FROM page_geometry WHERE geometry_version=? "
        "GROUP BY decision",
        (GEOMETRY_VERSION,),
    ).fetchall()
    total = sum(r[1] for r in rows)
    print(f"geometry {GEOMETRY_VERSION}: {total:,} documents")
    for decision, count, ms in rows:
        print(f"  {decision:<10} {count:>7,}  ({count / max(total, 1):.1%})  {ms or 0:.0f} ms/img")
    bins = [(0.5, 1), (1, 2), (2, 3), (3, 5), (5, 10), (10, 90)]
    print("  ROTATE by |theta|:")
    for lo, hi in bins:
        (k,) = conn.execute(
            "SELECT COUNT(*) FROM page_geometry WHERE geometry_version=? AND decision='ROTATE' "
            "AND ABS(theta_deg) >= ? AND ABS(theta_deg) < ?",
            (GEOMETRY_VERSION, lo, hi),
        ).fetchone()
        print(f"    {lo:>4}-{hi:<3} deg {k:>7,}")
    (flagged,) = conn.execute(
        "SELECT COUNT(*) FROM page_geometry WHERE geometry_version=? AND perspective_flag=1",
        (GEOMETRY_VERSION,),
    ).fetchone()
    print(f"  perspective flagged: {flagged:,}")
    conn.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", type=Path, default=DEFAULT_EXPORT)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--batch", type=int, default=50)
    parser.add_argument(
        "--pack", type=Path, default=None, help="analyse only this review pack's documents"
    )
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if args.status:
        return status(args.db)
    only = pack_documents(args.pack) if args.pack else None
    return run(args.export, args.db, args.limit, args.batch, only)


if __name__ == "__main__":
    raise SystemExit(main())
