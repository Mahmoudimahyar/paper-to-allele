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

# The second reader adopted 2026-09-03. Measured on 600 real crops it agrees
# with the trusted set 97.0% against Tesseract's 90.0%, and with the hard cells
# 91.0% against 51.5%, at 13 ms per crop on the CPU. It matters most where
# Tesseract is silent: 18,010 resolved cells, most of them class I, whose value
# box is four glyphs wide. Evidence:
# `docs/ingestion/OCR_MODEL_SURVEY_2026-09-03.md`.
PPOCR_CONFIRMER_VERSION = "ppocrv5/en-mobile-rec"
PPOCR_MODEL = "en_PP-OCRv5_mobile_rec"

ENGINES = {
    "tesseract5": CONFIRMER_VERSION,
    "ppocrv5": PPOCR_CONFIRMER_VERSION,
}

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
# 60x20 px cells legible to it. PP-OCRv5 does its own resizing and measured
# WORSE with an upscale (0.970 to 0.947), so it takes the crop as cut.
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


def build_ppocr_reader():  # type: ignore[no-untyped-def]
    """PP-OCRv5 recognition, English mobile. Needs the `confirm` extra.

    Recognition ONLY: the cell's geometry already came from the primary
    pipeline, and letting a second detector redraw the box would make this a
    different reading of a different crop rather than a second opinion on the
    same one.
    """
    import numpy as np
    from paddleocr import TextRecognition

    engine = TextRecognition(model_name=PPOCR_MODEL, device="cpu")

    def read(images: list) -> list[str]:
        if not images:
            return []
        # PaddleOCR wants BGR arrays; the crops are greyscale PIL images.
        arrays = [np.asarray(image.convert("RGB"))[:, :, ::-1] for image in images]
        out: list[str] = []
        for result in engine.predict(input=arrays):
            text = result.get("rec_text") if isinstance(result, dict) else None
            out.append(str(text or "").strip())
        return out

    return read


def run(
    facts_db: Path,
    export: Path,
    binary: str,
    limit: int | None,
    batch: int,
    engine: str = "tesseract5",
) -> int:
    from PIL import Image

    confirmer_version = ENGINES[engine]
    read_ppocr = build_ppocr_reader() if engine == "ppocrv5" else None
    vocabulary = load_vocabulary()
    con = sqlite3.connect(facts_db)
    con.executescript(SCHEMA)

    done = {
        (sha, field)
        for sha, field in con.execute(
            "SELECT sha256, field FROM confirmation WHERE confirmer_version=?",
            (confirmer_version,),
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
    pending: list[tuple[str, str, str, str, str, str, str]] = []
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())

    for start in range(0, len(work), batch):
        chunk = work[start : start + batch]
        with tempfile.TemporaryDirectory(prefix="km-crops-") as work_dir:
            crops: list[Path] = []
            images: list[list] = []
            kept: list[tuple[str, str, str | None]] = []
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
                if read_ppocr is not None:
                    # One crop PER VALUE BOX, not one spanning both.
                    # The survey that adopted this engine measured it on single
                    # allele crops; on a crop spanning a heterozygous pair it
                    # contradicted the pipeline on 50.7% of the cells the decode
                    # called unanimous AND Tesseract confirmed — a coin flip,
                    # which is what a mismatched crop looks like. These
                    # recognizers are strongly sensitive to framing (see the
                    # survey's section 3), so the crop has to match the one the
                    # engine was judged on.
                    pieces = []
                    for box in boxes:
                        bx0 = max(0, int((box[0] - PAD_X) * width))
                        by0 = max(0, int((box[1] - PAD_Y) * height))
                        bx1 = min(width, int((box[2] + PAD_X) * width))
                        by1 = min(height, int((box[3] + PAD_Y) * height))
                        if bx1 > bx0 and by1 > by0:
                            pieces.append(image.crop((bx0, by0, bx1, by1)))
                    if not pieces:
                        continue
                    images.append(pieces)
                    kept.append((sha, field, value))
                    continue

                crop = image.crop((x0, y0, x1, y1))
                if read_ppocr is None:
                    # Tesseract needs the upscale; PP-OCRv5 measured worse with
                    # one (0.970 -> 0.947), so it reads the crop as cut.
                    crop = crop.resize(
                        (crop.width * UPSCALE, crop.height * UPSCALE), Image.Resampling.LANCZOS
                    )
                    path = Path(work_dir) / f"{index:05d}.png"
                    crop.save(path)
                    crops.append(path)
                kept.append((sha, field, value))

            if read_ppocr is not None:
                # Flatten, read, and re-join per cell, so a heterozygous cell
                # comes back as the two alleles it holds.
                flat = [piece for pieces in images for piece in pieces]
                texts = read_ppocr(flat)
                readings = []
                cursor = 0
                for pieces in images:
                    part = texts[cursor : cursor + len(pieces)]
                    cursor += len(pieces)
                    readings.append(" ".join(t for t in part if t))
            else:
                readings = read_crops(binary, crops)
            for (sha, field, value), reading in zip(kept, readings, strict=True):
                accepted = tuple(part for part in (value or "").split() if part)
                verdict = confirm_value(field, accepted, reading, vocabulary)
                tally[verdict.value] += 1
                pending.append(
                    (sha, field, "facts/v1", confirmer_version, verdict.value, reading, now)
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
    print(f"\ncells confirmed against {confirmer_version}: {total:,}")
    for verdict in (Confirmation.CONFIRMED, Confirmation.CONTRADICTED, Confirmation.UNCONFIRMED):
        count = tally[verdict.value]
        print(f"  {verdict.value:<14}{count:>8,}  ({count / max(total, 1):6.1%})")
    print(
        f"\nThe {tally['CONFIRMED']:,} confirmed cells are the defensible auto-accept "
        f"candidates; the {tally['CONTRADICTED']:,} contradicted ones are the review budget."
    )
    print("Neither is an accuracy: only the golden corpus can say that (HA-007).")
    return 0


def rescore(facts_db: Path) -> int:
    """Re-judge every stored reading under the current `confirm_value`.

    The reading is Tesseract's and does not change; the comparison rule does
    (star-less readings, 2026-09-02). Re-running Tesseract to re-apply a rule
    would cost hours and change nothing about the evidence, so the verdicts are
    recomputed in place from the stored readings. Nothing here reads an image.
    """
    vocabulary = load_vocabulary()
    con = sqlite3.connect(facts_db)
    rows = con.execute(
        "SELECT c.sha256, c.field, c.verdict, c.reading, f.value FROM confirmation c "
        "JOIN fact f ON f.sha256=c.sha256 AND f.field=c.field "
        "AND f.extraction_version=c.extraction_version"
    ).fetchall()
    before: Counter[str] = Counter()
    after: Counter[str] = Counter()
    changed: list[tuple[str, str, str]] = []
    for sha, field, old, reading, value in rows:
        accepted = tuple(part for part in (value or "").split() if part)
        new = confirm_value(field, accepted, reading or "", vocabulary).value
        before[old] += 1
        after[new] += 1
        if new != old:
            changed.append((new, sha, field))
    con.executemany("UPDATE confirmation SET verdict=? WHERE sha256=? AND field=?", changed)
    con.commit()
    con.close()
    print(f"rescored {len(rows):,} stored readings; {len(changed):,} verdicts changed")
    for verdict in (Confirmation.CONFIRMED, Confirmation.CONTRADICTED, Confirmation.UNCONFIRMED):
        key = verdict.value
        print(f"  {key:<14}{before[key]:>8,} -> {after[key]:>8,}")
    print("The readings are unchanged; only the comparison rule moved.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--export", type=Path, default=ROOT / "data/raw/ChatExport_2026-08-31")
    parser.add_argument("--tesseract", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument(
        "--engine",
        choices=sorted(ENGINES),
        default="tesseract5",
        help="ppocrv5 needs the `confirm` extra; both write to the same table "
        "under their own confirmer_version, so neither replaces the other",
    )
    parser.add_argument(
        "--rescore",
        action="store_true",
        help="re-judge the stored readings under the current rule; runs no OCR",
    )
    args = parser.parse_args()
    if args.rescore:
        if not args.facts.exists():
            print(f"missing {args.facts}")
            return 2
        return rescore(args.facts)

    if not args.facts.exists():
        print(f"missing {args.facts}; run scripts/extract_facts.py first")
        return 2

    binary = ""
    if args.engine == "tesseract5":
        found = find_tesseract(args.tesseract)
        if found is None:
            print("Tesseract not found. Install it, or pass --tesseract <path>.")
            return 2
        binary = found

    return run(args.facts, args.export, binary, args.limit, args.batch_size, args.engine)


if __name__ == "__main__":
    raise SystemExit(main())
