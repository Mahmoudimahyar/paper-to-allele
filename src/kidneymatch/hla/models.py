from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum


class HLALocus(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    DRB1 = "DRB1"
    DRB3 = "DRB3"
    DRB4 = "DRB4"
    DRB5 = "DRB5"
    DQA1 = "DQA1"
    DQB1 = "DQB1"
    DPA1 = "DPA1"
    DPB1 = "DPB1"


@dataclass(frozen=True, slots=True)
class ReportedHLAValue:
    locus: HLALocus
    raw_value: str
    normalized_value: str | None
    is_low_resolution: bool
    requires_review: bool
