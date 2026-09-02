#!/usr/bin/env python3
"""Draw the golden-corpus sample for manual labelling.

`TEST_PLAN.md` section 8 requires 200 manually labelled unique documents before
full-batch extraction, targeting zero wrong-locus false acceptance and >= 99.5%
critical-field precision.

**The unit that matters is the CELL, not the document.** A typing report carries
several locus cells, so 200 documents yields roughly 800 labelled cells. That
distinction is what makes 200 defensible: by the rule of three, zero failures in
n observations gives a 95% upper bound of 3/n, so ~800 cells bounds the error
rate at ~0.375%, which is consistent with a >= 99.5% precision claim. **200
documents alone (200 observations) would only bound it at 1.5% and could not
support the claim at all.** Record cells labelled, not just documents.

Sampling design:

* **Equal allocation across VERIFIED template families**, not proportional.
  The purpose is to certify each template's cell mapping; a family with 95
  documents needs as much evidence as one with 779, and proportional allocation
  would starve the small ones.
* **A mixture/unverified stratum**, because those are where template matching is
  expected to fail and the pipeline must abstain rather than guess.
* **A non-report stratum** (documents with fewer than two loci), to measure that
  the classifier correctly declines to extract from advertisements and
  screenshots. A corpus made only of clean reports cannot measure false
  acceptance at all.
* **Quality bands within each stratum**, so the low-resolution tail is
  represented rather than averaged away.

Output: `data/derived/golden_sample.json` (gitignored — it lists PHI images).
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data/derived/ocr_pass.sqlite"
DEFAULT_FAMILIES = ROOT / "data/derived/template_families.json"
DEFAULT_OUT = ROOT / "data/derived/golden_sample.json"


# Quality bands by longest edge. 520 px is the corpus median, so the bands are
# chosen to split the real distribution rather than to look tidy.
def quality_band(width: int | None, height: int | None) -> str:
    longest = max(width or 0, height or 0)
    if longest == 0:
        return "unknown"
    if longest <= 560:
        return "low_<=560"
    if longest <= 900:
        return "mid_561-900"
    return "high_>900"


ALLELE_RE = re.compile(
    r"\b(?:DRB1|DQB1|DQA1|DPB1|DPA1|DRB3|DRB4|DRB5|[ABC])\s?\*?\s?(\d{2})(?::(\d{2,3}))?\b"
)


def allele_fingerprints(db: Path) -> dict[str, str]:
    """Map sha256 -> the sorted set of allele tokens the document reports.

    These images are already SHA-256 unique, so a shared fingerprint means NEAR
    duplication: the same report rephotographed or recompressed. Measured on this
    corpus, 62.9% of documents carrying >=4 allele tokens share a fingerprint with
    another, and one family of 83 documents collapses to just 3 distinct
    fingerprints.

    Sampling without collapsing these would draw the SAME patient's report many
    times and report it as independent evidence, which would inflate every
    confidence bound computed from the golden corpus.
    """
    con = sqlite3.connect(db)
    out: dict[str, str] = {}
    for sha, texts_json in con.execute("SELECT sha256, texts_json FROM ocr_result WHERE n_boxes>0"):
        tokens = sorted(
            {
                m.group(0).replace(" ", "").upper()
                for m in ALLELE_RE.finditer(" ".join(json.loads(texts_json)))
            }
        )
        if len(tokens) >= 4:
            out[sha] = "|".join(tokens)
    con.close()
    return out


def collapse_near_duplicates(pool: list[dict], fingerprints: dict[str, str]) -> list[dict]:
    """Keep at most one document per allele fingerprint."""
    seen: set[str] = set()
    kept = []
    for row in pool:
        fp = fingerprints.get(row["sha256"])
        if fp is not None:
            if fp in seen:
                continue
            seen.add(fp)
        kept.append(row)
    return kept


def stratified(pool: list[dict], n: int, rng: np.random.Generator) -> list[dict]:
    """Take n from pool, spread as evenly as possible across quality bands."""
    if not pool or n <= 0:
        return []
    by_band: dict[str, list[dict]] = defaultdict(list)
    for row in pool:
        by_band[row["quality_band"]].append(row)
    bands = sorted(by_band)
    picked: list[dict] = []
    per = max(1, n // max(1, len(bands)))
    for band in bands:
        rows = by_band[band]
        take = min(per, len(rows))
        for i in rng.choice(len(rows), take, replace=False):
            picked.append(rows[int(i)])
    # top up from whatever remains if rounding left us short
    if len(picked) < n:
        chosen = {r["sha256"] for r in picked}
        rest = [r for r in pool if r["sha256"] not in chosen]
        extra = min(n - len(picked), len(rest))
        for i in rng.choice(len(rest), extra, replace=False):
            picked.append(rest[int(i)])
    return picked[:n]


def build(db: Path, families_path: Path, out: Path, total: int) -> int:
    con = sqlite3.connect(db)
    meta = {
        sha: {
            "sha256": sha,
            "rel_path": rel,
            "n_boxes": nb,
            "quality_band": quality_band(w, h),
            "width": w,
            "height": h,
        }
        for sha, rel, w, h, nb in con.execute(
            "SELECT sha256, rel_path, width, height, n_boxes FROM ocr_result"
        )
    }
    con.close()

    fingerprints = allele_fingerprints(db)
    families = json.loads(families_path.read_text(encoding="utf-8"))
    verified = [f for f in families if f["verified_single_template"]]
    mixture = [f for f in families if not f["verified_single_template"]]
    in_family = {s for f in families for s in f["sha256"]}

    rng = np.random.default_rng(20260902)
    sample: list[dict] = []

    # 60% across verified families, EQUALLY, since each must be certified
    verified_budget = int(total * 0.60)
    per_family = max(1, verified_budget // max(1, len(verified)))
    for fam in verified:
        pool = [
            dict(meta[s], family_id=fam["family_id"], stratum="verified_template")
            for s in fam["sha256"]
            if s in meta
        ]
        sample += stratified(collapse_near_duplicates(pool, fingerprints), per_family, rng)

    # 20% from mixtures — where matching should abstain
    mix_pool = [
        dict(meta[s], family_id=f["family_id"], stratum="mixture_family")
        for f in mixture
        for s in f["sha256"]
        if s in meta
    ]
    sample += stratified(collapse_near_duplicates(mix_pool, fingerprints), int(total * 0.20), rng)

    # 10% LOW-RESOLUTION reports, sampled regardless of family.
    #
    # This stratum exists because template discovery is strongly resolution
    # biased: only 0.05% of images <=560 px reach a VERIFIED family, against
    # 7.03% of images >900 px — a ~140x gap. Without forcing them in, the golden
    # corpus would certify the pipeline on the easy half of the archive and say
    # nothing about the 9,666 low-resolution documents, which is exactly where
    # the mandatory-review policy has to hold.
    low_pool = [
        dict(meta[s], family_id=None, stratum="low_res_report")
        for s in in_family
        if s in meta and meta[s]["quality_band"] == "low_<=560"
    ]
    sample += stratified(collapse_near_duplicates(low_pool, fingerprints), int(total * 0.10), rng)

    # remainder: non-reports — the only way to measure false acceptance
    non_pool = [
        dict(meta[s], family_id=None, stratum="non_report") for s in meta if s not in in_family
    ]
    sample += stratified(collapse_near_duplicates(non_pool, fingerprints), total - len(sample), rng)

    seen, unique = set(), []
    for row in sample:
        if row["sha256"] not in seen:
            seen.add(row["sha256"])
            unique.append(row)

    payload = {
        "version": 1,
        "n_documents": len(unique),
        "design": "equal allocation across verified families; mixture and "
        "non-report strata included so false acceptance is measurable",
        "note": "The metric unit is the CELL. Record cells labelled, not just documents.",
        "documents": unique,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8", newline="\n")

    counts: dict[tuple[str, str], int] = defaultdict(int)
    for row in unique:
        counts[(row["stratum"], row["quality_band"])] += 1
    print(f"golden sample: {len(unique)} documents\n")
    print(f"{'stratum':<20}{'quality band':<16}{'docs':>6}")
    for (stratum, band), count in sorted(counts.items()):
        print(f"{stratum:<20}{band:<16}{count:>6}")
    per_stratum: dict[str, int] = defaultdict(int)
    for row in unique:
        per_stratum[row["stratum"]] += 1
    print()
    for stratum, count in sorted(per_stratum.items()):
        print(f"  {stratum:<22}{count:>5}  ({100 * count / len(unique):.0f}%)")
    verified_ids = {
        r["family_id"] for r in unique if r["family_id"] and r["stratum"] == "verified_template"
    }
    print(f"\nverified families covered: {len(verified_ids)} of {len(verified)}")
    print(f"written to {out.relative_to(ROOT)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--families", type=Path, default=DEFAULT_FAMILIES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--total", type=int, default=200)
    args = parser.parse_args()
    for path in (args.db, args.families):
        if not path.exists():
            print(f"missing {path}")
            return 2
    return build(args.db, args.families, args.out, args.total)


if __name__ == "__main__":
    raise SystemExit(main())
