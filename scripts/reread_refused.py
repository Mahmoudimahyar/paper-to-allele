#!/usr/bin/env python3
"""Re-read a value the resolver refused, and take it only when two engines agree.

Two of `anchors.py`'s gates refuse a cell for what the RECOGNIZER produced
rather than for where the box sits:

* gate 5 refuses a value whose first field is not an allele family of its locus
  (`A*83` is not a thing). The comment beside it names the cause: the commonest
  surviving error is a leading `0` read as `8` or `9`, and both readings are
  clean digits, so no glyph repair and no geometric gate can see it;
* gate 4 refuses a cell when a candidate on its row does not parse as an allele
  value at all, which throws away the siblings that read perfectly well.

Both are right to refuse — the resolver cannot repair what it cannot read — and
both leave the cell REVIEW_REQUIRED holding boxes nobody looks at again. Over
the corpus that is 5,145 cells, and on the reviewer's 220 labels it is five
cells a human read without difficulty.

So this pass asks two more recognizers what the box says:

* each value box is re-read by PP-OCRv6 and PP-OCRv5-server, and BOTH must
  state the same value. A single engine would only trade the first reader's
  guess for another: the pixels already defeated one recognizer, and a second
  producing a family that merely exists is not evidence that it is the printed
  one. Agreement between two is;
* the agreed reading is taken only when it parses as an allele value, is
  admissible for this locus, and differs from what the resolver refused. The
  asymmetry is the argument: one reader produced something impossible or
  unreadable, and two others independently produced the same possible thing
  from the same pixels;
* a reading carrying its own locus prefix must name this locus, exactly as
  gate 2 requires of a first reading. Geometry still owns the locus, never the
  text;
* more than two agreed values is a cardinality failure, not a read, and the
  cell keeps its refusal;
* a cell whose boxes do not all settle resolves from the ones that did and
  declares its second allele UNREAD — a partial read, not a claim of
  completeness.

A re-extraction rewrites every fact, so this pass must be re-run after one. It
resumes the way the decode and confirm passes do: a cell whose boxes are
byte-identical to the ones already read reuses the stored readings instead of
running the recognizers again, and a cell whose boxes moved is read afresh
because the stored readings were about a different crop.

Nothing is invented. A reading that is inadmissible, unparsable, equal to what
was refused, or prefixed for another locus leaves the cell exactly as the
resolver left it, and a later run re-judges what an earlier one decided.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kidneymatch.hla.vocabulary import load_vocabulary  # noqa: E402
from kidneymatch.ocr.crops import CONFIRMER_PADDED, prepare_crop  # noqa: E402
from kidneymatch.ocr.geometry import PageFrame  # noqa: E402
from kidneymatch.ocr.glyphs import parse_allele_values  # noqa: E402

LOCI = ("A", "B", "C", "DRB1", "DQA1", "DQB1", "DPA1", "DPB1")
REREAD_VERSION = "reread-refused/v1+ppocrv6+ppocrv5"
SOURCE = "reread-refused+two-engine-agreement"
# A locus has at most two alleles; more agreed values is a cardinality failure.
MAX_VALUES = 2

# The two refusals this pass can answer, and where each records what it refused.
REFUSALS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("inadmissible family", re.compile(r"^'([^']*)' is not an allele family of")),
    ("unparsable candidate", re.compile(r"^candidate '(.*)' does not parse as an allele value")),
)
SELECT_LIKE = ("%is not an allele family of%", "%does not parse as an allele value%")

RESOLVED_REASON = (
    "the resolver refused this cell for what the recognizer produced; two independent "
    "recognizers then read the same admissible value from the same boxes"
)
PARTIAL_REASON = (
    "one box of this row re-read as a value both recognizers agree on; the other did not "
    "settle, so the second allele is unread"
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS reread_refused (
    sha256             TEXT NOT NULL,
    field              TEXT NOT NULL,
    extraction_version TEXT NOT NULL,
    reread_version     TEXT NOT NULL,
    refusal            TEXT,
    refused            TEXT,
    boxes              TEXT,
    readings           TEXT,
    readings_second    TEXT,
    taken              TEXT,
    created_utc        TEXT NOT NULL,
    PRIMARY KEY (sha256, field, extraction_version, reread_version)
);
"""


def classify_refusal(reason: str | None) -> tuple[str, str] | None:
    """Which refusal this is, and the text the resolver refused."""
    for name, pattern in REFUSALS:
        found = pattern.match(reason or "")
        if found:
            return name, found.group(1)
    return None


def agreed_values(
    reading: str, second: str, locus: str, refused: str, vocabulary
) -> tuple[str, ...]:
    """Every value BOTH recognizers state, or empty when they settle nothing.

    Every condition here is one an original reading would have had to pass.

    A reading can state two: some forms print both alleles of a locus in one
    box (`A*24,*02`, 1,819 tokens on 890 documents), and the single-value
    parser this used to call returned None for all of them — so a box the
    resolver had already refused, and both engines then read correctly, still
    settled nothing.
    """
    first = _admissible(reading, locus, refused, vocabulary)
    if not first or first != _admissible(second, locus, refused, vocabulary):
        return ()
    return first


def agreed_value(reading: str, second: str, locus: str, refused: str, vocabulary) -> str | None:
    """The single value both recognizers state, kept for the contract tests."""
    found = agreed_values(reading, second, locus, refused, vocabulary)
    return found[0] if len(found) == 1 else None


def _admissible(reading: str, locus: str, refused: str, vocabulary) -> tuple[str, ...]:
    values = parse_allele_values((reading or "").strip())
    if not values:
        return ()
    out: list[str] = []
    for parsed in values:
        if parsed.locus_prefix and parsed.locus_prefix.upper() != locus.upper():
            return ()
        text = parsed.text()
        if refused and refused in (parsed.first_field, text, (parsed.raw or "").strip()):
            return ()
        if not vocabulary.covers(locus) or not vocabulary.is_admissible(locus, parsed.first_field):
            return ()
        out.append(text)
    return tuple(out)


def select_cells(con: sqlite3.Connection) -> list[dict[str, object]]:
    """Cells refused for a reading that still hold a box to re-read."""
    placeholders = ",".join("?" * len(LOCI))
    likes = " OR ".join(["f.reason LIKE ?"] * len(SELECT_LIKE))
    out: list[dict[str, object]] = []
    for sha, field, reason, boxes, rel, frame, tilt in con.execute(
        "SELECT f.sha256, f.field, f.reason, f.value_boxes, d.rel_path, d.frame, d.tilt_deg "
        "FROM fact f JOIN document d ON d.sha256=f.sha256 "
        "AND d.extraction_version=f.extraction_version "
        f"WHERE f.status='REVIEW_REQUIRED' AND f.field IN ({placeholders}) "
        f"AND ({likes}) AND f.value_boxes IS NOT NULL "
        "AND f.extraction_version='facts/v1' ORDER BY f.sha256, f.field",
        (*LOCI, *SELECT_LIKE),
    ):
        refusal = classify_refusal(reason)
        if refusal is None:
            continue
        out.append(
            {
                "sha256": sha,
                "field": field,
                "refusal": refusal[0],
                "refused": refusal[1],
                "boxes": json.loads(boxes),
                "rel": rel,
                "frame": frame,
                "tilt": tilt,
            }
        )
    return out


def run(
    facts_db: Path, export: Path, *, limit: int | None = None, dry_run: bool = False
) -> Counter[str]:
    from PIL import Image

    sys.path.insert(0, str(ROOT / "scripts"))
    from confirm_pass import (  # noqa: PLC0415
        PPOCR_MODEL,
        PPOCRV6_MODEL,
        build_ppocr_reader,
    )

    vocabulary = load_vocabulary()
    con = sqlite3.connect(facts_db)
    con.executescript(SCHEMA)
    cells = select_cells(con)
    if limit:
        cells = cells[:limit]
    tally: Counter[str] = Counter()
    if not cells:
        tally["cells examined"] = 0
        return tally
    read = build_ppocr_reader(PPOCRV6_MODEL)
    read_second = build_ppocr_reader(PPOCR_MODEL)
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    images: dict[str, object] = {}
    for cell in cells:
        rel = str(cell["rel"])
        if rel not in images:
            try:
                images[rel] = np.asarray(Image.open(export / rel).convert("L"))
            except OSError:
                images[rel] = None
        image = images[rel]
        if image is None:
            tally["image unreadable"] += 1
            continue
        frame = None
        if cell["frame"] == "ROTATE" and cell["tilt"]:
            frame = PageFrame(float(cell["tilt"]), int(image.shape[1]), int(image.shape[0]))
        crops = []
        for box in cell["boxes"]:  # type: ignore[union-attr]
            crop = prepare_crop(image, box, frame=frame, profile=CONFIRMER_PADDED)
            if crop is not None and crop.pixels.size:
                crops.append(Image.fromarray(crop.pixels))
        if not crops:
            tally["no crop"] += 1
            continue
        boxes_key = json.dumps(cell["boxes"], sort_keys=True)
        remembered = con.execute(
            "SELECT readings, readings_second FROM reread_refused WHERE sha256=? AND field=? "
            "AND extraction_version='facts/v1' AND reread_version=? AND boxes=?",
            (cell["sha256"], cell["field"], REREAD_VERSION, boxes_key),
        ).fetchone()
        if remembered:
            readings = json.loads(remembered[0])
            seconds = json.loads(remembered[1])
            tally["boxes already read; the stored readings stand"] += 1
        else:
            readings = read(crops)
            seconds = read_second(crops)
        if len(readings) != len(crops) or len(seconds) != len(crops):
            tally["stored readings do not match the crops; read again"] += 1
            readings, seconds = read(crops), read_second(crops)
        taken: list[str] = []
        for reading, second in zip(readings, seconds, strict=True):
            taken.extend(
                agreed_values(reading, second, str(cell["field"]), str(cell["refused"]), vocabulary)
            )
        if not dry_run:
            con.execute(
                "INSERT OR REPLACE INTO reread_refused VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    cell["sha256"],
                    cell["field"],
                    "facts/v1",
                    REREAD_VERSION,
                    cell["refusal"],
                    cell["refused"],
                    boxes_key,
                    json.dumps(list(readings)),
                    json.dumps(list(seconds)),
                    json.dumps(taken),
                    now,
                ),
            )
        if not taken:
            tally[f"{cell['refusal']}: the two readers do not agree; the refusal stands"] += 1
            continue
        if len(taken) > MAX_VALUES:
            tally[f"{cell['refusal']}: more than two agreed values; the refusal stands"] += 1
            continue
        complete = len(taken) >= len(crops)
        where = "whole cell" if complete else "part of the cell"
        tally[f"{cell['refusal']}: re-read {where}, {len(taken)} value(s)"] += 1
        if dry_run:
            continue
        con.execute(
            "UPDATE fact SET status='RESOLVED', value=?, reason=?, source=?, repaired=1, "
            "second_allele=? WHERE sha256=? AND field=? AND extraction_version='facts/v1'",
            (
                " ".join(taken),
                RESOLVED_REASON if complete else PARTIAL_REASON,
                SOURCE,
                "READ" if complete else "UNREAD",
                cell["sha256"],
                cell["field"],
            ),
        )
        con.commit()
    con.commit()
    con.close()
    tally["cells examined"] = len(cells)
    return tally


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--export", type=Path, default=ROOT / "data/raw/ChatExport_2026-08-31")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true", help="read and count, change nothing")
    args = parser.parse_args()
    if not args.facts.exists():
        print(f"missing {args.facts}")
        return 2
    tally = run(args.facts, args.export, limit=args.limit, dry_run=args.dry_run)
    verb = "read" if args.dry_run else "rewrote"
    print(f"{verb} {tally.pop('cells examined', 0):,} refused cells")
    for key, count in sorted(tally.items()):
        print(f"  {key:<62}{count:>8,}")
    print(
        "A value is taken only when both recognizers state it, it parses, it is admissible "
        "for this locus, and it differs from what the resolver refused."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
