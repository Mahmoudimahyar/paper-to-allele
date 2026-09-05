#!/usr/bin/env python3
"""Score the pipeline against the golden corpus. The acceptance gate for OCR-001.

This is the only place a number in this project becomes an accuracy rather than
a yield. It exits non-zero if a single cell was resolved to something a human
did not read, because `OCR-001`'s acceptance criterion is that wrong-locus false
acceptance is **zero** on the release golden set — not low, zero.

`scripts/acceptance.py run OCR-001` captures this output as the evidence file;
a criterion cannot be marked met without it.

Usage:
    uv run --frozen --extra hist python scripts/golden_score.py \\
        --labels data/review/golden/labels_a.json data/review/golden/labels_b.json \\
        --adjudicated data/review/golden/adjudicated.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kidneymatch.review.golden import (  # noqa: E402
    CellLabel,
    LabelState,
    Resolution,
    adjudicate,
    score_against_pipeline,
)


def read_labels(path: Path) -> dict[str, CellLabel]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, CellLabel] = {}
    for cell_id, entry in payload.get("cells", {}).items():
        resolution = entry.get("resolution")
        out[cell_id] = CellLabel(
            state=LabelState(entry["state"]),
            alleles=tuple(entry.get("alleles") or ()),
            resolution=Resolution(resolution) if resolution else None,
            annotator=str(entry.get("annotator") or payload.get("annotator") or path.stem),
            unsure=bool(entry.get("unsure")),
        )
    return out


def read_pipeline(path: Path) -> dict[str, tuple[str, ...]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, tuple[str, ...]] = {}
    for cell_id, entry in payload["cells"].items():
        raw = entry.get("value") or ""
        # A locus value is stored as the space-separated alleles it resolved to;
        # the locus prefix is provenance, not part of the reading being judged.
        values = tuple(part.split("*")[-1] for part in raw.split() if part)
        # The pipeline's own declaration of whether it read the second allele
        # (KI-015). Older hidden files lack it, and then a single value against a
        # printed pair stays a false acceptance, as before.
        second = entry.get("second_allele")
        out[cell_id] = (
            (entry["status"], entry["locus"], values, str(second))
            if second
            else (entry["status"], entry["locus"], values)
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, nargs=2, required=True)
    parser.add_argument("--adjudicated", type=Path, default=None)
    parser.add_argument("--hidden", type=Path, default=ROOT / "data/review/golden/hidden.json")
    args = parser.parse_args()

    for path in (*args.labels, args.hidden):
        if not path.exists():
            print(f"missing {path}")
            return 2

    first, second = (read_labels(path) for path in args.labels)
    settled = (
        read_labels(args.adjudicated) if args.adjudicated and args.adjudicated.exists() else None
    )
    truth = adjudicate(first, second, settled)
    report = score_against_pipeline(truth, read_pipeline(args.hidden))

    print(f"labelled by         : {args.labels[0].stem} and {args.labels[1].stem}")
    print(f"cells agreed        : {len(truth.agreed):,}")
    print(f"cells still disputed: {len(truth.disputed):,}")
    print()
    print(f"scored              : {report.scored:,}")
    print(f"  correct           : {report.correct:,}")
    print(f"  correct abstention: {report.correct_abstentions:,}")
    print(f"  missed (recall)   : {report.missed:,}")
    print(f"  partial (2nd unread, declared): {report.partial:,}")
    print(f"  FALSE ACCEPTANCE  : {len(report.false_acceptances):,}")
    if report.per_locus:
        print(f"\n{'locus':<8}{'correct':>9}{'false':>8}{'missed':>8}{'abstained':>11}")
        for locus, tally in sorted(report.per_locus.items()):
            print(
                f"{locus:<8}{tally.correct:>9,}{tally.false_acceptances:>8,}"
                f"{tally.missed:>8,}{tally.correct_abstentions:>11,}"
            )

    bound = report.false_acceptance_upper_bound
    if bound is not None:
        print(
            f"\nzero failures over {report.accepted:,} accepted cells: false acceptance "
            f"is at most {bound:.3%} (rule of three, 95%)."
        )
        print(
            "Cells within one document and documents within one family are not "
            "independent, so this bounds the per-cell rate, not the per-family one."
        )

    if not report.passed:
        print(f"\nFAIL: {len(report.false_acceptances)} cell(s) resolved to something the")
        print("golden corpus does not agree with. OCR-001 requires zero.")
        for cell_id in report.false_acceptances[:20]:
            print(f"  {cell_id}")
        return 1
    if report.scored == 0:
        print("\nFAIL: nothing was scored. Label the corpus before claiming a rate.")
        return 1
    print("\nPASS: no cell was resolved to something the golden corpus contradicts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
