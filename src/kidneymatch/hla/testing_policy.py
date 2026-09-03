"""Which loci a form family's laboratory actually reports.

`HA-009`. These forms print a DPA1 and DPB1 row and leave the cell empty
(KI-013). Every such cell reaches the review queue as "anchor found but no box
at all", which is roughly 24,000 items a reviewer can do nothing with: the
laboratory did not perform the test, and no amount of looking will make a value
appear.

## Why this is measured and committed rather than computed

The rule turns a review item into a finding — `NOT_TESTED` — and a finding is
published. If the threshold moved at runtime, records already published could
change meaning without anyone regenerating a file and reading the diff. So
`scripts/build_testing_policy.py` measures the corpus, writes
`config/locus_testing_rates.json`, and that file is committed and reviewed. This
module reads the stored verdict and does not second-guess it.

## What the verdict rests on

Not how often the cell is empty — a cell can be empty because the reading
failed. It rests on how often an anchored cell **ever resolves to a value**,
which separates the corpus cleanly:

    DPA1  0.0-0.4%      DPB1  0.0-0.5%   |   DQA1  3.9-11.9%   C  11.7-28.3%

DPA1 and DPB1 are on one side of that gap and every other locus on the other.

The rule can only reclassify a cell the resolver already found **empty**. A cell
that resolved keeps its value, which is also why applying the policy does not
move the measurement that produced it.

For matching, `NOT_TESTED` is not a mismatch and not a zero: it is UNKNOWN with
a reason, and `MATCH-HLA-001` must treat DP as structurally absent for
historical records (KI-013).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_NAME = "locus-testing-rates/v1"
DEFAULT_PATH = Path(__file__).resolve().parents[3] / "config/locus_testing_rates.json"


class LocusTestingUnavailable(RuntimeError):
    """The measured policy is missing or unreadable.

    Deliberately fatal. Degrading to "nothing is untested" would silently
    restore 24,663 review items; degrading the other way would erase values a
    laboratory did report. Neither belongs in a default.
    """


@dataclass(frozen=True, slots=True)
class LocusTestingPolicy:
    """The committed measurement, read back."""

    max_resolve_rate: float
    min_anchored: int
    measured_utc: str
    _families: dict[str, dict[str, dict[str, Any]]]

    def _stats(self, family: str | None, locus: str) -> dict[str, Any] | None:
        return self._families.get(family or "", {}).get(locus)

    def is_not_tested(self, family: str | None, locus: str) -> bool:
        """Does this family's laboratory leave this locus untested?

        A family nobody measured gets `False`, which routes the cell to review:
        the safe answer, and the one that cannot lose a value.
        """
        stats = self._stats(family, locus)
        return bool(stats and stats.get("not_tested"))

    def resolve_rate(self, family: str | None, locus: str) -> float | None:
        stats = self._stats(family, locus)
        return None if stats is None else float(stats["resolve_rate"])

    def anchored(self, family: str | None, locus: str) -> int:
        stats = self._stats(family, locus)
        return 0 if stats is None else int(stats["anchored"])

    def not_tested_pairs(self) -> list[tuple[str, str]]:
        return sorted(
            (family, locus)
            for family, loci in self._families.items()
            for locus, stats in loci.items()
            if stats.get("not_tested")
        )

    def reason(self, family: str | None, locus: str) -> str:
        """Provenance for the record: why this cell was not sent to review."""
        stats = self._stats(family, locus)
        if stats is None:
            return "no measured testing rate for this family"
        return (
            f"this form family reports {locus} on {stats['resolved']} of "
            f"{stats['anchored']} anchored cells ({float(stats['resolve_rate']):.2%}); "
            f"the laboratory does not perform this test"
        )


def load_testing_policy(path: Path | None = None) -> LocusTestingPolicy:
    source = path or DEFAULT_PATH
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except OSError as error:
        raise LocusTestingUnavailable(
            f"{source} is missing; run scripts/build_testing_policy.py"
        ) from error
    except json.JSONDecodeError as error:
        raise LocusTestingUnavailable(f"{source} is not readable JSON") from error

    if payload.get("schema") != SCHEMA_NAME:
        raise LocusTestingUnavailable(
            f"{source} has schema {payload.get('schema')!r}, expected {SCHEMA_NAME!r}"
        )
    return LocusTestingPolicy(
        max_resolve_rate=float(payload.get("max_resolve_rate", 0.01)),
        min_anchored=int(payload.get("min_anchored", 200)),
        measured_utc=str(payload.get("measured_utc", "")),
        _families=payload.get("families", {}),
    )
