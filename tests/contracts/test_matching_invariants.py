"""The invariants a ranking must hold, and the proof that these checks can fail.

`MATCH-EVAL-001`. Policy: `docs/clinical/MATCHING_POLICY_V2.md` sections 5, 6.3
and 6.4.

Every rule in this file is one a person could be harmed by if it quietly stopped
holding: a blocked pair presented as a low-ranked one, an untyped locus read as
a clean match, an order that moves when a field the matcher may not read
changes. None of them are visible in the output of a single well-typed pair,
which is why they are written as invariants over whole rankings rather than as
expectations about one row.

The second half of the file exists because this repository has been burned by
tests that could not fail. Each invariant is a checker taking a ranking
callable, and each checker is itself put in front of a ranker deliberately built
to break exactly that rule: one that ignores the buckets, one that reads a
missing locus as a zero mismatch, one that sells the first position, one whose
answer depends on how many times it has been called, one that rewards a
candidate for having less data, one that charges nothing for a locus nobody
typed, one that reads an untyped DRB1 as a matched one, one that discounts the
extraction evidence of a locus it could not read, one that calls a typing
foreign because it was printed without its locus prefix, one that lets an
unreadable blood group into a ranked bucket, one that takes its caller's word
for the anchor's role, and one that lets a donor-side crossmatch mask a
recipient-side one. A checker that does not raise there is a checker that proves
nothing, and the meta-test says so before the invariant is trusted.

Monotonicity is why several of these rules read the way they do. The sort tuple
is compared lexicographically, so nothing at a later position can offset a
saving at an earlier one: an unknown locus that cost nothing at the penalty
position was never paid for by the unknown count three positions further down,
and deleting a mismatched typing improved a candidate's rank. An unknown locus
is therefore charged at its worst case, at the position where the saving would
otherwise appear.

No real typing appears here. Every allele string is synthetic and every profile
identifier is a label, not a person.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Sequence
from dataclasses import dataclass, fields, replace
from itertools import count
from pathlib import Path
from unittest import mock

import pytest

from kidneymatch.matching import core, gates, ranking
from kidneymatch.matching.abo import AboProvenance
from kidneymatch.matching.core import Profile, RankedPair, Role, rank_donors_for
from kidneymatch.matching.core import build_vector as real_build_vector
from kidneymatch.matching.gates import Bucket, CrossmatchState
from kidneymatch.matching.mismatch import (
    PRESENCE_GENES,
    SCORED_LOCI,
    LocusMismatch,
    LocusValue,
    MismatchStatus,
    MismatchVector,
    PresenceMismatch,
)
from kidneymatch.matching.mismatch import parse_locus_value as real_parse_locus_value
from kidneymatch.matching.policy import MatchingPolicy, load_policy
from kidneymatch.matching.ranking import NO_LEVEL

pytestmark = pytest.mark.task("MATCH-EVAL-001")

Ranker = Callable[[Profile, Sequence[Profile]], list[RankedPair]]
Penalty = Callable[[MismatchVector, MatchingPolicy], int]

MEASURED = AboProvenance.LABORATORY_MEASURED
REPORTED = AboProvenance.PATIENT_REPORTED_ON_FORM
CAPTION = AboProvenance.CAPTION_CLAIM

Typing = dict[str, tuple[str | None, str | None]]

#: One synthetic reference typing. Every fixture below is a stated edit of it,
#: so what a case is testing is the edit and nothing else.
REFERENCE: Typing = {
    "A": ("A*01 A*02", "READ"),
    "B": ("B*07 B*08", "READ"),
    "C": ("C*01 C*02", "READ"),
    "DRB1": ("DRB1*03 DRB1*04", "READ"),
    "DQB1": ("DQB1*02 DQB1*03", "READ"),
}

#: Presence established as absent on all three genes: no conflict, no unknown.
NO_DRBX: dict[str, str] = {"DRB3": "ABSENT", "DRB4": "ABSENT", "DRB5": "ABSENT"}
CARRIES_DRB3: dict[str, str] = {"DRB3": "PRESENT", "DRB4": "ABSENT", "DRB5": "ABSENT"}

#: Values that are present in the record but are not an ABO group: an OCR
#: garble, an Rh-carrying string, a zero read for the letter O, a stray cell.
#: None of them says anything about compatibility, in either direction.
UNREADABLE_GROUPS: tuple[str, ...] = ("not-a-group", "O+", "   ", "0", "AB Rh+")

#: How serious a crossmatch record is, least first. Written out here rather than
#: imported so the test states the rule instead of repeating the implementation.
CROSSMATCH_SEVERITY: tuple[CrossmatchState, ...] = (
    CrossmatchState.NEGATIVE,
    CrossmatchState.NOT_PERFORMED,
    CrossmatchState.EXPIRED,
    CrossmatchState.INDETERMINATE,
    CrossmatchState.POSITIVE,
)


def edited(base: Typing, **loci: tuple[str | None, str | None]) -> Typing:
    """The reference typing with named loci replaced."""
    return {**base, **loci}


def without(base: Typing, locus: str) -> Typing:
    """The reference typing with one locus never typed at all."""
    return {name: value for name, value in base.items() if name != locus}


def a_recipient(
    profile_id: str = "R",
    *,
    hla: Typing | None = None,
    presence: dict[str, str] | None = None,
    abo: str | None = "O",
    provenance: AboProvenance = MEASURED,
    crossmatch: CrossmatchState = CrossmatchState.NOT_PERFORMED,
    dsa_conflicts: tuple[str, ...] = (),
) -> Profile:
    return Profile(
        profile_id=profile_id,
        role=Role.RECIPIENT,
        hla=dict(REFERENCE if hla is None else hla),
        presence=dict(NO_DRBX if presence is None else presence),
        abo=abo,
        abo_provenance=provenance,
        crossmatch=crossmatch,
        dsa_conflicts=dsa_conflicts,
    )


def a_donor(
    profile_id: str,
    *,
    hla: Typing | None = None,
    presence: dict[str, str] | None = None,
    abo: str | None = "O",
    provenance: AboProvenance = MEASURED,
    crossmatch: CrossmatchState = CrossmatchState.NOT_PERFORMED,
    eligible: bool = True,
) -> Profile:
    return Profile(
        profile_id=profile_id,
        role=Role.DONOR,
        hla=dict(REFERENCE if hla is None else hla),
        presence=dict(NO_DRBX if presence is None else presence),
        abo=abo,
        abo_provenance=provenance,
        crossmatch=crossmatch,
        eligible=eligible,
    )


def a_roleless_profile(profile_id: str = "P-NO-ROLE") -> Profile:
    """A profile whose role no reviewer has established."""
    return Profile(
        profile_id=profile_id,
        role=Role.UNKNOWN,
        hla=dict(REFERENCE),
        presence=dict(NO_DRBX),
        abo="O",
        abo_provenance=MEASURED,
    )


def order_of(rows: Sequence[RankedPair]) -> list[str]:
    """The candidate identifiers in the order the ranking returned them."""
    return [row.candidate_id for row in rows]


def by_id(rows: Sequence[RankedPair]) -> dict[str, RankedPair]:
    return {row.candidate_id: row for row in rows}


def a_presence(*, conflict: str = "", unknown: str = "") -> tuple[PresenceMismatch, ...]:
    """The three DRB3/4/5 genes settled, with at most one gene disturbed."""
    out: list[PresenceMismatch] = []
    for gene in PRESENCE_GENES:
        if gene == unknown:
            out.append(
                PresenceMismatch(gene, MismatchStatus.UNKNOWN, reason="presence not established")
            )
        elif gene == conflict:
            out.append(
                PresenceMismatch(
                    gene,
                    MismatchStatus.KNOWN,
                    conflict=True,
                    reason="donor carries a gene the recipient lacks",
                )
            )
        else:
            out.append(PresenceMismatch(gene, MismatchStatus.KNOWN))
    return tuple(out)


def a_vector(
    *,
    counts: dict[str, int] | None = None,
    unknown: tuple[str, ...] = (),
    presence: tuple[PresenceMismatch, ...] | None = None,
) -> MismatchVector:
    """A mismatch vector stated directly, so one locus varies and nothing else.

    Built by hand rather than from two profiles because the arithmetic rules
    below are about the tie-breaker alone; routing them through a typing would
    let a compensating error in the mismatch counter hide one in the charge.
    """
    per_locus: dict[str, LocusMismatch] = {}
    for locus in SCORED_LOCI:
        if locus in unknown:
            per_locus[locus] = LocusMismatch(MismatchStatus.UNKNOWN, reason="not typed")
            continue
        n = (counts or {}).get(locus, 0)
        per_locus[locus] = LocusMismatch(
            MismatchStatus.KNOWN, count=n, lower=n, upper=n, compared_depth=1
        )
    return MismatchVector(
        per_locus,
        a_presence() if presence is None else presence,
        "DQB1_ONLY",
        (),
    )


# --- the invariant checkers -----------------------------------------------
#
# Each takes a ranking callable and raises AssertionError when the rule it
# names does not hold. They are functions rather than tests so that a broken
# ranker can be pushed through the identical code path.


def check_gates_precede_the_hla_heuristic(rank: Ranker) -> None:
    """A blocked pair never outranks a ranked one, whatever its HLA.

    `PRODUCT_CONSTITUTION` gives BLOCKED a status of its own. A ranking that
    lists an incompatible donor at all invites someone to act on it, so position
    zero of the sort tuple is the bucket and the HLA heuristic can never reach
    past it.
    """
    recipient = a_recipient("R")
    blocked = a_donor("D-PERFECT-BUT-BLOCKED", abo="B")  # B may not donate to O
    cleared = a_donor(
        "D-POOR-BUT-CLEARED",
        hla=edited(REFERENCE, B=("B*15 B*44", "READ"), DRB1=("DRB1*11 DRB1*13", "READ")),
    )

    rows = rank(recipient, [blocked, cleared])
    found = by_id(rows)
    assert found["D-PERFECT-BUT-BLOCKED"].key.km_level < found["D-POOR-BUT-CLEARED"].key.km_level, (
        "this fixture is not adversarial: the blocked donor must hold the better HLA, "
        "or the invariant would be satisfied by the heuristic agreeing with the gate"
    )

    blocked_above = ""
    for row in rows:
        if not row.bucket.is_ranked:
            blocked_above = f"{row.candidate_id} ({row.bucket.value})"
        elif blocked_above:
            raise AssertionError(
                f"a blocked pair outranks a ranked one: {blocked_above} sits above "
                f"{row.candidate_id} ({row.bucket.value})"
            )


def check_a_missing_locus_is_unknown_never_zero(rank: Ranker) -> None:
    """An untyped locus is UNKNOWN. It is not a zero mismatch and never helps.

    Policy section 3.5. Zero mismatch is a claim about two typings; there is
    only one here.
    """
    recipient = a_recipient("R")
    typed = a_donor("D-TYPED")
    no_a = a_donor("D-NO-A", hla=without(REFERENCE, "A"))
    no_dr = a_donor("D-NO-DR", hla=without(REFERENCE, "DRB1"))

    rows = rank(recipient, [typed, no_a, no_dr])
    found = by_id(rows)

    assert found["D-TYPED"].key.km_level == 1, (
        "this fixture is not adversarial: the fully typed donor must reach KM-1 "
        "so that an untyped one reaching it too is visible"
    )
    assert found["D-NO-A"].key.km_level != 1, (
        "an untyped HLA-A was read as a zero mismatch: UNKNOWN is not 0, "
        "and KM-1 is a claim that cannot be made from missing data"
    )

    absent = found["D-NO-A"].vector.per_locus["A"]
    assert absent.status is MismatchStatus.UNKNOWN, "UNKNOWN is not 0: an untyped locus is UNKNOWN"
    assert absent.count is None and absent.upper is None, (
        "UNKNOWN is not 0: an untyped locus carries no count at all"
    )
    assert "A" in found["D-NO-A"].explanation["unknown_loci"], (
        "UNKNOWN is not 0: the explanation must name the locus it could not read"
    )

    assert found["D-NO-DR"].key.km_level == NO_LEVEL, (
        "UNKNOWN is not 0: an untyped DRB1 cannot produce a KM level"
    )
    assert found["D-NO-DR"].bucket is Bucket.INSUFFICIENT_HLA, (
        "UNKNOWN is not 0: an untyped DRB1 belongs outside the ranked list"
    )

    order = order_of(rows)
    assert order.index("D-TYPED") < order.index("D-NO-A"), (
        "UNKNOWN is not 0: the untyped donor outranked the fully typed one"
    )


def check_an_unknown_locus_is_charged_at_its_worst_case(penalty: Penalty) -> None:
    """An unknown locus costs exactly what a fully mismatched one costs.

    This checker takes the tie-breaker rather than a ranking callable: the rule
    is an arithmetic property of one function, and stating it through a whole
    ranking would let a compensating difference elsewhere in the sort tuple hide
    a saving here.

    The earlier contract was that an unknown locus contributes nothing, on the
    stated ground that the unknown is counted at sort position 5 instead. That
    is arithmetically impossible: the penalty is position 3, and a lexicographic
    comparison is decided by the vanished penalty before it ever reads position
    5. So absence is charged at its worst case, `ranking.UNKNOWN_AS`, which for
    a diploid locus is both alleles foreign. Missing is then never cheaper than
    known-bad, and deleting a typing cannot buy a position.
    """
    policy = load_policy()
    matched = penalty(a_vector(), policy)
    for locus in SCORED_LOCI:
        mismatched = penalty(a_vector(counts={locus: 2}), policy)
        unreadable = penalty(a_vector(unknown=(locus,)), policy)
        assert mismatched > matched, (
            f"this fixture is not adversarial: a fully mismatched {locus} must cost "
            "something, or an unknown one costing the same would prove nothing"
        )
        assert unreadable == mismatched, (
            f"an unknown {locus} was not charged at its worst case: it cost {unreadable} "
            f"where a fully mismatched {locus} costs {mismatched}"
        )
        assert unreadable > matched, (
            f"an unknown {locus} cost no more than a matched one, {unreadable} against "
            f"{matched}: missing must never be cheaper than known-bad"
        )


def check_an_unknown_drb1_keeps_the_dr_gate_closed(penalty: Penalty) -> None:
    """An unknown DRB1 is not a matched DRB1, so the other loci stay halved.

    The DR gate halves every other locus once DRB1 is mismatched, because a
    single DR incompatibility abolished the class I matching benefit across
    39,205 Eurotransplant transplants. Reading an untyped DRB1 as an open gate
    would restore full weight to the class I loci on no evidence at all, and
    would hand a candidate a discount for having less data.
    """
    policy = load_policy()

    def cost_of_a_mismatched_c(*, drb1: int | None) -> int:
        """What two HLA-C mismatches add, beside a DRB1 in the given state.

        `drb1=None` is the untyped case; every other locus is matched in both
        vectors, so the difference is the charge for HLA-C and nothing else.
        """
        unknown = () if drb1 is not None else ("DRB1",)
        counts = {} if drb1 is None else {"DRB1": drb1}
        with_c = a_vector(counts={**counts, "C": 2}, unknown=unknown)
        without_c = a_vector(counts=counts, unknown=unknown)
        return penalty(with_c, policy) - penalty(without_c, policy)

    open_gate = cost_of_a_mismatched_c(drb1=0)
    shut_by_a_mismatch = cost_of_a_mismatched_c(drb1=2)
    shut_by_absence = cost_of_a_mismatched_c(drb1=None)

    assert shut_by_a_mismatch < open_gate, (
        "this fixture is not adversarial: a mismatched DRB1 must actually halve the "
        f"charge for HLA-C, and {shut_by_a_mismatch} is not less than {open_gate}"
    )
    assert shut_by_absence == shut_by_a_mismatch, (
        f"an unknown DRB1 left the DR gate open: HLA-C cost {shut_by_absence} beside it "
        f"where a mismatched DRB1 charges {shut_by_a_mismatch}"
    )


def check_an_unestablished_drbx_presence_is_charged_like_a_conflict(penalty: Penalty) -> None:
    """A DRB3/4/5 gene nobody established costs what a conflict costs.

    The same monotonicity argument as the loci: if presence conflict is charged
    and absence of the record is free, then deleting the presence row is a
    saving, and the candidate whose DRB3 was never looked at outranks the one
    whose DRB3 was found to conflict.
    """
    policy = load_policy()
    settled = penalty(a_vector(), policy)
    for gene in PRESENCE_GENES:
        conflicting = penalty(a_vector(presence=a_presence(conflict=gene)), policy)
        never_established = penalty(a_vector(presence=a_presence(unknown=gene)), policy)
        assert conflicting > settled, (
            f"this fixture is not adversarial: a {gene} presence conflict must cost "
            "something, or an unestablished one costing the same would prove nothing"
        )
        assert never_established == conflicting, (
            f"a {gene} whose presence was never established cost {never_established} "
            f"where a {gene} conflict costs {conflicting}: not looking must never be "
            "cheaper than looking and finding a conflict"
        )


def check_no_compensation_field(profile_cls: type) -> None:
    """The matcher cannot read what it was never handed.

    This checker takes the profile class rather than a ranking callable: the
    rule is about the shape of the input, and the shape is where it can be
    enforced structurally instead of by review.
    """
    payment_words = (
        "compensation",
        "payment",
        "price",
        "amount",
        "fee",
        "money",
        "rial",
        "toman",
        "reward",
        "incentive",
    )
    for field in fields(profile_cls):
        for word in payment_words:
            assert word not in field.name.lower(), (
                f"{profile_cls.__name__}.{field.name} reads as compensation; the matching "
                "core may not be handed what it may not read"
            )


def check_an_unread_field_cannot_change_the_order(rank: Ranker) -> None:
    """Two runs whose profiles differ only in a field the matcher does not read
    must produce the same order and the same sort keys.

    The absence of a field on `Profile` is one half of the guarantee. This is
    the other: even when a caller smuggles the value in on a subclass, nothing
    downstream can reach it.
    """
    recipient = a_recipient("R")
    typings = {
        "D-BEST": REFERENCE,
        "D-MIDDLE": edited(REFERENCE, B=("B*07 B*44", "READ")),
        "D-WORST": edited(REFERENCE, DRB1=("DRB1*11 DRB1*13", "READ")),
    }

    def run(amounts: dict[str, int]) -> list[RankedPair]:
        donors = [
            _ProfileWithAnUnreadField(
                profile_id=name,
                role=Role.DONOR,
                hla=dict(typing),
                presence=dict(NO_DRBX),
                abo="O",
                abo_provenance=MEASURED,
                unreadable_amount=amounts[name],
            )
            for name, typing in typings.items()
        ]
        return rank(recipient, donors)

    nothing_paid = run(dict.fromkeys(typings, 0))
    worst_paid_most = run({"D-BEST": 0, "D-MIDDLE": 1, "D-WORST": 9_000_000})

    assert order_of(nothing_paid) == order_of(worst_paid_most), (
        "a field the matcher does not read changed the order: "
        f"{order_of(nothing_paid)} became {order_of(worst_paid_most)}"
    )
    assert [row.key.as_tuple() for row in nothing_paid] == [
        row.key.as_tuple() for row in worst_paid_most
    ], "a field the matcher does not read changed the sort keys"


def check_the_same_input_gives_the_same_output(rank: Ranker) -> None:
    """The same profiles under the same policy give the same answer, twice.

    A ranking that cannot be reproduced cannot be reviewed, and a reviewer who
    reruns it has to see what the first reader saw.
    """
    recipient = a_recipient("R")
    donors = [
        a_donor("D-1"),
        a_donor("D-2", hla=edited(REFERENCE, B=("B*07 B*44", "READ"))),
        a_donor("D-3", hla=without(REFERENCE, "DQB1")),
        a_donor("D-4", abo="B"),
    ]

    first = rank(recipient, donors)
    second = rank(recipient, donors)

    assert order_of(first) == order_of(second), (
        f"the same input and policy did not give the same order: "
        f"{order_of(first)} then {order_of(second)}"
    )
    assert [row.key.as_tuple() for row in first] == [row.key.as_tuple() for row in second], (
        "the same input and policy did not give the same sort keys"
    )
    assert [row.explanation for row in first] == [row.explanation for row in second], (
        "the same input and policy did not give the same explanations"
    )


def check_losing_information_never_improves_a_position(rank: Ranker) -> None:
    """Delete one locus of the candidate's typing at a time; nothing may improve.

    Policy section 6.3 states this invariant and requires it be tested per
    locus, DRB3/4/5 included. It is checked on the whole sort key rather than on
    the final position alone, because the tuple is compared lexicographically:
    a saving at the penalty position is spent before any later position is read,
    so an offset counted further down the tuple offsets nothing. That is the
    arithmetic that made the earlier "an unknown locus contributes nothing" rule
    unsound, and these assertions are what holds the correction in place.

    The candidate and the rival keep their identifiers throughout, so the stable
    hash at the end of the tuple is constant and is never what a comparison
    turns on.
    """
    recipient = a_recipient("R")
    rival = a_donor("D-RIVAL", hla=edited(REFERENCE, C=("C*01 C*03", "READ")))
    candidate_typing = edited(REFERENCE, C=("C*03 C*04", "READ"))
    candidate = a_donor("D-CANDIDATE", hla=candidate_typing, presence=CARRIES_DRB3)

    def row_and_position(profile: Profile) -> tuple[RankedPair, int]:
        rows = rank(recipient, [profile, rival])
        return by_id(rows)["D-CANDIDATE"], order_of(rows).index("D-CANDIDATE")

    baseline, baseline_at = row_and_position(candidate)

    def compare(degraded: Profile, what: str) -> None:
        row, position = row_and_position(degraded)
        assert position >= baseline_at, (
            f"deleting the candidate's {what} improved its position from "
            f"{baseline_at} to {position}: losing information must never improve a rank"
        )
        assert row.key.penalty >= baseline.key.penalty, (
            f"deleting the candidate's {what} lowered the tie-breaker penalty from "
            f"{baseline.key.penalty} to {row.key.penalty}: absence is charged at its "
            "worst case, so it can never be cheaper than the count it replaced"
        )
        assert row.key.evidence_penalty >= baseline.key.evidence_penalty, (
            f"deleting the candidate's {what} lowered the evidence penalty from "
            f"{baseline.key.evidence_penalty} to {row.key.evidence_penalty}: a locus no "
            "labelled cell was ever read for is the worst evidence, not the absence of any"
        )
        assert row.key.as_tuple() >= baseline.key.as_tuple(), (
            f"deleting the candidate's {what} improved its sort key from "
            f"{baseline.key.as_tuple()} to {row.key.as_tuple()}"
        )

    for locus in ("A", "B", "C", "DRB1", "DQB1"):
        compare(replace(candidate, hla=without(candidate_typing, locus)), f"{locus} typing")

    for gene in ("DRB3", "DRB4", "DRB5"):
        thinner = {name: state for name, state in CARRIES_DRB3.items() if name != gene}
        compare(replace(candidate, presence=thinner), f"{gene} presence")


def check_the_same_typing_written_two_ways_ranks_the_same(rank: Ranker) -> None:
    """One typing, three printed shapes, one answer. And the locus is geometry.

    The archive writes the same value as `DRB1*04 DRB1*11`, as `A*02 A*11`, and
    as bare digit pairs `04 11` with no prefix at all on 2,124 rows. Compared as
    printed text an identical pair looks maximally foreign: a full DRB1 match
    stored bare against one stored prefixed reached KM-6, the exact inversion
    the KM re-cut exists to prevent. The prefix is therefore written onto a bare
    token rather than stripped off the other side, so the explanation keeps the
    printed identity.

    The opposite case may not be normalised at all. A value printed `A*02` in a
    DRB1 cell is a locus-binding failure, not a formatting one: the locus comes
    from the template cell, so the row is REVIEW_REQUIRED and the pair leaves
    the ranked list rather than being rewritten into agreement.
    """
    recipient = a_recipient("R", hla=edited(REFERENCE, DRB1=("DRB1*04 DRB1*11", "READ")))
    prefixed = a_donor("D-PREFIXED", hla=edited(REFERENCE, DRB1=("DRB1*04 DRB1*11", "READ")))
    bare = a_donor("D-BARE", hla=edited(REFERENCE, DRB1=("04 11", "READ")))

    found = by_id(rank(recipient, [prefixed, bare]))
    assert found["D-PREFIXED"].vector.per_locus["DRB1"].count == 0, (
        "this fixture is not adversarial: the prefixed donor must be a full DRB1 match"
    )
    assert found["D-BARE"].vector.per_locus["DRB1"].count == 0, (
        "a typing stored without its locus prefix was read as foreign: the row's locus "
        "is written onto a bare token, and the same typing written two ways compares equal"
    )
    assert found["D-BARE"].key.as_tuple()[:-1] == found["D-PREFIXED"].key.as_tuple()[:-1], (
        "the same typing written two ways ranked differently: "
        f"{found['D-BARE'].key.as_tuple()[:-1]} against "
        f"{found['D-PREFIXED'].key.as_tuple()[:-1]}"
    )

    wrong_locus = a_donor("D-WRONG-PREFIX", hla=edited(REFERENCE, DRB1=("A*02 A*11", "READ")))
    row = by_id(rank(recipient, [wrong_locus]))["D-WRONG-PREFIX"]
    assert row.vector.per_locus["DRB1"].status is MismatchStatus.UNKNOWN, (
        "a value whose printed prefix names another locus was compared anyway: the locus "
        "is decided by geometry, so a disagreement is REVIEW_REQUIRED, not a rewrite"
    )
    assert row.bucket is Bucket.INSUFFICIENT_HLA, (
        "a pair whose DRB1 cell contradicts its own prefix stayed in the ranked list"
    )


def check_an_unreadable_blood_group_never_reaches_a_ranked_bucket(rank: Ranker) -> None:
    """A present but unreadable blood group is a MISSING group, not a weak one.

    PROVISIONAL_ABO is a ranked bucket. It says the two groups are compatible
    and only the provenance is thin, which is a claim about compatibility. An
    OCR garble, an Rh-carrying string or a stray cell supports no such claim, so
    it belongs in INSUFFICIENT_ABO with the missing ones. Routing it to
    PROVISIONAL_ABO would put a pair nobody has cleared into the list a
    coordinator acts on, on the strength of a value that is not a blood group.
    """
    recipient = a_recipient("R")
    cleared = a_donor(
        "D-WORSE-CLEARED",
        hla=edited(REFERENCE, DRB1=("DRB1*11 DRB1*13", "READ"), B=("B*15 B*44", "READ")),
    )

    for garble in UNREADABLE_GROUPS:
        rows = rank(recipient, [a_donor("D-UNREADABLE", abo=garble), cleared])
        row = by_id(rows)["D-UNREADABLE"]
        assert row.key.km_level == 1, (
            "this fixture is not adversarial: the unreadable donor must hold a perfect "
            "HLA match, or the bucket would be doing no work"
        )
        assert row.bucket is Bucket.INSUFFICIENT_ABO, (
            f"a blood group stored as {garble!r} reached {row.bucket.value}: an unreadable "
            "group is a missing group, not a weak one"
        )
        assert row.bucket.is_ranked is False, (
            f"a blood group stored as {garble!r} reached a ranked bucket"
        )
        assert order_of(rows) == ["D-WORSE-CLEARED", "D-UNREADABLE"], (
            f"a donor whose blood group reads {garble!r} outranked a cleared one"
        )

    for garble in UNREADABLE_GROUPS:
        row = by_id(rank(a_recipient("R", abo=garble), [a_donor("D-1")]))["D-1"]
        assert row.bucket is Bucket.INSUFFICIENT_ABO, (
            f"a recipient blood group stored as {garble!r} reached {row.bucket.value}: "
            "the group has to be readable on both sides of the pair"
        )


def check_the_anchors_own_role_is_checked(rank_donors: Ranker, rank_recipients: Ranker) -> None:
    """`rank_donors_for` needs a RECIPIENT anchor, `rank_recipients_for` a DONOR.

    Filtering the candidate list is only half of it. The mismatch count is host
    versus graft and is not symmetric, so the anchor is not a free choice: a
    donor handed in as the anchor of `rank_donors_for` is scored as the
    recipient of every pair, which does not produce a worse answer but a
    differently defined one, under a heading saying the opposite. 2,026 profiles
    have no established role at all, and establishing one is a review action the
    matcher may not perform, so it refuses rather than infers.
    """
    donor, recipient, roleless = a_donor("D-1"), a_recipient("R"), a_roleless_profile()

    def refuses(rank: Ranker, anchor: Profile, candidates: Sequence[Profile], what: str) -> None:
        try:
            rank(anchor, candidates)
        except core.RoleMismatch:
            return
        raise AssertionError(
            f"{what}: the anchor's own role was never checked, so the direction of the "
            "mismatch count was decided by the caller rather than by the record"
        )

    refuses(rank_donors, donor, [a_donor("D-2")], "a donor anchored rank_donors_for")
    refuses(
        rank_donors,
        roleless,
        [a_donor("D-2")],
        "a role-UNKNOWN profile anchored rank_donors_for",
    )
    refuses(
        rank_recipients,
        recipient,
        [a_recipient("R-2")],
        "a recipient anchored rank_recipients_for",
    )
    refuses(
        rank_recipients,
        roleless,
        [a_recipient("R-2")],
        "a role-UNKNOWN profile anchored rank_recipients_for",
    )

    assert order_of(rank_donors(recipient, [donor])) == ["D-1"], (
        "this fixture is not adversarial: the right anchor must still rank, or every "
        "refusal above would be satisfied by a function that refuses everything"
    )
    assert order_of(rank_recipients(donor, [recipient])) == ["R"], (
        "this fixture is not adversarial: the right anchor must still rank in the "
        "recipients-for-donor direction too"
    )


def check_the_worst_crossmatch_on_either_side_decides(rank: Ranker) -> None:
    """A crossmatch is a property of the pair, so the worse record wins.

    A donor-side NEGATIVE once hid a recipient-side POSITIVE, which is the one
    direction of error this gate exists to prevent: the pair was presented as
    ranked and cleared by a laboratory finding that said the opposite. Every
    ordered combination is checked, because the defect was invisible in the
    combinations anyone had thought to write down.
    """
    for donor_state in CROSSMATCH_SEVERITY:
        for recipient_state in CROSSMATCH_SEVERITY:
            worst = max(donor_state, recipient_state, key=CROSSMATCH_SEVERITY.index)
            rows = rank(
                a_recipient("R", crossmatch=recipient_state),
                [a_donor("D-1", crossmatch=donor_state)],
            )
            row = rows[0]
            assert row.explanation["crossmatch_status"] == worst.value, (
                f"a donor recorded {donor_state.value} and a recipient recorded "
                f"{recipient_state.value} were read as "
                f"{row.explanation['crossmatch_status']}: the worse of the two records "
                "decides a pair-level crossmatch"
            )
            assert (row.bucket is Bucket.BLOCKED_POSITIVE_CROSSMATCH) is (
                worst is CrossmatchState.POSITIVE
            ), (
                f"a donor recorded {donor_state.value} and a recipient recorded "
                f"{recipient_state.value} landed in {row.bucket.value}: a POSITIVE on "
                "either side blocks the pair, and nothing else does"
            )


# --- the rankers built to break them --------------------------------------


@dataclass(frozen=True, slots=True)
class _ProfileWithAnUnreadField(Profile):
    """A profile carrying a value the matching core has no name for.

    Used two ways: the honest runs prove the value cannot reach the order, and
    `sells_the_first_position` proves the check would notice if it did.
    """

    unreadable_amount: int = 0


def ignores_the_buckets(anchor: Profile, candidates: Sequence[Profile]) -> list[RankedPair]:
    """Ranks on the HLA heuristic alone, so a blocked pair can reach the top."""
    rows = rank_donors_for(anchor, candidates)
    rows.sort(key=lambda row: (row.key.km_level, row.key.penalty))
    return rows


def reads_unknown_as_zero(anchor: Profile, candidates: Sequence[Profile]) -> list[RankedPair]:
    """Treats an untyped locus as a clean zero mismatch, which is the single
    most dangerous thing this system could do quietly."""

    def optimistic(donor: Profile, recipient: Profile) -> MismatchVector:
        vector = real_build_vector(donor, recipient)
        per_locus = {
            locus: LocusMismatch(MismatchStatus.KNOWN, count=0, lower=0, upper=0, compared_depth=1)
            if mm.status is MismatchStatus.UNKNOWN
            else mm
            for locus, mm in vector.per_locus.items()
        }
        return MismatchVector(per_locus, vector.presence, vector.dq_mode, vector.notes)

    with mock.patch.object(core, "build_vector", optimistic):
        return rank_donors_for(anchor, candidates)


def sells_the_first_position(anchor: Profile, candidates: Sequence[Profile]) -> list[RankedPair]:
    """Reads the field the real matcher cannot see, and sorts by it."""
    paid = {c.profile_id: getattr(c, "unreadable_amount", 0) for c in candidates}
    rows = rank_donors_for(anchor, candidates)
    rows.sort(key=lambda row: (-paid.get(row.candidate_id, 0), row.key.as_tuple()))
    return rows


def rewards_missing_data(anchor: Profile, candidates: Sequence[Profile]) -> list[RankedPair]:
    """Lets a candidate float upwards for every locus it failed to have typed."""
    rows = rank_donors_for(anchor, candidates)
    rows.sort(key=lambda row: (-row.key.unknown_count, row.key.as_tuple()))
    return rows


def answers_differently_each_call() -> Ranker:
    """A ranker whose answer depends on how many times it has been called."""
    calls = count()

    def rank(anchor: Profile, candidates: Sequence[Profile]) -> list[RankedPair]:
        rows = rank_donors_for(anchor, candidates)
        return rows if next(calls) % 2 == 0 else list(reversed(rows))

    return rank


def _worst_count(vector: MismatchVector, locus: str) -> int | None:
    """The conservative end of a locus count, or None when it is unknown."""
    mm = vector.per_locus.get(locus)
    if mm is None or mm.status is MismatchStatus.UNKNOWN:
        return None
    return mm.upper


def charges_nothing_for_an_unknown_locus(vector: MismatchVector, policy: MatchingPolicy) -> int:
    """The tie-breaker as it was before the fix: absence was free.

    Reproduced rather than described, because the defect is not obvious from
    reading it. Every charge is conditional on a count existing, so a locus
    nobody typed costs nothing and deleting a mismatched typing is a saving.
    """
    dr = _worst_count(vector, "DRB1")
    dr_matched = dr == 0
    total = 0
    for locus in policy.scored_loci:
        count_at_locus = _worst_count(vector, locus)
        if count_at_locus is None:
            continue
        total += policy.charge(locus, count_at_locus, dr_matched=dr_matched)
    charge = policy.first_mismatch.get("DRB3_4_5_presence_conflict", 0)
    gate = policy.gate_full if dr_matched else policy.gate_halved
    total += (gate * charge * vector.presence_conflicts()) // 10
    return total


def treats_an_unknown_drb1_as_matched(vector: MismatchVector, policy: MatchingPolicy) -> int:
    """Charges every unknown locus, but reads an untyped DRB1 as an open DR gate."""
    dr = _worst_count(vector, "DRB1")
    dr_matched = dr is None or dr == 0
    total = 0
    for locus in policy.scored_loci:
        count_at_locus = _worst_count(vector, locus)
        total += policy.charge(
            locus,
            ranking.UNKNOWN_AS if count_at_locus is None else count_at_locus,
            dr_matched=dr_matched,
        )
    charge = policy.first_mismatch.get("DRB3_4_5_presence_conflict", 0)
    gate = policy.gate_full if dr_matched else policy.gate_halved
    chargeable = sum(1 for p in vector.presence if p.conflict or p.status is MismatchStatus.UNKNOWN)
    total += (gate * charge * chargeable) // 10
    return total


def charges_nothing_for_absence(anchor: Profile, candidates: Sequence[Profile]) -> list[RankedPair]:
    """Ranks with the tie-breaker as it was, so absence is a discount."""
    with mock.patch.object(ranking, "tiebreaker_penalty", charges_nothing_for_an_unknown_locus):
        return rank_donors_for(anchor, candidates)


def _skips_unknown_evidence(donor: Profile, recipient: Profile, vector: MismatchVector) -> int:
    """The evidence penalty as it was: a locus it could not read cost nothing."""
    cost = {"A": 0, "B": 1, "C": 3}
    worst = max(cost.values())
    total = 0
    for locus, mm in vector.per_locus.items():
        if mm.status is MismatchStatus.UNKNOWN:
            continue
        for side in (donor, recipient):
            total += cost.get((side.tiers.get(locus) or "C").upper(), worst)
    return total


def discounts_unreadable_evidence(
    anchor: Profile, candidates: Sequence[Profile]
) -> list[RankedPair]:
    """Ranks with the old evidence penalty, so deleting a locus is a discount."""
    with mock.patch.object(core, "_evidence_penalty", _skips_unknown_evidence):
        return rank_donors_for(anchor, candidates)


def compares_the_printed_text(anchor: Profile, candidates: Sequence[Profile]) -> list[RankedPair]:
    """Parses every cell without telling it which locus it came from, so a bare
    `04 11` looks foreign to the identical typing stored as `DRB1*04 DRB1*11`."""

    def as_printed(raw: str | None, flag: str | None, *, locus: str = "") -> LocusValue:
        return real_parse_locus_value(raw, flag, locus="")

    with mock.patch.object(core, "parse_locus_value", as_printed):
        return rank_donors_for(anchor, candidates)


def reads_a_garble_as_a_weak_group(
    anchor: Profile, candidates: Sequence[Profile]
) -> list[RankedPair]:
    """Accepts any value in the blood-group field as a group, so an unreadable
    one is merely unmeasured and lands in a ranked bucket."""
    with mock.patch.object(gates, "_both_groups_readable", lambda inputs: True):
        return rank_donors_for(anchor, candidates)


def without_the_anchor_check(rank: Ranker) -> Ranker:
    """The same entry point with the anchor's own role taken on trust."""

    def lenient(anchor: Profile, candidates: Sequence[Profile]) -> list[RankedPair]:
        with mock.patch.object(core, "_require_role", lambda *a, **k: None):
            return rank(anchor, candidates)

    return lenient


def _the_donor_side_wins(donor: Profile, recipient: Profile) -> CrossmatchState:
    """The crossmatch rule as it was: the donor's record unless it is absent."""
    if donor.crossmatch is not CrossmatchState.NOT_PERFORMED:
        return donor.crossmatch
    return recipient.crossmatch


def lets_the_donor_side_mask_the_recipient(
    anchor: Profile, candidates: Sequence[Profile]
) -> list[RankedPair]:
    """Ranks with the old crossmatch rule, so a donor NEGATIVE hides a
    recipient POSITIVE."""
    with mock.patch.object(core, "_worst_crossmatch", _the_donor_side_wins):
        return rank_donors_for(anchor, candidates)


@dataclass(frozen=True, slots=True)
class _ProfileThatWasHandedAnAmount(Profile):
    """What the matching core must never be given."""

    compensation_rial: int = 0


# --- the invariants, against the real ranking ------------------------------


def test_gates_precede_the_hla_heuristic() -> None:
    check_gates_precede_the_hla_heuristic(rank_donors_for)


def test_a_missing_locus_is_unknown_never_zero() -> None:
    check_a_missing_locus_is_unknown_never_zero(rank_donors_for)


def test_an_unknown_locus_is_charged_at_its_worst_case() -> None:
    check_an_unknown_locus_is_charged_at_its_worst_case(ranking.tiebreaker_penalty)


def test_an_unknown_drb1_keeps_the_dr_gate_closed() -> None:
    check_an_unknown_drb1_keeps_the_dr_gate_closed(ranking.tiebreaker_penalty)


def test_an_unestablished_drbx_presence_is_charged_like_a_conflict() -> None:
    check_an_unestablished_drbx_presence_is_charged_like_a_conflict(ranking.tiebreaker_penalty)


def test_the_profile_has_no_compensation_field() -> None:
    check_no_compensation_field(Profile)


def test_an_unread_field_cannot_change_the_order() -> None:
    check_an_unread_field_cannot_change_the_order(rank_donors_for)


def test_the_same_input_gives_the_same_output() -> None:
    check_the_same_input_gives_the_same_output(rank_donors_for)


def test_losing_information_never_improves_a_position() -> None:
    check_losing_information_never_improves_a_position(rank_donors_for)


def test_the_same_typing_written_two_ways_ranks_the_same() -> None:
    check_the_same_typing_written_two_ways_ranks_the_same(rank_donors_for)


def test_an_unreadable_blood_group_never_reaches_a_ranked_bucket() -> None:
    check_an_unreadable_blood_group_never_reaches_a_ranked_bucket(rank_donors_for)


def test_the_anchors_own_role_is_checked() -> None:
    check_the_anchors_own_role_is_checked(rank_donors_for, core.rank_recipients_for)


def test_the_worst_crossmatch_on_either_side_decides() -> None:
    check_the_worst_crossmatch_on_either_side_decides(rank_donors_for)


def test_no_matching_module_imports_compensation() -> None:
    """`scripts/architecture_lint.py` enforces this outside the test suite. It
    is asserted here too so the MATCH-EVAL-001 acceptance run cannot pass while
    the import exists."""
    package = Path(core.__file__).resolve().parent
    modules = sorted(package.rglob("*.py"))
    assert modules, "no matching module was found to inspect"
    for path in modules:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                assert "compensation" not in name, f"{path.name} imports compensation: {name}"


# --- the meta-tests: each checker must fail on a ranker that breaks it ------


def test_the_gate_checker_fails_on_a_ranker_that_ignores_the_buckets() -> None:
    with pytest.raises(AssertionError, match="a blocked pair outranks a ranked one"):
        check_gates_precede_the_hla_heuristic(ignores_the_buckets)


def test_the_unknown_checker_fails_on_a_ranker_that_reads_unknown_as_zero() -> None:
    with pytest.raises(AssertionError, match="UNKNOWN is not 0"):
        check_a_missing_locus_is_unknown_never_zero(reads_unknown_as_zero)


def test_the_worst_case_checker_fails_on_a_tiebreaker_that_charges_nothing() -> None:
    with pytest.raises(AssertionError, match="was not charged at its worst case"):
        check_an_unknown_locus_is_charged_at_its_worst_case(charges_nothing_for_an_unknown_locus)


def test_the_dr_gate_checker_fails_on_a_tiebreaker_that_opens_it_on_absence() -> None:
    with pytest.raises(AssertionError, match="an unknown DRB1 left the DR gate open"):
        check_an_unknown_drb1_keeps_the_dr_gate_closed(treats_an_unknown_drb1_as_matched)


def test_the_presence_checker_fails_on_a_tiebreaker_that_charges_only_conflicts() -> None:
    with pytest.raises(AssertionError, match="whose presence was never established cost"):
        check_an_unestablished_drbx_presence_is_charged_like_a_conflict(
            charges_nothing_for_an_unknown_locus
        )


def test_the_field_checker_fails_on_a_profile_carrying_an_amount() -> None:
    with pytest.raises(AssertionError, match="reads as compensation"):
        check_no_compensation_field(_ProfileThatWasHandedAnAmount)


def test_the_unread_field_checker_fails_on_a_ranker_that_sells_position() -> None:
    with pytest.raises(AssertionError, match="changed the order"):
        check_an_unread_field_cannot_change_the_order(sells_the_first_position)


def test_the_determinism_checker_fails_on_a_ranker_that_answers_differently() -> None:
    with pytest.raises(AssertionError, match="did not give the same order"):
        check_the_same_input_gives_the_same_output(answers_differently_each_call())


def test_the_information_checker_fails_on_a_ranker_that_rewards_missing_data() -> None:
    with pytest.raises(AssertionError, match="improved its position"):
        check_losing_information_never_improves_a_position(rewards_missing_data)


def test_the_information_checker_fails_on_a_ranker_that_discounts_absence() -> None:
    """The defect the position assertion alone could not see: the candidate did
    not move here, its penalty did, and the position it buys is one rival
    away."""
    with pytest.raises(AssertionError, match="lowered the tie-breaker penalty"):
        check_losing_information_never_improves_a_position(charges_nothing_for_absence)


def test_the_information_checker_fails_on_a_ranker_that_discounts_unread_evidence() -> None:
    with pytest.raises(AssertionError, match="lowered the evidence penalty"):
        check_losing_information_never_improves_a_position(discounts_unreadable_evidence)


def test_the_prefix_checker_fails_on_a_ranker_that_compares_the_printed_text() -> None:
    with pytest.raises(AssertionError, match="was read as foreign"):
        check_the_same_typing_written_two_ways_ranks_the_same(compares_the_printed_text)


def test_the_abo_checker_fails_on_a_ranker_that_reads_a_garble_as_a_weak_group() -> None:
    with pytest.raises(AssertionError, match="reached PROVISIONAL_ABO"):
        check_an_unreadable_blood_group_never_reaches_a_ranked_bucket(
            reads_a_garble_as_a_weak_group
        )


def test_the_role_checker_fails_on_a_ranker_that_trusts_its_caller() -> None:
    with pytest.raises(AssertionError, match="the anchor's own role was never checked"):
        check_the_anchors_own_role_is_checked(
            without_the_anchor_check(rank_donors_for),
            without_the_anchor_check(core.rank_recipients_for),
        )


def test_the_crossmatch_checker_fails_on_a_ranker_that_prefers_the_donor_side() -> None:
    with pytest.raises(AssertionError, match="the worse of the two records"):
        check_the_worst_crossmatch_on_either_side_decides(lets_the_donor_side_mask_the_recipient)


# --- adversarial counterexamples -------------------------------------------


def test_a_barely_typed_donor_does_not_outrank_a_fully_typed_one() -> None:
    """The barely typed donor agrees with the recipient everywhere it was read.
    Read optimistically it is a perfect match; read honestly its two single
    alleles are ranges and its other three loci are nothing at all."""
    recipient = a_recipient("R")
    barely = a_donor(
        "D-BARELY-TYPED",
        hla={"B": ("B*07", "UNREAD"), "DRB1": ("DRB1*03", "UNREAD")},
        presence={},
    )
    fully = a_donor(
        "D-FULLY-TYPED",
        hla=edited(REFERENCE, A=("A*01 A*11", "READ"), B=("B*07 B*44", "READ")),
    )

    rows = rank_donors_for(recipient, [barely, fully])
    found = by_id(rows)

    assert found["D-BARELY-TYPED"].key.partial_count > 0
    assert found["D-BARELY-TYPED"].key.unknown_count > 0
    assert found["D-FULLY-TYPED"].key.unknown_count == 0
    assert order_of(rows) == ["D-FULLY-TYPED", "D-BARELY-TYPED"], (
        "a donor with two half-read loci and three untyped ones outranked a donor "
        "typed at every locus with two real mismatches"
    )


@pytest.mark.parametrize(
    ("group", "provenance", "expected"),
    [
        (None, AboProvenance.UNKNOWN, Bucket.INSUFFICIENT_ABO),
        ("O", REPORTED, Bucket.PROVISIONAL_ABO),
        ("O", CAPTION, Bucket.PROVISIONAL_ABO),
        ("O", AboProvenance.UNKNOWN, Bucket.PROVISIONAL_ABO),
        ("not-a-group", MEASURED, Bucket.INSUFFICIENT_ABO),
        ("O+", MEASURED, Bucket.INSUFFICIENT_ABO),
        ("   ", MEASURED, Bucket.INSUFFICIENT_ABO),
        ("0", MEASURED, Bucket.INSUFFICIENT_ABO),
    ],
)
def test_an_abo_that_cannot_clear_never_reaches_ranked(
    group: str | None, provenance: AboProvenance, expected: Bucket
) -> None:
    """A perfect HLA match does not buy a clearance the blood group cannot give.
    KI-014: the dominant letterhead disclaims its own blood-group field on 2,928
    documents, and a group carrying that disclaimer may exclude a pair but never
    clear one.

    The two failures are different sizes and the buckets say so. A real group
    from a weak source is PROVISIONAL_ABO, which is ranked and carries the
    action "obtain a laboratory blood group". A value that is not a group at all
    is INSUFFICIENT_ABO and is not ranked, however it was measured: an Rh string
    or an OCR garble supports no compatibility claim to weaken."""
    recipient = a_recipient("R")
    donor = a_donor("D-UNCLEARED", abo=group, provenance=provenance)

    rows = rank_donors_for(recipient, [donor])
    row = rows[0]

    assert row.key.km_level == 1, "the fixture must hold a perfect HLA match to be adversarial"
    assert row.bucket is not Bucket.RANKED, (
        f"a blood group of provenance {provenance.value} reached RANKED"
    )
    assert row.bucket is expected
    assert row.bucket.is_ranked is (expected is Bucket.PROVISIONAL_ABO), (
        f"a blood group stored as {group!r} landed in {row.bucket.value}, which is on the "
        "wrong side of the ranked line"
    )


def test_an_unclearable_abo_sorts_below_a_worse_but_cleared_donor() -> None:
    recipient = a_recipient("R")
    unclearable = a_donor("D-PERFECT-UNCLEARED", provenance=REPORTED)
    cleared = a_donor(
        "D-WORSE-CLEARED",
        hla=edited(REFERENCE, DRB1=("DRB1*11 DRB1*13", "READ"), B=("B*15 B*44", "READ")),
    )

    rows = rank_donors_for(recipient, [unclearable, cleared])
    assert order_of(rows) == ["D-WORSE-CLEARED", "D-PERFECT-UNCLEARED"]


def test_a_positive_crossmatch_stops_a_perfect_hla_match() -> None:
    """The crossmatch is a laboratory finding about these two people. No HLA
    level reaches past it, and the pair leaves the ranked list rather than
    sitting at the bottom of it."""
    recipient = a_recipient("R")
    blocked = a_donor("D-PERFECT-POSITIVE-XM", crossmatch=CrossmatchState.POSITIVE)
    cleared = a_donor(
        "D-WORSE-NEGATIVE-XM",
        hla=edited(REFERENCE, DRB1=("DRB1*11 DRB1*13", "READ"), B=("B*15 B*44", "READ")),
        crossmatch=CrossmatchState.NEGATIVE,
    )

    rows = rank_donors_for(recipient, [blocked, cleared])
    found = by_id(rows)
    stopped = found["D-PERFECT-POSITIVE-XM"]

    assert stopped.key.km_level == 1, "the blocked pair must hold a perfect HLA match"
    assert stopped.bucket is Bucket.BLOCKED_POSITIVE_CROSSMATCH
    assert stopped.bucket.is_ranked is False
    assert order_of(rows) == ["D-WORSE-NEGATIVE-XM", "D-PERFECT-POSITIVE-XM"]
    assert any("crossmatch" in blocker for blocker in stopped.decision.blockers)
    assert stopped.explanation["next_clinical_action"] == "direct pathway blocked"


def test_a_recipient_side_positive_crossmatch_is_not_masked_by_the_donor() -> None:
    """The counterexample the pair-level rule was written from: the donor's own
    record is NEGATIVE, and reading it alone presented a pair a laboratory had
    already stopped as ranked and cleared."""
    recipient = a_recipient("R", crossmatch=CrossmatchState.POSITIVE)
    donor = a_donor("D-DONOR-SIDE-NEGATIVE", crossmatch=CrossmatchState.NEGATIVE)

    row = rank_donors_for(recipient, [donor])[0]

    assert row.bucket is Bucket.BLOCKED_POSITIVE_CROSSMATCH
    assert row.bucket.is_ranked is False
    assert row.explanation["crossmatch_status"] == CrossmatchState.POSITIVE.value
    assert any("crossmatch" in blocker for blocker in row.decision.blockers)

    back = core.rank_recipients_for(donor, [recipient])[0]
    assert back.bucket is Bucket.BLOCKED_POSITIVE_CROSSMATCH, (
        "the pair is blocked from whichever side it is looked at"
    )


def test_two_b_mismatches_with_a_matched_dr_beat_one_dr_mismatch() -> None:
    """The re-cut that separates this scheme from the UK levels. A flat
    per-mismatch score gets this backwards: the donor that wins here carries
    more mismatches, and a single DR incompatibility abolished the class I
    matching benefit across 39,205 Eurotransplant transplants."""
    recipient = a_recipient("R")
    two_b = a_donor("D-2B-0DR", hla=edited(REFERENCE, B=("B*15 B*44", "READ")))
    one_dr = a_donor("D-0B-1DR", hla=edited(REFERENCE, DRB1=("DRB1*03 DRB1*11", "READ")))

    rows = rank_donors_for(recipient, [two_b, one_dr])
    found = by_id(rows)

    assert found["D-2B-0DR"].vector.per_locus["B"].count == 2
    assert found["D-2B-0DR"].vector.per_locus["DRB1"].count == 0
    assert found["D-0B-1DR"].vector.per_locus["B"].count == 0
    assert found["D-0B-1DR"].vector.per_locus["DRB1"].count == 1
    assert found["D-2B-0DR"].key.km_level == 3
    assert found["D-0B-1DR"].key.km_level == 4
    assert order_of(rows) == ["D-2B-0DR", "D-0B-1DR"], (
        "the donor with more total mismatches but a matched DRB1 must rank first"
    )


def test_a_genotype_tie_is_broken_by_the_stable_hash_the_same_way_every_time() -> None:
    """1,974 profiles share a genotype with another profile. Without a stable
    last position their order would follow dictionary iteration, and two readers
    of the same pack would see different lists."""
    recipient = a_recipient("R")
    twins = [a_donor("D-TWIN-A"), a_donor("D-TWIN-B")]

    rows = rank_donors_for(recipient, twins)
    first, second = rows

    assert first.key.as_tuple()[:-1] == second.key.as_tuple()[:-1], (
        "the fixture must be a genuine tie for the hash to be what breaks it"
    )
    assert first.key.stable_hash != second.key.stable_hash

    again = rank_donors_for(recipient, twins)
    reversed_input = rank_donors_for(recipient, list(reversed(twins)))
    assert order_of(rows) == order_of(again)
    assert order_of(rows) == order_of(reversed_input), (
        "the tie broke differently when the candidates arrived in a different order"
    )


def test_the_stable_hash_moves_with_the_identifiers_and_nothing_else() -> None:
    """The final tiebreak is over the ordered pair of identifiers and the policy
    version. A hash that also moved with a profile's contents would be a second,
    unexplained ranking signal."""
    recipient = a_recipient("R")
    plain = a_donor("D-SAME-ID")
    rewritten = a_donor("D-SAME-ID", hla=edited(REFERENCE, DRB1=("DRB1*11 DRB1*13", "READ")))

    one = rank_donors_for(recipient, [plain])[0]
    other = rank_donors_for(recipient, [rewritten])[0]

    assert one.key.stable_hash == other.key.stable_hash
    assert one.key.km_level != other.key.km_level


def test_a_role_unknown_profile_appears_in_neither_direction() -> None:
    """2,026 profiles have no established role. Treating one as either party
    would be an inference the matcher may not make."""
    recipient = a_recipient("R")
    roleless = a_roleless_profile()

    rows = rank_donors_for(recipient, [roleless, a_donor("D-1")])
    assert order_of(rows) == ["D-1"]

    donor = a_donor("D-1")
    back = core.rank_recipients_for(donor, [roleless, a_recipient("R-1")])
    assert order_of(back) == ["R-1"]
