#!/usr/bin/env python3
"""Choose the documents a person should read, and pack them for the review page.

The golden protocol (ADR 0009) labels cells blind. This pack is the other
instrument: a person sees the whole report, every cell's crop, and what each
engine read, and either approves or corrects. It is faster and it anchors the
reader on the suggestions, so the output is recorded as APPROVED / EDITED /
ADDED per cell and is scored with `scripts/golden_score.py` like any labels.

## How the documents are chosen

A random sample would be almost all easy cells. The point is to find where the
pipeline is wrong, so documents are drawn from strata defined by the failure
signals the pipeline already emits, with quotas that over-represent the rare
ones, plus a clean-control stratum that measures how often "every signal
agrees" is still wrong. A document is assigned to the FIRST stratum in
`STRATA` that it belongs to, so the rarest signals fill first; every tag it
carries is kept on the record.

## What the pack contains (PHI: lands under the gitignored `data/review/`)

    <out>/index.html      the review page (a copy of tools/hla_review.html)
    <out>/pack.js         window.PACK = {...}  (the page loads this, no server)
    <out>/pack.json       the same data
    <out>/pipeline.json   the pipeline's readings in golden_score's hidden format
    <out>/images/<id>.jpg the original photo
    <out>/crops/<id>_<locus>.png  one crop per cell that had a box

Cell ids are `<sha256[:16]>:<LOCUS>`, the golden corpus convention.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

PACK_SCHEMA = "hla-review-pack/v1"
HLA_LOCI = ("A", "B", "C", "DRB1", "DQA1", "DQB1", "DPA1", "DPB1")
DRBX_LOCI = ("DRB3", "DRB4", "DRB5")
CELL_FIELDS = HLA_LOCI + DRBX_LOCI
DOC_FIELDS = ("ROLE", "ABO", "RH")

# (tag, weight, what it means). Order = priority when a document carries
# several tags. Weights are relative quotas; `--n` scales them.
STRATA: tuple[tuple[str, int, str], ...] = (
    ("consistency_flag", 10, "DRB1 and the DRB3/4/5 row contradict each other"),
    ("low_res", 5, "quality band LOW"),
    ("digits_lost", 15, "the constrained decode dropped a digit the recognizer saw"),
    ("proposal", 10, "the resolver refused the cell for shape; the decode reads a clean allele"),
    ("review_refused", 15, "boxes sat on the row but the resolver refused the cell"),
    ("unread_second", 10, "a second allele the pipeline could not read"),
    ("decode_split", 20, "the reading changes under one-pixel jitter"),
    ("confirmer_contradicted", 20, "Tesseract read different digits"),
    ("repaired_glyph", 15, "the accepted value went through glyph repair"),
    ("comparison_sheet", 5, "donor and recipient on one sheet"),
    ("mid_res", 10, "quality band MID"),
    ("default_rule", 10, "no layout family; the generic rule bound the values"),
    (
        "zero_fact_no_anchor",
        10,
        "no locus label anchored anywhere; measured, most of these are not reports",
    ),
    ("zero_fact_refused", 10, "labels anchored but every cell refused; nothing extracted"),
    ("clean_control", 20, "every signal agrees; measures how often 'clean' is still wrong"),
)
FLAGGED_CONSISTENCY = {"EXPECTED_GENE_ABSENT", "FORBIDDEN_GENE_PRESENT"}
# Padding around a cell crop, as a fraction of the page.
PAD_X, PAD_Y = 0.012, 0.008
MIN_CROP_HEIGHT = 44  # px; smaller crops are upscaled for the eye


@dataclass(slots=True)
class Cell:
    locus: str
    status: str
    value: str | None
    raw: str | None
    repaired: bool
    second_allele: str | None
    reason: str | None
    rule_id: str | None
    stability: str | None
    anchor_box: list[float] | None
    value_boxes: list[list[float]]
    tesseract: dict[str, str | None] | None = None
    decode: dict[str, object] | None = None


@dataclass(slots=True)
class Doc:
    sha256: str
    rel_path: str
    quality_band: str | None
    family: str | None
    comparison_sheet: bool
    consistency: str | None
    consistency_reason: str | None
    cells: dict[str, Cell] = field(default_factory=dict)
    role: dict[str, str | None] = field(default_factory=dict)
    abo: dict[str, str | None] = field(default_factory=dict)
    rh: dict[str, str | None] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    @property
    def short(self) -> str:
        return self.sha256[:16]


def _loads(text: str | None) -> Any:
    return json.loads(text) if text else None


def _boxes(text: str | None) -> list[list[float]]:
    raw = _loads(text)
    if not raw:
        return []
    return [raw] if isinstance(raw[0], (int, float)) else list(raw)


def load_documents(con: sqlite3.Connection) -> dict[str, Doc]:
    docs: dict[str, Doc] = {}
    for row in con.execute(
        "SELECT sha256, rel_path, quality_band, family, comparison_sheet, consistency, "
        "consistency_reason FROM document"
    ):
        docs[row[0]] = Doc(row[0], row[1], row[2], row[3], bool(row[4]), row[5], row[6])
    for (
        sha,
        fld,
        status,
        value,
        raw,
        repaired,
        second,
        reason,
        rule,
        stab,
        abox,
        vboxes,
        src,
    ) in con.execute(
        "SELECT sha256, field, status, value, raw, repaired, second_allele, reason, rule_id, "
        "stability, anchor_box, value_boxes, source FROM fact"
    ):
        doc = docs.get(sha)
        if doc is None:
            continue
        if fld in CELL_FIELDS:
            doc.cells[fld] = Cell(
                fld,
                status,
                value,
                raw,
                bool(int(repaired or 0)),
                second,
                reason,
                rule,
                stab,
                _loads(abox),
                _boxes(vboxes),
            )
        elif fld == "ROLE":
            doc.role = {"status": status, "value": value, "source": src}
        elif fld == "ABO":
            doc.abo = {"status": status, "value": value, "source": src, "reason": reason}
        elif fld == "RH":
            doc.rh = {"status": status, "value": value}
    for sha, fld, verdict, reading in con.execute(
        "SELECT sha256, field, verdict, reading FROM confirmation"
    ):
        cell = docs[sha].cells.get(fld) if sha in docs else None
        if cell is not None:
            cell.tesseract = {"verdict": verdict, "reading": reading}
    for sha, fld, verdict, reading, jitter in con.execute(
        "SELECT sha256, field, verdict, reading, jitter_readings FROM decode "
        "WHERE decoder_version LIKE 'ctc-viterbi%'"
    ):
        cell = docs[sha].cells.get(fld) if sha in docs else None
        if cell is not None:
            votes = _loads(jitter) or {}
            cell.decode = {"verdict": verdict, "reading": reading, "votes": votes}
    return docs


def tag_document(doc: Doc, export: Path) -> list[str]:
    """Every stratum this document belongs to, in `STRATA` order."""
    hla = [c for c in doc.cells.values() if c.locus in HLA_LOCI]
    resolved = [c for c in hla if c.status == "RESOLVED"]
    verdicts = {c.locus: (c.decode or {}).get("verdict") for c in hla}
    tess = {c.locus: (c.tesseract or {}).get("verdict") for c in hla}
    tags: set[str] = set()
    if doc.consistency in FLAGGED_CONSISTENCY:
        tags.add("consistency_flag")
    if doc.quality_band == "LOW":
        tags.add("low_res")
    if doc.quality_band == "MID":
        tags.add("mid_res")
    if any(v == "DIGITS_LOST" for v in verdicts.values()):
        tags.add("digits_lost")
    if any(v == "SPLIT" for v in verdicts.values()):
        tags.add("decode_split")
    if any(v == "PROPOSAL" for v in verdicts.values()):
        tags.add("proposal")
    if any(c.status == "REVIEW_REQUIRED" and c.value_boxes for c in hla):
        tags.add("review_refused")
    if any(c.second_allele == "UNREAD" for c in resolved):
        tags.add("unread_second")
    if any(v == "CONTRADICTED" for v in tess.values()):
        tags.add("confirmer_contradicted")
    if any(c.repaired for c in resolved):
        tags.add("repaired_glyph")
    if doc.comparison_sheet:
        tags.add("comparison_sheet")
    if doc.family is None and resolved:
        tags.add("default_rule")
    if not resolved:
        anchored = any(c.status == "REVIEW_REQUIRED" for c in hla)
        tags.add("zero_fact_refused" if anchored else "zero_fact_no_anchor")
    if (
        not tags
        and len(resolved) >= 3
        and all(c.stability == "UNANIMOUS" for c in resolved)
        and all(tess.get(c.locus) in (None, "CONFIRMED") for c in resolved)
        and any(tess.get(c.locus) == "CONFIRMED" for c in resolved)
    ):
        tags.add("clean_control")
    return [t for t, _, _ in STRATA if t in tags]


def choose(docs: dict[str, Doc], n: int, seed: int, export: Path) -> list[Doc]:
    """Stratified, deterministic, spread across layout families inside a stratum."""
    rng = random.Random(seed)
    pools: dict[str, list[Doc]] = defaultdict(list)
    for doc in docs.values():
        doc.tags = tag_document(doc, export)
        if doc.tags and (export / doc.rel_path).exists():
            pools[doc.tags[0]].append(doc)
    total_weight = sum(w for _, w, _ in STRATA)
    quota = {t: max(1, round(n * w / total_weight)) if pools[t] else 0 for t, w, _ in STRATA}
    chosen: list[Doc] = []
    for tag, _, _ in STRATA:
        by_family: dict[str | None, list[Doc]] = defaultdict(list)
        for doc in pools[tag]:
            by_family[doc.family].append(doc)
        for group in by_family.values():
            rng.shuffle(group)
        families = sorted(by_family, key=lambda f: (f is None, str(f)))
        picked: list[Doc] = []
        while len(picked) < min(quota[tag], len(pools[tag])):
            for fam in families:  # round-robin across families
                if by_family[fam] and len(picked) < quota[tag]:
                    picked.append(by_family[fam].pop())
        chosen.extend(picked)
    # Top up from the biggest pools if rounding or empty strata left room.
    seen = {d.sha256 for d in chosen}
    while len(chosen) < n:
        spare = [d for t, _, _ in STRATA for d in pools[t] if d.sha256 not in seen]
        if not spare:
            break
        pick = rng.choice(spare)
        chosen.append(pick)
        seen.add(pick.sha256)
    return chosen[:n]


def cell_crop_box(cell: Cell, width: int, height: int) -> tuple[int, int, int, int] | None:
    boxes = list(cell.value_boxes)
    if cell.anchor_box:
        boxes.append(cell.anchor_box)
    if not boxes:
        return None
    x0 = min(b[0] for b in boxes) - PAD_X
    y0 = min(b[1] for b in boxes) - PAD_Y
    x1 = max(b[2] for b in boxes) + PAD_X
    y1 = max(b[3] for b in boxes) + PAD_Y
    if not cell.value_boxes and cell.anchor_box:
        # The resolver saw the label but bound nothing: show the whole row to
        # the right of it so the reader can see what was there.
        x1 = min(1.0, cell.anchor_box[2] + 0.45)
    return (
        max(0, int(x0 * width)),
        max(0, int(y0 * height)),
        min(width, int(x1 * width)),
        min(height, int(y1 * height)),
    )


def pack_document(doc: Doc, export: Path, out: Path) -> tuple[dict[str, object], dict[str, object]]:
    """Copy the image, cut the crops, and return (record, pipeline_cells)."""
    from PIL import Image

    image = Image.open(export / doc.rel_path).convert("RGB")
    width, height = image.size
    image_name = f"images/{doc.short}.jpg"
    shutil.copyfile(export / doc.rel_path, out / image_name)
    cells: list[dict[str, object]] = []
    pipeline: dict[str, object] = {}
    for locus in CELL_FIELDS:
        cell = doc.cells.get(locus)
        if cell is None:
            continue
        cell_id = f"{doc.short}:{locus}"
        crop_name: str | None = None
        box = cell_crop_box(cell, width, height)
        if box and box[2] - box[0] > 3 and box[3] - box[1] > 3:
            piece = image.crop(box)
            if piece.height < MIN_CROP_HEIGHT:
                scale = MIN_CROP_HEIGHT / piece.height
                piece = piece.resize(
                    (int(piece.width * scale), MIN_CROP_HEIGHT), Image.Resampling.LANCZOS
                )
            crop_name = f"crops/{doc.short}_{locus}.png"
            piece.save(out / crop_name)
        suggestions: dict[str, object] = {
            "pipeline": {
                "value": cell.value,
                "raw": cell.raw,
                "repaired": cell.repaired,
                "status": cell.status,
                "reason": cell.reason,
                "rule": cell.rule_id,
                "second_allele": cell.second_allele,
                "stability": cell.stability,
            },
        }
        if cell.tesseract:
            suggestions["tesseract"] = cell.tesseract
        if cell.decode:
            suggestions["decode"] = cell.decode
        cells.append(
            {
                "cell_id": cell_id,
                "locus": locus,
                "kind": "DRBX" if locus in DRBX_LOCI else "HLA",
                "status": cell.status,
                "value": cell.value,
                "crop": crop_name,
                "anchor_box": cell.anchor_box,
                "value_boxes": cell.value_boxes,
                "suggestions": suggestions,
            }
        )
        pipeline[cell_id] = {
            "status": cell.status,
            "locus": locus,
            "value": cell.value,
            "rule": cell.rule_id,
        }
    record: dict[str, object] = {
        "id": doc.short,
        "sha256": doc.sha256,
        "image": image_name,
        "width": width,
        "height": height,
        "quality_band": doc.quality_band,
        "family": doc.family,
        "comparison_sheet": doc.comparison_sheet,
        "consistency": doc.consistency,
        "consistency_reason": doc.consistency_reason,
        "tags": doc.tags,
        "primary_tag": doc.tags[0] if doc.tags else None,
        "role": doc.role,
        "abo": doc.abo,
        "rh": doc.rh,
        "cells": cells,
    }
    return record, pipeline


def build_pack(
    facts_db: Path,
    export: Path,
    out: Path,
    n: int,
    seed: int,
    page: Path,
    suggestions_dir: Path | None = None,
) -> dict[str, int]:
    con = sqlite3.connect(facts_db)
    docs = load_documents(con)
    con.close()
    chosen = choose(docs, n, seed, export)
    if len({d.short for d in chosen}) != len(chosen):
        raise ValueError("two chosen documents share a 16-character id prefix")
    out.mkdir(parents=True, exist_ok=True)
    (out / "images").mkdir(exist_ok=True)
    (out / "crops").mkdir(exist_ok=True)
    records: list[dict[str, object]] = []
    pipeline: dict[str, object] = {}
    for doc in chosen:
        record, cells = pack_document(doc, export, out)
        records.append(record)
        pipeline.update(cells)
    extra: dict[str, dict[str, str]] = {}
    if suggestions_dir and suggestions_dir.exists():
        for path in sorted(suggestions_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            extra[str(payload.get("engine") or path.stem)] = dict(payload.get("cells", {}))
    strata_counts = Counter(str(r["primary_tag"]) for r in records)
    pack = {
        "schema": PACK_SCHEMA,
        "pack_id": f"{seed}-{n}-{time.strftime('%Y%m%d', time.gmtime())}",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        "strata": [
            {"tag": t, "weight": w, "meaning": m, "n": strata_counts.get(t, 0)}
            for t, w, m in STRATA
        ],
        "n_documents": len(records),
        "n_cells": len(pipeline),
        "engines": sorted(extra),
        "suggestions": extra,
        "documents": records,
    }
    (out / "pack.json").write_text(json.dumps(pack, ensure_ascii=False), encoding="utf-8")
    (out / "pack.js").write_text(
        "window.PACK = " + json.dumps(pack, ensure_ascii=False) + ";\n", encoding="utf-8"
    )
    (out / "pipeline.json").write_text(
        json.dumps({"schema": "golden-hidden/v1", "cells": pipeline}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    shutil.copyfile(page, out / "index.html")
    write_launcher(out)
    return {t: strata_counts.get(t, 0) for t, _, _ in STRATA}


def write_launcher(out: Path) -> None:
    """A double-clickable server for the pack.

    Opened straight off the disk, a browser may refuse this page `localStorage`,
    and the page would then forget the labels on reload. It says so when that
    happens, but the better answer is not to depend on it: serving the folder
    over localhost makes storage ordinary, and costs the reader one click.
    """
    windows = [
        "@echo off",
        'cd /d "%~dp0"',
        'start "" http://localhost:8765/index.html',
        "python -m http.server 8765 --bind 127.0.0.1",
        "",
    ]
    posix = [
        "#!/bin/sh",
        'cd "$(dirname "$0")"',
        "python -m http.server 8765 --bind 127.0.0.1",
        "",
    ]
    # newline="" or the platform translates these again and cmd.exe gets \r\r\n.
    (out / "serve.cmd").write_text("\r\n".join(windows), encoding="ascii", newline="")
    (out / "serve.sh").write_text("\n".join(posix), encoding="ascii", newline="")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--export", type=Path, default=ROOT / "data/raw/ChatExport_2026-08-31")
    parser.add_argument("--out", type=Path, default=ROOT / "data/review/hla_pack")
    parser.add_argument("--n", type=int, default=150)
    parser.add_argument("--seed", type=int, default=20260902)
    parser.add_argument("--page", type=Path, default=ROOT / "tools/hla_review.html")
    parser.add_argument(
        "--suggestions",
        type=Path,
        default=None,
        help="directory of <engine>.json files {engine, cells:{cell_id: text}} to show as well",
    )
    args = parser.parse_args()
    if not args.facts.exists():
        print(f"missing {args.facts}; run scripts/extract_facts.py first")
        return 2
    counts = build_pack(
        args.facts, args.export, args.out, args.n, args.seed, args.page, args.suggestions
    )
    print(f"packed {sum(counts.values())} documents into {args.out}")
    for tag, count in counts.items():
        print(f"  {tag:<24}{count:>5}")
    print("Run serve.cmd in that directory, then label at http://localhost:8765 .")
    print("Labels export as golden-labels/v1 and are scored by scripts/golden_score.py.")
    print("Nothing in this directory may be committed: it is the patients' reports.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
