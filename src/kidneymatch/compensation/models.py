from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CompensationRequest:
    donor_id: str
    amount_rial: int

    def __post_init__(self) -> None:
        if self.amount_rial < 0:
            raise ValueError("amount_rial must be non-negative")

    @property
    def amount_toman(self) -> int:
        return self.amount_rial // 10
