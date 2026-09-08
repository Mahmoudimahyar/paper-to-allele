"""The hard gates, as buckets, and why assignment is a two-pass affair.

`MATCH-ABO-001`, `MATCH-IMMUNE-001`. Policy: `docs/clinical/MATCHING_POLICY_V2.md`
section 5.

A blocked pair is not a low-ranked pair. The constitution gives `BLOCKED` a
status of its own, and a ranking that lists an incompatible donor at all invites
someone to act on it, so buckets are rendered as separate sections with their
own next action rather than concatenated into one list.

Assignment is two passes because a pair can satisfy several entry conditions at
once. Taking the first match in display order would let an informational bucket
hide a blocking one: a pair that is both under-typed and crossmatch-blocked
would show as merely under-typed. So every blocking condition is evaluated
first, and each blocking reason that applied is reported even though the pair
occupies one bucket.

The DSA and crossmatch gates are specified and currently inert: the archive
holds no antibody, panel-reactive antibody or crossmatch data at all. Every pair
is therefore `ANTIBODY_UNKNOWN`, and that status is carried explicitly rather
than omitted, because absence of antibody data is not evidence of absence of
antibody.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .abo import GROUPS, AboDecision, AboGate, AboProvenance, abo_gate
from .mismatch import MismatchStatus, MismatchVector

__all__ = [
    "Bucket",
    "BucketDecision",
    "CrossmatchState",
    "PairInputs",
    "assign_bucket",
]


class Bucket(StrEnum):
    """Where a pair lands. Declaration order is DISPLAY order, not precedence."""

    RANKED = "RANKED"
    PROVISIONAL_ABO = "PROVISIONAL_ABO"
    INSUFFICIENT_HLA = "INSUFFICIENT_HLA"
    INSUFFICIENT_ABO = "INSUFFICIENT_ABO"
    ABO_INCOMPATIBLE = "ABO_INCOMPATIBLE"
    BLOCKED_DSA_OR_LAB_REVIEW = "BLOCKED_DSA_OR_LAB_REVIEW"
    BLOCKED_POSITIVE_CROSSMATCH = "BLOCKED_POSITIVE_CROSSMATCH"
    EXCLUDED_NON_CLINICAL = "EXCLUDED_NON_CLINICAL"

    @property
    def rank(self) -> int:
        return _DISPLAY_ORDER.index(self)

    @property
    def is_ranked(self) -> bool:
        return self in (Bucket.RANKED, Bucket.PROVISIONAL_ABO)


_DISPLAY_ORDER: tuple[Bucket, ...] = (
    Bucket.RANKED,
    Bucket.PROVISIONAL_ABO,
    Bucket.INSUFFICIENT_HLA,
    Bucket.INSUFFICIENT_ABO,
    Bucket.ABO_INCOMPATIBLE,
    Bucket.BLOCKED_DSA_OR_LAB_REVIEW,
    Bucket.BLOCKED_POSITIVE_CROSSMATCH,
    Bucket.EXCLUDED_NON_CLINICAL,
)

#: Evaluated before anything informational, most severe first.
_BLOCKING_ORDER: tuple[Bucket, ...] = (
    Bucket.EXCLUDED_NON_CLINICAL,
    Bucket.BLOCKED_POSITIVE_CROSSMATCH,
    Bucket.BLOCKED_DSA_OR_LAB_REVIEW,
    Bucket.ABO_INCOMPATIBLE,
)


class CrossmatchState(StrEnum):
    NOT_PERFORMED = "NOT_PERFORMED"
    NEGATIVE = "NEGATIVE"
    POSITIVE = "POSITIVE"
    INDETERMINATE = "INDETERMINATE"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True, slots=True)
class PairInputs:
    """Everything the gates may see. Deliberately small.

    There is no field for compensation, for a direct identifier, for message
    text or for a preference claim. The gates cannot consider what they cannot
    be handed.
    """

    donor_group: str | None
    recipient_group: str | None
    donor_provenance: AboProvenance = AboProvenance.UNKNOWN
    recipient_provenance: AboProvenance = AboProvenance.UNKNOWN
    donor_eligible: bool = True
    recipient_eligible: bool = True
    ineligibility_reason: str = ""
    crossmatch: CrossmatchState = CrossmatchState.NOT_PERFORMED
    dsa_conflicts: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BucketDecision:
    """The bucket, every blocking reason that applied, and the ABO detail."""

    bucket: Bucket
    reasons: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    abo: AboDecision | None = None
    antibody_status: str = "ANTIBODY_UNKNOWN"
    next_action: str = ""
    extras: dict[str, str] = field(default_factory=dict)


_NEXT_ACTION: dict[Bucket, str] = {
    Bucket.RANKED: "proceed to clinical evaluation",
    Bucket.PROVISIONAL_ABO: "obtain a laboratory blood group",
    Bucket.INSUFFICIENT_HLA: "obtain HLA typing",
    Bucket.INSUFFICIENT_ABO: "obtain a laboratory blood group",
    Bucket.ABO_INCOMPATIBLE: "not a candidate on the direct pathway",
    Bucket.BLOCKED_DSA_OR_LAB_REVIEW: "laboratory review",
    Bucket.BLOCKED_POSITIVE_CROSSMATCH: "direct pathway blocked",
    Bucket.EXCLUDED_NON_CLINICAL: "none",
}


def _both_groups_readable(inputs: PairInputs) -> bool:
    """True only when both sides carry a value that is actually an ABO group."""
    return all(
        group is not None and group.strip().upper() in GROUPS
        for group in (inputs.donor_group, inputs.recipient_group)
    )


def _hla_sufficient(vector: MismatchVector) -> tuple[bool, str]:
    """A pair needs DRB1 and B usable on both sides to receive a level."""
    missing = [
        locus
        for locus in ("DRB1", "B")
        if vector.per_locus.get(locus) is None
        or vector.per_locus[locus].status is MismatchStatus.UNKNOWN
    ]
    if missing:
        return False, f"{' and '.join(missing)} unknown on at least one side"
    return True, ""


def assign_bucket(inputs: PairInputs, vector: MismatchVector) -> BucketDecision:
    """Place a pair in exactly one bucket, blocking conditions first."""
    abo = abo_gate(
        inputs.donor_group,
        inputs.recipient_group,
        donor_provenance=inputs.donor_provenance,
        recipient_provenance=inputs.recipient_provenance,
    )

    blockers: list[str] = []
    hit: dict[Bucket, str] = {}

    if not (inputs.donor_eligible and inputs.recipient_eligible):
        why = inputs.ineligibility_reason or "a party is not eligible for matching"
        hit[Bucket.EXCLUDED_NON_CLINICAL] = why
        blockers.append(why)
    if inputs.crossmatch is CrossmatchState.POSITIVE:
        why = "a valid positive physical crossmatch blocks the direct pathway"
        hit[Bucket.BLOCKED_POSITIVE_CROSSMATCH] = why
        blockers.append(why)
    if inputs.dsa_conflicts:
        why = "a reviewed unacceptable antigen or DSA targets a reviewed donor value: " + ", ".join(
            inputs.dsa_conflicts
        )
        hit[Bucket.BLOCKED_DSA_OR_LAB_REVIEW] = why
        blockers.append(why)
    if abo.gate is AboGate.INCOMPATIBLE:
        hit[Bucket.ABO_INCOMPATIBLE] = abo.reason
        blockers.append(abo.reason)

    for bucket in _BLOCKING_ORDER:
        if bucket in hit:
            return BucketDecision(
                bucket,
                reasons=(hit[bucket],),
                blockers=tuple(blockers),
                abo=abo,
                next_action=_NEXT_ACTION[bucket],
            )

    # Nothing blocks. Now the informational passes, most limiting first.
    #
    # A group is usable only if it is actually an ABO letter. A present but
    # unrecognised value (an OCR garble, an Rh-carrying string, a stray cell) is
    # a MISSING group, not a weak one: routing it to PROVISIONAL_ABO would put
    # it in a ranked bucket, which is the one thing an unreadable blood group
    # must never reach.
    if not _both_groups_readable(inputs):
        return BucketDecision(
            Bucket.INSUFFICIENT_ABO,
            reasons=(abo.reason,),
            abo=abo,
            next_action=_NEXT_ACTION[Bucket.INSUFFICIENT_ABO],
        )

    sufficient, why = _hla_sufficient(vector)
    if not sufficient:
        return BucketDecision(
            Bucket.INSUFFICIENT_HLA,
            reasons=(f"no KM level: {why}",),
            abo=abo,
            next_action=_NEXT_ACTION[Bucket.INSUFFICIENT_HLA],
        )

    if abo.gate is AboGate.UNKNOWN:
        # Groups are present and compatible, but at least one is not a
        # laboratory measurement, so it may not clear the pair (KI-014).
        return BucketDecision(
            Bucket.PROVISIONAL_ABO,
            reasons=(abo.reason,),
            abo=abo,
            next_action=_NEXT_ACTION[Bucket.PROVISIONAL_ABO],
        )

    return BucketDecision(
        Bucket.RANKED,
        reasons=(abo.reason,),
        abo=abo,
        next_action=_NEXT_ACTION[Bucket.RANKED],
    )
