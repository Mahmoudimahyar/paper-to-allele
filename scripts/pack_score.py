#!/usr/bin/env python3
"""Score one annotator's anchored review-pack labels against the pipeline.

This is NOT the golden-corpus gate (`golden_score.py`). That gate needs two blind
labellers and a third adjudicator, because a person who sees the proposal beside
the crop measures agreement rather than truth. The review pack is the other
instrument: the labeller sees the proposal on purpose, works the strata that
were chosen because something looked wrong, and the question is "where does the
pipeline fail, and how" rather than "what is its error rate".

So this prints diagnostics, per locus and per stratum, and never a PASS. It also
prints the DRB3/4/5 shape diagnostics that decide whether the presence model is
being asked the wrong question by the labelling page.

Counts and shapes only. No allele value, cell id or document id is printed; the
JSON report written to `.artifacts/` holds the same aggregates.

Usage:
    uv run --frozen python scripts/pack_score.py --export <golden-labels/v1.json>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kidneymatch.review.golden import (  # noqa: E402
    Adjudication,
    CellLabel,
    LabelState,
    Resolution,
    score_against_pipeline,
)

DRBX = ("DRB3", "DRB4", "DRB5")
GENE_DIGITS = {"03", "04", "05"}


def read_export(path: Path) -> tuple[dict[str, CellLabel], dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "golden-labels/v1":
        raise SystemExit(f"not a golden-labels/v1 export: {payload.get('schema')}")
    labels: dict[str, CellLabel] = {}
    for cell_id, entry in payload.get("cells", {}).items():
        resolution = entry.get("resolution")
        labels[cell_id] = CellLabel(
            state=LabelState(entry["state"]),
            alleles=tuple(str(a) for a in (entry.get("alleles") or ())),
            resolution=Resolution(resolution) if resolution else None,
            annotator=str(payload.get("annotator") or ""),
            unsure=bool(entry.get("unsure")),
        )
    return labels, payload


def read_pipeline(path: Path) -> dict[str, tuple[str, str, tuple[str, ...]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for cell_id, entry in payload["cells"].items():
        raw = entry.get("value") or ""
        values = tuple(part.split("*")[-1] for part in raw.split() if part)
        out[cell_id] = (entry["status"], entry["locus"], values)
    return out


def read_pack(path: Path) -> tuple[dict[str, dict], dict[str, dict]]:
    """(document id -> record, cell id -> cell) from pack.json."""
    pack = json.loads(path.read_text(encoding="utf-8"))
    docs = {d["id"]: d for d in pack["documents"]}
    cells = {c["cell_id"]: c for d in pack["documents"] for c in d["cells"]}
    return docs, cells


def mask(text: str | None) -> str:
    """The SHAPE of a token: digits to d, letters to L, everything else kept."""
    if not text:
        return "(empty)"
    s = re.sub(r"\d", "d", str(text))
    s = re.sub(r"[A-Za-z]", "L", s)
    return s


def scored_table(report) -> list[str]:
    lines = [f"{'locus':<8}{'correct':>9}{'false':>8}{'missed':>8}{'abstained':>11}"]
    for locus, tally in sorted(report.per_locus.items()):
        lines.append(
            f"{locus:<8}{tally.correct:>9,}{tally.false_acceptances:>8,}"
            f"{tally.missed:>8,}{tally.correct_abstentions:>11,}"
        )
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--pack", type=Path, default=ROOT / "data/review/hla_pack")
    parser.add_argument("--out", type=Path, default=ROOT / ".artifacts/pack_score")
    args = parser.parse_args()

    labels, export = read_export(args.export)
    pipeline = read_pipeline(args.pack / "pipeline.json")
    docs, pack_cells = read_pack(args.pack / "pack.json")
    # The pipeline's own declaration of whether it read a second allele lives
    # in the pack's suggestions; with it the scorer can tell an honest partial
    # read from a value claimed complete (KI-015).
    for cell_id, entry in list(pipeline.items()):
        suggestion = (pack_cells.get(cell_id, {}).get("suggestions") or {}).get("pipeline") or {}
        second = suggestion.get("second_allele")
        if second:
            pipeline[cell_id] = (*entry[:3], str(second))
    if export.get("pack") and export["pack"] != json.loads(
        (args.pack / "pack.json").read_text(encoding="utf-8")
    ).get("pack_id"):
        print("WARNING: the export names a different pack than the one on disk")

    sure = {k: v for k, v in labels.items() if not v.unsure}
    truth_all = Adjudication(agreed=labels, disputed={})
    truth_sure = Adjudication(agreed=sure, disputed={})
    report_all = score_against_pipeline(truth_all, pipeline)
    report_sure = score_against_pipeline(truth_sure, pipeline)

    print("ANCHORED REVIEW PACK — one annotator, proposal visible. Diagnostic, not a gate.")
    print(f"labelled cells      : {len(labels):,}  (unsure: {len(labels) - len(sure):,})")
    docs_labelled = {cid.split(":")[0] for cid in labels}
    print(f"documents touched   : {len(docs_labelled):,} of {len(docs):,} in the pack")
    print()
    for name, report in (("all labelled cells", report_all), ("excluding unsure", report_sure)):
        print(f"== {name} ==")
        print(f"scored              : {report.scored:,}")
        print(f"  correct           : {report.correct:,}")
        print(f"  correct abstention: {report.correct_abstentions:,}")
        print(f"  missed (recall)   : {report.missed:,}")
        print(
            f"  partial           : {report.partial:,}"
            "   (one allele read, second declared unread, and it is in the pair)"
        )
        print(
            f"  contradicted      : {len(report.false_acceptances):,}"
            "   (pipeline resolved; human read it differently)"
        )
        print("\n".join(scored_table(report)))
        print()

    # ---- per stratum --------------------------------------------------------
    print("== by stratum (primary tag of the document) ==")
    per_tag: dict[str, Counter] = defaultdict(Counter)
    per_band: dict[str, Counter] = defaultdict(Counter)
    contradicted = set(report_all.false_acceptances)
    for cell_id, label in labels.items():
        doc = docs.get(cell_id.split(":")[0], {})
        tag = str(doc.get("primary_tag"))
        band = str(doc.get("quality_band"))
        entry = pipeline.get(cell_id)
        if entry is None:
            outcome = "not in pipeline"
        elif cell_id in contradicted:
            outcome = "contradicted"
        elif (
            entry[0] == "RESOLVED"
            and len(entry) > 3
            and entry[3] == "UNREAD"
            and len(entry[2]) == 1
            and label.state is LabelState.VALUE
            and len(label.alleles) == 2
        ):
            outcome = "partial"
        elif entry[0] == "RESOLVED":
            outcome = "correct"
        elif label.state in (LabelState.VALUE, LabelState.PRESENT_ONLY, LabelState.ABSENT):
            outcome = "missed"
        else:
            outcome = "abstained"
        per_tag[tag][outcome] += 1
        per_band[band][outcome] += 1
    cols = ("correct", "partial", "contradicted", "missed", "abstained")
    print(f"{'stratum':<24}{'n':>5}" + "".join(f"{c:>14}" for c in cols))
    for tag, c in sorted(per_tag.items(), key=lambda kv: -sum(kv[1].values())):
        print(f"{tag:<24}{sum(c.values()):>5}" + "".join(f"{c.get(k, 0):>14}" for k in cols))
    print()
    print(f"{'quality band':<24}{'n':>5}" + "".join(f"{c:>14}" for c in cols))
    for band, c in sorted(per_band.items()):
        print(f"{band:<24}{sum(c.values()):>5}" + "".join(f"{c.get(k, 0):>14}" for k in cols))
    print()

    # ---- DRB3/4/5 diagnostics -----------------------------------------------
    print("== DRB3/4/5: what the row printed vs what the page asked for ==")
    raw_shapes: Counter[str] = Counter()
    for cell_id, label in labels.items():
        if label.state is LabelState.NOT_PRINTED:
            continue
        locus = cell_id.split(":")[1]
        if locus not in DRBX:
            continue
        cell = pack_cells.get(cell_id, {})
        raw = ((cell.get("suggestions") or {}).get("pipeline") or {}).get("raw")
        raw_shapes[mask(raw)] += 1
    print("pipeline raw-token shapes on labelled DRB3/4/5 cells (d=digit, L=letter):")
    for shape, n in raw_shapes.most_common(12):
        print(f"  {n:3d}  {shape}")

    value_cells = [
        (cid, lab)
        for cid, lab in labels.items()
        if cid.split(":")[1] in DRBX and lab.state is LabelState.VALUE
    ]
    gene_digit_only = sum(1 for _, lab in value_cells if set(lab.alleles) <= GENE_DIGITS)
    doubled = sum(
        1 for _, lab in value_cells if len(lab.alleles) == 2 and lab.alleles[0] == lab.alleles[1]
    )
    own_digit = 0
    for cid, lab in value_cells:
        gene = cid.split(":")[1]
        if lab.alleles and all(a == f"0{gene[-1]}" for a in lab.alleles):
            own_digit += 1
    print(f"human VALUE cells on DRB3/4/5      : {len(value_cells)}")
    print(f"  every allele in {{03,04,05}}      : {gene_digit_only}")
    print(f"  the two alleles identical         : {doubled}")
    print(f"  alleles == the cell's own gene digit (DRB4 -> 04): {own_digit}")
    print("  (a high count here means the page forced a NUMBER for a printed gene NAME)")

    by_doc: dict[str, dict[str, CellLabel]] = defaultdict(dict)
    for cid, lab in labels.items():
        by_doc[cid.split(":")[0]][cid.split(":")[1]] = lab
    trio_patterns: Counter[tuple[str, str, str]] = Counter()
    for loci in by_doc.values():
        trio = [loci.get(g) for g in DRBX]
        if all(trio):
            trio_patterns[tuple(t.state.value for t in trio)] += 1
    print("per-document state pattern (DRB3, DRB4, DRB5):")
    for pat, n in trio_patterns.most_common():
        print(f"  {n:2d}  {pat[0]:<12} {pat[1]:<12} {pat[2]:<12}")

    # ---- write the aggregate report ------------------------------------------
    args.out.mkdir(parents=True, exist_ok=True)
    out = args.out / f"{args.export.stem}.json"
    out.write_text(
        json.dumps(
            {
                "schema": "pack-score/v1",
                "export": args.export.name,
                "labelled": len(labels),
                "unsure": len(labels) - len(sure),
                "all": {
                    "scored": report_all.scored,
                    "correct": report_all.correct,
                    "partial": report_all.partial,
                    "correct_abstentions": report_all.correct_abstentions,
                    "missed": report_all.missed,
                    "contradicted": len(report_all.false_acceptances),
                    "per_locus": {k: asdict(v) for k, v in sorted(report_all.per_locus.items())},
                },
                "sure": {
                    "scored": report_sure.scored,
                    "correct": report_sure.correct,
                    "partial": report_sure.partial,
                    "missed": report_sure.missed,
                    "contradicted": len(report_sure.false_acceptances),
                },
                "by_stratum": {k: dict(v) for k, v in per_tag.items()},
                "by_quality_band": {k: dict(v) for k, v in per_band.items()},
                "drbx": {
                    "raw_shapes": dict(raw_shapes),
                    "value_cells": len(value_cells),
                    "gene_digit_only": gene_digit_only,
                    "doubled": doubled,
                    "own_gene_digit": own_digit,
                    "trio_patterns": {" | ".join(k): v for k, v in trio_patterns.items()},
                },
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nreport: {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
