"""The explanation contract: an account that reproduces the order it explains.

`MATCH-EXPLAIN-001`. Policy: `docs/clinical/MATCHING_POLICY_V2.md` section 7.

MATCH-001 requires the explanation to "exactly reconstruct the sort keys". That
is an acceptance criterion rather than a documentation wish, so these tests hold
it literally: the `sort_key` a row prints must be the key that row was actually
sorted by. An explanation written alongside the key instead of from it would
drift from the order the moment either changed, and a drifted explanation is
worse than none, because it is the artefact a reviewer trusts.

The rest of the module guards the refusals. An UNKNOWN or a RANGE arriving
without its reason reads as a small number rather than as absent evidence, so
both must always carry a `why`, and an UNKNOWN must never print a count.
`antibody_status` and `crossmatch_status` are present even though this archive
holds no antibody, PRA or crossmatch data at all, because a field left out is
read as a field that came back clear. `policy_adopted` is false while HA-004 is
open, and it must say so on every row rather than in a footnote.

Four further rules are held here because each of them is visible only in the
account. A crossmatch belongs to the pair rather than to either party, so the
worse of the two recorded states is the one reported: a donor-side NEGATIVE
that hid a recipient-side POSITIVE would print the safest looking value purely
because of argument order. The key is monotone in evidence, so deleting or
degrading a typing may never move a row up the list, or the account would
reward a candidate for losing a value. The locus a value is counted at comes
from the geometry of the cell it was read from, so a bare `04 11` and a printed
`DRB1*04 DRB1*11` explain identically, while a value carrying another locus
name is refused rather than rewritten. And a blood group that is present but is
not an ABO letter is a missing group, not a weak one, so it may not reach a
ranked bucket. The anchor's own role is checked before any of it, because a row
computed in the wrong direction is explained exactly as confidently as one
computed in the right one.

And nothing anywhere may be a percentage. A compatibility figure is the one
output the constitution names as forbidden, precisely because it is the one a
reader would believe without asking what produced it.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from kidneymatch.matching.abo import AboProvenance
from kidneymatch.matching.core import (
    Direction,
    Profile,
    RankedPair,
    Role,
    RoleMismatch,
    rank_donors_for,
    rank_recipients_for,
)
from kidneymatch.matching.gates import Bucket, CrossmatchState
from kidneymatch.matching.mismatch import SCORED_LOCI
from kidneymatch.matching.policy import load_policy

pytestmark = pytest.mark.task("MATCH-EXPLAIN-001")

MEASURED = AboProvenance.LABORATORY_MEASURED

# --- synthetic profiles ---------------------------------------------------
# Invented allele strings only. No archive row and no real person appears here.


def rows(**loci: str) -> dict[str, tuple[str | None, str | None]]:
    """Stored `(value, second_allele_flag)` rows, the flag derived from the value.

    Derived rather than passed so a fixture cannot accidentally build the
    value/flag contradiction that `parse_locus_value` exists to catch.
    """
    return {
        locus: (raw, "READ" if len(raw.split()) == 2 else "UNREAD") for locus, raw in loci.items()
    }


TYPED_VALUES: dict[str, str] = {
    "A": "A*02 A*11",
    "B": "B*07 B*08",
    "C": "C*07 C*04",
    "DRB1": "DRB1*04 DRB1*11",
    "DQB1": "DQB1*03 DQB1*05",
}

#: The same typing written with no locus prefix, the third shape the archive
#: stores (2,124 rows). It has to produce the same account as the prefixed form.
BARE_VALUES: dict[str, str] = {
    "A": "02 11",
    "B": "07 08",
    "C": "07 04",
    "DRB1": "04 11",
    "DQB1": "03 05",
}

#: Every locus mismatched against `TYPED_VALUES`, for the monotonicity checks.
MISMATCHED_VALUES: dict[str, str] = {
    "A": "A*01 A*03",
    "B": "B*35 B*44",
    "C": "C*01 C*02",
    "DRB1": "DRB1*07 DRB1*13",
    "DQB1": "DQB1*02 DQB1*06",
}

FULLY_TYPED = rows(**TYPED_VALUES)


def values_like(
    base: dict[str, str], **overrides: str | None
) -> dict[str, tuple[str | None, str | None]]:
    """`base` with loci replaced, or dropped entirely where the override is None."""
    merged = {**base, **overrides}
    return rows(**{locus: raw for locus, raw in merged.items() if raw is not None})


def typed_like(**overrides: str | None) -> dict[str, tuple[str | None, str | None]]:
    """`FULLY_TYPED` with loci replaced or dropped."""
    return values_like(TYPED_VALUES, **overrides)


def profile(
    pid: str,
    role: Role,
    hla_rows: dict[str, tuple[str | None, str | None]],
    *,
    abo: str | None = "O",
    provenance: AboProvenance = MEASURED,
    **extra: Any,
) -> Profile:
    return Profile(
        profile_id=pid,
        role=role,
        hla=hla_rows,
        abo=abo,
        abo_provenance=provenance,
        **extra,
    )


def a_recipient(pid: str = "r-anchor", **extra: Any) -> Profile:
    return profile(pid, Role.RECIPIENT, FULLY_TYPED, abo="A", **extra)


def a_donor(pid: str = "d-anchor", **extra: Any) -> Profile:
    return profile(pid, Role.DONOR, FULLY_TYPED, abo="A", **extra)


def candidate_donors() -> list[Profile]:
    """A spread wide enough to exercise every branch of the explanation."""
    return [
        profile("d-identical", Role.DONOR, FULLY_TYPED),
        profile(
            "d-one-b",
            Role.DONOR,
            rows(
                A="A*02 A*11",
                B="B*07 B*35",
                C="C*07 C*04",
                DRB1="DRB1*04 DRB1*11",
                DQB1="DQB1*03 DQB1*05",
            ),
        ),
        profile(
            "d-dr-mismatched",
            Role.DONOR,
            rows(
                A="A*01 A*03",
                B="B*35 B*44",
                C="C*07 C*04",
                DRB1="DRB1*07 DRB1*13",
                DQB1="DQB1*02 DQB1*06",
            ),
        ),
        # one allele read at A: a RANGE, never a homozygous zero
        profile(
            "d-partial-a",
            Role.DONOR,
            rows(A="A*24", B="B*07 B*08", DRB1="DRB1*04 DRB1*11", DQB1="DQB1*03 DQB1*05"),
        ),
        # no DRB1 at all: no KM level, so INSUFFICIENT_HLA rather than ranked last
        profile("d-no-drb1", Role.DONOR, rows(A="A*02 A*11", B="B*07 B*08")),
        # a group the laboratory disclaimed: it may exclude a pair but not clear one
        profile(
            "d-reported-abo",
            Role.DONOR,
            FULLY_TYPED,
            provenance=AboProvenance.PATIENT_REPORTED_ON_FORM,
        ),
        # no group at all
        profile("d-no-abo", Role.DONOR, FULLY_TYPED, abo=None, provenance=AboProvenance.UNKNOWN),
        # group AB into a group-A recipient: blocked, not ranked low
        profile("d-abo-blocked", Role.DONOR, FULLY_TYPED, abo="AB"),
        # a value printed with another locus name: refused, not rewritten
        profile("d-crossed-prefix", Role.DONOR, typed_like(DRB1="A*02 A*11")),
        # a group that is present but is not an ABO letter: missing, not weak
        profile("d-unreadable-abo", Role.DONOR, FULLY_TYPED, abo="0"),
    ]


def candidate_recipients() -> list[Profile]:
    """The mirror population, so both directions are covered by one assertion."""
    return [
        profile("r-identical", Role.RECIPIENT, FULLY_TYPED, abo="A"),
        profile(
            "r-partial-drb1",
            Role.RECIPIENT,
            rows(A="A*02 A*11", B="B*07 B*08", DRB1="DRB1*04", DQB1="DQB1*03 DQB1*05"),
            abo="AB",
        ),
        profile("r-no-b", Role.RECIPIENT, rows(A="A*02 A*11", DRB1="DRB1*04 DRB1*11"), abo="A"),
        # a group-A donor cannot give to a group-O recipient
        profile("r-abo-blocked", Role.RECIPIENT, FULLY_TYPED, abo="O"),
        # the same typing written bare: it must explain like the prefixed form
        profile("r-bare-typing", Role.RECIPIENT, values_like(BARE_VALUES), abo="A"),
        profile(
            "r-not-eligible",
            Role.RECIPIENT,
            FULLY_TYPED,
            abo="A",
            eligible=False,
            ineligibility_reason="withdrawn from matching at the profile owner's request",
        ),
    ]


def every_pair() -> list[RankedPair]:
    return [
        *rank_donors_for(a_recipient(), candidate_donors()),
        *rank_recipients_for(a_donor(), candidate_recipients()),
    ]


def one_pair(donor: Profile, recipient: Profile) -> RankedPair:
    """The single ranked row for one ordered pair, in the donors-for-recipient view."""
    ranked = rank_donors_for(recipient, [donor])
    assert len(ranked) == 1
    return ranked[0]


def key_of(
    donor_rows: dict[str, tuple[str | None, str | None]],
    *,
    recipient: Profile | None = None,
    **donor_extra: Any,
) -> list[Any]:
    """The printed sort key for one donor against the standard anchor recipient.

    One donor identifier throughout, so the final stable hash is held constant
    and any difference between two keys is a difference in evidence rather than
    a difference in identity.
    """
    donor = profile("d-key", Role.DONOR, donor_rows, **donor_extra)
    return list(one_pair(donor, recipient or a_recipient()).explanation["sort_key"])


# --- the acceptance criterion: the explanation IS the sort key ------------


def test_the_sort_key_field_is_the_key_the_row_was_sorted_by() -> None:
    """MATCH-001: "rank explanation exactly reconstructs sort keys". Not an
    equivalent rendering and not a rounded one: the same eight values."""
    pairs = every_pair()
    assert len(pairs) >= 8, "the population must cover both directions and several buckets"
    for pair in pairs:
        assert pair.explanation["sort_key"] == list(pair.key.as_tuple())


def test_the_sort_key_field_is_a_list_of_eight() -> None:
    """It is serialised into a MatchRun snapshot, where a tuple becomes a list
    anyway; producing a list here keeps the stored and in-memory forms the same
    object to compare."""
    for pair in every_pair():
        assert isinstance(pair.explanation["sort_key"], list)
        assert len(pair.explanation["sort_key"]) == 8


def test_every_position_in_the_key_is_rebuildable_from_the_prose_fields() -> None:
    """The stronger reading of the criterion: a reviewer holding only the
    readable fields can rederive the numbers that produced the order. Five of
    the eight positions are checked here; the tie-breaker and the evidence
    penalty are admin-only weights pinned by the monotonicity section below, and
    the last is a hash."""
    for pair in every_pair():
        explanation = pair.explanation
        bucket_rank, km_level, dq_binary = explanation["sort_key"][:3]
        _, _, _, _, _, unknown_count, partial_count, _ = explanation["sort_key"]

        assert bucket_rank == Bucket(explanation["bucket"]).rank
        assert km_level == explanation["km_level"]

        dqb1 = explanation["mismatches"]["DQB1"]
        worst = dqb1.get("count", dqb1.get("upper"))
        assert dq_binary == (0 if worst == 0 else 1), (
            "DQB1 is binary and an UNKNOWN DQB1 sorts with the non-zero group: "
            "it is not evidence of a match"
        )

        assert unknown_count == len(explanation["unknown_loci"])
        assert partial_count == len(explanation["partial_loci"])


def test_the_order_of_the_result_is_the_order_of_the_explained_keys() -> None:
    """If sorting ever stopped using the key the explanation prints, this is the
    assertion that would notice."""
    ranked = rank_donors_for(a_recipient(), candidate_donors())
    printed = [tuple(pair.explanation["sort_key"]) for pair in ranked]
    assert printed == sorted(printed)


def test_the_direction_is_recorded_on_every_row() -> None:
    """The count is host versus graft and is not symmetric, so a row that does
    not say which way it was computed cannot be checked."""
    for pair in rank_donors_for(a_recipient(), candidate_donors()):
        assert pair.explanation["direction"] == Direction.DONORS_FOR_RECIPIENT.value
    for pair in rank_recipients_for(a_donor(), candidate_recipients()):
        assert pair.explanation["direction"] == Direction.RECIPIENTS_FOR_DONOR.value


# --- the anchor's own role is checked before any row exists --------------


@pytest.mark.parametrize("role", [Role.DONOR, Role.UNKNOWN])
def test_ranking_donors_refuses_an_anchor_that_is_not_a_recipient(role: Role) -> None:
    """The candidate list was filtered by role while the anchor was not, so a
    donor, or a profile with no established role at all, could be ranked as the
    recipient. The count is host versus graft and is not symmetric, so every row
    of such a run is a number computed in the wrong direction and explained as
    though it were the right one. 2,026 profiles have no established role, and a
    role is established by review: a matcher that inferred one would be making
    exactly the judgement the review exists to make."""
    anchor = profile("x-anchor", role, FULLY_TYPED, abo="A")
    with pytest.raises(RoleMismatch) as raised:
        rank_donors_for(anchor, candidate_donors())
    assert "RECIPIENT is required" in str(raised.value)
    assert role.value in str(raised.value)


@pytest.mark.parametrize("role", [Role.RECIPIENT, Role.UNKNOWN])
def test_ranking_recipients_refuses_an_anchor_that_is_not_a_donor(role: Role) -> None:
    """The mirror refusal, so neither direction can be entered from the wrong
    side of the pair."""
    anchor = profile("x-anchor", role, FULLY_TYPED, abo="A")
    with pytest.raises(RoleMismatch) as raised:
        rank_recipients_for(anchor, candidate_recipients())
    assert "DONOR is required" in str(raised.value)
    assert role.value in str(raised.value)


def test_a_role_unknown_candidate_is_explained_in_neither_direction() -> None:
    """The candidate-side rule that the anchor-side rule was missing from: a
    profile with no role appears on no list, rather than on both."""
    unknown = profile("x-candidate", Role.UNKNOWN, FULLY_TYPED, abo="A")
    assert rank_donors_for(a_recipient(), [unknown]) == []
    assert rank_recipients_for(a_donor(), [unknown]) == []


# --- the printed key is monotone in evidence -----------------------------


@pytest.mark.parametrize("locus", sorted(TYPED_VALUES))
@pytest.mark.parametrize("start", ["matched", "mismatched"])
def test_deleting_a_typing_never_improves_the_row_it_is_deleted_from(
    start: str, locus: str
) -> None:
    """The key is read left to right, so a position that gets cheaper cannot be
    repaid by a later one. An UNKNOWN locus charged nothing in the tie-breaker
    therefore made a deleted mismatch a promotion: the penalty sits at position 3
    and the unknown count at position 5, and the comparison is decided on the
    vanished penalty long before it reaches the extra unknown. Losing a value may
    cost a candidate its place; it may never win one."""
    base_values = TYPED_VALUES if start == "matched" else MISMATCHED_VALUES
    base = key_of(values_like(base_values))
    reduced = key_of(values_like(base_values, **{locus: None}))
    assert reduced > base, (
        f"deleting {locus} from a {start} donor moved the row up the list; a "
        "candidate would gain by losing a typing"
    )
    assert reduced[3] >= base[3], "the tie-breaker penalty fell when evidence was removed"
    assert reduced[4] >= base[4], "the evidence penalty fell when evidence was removed"


@pytest.mark.parametrize("locus", sorted(TYPED_VALUES))
def test_degrading_a_typing_to_one_allele_never_improves_the_row(locus: str) -> None:
    """The same rule one step short of deletion. One allele read is not
    homozygosity (KI-015), so the answer widens to a range, and a widened answer
    may not outrank the measured one it came from."""
    base = key_of(values_like(TYPED_VALUES))
    half = key_of(values_like(TYPED_VALUES, **{locus: TYPED_VALUES[locus].split()[0]}))
    assert half > base, f"reading one allele at {locus} instead of two moved the row up"


def test_an_unknown_locus_costs_what_a_fully_mismatched_one_costs_and_more_than_a_match() -> None:
    """The corrected charge, put as the two comparisons that matter. An unknown
    locus is charged at its worst case, so it is never cheaper than the worst
    thing it could turn out to be, and never as cheap as a match."""
    matched = key_of(values_like(TYPED_VALUES))[3]
    mismatched = key_of(values_like(TYPED_VALUES, C=MISMATCHED_VALUES["C"]))[3]
    unknown = key_of(values_like(TYPED_VALUES, C=None))[3]
    assert matched < mismatched, "a mismatched locus must cost more than a matched one"
    assert unknown == mismatched, (
        "an unknown locus is charged as if fully mismatched; charging it nothing "
        "let a deleted mismatch improve a rank"
    )
    assert unknown > matched, "an unknown locus may never be as cheap as a matched one"


def test_an_unknown_drb1_keeps_the_dr_gate_closed_on_the_other_loci() -> None:
    """An unknown DRB1 is not a matched DRB1. The gate that halves every other
    locus once DR is mismatched has to stay shut, or absence of DR evidence would
    buy the pair the full weight of its class I match."""
    baseline = key_of(values_like(TYPED_VALUES))[3]
    a_at_full_weight = key_of(values_like(TYPED_VALUES, A=MISMATCHED_VALUES["A"]))[3] - baseline
    dr_only = key_of(values_like(TYPED_VALUES, DRB1=MISMATCHED_VALUES["DRB1"]))[3]
    dr_mismatched = key_of(
        values_like(TYPED_VALUES, A=MISMATCHED_VALUES["A"], DRB1=MISMATCHED_VALUES["DRB1"])
    )[3]
    dr_unknown = key_of(values_like(TYPED_VALUES, A=MISMATCHED_VALUES["A"], DRB1=None))[3]

    assert a_at_full_weight > 0
    assert a_at_full_weight % 2 == 0, "the halving must be exact under integer arithmetic"
    assert dr_mismatched - dr_only == a_at_full_weight // 2, (
        "a mismatched DRB1 halves the charge for HLA-A"
    )
    assert dr_unknown == dr_mismatched, (
        "an unknown DRB1 costs what a mismatched one costs, the gate included"
    )
    assert dr_unknown > baseline + a_at_full_weight, "an unknown DRB1 may not read as a matched one"


def test_a_drb3_4_5_gene_whose_presence_was_never_established_is_charged_like_a_conflict() -> None:
    """The presence genes are evidence like any other, so the same rule governs
    them: a gene nobody established may not be cheaper than the conflict it might
    turn out to be, or a pair would improve its position by dropping the row that
    recorded the gene."""
    agreeing = {"DRB3": "PRESENT", "DRB4": "ABSENT", "DRB5": "ABSENT"}
    recipient = a_recipient(presence=agreeing)
    settled = key_of(values_like(TYPED_VALUES), recipient=recipient, presence=agreeing)
    conflicting = key_of(
        values_like(TYPED_VALUES),
        recipient=recipient,
        presence={**agreeing, "DRB3": "PRESENT", "DRB4": "PRESENT"},
    )
    unestablished = key_of(
        values_like(TYPED_VALUES),
        recipient=recipient,
        presence={locus: state for locus, state in agreeing.items() if locus != "DRB4"},
    )
    assert settled[3] < conflicting[3], "a presence conflict must cost something"
    assert unestablished[3] == conflicting[3], (
        "an unestablished gene is charged what a conflicting one is charged"
    )
    assert unestablished > settled, "dropping a presence row moved the pair up the list"


def test_an_unknown_locus_is_charged_at_the_worst_evidence_tier_rather_than_skipped() -> None:
    """The evidence penalty had the same defect as the tie-breaker: it skipped an
    UNKNOWN locus, so a pair holding the best possible extraction evidence could
    improve its own evidence position by losing a locus entirely. Tier C is a
    locus no labelled cell has ever tested, and an absent locus is charged as two
    of those."""
    best = dict.fromkeys(TYPED_VALUES, "A")
    worst_at_c = {**best, "C": "C"}
    typed = key_of(values_like(TYPED_VALUES), recipient=a_recipient(tiers=best), tiers=best)[4]
    absent = key_of(
        values_like(TYPED_VALUES, C=None), recipient=a_recipient(tiers=best), tiers=best
    )[4]
    thin = key_of(
        values_like(TYPED_VALUES), recipient=a_recipient(tiers=worst_at_c), tiers=worst_at_c
    )[4]
    assert typed == 0, "tier A on both sides of every locus is the best evidence there is"
    assert absent > typed, "deleting a locus became the cheapest evidence a pair could hold"
    assert absent == thin, (
        "an untyped locus is charged exactly what the worst evidenced typed pair costs"
    )


# --- every scored locus is accounted for ---------------------------------


def test_every_scored_locus_appears_with_a_status() -> None:
    """A locus silently missing from the account is indistinguishable from a
    locus that matched."""
    for pair in every_pair():
        mismatches = pair.explanation["mismatches"]
        for locus in SCORED_LOCI:
            assert locus in mismatches, f"{locus} missing from {pair.explanation['candidate_id']}"
            assert mismatches[locus]["status"] in {"KNOWN", "RANGE", "UNKNOWN"}


def test_an_unknown_locus_carries_a_why_and_never_a_count() -> None:
    """UNKNOWN is not zero. A count printed beside it would be read as one."""
    seen = 0
    for pair in every_pair():
        for locus, entry in pair.explanation["mismatches"].items():
            if entry["status"] != "UNKNOWN":
                continue
            seen += 1
            assert entry["why"], f"{locus} is UNKNOWN with no reason given"
            assert "count" not in entry
            assert "lower" not in entry
            assert "upper" not in entry
            assert locus in pair.explanation["unknown_loci"]
    assert seen, "the population must contain at least one UNKNOWN locus"


def test_the_why_on_an_untyped_locus_names_the_side_that_lacks_it() -> None:
    donor = profile(
        "d-no-c",
        Role.DONOR,
        rows(A="A*02 A*11", B="B*07 B*08", DRB1="DRB1*04 DRB1*11"),
    )
    entry = one_pair(donor, a_recipient()).explanation["mismatches"]["C"]
    assert entry["status"] == "UNKNOWN"
    assert entry["why"].startswith("donor:")
    assert "not typed" in entry["why"]


# --- the locus is decided by geometry, not by the printed prefix ---------


@pytest.mark.parametrize("locus", [*sorted(BARE_VALUES), "all"])
def test_a_bare_value_and_a_prefixed_one_produce_the_same_account(locus: str) -> None:
    """The archive writes one typing three ways: `DRB1*04 DRB1*11`, `A*02 A*11`,
    and bare digit pairs with no prefix at all. Comparing the printed text made
    an identical pair look maximally mismatched, which demoted the best pairs
    below the worst: a full DRB1 match stored bare against one stored prefixed
    reached KM-6, the exact inversion the KM re-cut exists to prevent. The
    account, the level and every position of the key must be identical."""
    overrides = BARE_VALUES if locus == "all" else {locus: BARE_VALUES[locus]}
    bare = one_pair(
        profile("d-shape", Role.DONOR, typed_like(**overrides)), a_recipient()
    ).explanation
    prefixed = one_pair(profile("d-shape", Role.DONOR, FULLY_TYPED), a_recipient()).explanation
    assert bare["mismatches"] == prefixed["mismatches"]
    assert bare["km_level"] == prefixed["km_level"] == 1
    assert bare["unknown_loci"] == prefixed["unknown_loci"]
    assert bare["sort_key"] == prefixed["sort_key"], (
        "a difference in how a value was printed reached the order"
    )


def test_the_prefix_is_written_on_rather_than_stripped_off_the_printed_identity() -> None:
    """Normalising by deleting the prefix would make the account say less than the
    document did. The comparison is normalised; the printed depth still shows the
    fields that were actually read."""
    bare = one_pair(
        profile("d-bare-depth", Role.DONOR, typed_like(DRB1=BARE_VALUES["DRB1"])), a_recipient()
    ).explanation
    entry = bare["mismatches"]["DRB1"]
    assert entry["status"] == "KNOWN"
    assert entry["count"] == 0
    assert entry["depth"] == "one_field"
    assert "comparison_truncated" not in entry


@pytest.mark.parametrize(
    ("locus", "foreign_value"),
    [
        ("DRB1", "A*02 A*11"),
        ("DQB1", "DRB1*04 DRB1*11"),
        ("A", "B*07 B*08"),
        ("C", "C*07 A*11"),
    ],
)
def test_a_value_whose_prefix_contradicts_its_row_is_refused_not_rewritten(
    locus: str, foreign_value: str
) -> None:
    """The locus is decided by the geometry of the cell, so a value printed with
    another locus name is a locus-binding failure rather than a formatting one.
    Rewriting it either way would be the matcher assigning a locus from OCR text,
    which the ingestion policy forbids outside three measured, withdrawable
    exceptions that do not apply here."""
    donor = profile("d-crossed", Role.DONOR, typed_like(**{locus: foreign_value}))
    explanation = one_pair(donor, a_recipient()).explanation
    entry = explanation["mismatches"][locus]
    assert entry["status"] == "UNKNOWN"
    assert "count" not in entry
    assert "lower" not in entry and "upper" not in entry
    assert entry["why"].startswith("donor:")
    assert "geometry" in entry["why"]
    assert locus in explanation["unknown_loci"]


def test_a_crossed_prefix_at_drb1_costs_the_pair_its_level_rather_than_being_scored() -> None:
    """A locus that cannot be bound is not a locus that matched. The pair loses
    its KM level and leaves the ranked buckets entirely, and the value is not
    quietly counted at whichever locus its prefix named."""
    donor = profile("d-crossed-drb1", Role.DONOR, typed_like(DRB1="A*02 A*11"))
    explanation = one_pair(donor, a_recipient()).explanation
    assert explanation["bucket"] == Bucket.INSUFFICIENT_HLA.value
    assert Bucket(explanation["bucket"]).is_ranked is False
    assert explanation["km_level_name"] == "no level"
    assert explanation["mismatches"]["A"]["status"] == "KNOWN", (
        "the misfiled value must not be counted at the locus its prefix named"
    )
    assert explanation["mismatches"]["A"]["count"] == 0


# --- a range shows both ends and says which allele was not read ----------


@pytest.mark.parametrize(
    ("donor_a", "recipient_a", "expected_side"),
    [
        ("A*24", "A*02 A*11", "donor second allele not read"),
        ("A*02 A*11", "A*24", "recipient second allele not read"),
    ],
)
def test_a_range_carries_lower_upper_and_the_side_that_was_unread(
    donor_a: str, recipient_a: str, expected_side: str
) -> None:
    """One value read is not homozygosity (KI-015): between 29 and 36 of every
    hundred resolved cells carried a single value, far above any plausible
    homozygous rate. So the answer is a range, and it says whose allele is
    missing."""
    donor = profile(
        "d-range",
        Role.DONOR,
        rows(A=donor_a, B="B*07 B*08", DRB1="DRB1*04 DRB1*11", DQB1="DQB1*03 DQB1*05"),
    )
    recipient = profile(
        "r-range",
        Role.RECIPIENT,
        rows(A=recipient_a, B="B*07 B*08", DRB1="DRB1*04 DRB1*11", DQB1="DQB1*03 DQB1*05"),
        abo="A",
    )
    entry = one_pair(donor, recipient).explanation["mismatches"]["A"]
    assert entry["status"] == "RANGE"
    assert entry["lower"] == 1
    assert entry["upper"] == 2
    assert entry["lower"] < entry["upper"]
    assert entry["why"] == expected_side
    assert "count" not in entry, "a range has no single count to print"


def test_a_range_unread_on_both_sides_names_both() -> None:
    donor = profile(
        "d-both",
        Role.DONOR,
        rows(A="A*24", B="B*07 B*08", DRB1="DRB1*04 DRB1*11", DQB1="DQB1*03 DQB1*05"),
    )
    recipient = profile(
        "r-both",
        Role.RECIPIENT,
        rows(A="A*02", B="B*07 B*08", DRB1="DRB1*04 DRB1*11", DQB1="DQB1*03 DQB1*05"),
        abo="A",
    )
    entry = one_pair(donor, recipient).explanation["mismatches"]["A"]
    assert entry["status"] == "RANGE"
    assert "donor second allele not read" in entry["why"]
    assert "recipient second allele not read" in entry["why"]


def test_every_range_locus_is_also_listed_in_partial_loci() -> None:
    for pair in every_pair():
        ranged = {
            locus
            for locus, entry in pair.explanation["mismatches"].items()
            if entry["status"] == "RANGE"
        }
        assert ranged == set(pair.explanation["partial_loci"])


# --- truncation is recorded, never silent --------------------------------


def test_comparison_truncated_appears_when_the_sides_are_typed_at_different_depths() -> None:
    """Silent truncation is forbidden by the policy: a two-field donor compared
    against a one-field recipient produces a one-field answer, and the reader has
    to be told that is what happened."""
    donor = profile(
        "d-two-field",
        Role.DONOR,
        rows(A="A*02:01 A*11:01", B="B*07 B*08", DRB1="DRB1*04 DRB1*11", DQB1="DQB1*03 DQB1*05"),
    )
    recipient = profile(
        "r-one-field",
        Role.RECIPIENT,
        rows(A="A*02 A*24", B="B*07 B*08", DRB1="DRB1*04 DRB1*11", DQB1="DQB1*03 DQB1*05"),
        abo="A",
    )
    explanation = one_pair(donor, recipient).explanation
    assert explanation["mismatches"]["A"]["comparison_truncated"] is True
    assert explanation["mismatches"]["A"]["depth"] == "one_field"


def test_comparison_truncated_is_absent_when_both_sides_are_typed_alike() -> None:
    """The flag has to mean something, so it may not be printed unconditionally."""
    explanation = one_pair(
        profile("d-same-depth", Role.DONOR, FULLY_TYPED), a_recipient()
    ).explanation
    for locus in ("A", "B", "C", "DRB1", "DQB1"):
        assert "comparison_truncated" not in explanation["mismatches"][locus]


# --- reproducibility stamps ----------------------------------------------


def test_every_row_carries_the_versions_that_produced_it() -> None:
    """A run that cannot say which policy and which IMGT release produced it
    cannot be reproduced, and an irreproducible clinical output is not evidence."""
    policy = load_policy()
    for pair in every_pair():
        explanation = pair.explanation
        assert explanation["policy_version"] == policy.policy_id
        assert explanation["imgt_version"] == policy.imgt_version
        assert explanation["pyard_version"] == policy.pyard_version
        assert explanation["policy_version"]
        assert explanation["imgt_version"]
        assert explanation["pyard_version"]


def test_policy_adopted_is_false_while_the_config_says_design_not_adopted() -> None:
    """HA-004 is open. Until an immunologist adopts the coefficients, every row
    must say on its face that the weights are a project design, not policy."""
    policy = load_policy()
    assert policy.status == "DESIGN_NOT_ADOPTED"
    assert policy.is_adopted is False
    for pair in every_pair():
        assert pair.explanation["policy_adopted"] is False


# --- the statuses that must never be omitted -----------------------------


def test_antibody_and_crossmatch_status_are_present_when_nothing_is_known() -> None:
    """The archive holds no antibody, PRA or crossmatch data at all. Omitting the
    fields would let absence of data be read as absence of antibody."""
    for pair in every_pair():
        explanation = pair.explanation
        assert "antibody_status" in explanation
        assert "crossmatch_status" in explanation
        assert explanation["antibody_status"] == "ANTIBODY_UNKNOWN"
        assert explanation["crossmatch_status"] == CrossmatchState.NOT_PERFORMED.value


def test_a_known_crossmatch_is_reported_rather_than_replacing_the_field() -> None:
    donor = profile("d-xm", Role.DONOR, FULLY_TYPED, crossmatch=CrossmatchState.POSITIVE)
    explanation = one_pair(donor, a_recipient()).explanation
    assert explanation["crossmatch_status"] == "POSITIVE"
    assert explanation["antibody_status"] == "ANTIBODY_UNKNOWN"


# --- the crossmatch belongs to the pair, and its worse record wins -------

#: Least to most serious. NOT_PERFORMED outranks NEGATIVE because a pair nobody
#: has tested has been cleared by nobody.
CROSSMATCH_SEVERITY: tuple[CrossmatchState, ...] = (
    CrossmatchState.NEGATIVE,
    CrossmatchState.NOT_PERFORMED,
    CrossmatchState.EXPIRED,
    CrossmatchState.INDETERMINATE,
    CrossmatchState.POSITIVE,
)


def worse_of(left: CrossmatchState, right: CrossmatchState) -> CrossmatchState:
    return max((left, right), key=CROSSMATCH_SEVERITY.index)


def test_the_severity_table_covers_every_state_the_package_can_record() -> None:
    """A state added to the enum and left unranked would be resolved by an order
    nobody chose, so the table this file compares against is asserted complete
    rather than assumed."""
    assert set(CROSSMATCH_SEVERITY) == set(CrossmatchState)
    assert len(CROSSMATCH_SEVERITY) == len(CrossmatchState)


@pytest.mark.parametrize("recipient_state", CROSSMATCH_SEVERITY)
@pytest.mark.parametrize("donor_state", CROSSMATCH_SEVERITY)
def test_the_worse_of_the_two_recorded_crossmatch_states_is_the_one_reported(
    donor_state: CrossmatchState, recipient_state: CrossmatchState
) -> None:
    """A crossmatch is a property of the pair. An earlier version read the donor
    state unless it was NOT_PERFORMED, so the safer looking record won on
    argument order alone, which is the one direction of error this package must
    not make. Every combination is checked, in both seatings, and the printed
    value has to be the one the gate acted on: a row that prints POSITIVE while
    sitting in a ranked bucket would be an account of a decision that was never
    taken."""
    expected = worse_of(donor_state, recipient_state)
    explanation = one_pair(
        profile("d-xm", Role.DONOR, FULLY_TYPED, crossmatch=donor_state),
        a_recipient("r-xm", crossmatch=recipient_state),
    ).explanation
    assert explanation["crossmatch_status"] == expected.value

    swapped = one_pair(
        profile("d-xm", Role.DONOR, FULLY_TYPED, crossmatch=recipient_state),
        a_recipient("r-xm", crossmatch=donor_state),
    ).explanation
    assert swapped["crossmatch_status"] == explanation["crossmatch_status"], (
        "which side holds the worse record may not change the answer"
    )

    blocked = explanation["bucket"] == Bucket.BLOCKED_POSITIVE_CROSSMATCH.value
    assert blocked is (expected is CrossmatchState.POSITIVE), (
        "the state the row prints must be the state the gate acted on"
    )


@pytest.mark.parametrize(
    ("donor_state", "recipient_state", "expected"),
    [
        (CrossmatchState.NEGATIVE, CrossmatchState.NOT_PERFORMED, CrossmatchState.NOT_PERFORMED),
        (CrossmatchState.NOT_PERFORMED, CrossmatchState.EXPIRED, CrossmatchState.EXPIRED),
        (CrossmatchState.EXPIRED, CrossmatchState.INDETERMINATE, CrossmatchState.INDETERMINATE),
        (CrossmatchState.INDETERMINATE, CrossmatchState.POSITIVE, CrossmatchState.POSITIVE),
    ],
)
def test_each_rung_of_the_severity_ladder_is_resolved_at_its_worse_end(
    donor_state: CrossmatchState,
    recipient_state: CrossmatchState,
    expected: CrossmatchState,
) -> None:
    """The ordering itself, one rung at a time, so a table that silently reordered
    two states fails here and not only in aggregate. A negative result does not
    clear a pair nobody tested, a fresh negative does not refresh an expired
    result on the other side, and an indeterminate result is not settled by an
    expired one."""
    explanation = one_pair(
        profile("d-rung", Role.DONOR, FULLY_TYPED, crossmatch=donor_state),
        a_recipient("r-rung", crossmatch=recipient_state),
    ).explanation
    assert explanation["crossmatch_status"] == expected.value
    if expected is not CrossmatchState.POSITIVE:
        assert explanation["bucket"] != Bucket.BLOCKED_POSITIVE_CROSSMATCH.value, (
            "only a positive crossmatch blocks; the rest are reported to the reader"
        )


def test_a_recipient_side_positive_crossmatch_is_not_hidden_by_the_donor_record() -> None:
    """The headline case of the pair rule. A donor-side NEGATIVE beside a
    recipient-side POSITIVE was reported as NEGATIVE, RANKED and with no blocker
    at all, purely because the donor was read first. The gate is inert today (the
    archive holds no antibody, PRA or crossmatch data), so this was a latent
    defect rather than a live one, which is the kind that survives until the day
    the data arrives."""
    donor = profile("d-xm-negative", Role.DONOR, FULLY_TYPED, crossmatch=CrossmatchState.NEGATIVE)
    recipient = a_recipient("r-xm-positive", crossmatch=CrossmatchState.POSITIVE)
    explanation = one_pair(donor, recipient).explanation
    assert explanation["crossmatch_status"] == "POSITIVE", (
        "the pair's worst recorded crossmatch must be the one reported"
    )
    assert explanation["bucket"] == Bucket.BLOCKED_POSITIVE_CROSSMATCH.value
    assert explanation["blockers"]
    assert "crossmatch" in " ".join(explanation["blockers"])
    assert explanation["next_clinical_action"] == "direct pathway blocked"


def test_a_donor_side_positive_crossmatch_is_not_hidden_by_the_recipient_record() -> None:
    """The mirror, so the rule is the worse of the two records and not a new
    preference for whichever side happens to be the candidate."""
    donor = profile("d-xm-positive", Role.DONOR, FULLY_TYPED, crossmatch=CrossmatchState.POSITIVE)
    recipient = a_recipient("r-xm-negative", crossmatch=CrossmatchState.NEGATIVE)
    explanation = one_pair(donor, recipient).explanation
    assert explanation["crossmatch_status"] == "POSITIVE"
    assert explanation["bucket"] == Bucket.BLOCKED_POSITIVE_CROSSMATCH.value
    assert explanation["blockers"]


def test_the_pair_rule_holds_in_the_recipients_for_donor_direction_too() -> None:
    """Both directions build the pair from the same two profiles, so a gate that
    held in one view only would be an artefact of the iteration rather than a
    property of the pair."""
    donor = a_donor("d-anchor-negative", crossmatch=CrossmatchState.NEGATIVE)
    recipient = profile(
        "r-candidate-positive",
        Role.RECIPIENT,
        FULLY_TYPED,
        abo="A",
        crossmatch=CrossmatchState.POSITIVE,
    )
    ranked = rank_recipients_for(donor, [recipient])
    assert len(ranked) == 1
    explanation = ranked[0].explanation
    assert explanation["crossmatch_status"] == "POSITIVE"
    assert explanation["bucket"] == Bucket.BLOCKED_POSITIVE_CROSSMATCH.value
    assert explanation["blockers"]


# --- blockers -------------------------------------------------------------


def test_a_blocked_pair_lists_its_blockers() -> None:
    """A blocked pair is not a low-ranked pair, and the reason it stopped is the
    whole content of the row."""
    donor = profile("d-abo", Role.DONOR, FULLY_TYPED, abo="AB")
    explanation = one_pair(donor, a_recipient()).explanation
    assert explanation["bucket"] == Bucket.ABO_INCOMPATIBLE.value
    assert explanation["blockers"], "a blocked pair with no stated blocker cannot be reviewed"
    assert "cannot donate" in " ".join(explanation["blockers"])
    assert explanation["next_clinical_action"]


def test_every_blocking_reason_is_listed_even_though_the_pair_sits_in_one_bucket() -> None:
    """Two-pass assignment exists so an informational bucket cannot hide a
    blocking one. The explanation has to show every reason that applied, or the
    hiding just moves one layer up."""
    donor = profile(
        "d-two-blocks",
        Role.DONOR,
        FULLY_TYPED,
        abo="AB",
        crossmatch=CrossmatchState.POSITIVE,
    )
    explanation = one_pair(donor, a_recipient()).explanation
    assert explanation["bucket"] == Bucket.BLOCKED_POSITIVE_CROSSMATCH.value
    assert len(explanation["blockers"]) == 2
    joined = " ".join(explanation["blockers"])
    assert "crossmatch" in joined
    assert "cannot donate" in joined


def test_a_ranked_pair_lists_no_blockers() -> None:
    explanation = one_pair(profile("d-clean", Role.DONOR, FULLY_TYPED), a_recipient()).explanation
    assert explanation["bucket"] == Bucket.RANKED.value
    assert explanation["blockers"] == []


# --- an unreadable blood group is a missing one, not a weak one ----------


@pytest.mark.parametrize("garbled", ["0", "AB0", "O+ Rh(D) positive", "   ", "-"])
def test_a_present_but_unreadable_blood_group_is_insufficient_never_provisional(
    garbled: str,
) -> None:
    """PROVISIONAL_ABO is a RANKED bucket: it holds pairs whose groups are known
    and compatible but not laboratory-measured. A value that is not an ABO letter
    at all is a MISSING group rather than a weak one, and routing it to a ranked
    bucket would put an OCR garble, a stray Rh cell or a blank on a list of
    candidates with a next action of proceeding."""
    donor = profile("d-garbled-abo", Role.DONOR, FULLY_TYPED, abo=garbled)
    explanation = one_pair(donor, a_recipient()).explanation
    assert explanation["bucket"] == Bucket.INSUFFICIENT_ABO.value
    assert Bucket(explanation["bucket"]).is_ranked is False
    assert explanation["sort_key"][0] == Bucket.INSUFFICIENT_ABO.rank
    assert explanation["abo"]["gate"] == "UNKNOWN"
    assert explanation["abo"]["reason"]
    assert explanation["next_clinical_action"] == "obtain a laboratory blood group"


def test_an_unreadable_group_on_the_recipient_side_is_caught_as_well() -> None:
    """The gate reads a pair, so it may not check only the candidate's side."""
    donor = profile("d-clean-abo", Role.DONOR, FULLY_TYPED)
    recipient = profile("r-garbled-abo", Role.RECIPIENT, FULLY_TYPED, abo="A negative")
    explanation = one_pair(donor, recipient).explanation
    assert explanation["bucket"] == Bucket.INSUFFICIENT_ABO.value
    assert Bucket(explanation["bucket"]).is_ranked is False


def test_a_readable_group_that_is_only_patient_reported_is_still_provisional() -> None:
    """The distinction has to hold in both directions. An unreadable group may
    not be ranked, and a readable but unmeasured one may not be treated as absent:
    it is evidence enough to exclude a pair, which is why it has a bucket of its
    own rather than being folded into the missing case (KI-014)."""
    donor = profile(
        "d-reported-group",
        Role.DONOR,
        FULLY_TYPED,
        provenance=AboProvenance.PATIENT_REPORTED_ON_FORM,
    )
    explanation = one_pair(donor, a_recipient()).explanation
    assert explanation["bucket"] == Bucket.PROVISIONAL_ABO.value
    assert Bucket(explanation["bucket"]).is_ranked is True
    assert explanation["abo"]["provenance"]["donor"] == "PATIENT_REPORTED_ON_FORM"


def test_an_unreadable_group_still_excludes_nothing_and_blocks_nothing() -> None:
    """INSUFFICIENT_ABO is a request for evidence, not a finding of
    incompatibility: an unreadable value is not grounds to tell two people they
    cannot proceed, only grounds to say the group is not known."""
    donor = profile("d-garbled-blockers", Role.DONOR, FULLY_TYPED, abo="0")
    explanation = one_pair(donor, a_recipient()).explanation
    assert explanation["bucket"] == Bucket.INSUFFICIENT_ABO.value
    assert explanation["blockers"] == []


# --- structural notes -----------------------------------------------------


def test_a_homozygous_recipient_is_explained_not_scored() -> None:
    """A DRB1-homozygous recipient reaches zero DR mismatch only from a donor
    sharing that allele. Without the note their structural one-mismatch reads as
    a poor donor, which is how DR-homozygous candidates accumulate on a list."""
    recipient = profile(
        "r-homozygous",
        Role.RECIPIENT,
        rows(A="A*02 A*11", B="B*07 B*08", DRB1="DRB1*04 DRB1*04", DQB1="DQB1*03 DQB1*05"),
        abo="A",
    )
    donor = profile(
        "d-for-homozygous",
        Role.DONOR,
        rows(A="A*02 A*11", B="B*07 B*08", DRB1="DRB1*04 DRB1*11", DQB1="DQB1*03 DQB1*05"),
    )
    notes = one_pair(donor, recipient).explanation["structural_notes"]
    homozygosity = [note for note in notes if "homozygous" in note]
    assert homozygosity, f"no homozygosity note in {notes}"
    assert "DRB1" in homozygosity[0]
    assert "recipient" in homozygosity[0]


def test_a_homozygous_donor_does_not_produce_a_recipient_homozygosity_note() -> None:
    """The access problem belongs to the recipient. Noting it for the donor would
    be a different claim, and a false one."""
    donor = profile(
        "d-homozygous",
        Role.DONOR,
        rows(A="A*02 A*11", B="B*07 B*08", DRB1="DRB1*04 DRB1*04", DQB1="DQB1*03 DQB1*05"),
    )
    notes = one_pair(donor, a_recipient()).explanation["structural_notes"]
    assert not [note for note in notes if "homozygous" in note]


def test_km_1_being_unreachable_is_stated_rather_than_left_as_a_lower_level() -> None:
    """DRB1 and B both matched but HLA-A unknown cannot be called a full match.
    Printing only "KM-2" would look like a class I mismatch that was measured."""
    donor = profile(
        "d-no-a",
        Role.DONOR,
        rows(B="B*07 B*08", C="C*07 C*04", DRB1="DRB1*04 DRB1*11", DQB1="DQB1*03 DQB1*05"),
    )
    explanation = one_pair(donor, a_recipient()).explanation
    assert explanation["km_level"] == 2
    assert any("KM-1 unreachable" in note for note in explanation["structural_notes"])
    assert any("HLA-A unknown" in note for note in explanation["structural_notes"])


def test_a_duplicate_candidate_is_flagged_as_possibly_the_same_person() -> None:
    """Profiles are photographs, not people: 1,974 share a genotype with another
    profile, so a list may be showing one person twice."""
    donor = profile(
        "d-duplicate",
        Role.DONOR,
        FULLY_TYPED,
        duplicate_candidate_of=("d-identical",),
    )
    notes = one_pair(donor, a_recipient()).explanation["structural_notes"]
    assert any("same" in note and "person" in note for note in notes)


# --- no percentage, anywhere ---------------------------------------------


def _walk(node: Any, path: str = "explanation") -> list[tuple[str, str | None, Any]]:
    """Every (path, key, value) in the explanation, however deeply nested."""
    found: list[tuple[str, str | None, Any]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            found.append((f"{path}.{key}", str(key), value))
            found.extend(_walk(value, f"{path}.{key}"))
    elif isinstance(node, list | tuple):
        for index, value in enumerate(node):
            found.append((f"{path}[{index}]", None, value))
            found.extend(_walk(value, f"{path}[{index}]"))
    return found


def test_no_key_anywhere_in_the_explanation_looks_like_a_percentage() -> None:
    """The constitution and the policy prohibitions both name the user-facing
    compatibility percentage. It is forbidden because it would be believed: one
    number invites action the evidence cannot support."""
    banned = ("percent", "pct", "compatibility_score", "match_score", "probability")
    for pair in every_pair():
        for path, key, _ in _walk(pair.explanation):
            if key is None:
                continue
            lowered = key.lower()
            for word in banned:
                assert word not in lowered, f"{path} looks like a percentage"


def test_no_value_anywhere_in_the_explanation_is_a_fraction_or_a_percentage() -> None:
    """The tie-breaker is integer arithmetic precisely so no float can leak out of
    it and be mistaken for a likelihood. A float in a clinical account is a
    percentage whatever its key is called."""
    for pair in every_pair():
        for path, _, value in _walk(pair.explanation):
            assert not isinstance(value, float), f"{path} is a float: {value!r}"
            if isinstance(value, str):
                lowered = value.lower()
                assert "%" not in value, f"{path} prints a percent sign: {value!r}"
                assert "percent" not in lowered, f"{path} says percent: {value!r}"
                assert "per cent" not in lowered, f"{path} says per cent: {value!r}"


def test_the_numeric_fields_that_do_exist_are_integers_and_admin_only() -> None:
    """The sort key carries a numeric tie-breaker. It is an ordering device, it is
    never displayed, and it is an integer so it cannot be read as a score out of
    anything."""
    for pair in every_pair():
        numbers = pair.explanation["sort_key"][:-1]
        tail = pair.explanation["sort_key"][-1]
        for value in numbers:
            assert isinstance(value, int)
            assert not isinstance(value, bool)
        assert isinstance(tail, str), "the final tiebreak is a stable hash, not a number"


def test_the_explanation_survives_a_json_round_trip_with_its_key_intact() -> None:
    """A MatchRun snapshot stores this. If a round trip changed the key, a stored
    run could no longer be checked against the order it recorded."""
    for pair in every_pair():
        restored = json.loads(json.dumps(pair.explanation))
        assert restored["sort_key"] == list(pair.key.as_tuple())
