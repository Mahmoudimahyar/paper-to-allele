"""The matching core: rank donors for a recipient, and recipients for a donor.

`MATCH-001`. Policy: `docs/clinical/MATCHING_POLICY_V2.md`.

Both directions call one mismatch function with the recipient always in the
recipient argument, because the count is host versus graft and is not symmetric:
`MM(D->R) - MM(R->D)` equals the difference in the two sides' distinct allele
counts, so a homozygous donor into a heterozygous recipient counts one where the
same two people swapped count two. Only the iteration changes between the two
directions; the arguments never do.

The explanation is generated FROM the sort key rather than alongside it, so a
field that does not appear in the key cannot influence the order and an order
cannot be produced that the explanation fails to account for. That is the
MATCH-001 acceptance criterion "rank explanation exactly reconstructs sort keys",
made structural.

No compensation, identifier, message text or preference claim reaches this
module. `Profile` has no field for any of them.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .abo import AboProvenance
from .gates import Bucket, BucketDecision, CrossmatchState, PairInputs, assign_bucket
from .mismatch import (
    PRESENCE_GENES,
    LocusMismatch,
    LocusTyping,
    LocusValue,
    MismatchStatus,
    MismatchVector,
    PresenceMismatch,
    mismatch_at_locus,
    parse_locus_value,
)
from .policy import MatchingPolicy, load_policy
from .ranking import KM_LEVEL_NAMES, SortKey, km_level, sort_key

__all__ = [
    "Direction",
    "MatchingNotImplemented",
    "Profile",
    "RankedPair",
    "Role",
    "build_vector",
    "rank_donors_for",
    "rank_recipients_for",
]


class MatchingNotImplemented(RuntimeError):
    """Kept so an older caller fails loudly rather than silently changing meaning."""


class Role(StrEnum):
    DONOR = "DONOR"
    RECIPIENT = "RECIPIENT"
    UNKNOWN = "UNKNOWN"


class Direction(StrEnum):
    DONORS_FOR_RECIPIENT = "donors_for_recipient"
    RECIPIENTS_FOR_DONOR = "recipients_for_donor"


@dataclass(frozen=True, slots=True)
class Profile:
    """A frozen view of one party. Everything ranking may see, and nothing else.

    `hla` maps a locus to the stored `(value, second_allele_flag)` pair exactly
    as `gold_fact` holds it, so the allele count is derived here rather than
    trusted from the flag.
    """

    profile_id: str
    role: Role
    hla: dict[str, tuple[str | None, str | None]] = field(default_factory=dict)
    presence: dict[str, str] = field(default_factory=dict)
    abo: str | None = None
    abo_provenance: AboProvenance = AboProvenance.UNKNOWN
    tiers: dict[str, str] = field(default_factory=dict)
    eligible: bool = True
    ineligibility_reason: str = ""
    crossmatch: CrossmatchState = CrossmatchState.NOT_PERFORMED
    dsa_conflicts: tuple[str, ...] = ()
    duplicate_candidate_of: tuple[str, ...] = ()

    def locus(self, name: str) -> LocusValue:
        raw, flag = self.hla.get(name, (None, None))
        return parse_locus_value(raw, flag, locus=name)


@dataclass(frozen=True, slots=True)
class RankedPair:
    """One row of a result, with the explanation that reproduces its position."""

    donor_id: str
    recipient_id: str
    bucket: Bucket
    key: SortKey
    vector: MismatchVector
    decision: BucketDecision
    explanation: dict[str, Any]

    @property
    def candidate_id(self) -> str:
        """The profile being ranked, as opposed to the one held fixed."""
        return str(self.explanation["candidate_id"])


def build_vector(donor: Profile, recipient: Profile) -> MismatchVector:
    """The host-versus-graft mismatch vector for an ordered pair."""
    per_locus: dict[str, LocusMismatch] = {}
    for locus in ("A", "B", "C", "DRB1", "DQB1"):
        per_locus[locus] = mismatch_at_locus(donor.locus(locus), recipient.locus(locus))

    presence: list[PresenceMismatch] = []
    for gene in PRESENCE_GENES:
        d = (donor.presence.get(gene) or "UNKNOWN").upper()
        r = (recipient.presence.get(gene) or "UNKNOWN").upper()
        if "REVIEW" in d or "REVIEW" in r:
            presence.append(
                PresenceMismatch(gene, MismatchStatus.UNKNOWN, reason="review required")
            )
        elif d == "UNKNOWN" or r == "UNKNOWN":
            presence.append(
                PresenceMismatch(gene, MismatchStatus.UNKNOWN, reason="presence not established")
            )
        else:
            conflict = d == "PRESENT" and r == "ABSENT"
            presence.append(
                PresenceMismatch(
                    gene,
                    MismatchStatus.KNOWN,
                    conflict=conflict,
                    reason="donor carries a gene the recipient lacks" if conflict else "",
                )
            )

    dq_mode = "DQB1_ONLY"
    notes: list[str] = []
    if donor.locus("DQA1").usable and recipient.locus("DQA1").usable:
        notes.append(
            "DQA1 is typed but a heterodimer comparison needs two-field typing on "
            "both chains with unambiguous phase; DQB1 alone was compared"
        )
    return MismatchVector(per_locus, tuple(presence), dq_mode, tuple(notes))


#: Worst crossmatch state wins, so a positive on either side is never masked.
_CROSSMATCH_SEVERITY: dict[CrossmatchState, int] = {
    CrossmatchState.NEGATIVE: 0,
    CrossmatchState.NOT_PERFORMED: 1,
    CrossmatchState.EXPIRED: 2,
    CrossmatchState.INDETERMINATE: 3,
    CrossmatchState.POSITIVE: 4,
}


def _worst_crossmatch(donor: Profile, recipient: Profile) -> CrossmatchState:
    """The more serious of the two recorded states.

    An earlier version preferred the donor's state unless it was NOT_PERFORMED,
    which let a donor-side NEGATIVE hide a recipient-side POSITIVE. A crossmatch
    is a property of the pair, and the conservative reading of two records is
    the worse one.
    """
    return max(
        (donor.crossmatch, recipient.crossmatch),
        key=lambda state: _CROSSMATCH_SEVERITY[state],
    )


def _evidence_penalty(donor: Profile, recipient: Profile, vector: MismatchVector) -> int:
    """Worse extraction evidence sorts later, all else equal.

    Tier C is a locus no labelled cell has ever tested; tier B is labelled but
    thin. This is extraction confidence, not clinical risk, and it only ever
    breaks a tie between otherwise equal candidates.

    An UNKNOWN locus is charged at the worst tier rather than skipped. Skipping
    it let deleting a typing lower the penalty, which is the same
    losing-information-improves-rank defect the tie-breaker had.
    """
    cost = {"A": 0, "B": 1, "C": 3}
    worst = max(cost.values())
    total = 0
    for locus, mm in vector.per_locus.items():
        if mm.status is MismatchStatus.UNKNOWN:
            total += 2 * worst
            continue
        for side in (donor, recipient):
            total += cost.get((side.tiers.get(locus) or "C").upper(), worst)
    return total


def _explain(
    *,
    direction: Direction,
    donor: Profile,
    recipient: Profile,
    vector: MismatchVector,
    decision: BucketDecision,
    key: SortKey,
    policy: MatchingPolicy,
) -> dict[str, Any]:
    """Rebuild the human-readable account directly from the sort key."""
    level = km_level(vector)
    anchor, candidate = (
        (recipient, donor) if direction is Direction.DONORS_FOR_RECIPIENT else (donor, recipient)
    )

    mismatches: dict[str, Any] = {}
    for locus, mm in sorted(vector.per_locus.items()):
        entry: dict[str, Any] = {"status": mm.status.value}
        if mm.status is MismatchStatus.KNOWN:
            entry["count"] = mm.count
        elif mm.status is MismatchStatus.RANGE:
            entry["lower"], entry["upper"] = mm.lower, mm.upper
        if mm.compared_depth is not None:
            entry["depth"] = "one_field" if mm.compared_depth == 1 else "two_field"
        if mm.truncated:
            entry["comparison_truncated"] = True
        if mm.reason:
            entry["why"] = mm.reason
        mismatches[locus] = entry

    structural: list[str] = []
    if level.km_1_unreachable:
        structural.append(f"KM-1 unreachable: {level.km_1_unreachable}")
    for locus in ("DRB1", "DQB1", "A", "B"):
        value = recipient.locus(locus)
        if value.typing is LocusTyping.BOTH and len(set(value.alleles)) == 1:
            structural.append(
                f"the recipient is homozygous at {locus}: zero mismatch there is only "
                "reachable from a donor sharing that allele"
            )
    if candidate.duplicate_candidate_of:
        structural.append(
            "this profile shares a genotype with another profile and may be the same "
            "person; profiles are photographs, not people"
        )
    structural.extend(vector.notes)

    return {
        "direction": direction.value,
        "anchor_id": anchor.profile_id,
        "candidate_id": candidate.profile_id,
        "donor_id": donor.profile_id,
        "recipient_id": recipient.profile_id,
        "bucket": decision.bucket.value,
        "km_level": level.level,
        "km_level_name": KM_LEVEL_NAMES.get(level.level, "no level"),
        "km_level_best_case": level.best_case,
        "sort_key": list(key.as_tuple()),
        "abo": {
            "donor": donor.abo,
            "recipient": recipient.abo,
            "gate": decision.abo.gate.value if decision.abo else "UNKNOWN",
            "reason": decision.abo.reason if decision.abo else "",
            "provenance": {
                "donor": donor.abo_provenance.value,
                "recipient": recipient.abo_provenance.value,
            },
        },
        "mismatches": mismatches,
        "presence": {
            p.gene: {"status": p.status.value, "conflict": p.conflict, "why": p.reason}
            for p in vector.presence
        },
        "dq_mode": vector.dq_mode,
        "antibody_status": decision.antibody_status,
        "crossmatch_status": _worst_crossmatch(donor, recipient).value,
        "unknown_loci": list(vector.unknown_loci()),
        "partial_loci": list(vector.partial_loci()),
        "structural_notes": structural,
        "blockers": list(decision.blockers),
        "next_clinical_action": decision.next_action,
        "policy_version": policy.policy_id,
        "policy_adopted": policy.is_adopted,
        "imgt_version": policy.imgt_version,
        "pyard_version": policy.pyard_version,
    }


def _rank(
    *,
    direction: Direction,
    anchor: Profile,
    candidates: Iterable[Profile],
    policy: MatchingPolicy,
) -> list[RankedPair]:
    rows: list[RankedPair] = []
    for candidate in candidates:
        if candidate.profile_id == anchor.profile_id:
            continue
        donor, recipient = (
            (candidate, anchor)
            if direction is Direction.DONORS_FOR_RECIPIENT
            else (anchor, candidate)
        )
        vector = build_vector(donor, recipient)
        inputs = PairInputs(
            donor_group=donor.abo,
            recipient_group=recipient.abo,
            donor_provenance=donor.abo_provenance,
            recipient_provenance=recipient.abo_provenance,
            donor_eligible=donor.eligible,
            recipient_eligible=recipient.eligible,
            ineligibility_reason=donor.ineligibility_reason or recipient.ineligibility_reason,
            crossmatch=_worst_crossmatch(donor, recipient),
            dsa_conflicts=recipient.dsa_conflicts,
        )
        decision = assign_bucket(inputs, vector)
        key = sort_key(
            bucket_rank=decision.bucket.rank,
            vector=vector,
            policy=policy,
            evidence_penalty=_evidence_penalty(donor, recipient, vector),
            anchor_id=anchor.profile_id,
            candidate_id=candidate.profile_id,
        )
        rows.append(
            RankedPair(
                donor_id=donor.profile_id,
                recipient_id=recipient.profile_id,
                bucket=decision.bucket,
                key=key,
                vector=vector,
                decision=decision,
                explanation=_explain(
                    direction=direction,
                    donor=donor,
                    recipient=recipient,
                    vector=vector,
                    decision=decision,
                    key=key,
                    policy=policy,
                ),
            )
        )
    rows.sort(key=lambda row: row.key.as_tuple())
    return rows


class RoleMismatch(ValueError):
    """The anchor was asked to play a role it does not hold."""


def _require_role(profile: Profile, wanted: Role, where: str) -> None:
    """The anchor's role is checked too, not only the candidates'.

    Filtering the candidate list alone let a role-UNKNOWN profile be ranked as
    the anchor, and let a donor be handed in as a recipient. Establishing a role
    is a review action; the matcher may not infer one, so it refuses instead.
    """
    if profile.role is not wanted:
        raise RoleMismatch(
            f"{where}: profile {profile.profile_id!r} has role {profile.role.value}, "
            f"and {wanted.value} is required; a role is established by review, not inferred"
        )


def _eligible(candidates: Iterable[Profile], wanted: Role) -> list[Profile]:
    """Role-UNKNOWN profiles appear in neither direction.

    2,026 profiles have no established role. Treating them as either party would
    be an inference the matcher may not make; establishing a role is a review
    action.
    """
    return [c for c in candidates if c.role is wanted]


def rank_donors_for(
    recipient: Profile,
    donors: Sequence[Profile],
    *,
    policy: MatchingPolicy | None = None,
) -> list[RankedPair]:
    """Rank every eligible donor for one recipient."""
    _require_role(recipient, Role.RECIPIENT, "rank_donors_for")
    return _rank(
        direction=Direction.DONORS_FOR_RECIPIENT,
        anchor=recipient,
        candidates=_eligible(donors, Role.DONOR),
        policy=policy or load_policy(),
    )


def rank_recipients_for(
    donor: Profile,
    recipients: Sequence[Profile],
    *,
    policy: MatchingPolicy | None = None,
) -> list[RankedPair]:
    """Rank every eligible recipient for one donor.

    The same host-versus-graft direction, iterating the other way. The mismatch
    arguments are not transposed.
    """
    _require_role(donor, Role.DONOR, "rank_recipients_for")
    return _rank(
        direction=Direction.RECIPIENTS_FOR_DONOR,
        anchor=donor,
        candidates=_eligible(recipients, Role.RECIPIENT),
        policy=policy or load_policy(),
    )


def rank_candidates(*_: object, **__: object) -> None:
    """Removed. Use `rank_donors_for` or `rank_recipients_for`."""
    raise MatchingNotImplemented(
        "rank_candidates was replaced by rank_donors_for / rank_recipients_for; "
        "the direction must be explicit because the mismatch count is not symmetric"
    )
