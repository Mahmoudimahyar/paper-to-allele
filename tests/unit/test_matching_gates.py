"""The bucket gates, and the two passes that stop a blocked pair looking merely thin.

`MATCH-IMMUNE-001`. Policy: `docs/clinical/MATCHING_POLICY_V2.md` section 5.

A blocked pair is not a low-ranked pair. It has a status of its own, and the
gates exist so that an incompatible or crossmatch-blocked donor never appears
anywhere a person could act on it. That makes the *assignment order* the thing
worth testing rather than the buckets themselves.

The defect these tests are built around: a pair can satisfy several entry
conditions at once, and the display order puts the informational buckets first.
Scanning in display order would therefore let `INSUFFICIENT_HLA` hide
`BLOCKED_POSITIVE_CROSSMATCH`, and the pair would be shown as under-typed, whose
next action is "obtain HLA typing", when the true next action is that the direct
pathway is closed. So every blocking condition is evaluated before any
informational one, and each blocking reason that applied is still reported.

The rest is the ABO asymmetry carried through to the buckets: weak evidence may
exclude a pair but may never clear one, so a patient-reported group that happens
to be compatible reaches `PROVISIONAL_ABO` and never `RANKED`, while the same
weak evidence pointing at an incompatibility still blocks.

A third case sits behind those two. A group that is present but unreadable (an
OCR garble, an Rh-carrying string, a blank or whitespace-only cell) is a MISSING
group rather than a weak one, so it belongs in `INSUFFICIENT_ABO`.
`PROVISIONAL_ABO` is a ranked bucket, and a value nobody could read must never
reach a ranked bucket at all: the gate never established compatibility for it,
so the pair would be shown to a coordinator as a candidate on evidence that
does not exist.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from kidneymatch.matching.abo import AboGate, AboProvenance
from kidneymatch.matching.gates import (
    Bucket,
    BucketDecision,
    CrossmatchState,
    PairInputs,
    assign_bucket,
)
from kidneymatch.matching.mismatch import (
    SCORED_LOCI,
    LocusMismatch,
    MismatchStatus,
    MismatchVector,
)

pytestmark = pytest.mark.task("MATCH-IMMUNE-001")

MEASURED = AboProvenance.LABORATORY_MEASURED
REPORTED = AboProvenance.PATIENT_REPORTED_ON_FORM
CAPTION = AboProvenance.CAPTION_CLAIM
NO_PROVENANCE = AboProvenance.UNKNOWN


# --- synthetic inputs -----------------------------------------------------


def _known(count: int) -> LocusMismatch:
    return LocusMismatch(
        MismatchStatus.KNOWN, count=count, lower=count, upper=count, compared_depth=2
    )


def _range(lower: int, upper: int) -> LocusMismatch:
    return LocusMismatch(MismatchStatus.RANGE, lower=lower, upper=upper, compared_depth=2)


def _unknown(reason: str = "donor: locus not typed") -> LocusMismatch:
    return LocusMismatch(MismatchStatus.UNKNOWN, reason=reason)


def vector(**overrides: LocusMismatch) -> MismatchVector:
    """A fully typed, zero-mismatch vector with named loci replaced."""
    per_locus = {locus: _known(0) for locus in SCORED_LOCI}
    per_locus.update(overrides)
    return MismatchVector(per_locus)


#: A pair that is clear on every gate, so a test only has to state its defect.
_CLEAR = PairInputs(
    donor_group="O",
    recipient_group="A",
    donor_provenance=MEASURED,
    recipient_provenance=MEASURED,
)


def pair(**overrides: object) -> PairInputs:
    return replace(_CLEAR, **overrides)  # type: ignore[arg-type]


def one_of_each_bucket() -> dict[Bucket, BucketDecision]:
    """The minimal defect that should send a pair to each bucket."""
    return {
        Bucket.RANKED: assign_bucket(pair(), vector()),
        Bucket.PROVISIONAL_ABO: assign_bucket(pair(donor_provenance=REPORTED), vector()),
        Bucket.INSUFFICIENT_HLA: assign_bucket(pair(), vector(DRB1=_unknown())),
        Bucket.INSUFFICIENT_ABO: assign_bucket(pair(donor_group=None), vector()),
        Bucket.ABO_INCOMPATIBLE: assign_bucket(
            pair(donor_group="A", recipient_group="O"), vector()
        ),
        Bucket.BLOCKED_DSA_OR_LAB_REVIEW: assign_bucket(pair(dsa_conflicts=("B*44",)), vector()),
        Bucket.BLOCKED_POSITIVE_CROSSMATCH: assign_bucket(
            pair(crossmatch=CrossmatchState.POSITIVE), vector()
        ),
        Bucket.EXCLUDED_NON_CLINICAL: assign_bucket(
            pair(recipient_eligible=False, ineligibility_reason="consent withdrawn"), vector()
        ),
    }


# --- every bucket is reachable by its own condition ------------------------


@pytest.mark.parametrize("expected", list(Bucket))
def test_each_bucket_is_reached_by_its_own_entry_condition(expected: Bucket) -> None:
    """A bucket nothing can reach is a gate that is not doing its job."""
    assert one_of_each_bucket()[expected].bucket is expected


@pytest.mark.parametrize("bucket", list(Bucket))
def test_every_decision_carries_a_reason_and_a_next_action(bucket: Bucket) -> None:
    """A bucket that does not say why, or what to do next, cannot be reviewed."""
    decision = one_of_each_bucket()[bucket]
    assert decision.reasons and all(decision.reasons)
    assert decision.next_action
    assert decision.abo is not None, "the ABO detail is carried into every bucket"


def test_a_clear_pair_measured_on_both_sides_is_ranked() -> None:
    decision = assign_bucket(pair(), vector())
    assert decision.bucket is Bucket.RANKED
    assert decision.abo is not None
    assert decision.abo.gate is AboGate.COMPATIBLE
    assert decision.blockers == ()
    assert decision.next_action == "proceed to clinical evaluation"


def test_an_ineligible_party_excludes_the_pair_on_either_side() -> None:
    for side in ("donor_eligible", "recipient_eligible"):
        decision = assign_bucket(pair(**{side: False}, ineligibility_reason="quarantine"), vector())
        assert decision.bucket is Bucket.EXCLUDED_NON_CLINICAL
        assert decision.reasons == ("quarantine",)
        assert decision.next_action == "none"


def test_an_exclusion_without_a_stated_reason_still_states_one() -> None:
    decision = assign_bucket(pair(donor_eligible=False), vector())
    assert decision.bucket is Bucket.EXCLUDED_NON_CLINICAL
    assert decision.reasons[0]
    assert decision.blockers == decision.reasons


def test_a_dsa_conflict_names_the_values_it_is_about() -> None:
    decision = assign_bucket(pair(dsa_conflicts=("B*44", "DQB1*03")), vector())
    assert decision.bucket is Bucket.BLOCKED_DSA_OR_LAB_REVIEW
    assert "B*44" in decision.reasons[0]
    assert "DQB1*03" in decision.reasons[0]
    assert decision.next_action == "laboratory review"


@pytest.mark.parametrize(
    "state",
    [
        CrossmatchState.NOT_PERFORMED,
        CrossmatchState.NEGATIVE,
        CrossmatchState.INDETERMINATE,
        CrossmatchState.EXPIRED,
    ],
)
def test_only_a_positive_crossmatch_closes_the_direct_pathway(state: CrossmatchState) -> None:
    """Section 5 blocks on a valid current POSITIVE physical crossmatch only.

    An indeterminate or expired result is not a positive one, so it does not
    block; what carries it forward is `antibody_status`, which stays
    `ANTIBODY_UNKNOWN` in every one of these cases.
    """
    decision = assign_bucket(pair(crossmatch=state), vector())
    assert decision.bucket is not Bucket.BLOCKED_POSITIVE_CROSSMATCH
    assert decision.antibody_status == "ANTIBODY_UNKNOWN"


# --- the two passes -------------------------------------------------------


def test_under_typed_and_crossmatch_positive_is_blocked_not_merely_under_typed() -> None:
    """The defect the design review caught, asserted directly.

    `INSUFFICIENT_HLA` sits EARLIER in display order than
    `BLOCKED_POSITIVE_CROSSMATCH`, so a single pass in display order would
    return the informational bucket and tell a coordinator to go and obtain HLA
    typing for a pair whose direct pathway is already closed.
    """
    decision = assign_bucket(
        pair(crossmatch=CrossmatchState.POSITIVE), vector(DRB1=_unknown(), B=_unknown())
    )
    assert Bucket.INSUFFICIENT_HLA.rank < Bucket.BLOCKED_POSITIVE_CROSSMATCH.rank
    assert decision.bucket is Bucket.BLOCKED_POSITIVE_CROSSMATCH
    assert decision.next_action == "direct pathway blocked"


def test_missing_blood_group_does_not_hide_a_crossmatch_block_either() -> None:
    decision = assign_bucket(pair(donor_group=None, crossmatch=CrossmatchState.POSITIVE), vector())
    assert decision.bucket is Bucket.BLOCKED_POSITIVE_CROSSMATCH


def test_an_abo_incompatibility_is_not_hidden_by_thin_typing() -> None:
    decision = assign_bucket(
        pair(donor_group="AB", recipient_group="O"), vector(DRB1=_unknown(), B=_unknown())
    )
    assert decision.bucket is Bucket.ABO_INCOMPATIBLE


@pytest.mark.invariant("MATCH-001", "ABO/DSA/crossmatch gates precede HLA heuristic")
def test_the_blocking_order_is_severity_not_display_order() -> None:
    """Peel the blocking conditions off one at a time and watch the order."""
    everything = pair(
        donor_group="A",
        recipient_group="O",
        donor_eligible=False,
        ineligibility_reason="consent withdrawn",
        crossmatch=CrossmatchState.POSITIVE,
        dsa_conflicts=("B*44",),
    )
    assert assign_bucket(everything, vector()).bucket is Bucket.EXCLUDED_NON_CLINICAL

    eligible = replace(everything, donor_eligible=True, ineligibility_reason="")
    assert assign_bucket(eligible, vector()).bucket is Bucket.BLOCKED_POSITIVE_CROSSMATCH

    no_crossmatch = replace(eligible, crossmatch=CrossmatchState.NOT_PERFORMED)
    assert assign_bucket(no_crossmatch, vector()).bucket is Bucket.BLOCKED_DSA_OR_LAB_REVIEW

    no_dsa = replace(no_crossmatch, dsa_conflicts=())
    assert assign_bucket(no_dsa, vector()).bucket is Bucket.ABO_INCOMPATIBLE


def test_every_applicable_blocking_reason_is_reported_not_only_the_winning_one() -> None:
    """One bucket, but a pair blocked three ways must report all three.

    A coordinator who clears the crossmatch and finds the pair still blocked on
    ABO has been told twice about one problem; the explanation carries every
    reason so the review is done once.
    """
    decision = assign_bucket(
        pair(
            donor_group="A",
            recipient_group="O",
            crossmatch=CrossmatchState.POSITIVE,
            dsa_conflicts=("DQB1*03",),
        ),
        vector(),
    )
    assert decision.bucket is Bucket.BLOCKED_POSITIVE_CROSSMATCH
    assert len(decision.blockers) == 3
    joined = " | ".join(decision.blockers)
    assert "crossmatch" in joined
    assert "DQB1*03" in joined
    assert "cannot donate" in joined
    assert decision.reasons[0] in decision.blockers, "the winning reason is one of the blockers"


def test_an_informational_bucket_reports_no_blockers() -> None:
    """`blockers` is what stops the pair. A thin pair is not stopped."""
    for decision in (
        assign_bucket(pair(), vector()),
        assign_bucket(pair(donor_provenance=REPORTED), vector()),
        assign_bucket(pair(), vector(B=_unknown())),
        assign_bucket(pair(recipient_group=None), vector()),
        assign_bucket(pair(recipient_group="Z"), vector()),
    ):
        assert decision.blockers == ()


# --- the ABO asymmetry, carried into the buckets --------------------------


@pytest.mark.parametrize(
    ("donor_provenance", "recipient_provenance"),
    [
        (REPORTED, MEASURED),
        (MEASURED, REPORTED),
        (REPORTED, REPORTED),
        (CAPTION, MEASURED),
        (NO_PROVENANCE, MEASURED),
    ],
)
def test_a_compatible_patient_reported_group_is_provisional_never_ranked(
    donor_provenance: AboProvenance, recipient_provenance: AboProvenance
) -> None:
    """The letterhead disclaims its own blood-group field (KI-014), so this
    evidence may not clear a pair even when the letters agree."""
    decision = assign_bucket(
        pair(donor_provenance=donor_provenance, recipient_provenance=recipient_provenance),
        vector(),
    )
    assert decision.bucket is Bucket.PROVISIONAL_ABO
    assert decision.abo is not None
    assert decision.abo.gate is AboGate.UNKNOWN
    assert decision.next_action == "obtain a laboratory blood group"


@pytest.mark.parametrize(
    ("donor_provenance", "recipient_provenance"),
    [(REPORTED, REPORTED), (REPORTED, MEASURED), (CAPTION, CAPTION), (NO_PROVENANCE, MEASURED)],
)
def test_an_incompatible_patient_reported_group_still_blocks_the_pair(
    donor_provenance: AboProvenance, recipient_provenance: AboProvenance
) -> None:
    """The other half of the asymmetry: a wrong exclusion costs a missed match,
    a wrong clearance costs a transfused incompatible kidney."""
    decision = assign_bucket(
        pair(
            donor_group="AB",
            recipient_group="B",
            donor_provenance=donor_provenance,
            recipient_provenance=recipient_provenance,
        ),
        vector(),
    )
    assert decision.bucket is Bucket.ABO_INCOMPATIBLE
    assert decision.next_action == "not a candidate on the direct pathway"


@pytest.mark.parametrize(
    ("donor_group", "recipient_group"), [(None, "A"), ("O", None), (None, None)]
)
def test_a_missing_blood_group_is_insufficient_abo(
    donor_group: str | None, recipient_group: str | None
) -> None:
    decision = assign_bucket(
        pair(donor_group=donor_group, recipient_group=recipient_group), vector()
    )
    assert decision.bucket is Bucket.INSUFFICIENT_ABO
    assert not decision.bucket.is_ranked


@pytest.mark.parametrize(
    ("donor_group", "recipient_group"),
    [
        ("Z", "A"),
        ("O+", "A"),
        ("", "A"),
        ("   ", "A"),
        ("\t", "A"),
        ("AB", "0"),
        ("O", ""),
        ("O", " "),
        ("O", "B-"),
    ],
)
def test_a_blood_group_that_is_not_a_group_is_insufficient_not_provisional(
    donor_group: str, recipient_group: str
) -> None:
    """Section 5: `INSUFFICIENT_ABO` is "blood group unknown on either side".

    A stored value that is not an ABO group leaves the group unknown just as
    surely as an empty cell does. `O+` carries Rh, which is a different
    question, and `0` is the digit the recogniser produces for the letter, so
    both are real shapes from this archive rather than invented ones. A cell
    holding only spaces or a tab is that same absence with something printed in
    it, which is the shape a "did we get a value?" test gets wrong.

    A present but unreadable group is a MISSING group, not a weak one, so it
    may not sit in a ranked bucket: `AB` into a garbled `0` would otherwise be
    an ABO-incompatible pair offered as a provisional candidate. Both
    provenances here are LABORATORY_MEASURED, so nothing but the unreadable
    value itself can be sending the pair to `INSUFFICIENT_ABO`.
    """
    decision = assign_bucket(
        pair(donor_group=donor_group, recipient_group=recipient_group), vector()
    )
    assert decision.bucket is Bucket.INSUFFICIENT_ABO
    assert not decision.bucket.is_ranked
    assert decision.abo is not None
    assert decision.abo.gate is AboGate.UNKNOWN
    assert not decision.abo.blocks_pair, "unreadable is not incompatible, it is unknown"
    assert decision.next_action == "obtain a laboratory blood group"
    assert decision.blockers == (), "an unreadable group under-evidences a pair, it does not block"


@pytest.mark.parametrize("unreadable", ["Z", "O+", "", "   ", "0", "AB+", "??"])
@pytest.mark.parametrize("provenance", [MEASURED, REPORTED, CAPTION, NO_PROVENANCE])
def test_an_unreadable_group_reaches_no_ranked_bucket_at_any_provenance(
    unreadable: str, provenance: AboProvenance
) -> None:
    """Provenance grades how good a group is; it cannot turn a non-group into
    one. `PROVISIONAL_ABO` is what weak provenance over a readable, compatible
    pair earns, and an unreadable value may not borrow that bucket from it."""
    decision = assign_bucket(pair(donor_group=unreadable, donor_provenance=provenance), vector())
    assert decision.bucket is Bucket.INSUFFICIENT_ABO
    assert not decision.bucket.is_ranked


def test_a_garbled_group_is_not_ranked_where_the_letter_it_stands_for_would_block() -> None:
    """The concrete harm, stated as the two outcomes it sits between.

    `0` is what the recogniser prints for `O`. Read as the letter, an `AB`
    donor into an `O` recipient is ABO-incompatible and the direct pathway is
    closed. Left unreadable, the pair belongs in `INSUFFICIENT_ABO`, whose next
    action is to go and obtain a laboratory group. The one outcome available
    under neither reading is a ranked bucket, which is exactly where a
    coordinator would see a candidate to act on.
    """
    garbled = assign_bucket(pair(donor_group="AB", recipient_group="0"), vector())
    resolved = assign_bucket(pair(donor_group="AB", recipient_group="O"), vector())
    assert resolved.bucket is Bucket.ABO_INCOMPATIBLE
    assert garbled.bucket is Bucket.INSUFFICIENT_ABO
    assert not garbled.bucket.is_ranked


@pytest.mark.parametrize("garble", ["Z", "O+", "XX"])
def test_the_reason_names_the_value_that_could_not_be_read(garble: str) -> None:
    """A coordinator sent to obtain a laboratory group has to be told which
    printed value stopped the pair."""
    decision = assign_bucket(pair(donor_group=garble), vector())
    assert decision.bucket is Bucket.INSUFFICIENT_ABO
    assert garble in decision.reasons[0]


@pytest.mark.parametrize(
    ("donor_group", "recipient_group"), [(" O ", "A"), ("o", "a"), ("ab", "AB"), ("B\n", "AB")]
)
def test_a_padded_or_lowercase_group_is_still_a_readable_group(
    donor_group: str, recipient_group: str
) -> None:
    """The other edge of the same rule: it must reject values that are not
    groups, not merely untidy ones. Case and surrounding whitespace are
    transcription noise, and a laboratory-measured compatible pair underneath
    that noise still reaches `RANKED`."""
    decision = assign_bucket(
        pair(donor_group=donor_group, recipient_group=recipient_group), vector()
    )
    assert decision.bucket is Bucket.RANKED
    assert decision.bucket.is_ranked


@pytest.mark.parametrize("donor_group", [None, "O+", "Z", "   "])
def test_an_unknown_blood_group_outranks_thin_typing_in_the_informational_pass(
    donor_group: str | None,
) -> None:
    """Section 5's informational order is ABO, then HLA, then provisional.

    An unreadable group is a missing one, so it takes the same place in that
    order as an absent one rather than yielding to the HLA bucket.
    """
    decision = assign_bucket(pair(donor_group=donor_group), vector(DRB1=_unknown(), B=_unknown()))
    assert decision.bucket is Bucket.INSUFFICIENT_ABO


@pytest.mark.parametrize("donor_group", [None, "O+", ""])
def test_an_unreadable_blood_group_does_not_hide_a_crossmatch_block_either(
    donor_group: str | None,
) -> None:
    """A group nobody could read is informational, and the blocking pass runs
    first, so such a pair still reads as blocked rather than as under-evidenced."""
    decision = assign_bucket(
        pair(donor_group=donor_group, crossmatch=CrossmatchState.POSITIVE), vector()
    )
    assert decision.bucket is Bucket.BLOCKED_POSITIVE_CROSSMATCH


# --- what makes a pair rankable at all ------------------------------------


@pytest.mark.parametrize("missing", ["DRB1", "B"])
def test_an_unknown_drb1_or_b_leaves_the_pair_without_a_level(missing: str) -> None:
    decision = assign_bucket(pair(), vector(**{missing: _unknown()}))
    assert decision.bucket is Bucket.INSUFFICIENT_HLA
    assert missing in decision.reasons[0]
    assert decision.next_action == "obtain HLA typing"


def test_a_locus_absent_from_the_vector_is_not_a_zero_mismatch() -> None:
    """UNKNOWN is never zero, and neither is a locus that was never compared."""
    decision = assign_bucket(pair(), MismatchVector({"A": _known(0)}))
    assert decision.bucket is Bucket.INSUFFICIENT_HLA


def test_only_drb1_and_b_decide_whether_a_level_can_be_given() -> None:
    """A, C and DQB1 refine the order; they do not gate it."""
    decision = assign_bucket(pair(), vector(A=_unknown(), C=_unknown(), DQB1=_unknown()))
    assert decision.bucket is Bucket.RANKED


def test_a_partially_typed_locus_still_receives_a_level() -> None:
    """One allele read is a range, not an absence, and a range has a worse end
    that can decide a level. Sending it to `INSUFFICIENT_HLA` would discard a
    usable bound."""
    decision = assign_bucket(pair(), vector(DRB1=_range(0, 1), B=_range(1, 2)))
    assert decision.bucket is Bucket.RANKED


# --- antibody status is stated, never omitted -----------------------------


@pytest.mark.parametrize("bucket", list(Bucket))
def test_antibody_status_is_present_in_every_bucket_and_reads_unknown(bucket: Bucket) -> None:
    """The archive holds no antibody, panel-reactive antibody or crossmatch
    data at all. Absence of antibody data is not evidence of absence of
    antibody, so the status is carried rather than left out."""
    assert one_of_each_bucket()[bucket].antibody_status == "ANTIBODY_UNKNOWN"


def test_antibody_status_is_unknown_even_when_a_crossmatch_was_negative() -> None:
    """A negative crossmatch on one donor is not a panel-reactive antibody
    screen, so it does not turn the pair's antibody status into a known one."""
    decision = assign_bucket(pair(crossmatch=CrossmatchState.NEGATIVE), vector())
    assert decision.antibody_status == "ANTIBODY_UNKNOWN"


# --- display order and rankability ----------------------------------------


def test_bucket_rank_is_the_display_sequence_of_the_policy() -> None:
    expected = [
        Bucket.RANKED,
        Bucket.PROVISIONAL_ABO,
        Bucket.INSUFFICIENT_HLA,
        Bucket.INSUFFICIENT_ABO,
        Bucket.ABO_INCOMPATIBLE,
        Bucket.BLOCKED_DSA_OR_LAB_REVIEW,
        Bucket.BLOCKED_POSITIVE_CROSSMATCH,
        Bucket.EXCLUDED_NON_CLINICAL,
    ]
    assert [bucket.rank for bucket in expected] == list(range(len(expected)))
    assert sorted(Bucket, key=lambda bucket: bucket.rank) == expected
    assert len({bucket.rank for bucket in Bucket}) == len(list(Bucket)), "ranks are unique"


def test_the_bucket_is_position_zero_of_the_sort_so_gates_precede_the_heuristic() -> None:
    """Any blocked or incomplete pair sorts after every rankable one, whatever
    its HLA level, because the bucket rank is the first element of the tuple."""
    decisions = one_of_each_bucket()
    ranked = [b.rank for b in decisions if b.is_ranked]
    rest = [b.rank for b in decisions if not b.is_ranked]
    assert max(ranked) < min(rest)


def test_is_ranked_is_true_only_for_ranked_and_provisional_abo() -> None:
    assert {bucket for bucket in Bucket if bucket.is_ranked} == {
        Bucket.RANKED,
        Bucket.PROVISIONAL_ABO,
    }


@pytest.mark.parametrize(
    "inputs",
    [
        pair(donor_eligible=False),
        pair(crossmatch=CrossmatchState.POSITIVE),
        pair(dsa_conflicts=("A*02",)),
        pair(donor_group="B", recipient_group="A"),
    ],
)
@pytest.mark.invariant("MATCH-001", "a blocking bucket is never displayed as a low rank")
def test_a_blocked_pair_never_lands_in_a_ranked_bucket(inputs: PairInputs) -> None:
    """A blocked pair is not a low-ranked pair, and must not appear at the
    bottom of a ranked list where someone could act on it."""
    assert not assign_bucket(inputs, vector()).bucket.is_ranked


# --- what the gates may not see -------------------------------------------


def test_the_gates_cannot_be_handed_anything_they_may_not_consider() -> None:
    """`AGENTS.md`: the matching core may not read compensation, and the gates
    have no field for an identifier, message text or a preference claim either.
    A gate that could see an amount is a gate that could be bought."""
    assert set(PairInputs.__dataclass_fields__) == {
        "donor_group",
        "recipient_group",
        "donor_provenance",
        "recipient_provenance",
        "donor_eligible",
        "recipient_eligible",
        "ineligibility_reason",
        "crossmatch",
        "dsa_conflicts",
    }
