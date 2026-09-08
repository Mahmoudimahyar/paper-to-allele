"""KM levels, the sort tuple and the admin-only tie-breaker.

`MATCH-001`. Policy: `docs/clinical/MATCHING_POLICY_V2.md` section 6.

The algorithm is the UK Kidney Allocation Scheme mismatch levels, re-cut on the
HLA-DR gate and extended with HLA-DQ. A level scheme rather than a point total,
because the measured shape is a step: in the cleanest test, antigen mismatch
above zero separated the cohort while the non-zero groups did not differ from
one another at all.

The re-cut exists because UK level 2 admits one DR mismatch with no B mismatch,
ranking it above zero DR with two B. In 39,205 Eurotransplant transplants a
single DR incompatibility abolished the class I matching benefit, so the levels
are cut so that every DR-matched pair outranks every DR-mismatched pair.

Nothing here is a percentage and nothing here is shown to an end user. The
tie-breaker is an ordering device, and the output of the module is an order.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .mismatch import MismatchStatus, MismatchVector
from .policy import MatchingPolicy

__all__ = [
    "KM_LEVEL_NAMES",
    "LevelOutcome",
    "SortKey",
    "km_level",
    "sort_key",
    "tiebreaker_penalty",
]

KM_LEVEL_NAMES: dict[int, str] = {
    1: "KM-1 full match at A, B and DRB1",
    2: "KM-2 DRB1 matched, at most one B mismatch",
    3: "KM-3 DRB1 matched, two B mismatches",
    4: "KM-4 one DRB1 mismatch, at most one B mismatch",
    5: "KM-5 one DRB1 mismatch, two B mismatches",
    6: "KM-6 two DRB1 mismatches, at most one B mismatch",
    7: "KM-7 two DRB1 mismatches, two B mismatches",
}

#: Returned when DRB1 or B is not usable on both sides. A pair without a level
#: does not belong in the ranked bucket at all; the gate layer routes it to
#: INSUFFICIENT_HLA. The sentinel sorts after every real level so that a bug in
#: the gate layer degrades to "ranked last", never to "ranked first".
NO_LEVEL = 99


@dataclass(frozen=True, slots=True)
class LevelOutcome:
    """A level, plus what it would have been had the unknowns gone the other way."""

    level: int
    best_case: int
    worst_case: int
    km_1_unreachable: str = ""
    reason: str = ""

    @property
    def is_ranked(self) -> bool:
        return self.level != NO_LEVEL


def _conservative(vector: MismatchVector, locus: str) -> int | None:
    """The worse end of a locus count, or None when it is unknown.

    A range decides a level at its worse end. Flattering a pair beyond what the
    data supports is the one direction of error this system must not make.
    """
    mm = vector.per_locus.get(locus)
    if mm is None or mm.status is MismatchStatus.UNKNOWN:
        return None
    return mm.upper


def _optimistic(vector: MismatchVector, locus: str) -> int | None:
    mm = vector.per_locus.get(locus)
    if mm is None or mm.status is MismatchStatus.UNKNOWN:
        return None
    return mm.lower


def _level_from(dr: int, b: int, a: int | None) -> int:
    """The KM level for known DR and B counts.

    `a` is None when HLA-A is unknown, which makes KM-1 unreachable: KM-1 is the
    claim that all three classic loci are matched, and that claim cannot be made
    from missing data.
    """
    if dr == 0:
        if b == 0 and a == 0:
            return 1
        return 2 if b <= 1 else 3
    if dr == 1:
        return 4 if b <= 1 else 5
    return 6 if b <= 1 else 7


def km_level(vector: MismatchVector) -> LevelOutcome:
    """Assign the KM level, conservatively, and report the optimistic case too."""
    dr = _conservative(vector, "DRB1")
    b = _conservative(vector, "B")
    if dr is None or b is None:
        missing = [name for name, v in (("DRB1", dr), ("B", b)) if v is None]
        return LevelOutcome(
            NO_LEVEL,
            NO_LEVEL,
            NO_LEVEL,
            reason=f"no level: {' and '.join(missing)} unknown on at least one side",
        )

    a = _conservative(vector, "A")
    level = _level_from(dr, b, a)

    best = _level_from(
        _optimistic(vector, "DRB1") or 0,
        _optimistic(vector, "B") or 0,
        _optimistic(vector, "A"),
    )
    unreachable = ""
    if level != 1 and dr == 0 and b == 0:
        # Reaching here, HLA-A is the only thing that can have cost KM-1: with
        # DRB1 and B both matched, a matched A would have produced level 1. So A
        # is unknown or non-zero, and the `else` is total rather than a fallback
        # for a case that cannot arise.
        unreachable = "HLA-A unknown" if a is None else f"{a} HLA-A mismatch(es)"
    return LevelOutcome(level, best, level, km_1_unreachable=unreachable)


#: What an unknown locus is charged: the worst it could be.
UNKNOWN_AS = 2


def tiebreaker_penalty(vector: MismatchVector, policy: MatchingPolicy) -> int:
    """The admin-only numeric tie-breaker. Integers only; never displayed.

    An UNKNOWN locus is charged at its WORST CASE, as if fully mismatched.

    An earlier version charged nothing for absence, which let deleting a
    mismatched typing improve a candidate's rank: the penalty sits at tuple
    position 3 and the unknown count at position 5, so a lexicographic
    comparison decides on the vanished penalty long before it reads the extra
    unknown. No later position can offset an earlier one. Charging the worst
    case fixes it at the source and is the same conservative rule the policy
    already applies to a partially typed locus: missing is never cheaper than
    known-bad, so losing information can never help.
    """
    dr = _conservative(vector, "DRB1")
    # An unknown DRB1 is not a matched DRB1. The gate stays closed.
    dr_matched = dr == 0
    total = 0
    for locus in policy.scored_loci:
        count = _conservative(vector, locus)
        if count is None:
            count = UNKNOWN_AS
        total += policy.charge(locus, count, dr_matched=dr_matched)
    # A DRB3/4/5 gene is charged when it conflicts AND when its presence was
    # never established, for the same reason: deleting the typing must not be
    # cheaper than the conflict it removed.
    charge = policy.first_mismatch.get("DRB3_4_5_presence_conflict", 0)
    gate = policy.gate_full if dr_matched else policy.gate_halved
    chargeable = sum(1 for p in vector.presence if p.conflict or p.status is MismatchStatus.UNKNOWN)
    total += (gate * charge * chargeable) // 10
    return total


@dataclass(frozen=True, slots=True)
class SortKey:
    """The ordering, and the only thing the explanation is generated from."""

    bucket_rank: int
    km_level: int
    dq_binary: int
    penalty: int
    evidence_penalty: int
    unknown_count: int
    partial_count: int
    stable_hash: str

    def as_tuple(self) -> tuple[int, int, int, int, int, int, int, str]:
        return (
            self.bucket_rank,
            self.km_level,
            self.dq_binary,
            self.penalty,
            self.evidence_penalty,
            self.unknown_count,
            self.partial_count,
            self.stable_hash,
        )


def _dq_binary(vector: MismatchVector) -> int:
    """Zero DQB1 mismatch, or anything else.

    Binary because no separation was found among non-zero groups at antigen
    level, because the one-field DQ call is the least reliable of the five loci,
    and because DQB1 carries only 30 distinct genotypes in this archive against
    DRB1's 113, so a chance zero is about four and a half times more likely.
    UNKNOWN sorts with the non-zero group: it is not evidence of a match.
    """
    mm = vector.per_locus.get("DQB1")
    if mm is None or mm.status is MismatchStatus.UNKNOWN:
        return 1
    return 0 if mm.upper == 0 else 1


def stable_hash(policy_id: str, left_id: str, right_id: str) -> str:
    """A deterministic final tiebreak over the ordered pair.

    Never price and never anything correlated with it. Ties are common: 1,974
    profiles share a genotype with another profile, so without a stable last
    position the order would depend on dictionary iteration.
    """
    payload = f"{policy_id}|{left_id}|{right_id}".encode()
    return hashlib.sha256(payload).hexdigest()


def sort_key(
    *,
    bucket_rank: int,
    vector: MismatchVector,
    policy: MatchingPolicy,
    evidence_penalty: int,
    anchor_id: str,
    candidate_id: str,
) -> SortKey:
    """Build the full sort key for one pair, in one place.

    The explanation is generated from this object, so a field that does not
    appear here cannot influence the order, and an order cannot be produced that
    the explanation fails to account for.
    """
    level = km_level(vector)
    return SortKey(
        bucket_rank=bucket_rank,
        km_level=level.level,
        dq_binary=_dq_binary(vector),
        penalty=tiebreaker_penalty(vector, policy),
        evidence_penalty=evidence_penalty,
        unknown_count=len(vector.unknown_loci()),
        partial_count=len(vector.partial_loci()),
        stable_hash=stable_hash(policy.policy_id, anchor_id, candidate_id),
    )
