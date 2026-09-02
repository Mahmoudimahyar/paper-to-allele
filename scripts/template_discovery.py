#!/usr/bin/env python3
"""Discover candidate laboratory template families from extracted geometry.

A template family is a recurring lab form layout. Finding them is a prerequisite
for the template registry, which is what supplies the LOCUS for each cell. This
script proposes candidates; it does not author cell boxes and it never assigns a
locus to a value.

Method, in three steps:

1. **Locus-position signature.** For each document, the normalized centre of the
   box containing each unambiguous locus label (`DRB1`, `DRB3`, `DRB4`, `DRB5`,
   `DQA1`, `DQB1`, `DPA1`, `DPB1`). Where a form prints its loci is far more
   discriminative than generic ink density, and it is exactly the information the
   registry needs. Single-letter loci (`A`, `B`, `C`) are excluded: they match
   too much incidental text to be trusted.

2. **Group by presence pattern, then cluster by position.** Which loci a form
   reports is itself a strong fingerprint and needs no geometry. Within each
   pattern, HDBSCAN over the label coordinates separates forms that report the
   same loci but lay them out differently.

3. **Verify against an INDEPENDENT signal.** A cluster found in locus-position
   space must also be tight in layout-occupancy space, which the clustering never
   saw. A cluster that is not is a MIXTURE, and hand-authoring cell boxes against
   a mixture would map cells to the wrong locus on part of the family — the exact
   failure the OCR spec forbids. Verified clusters are the only ones eligible for
   registry authoring.

Output: `data/derived/template_families.json` (gitignored; it references PHI
images by hash and path).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kidneymatch.ocr.glyphs import canonical_locus_label  # noqa: E402
from kidneymatch.ocr.store import read_corpus  # noqa: E402

DEFAULT_DB = ROOT / "data/derived/ocr_pass.sqlite"
DEFAULT_OUT = ROOT / "data/derived/template_families.json"

LOCI = ["DRB1", "DRB3", "DRB4", "DRB5", "DQA1", "DQB1", "DPA1", "DPB1"]

GRID = 16  # layout-occupancy resolution, used only for verification
MIN_GROUP = 200  # smallest presence group worth clustering
MIN_CLUSTER = 60  # smallest cluster worth proposing as a family
TIGHT_SD = 0.035  # mean coordinate sd below which a cluster is geometrically tight
MIN_LIFT = 0.10  # coherence lift over baseline required to call it a template
MIN_MODAL_SHARE = 0.70  # each locus label must sit in one modal position


def load(db: Path):
    """Layout signatures over the corpus.

    Reads through `kidneymatch.ocr.store`, so thumbnail copies are excluded
    (KI-009), and identifies locus labels with `glyphs.canonical_locus_label`,
    which repairs the recognizer's final-character confusions. The earlier
    version used neither: it clustered 9,581 thumbnails alongside originals and
    saw `DRB1` on 3,511 documents instead of 16,025, because the label is read
    `DRBI` more often than correctly. Both figures in the previous family set
    are therefore superseded.
    """
    keys, pos, occ = [], [], []
    for doc in read_corpus(db, with_boxes_only=True):
        centres = np.full((len(LOCI), 2), -1.0, dtype=np.float32)
        seen = np.zeros(len(LOCI), dtype=np.float32)
        grid = np.zeros((GRID, GRID), dtype=np.float32)
        for box in doc.boxes:
            x0, y0, x1, y1 = box.x0, box.y0, box.x1, box.y1
            gx0, gx1 = int(np.clip(x0 * GRID, 0, GRID - 1)), int(np.clip(x1 * GRID, 0, GRID - 1))
            gy0, gy1 = int(np.clip(y0 * GRID, 0, GRID - 1)), int(np.clip(y1 * GRID, 0, GRID - 1))
            grid[gy0 : gy1 + 1, gx0 : gx1 + 1] += 1.0
            locus = canonical_locus_label(box.text or "")
            if locus in LOCI:
                i = LOCI.index(locus)
                if not seen[i]:
                    centres[i] = ((x0 + x1) / 2, (y0 + y1) / 2)
                    seen[i] = 1.0

        if seen.sum() < 2:
            continue
        flat = grid.ravel()
        norm = np.linalg.norm(flat)
        if norm == 0:
            continue
        keys.append(doc.sha256)
        pos.append(np.concatenate([centres.ravel(), seen]))
        occ.append(flat / norm)

    return keys, np.asarray(pos, np.float32), np.asarray(occ, np.float32)


def coherence(occ: np.ndarray, rows: np.ndarray, rng: np.random.Generator) -> float | None:
    """Mean pairwise cosine similarity in layout space — the independent check."""
    if len(rows) < 20:
        return None
    sel = rng.choice(rows, min(300, len(rows)), replace=False)
    v = occ[sel]
    v = v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)
    sim = v @ v.T
    n = len(sim)
    return float((sim.sum() - n) / (n * n - n))


def anchor_purity(pos: np.ndarray, rows: np.ndarray, pat: np.ndarray) -> dict:
    """Do the members print each locus label in ONE place, or in several?

    Layout coherence is necessary but NOT sufficient. Measured on this corpus, a
    family of 1,034 documents that passes every coherence test prints its DRB4
    label in two different columns 0.285 apart, and the layout signature cannot
    separate the variants. Authoring one cell box there would bind the wrong
    locus for ~40% of members (ADR 0007).

    This test finds that: it bins each locus's x positions and reports the share
    held by the largest mode. A strong second mode means two sub-templates.
    """
    worst_locus, worst_share = None, 1.0
    for i, present in enumerate(pat):
        if not present:
            continue
        xs = pos[rows][:, 2 * i]
        xs = xs[xs >= 0]
        if len(xs) < 20:
            continue
        hist, _ = np.histogram(xs, bins=np.arange(0, 1.02, 0.02))
        share = float(hist.max() / hist.sum()) if hist.sum() else 1.0
        if share < worst_share:
            worst_share, worst_locus = share, LOCI[i]
    return {"modal_share": round(worst_share, 3), "weakest_locus": worst_locus}


def discover(db: Path, out: Path) -> int:
    from sklearn.cluster import HDBSCAN

    keys, pos, occ = load(db)
    print(f"documents with >=2 located loci: {len(keys):,}")
    presence = pos[:, len(LOCI) * 2 :] > 0
    rng = np.random.default_rng(0)

    patterns: dict[bytes, np.ndarray] = {}
    for i, row in enumerate(presence):
        patterns.setdefault(row.tobytes(), []).append(i)
    big = {k: np.asarray(v) for k, v in patterns.items() if len(v) >= MIN_GROUP}
    print(f"presence patterns: {len(patterns):,} total, {len(big)} with >={MIN_GROUP} documents\n")

    families = []
    for pat_bytes, rows in sorted(big.items(), key=lambda kv: -len(kv[1])):
        pat = np.frombuffer(pat_bytes, dtype=bool)
        name = "+".join(loc for loc, f in zip(LOCI, pat, strict=True) if f)
        cols = [c for i, f in enumerate(pat) if f for c in (2 * i, 2 * i + 1)]
        sub = pos[rows][:, cols]

        labels = HDBSCAN(
            min_cluster_size=MIN_CLUSTER, min_samples=10, cluster_selection_epsilon=0.02, copy=True
        ).fit_predict(sub)
        base = coherence(occ, rows, rng)
        if base is None:
            continue

        for cluster in sorted(set(labels[labels >= 0])):
            member_rows = rows[labels == cluster]
            sd = float(sub[labels == cluster].std(axis=0).mean())
            coh = coherence(occ, member_rows, rng)
            if coh is None:
                continue
            lift = coh - base
            purity = anchor_purity(pos, member_rows, pat)
            verified = bool(
                lift >= MIN_LIFT and sd <= TIGHT_SD and purity["modal_share"] >= MIN_MODAL_SHARE
            )
            families.append(
                {
                    "family_id": f"{name}#{cluster}",
                    "presence_pattern": name,
                    "n_documents": int(len(member_rows)),
                    "position_sd": round(sd, 4),
                    "layout_coherence": round(coh, 3),
                    "baseline_coherence": round(base, 3),
                    "coherence_lift": round(lift, 3),
                    "anchor_modal_share": purity["modal_share"],
                    "weakest_anchor_locus": purity["weakest_locus"],
                    "verified_single_template": verified,
                    "sha256": [keys[i] for i in member_rows],
                }
            )

    families.sort(key=lambda f: (-f["verified_single_template"], -f["n_documents"]))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(families, indent=2), encoding="utf-8", newline="\n")

    verified = [f for f in families if f["verified_single_template"]]
    print(f"{'family':<26}{'docs':>7}{'pos sd':>8}{'lift':>7}{'modal':>7}{'weak':>7}  verdict")
    for f in families[:20]:
        verdict = (
            "VERIFIED single template" if f["verified_single_template"] else "candidate / mixture"
        )
        print(
            f"{f['family_id']:<26}{f['n_documents']:>7,}{f['position_sd']:>8.4f}"
            f"{f['coherence_lift']:>+7.3f}{f['anchor_modal_share']:>7.2f}"
            f"{(f['weakest_anchor_locus'] or '-'):>7}  {verdict}"
        )
    print(f"\ntotal candidate families : {len(families)}")
    print(
        f"VERIFIED single templates: {len(verified)}  "
        f"covering {sum(f['n_documents'] for f in verified):,} documents"
    )
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
