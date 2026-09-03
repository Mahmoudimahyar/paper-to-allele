"""The ABO gate: who may donate to whom, and when we are not allowed to say.

`MATCH-ABO-001`. This is the one part of matching that is not national policy —
blood-group compatibility is the same in Tehran as anywhere — so it can be
written while `HA-004` (Iranian histocompatibility practice) is still open. The
HLA side cannot: which loci are counted and how mismatches are weighted is
exactly what that question asks.

**Not wired into `matching.core` yet.** MVP-HIST does not run clinical ranking,
and this changes no behaviour today. It exists so the gate is written, tested
and reviewable before anything depends on it.

## The gate is a hard stop, and it comes before HLA

An incompatible pair is not a low-ranked pair. `PRODUCT_CONSTITUTION` and
`MATCH-001` both require the ABO gate to precede the HLA heuristic, because a
ranking that lists an incompatible donor at all invites someone to act on it.

## Why most of this file is about refusing to answer

Measured (KI-014), the dominant letterhead in this archive prints:

> the information regarding the blood group is based on the attendee's own
> account, and the laboratory bears no responsibility for its accuracy

on 2,928 documents. A blood group carrying that disclaimer is
`PATIENT_REPORTED_ON_FORM`, not a laboratory measurement, and its agreement
with the caption is not corroboration because both can descend from the same
sentence. So a patient-reported group can *exclude* a pair — it is evidence
enough to stop — but it can never *clear* one. Clearing needs a measured group.

That asymmetry is the whole design: a wrong exclusion costs a missed match, and
a wrong clearance costs a transfused incompatible kidney.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# Who may give to whom, by red-cell antigen. Universal biology, not policy.
_CAN_DONATE: dict[str, frozenset[str]] = {
    "O": frozenset({"O", "A", "B", "AB"}),
    "A": frozenset({"A", "AB"}),
    "B": frozenset({"B", "AB"}),
    "AB": frozenset({"AB"}),
}

GROUPS = frozenset(_CAN_DONATE)


class AboProvenance(StrEnum):
    """Where a blood group came from, which decides what it may be used for."""

    LABORATORY_MEASURED = "LABORATORY_MEASURED"
    PATIENT_REPORTED_ON_FORM = "PATIENT_REPORTED_ON_FORM"
    CAPTION_CLAIM = "CAPTION_CLAIM"
    UNKNOWN = "UNKNOWN"


#: Provenances strong enough to CLEAR a pair. Everything else may only exclude.
_CAN_CLEAR = frozenset({AboProvenance.LABORATORY_MEASURED})


class AboGate(StrEnum):
    COMPATIBLE = "COMPATIBLE"
    INCOMPATIBLE = "INCOMPATIBLE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class AboDecision:
    """A gate outcome that always carries the reason it reached it."""

    gate: AboGate
    reason: str
    donor_provenance: AboProvenance = AboProvenance.UNKNOWN
    recipient_provenance: AboProvenance = AboProvenance.UNKNOWN

    @property
    def blocks_pair(self) -> bool:
        """Only INCOMPATIBLE stops a pair. UNKNOWN sends it to a person."""
        return self.gate is AboGate.INCOMPATIBLE


def abo_gate(
    donor_group: str | None,
    recipient_group: str | None,
    *,
    donor_provenance: AboProvenance = AboProvenance.UNKNOWN,
    recipient_provenance: AboProvenance = AboProvenance.UNKNOWN,
) -> AboDecision:
    """Decide the direct-route ABO gate for one donor and one recipient.

    Returns `UNKNOWN` — never a guess — when either group is missing, is not a
    real group, or is known only from a source that may not clear a pair.
    """
    if donor_group is None or recipient_group is None:
        return AboDecision(
            AboGate.UNKNOWN,
            "a blood group is missing; a missing value is UNKNOWN and never assumed",
            donor_provenance,
            recipient_provenance,
        )
    donor = donor_group.strip().upper()
    recipient = recipient_group.strip().upper()
    if donor not in GROUPS or recipient not in GROUPS:
        return AboDecision(
            AboGate.UNKNOWN,
            f"{donor!r} or {recipient!r} is not an ABO group",
            donor_provenance,
            recipient_provenance,
        )

    compatible = recipient in _CAN_DONATE[donor]
    if not compatible:
        # An exclusion is safe on weaker evidence than a clearance: the cost of
        # being wrong is a missed match, not a transfused incompatible organ.
        return AboDecision(
            AboGate.INCOMPATIBLE,
            f"group {donor} cannot donate to group {recipient}",
            donor_provenance,
            recipient_provenance,
        )

    unmeasured = [
        who
        for who, provenance in (("donor", donor_provenance), ("recipient", recipient_provenance))
        if provenance not in _CAN_CLEAR
    ]
    if unmeasured:
        return AboDecision(
            AboGate.UNKNOWN,
            (
                f"the {' and '.join(unmeasured)} blood group is not a laboratory measurement, "
                "so it may exclude a pair but may not clear one (KI-014)"
            ),
            donor_provenance,
            recipient_provenance,
        )

    return AboDecision(
        AboGate.COMPATIBLE,
        f"group {donor} may donate to group {recipient}, both laboratory-measured",
        donor_provenance,
        recipient_provenance,
    )
