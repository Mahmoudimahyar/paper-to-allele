#!/usr/bin/env python3
"""Find the printed forms in the corpus, and assign every document to one.

The previous version assigned **707 of 23,485** documents to a verified family
while one laboratory alone accounts for about two thirds of the corpus. The
skeptical review of ADR 0008 diagnosed why, and `kidneymatch.ocr.templates`
carries the fix and the evidence: the signature counted the grouped DRB3/4/5
row's VALUES as form labels, so one form split by genotype, and it clustered in
absolute page coordinates, which fragments a form photographed by hand.

The method here:

1. **Signature** from labels the form prints in a fixed place only.
2. **Prototypes** from documents that carry every one of those labels, grouped
   by their layout in a scale-and-offset-free comparison.
3. **Assignment** of any document with at least three labels by fitting a
   similarity transform to each prototype, refusing ties.

A document that matches nothing stays unassigned and gets the default relation.
That is the safe outcome: claiming a family would apply that family's authored
cell rule to a layout it was never measured on.

Output: `data/derived/template_families.json` (gitignored — it lists PHI images).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kidneymatch.hla.vocabulary import load_vocabulary  # noqa: E402
from kidneymatch.ocr.anchors import ResolutionStatus, ValueRule, resolve_document  # noqa: E402
from kidneymatch.ocr.store import read_corpus  # noqa: E402
from kidneymatch.ocr.templates import (  # noqa: E402
    CONSTANT_LABELS,
    MAX_RESIDUAL,
    MIN_LABELS,
    Assignment,
    LayoutPrototype,
    assign_prototype,
    constant_label_positions,
    fit_similarity,
)

DEFAULT_DB = ROOT / "data/derived/ocr_pass.sqlite"
DEFAULT_OUT = ROOT / "data/derived/template_families.json"

# A prototype is only worth authoring a rule against if enough documents share
# it; below this a "family" is a handful of photographs, not a printed form.
MIN_PROTOTYPE_MEMBERS = 100

# The conservative default relation, used only to sample which values a family
# binds so the prefix property can be measured without assuming it.
PROBE_RULE = ValueRule(direction="right", align_overlap=0.2, max_gap=20.0, max_values=2)


def _normalised(positions: dict[str, tuple[float, float]]) -> dict[str, tuple[float, float]]:
    """Put a document's labels in a frame of its own, so scale and offset drop out."""
    xs = [x for x, _ in positions.values()]
    ys = [y for _, y in positions.values()]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    spread = (
        sum((x - cx) ** 2 + (y - cy) ** 2 for x, y in positions.values()) / len(positions)
    ) ** 0.5
    if spread <= 1e-12:
        return {}
    return {locus: ((x - cx) / spread, (y - cy) / spread) for locus, (x, y) in positions.items()}


def _mean_positions(
    group: list[dict[str, tuple[float, float]]],
) -> dict[str, tuple[float, float]]:
    """The form's own label positions: the mean over the documents that share it."""
    summed: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for positions in group:
        for locus, point in positions.items():
            summed[locus].append(point)
    return {
        locus: (
            sum(p[0] for p in points) / len(points),
            sum(p[1] for p in points) / len(points),
        )
        for locus, points in summed.items()
    }


def build_prototypes(complete: list[dict[str, tuple[float, float]]]) -> list[LayoutPrototype]:
    """Group fully-labelled documents into printed forms.

    Greedy agglomeration in the normalised frame: a document either fits a
    prototype already found, or starts a new one. Simpler than a density
    clustering and, unlike one, it cannot label a document as noise merely
    because its neighbours were photographed at other distances.
    """
    prototypes: list[LayoutPrototype] = []
    members: list[list[dict[str, tuple[float, float]]]] = []

    for positions in complete:
        normalised = _normalised(positions)
        if not normalised:
            continue
        placed = False
        for index, prototype in enumerate(prototypes):
            fit = fit_similarity(normalised, prototype)
            if fit is not None and fit.residual <= 0.02:
                members[index].append(normalised)
                placed = True
                break
        if not placed:
            prototypes.append(LayoutPrototype.from_positions(f"T{len(prototypes)}", normalised))
            members.append([normalised])

    # Merge prototypes that are the SAME printed form.
    #
    # Greedy agglomeration at a tight threshold splits one form into several
    # seeds, exactly the fragmentation this rewrite exists to fix: measured, the
    # first version produced nine prototypes whose mutual residuals were 0.012
    # to 0.046, i.e. within the tolerance used to assign documents. Every
    # document then fitted two or more of them and was refused as ambiguous —
    # 4,096 of them. Two prototypes that fit each other are one form.
    groups = [list(group) for group in members]
    merged = True
    while merged:
        merged = False
        for i in range(len(groups)):
            if not groups[i]:
                continue
            for j in range(i + 1, len(groups)):
                if not groups[j]:
                    continue
                a = LayoutPrototype.from_positions("a", _mean_positions(groups[i]))
                fit = fit_similarity(_mean_positions(groups[j]), a)
                if fit is not None and fit.residual <= MAX_RESIDUAL:
                    groups[i].extend(groups[j])
                    groups[j] = []
                    merged = True
    refined: list[LayoutPrototype] = []
    for index, group in enumerate(g for g in groups if g):
        if len(group) < MIN_PROTOTYPE_MEMBERS:
            continue
        refined.append(LayoutPrototype.from_positions(f"FORM#{index}", _mean_positions(group)))
    return refined


def discover(db: Path, out: Path) -> int:
    vocabulary = load_vocabulary()
    documents = list(read_corpus(db, with_boxes_only=True))
    positions = {doc.sha256: constant_label_positions(doc.boxes) for doc in documents}
    complete = [p for p in positions.values() if len(p) == len(CONSTANT_LABELS)]
    print(f"documents: {len(documents):,}")
    print(f"  with every form label   : {len(complete):,}")
    print(
        f"  with >= {MIN_LABELS} form labels : "
        f"{sum(1 for p in positions.values() if len(p) >= MIN_LABELS):,}\n"
    )

    prototypes = build_prototypes(complete)
    print(f"prototypes found (>= {MIN_PROTOTYPE_MEMBERS} members): {len(prototypes)}\n")

    assigned: dict[str, Assignment] = {}
    for doc in documents:
        assignment = assign_prototype(doc.boxes, prototypes)
        if assignment is not None:
            assigned[doc.sha256] = assignment

    by_prototype: dict[str, list[str]] = defaultdict(list)
    residuals: dict[str, list[float]] = defaultdict(list)
    for sha, assignment in assigned.items():
        by_prototype[assignment.prototype_id].append(sha)
        residuals[assignment.prototype_id].append(assignment.residual)

    # Does this form print the locus on every value? That property, not the
    # distance, is what makes reading a whole row band safe, so it is measured
    # per family rather than assumed. `extract_facts.py` reads this flag.
    # Measured over values actually BOUND in a locus cell, not over every
    # parseable box on the page: a page carries dates, sample numbers and table
    # entries that parse as values and never name a locus, and counting those
    # put the share at 65% when the property being tested is about the form's
    # value cells.
    prefixed: dict[str, list[int]] = defaultdict(list)
    for doc in documents:
        assignment = assigned.get(doc.sha256)
        if assignment is None:
            continue
        for result in resolve_document(doc.boxes, PROBE_RULE, vocabulary=vocabulary).values():
            if result.status is not ResolutionStatus.RESOLVED:
                continue
            for value in result.parsed_values:
                prefixed[assignment.prototype_id].append(int(value.locus_prefix is not None))

    def prefix_share(family_id: str) -> float:
        seen = prefixed.get(family_id) or []
        return round(sum(seen) / len(seen), 4) if seen else 0.0

    families = [
        {
            "family_id": prototype.prototype_id,
            "prefix_share": prefix_share(prototype.prototype_id),
            "prints_locus_on_values": prefix_share(prototype.prototype_id) >= 0.95,
            "label_positions": {locus: list(point) for locus, point in prototype.positions.items()},
            "n_documents": len(by_prototype[prototype.prototype_id]),
            "median_residual": round(
                sorted(residuals[prototype.prototype_id])[
                    len(residuals[prototype.prototype_id]) // 2
                ],
                5,
            )
            if residuals[prototype.prototype_id]
            else None,
            "sha256": sorted(by_prototype[prototype.prototype_id]),
        }
        for prototype in prototypes
        if by_prototype[prototype.prototype_id]
    ]
    families.sort(key=lambda f: -f["n_documents"])

    payload = {
        "version": 2,
        "method": "constant-label signature, similarity fit, ties refused",
        "constant_labels": list(CONSTANT_LABELS),
        "n_documents": len(documents),
        "n_assigned": len(assigned),
        "families": families,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")

    print(f"{'family':<10}{'documents':>11}{'median residual':>18}{'locus on values':>18}")
    for family in families:
        print(
            f"{family['family_id']:<10}{family['n_documents']:>11,}"
            f"{family['median_residual']!s:>18}{family['prefix_share']:>17.1%}"
        )
    share = 100 * len(assigned) / max(len(documents), 1)
    print(f"\nassigned: {len(assigned):,} of {len(documents):,} ({share:.1f}%)")
    label_counts = Counter(len(p) for p in positions.values())
    print(f"unassigned by label count: {dict(sorted(label_counts.items()))}")
    print(f"written to {out.relative_to(ROOT)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    if not args.db.exists():
        print(f"missing {args.db}; run scripts/ocr_pass.py first")
        return 2
    return discover(args.db, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
