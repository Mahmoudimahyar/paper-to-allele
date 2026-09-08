"""What must hold for every pair, not only for the pairs somebody thought of.

`MATCH-EVAL-001`. Policy: `docs/clinical/MATCHING_POLICY_V2.md`.

The worked examples in the policy document were chosen by people, so they
cluster on the cases people find interesting. The inputs that will actually
arrive are messier: a homozygous donor read from a form that printed one
allele, a locus stored two-field on one side and one-field on the other, two
candidates whose keys land on the same rung. These tests state the rules as
invariants over generated input rather than over a handful of rows.

Each property is here because breaking it would be silent rather than loud.

* An ordering that is not a total order returns a different list depending on
  which candidate the database happened to yield first, and nobody reading the
  list can tell.
* A float anywhere in the sort key makes a candidate's position depend on
  rounding, and reads to whoever sees it as the compatibility percentage the
  constitution forbids.
* A count that narrows when information is lost flatters a pair beyond its
  evidence, which is the one direction of error this system must not make.
* A locus stored bare on one side and prefixed on the other is one typing
  written two ways, and comparing the printed text instead of the value makes
  the best pairs look like the worst.
* A charge that vanishes when a typing is deleted pays a candidate for losing
  evidence, at a tuple position no later position can answer.
* And a count that survived swapping the two roles unchanged would mean the
  code had quietly started counting graft versus host, which is a question
  about bone marrow and not about kidneys.
"""

from __future__ import annotations

import itertools
import json
from dataclasses import replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from kidneymatch.matching.abo import AboProvenance
from kidneymatch.matching.core import (
    Profile,
    Role,
    RoleMismatch,
    build_vector,
    rank_donors_for,
    rank_recipients_for,
)
from kidneymatch.matching.gates import Bucket, CrossmatchState
from kidneymatch.matching.mismatch import (
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
from kidneymatch.matching.policy import load_policy, policy_path
from kidneymatch.matching.ranking import UNKNOWN_AS, tiebreaker_penalty

pytestmark = pytest.mark.task("MATCH-EVAL-001")

SCORED: tuple[str, ...] = ("A", "B", "C", "DRB1", "DQB1")

#: Deliberately tiny, so that a draw of two alleles collides often and a
#: homozygous-looking profile is common rather than exotic. Every value is
#: synthetic; nothing in this module descends from a real record.
TWO_FIELD: dict[str, tuple[str, ...]] = {
    "A": ("A*01:01", "A*02:01", "A*03:01"),
    "B": ("B*07:02", "B*08:01", "B*35:01"),
    "C": ("C*04:01", "C*07:01"),
    "DRB1": ("DRB1*03:01", "DRB1*04:01", "DRB1*11:01"),
    "DQB1": ("DQB1*02:01", "DQB1*03:01"),
}

#: The same pool with the one-field forms mixed in, so a comparison sometimes
#: has to truncate to the coarser side. Truncation changes the compared depth,
#: so this pool is used only where the property does not depend on the depth
#: staying put between two calls.
MIXED: dict[str, tuple[str, ...]] = {
    locus: alleles + tuple(allele.split(":")[0] for allele in alleles)
    for locus, alleles in TWO_FIELD.items()
}


# --- generators -----------------------------------------------------------

# The draws below are weighted rather than uniform, and the weights are part of
# the test rather than a detail. Drawn uniformly, three quarters of the pairs
# are ineligible and four fifths have no KM level, so the properties would be
# checked almost entirely against one bucket and the no-level sentinel. The
# mixes here keep every bucket, every KM level and every typing shape in play.

#: Two values read, one value read, or the locus not typed at all. The single
#: value is common on purpose: 29 to 36 per cent of resolved A/B/DRB1 cells
#: carry one (KI-015), and it is the shape most likely to be miscounted.
_TYPING_MIX = ("BOTH", "BOTH", "BOTH", "ONE", "ABSENT")
_GROUPS = ("O", "A", "B", "AB", "O", "A", "B", "AB", None)
_PROVENANCES = (
    AboProvenance.LABORATORY_MEASURED,
    AboProvenance.LABORATORY_MEASURED,
    AboProvenance.LABORATORY_MEASURED,
    AboProvenance.PATIENT_REPORTED_ON_FORM,
    AboProvenance.CAPTION_CLAIM,
    AboProvenance.UNKNOWN,
)
_ELIGIBILITY = (True, True, True, True, True, True, True, False)
_CROSSMATCH = (
    CrossmatchState.NOT_PERFORMED,
    CrossmatchState.NOT_PERFORMED,
    CrossmatchState.NOT_PERFORMED,
    CrossmatchState.NOT_PERFORMED,
    CrossmatchState.NEGATIVE,
    CrossmatchState.POSITIVE,
    CrossmatchState.INDETERMINATE,
    CrossmatchState.EXPIRED,
)


@st.composite
def _stored(
    draw: st.DrawFn, pool: dict[str, tuple[str, ...]], locus: str
) -> tuple[str | None, str | None]:
    """A `gold_fact` row as `matching.core.Profile` stores it."""
    shape = draw(st.sampled_from(_TYPING_MIX))
    if shape == "ABSENT":
        return (None, None)
    alleles = st.sampled_from(pool[locus])
    if shape == "ONE":
        return (draw(alleles), "UNREAD")
    return (f"{draw(alleles)} {draw(alleles)}", "READ")


def _locus_value(pool: dict[str, tuple[str, ...]], locus: str) -> st.SearchStrategy[LocusValue]:
    return _stored(pool, locus).map(
        lambda stored: parse_locus_value(stored[0], stored[1], locus=locus)
    )


@st.composite
def _hla(
    draw: st.DrawFn,
    pool: dict[str, tuple[str, ...]],
    *,
    both_only: bool = False,
) -> dict[str, tuple[str | None, str | None]]:
    stored: dict[str, tuple[str | None, str | None]] = {}
    for locus in SCORED:
        if both_only:
            first = draw(st.sampled_from(pool[locus]))
            second = draw(st.sampled_from(pool[locus]))
            stored[locus] = (f"{first} {second}", "READ")
        else:
            stored[locus] = draw(_stored(pool, locus))
    return stored


@st.composite
def _profile(draw: st.DrawFn, profile_id: str, role: Role) -> Profile:
    return Profile(
        profile_id=profile_id,
        role=role,
        hla=draw(_hla(TWO_FIELD)),
        abo=draw(st.sampled_from(_GROUPS)),
        abo_provenance=draw(st.sampled_from(_PROVENANCES)),
        eligible=draw(st.sampled_from(_ELIGIBILITY)),
        crossmatch=draw(st.sampled_from(_CROSSMATCH)),
    )


@st.composite
def _cohort(draw: st.DrawFn, *, min_donors: int = 2) -> tuple[Profile, list[Profile]]:
    """One recipient and a handful of donors, every identifier distinct."""
    recipient = draw(_profile("R00", Role.RECIPIENT))
    count = draw(st.integers(min_value=min_donors, max_value=5))
    donors = [draw(_profile(f"D{index:02d}", Role.DONOR)) for index in range(count)]
    return recipient, donors


def _vector(counts: dict[str, int | None]) -> MismatchVector:
    """A vector built straight from counts, for the tie-breaker properties."""
    per_locus: dict[str, LocusMismatch] = {}
    for locus, count in counts.items():
        if count is None:
            per_locus[locus] = LocusMismatch(MismatchStatus.UNKNOWN, reason="not typed")
        else:
            per_locus[locus] = LocusMismatch(
                MismatchStatus.KNOWN, count=count, lower=count, upper=count, compared_depth=2
            )
    return MismatchVector(per_locus)


# --- the ordering is an ordering ------------------------------------------


@settings(deadline=None, max_examples=60)
@given(cohort=_cohort())
def test_the_sort_key_ordering_is_a_total_order(cohort: tuple[Profile, list[Profile]]) -> None:
    """Total, antisymmetric and transitive, or the list is not a ranking.

    A partial order would leave some pairs of candidates unordered, and the
    position they then took would come from whatever order the rows arrived in.
    """
    recipient, donors = cohort
    keys = [row.key.as_tuple() for row in rank_donors_for(recipient, donors)]
    assert len(keys) == len(donors)

    for left, right in itertools.product(keys, repeat=2):
        assert (left <= right) or (right <= left), "two keys that cannot be compared"
        if left <= right and right <= left:
            assert left == right, "two distinct keys each claiming to precede the other"

    for left, middle, right in itertools.product(keys, repeat=3):
        if left <= middle and middle <= right:
            assert left <= right, "the order is not transitive"


@settings(deadline=None, max_examples=60)
@given(cohort=_cohort())
def test_two_different_candidates_never_produce_the_same_key(
    cohort: tuple[Profile, list[Profile]],
) -> None:
    """1,974 profiles share a genotype with another profile. Without the stable
    hash in last position their relative order would follow dictionary
    iteration, so equal keys are exactly the failure to guard against."""
    recipient, donors = cohort
    keys = [row.key.as_tuple() for row in rank_donors_for(recipient, donors)]
    assert len(set(keys)) == len(keys)


@settings(deadline=None, max_examples=60)
@given(cohort=_cohort())
def test_the_returned_rows_are_in_key_order(cohort: tuple[Profile, list[Profile]]) -> None:
    recipient, donors = cohort
    keys = [row.key.as_tuple() for row in rank_donors_for(recipient, donors)]
    assert keys == sorted(keys)


@settings(deadline=None, max_examples=60)
@given(cohort=_cohort(min_donors=3), data=st.data())
def test_the_order_does_not_depend_on_the_order_candidates_arrive_in(
    cohort: tuple[Profile, list[Profile]],
    data: st.DataObject,
) -> None:
    """Reproducibility is a MATCH-001 invariant. The same recipient and the same
    donors must give the same list whichever way the query happened to page."""
    recipient, donors = cohort
    shuffled = list(data.draw(st.permutations(donors)))
    first = [row.candidate_id for row in rank_donors_for(recipient, donors)]
    second = [row.candidate_id for row in rank_donors_for(recipient, shuffled)]
    assert first == second


@settings(deadline=None, max_examples=40)
@given(cohort=_cohort())
def test_no_float_ever_reaches_a_sort_key(cohort: tuple[Profile, list[Profile]]) -> None:
    """Integers and one hash, and nothing else.

    A float would make a candidate's position depend on binary rounding, would
    stop the ordering being reproducible across machines, and would be read by
    whoever saw it as the compatibility percentage the constitution forbids.
    `bool` is excluded too: it is an integer that prints as a claim.
    """
    recipient, donors = cohort
    for row in rank_donors_for(recipient, donors):
        for position, element in enumerate(row.key.as_tuple()):
            assert type(element) in (int, str), (
                f"sort key position {position} is {type(element).__name__}, "
                "which is neither an integer nor the stable hash"
            )
        assert row.explanation["sort_key"] == list(row.key.as_tuple())


# --- what a count may be --------------------------------------------------


@given(locus=st.sampled_from(SCORED), data=st.data())
def test_a_count_is_bounded_and_a_range_never_inverts(locus: str, data: st.DataObject) -> None:
    """A diploid locus admits at most two mismatches, and a range that ran
    backwards would silently reorder every pair that carried it."""
    donor = data.draw(_locus_value(MIXED, locus))
    recipient = data.draw(_locus_value(MIXED, locus))
    answer = mismatch_at_locus(donor, recipient)

    if answer.status is MismatchStatus.KNOWN:
        assert answer.count is not None
        assert 0 <= answer.count <= 2
        assert answer.lower == answer.count == answer.upper
    elif answer.status is MismatchStatus.RANGE:
        assert answer.lower is not None and answer.upper is not None
        assert 0 <= answer.lower <= answer.upper <= 2
        assert answer.count is None, "a range is not a count and must not be read as one"
    else:
        assert answer.count is None
        assert answer.lower is None and answer.upper is None
        assert answer.worst is None, "UNKNOWN is never a zero"
        assert answer.reason, "a refusal that does not say why cannot be reviewed"


@given(locus=st.sampled_from(SCORED), data=st.data())
def test_losing_a_read_allele_only_ever_widens_the_answer(locus: str, data: st.DataObject) -> None:
    """Information loss may not narrow a count.

    A single-value row is not a homozygous one; it is a row whose second allele
    was usually printed past the edge of the region the reader covered. So
    dropping the second value must produce a range that still contains the
    answer the full typing gave, and dropping both values must produce a range
    containing the ones from dropping either.

    Every allele here is two-field so the compared depth is the same in all four
    calls; truncation is a separate rule and would confound this one.
    """
    pool = st.sampled_from(TWO_FIELD[locus])
    donor_alleles = (data.draw(pool), data.draw(pool))
    recipient_alleles = (data.draw(pool), data.draw(pool))

    donor_both = parse_locus_value(" ".join(donor_alleles), "READ", locus=locus)
    recipient_both = parse_locus_value(" ".join(recipient_alleles), "READ", locus=locus)
    donor_one = parse_locus_value(donor_alleles[0], "UNREAD", locus=locus)
    recipient_one = parse_locus_value(recipient_alleles[0], "UNREAD", locus=locus)

    full = mismatch_at_locus(donor_both, recipient_both)
    assert full.status is MismatchStatus.KNOWN
    truth = full.count
    assert truth is not None

    lost_donor = mismatch_at_locus(donor_one, recipient_both)
    lost_recipient = mismatch_at_locus(donor_both, recipient_one)
    lost_both = mismatch_at_locus(donor_one, recipient_one)

    for degraded in (lost_donor, lost_recipient, lost_both):
        assert degraded.status is MismatchStatus.RANGE
        assert degraded.lower is not None and degraded.upper is not None
        assert degraded.lower <= truth <= degraded.upper, (
            "losing an allele moved the answer outside the range that should bound it"
        )
        assert degraded.upper >= degraded.lower

    assert lost_both.lower is not None and lost_both.upper is not None
    for degraded in (lost_donor, lost_recipient):
        assert degraded.lower is not None and degraded.upper is not None
        assert lost_both.lower <= degraded.lower, "losing more narrowed the lower bound"
        assert lost_both.upper >= degraded.upper, "losing more narrowed the upper bound"


# --- the asymmetry theorem ------------------------------------------------


@given(locus=st.sampled_from(SCORED), data=st.data())
def test_swapping_the_roles_shifts_a_count_by_the_distinct_allele_difference(
    locus: str, data: st.DataObject
) -> None:
    """`MM(D->R) - MM(R->D) = d - r`, policy section 4.1.

    The count is host versus graft, so it is a set difference and not a
    distance. The two directions agree only when both sides carry the same
    number of distinct alleles at the compared depth.
    """
    pool = st.sampled_from(MIXED[locus])
    donor = parse_locus_value(f"{data.draw(pool)} {data.draw(pool)}", "READ", locus=locus)
    recipient = parse_locus_value(f"{data.draw(pool)} {data.draw(pool)}", "READ", locus=locus)

    forward = mismatch_at_locus(donor, recipient)
    reverse = mismatch_at_locus(recipient, donor)
    assert forward.status is MismatchStatus.KNOWN
    assert reverse.status is MismatchStatus.KNOWN

    depth = forward.compared_depth
    assert depth is not None
    assert reverse.compared_depth == depth, "the compared depth must not depend on the direction"

    distinct_donor = len(donor.distinct_at(depth))
    distinct_recipient = len(recipient.distinct_at(depth))
    assert forward.count is not None and reverse.count is not None
    assert forward.count - reverse.count == distinct_donor - distinct_recipient


@settings(deadline=None, max_examples=50)
@given(donor_hla=_hla(MIXED, both_only=True), recipient_hla=_hla(MIXED, both_only=True))
def test_the_theorem_survives_the_whole_vector_not_only_one_locus(
    donor_hla: dict[str, tuple[str | None, str | None]],
    recipient_hla: dict[str, tuple[str | None, str | None]],
) -> None:
    """The same statement through `build_vector`, which is what ranking calls.

    A transposed argument anywhere in the core would show up here as a locus
    whose two directions differed by something other than the allele counts.
    """
    donor = Profile(profile_id="D00", role=Role.DONOR, hla=donor_hla)
    recipient = Profile(profile_id="R00", role=Role.RECIPIENT, hla=recipient_hla)

    forward = build_vector(donor, recipient)
    reverse = build_vector(recipient, donor)

    for locus in SCORED:
        host_versus_graft = forward.per_locus[locus]
        transposed = reverse.per_locus[locus]
        assert host_versus_graft.status is MismatchStatus.KNOWN
        depth = host_versus_graft.compared_depth
        assert depth is not None
        distinct_donor = len(donor.locus(locus).distinct_at(depth))
        distinct_recipient = len(recipient.locus(locus).distinct_at(depth))
        assert host_versus_graft.count is not None and transposed.count is not None
        assert host_versus_graft.count - transposed.count == (
            distinct_donor - distinct_recipient
        ), locus


def test_the_homozygous_worked_example_from_the_policy() -> None:
    """Policy section 4.1, stated as a concrete pair so the general property
    above cannot pass by being vacuously true.

    A homozygous person is structurally advantaged as a donor and structurally
    disadvantaged as a recipient. That is what the biology means, not a scoring
    artefact.
    """
    homozygous = parse_locus_value("A*02:01 A*02:01", "READ", locus="A")
    heterozygous = parse_locus_value("A*01:01 A*03:01", "READ", locus="A")
    assert mismatch_at_locus(homozygous, heterozygous).count == 1
    assert mismatch_at_locus(heterozygous, homozygous).count == 2


# --- the tie-breaker ------------------------------------------------------


@given(locus=st.sampled_from(SCORED), dr_matched=st.booleans())
def test_a_locus_charge_is_never_negative_and_never_falls(locus: str, dr_matched: bool) -> None:
    """A charge that fell as a locus worsened would rank the worse pair first."""
    policy = load_policy()
    charges = [policy.charge(locus, count, dr_matched=dr_matched) for count in (0, 1, 2)]
    assert charges[0] == 0, "a matched locus is charged nothing"
    assert all(charge >= 0 for charge in charges)
    assert charges == sorted(charges)


def test_the_tiebreaker_is_never_negative_and_never_falls_as_a_locus_worsens() -> None:
    """Exhaustive over the 243 reachable count vectors.

    The interesting case is DRB1 going from zero to one, because that closes the
    DR gate and halves every other locus at the same moment. The total must
    still not fall, which is a property of these particular coefficients rather
    than of the formula, so it is checked rather than assumed.
    """
    policy = load_policy()
    for combination in itertools.product((0, 1, 2), repeat=len(SCORED)):
        counts: dict[str, int | None] = dict(zip(SCORED, combination, strict=True))
        base = tiebreaker_penalty(_vector(counts), policy)
        assert base >= 0
        for locus in SCORED:
            current = counts[locus]
            assert current is not None
            if current == 2:
                continue
            worse = dict(counts)
            worse[locus] = current + 1
            assert tiebreaker_penalty(_vector(worse), policy) >= base, (locus, combination)


def _key_for(
    recipient: Profile, candidate: Profile
) -> tuple[int, int, int, int, int, int, int, str]:
    rows = rank_donors_for(recipient, [candidate])
    assert len(rows) == 1
    return rows[0].key.as_tuple()


@settings(deadline=None, max_examples=100)
@given(
    locus=st.sampled_from(SCORED),
    recipient_hla=_hla(TWO_FIELD, both_only=True),
    candidate_hla=_hla(TWO_FIELD, both_only=True),
)
def test_deleting_one_locus_of_typing_never_lowers_a_candidates_sort_key(
    locus: str,
    recipient_hla: dict[str, tuple[str | None, str | None]],
    candidate_hla: dict[str, tuple[str | None, str | None]],
) -> None:
    """Policy section 6.3: losing information never improves a position.

    Stated on the key rather than on a position, because that is the invariant's
    real content. The stable hash is a function of the two identifiers only, so
    deleting a locus cannot change it; if the degraded key is strictly lower
    than the typed key, then a rival sitting between them overtakes on the
    deletion alone, whichever rivals the query happens to return.

    The invariant used to be argued from positions 5 and 6, which do count the
    now-unknown locus. Lexicographic comparison never reaches them: the
    tie-breaker at position 3 and the evidence penalty at position 4 are read
    first, so both of those now charge an unknown locus at its worst case
    rather than skipping it, and the deletion is paid for where it is read.
    """
    measured = AboProvenance.LABORATORY_MEASURED
    recipient = Profile(
        profile_id="R00", role=Role.RECIPIENT, hla=recipient_hla, abo="O", abo_provenance=measured
    )
    candidate = Profile(
        profile_id="D00", role=Role.DONOR, hla=candidate_hla, abo="O", abo_provenance=measured
    )
    thinner = {name: stored for name, stored in candidate_hla.items() if name != locus}

    typed = _key_for(recipient, candidate)
    degraded = _key_for(recipient, replace(candidate, hla=thinner))

    assert degraded >= typed, (
        f"deleting {locus} lowered the sort key from {typed[:7]} to {degraded[:7]}, "
        "so a rival between the two is overtaken by the deletion alone"
    )


def test_deleting_a_matched_locus_must_not_overtake_an_identically_typed_rival() -> None:
    """The same defect stated on the evidence penalty by itself.

    Both donors carry the recipient's own typing, so every locus is a zero
    mismatch. The deletion used to remove the evidence-quality charge at
    position 4, which `matching.core._evidence_penalty` skipped for an UNKNOWN
    locus: a profile improved its position by holding less typing on file, with
    no mismatch anywhere in the comparison.

    Position 4 is asserted element by element and both sides are put on the best
    extraction tier, so this stays a test of the evidence penalty. Read only
    through the whole tuple it would now pass on the tie-breaker at position 3,
    which the deletion also raises, and a regression confined to position 4
    would go unnoticed.
    """
    typing = {
        "A": ("A*01:01 A*02:01", "READ"),
        "B": ("B*07:02 B*08:01", "READ"),
        "C": ("C*04:01 C*07:01", "READ"),
        "DRB1": ("DRB1*03:01 DRB1*04:01", "READ"),
        "DQB1": ("DQB1*02:01 DQB1*03:01", "READ"),
    }
    measured = AboProvenance.LABORATORY_MEASURED
    #: The best tier costs nothing, so a skipped UNKNOWN locus would cost
    #: nothing either and the deletion would be free at position 4.
    best = dict.fromkeys(SCORED, "A")
    recipient = Profile(
        "R00", Role.RECIPIENT, hla=dict(typing), abo="O", abo_provenance=measured, tiers=dict(best)
    )
    rival = Profile(
        "D-RIVAL", Role.DONOR, hla=dict(typing), abo="O", abo_provenance=measured, tiers=dict(best)
    )
    candidate = Profile(
        "D-THIN", Role.DONOR, hla=dict(typing), abo="O", abo_provenance=measured, tiers=dict(best)
    )

    without_c: dict[str, tuple[str | None, str | None]] = {
        name: stored for name, stored in typing.items() if name != "C"
    }
    rival_key = _key_for(recipient, rival)[:7]
    typed_key = _key_for(recipient, candidate)[:7]
    thinned_key = _key_for(recipient, replace(candidate, hla=without_c))[:7]

    assert typed_key == rival_key, (
        "setup: with identical typing the two donors must be separable only by the "
        "stable hash, or this test proves nothing"
    )
    assert thinned_key > rival_key, (
        f"deleting a perfectly matched HLA-C typing moved the candidate from {typed_key} "
        f"to {thinned_key}, ahead of an identically typed rival at {rival_key}; "
        "less evidence must never buy a better place"
    )
    assert thinned_key[4] > rival_key[4], (
        f"the evidence penalty stayed at {rival_key[4]} when a typed locus became "
        "unknown, so an untyped locus is charged as good evidence"
    )
    assert thinned_key[3] > rival_key[3], (
        f"the tie-breaker stayed at {rival_key[3]} when a matched locus became unknown"
    )


# --- missing is never cheaper than known-bad ------------------------------


def test_an_unknown_locus_is_charged_what_a_fully_mismatched_one_is() -> None:
    """The correction to the rule this test used to state.

    It asserted that an unknown locus is charged what a MATCHED one is, on the
    stated ground that the unknown is counted at sort position 5 instead. That
    ground is arithmetically impossible, and the monotonicity property above
    disproved it: the penalty is compared at position 3, so a lexicographic
    comparison settles on the vanished charge long before it reaches position
    5, and deleting a mismatched typing improved a candidate's rank.

    The rule now is the conservative one the policy already applies to a
    partially typed locus. Missing is charged at its worst case, so missing is
    never cheaper than known-bad.

    The whole configuration of the other four loci is swept rather than one row
    of zeros, because the DR gate makes the charge for one locus depend on
    another: for DRB1 the comparison against a matched locus also opens the
    gate and doubles the other four, and the claim has to survive that too.
    """
    policy = load_policy()
    for locus in SCORED:
        rest = [name for name in SCORED if name != locus]
        for background in itertools.product((0, 1, 2, None), repeat=len(rest)):
            counts: dict[str, int | None] = dict(zip(rest, background, strict=True))
            unknown = tiebreaker_penalty(_vector({**counts, locus: None}), policy)
            worst = tiebreaker_penalty(_vector({**counts, locus: 2}), policy)
            matched = tiebreaker_penalty(_vector({**counts, locus: 0}), policy)
            assert unknown == worst, (
                f"an unknown {locus} is charged {unknown} where a fully mismatched one "
                f"is charged {worst}; missing must cost what the worst case costs"
            )
            assert unknown > matched, (
                f"an unknown {locus} is charged {unknown} against {matched} for a matched "
                "one; absence must never be as cheap as a measured match"
            )


def test_an_unknown_drb1_keeps_the_dr_gate_closed() -> None:
    """An unknown DRB1 is not a matched DRB1.

    The gate is what halves every other locus once DR is mismatched, so reading
    an absent DRB1 as matched would double the weight of the four remaining
    loci in exactly the pairs whose most important locus is missing.
    """
    policy = load_policy()
    zeros: dict[str, int | None] = dict.fromkeys(SCORED, 0)
    base = tiebreaker_penalty(_vector({**zeros, "DRB1": None}), policy)
    for locus in ("A", "B", "C", "DQB1"):
        for count in (1, 2):
            counts: dict[str, int | None] = {**zeros, "DRB1": None, locus: count}
            marginal = tiebreaker_penalty(_vector(counts), policy) - base
            halved = policy.charge(locus, count, dr_matched=False)
            assert marginal == halved, (
                f"with DRB1 unknown, {count} mismatch(es) at {locus} cost {marginal} "
                f"where the closed gate charges {halved}"
            )
            assert marginal < policy.charge(locus, count, dr_matched=True), (
                f"an unknown DRB1 left {locus} at full weight, so the gate was read as open"
            )


def _vector_with_presence(presence: tuple[PresenceMismatch, ...]) -> MismatchVector:
    """A fully matched vector carrying one DRB3/4/5 presence answer."""
    matched: dict[str, int | None] = dict.fromkeys(SCORED, 0)
    return MismatchVector(_vector(matched).per_locus, presence)


def test_a_presence_never_established_is_charged_like_a_conflict() -> None:
    """DRB3/4/5 are compared at presence level, and no record of a gene is not
    a record of its absence.

    Charging only the established conflict made deleting the presence record
    cheaper than the conflict it removed, which is the per-locus defect again
    in the one place the vector is not a count.
    """
    policy = load_policy()
    gene = PRESENCE_GENES[0]
    agreed = _vector_with_presence((PresenceMismatch(gene, MismatchStatus.KNOWN),))
    conflict = _vector_with_presence((PresenceMismatch(gene, MismatchStatus.KNOWN, conflict=True),))
    never_established = _vector_with_presence(
        (PresenceMismatch(gene, MismatchStatus.UNKNOWN, reason="presence not established"),)
    )
    assert tiebreaker_penalty(agreed, policy) == 0
    assert tiebreaker_penalty(conflict, policy) > tiebreaker_penalty(agreed, policy)
    assert tiebreaker_penalty(never_established, policy) == tiebreaker_penalty(conflict, policy), (
        "a gene whose presence was never established is cheaper than the conflict it "
        "might be, so deleting the record buys a better place"
    )


def test_deleting_a_typing_never_lowers_the_tiebreaker_from_any_starting_point() -> None:
    """Exhaustive: every one of the 243 count vectors, every locus deleted.

    The neighbouring property checks only that a locus getting worse never
    lowers the total. It does not check the step from a count to no count at
    all, and that is the step that was wrong.
    """
    policy = load_policy()
    for combination in itertools.product((0, 1, 2), repeat=len(SCORED)):
        counts: dict[str, int | None] = dict(zip(SCORED, combination, strict=True))
        base = tiebreaker_penalty(_vector(counts), policy)
        for locus in SCORED:
            deleted = tiebreaker_penalty(_vector({**counts, locus: None}), policy)
            assert deleted >= base, (
                f"deleting {locus} from {combination} lowered the tie-breaker from "
                f"{base} to {deleted}"
            )


#: Four alleles per locus, so that every count from zero to two is reachable
#: against one fixed recipient typing. Synthetic, like every value in this file.
_REALISABLE: dict[str, tuple[str, str, str, str]] = {
    "A": ("A*01:01", "A*02:01", "A*03:01", "A*11:01"),
    "B": ("B*07:02", "B*08:01", "B*35:01", "B*44:02"),
    "C": ("C*04:01", "C*07:01", "C*03:04", "C*06:02"),
    "DRB1": ("DRB1*03:01", "DRB1*04:01", "DRB1*11:01", "DRB1*15:01"),
    "DQB1": ("DQB1*02:01", "DQB1*03:01", "DQB1*05:01", "DQB1*06:02"),
}

#: The fixed recipient side of that pool.
_RECIPIENT_TYPING: dict[str, tuple[str | None, str | None]] = {
    locus: (f"{alleles[0]} {alleles[1]}", "READ") for locus, alleles in _REALISABLE.items()
}

#: The best extraction tier on both sides, so the evidence penalty starts at
#: zero and a deletion has somewhere to rise from. At the default tier the
#: charge for a typed locus already equals the charge for an unknown one, and
#: the property would pass without having tested anything.
_BEST_TIERS: dict[str, str] = dict.fromkeys(SCORED, "A")


def _donor_typing(counts: dict[str, int]) -> dict[str, tuple[str | None, str | None]]:
    """A donor typing whose mismatch against `_RECIPIENT_TYPING` is `counts`."""
    stored: dict[str, tuple[str | None, str | None]] = {}
    for locus, count in counts.items():
        first, second, third, fourth = _REALISABLE[locus]
        pair = {0: (first, second), 1: (first, third), 2: (third, fourth)}[count]
        stored[locus] = (" ".join(pair), "READ")
    return stored


@pytest.mark.invariant("MATCH-001", "losing information never improves a candidate's position")
def test_deleting_a_typing_never_improves_a_sort_key_from_any_starting_point() -> None:
    """The same monotonicity through the whole ranking, exhaustively.

    Policy section 6.3: losing information never improves a position. Stated
    over every starting mismatch count rather than over generated typings,
    because the deletion that used to pay was the deletion of a MISMATCHED
    locus, which a random draw reaches only sometimes and never with the count
    named in the failure message.

    Positions 3 and 4 are asserted element by element as well as through the
    tuple. A lexicographic comparison can rise on an earlier position while a
    later one falls, so `degraded >= typed` on its own would let the tie-breaker
    go back to paying for deletions wherever the KM level rose at position 1.
    """
    measured = AboProvenance.LABORATORY_MEASURED
    recipient = Profile(
        profile_id="R00",
        role=Role.RECIPIENT,
        hla=dict(_RECIPIENT_TYPING),
        abo="O",
        abo_provenance=measured,
        tiers=dict(_BEST_TIERS),
    )
    for combination in itertools.product((0, 1, 2), repeat=len(SCORED)):
        counts = dict(zip(SCORED, combination, strict=True))
        candidate = Profile(
            profile_id="D00",
            role=Role.DONOR,
            hla=_donor_typing(counts),
            abo="O",
            abo_provenance=measured,
            tiers=dict(_BEST_TIERS),
        )
        vector = build_vector(candidate, recipient)
        assert [vector.per_locus[locus].count for locus in SCORED] == list(combination), (
            "the generated typing does not realise the counts it claims to, so this "
            "combination would prove nothing"
        )

        typed = _key_for(recipient, candidate)
        for locus in SCORED:
            thinner = {name: value for name, value in candidate.hla.items() if name != locus}
            degraded = _key_for(recipient, replace(candidate, hla=thinner))
            assert degraded >= typed, (
                f"deleting {locus} from {combination} lowered the sort key from "
                f"{typed[:7]} to {degraded[:7]}"
            )
            assert degraded[4] > typed[4], (
                f"deleting {locus} did not raise the evidence penalty above {typed[4]}, "
                "so an untyped locus is cheaper evidence than a well-extracted one"
            )
            if counts[locus] == 2:
                assert degraded[3] == typed[3], (
                    f"deleting a fully mismatched {locus} changed the tie-breaker; "
                    "missing is charged as the worst case, and the worst case is two"
                )
            elif counts[locus] == 0:
                assert degraded[3] > typed[3], (
                    f"deleting a matched {locus} left the tie-breaker at {typed[3]}"
                )
            else:
                # A and C carry no second-mismatch coefficient, so one mismatch
                # and two are charged alike and this step is allowed to be flat.
                assert degraded[3] >= typed[3], (locus, combination)


def test_the_worst_case_charge_agrees_with_the_versioned_policy_file() -> None:
    """The number lives in the policy file, and the code may not drift from it.

    A ranking produced under coefficients that are not the ones on file could
    not be reproduced or explained, which the MATCH-001 invariants forbid.
    """
    data = json.loads(policy_path().read_text(encoding="utf-8"))
    assert data["tiebreaker"]["unknown_locus_charged_as_mismatches"] == UNKNOWN_AS
    assert UNKNOWN_AS == 2, "a diploid locus admits at most two mismatches"


# --- the stored shape is not the typing -----------------------------------


def _bare(allele: str) -> str:
    """The same allele as the archive's 2,124 prefixless rows store it."""
    return allele.split("*", 1)[-1]


@given(locus=st.sampled_from(SCORED), data=st.data())
def test_the_stored_prefix_shape_never_changes_a_count(locus: str, data: st.DataObject) -> None:
    """`DRB1*04:01 DRB1*11:01` and a bare `04:01 11:01` are one typing.

    The locus comes from the cell geometry, so the printed prefix is formatting
    and not information. Compared as printed text the two shapes share no
    token, so an identical pair counted as maximally mismatched: a full DRB1
    match stored bare against one stored prefixed reached KM-6, the exact
    inversion the KM re-cut exists to prevent.
    """
    pool = st.sampled_from(TWO_FIELD[locus])
    donor_alleles = (data.draw(pool), data.draw(pool))
    recipient_alleles = (data.draw(pool), data.draw(pool))

    def stored(alleles: tuple[str, str], *, bare: bool) -> LocusValue:
        text = " ".join(_bare(allele) if bare else allele for allele in alleles)
        return parse_locus_value(text, "READ", locus=locus)

    prefixed_donor = stored(donor_alleles, bare=False)
    prefixed_recipient = stored(recipient_alleles, bare=False)
    reference = mismatch_at_locus(prefixed_donor, prefixed_recipient)
    assert reference.status is MismatchStatus.KNOWN

    for donor_bare, recipient_bare in itertools.product((False, True), repeat=2):
        donor = stored(donor_alleles, bare=donor_bare)
        recipient = stored(recipient_alleles, bare=recipient_bare)
        assert donor.typing is LocusTyping.BOTH
        assert donor.alleles == prefixed_donor.alleles, (
            "the row's locus must be written onto the bare token; comparing the printed "
            "text makes one typing look like two"
        )
        answer = mismatch_at_locus(donor, recipient)
        assert answer.status is MismatchStatus.KNOWN
        assert answer.count == reference.count, (donor_bare, recipient_bare)
        assert answer.compared_depth == reference.compared_depth


@given(locus=st.sampled_from(SCORED), data=st.data())
def test_a_prefix_from_another_locus_is_refused_rather_than_rewritten(
    locus: str, data: st.DataObject
) -> None:
    """Geometry decides the locus, so a disagreeing prefix is a locus-binding
    failure and not a formatting one.

    Writing the row's locus over the printed one would let an `A*02` that
    landed in a DRB1 cell be counted as a DRB1 allele, which is the thing the
    geometry rule exists to prevent. Dropping the token silently would be worse
    still: the cell would then count as typed.
    """
    other = data.draw(st.sampled_from(SCORED).filter(lambda name: name != locus))
    foreign = data.draw(st.sampled_from(TWO_FIELD[other]))
    native = data.draw(st.sampled_from(TWO_FIELD[locus]))
    clean = parse_locus_value(f"{native} {native}", "READ", locus=locus)

    for text in (f"{foreign} {foreign}", f"{native} {foreign}", f"{foreign} {native}"):
        value = parse_locus_value(text, "READ", locus=locus)
        assert value.typing is LocusTyping.REVIEW_REQUIRED, text
        assert not value.usable
        assert value.reason, "a refusal that does not say why cannot be reviewed"

        for answer in (mismatch_at_locus(value, clean), mismatch_at_locus(clean, value)):
            assert answer.status is MismatchStatus.UNKNOWN
            assert answer.count is None
            assert answer.worst is None, "a locus-binding failure is never a zero"


# --- the gates ------------------------------------------------------------


#: Present in the cell but not an ABO group: an OCR garble, a value carrying
#: Rh, a subgroup, a stray character, whitespace.
_UNREADABLE_GROUPS = ("0", "AB+", "O+", "A2", "RH POSITIVE", "?", " ", "8", "A B")


def _clean_profile(
    profile_id: str, role: Role, group: str | None, provenance: AboProvenance
) -> Profile:
    """A fully typed profile whose only variable is its blood group."""
    return Profile(
        profile_id=profile_id,
        role=role,
        hla=dict(_RECIPIENT_TYPING),
        abo=group,
        abo_provenance=provenance,
    )


@given(
    value=st.sampled_from(_UNREADABLE_GROUPS),
    on_donor=st.booleans(),
    provenance=st.sampled_from(_PROVENANCES),
)
def test_an_unreadable_blood_group_never_reaches_a_ranked_bucket(
    value: str, on_donor: bool, provenance: AboProvenance
) -> None:
    """A present but unreadable group is a MISSING group, not a weak one.

    PROVISIONAL_ABO is a ranked bucket: it says the groups are known and
    compatible but not laboratory-measured, and its next action is to obtain a
    measurement. Routing an OCR garble there asserts a compatibility nobody
    read. INSUFFICIENT_ABO is the honest bucket, and it is not ranked.

    The provenance is swept because no provenance may rescue an unreadable
    value: a laboratory-measured garble is still a garble.
    """
    measured = AboProvenance.LABORATORY_MEASURED
    donor_group, recipient_group = (value, "O") if on_donor else ("O", value)
    donor_provenance, recipient_provenance = (
        (provenance, measured) if on_donor else (measured, provenance)
    )
    recipient = _clean_profile("R00", Role.RECIPIENT, recipient_group, recipient_provenance)
    donor = _clean_profile("D00", Role.DONOR, donor_group, donor_provenance)

    row = rank_donors_for(recipient, [donor])[0]
    assert row.bucket is Bucket.INSUFFICIENT_ABO, row.bucket
    assert not row.bucket.is_ranked
    assert row.bucket.rank > Bucket.PROVISIONAL_ABO.rank
    assert row.decision.abo is not None and row.decision.abo.reason

    # The same pair with a READABLE group from a source that may not clear it
    # does reach a ranked bucket, so the refusal above is about readability, and
    # this property is not passing because nothing ever reaches PROVISIONAL_ABO.
    claimed = AboProvenance.CAPTION_CLAIM
    contrast = rank_donors_for(
        _clean_profile("R00", Role.RECIPIENT, "O", claimed),
        [_clean_profile("D00", Role.DONOR, "O", claimed)],
    )[0]
    assert contrast.bucket is Bucket.PROVISIONAL_ABO
    assert contrast.bucket.is_ranked


@given(role=st.sampled_from(tuple(Role)))
def test_the_anchor_must_hold_the_role_the_direction_asks_of_it(role: Role) -> None:
    """The anchor's own role is checked, not only the candidate list's.

    Filtering the candidates alone let a role-UNKNOWN profile be ranked as the
    anchor, and let a donor be handed in where a recipient was meant, which
    silently reverses the direction of a count that is not symmetric. A role is
    established by review; the matcher may not infer one, so it refuses.
    """
    measured = AboProvenance.LABORATORY_MEASURED
    anchor = _clean_profile("X00", role, "O", measured)
    donor = _clean_profile("D00", Role.DONOR, "O", measured)
    recipient = _clean_profile("R01", Role.RECIPIENT, "O", measured)

    if role is Role.RECIPIENT:
        assert len(rank_donors_for(anchor, [donor])) == 1
    else:
        with pytest.raises(RoleMismatch) as raised:
            rank_donors_for(anchor, [donor])
        assert "X00" in str(raised.value) and role.value in str(raised.value)

    if role is Role.DONOR:
        assert len(rank_recipients_for(anchor, [recipient])) == 1
    else:
        with pytest.raises(RoleMismatch) as raised:
            rank_recipients_for(anchor, [recipient])
        assert "X00" in str(raised.value) and role.value in str(raised.value)


#: Written out here rather than imported, so this test states the ordering
#: independently of the table the implementation reads.
_CROSSMATCH_WORST_LAST = (
    CrossmatchState.NEGATIVE,
    CrossmatchState.NOT_PERFORMED,
    CrossmatchState.EXPIRED,
    CrossmatchState.INDETERMINATE,
    CrossmatchState.POSITIVE,
)


@given(
    donor_state=st.sampled_from(_CROSSMATCH_WORST_LAST),
    recipient_state=st.sampled_from(_CROSSMATCH_WORST_LAST),
)
def test_the_worse_crossmatch_of_the_two_sides_decides_the_pair(
    donor_state: CrossmatchState, recipient_state: CrossmatchState
) -> None:
    """A crossmatch is a property of the pair, so two records are read at their
    worse end.

    Preferring the donor's record unless it was NOT_PERFORMED let a donor-side
    NEGATIVE mask a recipient-side POSITIVE, and a positive physical crossmatch
    is the hardest stop in the policy. The masked pair was not merely
    mis-ranked; it was rendered as a candidate.
    """
    measured = AboProvenance.LABORATORY_MEASURED
    recipient = replace(
        _clean_profile("R00", Role.RECIPIENT, "O", measured), crossmatch=recipient_state
    )
    donor = replace(_clean_profile("D00", Role.DONOR, "O", measured), crossmatch=donor_state)

    row = rank_donors_for(recipient, [donor])[0]
    worst = max((donor_state, recipient_state), key=_CROSSMATCH_WORST_LAST.index)
    assert row.explanation["crossmatch_status"] == worst.value

    if CrossmatchState.POSITIVE in (donor_state, recipient_state):
        assert row.bucket is Bucket.BLOCKED_POSITIVE_CROSSMATCH, (
            f"donor {donor_state.value} with recipient {recipient_state.value} was not "
            "blocked; a positive crossmatch on either side blocks the pair"
        )
        assert not row.bucket.is_ranked
        assert row.decision.blockers
    else:
        assert row.bucket is not Bucket.BLOCKED_POSITIVE_CROSSMATCH
