#!/usr/bin/env python3
"""Threshold gate for mutation testing.

P2-3 of the harness readiness review. `TEST_PLAN.md` requires mutation testing
for the matching/authorization/consent core, and mutation score is the only
metric that answers "do these tests catch bugs, or do they merely execute code".

mutmut 3.7.0 has no threshold flag: `mutmut run` exits 0 even when mutants
survive (upstream issue #442). Without this gate a CI job would run the whole
mutation suite and then pass regardless of the result, which is the same class
of silent-success failure as a verification script that skips its own steps.

    mutmut run
    mutmut export-cicd-stats
    python scripts/mutation_gate.py --min-score 80

NOTE: mutmut calls os.fork() and therefore does NOT run on Windows. Use WSL
locally; CI runs on ubuntu. This is why the gate is a separate target and not
part of `verify_repo.py`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATS = ROOT / "mutants/mutmut-cicd-stats.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--min-score",
        type=float,
        default=80.0,
        help="Minimum percentage of mutants killed (default: 80).",
    )
    parser.add_argument("--stats", type=Path, default=STATS)
    args = parser.parse_args()

    if not args.stats.is_file():
        print(f"mutation_gate: FAIL - {args.stats} not found.")
        print("Run `mutmut run` then `mutmut export-cicd-stats` first.")
        print("A missing report is a failure, not a pass.")
        return 2

    stats = json.loads(args.stats.read_text(encoding="utf-8"))
    killed = int(stats.get("killed", 0))
    survived = int(stats.get("survived", 0))
    timeout = int(stats.get("timeout", 0))
    suspicious = int(stats.get("suspicious", 0))
    no_tests = int(stats.get("no_tests", 0))

    # A mutant with no test covering it is NOT a pass. Counting only
    # killed/(killed+survived) would let uncovered code inflate the score.
    considered = killed + survived + timeout + suspicious + no_tests
    if considered == 0:
        print("mutation_gate: FAIL - no mutants were evaluated.")
        return 2

    score = 100.0 * killed / considered
    print(
        f"mutation score: {score:.1f}%  "
        f"(killed={killed} survived={survived} no_tests={no_tests} "
        f"timeout={timeout} suspicious={suspicious})"
    )

    if survived:
        print(f"\n{survived} mutant(s) survived. Inspect with: mutmut browse")
    if no_tests:
        print(f"{no_tests} mutant(s) had no covering test at all.")

    if score < args.min_score:
        print(f"\nmutation_gate: FAIL ({score:.1f}% < {args.min_score}%)")
        return 1

    print(f"\nmutation_gate: PASS ({score:.1f}% >= {args.min_score}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
