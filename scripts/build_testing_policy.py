#!/usr/bin/env python3
"""Measure which loci a form family actually reports, and commit the answer.

`HA-009`. These laboratories print a row for DPA1 and DPB1 and leave the cell
empty (KI-013). Every one of those cells currently lands in the review queue,
which is on the order of 24,000 items that no reviewer can do anything about:
the laboratory did not perform the test.

## The statistic this uses, and the one it does not

The obvious measure — how often the cell is empty — is the wrong one, because a
cell can be empty through a reading failure as easily as through an absent test.
Measured, no family and locus reaches 95% emptiness, so a rule written on it
fires on nothing.

The right measure is how often an anchored cell **ever resolves to a value**:

    DPA1  0.0-0.4%      DPB1  0.0-0.5%      DQA1  3.9-11.9%
    C    11.7-28.3%     DRB1 37.1-82.9%

DPA1 and DPB1 are qualitatively different from the rest. Across 25,000 anchored
cells of those two loci, 44 carry a value. DQA1 and C plainly are tested
sometimes and must keep going to review.

So the policy is: **a family and locus whose anchored cells resolve less than
`MAX_RESOLVE_RATE` of the time is not tested by that laboratory.** It applies
ONLY to a cell the resolver found empty; a cell that did resolve keeps its
value, which is why measuring this and then applying it does not move the
measurement.

Writes `config/locus_testing_rates.json`, which is committed and versioned:
the thresholds downstream are stated in terms of it, so it must be regenerated
deliberately and reviewed, never inferred at runtime.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SCHEMA_NAME = "locus-testing-rates/v1"
DEFAULT_OUT = ROOT / "config/locus_testing_rates.json"

LOCI = ("A", "B", "C", "DRB1", "DQA1", "DQB1", "DPA1", "DPB1")

# A family and locus below this resolve rate is treated as not tested. Chosen
# from the measured distribution, which is bimodal: DPA1/DPB1 sit at 0.0-0.5%
# and the next locus up, DQA1, sits at 3.9%. Anywhere in between separates the
# same two groups; 1% is stated because it is the round number inside the gap.
MAX_RESOLVE_RATE = 0.01

# Below this many anchored cells a rate means nothing.
MIN_ANCHORED = 200


def measure(facts_db: Path) -> dict:
    con = sqlite3.connect(facts_db)
    rows = con.execute(
        "SELECT coalesce(d.family, ''), f.field, count(*), "
        "sum(CASE WHEN f.status='RESOLVED' THEN 1 ELSE 0 END), "
        "sum(CASE WHEN f.reason LIKE 'anchor found but no box%' THEN 1 ELSE 0 END) "
        "FROM fact f JOIN document d ON d.sha256 = f.sha256 "
        f"WHERE f.field IN ({','.join('?' * len(LOCI))}) AND f.status != 'UNKNOWN' "
        "GROUP BY 1, 2 ORDER BY 1, 2",
        LOCI,
    ).fetchall()
    con.close()

    families: dict[str, dict[str, dict[str, float | int | bool]]] = {}
    for family, locus, anchored, resolved, empty in rows:
        rate = resolved / anchored if anchored else 0.0
        families.setdefault(family, {})[locus] = {
            "anchored": anchored,
            "resolved": resolved,
            "empty": empty,
            "resolve_rate": round(rate, 5),
            "not_tested": bool(anchored >= MIN_ANCHORED and rate < MAX_RESOLVE_RATE),
        }
    return families


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    if not args.facts.exists():
        print(f"missing {args.facts}; run scripts/extract_facts.py first")
        return 2

    families = measure(args.facts)
    payload = {
        "schema": SCHEMA_NAME,
        "max_resolve_rate": MAX_RESOLVE_RATE,
        "min_anchored": MIN_ANCHORED,
        "measured_utc": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        "families": families,
    }
    args.out.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")

    not_tested = [
        (family or "(no family)", locus)
        for family, loci in sorted(families.items())
        for locus, stats in sorted(loci.items())
        if stats["not_tested"]
    ]
    covered = sum(
        int(stats["empty"])
        for loci in families.values()
        for stats in loci.values()
        if stats["not_tested"]
    )
    print(f"wrote {args.out}")
    print(f"family/locus pairs measured : {sum(len(v) for v in families.values()):>6}")
    print(f"pairs judged NOT TESTED     : {len(not_tested):>6}")
    for family, locus in not_tested:
        stats = families[family if family != "(no family)" else ""][locus]
        print(
            f"    {family:<12}{locus:<6}{stats['resolved']:>5} of {stats['anchored']:>6,} resolve"
        )
    print(f"empty cells this removes from review: {covered:,}")
    print("\nA cell that DID resolve keeps its value; only empty cells are reclassified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
