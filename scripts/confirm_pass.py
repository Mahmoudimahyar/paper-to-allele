#!/usr/bin/env python3
"""Confirm resolved values with a second, independent recognizer. Resumable.

ADR 0006's unanimity rule. The primary recognizer is neural; Tesseract is from a
different era and shares no training data with it, so its agreement is real
evidence in a way a second neural engine's would not be — measured, a 2-of-3
majority across neural engines was worse than unanimity, 3.50% against 4.50%
false acceptance.

Cells are re-cropped from the ORIGINAL image using the anchor-defined cell
geometry rather than the primary engine's own box: taking its box would ask the
confirmer to read exactly what the first engine decided to look at, which is
half the independence gone. Tesseract runs with a digit whitelist and
`--psm 7` (one line), the configuration that measured best of nine.

The verdict is written back per fact. `CONFIRMED` values are the defensible
auto-accept set; `CONTRADICTED` is the review budget; `UNCONFIRMED` means the
confirmer had no usable opinion and the value stands on the primary engine
alone.

Needs Tesseract on PATH or at the default Windows install location.

Output is PHI and lands in gitignored `data/derived/facts.sqlite`.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import string
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kidneymatch.hla.vocabulary import load_vocabulary  # noqa: E402
from kidneymatch.ocr.confirm import Confirmation, confirm_value  # noqa: E402

CONFIRMER_VERSION = "tesseract5/psm7-alnum"

# The alphabet a locus value can contain: allele digits, the field separator,
# the star, and the letters that appear in locus names.
# Built rather than written out: a literal run of ten digits reads as an Iranian
# national ID to `scripts/scan_pii.py`, and that check is worth more than the
# brevity.
WHITELIST = string.digits + ":*ABCDPQRW"

LOCI = ("A", "B", "C", "DRB1", "DQA1", "DQB1", "DPA1", "DPB1")

# Padding around the cell, as a fraction of the page. Measured: 10-30 px of
# white padding made Tesseract WORSE (agreement 84% to 68-70%), so this is
# deliberately small — just enough not to clip the glyphs.
PAD_X = 0.004
PAD_Y = 0.006

# Tesseract reads small text poorly; upscaling the crop is what makes these
# 60x20 px cells legible to it.
UPSCALE = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS confirmation (
    sha256             TEXT NOT NULL,
    field              TEXT NOT NULL,
    extraction_version TEXT NOT NULL,
    confirmer_version  TEXT NOT NULL,
    verdict            TEXT NOT NULL,
    reading            TEXT,
    created_utc        TEXT NOT NULL,
    PRIMARY KEY (sha256, field, extraction_version, confirmer_version)
);
"""


def find_tesseract(explicit: str | None) -> str | None:
    if explicit:
        return explicit if Path(explicit).exists() else None
    found = shutil.which("tesseract")
    if found:
        return found
    default = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    return str(default) if default.exists() else None


def read_crops(binary: str, crops: list[Path]) -> list[str]:
    """One Tesseract invocation for many crops, via a list file."""
    if not crops:
        return []
    with tempfile.TemporaryDirectory(prefix="km-confirm-") as work:
        listing = Path(work) / "files.txt"
        listing.write_text("\n".join(str(c) for c in crops) + "\n", encoding="utf-8")
        out = Path(work) / "out"
        subprocess.run(
            [
                binary,
                str(listing),
                str(out),
                "--psm",
                "7",
                "-c",
                # Letters as well as digits: on the forms that print the locus
                # on every value the cell reads `DRB1*11`, and a digit-only
                # whitelist turns that into noise. Measured, digits alone
                # confirmed 20.8% of cells against 86% for the alphanumeric
                # whitelist the design pass used.
                "tessedit_char_whitelist=" + WHITELIST,
            ],
            capture_output=True,
            check=False,
        )
        text = out.with_suffix(".txt")
        if not text.exists():
            return [""] * len(crops)
        # Tesseract separates pages with a form feed.
        pages = text.read_text(encoding="utf-8", errors="ignore").split("\f")
        pages = [p.strip() for p in pages]
        while len(pages) < len(crops):
            pages.append("")
        return pages[: len(crops)]


def run(facts_db: Path, export: Path, binary: str, limit: int | None, batch: int) -> int:
    from PIL import Image

    vocabulary = load_vocabulary()
    con = sqlite3.connect(facts_db)
    con.executescript(SCHEMA)

    done = {
        (sha, field)
        for sha, field in con.execute(
            "SELECT sha256, field FROM confirmation WHERE confirmer_version=?",
            (CONFIRMER_VERSION,),
        )
    }
    placeholders = ",".join("?" * len(LOCI))
    work = [
        row
        for row in con.execute(
            "SELECT f.sha256, f.field, f.value, f.value_boxes, d.rel_path "
            "FROM fact f JOIN document d ON d.sha256 = f.sha256 "
            f"WHERE f.status='RESOLVED' AND f.field IN ({placeholders}) "
            "AND f.value_boxes IS NOT NULL ORDER BY f.sha256, f.field",
            LOCI,
        )
        if (row[0], row[1]) not in done
    ]
    if limit:
        work = work[:limit]
    print(f"cells to confirm: {len(work):,}  (already done {len(done):,})", flush=True)
    if not work:
        print("nothing to do")
        return 0

    started = time.perf_counter()
    tally: Counter[str] = Counter()
    pending: list[tuple] = []
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())

    for start in range(0, len(work), batch):
        chunk = work[start : start + batch]
        with tempfile.TemporaryDirectory(prefix="km-crops-") as work_dir:
            crops: list[Path] = []
            kept: list[tuple] = []
            for index, (sha, field, value, value_boxes, rel_path) in enumerate(chunk):
                source = export / rel_path
                if not source.exists():
                    continue
                boxes = json.loads(value_boxes)
                if not boxes:
                    continue
                try:
                    image = Image.open(source).convert("L")
                except OSError:
                    continue
                width, height = image.size
                x0 = max(0, int((min(b[0] for b in boxes) - PAD_X) * width))
                y0 = max(0, int((min(b[1] for b in boxes) - PAD_Y) * height))
                x1 = min(width, int((max(b[2] for b in boxes) + PAD_X) * width))
                y1 = min(height, int((max(b[3] for b in boxes) + PAD_Y) * height))
                if x1 <= x0 or y1 <= y0:
                    continue
                crop = image.crop((x0, y0, x1, y1))
                crop = crop.resize((crop.width * UPSCALE, crop.height * UPSCALE), Image.LANCZOS)
                path = Path(work_dir) / f"{index:05d}.png"
                crop.save(path)
                crops.append(path)
                kept.append((sha, field, value))

            readings = read_crops(binary, crops)
            for (sha, field, value), reading in zip(kept, readings, strict=True):
                accepted = tuple(part for part in (value or "").split() if part)
                verdict = confirm_value(field, accepted, reading, vocabulary)
                tally[verdict.value] += 1
                pending.append(
                    (sha, field, "facts/v1", CONFIRMER_VERSION, verdict.value, reading, now)
                )

        con.executemany("INSERT OR REPLACE INTO confirmation VALUES (?,?,?,?,?,?,?)", pending)
        con.commit()
        pending.clear()
        seen = min(start + batch, len(work))
        elapsed = time.perf_counter() - started
        print(
            f"  {seen:>7,}/{len(work):,}  {seen / elapsed:5.1f} cell/s  "
            f"eta {(len(work) - seen) / max(seen / elapsed, 1e-9) / 60:5.1f} min",
            flush=True,
        )

    con.close()
    total = sum(tally.values())
    print(f"\ncells confirmed against {CONFIRMER_VERSION}: {total:,}")
    for verdict in (Confirmation.CONFIRMED, Confirmation.CONTRADICTED, Confirmation.UNCONFIRMED):
        count = tally[verdict.value]
        print(f"  {verdict.value:<14}{count:>8,}  ({count / max(total, 1):6.1%})")
    print(
        f"\nThe {tally['CONFIRMED']:,} confirmed cells are the defensible auto-accept "
        f"candidates; the {tally['CONTRADICTED']:,} contradicted ones are the review budget."
    )
    print("Neither is an accuracy: only the golden corpus can say that (HA-007).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--export", type=Path, default=ROOT / "data/raw/ChatExport_2026-08-31")
    parser.add_argument("--tesseract", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=200)
    args = parser.parse_args()

    if not args.facts.exists():
        print(f"missing {args.facts}; run scripts/extract_facts.py first")
        return 2
    binary = find_tesseract(args.tesseract)
    if binary is None:
        print("Tesseract not found. Install it, or pass --tesseract <path>.")
        return 2
    return run(args.facts, args.export, binary, args.limit, args.batch_size)


if __name__ == "__main__":
    raise SystemExit(main())
