"""The golden corpus: tasks, adjudication and scoring.

Written before the implementation. This is the binding constraint on the whole
project (KI-012): every figure produced so far is a yield or an
internal-consistency rate, and no extracted value has been compared to a human
reading. `OCR-001` cannot leave `BLOCKED_BY_BENCHMARK` until it has been.

Three design decisions carry evidence and are tested here:

* **The unit is the cell, not the document.** 199 documents hold 2,189 HLA
  cells, 948 of which the pipeline resolved. Zero failures over 948 observations
  bounds false acceptance at 0.32% by the rule of three; 199 observations would
  bound it only at 1.5% and could not support the claim at all.
* **The labeller never sees the OCR proposal.** It is kept in a separate file
  the page does not load, because a proposal shown beside a blurry crop is an
  anchor, and an anchored labeller measures agreement rather than truth.
* **Two people label, a third adjudicates.** Double entry by a different
  operator catches 88.3% of errors against 69.0% for the same operator twice
  (Kawado 2003), and letting the two entrants reconcile introduces new errors
  (Barchard 2020), so mismatches go to a third person against the image.
"""

from __future__ import annotations

import pytest

from kidneymatch.review.golden import (
    Adjudication,
    CellLabel,
    LabelState,
    ScoreReport,
    adjudicate,
    score_against_pipeline,
)


def label(state: LabelState, alleles: tuple[str, ...] = (), annotator: str = "a") -> CellLabel:
    return CellLabel(state=state, alleles=alleles, annotator=annotator)


VALUE = LabelState.VALUE
BLANK = LabelState.BLANK
NOT_PRINTED = LabelState.NOT_PRINTED
UNREADABLE = LabelState.UNREADABLE


# --- adjudication --------------------------------------------------------


def test_two_labellers_who_agree_need_no_adjudication() -> None:
    result = adjudicate(
        {"c1": label(VALUE, ("11", "15"), "a")},
        {"c1": label(VALUE, ("11", "15"), "b")},
    )
    assert result.agreed["c1"].alleles == ("11", "15")
    assert result.disputed == {}


def test_a_disagreement_is_not_resolved_by_either_labeller() -> None:
    """Letting the two entrants reconcile introduces new errors, so a mismatch
    is a question for a third person against the image."""
    result = adjudicate(
        {"c1": label(VALUE, ("11",), "a")},
        {"c1": label(VALUE, ("13",), "b")},
    )
    assert "c1" not in result.agreed
    assert result.disputed["c1"] == (label(VALUE, ("11",), "a"), label(VALUE, ("13",), "b"))


def test_the_same_value_in_a_different_order_still_agrees() -> None:
    """A locus has two alleles and the form's print order is not a fact."""
    result = adjudicate(
        {"c1": label(VALUE, ("11", "15"), "a")},
        {"c1": label(VALUE, ("15", "11"), "b")},
    )
    assert "c1" in result.agreed


def test_differing_states_disagree_even_with_the_same_alleles() -> None:
    result = adjudicate({"c1": label(VALUE, (), "a")}, {"c1": label(BLANK, (), "b")})
    assert "c1" in result.disputed


def test_a_cell_only_one_labeller_reached_is_disputed_not_dropped() -> None:
    """Silently taking the single answer would make coverage look complete."""
    result = adjudicate({"c1": label(VALUE, ("11",), "a")}, {})
    assert "c1" in result.disputed


def test_a_third_persons_answer_settles_a_dispute() -> None:
    result = adjudicate(
        {"c1": label(VALUE, ("11",), "a")},
        {"c1": label(VALUE, ("13",), "b")},
        adjudicated={"c1": label(VALUE, ("13",), "c")},
    )
    assert result.agreed["c1"].alleles == ("13",)
    assert result.agreed["c1"].annotator == "c"
    assert result.disputed == {}


# --- scoring -------------------------------------------------------------


def truth(**cells: CellLabel) -> Adjudication:
    return Adjudication(agreed=dict(cells), disputed={})


def test_a_matching_resolved_cell_is_correct() -> None:
    report = score_against_pipeline(
        truth(c1=label(VALUE, ("11", "15"))),
        pipeline={"c1": ("RESOLVED", "DRB1", ("11", "15"))},
    )
    assert report.correct == 1
    assert report.false_acceptances == []


def test_a_resolved_cell_with_the_wrong_value_is_a_false_acceptance() -> None:
    """The failure the whole project exists to prevent."""
    report = score_against_pipeline(
        truth(c1=label(VALUE, ("11", "15"))),
        pipeline={"c1": ("RESOLVED", "DRB1", ("11", "13"))},
    )
    assert report.false_acceptances == ["c1"]
    assert report.passed is False


@pytest.mark.parametrize("state", [BLANK, NOT_PRINTED, UNREADABLE])
def test_resolving_a_cell_the_human_could_not_read_is_a_false_acceptance(
    state: LabelState,
) -> None:
    """The pipeline claimed a value where a person sees none."""
    report = score_against_pipeline(
        truth(c1=label(state)), pipeline={"c1": ("RESOLVED", "DRB1", ("11",))}
    )
    assert report.false_acceptances == ["c1"]


def test_abstaining_where_a_value_exists_is_a_miss_not_a_failure() -> None:
    """Recall loss is a cost, not a harm: the record simply stays incomplete."""
    report = score_against_pipeline(
        truth(c1=label(VALUE, ("11",))),
        pipeline={"c1": ("REVIEW_REQUIRED", "DRB1", ())},
    )
    assert report.missed == 1
    assert report.false_acceptances == []
    assert report.passed is True


def test_abstaining_where_there_is_nothing_is_a_correct_abstention() -> None:
    report = score_against_pipeline(
        truth(c1=label(NOT_PRINTED)), pipeline={"c1": ("UNKNOWN", "DRB1", ())}
    )
    assert report.correct_abstentions == 1
    assert report.passed is True


def test_a_partial_read_of_a_two_allele_cell_is_a_false_acceptance() -> None:
    """Publishing one allele of a heterozygous pair as if complete is the
    KI-015 failure, and the golden set is where it becomes measurable."""
    report = score_against_pipeline(
        truth(c1=label(VALUE, ("11", "15"))),
        pipeline={"c1": ("RESOLVED", "DRB1", ("11",))},
    )
    assert report.false_acceptances == ["c1"]


def test_a_partial_read_that_declares_itself_is_a_partial_not_a_false_acceptance() -> None:
    """KI-015's fix made `second_allele` explicit: one value in a cell means one
    value was READ, and the record says so. A reading that is right as far as it
    goes, and declares that it stopped, is an incomplete record — a cost — not a
    wrong one. Measured on the first 165 anchored labels, both non-DRBX
    'contradictions' were exactly this: `B*NN` with the second allele UNREAD
    against a human pair containing that allele.

    Without the declaration the rule above stands unchanged.
    """
    report = score_against_pipeline(
        truth(c1=label(VALUE, ("44", "52"))),
        pipeline={"c1": ("RESOLVED", "B", ("44",), "UNREAD")},
    )
    assert report.partial == 1
    assert report.false_acceptances == []
    assert report.per_locus["B"].partial == 1
    assert report.passed is True
    assert report.scored == 1


def test_a_declared_partial_read_with_the_wrong_allele_is_a_false_acceptance() -> None:
    """Declaring the second allele unread excuses incompleteness, never error."""
    report = score_against_pipeline(
        truth(c1=label(VALUE, ("44", "52"))),
        pipeline={"c1": ("RESOLVED", "B", ("45",), "UNREAD")},
    )
    assert report.false_acceptances == ["c1"]
    assert report.partial == 0


def test_a_single_allele_claimed_complete_against_a_pair_is_a_false_acceptance() -> None:
    """`READ` means the pipeline claims both alleles were seen; one value with
    that claim against a printed pair is the KI-015 failure exactly."""
    report = score_against_pipeline(
        truth(c1=label(VALUE, ("44", "52"))),
        pipeline={"c1": ("RESOLVED", "B", ("44",), "READ")},
    )
    assert report.false_acceptances == ["c1"]


def test_a_declared_partial_read_against_a_single_printed_allele_is_correct() -> None:
    """The form printed one allele and the pipeline read it: complete agreement,
    whatever the pipeline believes about a second column it could not see."""
    report = score_against_pipeline(
        truth(c1=label(VALUE, ("44",))),
        pipeline={"c1": ("RESOLVED", "B", ("44",), "UNREAD")},
    )
    assert report.correct == 1
    assert report.partial == 0


def test_a_disputed_cell_is_never_scored() -> None:
    """An unresolved disagreement is not ground truth."""
    result = Adjudication(agreed={}, disputed={"c1": (label(VALUE, ("11",)), label(BLANK))})
    report = score_against_pipeline(result, pipeline={"c1": ("RESOLVED", "DRB1", ("11",))})
    assert report.scored == 0
    assert report.unadjudicated == 1


def test_the_report_bounds_the_error_rate_by_the_rule_of_three() -> None:
    """Zero failures in n observations bounds the rate at 3/n with 95%
    confidence, which is why the CELL is the unit."""
    report = score_against_pipeline(
        truth(**{f"c{i}": label(VALUE, ("11",)) for i in range(300)}),
        pipeline={f"c{i}": ("RESOLVED", "DRB1", ("11",)) for i in range(300)},
    )
    assert report.passed is True
    assert report.false_acceptance_upper_bound == pytest.approx(0.01, abs=1e-4)


def test_the_bound_is_undefined_with_nothing_accepted() -> None:
    report = score_against_pipeline(truth(), pipeline={})
    assert report.false_acceptance_upper_bound is None


def test_per_locus_results_are_reported() -> None:
    """A per-cell bound assumes independent trials; cells within one family are
    not, so the per-locus split has to be visible."""
    report: ScoreReport = score_against_pipeline(
        truth(c1=label(VALUE, ("11",)), c2=label(VALUE, ("03",))),
        pipeline={"c1": ("RESOLVED", "DRB1", ("11",)), "c2": ("RESOLVED", "DQB1", ("03",))},
    )
    assert report.per_locus["DRB1"].correct == 1
    assert report.per_locus["DQB1"].correct == 1


# --- presence-typed genes -----------------------------------------------


def test_absent_is_a_reading_of_its_own_for_a_presence_typed_gene() -> None:
    """DRB3/4/5 resolve to PRESENT or ABSENT, not to alleles.

    Before `ABSENT` existed a human could only say PRESENT_ONLY, and the score
    counted any pipeline value as correct against it, so a form that printed
    "not present" could never contradict a pipeline that said PRESENT.
    """
    truth = adjudicate(
        {"d:DRB3": label(LabelState.ABSENT), "d:DRB4": label(LabelState.PRESENT_ONLY)},
        {
            "d:DRB3": label(LabelState.ABSENT, annotator="b"),
            "d:DRB4": label(LabelState.PRESENT_ONLY, annotator="b"),
        },
    )
    right = score_against_pipeline(
        truth,
        {"d:DRB3": ("RESOLVED", "DRB3", ("ABSENT",)), "d:DRB4": ("RESOLVED", "DRB4", ("PRESENT",))},
    )
    assert right.correct == 2 and not right.false_acceptances

    wrong = score_against_pipeline(
        truth,
        {"d:DRB3": ("RESOLVED", "DRB3", ("PRESENT",)), "d:DRB4": ("RESOLVED", "DRB4", ("ABSENT",))},
    )
    assert wrong.false_acceptances == ["d:DRB3", "d:DRB4"]

    declined = score_against_pipeline(truth, {"d:DRB3": ("REVIEW_REQUIRED", "DRB3", ())})
    assert declined.missed == 1
