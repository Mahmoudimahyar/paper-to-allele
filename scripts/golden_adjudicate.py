#!/usr/bin/env python3
"""Build the adjudication queue from two independent labellings.

A mismatch between two labellers is a question for a **third person against the
image**, never for the two of them to settle between themselves: measured, when
double-entry participants reconcile their own disagreements they make the
entries match, sometimes by introducing new errors (Barchard 2020).

This writes the disputed cells to a queue the third person works through, and
that person's answers become `adjudicated.json`, which `golden_score.py` treats
as ground truth.

Usage:
    uv run --frozen --extra hist python scripts/golden_adjudicate.py \\
        --labels data/review/golden/labels_a.json data/review/golden/labels_b.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kidneymatch.review.golden import adjudicate  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, nargs=2, required=True)
    parser.add_argument("--tasks", type=Path, default=ROOT / "data/review/golden/tasks.json")
    parser.add_argument("--out", type=Path, default=ROOT / "data/review/golden/disputes.json")
    args = parser.parse_args()

    from golden_score import read_labels  # noqa: PLC0415 - sibling script, not a package

    for path in (*args.labels, args.tasks):
        if not path.exists():
            print(f"missing {path}")
            return 2

    first, second = (read_labels(path) for path in args.labels)
    result = adjudicate(first, second)
    tasks = {
        task["cell_id"]: task
        for task in json.loads(args.tasks.read_text(encoding="utf-8"))["tasks"]
    }

    def describe(label) -> dict | None:
        if label is None:
            return None
        return {
            "annotator": label.annotator,
            "state": label.state.value,
            "alleles": list(label.alleles),
            "unsure": label.unsure,
        }

    disputes = [
        {
            "cell_id": cell_id,
            "locus": tasks.get(cell_id, {}).get("locus"),
            "crops": tasks.get(cell_id, {}).get("crops"),
            "readings": [describe(a), describe(b)],
        }
        for cell_id, (a, b) in sorted(result.disputed.items())
    ]

    kinds: Counter[str] = Counter()
    for a, b in result.disputed.values():
        if a is None or b is None:
            kinds["only one labeller reached it"] += 1
        elif a.state is not b.state:
            kinds[f"{a.state.value} vs {b.state.value}"] += 1
        else:
            kinds["same state, different alleles"] += 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "schema": "golden-disputes/v1",
                "note": (
                    "Answered by a THIRD person against the image. The two "
                    "labellers must not reconcile these between themselves."
                ),
                "n_disputes": len(disputes),
                "disputes": disputes,
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    total = len(result.agreed) + len(result.disputed)
    print(f"cells labelled by both : {total:,}")
    print(
        f"  agreed               : {len(result.agreed):,}"
        f"  ({len(result.agreed) / max(total, 1):.1%})"
    )
    print(f"  to adjudicate        : {len(result.disputed):,}")
    for kind, count in kinds.most_common():
        print(f"      {kind:<40}{count:>6,}")
    print(f"\nwritten to {args.out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
