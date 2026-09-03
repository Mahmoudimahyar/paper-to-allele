#!/usr/bin/env python3
"""Order the review queue by what a decision actually buys.

`REVIEW-001`. After HA-009 removed the ~24,000 cells nobody could act on, what
remains is still far more than anyone will read, so the order matters more than
the count. Reviewing by "reason" — all the two-anchor cases, then all the
too-many-candidates cases — spends a person on whatever the resolver happened to
fail at most often. Reviewing by VALUE spends them on the records that become
usable.

## The ordering, and why each tier is where it is

1. **Completes a matchable record.** A document that already has a role and
   four or more other loci needs one more cell to become a record matching can
   use. Nothing else converts a person's minute into as much.
2. **A two-way choice.** The constrained decode split between exactly two
   readings under one-pixel jitter, and the page shows both: this is a click,
   not a transcription.
3. **The two readers disagree.** The pipeline and an independent recognizer
   read different digits. One of them is wrong and a person settles it.
4. **Boxes on the row the resolver refused to bind.** "N candidates exceeds
   max_values" and "2 anchors found" — the reader can see the row and type.
5. **Everything else**, newest first.

A cell already labelled in a review pack is excluded, so two people do not
spend their afternoons on the same rows.

## What this is not

It is not a claim about which cells are WRONG. That ordering can only be
calibrated once the review pack (HA-008) says which signals actually predict
errors; until then this is an argument from value, stated so it can be checked
and replaced. Nothing here resolves a cell or changes a fact.

Prints counts only; the queue file is PHI and belongs under `data/review/`.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

QUEUE_SCHEMA = "hla-review-queue/v1"
HLA_LOCI = ("A", "B", "C", "DRB1", "DQA1", "DQB1", "DPA1", "DPB1")

# Tier 1's threshold: a document with a role and four other resolved loci is one
# cell short of a record `MATCH-HLA-001` can use.
COMPLETES_ROLE_REQUIRED = True
COMPLETES_MIN_OTHER_LOCI = 4


@dataclass(frozen=True, slots=True)
class QueueItem:
    cell_id: str
    sha256: str
    locus: str
    status: str
    tier: int
    tier_name: str
    why: str
    reason: str | None


TIERS = {
    1: "completes a matchable record",
    2: "an unstable reading, shown as a choice",
    3: "the two readers disagree on an accepted value",
    4: "boxes on the row, refused",
    5: "everything else",
}


def build(facts_db: Path, labelled: set[str]) -> list[QueueItem]:
    con = sqlite3.connect(facts_db)

    resolved_loci: Counter[str] = Counter()
    for (sha256,) in con.execute(
        "SELECT sha256 FROM fact WHERE status='RESOLVED' "
        f"AND field IN ({','.join('?' * len(HLA_LOCI))})",
        HLA_LOCI,
    ):
        resolved_loci[sha256] += 1
    with_role = {
        sha256
        for (sha256,) in con.execute(
            "SELECT sha256 FROM fact WHERE field='ROLE' AND status='RESOLVED'"
        )
    }

    # Which cells have a two-way split, and which have a reader disagreement.
    split_readings = {
        (sha256, field): jitter
        for sha256, field, jitter in con.execute(
            "SELECT sha256, field, jitter_readings FROM decode WHERE verdict='SPLIT'"
        )
    }
    contradicted = {
        (sha256, field)
        for sha256, field in con.execute(
            "SELECT sha256, field FROM confirmation WHERE verdict='CONTRADICTED'"
        )
    }

    # Two kinds of item, and both are review work: a cell the resolver REFUSED
    # (nothing was read), and a cell it RESOLVED that a second reader disputes
    # or the decode could not read stably. Queueing only the first would leave
    # the disputed values — the ones that are wrong in the database right now —
    # entirely unreviewed.
    items: list[QueueItem] = []
    for sha256, field, reason, status in con.execute(
        "SELECT sha256, field, reason, status FROM fact "
        "WHERE (status='REVIEW_REQUIRED' OR (status='RESOLVED' AND stability IN "
        "('SPLIT','DIGITS_LOST','ILLEGIBLE'))) "
        f"AND field IN ({','.join('?' * len(HLA_LOCI))}) ORDER BY sha256, field",
        HLA_LOCI,
    ):
        cell_id = f"{sha256[:16]}:{field}"
        if cell_id in labelled:
            continue
        others = resolved_loci.get(sha256, 0)
        has_role = sha256 in with_role

        if (sha256, field) in contradicted:
            # An accepted value a second reader disputes. One of them is wrong,
            # and it is in the database either way.
            tier, why = 3, "an independent reader read different digits"
        elif status == "RESOLVED":
            tier, why = 2, "the accepted value was not stable under one-pixel jitter"
        elif (not COMPLETES_ROLE_REQUIRED or has_role) and others >= COMPLETES_MIN_OTHER_LOCI:
            tier, why = 1, f"document has a role and {others} other resolved loci"
        elif (sha256, field) in split_readings and _two_way(split_readings[(sha256, field)]):
            tier, why = 2, "the decode split between exactly two readings"
        elif reason and (
            "candidate values exceeds" in reason or "cannot decide which row" in reason
        ):
            tier, why = 4, "boxes sit on the row and the resolver refused to bind them"
        else:
            tier, why = 5, "no stronger signal"
        items.append(QueueItem(cell_id, sha256, field, status, tier, TIERS[tier], why, reason))

    con.close()
    items.sort(key=lambda item: (item.tier, item.cell_id))
    return items


def _two_way(jitter_readings: str | None) -> bool:
    """Did the decode land on exactly two distinct readings?

    Three or more is not a choice a reader can be shown; it is a transcription.
    """
    if not jitter_readings:
        return False
    try:
        votes = json.loads(jitter_readings)
    except json.JSONDecodeError:
        return False
    distinct = {key.split(":", 1)[1] for key in votes if ":" in key}
    return len(distinct) == 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--out", type=Path, default=ROOT / "data/review/queue.json")
    parser.add_argument(
        "--exclude-labelled",
        type=Path,
        nargs="*",
        default=[],
        help="golden-labels/v1 files whose cells are already read",
    )
    args = parser.parse_args()
    if not args.facts.exists():
        print(f"missing {args.facts}; run scripts/extract_facts.py first")
        return 2

    labelled: set[str] = set()
    for path in args.exclude_labelled:
        if path.exists():
            labelled |= set(json.loads(path.read_text(encoding="utf-8")).get("cells", {}))

    items = build(args.facts, labelled)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "schema": QUEUE_SCHEMA,
                "n_items": len(items),
                "already_labelled": len(labelled),
                "items": [asdict(item) for item in items],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    by_tier = Counter(item.tier for item in items)
    print(
        f"review items queued: {len(items):,}   (excluded as already labelled: {len(labelled):,})"
    )
    for tier in sorted(TIERS):
        print(f"  tier {tier}  {TIERS[tier]:<38}{by_tier.get(tier, 0):>9,}")
    print(f"\nwritten to {args.out}")
    print("Order is an argument from value, not a claim about which cells are wrong.")
    print("Only the review pack (HA-008) can say which signals predict errors.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
