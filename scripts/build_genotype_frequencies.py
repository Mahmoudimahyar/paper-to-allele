#!/usr/bin/env python3
"""Measure how identifying an HLA genotype actually is in this corpus.

`ENTITY-001`. The tempting rule — "same HLA on three loci means the same
person" — is arithmetic nonsense here, and this file is what proves it.

Measured over the documents that resolve three or more of A/B/C/DRB1/DQB1, the
chance two unrelated documents carry the same first-field genotype at one locus:

    DQB1 1 in 10    C 1 in 40    DRB1 1 in 44    A 1 in 55    B 1 in 90

These are first fields from one country's donor and recipient pool, not alleles.
10,032 documents make 50.3 million pairs, so **any per-pair match probability
above 2e-8 yields an expected false merge**. "Identical on three loci" reaches
only 1 in 22,000 to 1 in 218,000 for the triples that actually occur — hundreds
to thousands of coincidental pairs corpus-wide. Merging on that fabricates
people, and a fabricated person in a transplant database is a person who gets
matched to a stranger's kidney.

So a fingerprint link is *scored* against this table, and the score only ever
proposes. Auto-linking needs a non-HLA identifier as well.

Writes `config/locus_genotype_frequencies.json`, committed and versioned: every
threshold in `kidneymatch.domain.entity_resolution` is stated in terms of it, so
it must be regenerated deliberately whenever extraction changes.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SCHEMA_NAME = "locus-genotype-frequencies/v1"
DEFAULT_OUT = ROOT / "config/locus_genotype_frequencies.json"
LOCI = ("A", "B", "C", "DRB1", "DQB1")
MIN_DOCUMENTS = 500


def measure(facts_db: Path) -> dict:
    con = sqlite3.connect(facts_db)
    rows = con.execute(
        "SELECT sha256, field, value FROM fact WHERE status='RESOLVED' "
        f"AND field IN ({','.join('?' * len(LOCI))})",
        LOCI,
    ).fetchall()
    con.close()

    per_document: dict[str, dict[str, str]] = defaultdict(dict)
    for sha256, field, value in rows:
        # The genotype, order-independent: which allele the form printed first
        # is not a fact about the patient.
        per_document[sha256][field] = " ".join(
            sorted(part.split("*")[-1] for part in (value or "").split() if part)
        )

    out: dict[str, dict[str, float | int]] = {}
    for locus in LOCI:
        counts = Counter(d[locus] for d in per_document.values() if locus in d)
        total = sum(counts.values())
        if total < MIN_DOCUMENTS:
            continue
        match_probability = sum((n / total) ** 2 for n in counts.values())
        out[locus] = {
            "documents": total,
            "distinct_genotypes": len(counts),
            "match_probability": round(match_probability, 6),
            "one_in": round(1 / match_probability) if match_probability else 0,
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    if not args.facts.exists():
        print(f"missing {args.facts}; run scripts/extract_facts.py first")
        return 2

    loci = measure(args.facts)
    payload = {
        "schema": SCHEMA_NAME,
        "min_documents": MIN_DOCUMENTS,
        "measured_utc": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        "loci": loci,
    }
    args.out.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")

    print(f"wrote {args.out}\n")
    print(f"{'locus':<8}{'documents':>11}{'genotypes':>11}{'two random docs match':>24}")
    for locus, stats in sorted(
        loci.items(), key=lambda kv: kv[1]["match_probability"], reverse=True
    ):
        print(
            f"{locus:<8}{stats['documents']:>11,}{stats['distinct_genotypes']:>11,}"
            f"{'1 in ' + format(stats['one_in'], ','):>24}"
        )
    print("\nThese are first fields from one country's pool. They identify a genotype,")
    print("not a person: `ENTITY-001` scores a link with them and never auto-merges on them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
