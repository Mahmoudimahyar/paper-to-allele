"""The golden corpus: what a human said, and what it says about the pipeline.

This is the binding constraint on the project (KI-012). Every figure produced so
far is a yield or an internal-consistency rate; no extracted value has been
compared to a human reading, and `OCR-001` cannot leave
`BLOCKED_BY_BENCHMARK` until one has.

## Three decisions, each with its evidence

**The unit is the cell, not the document.** The 199 sampled documents hold 2,189
HLA cells, of which the pipeline resolved 948. By the rule of three, zero
failures in n observations bounds the error rate at 3/n with 95% confidence, so
948 cells bound false acceptance at 0.32%. 199 documents would bound it at 1.5%
and could not support any precision claim at all.

**The labeller never sees the OCR proposal.** It lives in a separate file the
labelling page does not load. A proposal shown beside a blurry crop is an
anchor, and an anchored labeller measures agreement rather than truth.

**Two people label and a third adjudicates.** Double entry by a *different*
operator detects 88.3% of errors against 69.0% for the same operator twice
(Kawado 2003). Letting the two entrants reconcile is worse than useless — they
make the entries match, sometimes by introducing new errors (Barchard 2020) — so
a mismatch goes to a third person against the image.

## What counts as a failure

Only two outcomes are failures, and both mean the pipeline asserted something
untrue: it resolved a cell to a value the human read differently, or it resolved
a cell the human could not read at all. Abstaining where a value exists is a
*miss* — the record stays incomplete, which is a cost rather than a harm.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class LabelState(StrEnum):
    """What a human found in one cell.

    `NOT_PRINTED`, `BLANK` and `UNREADABLE` are kept apart because they mean
    different things about the laboratory and about the pipeline: the form does
    not report this gene, the form reports it and the laboratory left it empty,
    or it is there and cannot be read.
    """

    VALUE = "VALUE"
    NOT_PRINTED = "NOT_PRINTED"
    BLANK = "BLANK"
    UNREADABLE = "UNREADABLE"
    PRESENT_ONLY = "PRESENT_ONLY"
    NOT_A_REPORT = "NOT_A_REPORT"


class Resolution(StrEnum):
    """How precisely the form states the value."""

    FIRST_FIELD = "FIRST_FIELD"
    TWO_FIELD = "TWO_FIELD"
    SEROLOGY = "SEROLOGY"
    UNCLEAR = "UNCLEAR"


@dataclass(frozen=True, slots=True)
class CellLabel:
    """One person's reading of one cell."""

    state: LabelState
    alleles: tuple[str, ...] = ()
    resolution: Resolution | None = None
    annotator: str = ""
    unsure: bool = False

    def same_reading(self, other: CellLabel) -> bool:
        """Do these two people say the same thing about the cell?

        The print order of two alleles is not a fact about the patient, so it is
        not part of the reading.
        """
        return self.state is other.state and sorted(self.alleles) == sorted(other.alleles)


@dataclass(frozen=True, slots=True)
class Adjudication:
    """Ground truth so far, and what is still in dispute."""

    agreed: dict[str, CellLabel]
    disputed: dict[str, tuple[CellLabel | None, CellLabel | None]]


@dataclass(slots=True)
class LocusTally:
    correct: int = 0
    false_acceptances: int = 0
    missed: int = 0
    correct_abstentions: int = 0


@dataclass(slots=True)
class ScoreReport:
    """What the golden corpus says about the pipeline."""

    correct: int = 0
    missed: int = 0
    correct_abstentions: int = 0
    unadjudicated: int = 0
    false_acceptances: list[str] = field(default_factory=list)
    per_locus: dict[str, LocusTally] = field(default_factory=dict)

    @property
    def accepted(self) -> int:
        """Cells the pipeline resolved and the golden corpus could judge."""
        return self.correct + len(self.false_acceptances)

    @property
    def scored(self) -> int:
        return self.correct + self.missed + self.correct_abstentions + len(self.false_acceptances)

    @property
    def false_acceptance_upper_bound(self) -> float | None:
        """95% upper bound on the false-acceptance rate, by the rule of three.

        Defined only while no failure has been seen: with a failure the bound is
        no longer the question, because the answer is already "not zero".
        """
        if self.accepted == 0 or self.false_acceptances:
            return None
        return 3.0 / self.accepted

    @property
    def passed(self) -> bool:
        """`OCR-001`: wrong-locus false acceptance is zero on the golden set."""
        return not self.false_acceptances


def adjudicate(
    first: dict[str, CellLabel],
    second: dict[str, CellLabel],
    adjudicated: dict[str, CellLabel] | None = None,
) -> Adjudication:
    """Combine two independent labellings, with a third person's answers on top.

    A cell only one person reached is disputed rather than accepted: taking the
    single answer would make coverage look complete when half of it was never
    double-entered.
    """
    settled = adjudicated or {}
    agreed: dict[str, CellLabel] = {}
    disputed: dict[str, tuple[CellLabel | None, CellLabel | None]] = {}

    for cell_id in sorted(set(first) | set(second) | set(settled)):
        if cell_id in settled:
            agreed[cell_id] = settled[cell_id]
            continue
        a, b = first.get(cell_id), second.get(cell_id)
        if a is not None and b is not None and a.same_reading(b):
            agreed[cell_id] = a
        else:
            disputed[cell_id] = (a, b)
    return Adjudication(agreed=agreed, disputed=disputed)


def score_against_pipeline(
    truth: Adjudication,
    pipeline: dict[str, tuple[str, str, tuple[str, ...]]],
) -> ScoreReport:
    """Judge the pipeline against the golden corpus.

    `pipeline` maps a cell id to its (status, locus, values). Only cells whose
    reading two people agreed on, or a third settled, are scored: an unresolved
    disagreement is not ground truth.
    """
    report = ScoreReport(unadjudicated=len(truth.disputed))

    for cell_id, label in truth.agreed.items():
        entry = pipeline.get(cell_id)
        if entry is None:
            continue
        status, locus, values = entry
        tally = report.per_locus.setdefault(locus, LocusTally())

        if status == "RESOLVED":
            if (
                label.state is LabelState.VALUE
                and sorted(values) == sorted(label.alleles)
                or label.state is LabelState.PRESENT_ONLY
                and values
            ):
                report.correct += 1
                tally.correct += 1
            else:
                # The pipeline asserted something the human did not read: either
                # a different value, or a value where there is none. This is the
                # failure the project exists to prevent.
                report.false_acceptances.append(cell_id)
                tally.false_acceptances += 1
        elif label.state in (LabelState.VALUE, LabelState.PRESENT_ONLY):
            # A real value the pipeline declined to read. The record stays
            # incomplete, which is a cost rather than a harm.
            report.missed += 1
            tally.missed += 1
        else:
            report.correct_abstentions += 1
            tally.correct_abstentions += 1

    report.false_acceptances.sort()
    return report
