"""Locus resolution by printed anchor — the code that binds a value to a gene.

Written before the implementation. Every test here encodes a rule from
`OCR_SPEC.md` or `HLA_VALIDATION_SPEC.md`; a failure means the pipeline could
attribute a value to the wrong locus, which is the worst failure this project
can produce.

The design is ADR 0007: the registry stores the RELATION between a printed locus
label and its value, and the cell is located per document from that document's
own anchor. Absolute cell rectangles were retired because within one otherwise
clean family the DRB4 label occupies two different columns.
"""

from __future__ import annotations

import pytest
from kidneymatch.ocr.anchors import (
    Box,
    LocusResolution,
    ResolutionStatus,
    ValueRule,
    resolve_locus,
)

# A synthetic row: the label on the left, two allele values to its right.
# Coordinates are normalized, as stored by the OCR pass.
LABEL = Box(x0=0.10, y0=0.50, x1=0.18, y1=0.53, text="DRB1")
VALUE_1 = Box(x0=0.22, y0=0.50, x1=0.28, y1=0.53, text="15")
VALUE_2 = Box(x0=0.32, y0=0.50, x1=0.38, y1=0.53, text="11")
FAR_AWAY = Box(x0=0.80, y0=0.50, x1=0.86, y1=0.53, text="99")
OTHER_ROW = Box(x0=0.22, y0=0.70, x1=0.28, y1=0.73, text="07")

RULE = ValueRule(direction="right", same_row_tol=0.6, max_gap=2.5, max_values=2)


def resolve(boxes: list[Box], locus: str = "DRB1") -> LocusResolution:
    return resolve_locus(boxes, locus=locus, anchor_pattern=rf"^(?:HLA[-\s]?)?{locus}$", rule=RULE)


def test_a_value_to_the_right_of_its_label_is_bound_to_that_locus() -> None:
    result = resolve([LABEL, VALUE_1])
    assert result.status is ResolutionStatus.RESOLVED
    assert result.locus == "DRB1"
    assert result.values == ["15"]


def test_both_alleles_of_a_heterozygous_locus_are_captured() -> None:
    """An HLA locus has two alleles; a rule that takes only one silently drops data."""
    result = resolve([LABEL, VALUE_1, VALUE_2])
    assert result.status is ResolutionStatus.RESOLVED
    assert result.values == ["15", "11"]


def test_a_missing_anchor_yields_UNKNOWN_not_a_guess() -> None:
    """Constitution: a missing locus is UNKNOWN, never an inferred value.

    ADR 0007: no locus may be emitted that was not physically present as a label
    on the source document.
    """
    result = resolve([VALUE_1, VALUE_2])
    assert result.status is ResolutionStatus.UNKNOWN
    assert result.values == []


def test_a_duplicated_anchor_requires_review() -> None:
    """Two DRB1 labels means we cannot tell which row owns the value.

    Measured: DRB3 appears more than once in 17.7% of documents.
    """
    second_label = Box(x0=0.10, y0=0.70, x1=0.18, y1=0.73, text="DRB1")
    result = resolve([LABEL, second_label, VALUE_1])
    assert result.status is ResolutionStatus.REVIEW_REQUIRED
    assert result.values == []


def test_a_label_with_no_value_in_range_requires_review() -> None:
    """The label is printed but the value was not read: that is not UNKNOWN.

    UNKNOWN means the form does not report this locus. A label with an
    unreadable value is a different state and a human must look at it.
    """
    result = resolve([LABEL, FAR_AWAY])
    assert result.status is ResolutionStatus.REVIEW_REQUIRED


def test_a_value_on_a_different_row_is_not_taken() -> None:
    result = resolve([LABEL, OTHER_ROW])
    assert result.status is ResolutionStatus.REVIEW_REQUIRED
    assert result.values == []


def test_the_locus_comes_from_the_anchor_never_from_the_value_text() -> None:
    """`OCR_SPEC` section 2: geometry decides the locus, OCR decides the characters.

    A value token that happens to spell another locus must not retarget it.
    """
    misleading = Box(x0=0.22, y0=0.50, x1=0.30, y1=0.53, text="DQB1*03")
    result = resolve([LABEL, misleading])
    assert result.locus == "DRB1"
    assert result.status is not ResolutionStatus.RESOLVED or result.locus == "DRB1"


def test_a_value_prefix_never_matches_the_anchor() -> None:
    """`\\bDRB1\\b` also matches the DRB1 inside DRB1*11.

    Measured on the real corpus, that inflated apparent DRB1 presence 5.18x and,
    worse, placed the locus at wherever a patient-specific value happened to sit.
    """
    value_token_only = Box(x0=0.22, y0=0.50, x1=0.30, y1=0.53, text="DRB1*11")
    result = resolve([value_token_only])
    assert result.status is ResolutionStatus.UNKNOWN, "a value token is not a label"


def test_more_values_than_the_locus_can_have_requires_review() -> None:
    """Three candidates in a two-allele row means the row was misread."""
    third = Box(x0=0.42, y0=0.50, x1=0.48, y1=0.53, text="04")
    result = resolve([LABEL, VALUE_1, VALUE_2, third])
    assert result.status is ResolutionStatus.REVIEW_REQUIRED


def test_a_combined_drb345_header_is_not_treated_as_one_locus() -> None:
    """`HLA_VALIDATION_SPEC` section 7: DRB3/4/5 are separate genes.

    A form row labelled `DRB3/4/5` is a presentation grouping. Binding one value
    to it would assign the same allele to three genes.
    """
    combined = Box(x0=0.10, y0=0.50, x1=0.22, y1=0.53, text="DRB3/4/5")
    result = resolve_locus(
        [combined, VALUE_1], locus="DRB3", anchor_pattern=r"^(?:HLA[-\s]?)?DRB3$", rule=RULE
    )
    assert result.status is ResolutionStatus.UNKNOWN, "the combined header is not a DRB3 label"


@pytest.mark.parametrize("direction", ["right", "below"])
def test_direction_is_honoured(direction: str) -> None:
    below = Box(x0=0.10, y0=0.56, x1=0.16, y1=0.59, text="15")
    rule = ValueRule(direction=direction, same_row_tol=0.6, max_gap=2.5, max_values=2)
    result = resolve_locus([LABEL, below], locus="DRB1", anchor_pattern=r"^DRB1$", rule=rule)
    if direction == "below":
        assert result.status is ResolutionStatus.RESOLVED
        assert result.values == ["15"]
    else:
        assert result.status is ResolutionStatus.REVIEW_REQUIRED


def test_resolution_records_the_anchor_box_for_provenance() -> None:
    """Every derived medical fact must point back at the pixels it came from."""
    result = resolve([LABEL, VALUE_1])
    assert result.anchor_box == LABEL
    assert result.value_boxes == [VALUE_1]
