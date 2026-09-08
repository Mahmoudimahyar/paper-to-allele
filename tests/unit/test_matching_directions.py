"""Both ranking directions, and the asymmetry that makes them two questions.

`MATCH-001`. Policy: `docs/clinical/MATCHING_POLICY_V2.md` sections 3.1 and 3.2.

A kidney pre-screen counts host versus graft: the donor's distinct alleles that
the recipient lacks. That count is not symmetric, so `rank(donors | recipient)`
and `rank(recipients | donor)` are two different questions about the same two
people, not one question read from either end. The cheapest way to get this
wrong is to transpose the mismatch arguments to serve the second direction and
call it done. A homozygous profile is where a transposition shows itself,
because it collapses to one distinct allele when it is the donor and offers no
cover at all when it is the recipient, so the concrete pair is asserted here
against `build_vector` and then again against both public entry points.

The remaining tests guard the boundary around that count. A profile whose role
was never established is an inference the matcher may not make, so it is offered
to neither direction and refused as an anchor. A donor is never listed as
somebody's recipient, and a donor handed in where a recipient is expected is
refused rather than read backwards. An anchor is never ranked against itself,
including against a record carrying its own identifier under the other role. The
explanation names the anchor and the candidate the right way round, because a row
read the wrong way round has every mismatch count backwards. A crossmatch belongs
to the pair rather than to whichever party anchors the query, so the worse of the
two records is the one reported in either direction. And the order follows the
sort key rather than the order the candidates happened to arrive in, which is the
property that lets two runs of one query be compared at all, and which no
candidate may improve by losing a typing.
"""

from __future__ import annotations

import random
from dataclasses import replace

import pytest

from kidneymatch.matching.abo import AboProvenance
from kidneymatch.matching.core import (
    Direction,
    MatchingNotImplemented,
    Profile,
    RankedPair,
    Role,
    RoleMismatch,
    build_vector,
    rank_candidates,
    rank_donors_for,
    rank_recipients_for,
)
from kidneymatch.matching.gates import Bucket, CrossmatchState
from kidneymatch.matching.mismatch import MismatchStatus

pytestmark = pytest.mark.task("MATCH-001")

MEASURED = AboProvenance.LABORATORY_MEASURED

#: Two synthetic genotypes that differ at A and B and agree at DRB1 and DQB1, so
#: the only thing the direction can change is the class I count. Every allele
#: string in this file is invented; no archive value appears here.
HOMOZYGOUS = {"a": "A*02 A*02", "b": "B*07 B*07"}
HETEROZYGOUS = {"a": "A*01 A*03", "b": "B*08 B*15"}


def _flag(raw: str) -> str:
    """The stored `second_allele` status that agrees with the stored value."""
    return "READ" if len(raw.split()) == 2 else "UNREAD"


def make_profile(
    profile_id: str,
    role: Role,
    *,
    a: str | None = "A*01 A*03",
    b: str | None = "B*08 B*15",
    c: str | None = None,
    drb1: str | None = "DRB1*04 DRB1*11",
    dqb1: str | None = "DQB1*03 DQB1*05",
    abo: str | None = "O",
) -> Profile:
    """A synthetic profile, typed well enough to reach the RANKED bucket."""
    hla: dict[str, tuple[str | None, str | None]] = {
        locus: (raw, _flag(raw))
        for locus, raw in (("A", a), ("B", b), ("C", c), ("DRB1", drb1), ("DQB1", dqb1))
        if raw is not None
    }
    return Profile(
        profile_id=profile_id,
        role=role,
        hla=hla,
        abo=abo,
        abo_provenance=MEASURED,
    )


def ids(rows: list[RankedPair]) -> list[str]:
    return [row.candidate_id for row in rows]


def donor_pool() -> list[Profile]:
    """A mixed pool: an identical donor, a genotype tie, a partial, two gated."""
    return [
        make_profile("D-identical", Role.DONOR),
        make_profile("D-tie-one", Role.DONOR, a="A*02 A*11", b="B*07 B*44", drb1="DRB1*01 DRB1*13"),
        make_profile("D-tie-two", Role.DONOR, a="A*02 A*11", b="B*07 B*44", drb1="DRB1*01 DRB1*13"),
        make_profile("D-dr-matched", Role.DONOR, a="A*02 A*11", b="B*08 B*44"),
        make_profile("D-partial-a", Role.DONOR, a="A*24"),
        make_profile("D-untyped-drb1", Role.DONOR, drb1=None),
        make_profile("D-wrong-group", Role.DONOR, abo="A"),
    ]


def recipient_pool() -> list[Profile]:
    """The mirror pool for the other direction, anchored on a group A donor."""
    return [
        make_profile("R-identical", Role.RECIPIENT, abo="A"),
        make_profile(
            "R-tie-one",
            Role.RECIPIENT,
            a="A*02 A*11",
            b="B*07 B*44",
            drb1="DRB1*01 DRB1*13",
            abo="AB",
        ),
        make_profile(
            "R-tie-two",
            Role.RECIPIENT,
            a="A*02 A*11",
            b="B*07 B*44",
            drb1="DRB1*01 DRB1*13",
            abo="AB",
        ),
        make_profile("R-dr-matched", Role.RECIPIENT, a="A*02 A*11", b="B*08 B*44", abo="A"),
        make_profile("R-partial-a", Role.RECIPIENT, a="A*24", abo="AB"),
        make_profile("R-untyped-drb1", Role.RECIPIENT, drb1=None, abo="A"),
        make_profile("R-wrong-group", Role.RECIPIENT, abo="O"),
    ]


# --- both directions run --------------------------------------------------


def test_both_directions_return_ranked_pair_rows() -> None:
    """The roadmap asks for donors-for-a-recipient; the operator asks for both."""
    recipient = make_profile("R-anchor", Role.RECIPIENT)
    donor = make_profile("D-anchor", Role.DONOR)

    forwards = rank_donors_for(recipient, [donor])
    backwards = rank_recipients_for(donor, [recipient])

    for rows in (forwards, backwards):
        assert len(rows) == 1
        assert isinstance(rows[0], RankedPair)
        assert rows[0].donor_id == "D-anchor"
        assert rows[0].recipient_id == "R-anchor"
        assert rows[0].bucket is Bucket.RANKED
        assert rows[0].key.bucket_rank == Bucket.RANKED.rank

    assert forwards[0].explanation["direction"] == Direction.DONORS_FOR_RECIPIENT.value
    assert backwards[0].explanation["direction"] == Direction.RECIPIENTS_FOR_DONOR.value


# --- the asymmetry --------------------------------------------------------


def test_a_homozygous_donor_counts_one_where_the_swap_counts_two() -> None:
    """The worked example from policy section 3.2, asserted on the vector itself.

    A donor carrying `A*02` twice presents one distinct allele, and a recipient
    with neither copy of it lacks exactly that one. Read the other way round,
    the heterozygous side presents two alleles and the homozygous side covers
    neither. One pair, two counts, because the count is host versus graft.
    """
    homozygous = make_profile("P-hom", Role.DONOR, **HOMOZYGOUS)
    heterozygous = make_profile("P-het", Role.RECIPIENT, **HETEROZYGOUS)

    forwards = build_vector(homozygous, heterozygous).per_locus["A"]
    backwards = build_vector(heterozygous, homozygous).per_locus["A"]

    assert forwards.status is MismatchStatus.KNOWN
    assert forwards.count == 1
    assert backwards.status is MismatchStatus.KNOWN
    assert backwards.count == 2
    assert forwards.count != backwards.count, "a transposed count would make these equal"


@pytest.mark.parametrize(
    ("donor_alleles", "recipient_alleles", "expected"),
    [
        ("A*02 A*11", "A*01 A*03", 2),
        ("A*02 A*11", "A*02 A*03", 1),
        ("A*02 A*11", "A*02 A*11", 0),
        ("A*02 A*02", "A*02 A*03", 0),
        ("A*02 A*02", "A*01 A*03", 1),
        ("A*02 A*11", "A*02 A*02", 1),
        ("A*02 A*02", "A*02 A*02", 0),
    ],
)
def test_the_worked_examples_from_the_policy_table(
    donor_alleles: str, recipient_alleles: str, expected: int
) -> None:
    """Policy section 3.2's table, checked line by line rather than in prose."""
    donor = make_profile("P-d", Role.DONOR, a=donor_alleles)
    recipient = make_profile("P-r", Role.RECIPIENT, a=recipient_alleles)
    assert build_vector(donor, recipient).per_locus["A"].count == expected


def test_the_two_directions_disagree_about_the_same_two_genotypes() -> None:
    """The asymmetry has to survive the trip through the public entry points.

    The same two genotypes are ranked twice with the roles swapped. Homozygous
    as the donor, the pair is one A and one B mismatch and reaches KM-2;
    homozygous as the recipient, the same genotypes are two and two and reach
    KM-3. A ranker that transposed its arguments would return one level twice.
    """
    hom_donor = make_profile("G-hom", Role.DONOR, **HOMOZYGOUS)
    het_recipient = make_profile("G-het", Role.RECIPIENT, **HETEROZYGOUS)
    het_donor = make_profile("G-het", Role.DONOR, **HETEROZYGOUS)
    hom_recipient = make_profile("G-hom", Role.RECIPIENT, **HOMOZYGOUS)

    forwards = rank_donors_for(het_recipient, [hom_donor])[0]
    backwards = rank_recipients_for(het_donor, [hom_recipient])[0]

    assert forwards.vector.per_locus["A"].count == 1
    assert forwards.vector.per_locus["B"].count == 1
    assert backwards.vector.per_locus["A"].count == 2
    assert backwards.vector.per_locus["B"].count == 2

    assert forwards.explanation["km_level"] == 2
    assert backwards.explanation["km_level"] == 3
    assert forwards.key.km_level != backwards.key.km_level


# --- who may be offered to whom -------------------------------------------


def test_a_role_unknown_profile_appears_in_neither_direction() -> None:
    """2,026 profiles have no established role. Treating one as either party is
    an inference the matcher may not make; establishing a role is a review
    action, not a default."""
    unknown = make_profile("X-no-role", Role.UNKNOWN)
    recipient = make_profile("R-anchor", Role.RECIPIENT)
    donor = make_profile("D-anchor", Role.DONOR)

    assert ids(rank_donors_for(recipient, [unknown, donor])) == ["D-anchor"]
    assert ids(rank_recipients_for(donor, [unknown, recipient])) == ["R-anchor"]


def test_a_role_unknown_profile_is_not_an_anchor_either() -> None:
    """Policy section 4.3: role-UNKNOWN profiles are "excluded from both
    directions" and "never silently treated as either party".

    Filtering the candidate list alone left the anchor side open: ranking donors
    for a profile whose role was never established returned a clean KM-1 result
    page, which is the platform asserting that this person is a recipient. It is
    the same profile population on either side of the query, so the refusal is
    now explicit rather than a matter of what happens to be left in the list, and
    it fires on the anchor before any candidate is read: an empty pool is refused
    exactly as loudly as a full one.
    """
    unknown = make_profile("X-no-role", Role.UNKNOWN)
    donor_pools: list[list[Profile]] = [[], [make_profile("D-ok", Role.DONOR)]]
    recipient_pools: list[list[Profile]] = [[], [make_profile("R-ok", Role.RECIPIENT)]]

    for donors in donor_pools:
        with pytest.raises(RoleMismatch, match="X-no-role"):
            rank_donors_for(unknown, donors)

    for recipients in recipient_pools:
        with pytest.raises(RoleMismatch, match="X-no-role"):
            rank_recipients_for(unknown, recipients)


def test_an_anchor_of_the_wrong_role_is_refused_in_each_direction() -> None:
    """A donor asked for its donors is not a query with a typo in it.

    Every row of that answer would read host against graft the wrong way round,
    and the count is not symmetric, so the numbers would be wrong rather than
    merely oddly labelled. The refusal names the profile and the role the call
    required, so an operator can see which way round the call was made, and it is
    a `ValueError` so that a caller validating its inputs catches it alongside
    the rest of them rather than with a bare `except`.
    """
    assert issubclass(RoleMismatch, ValueError)

    donor = make_profile("D-anchor", Role.DONOR)
    recipient = make_profile("R-anchor", Role.RECIPIENT)

    with pytest.raises(RoleMismatch) as forwards:
        rank_donors_for(donor, [make_profile("D-ok", Role.DONOR)])
    assert "D-anchor" in str(forwards.value)
    assert "RECIPIENT" in str(forwards.value)

    with pytest.raises(RoleMismatch) as backwards:
        rank_recipients_for(recipient, [make_profile("R-ok", Role.RECIPIENT)])
    assert "R-anchor" in str(backwards.value)
    assert "DONOR" in str(backwards.value)


def test_a_donor_is_never_offered_as_a_recipient() -> None:
    donor_anchor = make_profile("D-anchor", Role.DONOR)
    other_donor = make_profile("D-other", Role.DONOR)
    recipient = make_profile("R-ok", Role.RECIPIENT)

    assert ids(rank_recipients_for(donor_anchor, [other_donor, recipient])) == ["R-ok"]


def test_a_recipient_is_never_offered_as_a_donor() -> None:
    recipient_anchor = make_profile("R-anchor", Role.RECIPIENT)
    other_recipient = make_profile("R-other", Role.RECIPIENT)
    donor = make_profile("D-ok", Role.DONOR)

    assert ids(rank_donors_for(recipient_anchor, [other_recipient, donor])) == ["D-ok"]


def test_the_anchor_is_never_ranked_against_itself() -> None:
    """A profile is a photograph, not a person, and the same identifier can turn
    up under the other role in a candidate list. Self-matching would put a
    guaranteed KM-1 at the top of every result page."""
    recipient_anchor = make_profile("P-shared", Role.RECIPIENT)
    donor_twin = make_profile("P-shared", Role.DONOR)
    real_donor = make_profile("D-real", Role.DONOR)

    assert ids(rank_donors_for(recipient_anchor, [donor_twin, real_donor, recipient_anchor])) == [
        "D-real"
    ]

    donor_anchor = make_profile("P-shared", Role.DONOR)
    recipient_twin = make_profile("P-shared", Role.RECIPIENT)
    real_recipient = make_profile("R-real", Role.RECIPIENT)

    assert ids(
        rank_recipients_for(donor_anchor, [recipient_twin, real_recipient, donor_anchor])
    ) == ["R-real"]


# --- the explanation names the right two people ---------------------------


def test_the_explanation_names_the_anchor_and_the_candidate_in_each_direction() -> None:
    """Read the wrong way round, every mismatch count in the row is backwards."""
    recipient = make_profile("R-anchor", Role.RECIPIENT)
    donor = make_profile("D-candidate", Role.DONOR)

    forwards = rank_donors_for(recipient, [donor])[0]
    assert forwards.explanation["anchor_id"] == "R-anchor"
    assert forwards.explanation["candidate_id"] == "D-candidate"
    assert forwards.explanation["donor_id"] == "D-candidate"
    assert forwards.explanation["recipient_id"] == "R-anchor"
    assert forwards.candidate_id == "D-candidate"

    donor_anchor = make_profile("D-anchor", Role.DONOR)
    recipient_candidate = make_profile("R-candidate", Role.RECIPIENT)

    backwards = rank_recipients_for(donor_anchor, [recipient_candidate])[0]
    assert backwards.explanation["anchor_id"] == "D-anchor"
    assert backwards.explanation["candidate_id"] == "R-candidate"
    assert backwards.explanation["donor_id"] == "D-anchor"
    assert backwards.explanation["recipient_id"] == "R-candidate"
    assert backwards.candidate_id == "R-candidate"


def test_every_row_names_its_own_anchor_across_a_mixed_pool() -> None:
    """Including the gated rows: a blocked pair still has to say who it is about."""
    recipient = make_profile("R-anchor", Role.RECIPIENT)
    pool = donor_pool()
    rows = rank_donors_for(recipient, pool)

    assert len(rows) == len(pool)
    for row in rows:
        assert row.explanation["anchor_id"] == "R-anchor"
        assert row.explanation["candidate_id"] == row.donor_id
        assert row.recipient_id == "R-anchor"


# --- the crossmatch belongs to the pair, not to the anchor ----------------


@pytest.mark.parametrize("positive_side", ["donor", "recipient"])
def test_a_positive_crossmatch_on_either_side_blocks_in_both_directions(
    positive_side: str,
) -> None:
    """A crossmatch is a property of two people, so neither record may hide the
    other.

    An earlier version read the donor's state and fell back to the recipient's
    only when the donor had none recorded, which let a donor-side NEGATIVE mask a
    recipient-side POSITIVE: the pair was published as RANKED with a crossmatch
    status of NEGATIVE, which is a blocked pair presented for clinical
    evaluation. The control run pins that the pair blocks on the crossmatch and
    on nothing else.
    """
    negative = CrossmatchState.NEGATIVE
    donor = replace(make_profile("D-xm", Role.DONOR), crossmatch=negative)
    recipient = replace(make_profile("R-xm", Role.RECIPIENT), crossmatch=negative)

    control = rank_donors_for(recipient, [donor])[0]
    assert control.bucket is Bucket.RANKED
    assert control.explanation["crossmatch_status"] == negative.value

    if positive_side == "donor":
        donor = replace(donor, crossmatch=CrossmatchState.POSITIVE)
    else:
        recipient = replace(recipient, crossmatch=CrossmatchState.POSITIVE)

    forwards = rank_donors_for(recipient, [donor])[0]
    backwards = rank_recipients_for(donor, [recipient])[0]
    for row in (forwards, backwards):
        assert row.explanation["crossmatch_status"] == CrossmatchState.POSITIVE.value
        assert row.bucket is Bucket.BLOCKED_POSITIVE_CROSSMATCH
        assert not row.bucket.is_ranked
        assert any("crossmatch" in blocker for blocker in row.decision.blockers)


@pytest.mark.parametrize(
    ("one", "other", "expected"),
    [
        (CrossmatchState.NEGATIVE, CrossmatchState.POSITIVE, CrossmatchState.POSITIVE),
        (CrossmatchState.NEGATIVE, CrossmatchState.INDETERMINATE, CrossmatchState.INDETERMINATE),
        (CrossmatchState.NEGATIVE, CrossmatchState.EXPIRED, CrossmatchState.EXPIRED),
        (CrossmatchState.NEGATIVE, CrossmatchState.NOT_PERFORMED, CrossmatchState.NOT_PERFORMED),
        (CrossmatchState.EXPIRED, CrossmatchState.INDETERMINATE, CrossmatchState.INDETERMINATE),
        (CrossmatchState.NEGATIVE, CrossmatchState.NEGATIVE, CrossmatchState.NEGATIVE),
    ],
)
def test_the_reported_crossmatch_is_the_worse_of_the_two_records(
    one: CrossmatchState, other: CrossmatchState, expected: CrossmatchState
) -> None:
    """Only POSITIVE blocks today, so the rest of the ladder is visible only in
    the explanation, and it still may not be flattered.

    A row reporting NEGATIVE where one side has no valid crossmatch at all tells
    its reader that a test stands which does not. The severity ladder runs
    NEGATIVE, NOT_PERFORMED, EXPIRED, INDETERMINATE, POSITIVE, and which side
    holds which state cannot matter, so each pair is asserted both ways round.
    """
    for donor_state, recipient_state in ((one, other), (other, one)):
        donor = replace(make_profile("D-xm", Role.DONOR), crossmatch=donor_state)
        recipient = replace(make_profile("R-xm", Role.RECIPIENT), crossmatch=recipient_state)

        forwards = rank_donors_for(recipient, [donor])[0]
        backwards = rank_recipients_for(donor, [recipient])[0]
        assert forwards.explanation["crossmatch_status"] == expected.value
        assert backwards.explanation["crossmatch_status"] == expected.value


# --- the order comes from the sort key, not from the input order ----------


def _permutations(profiles: list[Profile], seed: int, count: int = 6) -> list[list[Profile]]:
    rng = random.Random(seed)
    return [rng.sample(profiles, len(profiles)) for _ in range(count)]


def test_the_donor_order_is_identical_across_input_permutations() -> None:
    """Two runs of one query must be comparable, so nothing about the order may
    depend on the order the candidates arrived in. The pool holds two profiles
    with an identical genotype, so the stable hash is genuinely load-bearing
    here rather than decorative."""
    recipient = make_profile("R-anchor", Role.RECIPIENT)
    expected = ids(rank_donors_for(recipient, donor_pool()))
    shuffles = _permutations(donor_pool(), seed=20260908)

    for shuffled in shuffles:
        assert ids(rank_donors_for(recipient, shuffled)) == expected

    assert any([p.profile_id for p in perm] != expected for perm in shuffles), (
        "every permutation already matched the ranked order, so this test would "
        "also pass against an implementation that returned its input unsorted"
    )


def test_the_recipient_order_is_identical_across_input_permutations() -> None:
    donor = make_profile("D-anchor", Role.DONOR, abo="A")
    expected = ids(rank_recipients_for(donor, recipient_pool()))
    shuffles = _permutations(recipient_pool(), seed=20260907)

    for shuffled in shuffles:
        assert ids(rank_recipients_for(donor, shuffled)) == expected

    assert any([p.profile_id for p in perm] != expected for perm in shuffles)


@pytest.mark.parametrize(
    ("typed", "erased", "strictly_worse"),
    [
        (
            make_profile("D-typed", Role.DONOR, dqb1="DQB1*03 DQB1*06"),
            make_profile("D-erased", Role.DONOR, dqb1=None),
            True,
        ),
        (
            make_profile("D-typed", Role.DONOR, a="A*01 A*24"),
            make_profile("D-erased", Role.DONOR, a=None),
            False,
        ),
    ],
    ids=["dqb1-also-carries-a-second-mismatch-charge", "a-carries-a-first-charge-only"],
)
def test_erasing_a_typing_never_moves_a_candidate_up_the_page(
    typed: Profile, erased: Profile, strictly_worse: bool
) -> None:
    """Losing evidence may not be rewarded, and a result page is read top down.

    Each pair of donors here shares a genotype except that one carries a typed
    locus with a single mismatch and the other has nothing recorded there at all.
    Both reach the same bucket and the same KM level, so the tie-breaker decides
    which is read first. While an unknown locus was charged nothing, the untyped
    donor won that comparison: the penalty is compared at position 3 of the sort
    tuple and the unknown count only at position 5, so the count that was meant
    to answer for the missing locus is never reached. An unknown locus is now
    charged at its worst case, which at DQB1 is strictly dearer than the one
    mismatch it replaces and at HLA-A, where the policy prices no second
    mismatch, is exactly as dear. Never cheaper is the invariant; the order is
    then settled by the unknown count, which the deletion also worsens.
    """
    recipient = make_profile("R-anchor", Role.RECIPIENT)
    rows = rank_donors_for(recipient, [erased, typed])
    assert ids(rows) == ["D-typed", "D-erased"]

    by_id = {row.candidate_id: row for row in rows}
    assert by_id["D-erased"].bucket is by_id["D-typed"].bucket
    assert by_id["D-erased"].key.km_level == by_id["D-typed"].key.km_level
    assert set(by_id["D-erased"].vector.unknown_loci()) > set(
        by_id["D-typed"].vector.unknown_loci()
    )

    assert by_id["D-erased"].key.penalty >= by_id["D-typed"].key.penalty
    if strictly_worse:
        assert by_id["D-erased"].key.penalty > by_id["D-typed"].key.penalty
    assert by_id["D-erased"].key.evidence_penalty >= by_id["D-typed"].key.evidence_penalty
    assert by_id["D-erased"].key.unknown_count > by_id["D-typed"].key.unknown_count
    assert by_id["D-erased"].key.as_tuple() > by_id["D-typed"].key.as_tuple()


def test_the_gated_rows_never_interleave_with_the_ranked_ones() -> None:
    """A blocked pair is not a low-ranked pair, and the bucket leads the sort
    tuple, so a gated row can never appear inside the ranked section."""
    recipient = make_profile("R-anchor", Role.RECIPIENT)
    donor = make_profile("D-anchor", Role.DONOR, abo="A")

    for rows in (
        rank_donors_for(recipient, donor_pool()),
        rank_recipients_for(donor, recipient_pool()),
    ):
        ranks = [row.bucket.rank for row in rows]
        assert ranks == sorted(ranks)
        assert rows[0].bucket is Bucket.RANKED
        assert rows[-1].bucket is not Bucket.RANKED


# --- what build_vector carries besides the five counts ---------------------


@pytest.mark.parametrize("side", ["donor", "recipient"])
@pytest.mark.parametrize("gene", ["DRB3", "DRB4", "DRB5"])
def test_a_drbx_gene_awaiting_review_is_unknown_rather_than_absent(gene: str, side: str) -> None:
    """A DRB3/4/5 row a human still has to resolve is not a gene established as
    absent. Reading it as absent would be the flattering direction twice over:
    it removes a possible conflict from the tie-breaker, and it does so on the
    strength of a record that has been marked as not yet readable. It is
    UNKNOWN, which the tie-breaker charges."""
    established = {"DRB3": "PRESENT", "DRB4": "ABSENT", "DRB5": "ABSENT"}
    pending = {**established, gene: "REVIEW_REQUIRED"}
    donor = make_profile("D-1", Role.DONOR)
    recipient = make_profile("R-1", Role.RECIPIENT)
    if side == "donor":
        donor = replace(donor, presence=pending, tiers={})
        recipient = replace(recipient, presence=established, tiers={})
    else:
        donor = replace(donor, presence=established, tiers={})
        recipient = replace(recipient, presence=pending, tiers={})

    by_gene = {p.gene: p for p in build_vector(donor, recipient).presence}
    assert by_gene[gene].status is MismatchStatus.UNKNOWN
    assert by_gene[gene].reason == "review required"
    assert by_gene[gene].conflict is False, "unknown is not a conflict, it is a gap"
    others = [name for name in ("DRB3", "DRB4", "DRB5") if name != gene]
    assert all(by_gene[name].status is MismatchStatus.KNOWN for name in others), (
        "one gene under review must not make the other two unknown"
    )


def test_a_review_required_drbx_outranks_a_plain_unknown_in_the_reason_given() -> None:
    """Both are UNKNOWN and both are charged the same, but the reasons differ
    and a reviewer acts on them differently: one is a row to repair, the other
    is a test to order."""
    typed = {"DRB3": "PRESENT", "DRB4": "ABSENT", "DRB5": "ABSENT"}
    donor = replace(make_profile("D-1", Role.DONOR), presence={**typed, "DRB3": "REVIEW"})
    never = replace(make_profile("R-1", Role.RECIPIENT), presence={"DRB4": "ABSENT"})
    reasons = {p.gene: p.reason for p in build_vector(donor, never).presence}
    assert reasons["DRB3"] == "review required"
    assert reasons["DRB5"] == "presence not established"


def test_dqa1_typed_on_both_sides_is_reported_and_still_not_compared() -> None:
    """Section 4: a DQ heterodimer needs two-field typing on both chains with
    unambiguous phase, which this archive does not have. Silently ignoring a
    typed DQA1 would leave an operator believing DQ was compared in full, so the
    vector says the typing was seen and says why DQB1 alone decided it."""
    dqa1: dict[str, tuple[str | None, str | None]] = {"DQA1": ("DQA1*01 DQA1*05", "READ")}
    donor = make_profile("D-1", Role.DONOR)
    recipient = make_profile("R-1", Role.RECIPIENT)
    both_typed = build_vector(
        replace(donor, hla={**donor.hla, **dqa1}),
        replace(recipient, hla={**recipient.hla, **dqa1}),
    )
    assert both_typed.dq_mode == "DQB1_ONLY"
    assert any("heterodimer" in note for note in both_typed.notes)
    assert "DQA1" not in both_typed.per_locus, "a note is not a comparison"


@pytest.mark.parametrize("side", ["donor", "recipient"])
def test_dqa1_on_one_side_only_says_nothing(side: str) -> None:
    """A heterodimer comparison needs both chains on both people, so one typed
    side is not a comparison that was declined, it is nothing to decline."""
    dqa1: dict[str, tuple[str | None, str | None]] = {"DQA1": ("DQA1*01 DQA1*05", "READ")}
    donor = make_profile("D-1", Role.DONOR)
    recipient = make_profile("R-1", Role.RECIPIENT)
    if side == "donor":
        donor = replace(donor, hla={**donor.hla, **dqa1})
    else:
        recipient = replace(recipient, hla={**recipient.hla, **dqa1})
    assert build_vector(donor, recipient).notes == ()


def test_the_removed_symmetric_entry_point_refuses_rather_than_guesses() -> None:
    """`rank_candidates` took no direction, and the count is not symmetric, so
    there is no direction it could have picked that is right half the time by
    anything better than luck. It is kept as a loud failure because a caller
    left over from v1 would otherwise get an ordering that reads plausibly and
    counts the wrong way round."""
    with pytest.raises(MatchingNotImplemented) as raised:
        rank_candidates(make_profile("R-1", Role.RECIPIENT), [])
    assert "rank_donors_for" in str(raised.value)
    assert "rank_recipients_for" in str(raised.value)
    assert "not symmetric" in str(raised.value)
