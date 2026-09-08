"""The versioned policy, loaded from disk rather than written into the code.

`MATCH-001`. Policy document: `docs/clinical/MATCHING_POLICY_V2.md`.

The coefficients are a project engineering policy, not a universal clinical
standard, and HA-004 has not confirmed them. Keeping them in
`config/matching_policy_ir_v2.json` rather than in the source has three
consequences that matter: a MatchRun can record exactly which numbers produced
it, an immunologist can be shown one file, and adopting the policy is a change
to `status` rather than a code change.

`is_adopted` is False while `status` is `DESIGN_NOT_ADOPTED`. Callers that
present results to a person are expected to check it and say so.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

__all__ = ["MatchingPolicy", "load_policy", "policy_path"]

_DEFAULT = Path(__file__).resolve().parents[3] / "config" / "matching_policy_ir_v2.json"


def policy_path() -> Path:
    return _DEFAULT


@dataclass(frozen=True, slots=True)
class MatchingPolicy:
    """Everything the ranking is allowed to depend on, and nothing else."""

    policy_id: str
    status: str
    first_mismatch: dict[str, int]
    second_mismatch: dict[str, int]
    gate_full: int
    gate_halved: int
    scored_loci: tuple[str, ...]
    sort_tuple: tuple[str, ...]
    buckets_in_order: tuple[str, ...]
    imgt_version: str
    pyard_version: str
    source_doc: str

    @property
    def is_adopted(self) -> bool:
        """True only when a human has adopted the policy after HA-004."""
        return self.status == "ADOPTED"

    def charge(self, locus: str, mismatches: int, *, dr_matched: bool) -> int:
        """The tie-breaker charge for one locus, in integer tenths-scaled points.

        The gate halves every locus except DRB1 once DR is mismatched. The
        halving is exact for these coefficients: every gated per-locus charge is
        a multiple of two after scaling, which a test asserts rather than
        assumes.
        """
        if mismatches <= 0:
            return 0
        first = self.first_mismatch.get(locus, 0)
        second = self.second_mismatch.get(locus, 0) if mismatches >= 2 else 0
        terms = first + second
        gate = self.gate_full if locus == "DRB1" or dr_matched else self.gate_halved
        scaled = gate * terms
        if scaled % 10:  # pragma: no cover - guarded by a test
            raise ValueError(
                f"policy {self.policy_id}: charge for {locus} at {mismatches} mismatches "
                f"is not exact under integer arithmetic ({gate} x {terms})"
            )
        return scaled // 10


def _require(data: dict[str, Any], *path: str) -> Any:
    node: Any = data
    for key in path:
        if not isinstance(node, dict) or key not in node:
            raise ValueError(f"matching policy is missing {'.'.join(path)}")
        node = node[key]
    return node


@lru_cache(maxsize=4)
def load_policy(path: Path | None = None) -> MatchingPolicy:
    """Read and validate the policy file.

    Raises rather than falling back to a default: a ranking produced under an
    unknown policy could not be reproduced or explained, which the MATCH-001
    invariants forbid.
    """
    target = path or _DEFAULT
    data = json.loads(target.read_text(encoding="utf-8"))

    tiebreaker = _require(data, "tiebreaker")
    first = {str(k): int(v) for k, v in _require(tiebreaker, "first_mismatch").items()}
    second = {str(k): int(v) for k, v in _require(tiebreaker, "second_mismatch").items()}
    gate = _require(tiebreaker, "gate")

    policy = MatchingPolicy(
        policy_id=str(_require(data, "policy_id")),
        status=str(_require(data, "status")),
        first_mismatch=first,
        second_mismatch=second,
        gate_full=int(gate["DRB1"]),
        gate_halved=int(gate["other_when_DRB1_mismatched"]),
        scored_loci=tuple(_require(data, "loci", "ranked")),
        sort_tuple=tuple(_require(data, "sort_tuple")),
        buckets_in_order=tuple(_require(data, "buckets_in_order")),
        imgt_version=str(_require(data, "reproducibility", "imgt_version")),
        pyard_version=str(_require(data, "reproducibility", "pyard_version")),
        source_doc=str(data.get("source_doc", "")),
    )

    if int(gate["other_when_DRB1_matched"]) != policy.gate_full:
        raise ValueError("policy: an unmismatched DRB1 must not attenuate the other loci")
    for locus in policy.scored_loci:
        if locus not in policy.first_mismatch:
            raise ValueError(f"policy: scored locus {locus} has no first-mismatch charge")
    return policy
