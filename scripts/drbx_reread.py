#!/usr/bin/env python3
"""Re-read a DRB3/4/5 gene box whose gene rests on the S-for-5 repair.

`ocr/drbx.py` repairs a final `S` to `5` because, measured over the corpus,
`DRBS` matches a DRB5-expecting DRB1 genotype 99.5% of the time. But `S` is
also how a printed `3` reads, and KI-026 measured the cost: on the reviewer's
labels, rows whose gene rested on that repair were wrong often enough that the
row can certify no absence. That left the whole row abstaining — the largest
single group of misses in the 220-label review of 2026-09-05.

Abstaining is not the answer, because the digit is *legible*: an independent
recognizer reads it. On the two labelled rows where the reviewer wrote DRB3 and
DRB5, the second engine read `DRB3` in the box our repair had called DRB5, and
read `DRB3/5` in a box our pair pattern had collapsed to a single DRB5. Both
match the reviewer exactly.

So this pass asks the reader instead of guessing:

* every gene box of a grouped row that carries a repair is re-read with
  PP-OCRv6 (the best reader measured against labels — 65 of 67 cells exact,
  `docs/ingestion/ENGINE_BENCH_2026-09-05.md`);
* the reading counts only when it is UNAMBIGUOUS — a gene digit that is
  literally 3, 4 or 5, never another `S`. An `S` from the second engine is the
  same ambiguity twice and settles nothing;
* the row is rewritten from what the reader saw, under `drbx.py`'s own counting
  rule: named genes PRESENT, and the rest ABSENT only when two slots were
  accounted for. `source` names the engine, and the reading is kept.

Nothing is invented: a gene outside the printed enumeration is refused, an
ambiguous or silent reading leaves the row exactly as the row rule left it, and
a later run re-judges what an earlier one decided. Prints counts only.
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

from kidneymatch.ocr.crops import CONFIRMER_PADDED, prepare_crop  # noqa: E402
from kidneymatch.ocr.geometry import PageFrame  # noqa: E402

GENES = ("DRB3", "DRB4", "DRB5")
REREAD_VERSION = "drbx-reread/v1+ppocrv6"
SOURCE = "drbx-reread+ppocrv6"
# The reasons this pass may overwrite: the row rule's own abstentions on a
# repaired row, and its own earlier decisions.
HELD_REASON = "a slot on this row rests on an S read as 5"
DEMOTED_REASON = "the S-for-5 repair on this gene token was contradicted"
PRESENT_REASON = (
    "the gene printed in this box was read by PP-OCRv6, not inferred from the S-for-5 repair"
)
ABSENT_REASON = (
    "both haplotypes accounted for by two gene boxes an independent reader read outright"
)
UNKNOWN_REASON = "only one gene box was read outright; the second column is unread or empty"

# A gene the reader saw: the digit must BE a digit. `S` is the ambiguity this
# pass exists to settle, so a reading that says `S` settles nothing.
_GENE = re.compile(r"(?:D\s*R\s*[B8]?)?\s*[*]?\s*([345])(?![0-9])", re.IGNORECASE)
_AMBIGUOUS = re.compile(r"(?<![0-9A-Z])S(?![0-9A-Z])", re.IGNORECASE)

SCHEMA = """
CREATE TABLE IF NOT EXISTS drbx_reread (
    sha256             TEXT NOT NULL,
    field              TEXT NOT NULL,
    extraction_version TEXT NOT NULL,
    reread_version     TEXT NOT NULL,
    reading            TEXT,
    genes              TEXT,
    created_utc        TEXT NOT NULL,
    PRIMARY KEY (sha256, field, extraction_version, reread_version)
);
"""


def genes_in(reading: str) -> list[str] | None:
    """The genes this reading names, or None when it settles nothing.

    `DRB3` -> [DRB3]; `DRB3/5` -> [DRB3, DRB5]; `DRBS`, `` or `DRB1` -> None.
    """
    text = (reading or "").strip()
    if not text or _AMBIGUOUS.search(re.sub(r"(?i)^HLA[\s\-]*", "", text)):
        return None
    found = [f"DRB{d}" for d in _GENE.findall(text)]
    if not found or len(found) > 2:
        return None
    # A pair box (`DRB3/5`) names two; anything naming the same gene twice is
    # one gene read twice, not a haplotype count.
    out: list[str] = []
    for gene in found:
        if gene not in out:
            out.append(gene)
    return out


def _separate(boxes: list[tuple[str, list[float]]]) -> list[tuple[str, list[float]]]:
    """The row's gene boxes, minus any that is the same printed token twice.

    Two boxes count as two haplotype slots, and that is what lets the counting
    rule certify the third gene ABSENT — so a detector that boxed one printed
    token twice would manufacture an absence. Overlapping boxes are the same
    token; only boxes standing apart along the row are two of them.
    """
    kept: list[tuple[str, list[float]]] = []
    for field, box in sorted(boxes, key=lambda pair: pair[1][0]):
        if any(min(box[2], other[2]) - max(box[0], other[0]) > 0 for _, other in kept):
            continue
        kept.append((field, box))
    return kept


def select_rows(con: sqlite3.Connection) -> list[dict[str, object]]:
    """Grouped rows carrying a repair, with every gene box on them."""
    rows: dict[str, dict[str, object]] = {}
    placeholders = ",".join("?" * len(GENES))
    for sha, field, value, boxes, reason, repaired, source, rel, frame, tilt in con.execute(
        "SELECT f.sha256, f.field, f.value, f.value_boxes, f.reason, f.repaired, "
        "f.source, d.rel_path, d.frame, d.tilt_deg FROM fact f JOIN document d "
        "ON d.sha256=f.sha256 AND d.extraction_version=f.extraction_version "
        f"WHERE f.field IN ({placeholders}) AND f.extraction_version='facts/v1' "
        "AND f.rule_id='GROUPED_DRBX/v1' ORDER BY f.sha256",
        GENES,
    ):
        row = rows.setdefault(
            sha,
            {"sha256": sha, "rel": rel, "frame": frame, "tilt": tilt, "boxes": [], "flag": False},
        )
        # The box of a gene the row rule READ. A cell this pass or the S-rule
        # demoted keeps its box and loses its value, and it is exactly the one
        # that needs a second reading; a cell whose box is the ink region of an
        # empty slot (`drbx_ink_pass.py`) holds no gene and is not re-read.
        if boxes and value != "ABSENT" and source != "ink-certified":
            # EVERY box the row named this gene with. A row can print one gene
            # twice, once per haplotype, and taking only the first hid the
            # second from this pass on 224 rows — rows whose only S-for-5
            # repair was on the box nobody re-read, so nothing could settle.
            for box in json.loads(boxes):
                row["boxes"].append((field, box))  # type: ignore[union-attr]
        if (
            repaired
            or (reason or "").startswith(HELD_REASON[:40])
            or ((reason or "").startswith(DEMOTED_REASON[:40]))
            or source == SOURCE
        ):
            row["flag"] = True
    return [r for r in rows.values() if r["flag"] and r["boxes"]]


def run(
    facts_db: Path, export: Path, *, limit: int | None = None, dry_run: bool = False
) -> Counter[str]:
    from PIL import Image

    from kidneymatch.ocr.confirm import Confirmation  # noqa: F401  (kept for parity)

    sys.path.insert(0, str(ROOT / "scripts"))
    from confirm_pass import PPOCRV6_MODEL, build_ppocr_reader  # noqa: PLC0415

    con = sqlite3.connect(facts_db)
    con.executescript(SCHEMA)
    rows = select_rows(con)
    if limit:
        rows = rows[:limit]
    tally: Counter[str] = Counter()
    if not rows:
        tally["rows examined"] = 0
        return tally
    read = build_ppocr_reader(PPOCRV6_MODEL)
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    for row in rows:
        try:
            image = np.asarray(Image.open(export / str(row["rel"])).convert("L"))
        except OSError:
            tally["image unreadable"] += 1
            continue
        frame = None
        if row["frame"] == "ROTATE" and row["tilt"]:
            frame = PageFrame(float(row["tilt"]), int(image.shape[1]), int(image.shape[0]))
        boxes: list[tuple[str, list[float]]] = row["boxes"]  # type: ignore[assignment]
        crops, keys = [], []
        for field, box in _separate(boxes):
            crop = prepare_crop(image, box, frame=frame, profile=CONFIRMER_PADDED)
            if crop is not None and crop.pixels.size:
                crops.append(Image.fromarray(crop.pixels))
                keys.append(field)
        if not crops:
            tally["no crop"] += 1
            continue
        readings = read(crops)
        named: list[str] = []
        slots = 0
        settled = True
        for field, reading in zip(keys, readings, strict=True):
            seen = genes_in(reading)
            if not dry_run:
                con.execute(
                    "INSERT OR REPLACE INTO drbx_reread VALUES (?,?,?,?,?,?,?)",
                    (
                        row["sha256"],
                        field,
                        "facts/v1",
                        REREAD_VERSION,
                        reading,
                        json.dumps(seen),
                        now,
                    ),
                )
            if seen is None:
                settled = False
                continue
            # A haplotype slot per gene the box names: a pair box (`DRB3/5`)
            # accounts for both, and two boxes naming the SAME gene still
            # account for both — that is what makes the third gene ABSENT
            # rather than unknown (`drbx.py`'s counting rule).
            slots += len(seen)
            for gene in seen:
                if gene not in named:
                    named.append(gene)
        if not settled or not named or len(named) > 2:
            tally["reader settles nothing; the row rule stands" if not settled else "unusable"] += 1
            continue
        tally[f"row read outright: {len(named)} gene(s), {min(slots, 2)} slot(s)"] += 1
        if dry_run:
            continue
        others = "ABSENT" if slots >= 2 else None
        for gene in GENES:
            if gene in named:
                con.execute(
                    "UPDATE fact SET status='RESOLVED', value='PRESENT', reason=?, source=?, "
                    "repaired=1 WHERE sha256=? AND field=? AND extraction_version='facts/v1'",
                    (PRESENT_REASON, SOURCE, row["sha256"], gene),
                )
            elif others:
                con.execute(
                    "UPDATE fact SET status='RESOLVED', value='ABSENT', reason=?, source=? "
                    "WHERE sha256=? AND field=? AND extraction_version='facts/v1'",
                    (ABSENT_REASON, SOURCE, row["sha256"], gene),
                )
            else:
                con.execute(
                    "UPDATE fact SET status='UNKNOWN', value=NULL, reason=?, source=? "
                    "WHERE sha256=? AND field=? AND extraction_version='facts/v1'",
                    (UNKNOWN_REASON, SOURCE, row["sha256"], gene),
                )
        con.commit()
    con.commit()
    con.close()
    tally["rows examined"] = len(rows)
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
    print(
        f"{'read' if args.dry_run else 'rewrote'} {tally.pop('rows examined', 0):,} repaired rows"
    )
    for key, count in sorted(tally.items()):
        print(f"  {key:<48}{count:>8,}")
    print(
        "A gene is taken from the reader only when the digit it returns IS a digit; an `S` "
        "settles nothing and leaves the row as the row rule left it."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
