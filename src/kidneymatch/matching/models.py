"""The V1 result skeleton. Superseded, retained, and not to be imported.

`PairStage` and `MatchResult` were the shape sketched in
`docs/architecture/DATA_MODEL.md` before MATCH-001 was designed. The V2 design
does not use them: a pair's outcome is a `gates.Bucket` with a
`gates.BucketDecision`, and a row is a `core.RankedPair` carrying a
`ranking.SortKey`. The two models disagree on the thing that matters, which is
why this file is inert rather than adapted. `PairStage` is a LINEAR pipeline in
which a pair advances through stages, so a pair that is simultaneously
under-typed and crossmatch-blocked has one position on that line. `Bucket` is
not a line: assignment runs blocking conditions first and reports every blocking
reason that applied, precisely so an informational state cannot hide a blocking
one.

Nothing imports this module and nothing should. It is kept only so that a reader
arriving from the architecture document finds the disagreement written down
rather than finding a file that quietly vanished. Deleting it, and amending that
document, is a human decision this task did not take.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PairStage(StrEnum):
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    ABO_ROUTE_DETERMINED = "ABO_ROUTE_DETERMINED"
    HLA_REVIEWED = "HLA_REVIEWED"
    DSA_REVIEWED = "DSA_REVIEWED"
    VIRTUAL_CROSSMATCH_ACCEPTABLE = "VIRTUAL_CROSSMATCH_ACCEPTABLE"
    PHYSICAL_CROSSMATCH_NEGATIVE = "PHYSICAL_CROSSMATCH_NEGATIVE"
    CENTER_ACCEPTED = "CENTER_ACCEPTED"


@dataclass(frozen=True, slots=True)
class MatchResult:
    policy_version: str
    stage: PairStage
    blockers: tuple[str, ...]
    unknowns: tuple[str, ...]
    explanation: tuple[str, ...]
