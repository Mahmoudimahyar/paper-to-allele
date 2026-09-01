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
