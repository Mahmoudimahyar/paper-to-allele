"""Why a mismatch count may be a range, and may never be a guess.

`MATCH-HLA-001`. Policy: `docs/clinical/MATCHING_POLICY_V2.md` section 3.

Four refusals are what these tests defend, because each is the difference
between a pre-screen a clinician can act on and a number that merely looks like
one.

**The count is directional.** It is the donor's distinct alleles the recipient
lacks, host versus graft. A suite built only from symmetric fixtures would pass
against a transposed implementation, so the direction tests here use pairs whose
two directions genuinely differ, and assert both.

**One allele read is not homozygosity.** `second_allele` is a status flag, and
29 to 36 per cent of resolved A/B/DRB1 cells carried a single value (KI-015),
far above any plausible homozygosity rate. A locus read once therefore produces
a range, and the range must never collapse into a flattering zero. Flattering a
pair beyond what the data supports is the one direction of error this system
must not make, so every partial case is asserted at both ends.

**UNKNOWN is not zero.** A locus that cannot be compared has no count at all.
These tests assert the absence of a number rather than the presence of a zero,
because `count or 0` cannot tell those two apart and a caller who writes it gets
a clean match out of missing data. The ranking now charges an unknown locus at
its worst case (`ranking.UNKNOWN_AS`), so the absence asserted here is what
keeps that charge reachable: a zero arriving from this module would be spent as
a match before the ranking ever saw the gap.

**The locus comes from geometry, not from the printed prefix.** The template
cell decides which locus a value belongs to (HA-017), so the row's locus is
written ONTO every token: `DRB1*04 DRB1*11` and bare `04 11` read from a DRB1
cell are one typing, and a token printed with a different locus is a
locus-binding failure a human must resolve rather than a formatting variant an
extractor may rewrite.

Every allele string below is synthetic.
"""

from __future__ import annotations

import pytest

from kidneymatch.matching.mismatch import (
    LocusTyping,
    LocusValue,
    MismatchStatus,
    MismatchVector,
    mismatch_at_locus,
    parse_locus_value,
)

pytestmark = pytest.mark.task("MATCH-HLA-001")


def both(raw: str, locus: str = "A") -> LocusValue:
    """A locus stored as the archive stores a fully read one: value plus READ."""
    return parse_locus_value(raw, "READ", locus=locus)


def one(raw: str, locus: str = "A") -> LocusValue:
    """A locus where only the first allele was read. NOT homozygous."""
    return parse_locus_value(raw, "UNREAD", locus=locus)


def absent(locus: str = "A") -> LocusValue:
    """A locus that was never typed."""
    return parse_locus_value(None, None, locus=locus)


# --- the direction --------------------------------------------------------


def test_a_recipient_allele_the_donor_lacks_does_not_count() -> None:
    """Host versus graft. The recipient's A*03 is nowhere on the graft, so the
    recipient's immune system will never see it and it may not raise the count.
    A symmetric implementation returns 1 here."""
    result = mismatch_at_locus(both("A*02 A*02"), both("A*02 A*03"))
    assert result.status is MismatchStatus.KNOWN
    assert result.count == 0
    assert result.lower == 0
    assert result.upper == 0


def test_the_two_directions_are_not_transposes_of_one_another() -> None:
    """Policy section 4.1, worked. A homozygous person is structurally
    advantaged as a donor and disadvantaged as a recipient. That is what the
    biology means, not a scoring artefact, so the two answers must differ."""
    homozygous = both("A*02 A*02")
    heterozygous = both("A*01 A*03")
    assert mismatch_at_locus(homozygous, heterozygous).count == 1
    assert mismatch_at_locus(heterozygous, homozygous).count == 2


def test_a_partial_direction_is_not_symmetric_either() -> None:
    """The same refusal has to survive the range arithmetic: a donor read once
    and a recipient read once are bounded for different reasons, and the reason
    is recorded so the two cases stay distinguishable in the explanation."""
    donor_partial = mismatch_at_locus(one("A*01"), both("A*02 A*03"))
    recipient_partial = mismatch_at_locus(both("A*01 A*11"), one("A*02"))
    assert (donor_partial.lower, donor_partial.upper) == (1, 2)
    assert (recipient_partial.lower, recipient_partial.upper) == (1, 2)
    assert donor_partial.reason == "donor second allele not read"
    assert recipient_partial.reason == "recipient second allele not read"


# --- homozygosity falls out of set semantics ------------------------------


@pytest.mark.parametrize(
    ("donor", "recipient", "expected"),
    [
        ("A*02 A*11", "A*01 A*03", 2),
        ("A*02 A*11", "A*02 A*03", 1),
        ("A*02 A*11", "A*02 A*11", 0),
        ("A*02 A*02", "A*02 A*03", 0),
        ("A*02 A*02", "A*01 A*03", 1),
        ("A*02 A*11", "A*02 A*02", 1),
        ("A*02 A*02", "A*02 A*02", 0),
    ],
    ids=[
        "nothing-shared",
        "one-shared",
        "identical",
        "homozygous-donor-shared",
        "homozygous-donor-not-shared",
        "homozygous-recipient",
        "both-homozygous-and-equal",
    ],
)
def test_the_worked_examples_of_policy_section_3_2(
    donor: str, recipient: str, expected: int
) -> None:
    """The reference table, asserted on the fields rather than on the rendering,
    because the ranking reads `upper` and never reads `str()`."""
    result = mismatch_at_locus(both(donor), both(recipient))
    assert result.status is MismatchStatus.KNOWN
    assert result.count == expected
    assert result.lower == expected
    assert result.upper == expected
    assert result.worst == expected
    assert result.compared_depth == 1
    assert result.truncated is False


def test_a_homozygous_side_needs_no_special_case_because_the_count_is_over_distinct() -> None:
    """Zygosity is a property of the comparison, not of a profile, so nothing
    about the parse detects it and nothing about the value records it."""
    donor = both("A*02 A*02")
    assert donor.typing is LocusTyping.BOTH
    assert len(donor.alleles) == 2
    assert donor.distinct_at(1) == frozenset({"A*02"})


def test_an_identical_pair_is_zero_in_both_directions() -> None:
    """Zero in one direction is a subset relation; zero in both is identity."""
    left = both("A*02 A*11")
    right = both("A*02 A*11")
    assert mismatch_at_locus(left, right).count == 0
    assert mismatch_at_locus(right, left).count == 0


# --- one allele read is a range, never a clean zero -----------------------


@pytest.mark.parametrize(
    ("donor", "recipient", "expected"),
    [
        (one("A*02"), both("A*02 A*03"), (0, 1)),
        (one("A*01"), both("A*02 A*03"), (1, 2)),
        (both("A*01 A*11"), one("A*02"), (1, 2)),
        (one("A*02"), one("A*02"), (0, 1)),
        (one("A*01"), one("A*02"), (0, 2)),
    ],
    ids=[
        "donor-one-typed-read-allele-shared",
        "donor-one-typed-read-allele-foreign",
        "recipient-one-typed-nothing-shared",
        "both-one-typed-read-alleles-equal",
        "both-one-typed-read-alleles-differ",
    ],
)
def test_a_partially_typed_locus_yields_a_range(
    donor: LocusValue, recipient: LocusValue, expected: tuple[int, int]
) -> None:
    """The rows of policy section 3.3, plus the both-read-once disagreement it
    does not tabulate. The known part is still counted, so the locus is not
    thrown away, but it can never masquerade as a clean number."""
    result = mismatch_at_locus(donor, recipient)
    assert result.status is MismatchStatus.RANGE
    assert (result.lower, result.upper) == expected
    assert result.count is None, "a range has no single count; a caller must read both ends"
    assert result.reason


def test_the_worse_end_is_the_one_that_decides() -> None:
    """`worst` exists so a caller that has to pick a number picks the
    conservative one without branching on status."""
    result = mismatch_at_locus(one("A*02"), both("A*02 A*03"))
    assert result.worst == 1
    assert result.upper == 1
    assert str(result) == "0-1"


def test_a_donor_read_twice_and_a_donor_read_once_are_not_the_same_answer() -> None:
    """The whole point of KI-015. Both donors show A*02 and the recipient has
    A*02, but only one of them has been shown to carry nothing else."""
    read_twice = mismatch_at_locus(both("A*02 A*02"), both("A*02 A*03"))
    read_once = mismatch_at_locus(one("A*02"), both("A*02 A*03"))
    assert read_twice.status is MismatchStatus.KNOWN
    assert read_twice.count == 0
    assert read_once.status is MismatchStatus.RANGE
    assert read_once.count is None
    assert read_once.upper == 1


def test_a_range_may_be_a_point_and_is_still_reported_as_a_range() -> None:
    """The donor is fully typed and collapses to one distinct allele at the
    compared depth, so the recipient's unread allele cannot change the count.
    The status stays RANGE, because partial typing is a fact about the evidence
    and the ranking carries a partial-locus count of its own alongside the
    charge it takes from the worse end of the range."""
    result = mismatch_at_locus(both("A*02:01 A*02:02"), one("A*02"))
    assert result.status is MismatchStatus.RANGE
    assert (result.lower, result.upper) == (0, 0)
    assert result.count is None


# --- UNKNOWN --------------------------------------------------------------


@pytest.mark.parametrize(
    ("donor", "recipient", "side"),
    [
        (absent(), both("A*02 A*03"), "donor"),
        (both("A*02 A*03"), absent(), "recipient"),
        (absent(), absent(), "donor"),
    ],
)
def test_an_untyped_side_gives_unknown_and_no_number_at_all(
    donor: LocusValue, recipient: LocusValue, side: str
) -> None:
    """Policy 3.5. UNKNOWN is never 0 and never improves a rank: the ranking
    charges the locus at its worst case precisely because nothing was compared
    here, so there must be no number present for that charge to be traded
    against."""
    result = mismatch_at_locus(donor, recipient)
    assert result.status is MismatchStatus.UNKNOWN
    assert result.count is None
    assert result.lower is None
    assert result.upper is None
    assert result.worst is None
    assert result.compared_depth is None
    assert result.truncated is False
    assert result.reason.startswith(side)
    assert str(result) == "UNKNOWN"


@pytest.mark.parametrize("stored", ["", "   ", None])
def test_a_side_stored_as_empty_text_is_unknown_rather_than_a_zero(stored: str | None) -> None:
    """An empty cell and a missing row are the same clinical fact: nothing was
    read there. Neither may become a count."""
    result = mismatch_at_locus(parse_locus_value(stored, "READ", locus="A"), both("A*02 A*03"))
    assert result.status is MismatchStatus.UNKNOWN
    assert result.count is None


# --- the stored shapes ----------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "locus", "flag", "typing", "alleles"),
    [
        ("A*02 A*11", "A", "READ", LocusTyping.BOTH, ("A*02", "A*11")),
        ("DRB1*04 DRB1*11", "DRB1", "READ", LocusTyping.BOTH, ("DRB1*04", "DRB1*11")),
        ("04 11", "DRB1", "READ", LocusTyping.BOTH, ("DRB1*04", "DRB1*11")),
        ("A*02:01 A*11:01", "A", "READ", LocusTyping.BOTH, ("A*02:01", "A*11:01")),
        ("A*02", "A", "UNREAD", LocusTyping.ONE, ("A*02",)),
        (None, "A", None, LocusTyping.ABSENT, ()),
    ],
    ids=[
        "prefixed-pair",
        "locus-prefixed-pair",
        "bare-digit-pair",
        "two-field-pair",
        "single-value-unread",
        "not-typed",
    ],
)
def test_the_six_stored_shapes_parse_to_the_typing_the_value_supports(
    raw: str | None,
    locus: str,
    flag: str | None,
    typing: LocusTyping,
    alleles: tuple[str, ...],
) -> None:
    """The typing comes from how many values are stored, and the allele text
    comes from the cell's locus applied to whatever was printed. The bare pair
    is the case that moved: `04 11` in a DRB1 cell parses as `DRB1*04
    DRB1*11`, so the two printings of that typing are one parsed value."""
    parsed = parse_locus_value(raw, flag, locus=locus)
    assert parsed.typing is typing
    assert parsed.alleles == alleles


@pytest.mark.parametrize(
    ("raw", "flag"),
    [("A*02", "READ"), ("A*02 A*11", "UNREAD")],
    ids=["read-but-one-value-stored", "unread-but-two-values-stored"],
)
def test_a_row_that_contradicts_itself_is_review_required(raw: str, flag: str) -> None:
    """49 Gold rows say READ while storing one allele. Trusting the flag would
    treat a half-typed locus as complete and miscount it; trusting the value in
    silence would hide a row that needs repair. Neither is allowed."""
    parsed = parse_locus_value(raw, flag, locus="A")
    assert parsed.typing is LocusTyping.REVIEW_REQUIRED
    assert parsed.usable is False
    assert "contradicts itself" in parsed.reason


def test_more_than_two_tokens_at_a_diploid_locus_is_review_required() -> None:
    """A third value at a locus is not a third allele; it is an extraction that
    ran into the neighbouring cell."""
    parsed = parse_locus_value("A*02 A*11 A*24", "READ", locus="A")
    assert parsed.typing is LocusTyping.REVIEW_REQUIRED
    assert parsed.usable is False
    assert "diploid" in parsed.reason


def test_the_allele_count_comes_from_the_value_and_not_from_the_flag() -> None:
    """With no flag stored at all the value still decides, and one value is
    still ONE rather than a silently doubled homozygote."""
    assert parse_locus_value("A*02", None, locus="A").typing is LocusTyping.ONE
    assert parse_locus_value("A*02 A*11", None, locus="A").typing is LocusTyping.BOTH


def test_the_flag_is_read_case_insensitively_before_it_is_disbelieved() -> None:
    """A contradiction must not be missed because the flag was stored lowercase
    or padded; that would turn a REVIEW_REQUIRED row into a usable one."""
    assert parse_locus_value("A*02", " read ", locus="A").typing is LocusTyping.REVIEW_REQUIRED


@pytest.mark.parametrize(
    "raw", ["A*02 A*11", "A*02,A*11", "A*02;A*11", "A*02/A*11", "A*02+A*11", "A*02  A*11"]
)
def test_the_stored_separators_all_split_into_two_alleles(raw: str) -> None:
    parsed = parse_locus_value(raw, "READ", locus="A")
    assert parsed.typing is LocusTyping.BOTH
    assert parsed.alleles == ("A*02", "A*11")


@pytest.mark.parametrize(
    ("parsed", "expected"),
    [
        (both("A*02 A*11"), True),
        (one("A*02"), True),
        (absent(), False),
        (parse_locus_value("A*02", "READ", locus="A"), False),
        (parse_locus_value("A*02 A*11 A*24", "READ", locus="A"), False),
    ],
)
def test_only_a_locus_with_alleles_and_no_contradiction_is_usable(
    parsed: LocusValue, expected: bool
) -> None:
    assert parsed.usable is expected


# --- REVIEW_REQUIRED reaches the count as UNKNOWN -------------------------


@pytest.mark.parametrize("side", ["donor", "recipient"])
def test_a_review_required_locus_yields_unknown_rather_than_a_count(side: str) -> None:
    """A row that contradicts itself may not be used, and may-not-be-used has to
    mean UNKNOWN. Falling back to the stored value would silently rank a pair on
    evidence a human has not yet repaired."""
    contradicted = parse_locus_value("A*02", "READ", locus="A")
    clean = both("A*02 A*11")
    donor, recipient = (contradicted, clean) if side == "donor" else (clean, contradicted)
    result = mismatch_at_locus(donor, recipient)
    assert result.status is MismatchStatus.UNKNOWN
    assert result.count is None
    assert result.upper is None
    assert result.reason.startswith(side)
    assert "contradicts itself" in result.reason


# --- resolution and truncation --------------------------------------------


def test_one_field_against_two_field_compares_at_the_coarser_depth() -> None:
    """Policy 3.4. Nothing is ever expanded, so the two-field side is truncated
    rather than the one-field side being imputed."""
    result = mismatch_at_locus(both("A*02:01 A*11:01"), both("A*02 A*03"))
    assert result.status is MismatchStatus.KNOWN
    assert result.count == 1
    assert result.compared_depth == 1
    assert result.truncated is True


def test_a_zero_from_a_truncated_comparison_says_so() -> None:
    """A one-field agreement is weaker evidence than a two-field one, and the
    reader must be able to see which happened. This zero came from four alleles
    compared at half the depth two of them were read at."""
    result = mismatch_at_locus(both("A*02:01 A*11:01"), both("A*02 A*11"))
    assert result.count == 0
    assert result.compared_depth == 1
    assert result.truncated is True


def test_two_field_on_both_sides_is_not_a_truncated_comparison() -> None:
    result = mismatch_at_locus(both("A*02:01 A*11:01"), both("A*02:01 A*11:02"))
    assert result.status is MismatchStatus.KNOWN
    assert result.count == 1
    assert result.compared_depth == 2
    assert result.truncated is False


def test_one_field_on_both_sides_is_not_a_truncated_comparison() -> None:
    """97 per cent of stored values are one field. The common case must not be
    flagged as degraded, or the flag stops meaning anything."""
    result = mismatch_at_locus(both("A*02 A*11"), both("A*02 A*03"))
    assert result.compared_depth == 1
    assert result.truncated is False


def test_truncation_is_reported_on_a_range_as_well_as_on_a_count() -> None:
    result = mismatch_at_locus(one("A*02:01"), both("A*02 A*03"))
    assert result.status is MismatchStatus.RANGE
    assert (result.lower, result.upper) == (0, 1)
    assert result.compared_depth == 1
    assert result.truncated is True


def test_mixed_depth_within_one_side_truncates_that_side_too() -> None:
    """A single stored row can hold one allele at two fields and one at one
    field. The compared depth is the coarsest of all four values."""
    result = mismatch_at_locus(both("A*02:01 A*11"), both("A*02:04 A*03"))
    assert result.compared_depth == 1
    assert result.truncated is True
    assert result.count == 1


# --- expression suffixes ---------------------------------------------------


def test_an_expression_suffix_is_dropped_with_the_field_it_belongs_to() -> None:
    """`A*24:02N` is a null allele read at two fields. At one field the second
    field goes, and its suffix goes with it, because `N` qualifies `02`."""
    parsed = both("A*24:02N A*01:01")
    assert parsed.distinct_at(2) == frozenset({"A*24:02N", "A*01:01"})
    assert parsed.distinct_at(1) == frozenset({"A*24", "A*01"})


def test_a_suffix_on_a_first_field_is_part_of_that_field_and_survives() -> None:
    """`A*24N` carries its suffix on the only field there is, so truncating to
    one field cannot separate them."""
    assert both("A*24N A*01").distinct_at(1) == frozenset({"A*24N", "A*01"})


def test_a_null_allele_is_a_distinct_allele_at_the_depth_it_was_read() -> None:
    """The suffix is part of the allele's identity and is never stripped for a
    comparison at the depth that carries it."""
    result = mismatch_at_locus(both("A*24:02N A*01:01"), both("A*24:02 A*01:01"))
    assert result.compared_depth == 2
    assert result.truncated is False
    assert result.count == 1


def test_a_null_allele_truncates_to_its_first_field_against_one_field_typing() -> None:
    result = mismatch_at_locus(both("A*24:02N A*01:01"), both("A*24 A*01"))
    assert result.compared_depth == 1
    assert result.truncated is True
    assert result.count == 0


# --- bare digit pairs ------------------------------------------------------


def test_bare_digit_pairs_compare_at_one_field() -> None:
    """`04 11` is a measured stored shape: the locus came from the template
    cell, so the value never had to repeat it."""
    result = mismatch_at_locus(both("04 11", locus="DRB1"), both("04 07", locus="DRB1"))
    assert result.status is MismatchStatus.KNOWN
    assert result.count == 1
    assert result.compared_depth == 1
    assert result.truncated is False


def test_identical_bare_digit_pairs_are_a_zero() -> None:
    result = mismatch_at_locus(both("04 11", locus="DRB1"), both("04 11", locus="DRB1"))
    assert result.count == 0


def test_a_bare_digit_pair_matches_the_same_typing_written_with_its_locus_prefix() -> None:
    """The archive stores both `DRB1*04 DRB1*11` and bare `04 11` for DRB1, as
    the module's own token comment records. The locus is already fixed by the
    `gold_fact` row the value is read from, so the row's locus is written onto
    every token and two rows differing only by the printed prefix parse to the
    same alleles. Comparing the printed text instead made an identical pair look
    maximally mismatched and sent a full DRB1 match to KM-6, which is the
    inversion the KM re-cut exists to prevent, so this is asserted as an
    equality of the parsed values and as a zero in both directions."""
    prefixed = both("DRB1*04 DRB1*11", locus="DRB1")
    bare = both("04 11", locus="DRB1")
    assert prefixed.alleles == bare.alleles == ("DRB1*04", "DRB1*11")
    assert prefixed.distinct_at(1) == bare.distinct_at(1)
    forwards = mismatch_at_locus(prefixed, bare)
    backwards = mismatch_at_locus(bare, prefixed)
    assert forwards.status is backwards.status is MismatchStatus.KNOWN
    assert forwards.count == backwards.count == 0
    assert forwards.compared_depth == 1
    assert forwards.truncated is False


def test_a_bare_token_takes_the_locus_of_the_cell_it_was_read_from() -> None:
    """The prefix is written ON the token rather than stripped off the other
    side, so `04` read from a DRB1 cell is `DRB1*04` and keeps the binding
    geometry gave it. Stripping instead would have made the same printed digits
    at two different loci compare equal, which is a cross-locus match built out
    of a coincidence of numbering."""
    drb1 = both("04 11", locus="DRB1")
    b = both("04 11", locus="B")
    assert drb1.alleles == ("DRB1*04", "DRB1*11")
    assert b.alleles == ("B*04", "B*11")
    assert drb1.distinct_at(1).isdisjoint(b.distinct_at(1))
    assert mismatch_at_locus(drb1, b).count == 2


def test_a_bare_single_value_gains_the_prefix_and_is_still_only_one_allele() -> None:
    """Normalisation is about the text, never about how much was read: a bare
    value read once stays ONE and still yields a range."""
    parsed = one("07", locus="DRB1")
    assert parsed.typing is LocusTyping.ONE
    assert parsed.alleles == ("DRB1*07",)
    result = mismatch_at_locus(parsed, both("DRB1*07 DRB1*15", locus="DRB1"))
    assert result.status is MismatchStatus.RANGE
    assert (result.lower, result.upper) == (0, 1)


def test_the_prefix_rule_does_not_make_two_different_typings_equal() -> None:
    """The counterexample the equality above needs. A normalisation that
    collapsed the tokens too far would score every DRB1 pair a zero, so the same
    bare fixture is asserted against typings it genuinely differs from."""
    bare = both("04 11", locus="DRB1")
    assert mismatch_at_locus(bare, both("DRB1*04 DRB1*07", locus="DRB1")).count == 1
    assert mismatch_at_locus(bare, both("DRB1*01 DRB1*07", locus="DRB1")).count == 2
    assert mismatch_at_locus(bare, both("04 07", locus="DRB1")).count == 1


def test_a_cell_that_prints_the_prefix_on_only_one_value_is_one_typing() -> None:
    """A row may carry the prefix on the first value and omit it on the second.
    Both tokens were read from the same cell, so both take that cell's locus."""
    mixed = both("DRB1*04 11", locus="DRB1")
    assert mixed.alleles == ("DRB1*04", "DRB1*11")
    assert mismatch_at_locus(mixed, both("04 DRB1*11", locus="DRB1")).count == 0


def test_a_two_field_bare_value_keeps_its_depth_once_it_gains_the_prefix() -> None:
    """Writing the prefix on must not change what counts as a field, or a bare
    two-field value would be compared at the wrong depth and a truncation would
    stop being reported."""
    deep = both("04:01 11:01", locus="DRB1")
    assert deep.distinct_at(2) == frozenset({"DRB1*04:01", "DRB1*11:01"})
    assert deep.distinct_at(1) == frozenset({"DRB1*04", "DRB1*11"})
    same_depth = mismatch_at_locus(deep, both("DRB1*04:01 DRB1*11:01", locus="DRB1"))
    assert same_depth.count == 0
    assert same_depth.compared_depth == 2
    assert same_depth.truncated is False
    coarser = mismatch_at_locus(deep, both("DRB1*04 DRB1*11", locus="DRB1"))
    assert coarser.count == 0
    assert coarser.compared_depth == 1
    assert coarser.truncated is True


# --- the printed prefix may not overrule the cell --------------------------


@pytest.mark.parametrize(
    ("raw", "flag", "locus"),
    [
        ("A*02 A*11", "READ", "DRB1"),
        ("DRB1*04 DRB1*11", "READ", "A"),
        ("DRB1*04 11", "READ", "A"),
        ("04 DRB1*11", "READ", "A"),
        ("B*07", "UNREAD", "A"),
    ],
    ids=[
        "class-i-value-in-a-drb1-cell",
        "drb1-value-in-an-a-cell",
        "the-first-token-disagrees",
        "the-second-token-disagrees",
        "single-value-in-the-wrong-cell",
    ],
)
def test_a_token_prefixed_with_another_locus_is_review_required(
    raw: str, flag: str, locus: str
) -> None:
    """HA-017: the locus is decided by the template cell, not by the printed
    prefix. So a value printed `A*02` in a DRB1 cell is a locus-binding failure
    with two incompatible readings, and an extractor may take neither. Rewriting
    it to `DRB1*02` would invent a typing nobody read; accepting the text as
    printed would compare an A allele against DRB1 alleles and count the
    formatting fault as mismatches. Only a human may say which row is wrong."""
    parsed = parse_locus_value(raw, flag, locus=locus)
    assert parsed.typing is LocusTyping.REVIEW_REQUIRED
    assert parsed.usable is False
    assert "geometry" in parsed.reason
    assert locus in parsed.reason
    assert parsed.alleles == tuple(raw.split()), "the printed value survives for the reviewer"


def test_the_disagreement_is_refused_before_the_flag_contradiction_is_reported() -> None:
    """A row can be wrong twice. The locus binding is the more serious of the
    two, so it is the reason a reviewer is shown; either way the row is refused
    and neither reason may become a count."""
    parsed = parse_locus_value("A*02", "READ", locus="DRB1")
    assert parsed.typing is LocusTyping.REVIEW_REQUIRED
    assert parsed.usable is False
    assert "geometry" in parsed.reason


@pytest.mark.parametrize("side", ["donor", "recipient"])
def test_a_disagreeing_prefix_reaches_the_count_as_unknown(side: str) -> None:
    """The refusal has to survive into the comparison, on either side. An A
    value sitting in a DRB1 row may not be counted at all: not as mismatches,
    which would demote a pair over a formatting fault, and not as a match after
    a silent rewrite, which would promote one on a typing nobody read."""
    offending = parse_locus_value("A*02 A*11", "READ", locus="DRB1")
    clean = both("DRB1*04 DRB1*11", locus="DRB1")
    donor, recipient = (offending, clean) if side == "donor" else (clean, offending)
    result = mismatch_at_locus(donor, recipient)
    assert result.status is MismatchStatus.UNKNOWN
    assert result.count is None
    assert result.lower is None
    assert result.upper is None
    assert result.worst is None
    assert result.reason.startswith(side)
    assert "geometry" in result.reason


def test_a_lowercase_prefix_is_a_printing_variant_and_not_a_disagreement() -> None:
    """The cell and the token name the same locus, so the row is usable; the
    text still comes from the cell, so a case difference cannot split one allele
    into two and cost a matched pair its zero."""
    parsed = parse_locus_value("drb1*04 DRB1*11", "READ", locus="DRB1")
    assert parsed.typing is LocusTyping.BOTH
    assert parsed.alleles == ("DRB1*04", "DRB1*11")
    assert mismatch_at_locus(parsed, both("04 11", locus="DRB1")).count == 0


# --- what the vector hands to the ranking ----------------------------------


def test_the_vector_names_its_unknown_and_partial_loci() -> None:
    """The ranking charges an unknown locus at its worst case AND counts the
    unknowns and partials in later positions of the sort key, so the vector has
    to be able to say which loci they were rather than only how many."""
    vector = MismatchVector(
        per_locus={
            "A": mismatch_at_locus(both("A*02 A*11"), both("A*02 A*11")),
            "B": mismatch_at_locus(one("B*07", locus="B"), both("B*07 B*08", locus="B")),
            "C": mismatch_at_locus(absent("C"), both("C*01 C*02", locus="C")),
            "DRB1": mismatch_at_locus(both("04 11", locus="DRB1"), both("04 07", locus="DRB1")),
        }
    )
    assert vector.unknown_loci() == ("C",)
    assert vector.partial_loci() == ("B",)


# --- the invariant every answer has to satisfy -----------------------------


_SHAPES = (
    both("A*01 A*02"),
    both("A*02 A*02"),
    both("A*02 A*03"),
    both("A*03 A*11"),
    both("A*02:01 A*11:01"),
    one("A*02"),
    one("A*11"),
    one("A*02:01"),
    both("04 11"),
    absent(),
    parse_locus_value("A*02", "READ", locus="A"),
    parse_locus_value("A*02 A*11 A*24", "READ", locus="A"),
    parse_locus_value("DRB1*04 DRB1*11", "READ", locus="A"),
)


@pytest.mark.parametrize("recipient", _SHAPES)
@pytest.mark.parametrize("donor", _SHAPES)
def test_a_locus_answer_is_always_internally_consistent(
    donor: LocusValue, recipient: LocusValue
) -> None:
    """A locus is diploid, so no comparison of two of them can produce more than
    two mismatches or fewer than none, and no range may be ordered backwards.
    An UNKNOWN carries no number in any field, which is what stops a caller
    reading it as a match."""
    result = mismatch_at_locus(donor, recipient)

    if result.status is MismatchStatus.UNKNOWN:
        assert result.count is None
        assert result.lower is None
        assert result.upper is None
        assert result.compared_depth is None
        assert result.reason
        return

    assert result.lower is not None
    assert result.upper is not None
    assert 0 <= result.lower <= result.upper <= 2
    assert result.compared_depth in (1, 2)

    if result.status is MismatchStatus.KNOWN:
        assert result.count is not None
        assert 0 <= result.count <= 2
        assert result.count == result.lower == result.upper
    else:
        assert result.count is None


# --- the rendering, and the cell that holds only punctuation ---------------


@pytest.mark.parametrize(
    ("donor", "recipient", "rendered"),
    [
        (both("A*02 A*11"), both("A*02 A*11"), "0"),
        (both("A*02 A*11"), both("A*02 A*24"), "1"),
        (both("A*02 A*11"), both("A*23 A*24"), "2"),
        (one("A*02"), both("A*23 A*24"), "1-2"),
        (absent(), both("A*02 A*11"), "UNKNOWN"),
    ],
    ids=["known-zero", "known-one", "known-two", "a-range", "unknown"],
)
def test_a_count_renders_as_the_thing_it_is(
    donor: LocusValue, recipient: LocusValue, rendered: str
) -> None:
    """`str()` is what an operator reads in the terminal runner, so a range must
    stay visibly a range and an unknown must stay visibly unknown. A rendering
    that collapsed either into a single digit would hand back the certainty the
    rest of this module spends its effort refusing to invent."""
    assert str(mismatch_at_locus(donor, recipient)) == rendered


@pytest.mark.parametrize("raw", [",", "//", "+", " ; ", ",,", "/+/"])
def test_a_cell_holding_only_separators_is_untyped_rather_than_typed(raw: str) -> None:
    """A cell can survive extraction carrying punctuation and no allele: a
    dropped value whose comma remained, or a stray mark read as a slash. It is
    not an empty cell, so a bare emptiness check passes it through, and it is
    not an allele, so anything downstream that counted it would be counting a
    character. It parses as ABSENT, which is the same answer as a cell nobody
    ever wrote in."""
    parsed = parse_locus_value(raw, "READ", locus="A")
    assert parsed.typing is LocusTyping.ABSENT
    assert parsed.alleles == ()
    assert parsed.usable is False
    assert "no allele token" in parsed.reason


def test_a_separators_only_cell_reaches_the_count_as_unknown() -> None:
    """The refusal has to survive into the comparison rather than stopping at
    the parser, because ABSENT and a zero count are the two answers this module
    exists to keep apart."""
    result = mismatch_at_locus(parse_locus_value(",", "READ", locus="A"), both("A*02 A*11"))
    assert result.status is MismatchStatus.UNKNOWN
    assert result.count is None
