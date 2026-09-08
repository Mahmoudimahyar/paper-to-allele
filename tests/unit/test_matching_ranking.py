"""Why an order is an order, and what stops a pair being flattered into a better one.

`MATCH-001`. Policy: `docs/clinical/MATCHING_POLICY_V2.md` section 6.

The KM levels are the UK scheme re-cut so that a matched DRB1 outranks anything
the other loci can offer. If that re-cut silently reverted, a single DR mismatch
with a clean B would climb above a DR-matched pair carrying two B mismatches,
which is precisely the ordering the interaction evidence says is backwards, and
nothing about the output would look wrong. So the level table is written out one
row at a time rather than derived from the implementation, and the re-cut is
asserted over the whole grid rather than at one convenient point.

The rest of these tests defend the direction of error. A range decides at its
worse end, an UNKNOWN locus is never a zero, and KM-1 is a claim about three
loci that cannot be made when one of them was never read. Each is one line of
implementation that would still return a plausible-looking level if it were
deleted, and each would fail in the flattering direction.

An UNKNOWN locus is charged at its worst case, as if it carried two mismatches
(section 6.4). An earlier version charged nothing and justified that by the
unknown count at sort position 5. The justification was arithmetically
impossible: the penalty is position 3, so a lexicographic comparison settles on
the charge that vanished long before it reads position 5, and deleting a
MISMATCHED typing improved a candidate's rank. The tests below therefore assert
the charge itself rather than only the order that follows from it, and one of
them walks the whole count grid deleting one locus at a time.

Weights come from the versioned policy file through `load_policy()`. A test that
restated 60 here would pass after somebody edited the policy and would be
proving only that the test file agrees with itself. The exceptions are the
published worked example in section 6.5 and the two gate figures quoted beside
it: those are golden numbers, and changing the policy is meant to break them.

The worked example assumes all five scored loci are typed. HLA-C is absent from
the published table because it is matched, not because it was never read, so
these fixtures set it to zero explicitly. A vector that simply omits it carries
an UNKNOWN HLA-C, which is now charged, and every published total would be
wrong by exactly that charge.
"""

from __future__ import annotations

import itertools
from operator import itemgetter

import pytest

from kidneymatch.matching.gates import Bucket
from kidneymatch.matching.mismatch import (
    SCORED_LOCI,
    LocusMismatch,
    MismatchStatus,
    MismatchVector,
    PresenceMismatch,
)
from kidneymatch.matching.policy import load_policy
from kidneymatch.matching.ranking import (
    NO_LEVEL,
    UNKNOWN_AS,
    SortKey,
    km_level,
    sort_key,
    stable_hash,
    tiebreaker_penalty,
)

pytestmark = pytest.mark.task("MATCH-001")

POLICY = load_policy()
RANKED = Bucket.RANKED.rank

#: A locus count as these tests write it: an int is KNOWN, a pair is a RANGE,
#: and None (or an omitted locus) is UNKNOWN, which is what a real vector holds
#: for a locus nobody typed.
Spec = int | tuple[int, int] | None


def _mm(spec: Spec) -> LocusMismatch:
    if spec is None:
        return LocusMismatch(MismatchStatus.UNKNOWN, reason="not typed on either side")
    if isinstance(spec, tuple):
        lower, upper = spec
        return LocusMismatch(
            MismatchStatus.RANGE,
            lower=lower,
            upper=upper,
            compared_depth=1,
            reason="donor second allele not read",
        )
    return LocusMismatch(MismatchStatus.KNOWN, count=spec, lower=spec, upper=spec, compared_depth=1)


def vec(presence: tuple[PresenceMismatch, ...] = (), /, **by_locus: Spec) -> MismatchVector:
    """A mismatch vector written as counts, e.g. `vec(DRB1=0, B=1, A=(0, 1))`."""
    stray = set(by_locus) - set(SCORED_LOCI)
    if stray:
        raise AssertionError(f"not a scored locus: {sorted(stray)}")
    return MismatchVector({locus: _mm(by_locus.get(locus)) for locus in SCORED_LOCI}, presence)


def key(
    vector: MismatchVector,
    *,
    bucket_rank: int = RANKED,
    evidence: int = 0,
    anchor: str = "R-anchor",
    candidate: str = "D-candidate",
) -> SortKey:
    return sort_key(
        bucket_rank=bucket_rank,
        vector=vector,
        policy=POLICY,
        evidence_penalty=evidence,
        anchor_id=anchor,
        candidate_id=candidate,
    )


def fully_typed(presence: tuple[PresenceMismatch, ...] = (), /, **by_locus: Spec) -> MismatchVector:
    """A vector with every scored locus known, so nothing sorts on an unknown.

    Every penalty fixture below builds on this rather than on `vec()`. An omitted
    locus is UNKNOWN, and an UNKNOWN locus is now charged, so a fixture that
    leaves HLA-C out is asking a different question from the one it looks like it
    is asking.
    """
    counts: dict[str, Spec] = dict.fromkeys(SCORED_LOCI, 0)
    counts.update(by_locus)
    return vec(presence, **counts)


# --- the KM levels, section 6.2 -------------------------------------------

#: (DRB1, B, A, level). The published table, transcribed, not derived.
LEVEL_TABLE: tuple[tuple[int, int, int, int], ...] = (
    (0, 0, 0, 1),
    (0, 0, 1, 2),
    (0, 0, 2, 2),
    (0, 1, 0, 2),
    (0, 1, 2, 2),
    (0, 2, 0, 3),
    (0, 2, 2, 3),
    (1, 0, 0, 4),
    (1, 1, 0, 4),
    (1, 2, 0, 5),
    (2, 0, 0, 6),
    (2, 1, 0, 6),
    (2, 2, 0, 7),
)


@pytest.mark.parametrize(("dr", "b", "a", "expected"), LEVEL_TABLE)
def test_the_km_level_table_row_by_row(dr: int, b: int, a: int, expected: int) -> None:
    assert km_level(vec(DRB1=dr, B=b, A=a)).level == expected


def test_every_level_from_one_to_seven_is_reachable() -> None:
    """A level nothing can reach is a level that is not in the scheme."""
    reached = {km_level(vec(DRB1=dr, B=b, A=a)).level for dr, b, a, _ in LEVEL_TABLE}
    assert reached == set(range(1, 8))


def test_hla_a_separates_only_km_1_from_km_2() -> None:
    """Section 6.2: HLA-A has no independent survival signal, so once the pair
    is past KM-1 the A count may not move the level."""
    for a in (0, 1, 2):
        assert km_level(vec(DRB1=0, B=1, A=a)).level == 2
        assert km_level(vec(DRB1=1, B=0, A=a)).level == 4
        assert km_level(vec(DRB1=2, B=2, A=a)).level == 7


def test_every_dr_matched_pair_outranks_every_dr_mismatched_pair() -> None:
    """The whole point of the re-cut, over the grid rather than at one point.

    The DR-matched side is handicapped everywhere else it can be, and the
    DR-mismatched side is given a clean sweep at every other locus. The level
    still decides, because it sits above the tie-breaker in the tuple.
    """
    grid = list(itertools.product((0, 1, 2), repeat=3))
    matched = [key(fully_typed(DRB1=0, B=b, A=a, DQB1=dq, C=2)) for b, a, dq in grid]
    mismatched = [
        key(fully_typed(DRB1=dr, B=b, A=a, DQB1=dq, C=0)) for dr in (1, 2) for b, a, dq in grid
    ]
    worst_matched = max(k.as_tuple() for k in matched)
    best_mismatched = min(k.as_tuple() for k in mismatched)
    assert worst_matched < best_mismatched


# --- KM-1 is a claim about three loci -------------------------------------


def test_km_1_needs_hla_a_known_and_zero() -> None:
    outcome = km_level(vec(DRB1=0, B=0, A=0))
    assert outcome.level == 1
    assert outcome.km_1_unreachable == ""


def test_an_unknown_hla_a_falls_to_km_2_and_says_why() -> None:
    """An unknown A cannot satisfy `A = 0`. The pair is otherwise perfect, so
    without the note a reader would take the KM-2 for a real A mismatch."""
    outcome = km_level(vec(DRB1=0, B=0))
    assert outcome.level == 2
    assert outcome.km_1_unreachable == "HLA-A unknown"


@pytest.mark.parametrize("a", [1, 2])
def test_a_measured_hla_a_mismatch_is_named_as_the_reason_km_1_was_missed(a: int) -> None:
    outcome = km_level(vec(DRB1=0, B=0, A=a))
    assert outcome.level == 2
    assert outcome.km_1_unreachable == f"{a} HLA-A mismatch(es)"


def test_an_unknown_a_is_not_silently_equivalent_to_a_matched_a() -> None:
    """Both a mismatched A and an unread A sit at KM-2. The sort key is where
    the difference between them survives."""
    known = key(fully_typed(DRB1=0, B=0, A=0, C=0, DQB1=0))
    unread = key(fully_typed(DRB1=0, B=0, C=0, DQB1=0, A=None))
    assert km_level(vec(DRB1=0, B=0, A=1)).level == km_level(vec(DRB1=0, B=0)).level == 2
    assert known.as_tuple() < unread.as_tuple()


# --- a range decides at its worse end -------------------------------------


@pytest.mark.parametrize(
    ("spec", "worse", "better"),
    [
        ({"DRB1": (0, 1), "B": 0, "A": 0}, 4, 1),
        ({"DRB1": 0, "B": (1, 2), "A": 0}, 3, 2),
        ({"DRB1": 0, "B": 0, "A": (0, 1)}, 2, 1),
        ({"DRB1": (1, 2), "B": (0, 2), "A": 0}, 7, 4),
    ],
)
def test_a_range_decides_the_level_at_its_worse_end(
    spec: dict[str, Spec], worse: int, better: int
) -> None:
    outcome = km_level(vec(**spec))
    assert outcome.level == worse
    assert outcome.worst_case == worse
    assert outcome.best_case == better, "the better end is reported, never used"


@pytest.mark.parametrize(("lower", "upper"), [(0, 1), (0, 2), (1, 2)])
def test_a_range_is_worth_exactly_its_worse_end_and_no_more(lower: int, upper: int) -> None:
    """A partially typed locus may never buy a level the count cannot support."""
    ranged = km_level(vec(DRB1=0, B=(lower, upper), A=0))
    assert ranged.level == km_level(vec(DRB1=0, B=upper, A=0)).level


def test_a_range_that_could_reach_km_1_still_does_not() -> None:
    outcome = km_level(vec(DRB1=0, B=0, A=(0, 1)))
    assert outcome.level == 2
    assert outcome.best_case == 1
    assert outcome.km_1_unreachable == "1 HLA-A mismatch(es)"


def test_a_partially_typed_locus_is_counted_in_the_sort_key() -> None:
    ranked = key(fully_typed(DRB1=0, B=(1, 2), A=0, C=0, DQB1=0))
    assert ranked.partial_count == 1
    assert ranked.unknown_count == 0


# --- no level at all ------------------------------------------------------


@pytest.mark.parametrize(
    ("spec", "named"),
    [
        ({"B": 0, "A": 0}, ("DRB1",)),
        ({"DRB1": 0, "A": 0}, ("B",)),
        ({"A": 0}, ("DRB1", "B")),
    ],
)
def test_an_unknown_drb1_or_b_produces_no_level_at_all(
    spec: dict[str, Spec], named: tuple[str, ...]
) -> None:
    outcome = km_level(vec(**spec))
    assert outcome.level == NO_LEVEL
    assert outcome.is_ranked is False
    for locus in named:
        assert locus in outcome.reason


def test_the_no_level_reason_names_only_the_locus_that_is_missing() -> None:
    """`DRB1` contains `B`, so a reason assembled carelessly would be unreadable."""
    assert "DRB1" not in km_level(vec(DRB1=0, A=0)).reason


def test_no_level_sorts_after_every_real_level_at_the_same_bucket() -> None:
    """The sentinel exists so a bug in the gate layer degrades to ranked last.

    The buckets are held equal here on purpose: if `INSUFFICIENT_HLA` ever
    failed to catch a levelless pair, this is the property that keeps it out of
    the top of the list rather than at the top of it.
    """
    levelless = key(fully_typed(DRB1=None))
    for dr, b, a, _ in LEVEL_TABLE:
        ranked = key(fully_typed(DRB1=dr, B=b, A=a))
        assert ranked.as_tuple() < levelless.as_tuple()


def test_losing_the_drb1_typing_costs_more_than_matching_it_and_still_has_no_level() -> None:
    """A lost DRB1 is charged as if both alleles were mismatched, so it costs the
    most any DRB1 can cost, and the pair has no level on top of that.

    The old contract charged nothing for the lost typing AND opened the gate that
    halves the other loci, which made a pair that lost its DRB1 cheaper at
    position 3 than one that matched it. Only position 1 was saving it.
    """
    matched = fully_typed(DRB1=0, B=2)
    mismatched = fully_typed(DRB1=2, B=2)
    lost = fully_typed(DRB1=None, B=2)
    assert tiebreaker_penalty(lost, POLICY) > tiebreaker_penalty(matched, POLICY)
    assert tiebreaker_penalty(lost, POLICY) == tiebreaker_penalty(mismatched, POLICY)
    assert km_level(lost).level == NO_LEVEL
    assert key(matched).as_tuple() < key(lost).as_tuple()
    assert key(mismatched).as_tuple() < key(lost).as_tuple()


def test_an_unknown_drb1_leaves_the_dr_gate_closed() -> None:
    """An unknown DRB1 is not a matched DRB1, so the other loci stay halved.

    Reading the gate off `dr != 1 and dr != 2` rather than off `dr == 0` would
    give the unread pair the full-weight class I charge, which is the flattering
    direction: it would price the other loci as though DR had been matched.
    """
    lost_alone = tiebreaker_penalty(fully_typed(DRB1=None), POLICY)
    with_b = tiebreaker_penalty(fully_typed(DRB1=None, B=2), POLICY)
    assert with_b - lost_alone == POLICY.charge("B", 2, dr_matched=False)
    assert with_b - lost_alone != POLICY.charge("B", 2, dr_matched=True)


# --- the worked example, section 6.5 --------------------------------------

#: (donor, DRB1, B, A, DQB1, level, penalty) exactly as published. D8 is
#: ABO-incompatible and is not in the ranked list at all, so it is not here.
#: HLA-C is not a column in the published table because it is matched throughout;
#: these rows are scored with `fully_typed`, which sets it to zero. Scoring them
#: with an unread HLA-C would add its worst-case charge to every published total.
WORKED_EXAMPLE: tuple[tuple[str, int, int, int, int, int, int], ...] = (
    ("D1", 0, 0, 0, 0, 1, 0),
    ("D2", 0, 0, 1, 0, 2, 10),
    ("D3", 0, 1, 2, 0, 2, 30),
    ("D4", 0, 1, 2, 1, 2, 70),
    ("D5", 0, 2, 0, 0, 3, 30),
    ("D6", 1, 0, 0, 0, 4, 60),
    ("D7", 2, 0, 0, 0, 6, 80),
)


@pytest.mark.parametrize(("donor", "dr", "b", "a", "dq", "level", "penalty"), WORKED_EXAMPLE)
def test_the_worked_example_level_and_penalty(
    donor: str, dr: int, b: int, a: int, dq: int, level: int, penalty: int
) -> None:
    vector = fully_typed(DRB1=dr, B=b, A=a, DQB1=dq, C=0)
    assert km_level(vector).level == level, donor
    assert tiebreaker_penalty(vector, POLICY) == penalty, donor


@pytest.mark.parametrize(("donor", "dr", "b", "a", "dq", "level", "penalty"), WORKED_EXAMPLE)
def test_the_worked_example_totals_hold_only_because_hla_c_is_typed(
    donor: str, dr: int, b: int, a: int, dq: int, level: int, penalty: int
) -> None:
    """The published numbers are for a fully typed pair, and an unread HLA-C is
    not free. Four profiles in five have no HLA-C, so this is the common shape
    rather than the corner one, and the difference must be exactly the worst-case
    charge for that locus under whichever gate the row's DRB1 opens."""
    unread_c = fully_typed(DRB1=dr, B=b, A=a, DQB1=dq, C=None)
    charged = POLICY.charge("C", UNKNOWN_AS, dr_matched=dr == 0)
    assert charged > 0, "an HLA-C charging nothing would make this test vacuous"
    assert tiebreaker_penalty(unread_c, POLICY) == penalty + charged, donor
    assert km_level(unread_c).level == level, f"{donor}: HLA-C never moves the level"


def test_the_worked_example_ranks_d1_to_d7_in_the_published_order() -> None:
    """Fed in shuffled, so the sort does the work rather than the input order."""
    rows = {donor: (dr, b, a, dq) for donor, dr, b, a, dq, _, _ in WORKED_EXAMPLE}
    shuffled = ("D5", "D2", "D7", "D1", "D4", "D6", "D3")
    keys = []
    for donor in shuffled:
        dr, b, a, dq = rows[donor]
        vector = fully_typed(DRB1=dr, B=b, A=a, DQB1=dq, C=0)
        keys.append((key(vector, candidate=donor).as_tuple(), donor))
    keys.sort(key=itemgetter(0))
    assert [donor for _, donor in keys] == [row[0] for row in WORKED_EXAMPLE]


def test_a_dr_matched_donor_with_two_b_mismatches_beats_one_dr_mismatch() -> None:
    """D5 over D6. A flat per-mismatch score gets this pair the wrong way round:
    D5 carries two B mismatches against D6's none."""
    d5 = key(fully_typed(DRB1=0, B=2, A=0, DQB1=0, C=0), candidate="D5")
    d6 = key(fully_typed(DRB1=1, B=0, A=0, DQB1=0, C=0), candidate="D6")
    assert (d5.km_level, d6.km_level) == (3, 4)
    assert d5.as_tuple() < d6.as_tuple()


def test_the_dq_binary_orders_d3_before_d4_at_an_equal_level() -> None:
    """D3 and D4 differ only at DQB1, and position 2 is where that lands."""
    d3 = key(fully_typed(DRB1=0, B=1, A=2, DQB1=0, C=0), candidate="D3")
    d4 = key(fully_typed(DRB1=0, B=1, A=2, DQB1=1, C=0), candidate="D4")
    assert d3.km_level == d4.km_level == 2
    assert (d3.dq_binary, d4.dq_binary) == (0, 1)
    assert d3.as_tuple() < d4.as_tuple()


# --- the DR gate on the tie-breaker, section 6.4 --------------------------


def test_the_dr_gate_halves_the_other_loci() -> None:
    """Two B mismatches cost 30 behind a matched DR, and 15 of a total of 75
    once DR is lost. The figures are quoted in section 6.4 and are also derived
    from the policy here, so a weight change explains itself.

    Both pairs are fully typed. The quoted figures are for a pair with nothing
    unread, and an unread locus now carries its own charge.
    """
    dr_matched = tiebreaker_penalty(fully_typed(DRB1=0, B=2), POLICY)
    dr_mismatched = tiebreaker_penalty(fully_typed(DRB1=1, B=2), POLICY)
    assert dr_matched == 30
    assert dr_mismatched == 75
    assert dr_matched == POLICY.charge("B", 2, dr_matched=True)
    assert dr_mismatched == POLICY.charge("DRB1", 1, dr_matched=False) + POLICY.charge(
        "B", 2, dr_matched=False
    )


@pytest.mark.parametrize("count", [1, 2])
@pytest.mark.parametrize("locus", [name for name in POLICY.scored_loci if name != "DRB1"])
def test_the_halving_is_exact_for_every_locus_and_count(locus: str, count: int) -> None:
    """Integer arithmetic in tenths, so no locus loses a half point to
    truncation. A truncated charge would make the order depend on which loci a
    pair happened to be scored at."""
    full = tiebreaker_penalty(fully_typed(DRB1=0, **{locus: count}), POLICY)
    drb1_only = tiebreaker_penalty(fully_typed(DRB1=1), POLICY)
    halved = tiebreaker_penalty(fully_typed(DRB1=1, **{locus: count}), POLICY) - drb1_only
    assert full > 0, "a locus charging nothing would make this test vacuous"
    assert halved * 2 == full


@pytest.mark.parametrize("count", [1, 2])
def test_the_gate_never_attenuates_drb1_itself(count: int) -> None:
    """`gate(DRB1) = 10` always. DRB1 is what opened the gate; halving it would
    make its own mismatch cheaper for having happened."""
    assert POLICY.charge("DRB1", count, dr_matched=False) == POLICY.charge(
        "DRB1", count, dr_matched=True
    )
    assert tiebreaker_penalty(fully_typed(DRB1=count), POLICY) == POLICY.charge(
        "DRB1", count, dr_matched=True
    )


def test_a_second_mismatch_at_a_locus_never_costs_more_than_the_first() -> None:
    """The measured shape is a step, not a ramp: roughly a third at DRB1, a half
    at B. Only the direction is asserted; the ratios live in the policy file."""
    for locus in POLICY.scored_loci:
        first = POLICY.charge(locus, 1, dr_matched=True)
        both = POLICY.charge(locus, 2, dr_matched=True)
        assert both >= first, locus
        assert both - first <= first, locus


def test_a_drb3_4_5_presence_conflict_is_charged_and_gated_like_a_locus() -> None:
    conflict = (PresenceMismatch("DRB3", MismatchStatus.KNOWN, conflict=True),)
    charged = tiebreaker_penalty(fully_typed(conflict, DRB1=0), POLICY)
    gated = tiebreaker_penalty(fully_typed(conflict, DRB1=1), POLICY) - tiebreaker_penalty(
        fully_typed(DRB1=1), POLICY
    )
    assert charged == POLICY.first_mismatch["DRB3_4_5_presence_conflict"]
    assert gated * 2 == charged


def test_a_drb3_4_5_gene_whose_presence_was_never_established_is_charged_too() -> None:
    """Same reason as an unknown locus, one gene lower. A DRB3/4/5 whose presence
    nobody established costs what a conflict costs, so deleting the row that held
    the conflict cannot buy a cheaper number."""
    conflict = (PresenceMismatch("DRB3", MismatchStatus.KNOWN, conflict=True),)
    never_established = (PresenceMismatch("DRB3", MismatchStatus.UNKNOWN),)
    agreed = (PresenceMismatch("DRB3", MismatchStatus.KNOWN, conflict=False),)
    clean = tiebreaker_penalty(fully_typed(agreed, DRB1=0), POLICY)
    assert tiebreaker_penalty(fully_typed(never_established, DRB1=0), POLICY) == tiebreaker_penalty(
        fully_typed(conflict, DRB1=0), POLICY
    )
    assert tiebreaker_penalty(fully_typed(never_established, DRB1=0), POLICY) > clean
    assert clean == tiebreaker_penalty(fully_typed(DRB1=0), POLICY), "an agreed gene costs nothing"


def test_an_unestablished_drb3_4_5_gene_never_improves_the_key() -> None:
    """The presence gene is counted at position 5 as well, but position 3 is
    where it has to be settled, because position 3 is read first."""
    conflict = (PresenceMismatch("DRB3", MismatchStatus.KNOWN, conflict=True),)
    never_established = (PresenceMismatch("DRB3", MismatchStatus.UNKNOWN),)
    lost = key(fully_typed(never_established, DRB1=0))
    held = key(fully_typed(conflict, DRB1=0))
    assert lost.penalty == held.penalty
    assert lost.unknown_count == held.unknown_count + 1
    assert held.as_tuple() < lost.as_tuple()


# --- UNKNOWN is never a zero, and it is charged at its worst case ---------


@pytest.mark.parametrize("locus", list(SCORED_LOCI))
def test_an_unknown_locus_is_charged_exactly_what_a_full_mismatch_is_charged(locus: str) -> None:
    """Section 6.4. Absence is priced as the worst the data could be.

    Charging nothing was the bug: the penalty is compared at position 3 and the
    unknown count only at position 5, so a lexicographic comparison never reaches
    the count that was supposed to be paying for the missing charge. The charge is
    the worst case and no worse than the worst case, so the assertion is an
    equality in both directions rather than an inequality.
    """
    counts: dict[str, Spec] = {"DRB1": 0, "A": 1, "B": 1, "C": 1, "DQB1": 1}
    counts[locus] = 0
    matched = tiebreaker_penalty(fully_typed(**counts), POLICY)
    counts[locus] = None
    absent = tiebreaker_penalty(fully_typed(**counts), POLICY)
    counts[locus] = 2
    worst = tiebreaker_penalty(fully_typed(**counts), POLICY)
    assert absent == worst, "an unknown locus is charged as if fully mismatched"
    assert absent > matched, "an unknown locus costs strictly more than a matched one"


@pytest.mark.parametrize("locus", list(SCORED_LOCI))
def test_an_unknown_locus_is_charged_at_the_worst_a_locus_can_carry_and_no_more(
    locus: str,
) -> None:
    """The intended consequence, stated as its own claim: unknown costs the same
    as fully mismatched, not more. A locus is diploid, so two is the ceiling."""
    assert UNKNOWN_AS == 2
    for dr_matched in (True, False):
        possible = [POLICY.charge(locus, count, dr_matched=dr_matched) for count in (0, 1, 2)]
        assert POLICY.charge(locus, UNKNOWN_AS, dr_matched=dr_matched) == max(possible)


@pytest.mark.parametrize("locus", [name for name in SCORED_LOCI if name != "DRB1"])
def test_an_unknown_locus_costs_the_same_as_a_range_reaching_its_worse_end(locus: str) -> None:
    """A partially typed locus is already priced at its worse end, and an unread
    one is the same rule taken one step further. If the two disagreed, whether a
    profile was half read or not read at all would change the price of the same
    worst case."""
    ranged = tiebreaker_penalty(fully_typed(DRB1=0, **{locus: (0, 2)}), POLICY)
    unread = tiebreaker_penalty(fully_typed(DRB1=0, **{locus: None}), POLICY)
    assert ranged == unread


@pytest.mark.parametrize("locus", list(SCORED_LOCI))
def test_an_unknown_locus_sorts_after_a_matched_one_and_costs_more(locus: str) -> None:
    """Worse penalty AND a worse key. The old contract asserted an EQUAL penalty
    here and leaned on position 5 to break the tie; that held only because the
    base vector was matched everywhere, and collapsed as soon as the deleted
    locus had carried a mismatch."""
    matched = key(fully_typed())
    absent = key(fully_typed(**{locus: None}))
    assert absent.penalty > matched.penalty
    assert absent.penalty - matched.penalty == POLICY.charge(locus, UNKNOWN_AS, dr_matched=True)
    assert absent.unknown_count == matched.unknown_count + 1
    assert matched.as_tuple() < absent.as_tuple()


@pytest.mark.parametrize("locus", list(SCORED_LOCI))
def test_deleting_a_mismatched_typing_never_lowers_the_penalty(locus: str) -> None:
    """The counterexample the property test found, written out.

    Under the old contract a candidate carrying two mismatches at this locus paid
    for them, and the same candidate with that row deleted paid nothing, so the
    poorer record won at position 3 before position 5 was ever read. The grid is
    walked rather than sampled: the deletion is applied against every combination
    of counts at the other loci, because the DR gate makes the charge depend on
    them.
    """
    others = [name for name in SCORED_LOCI if name != locus]
    for combination in itertools.product((0, 1, 2), repeat=len(others)):
        base: dict[str, Spec] = dict(zip(others, combination, strict=True))
        for count in (0, 1, 2):
            held = fully_typed(**base, **{locus: count})
            lost = fully_typed(**base, **{locus: None})
            assert tiebreaker_penalty(lost, POLICY) >= tiebreaker_penalty(held, POLICY), (
                f"{locus}={count} with {base} got cheaper when it was deleted"
            )


@pytest.mark.parametrize("locus", list(SCORED_LOCI))
def test_deleting_a_typing_never_improves_the_candidates_position(locus: str) -> None:
    """The invariant the penalty rule exists to serve, asserted on the whole key
    rather than on the number alone. Bucket and evidence penalty are held equal so
    that the HLA positions are what decide."""
    others = [name for name in SCORED_LOCI if name != locus]
    for combination in itertools.product((0, 2), repeat=len(others)):
        base: dict[str, Spec] = dict(zip(others, combination, strict=True))
        for count in (0, 1, 2):
            held = key(fully_typed(**base, **{locus: count}))
            lost = key(fully_typed(**base, **{locus: None}))
            assert held.as_tuple() < lost.as_tuple(), (
                f"{locus}={count} with {base} improved its rank by losing the typing"
            )


# --- position 2: DQ is binary ---------------------------------------------


@pytest.mark.parametrize(
    ("spec", "expected"),
    [(0, 0), (1, 1), (2, 1), (None, 1), ((0, 1), 1), ((1, 2), 1), ((0, 0), 0)],
)
def test_dq_is_binary_and_unknown_sorts_with_the_mismatched(spec: Spec, expected: int) -> None:
    """UNKNOWN is not evidence of a match, so it joins the non-zero group. A
    range joins it too, unless even its worse end is zero."""
    assert key(fully_typed(DQB1=spec)).dq_binary == expected


def test_an_unknown_dq_never_outranks_a_matched_dq_at_the_same_level() -> None:
    matched = key(fully_typed(DQB1=0))
    absent = key(fully_typed(DQB1=None))
    mismatched = key(fully_typed(DQB1=1))
    assert matched.km_level == absent.km_level == mismatched.km_level
    assert absent.dq_binary == mismatched.dq_binary
    assert matched.as_tuple() < absent.as_tuple()


# --- position 0 and position 7 --------------------------------------------


def test_the_bucket_precedes_the_hla_heuristic_structurally() -> None:
    """A blocked pair is never rescued by a perfect HLA match, because the
    bucket is position 0 rather than a convention the caller has to remember."""
    blocked = key(fully_typed(), bucket_rank=Bucket.ABO_INCOMPATIBLE.rank)
    poor = key(fully_typed(DRB1=2, B=2, A=2, C=2, DQB1=2))
    assert poor.as_tuple() < blocked.as_tuple()


def test_the_sort_key_has_exactly_the_positions_the_policy_declares() -> None:
    """A field that is not in the key cannot influence the order, and the
    explanation is generated from the key, so a widened key without a widened
    policy would be an unexplained ordering."""
    assert len(key(fully_typed()).as_tuple()) == len(POLICY.sort_tuple)


def test_the_stable_hash_is_deterministic() -> None:
    first = stable_hash(POLICY.policy_id, "R-1", "D-1")
    assert first == stable_hash(POLICY.policy_id, "R-1", "D-1")
    assert len(first) == 64
    # The property is "lowercase hexadecimal", asserted rather than spelled out:
    # a literal hex alphabet contains a ten-digit run that the repository's PII
    # scanner reads as an Iranian national identifier and rejects.
    assert first == first.lower()
    int(first, 16)  # raises unless every character is a hexadecimal digit


def test_the_stable_hash_is_over_the_ordered_pair() -> None:
    """The pair is ordered, and the two directions are not transposes of one
    another, so the last tiebreak may not collapse them into one value."""
    assert stable_hash(POLICY.policy_id, "R-1", "D-1") != stable_hash(
        POLICY.policy_id, "D-1", "R-1"
    )


def test_swapping_the_ordered_pair_changes_the_key_hash() -> None:
    vector = fully_typed()
    forward = key(vector, anchor="P-1", candidate="P-2")
    reverse = key(vector, anchor="P-2", candidate="P-1")
    assert forward.as_tuple()[:-1] == reverse.as_tuple()[:-1]
    assert forward.stable_hash != reverse.stable_hash


def test_the_stable_hash_moves_with_the_policy_version() -> None:
    """A rerun under a new policy is a new run, not the old one with new numbers."""
    assert stable_hash("IR_KIDNEY_SCREEN_2.0", "R-1", "D-1") != stable_hash(
        "IR_KIDNEY_SCREEN_2.1", "R-1", "D-1"
    )


def test_two_candidates_tied_on_everything_else_are_still_ordered() -> None:
    """1,974 profiles share a genotype with another profile, so ties are the
    normal case rather than the corner one. Without the last position the order
    would follow dictionary iteration."""
    vector = fully_typed()
    left = key(vector, candidate="D-1")
    right = key(vector, candidate="D-2")
    assert left.as_tuple()[:-1] == right.as_tuple()[:-1]
    assert left.stable_hash != right.stable_hash
    forward = sorted([left, right], key=lambda k: k.as_tuple())
    backward = sorted([right, left], key=lambda k: k.as_tuple())
    assert forward == backward


def test_only_hla_a_can_be_the_reason_km_1_was_missed() -> None:
    """The claim that makes the `km_1_unreachable` message total.

    KM-1 is "matched at A, B and DRB1". If DRB1 and B are both matched and the
    level is still not 1, HLA-A is the only remaining cause, so the message
    never has to say "some other reason" and the code never needs a branch for
    one. The whole space of A values is walked rather than argued about.
    """
    for a in (0, 1, 2, None, (0, 1), (1, 2), (0, 2)):
        outcome = km_level(fully_typed(DRB1=0, B=0, A=a))
        if outcome.level == 1:
            assert a == 0, "only a matched HLA-A may produce KM-1"
            assert outcome.km_1_unreachable == ""
            continue
        assert outcome.km_1_unreachable != "", (
            f"KM-1 was missed with DRB1 and B matched and A={a}, and nothing said why"
        )
        assert "HLA-A" in outcome.km_1_unreachable


def test_a_range_at_hla_a_is_reported_at_its_worse_end() -> None:
    """A half-read HLA-A that could be a match is not a match, so the message
    names the count that decided the level rather than the hopeful one."""
    outcome = km_level(fully_typed(DRB1=0, B=0, A=(0, 1)))
    assert outcome.level == 2
    assert outcome.km_1_unreachable == "1 HLA-A mismatch(es)"
    assert outcome.best_case == 1, "the optimistic reading is still reported separately"


def test_km_1_is_never_claimed_from_an_unread_hla_a() -> None:
    """The one that would be a real clinical misstatement: KM-1 asserts three
    matched loci, and an untyped locus is not a matched one."""
    outcome = km_level(fully_typed(DRB1=0, B=0, A=None))
    assert outcome.level == 2
    assert outcome.km_1_unreachable == "HLA-A unknown"
