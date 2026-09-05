"""On a form that prints the locus on every value, a candidate naming another
locus is set aside before the candidate count.

The family rule reads a row band 1.9 anchor heights wide with no distance cap,
which on a hand-held photograph lets the neighbouring row's values drift into
the band. Before this, three candidates — two naming this locus and one naming
the next — refused the cell as "exceeds max_values". Measured corpus-wide,
1,366 refused cells hold exactly two values naming their own locus beside one
or two naming another. Gate 2 ("geometry and text disagree") is unchanged for
a cell with no more candidates than the locus can have: there the disagreement
is real and a human looks.
"""

from __future__ import annotations

import pytest

from kidneymatch.ocr.anchors import Box, ResolutionStatus, ValueRule, resolve_locus

pytestmark = pytest.mark.task("OCR-001")

LABEL = Box(0.10, 0.500, 0.18, 0.530, "HLA-A")
FAMILY_RULE = ValueRule(
    direction="right",
    align_overlap=0.2,
    max_gap=None,
    max_values=2,
    centre_band=1.9,
    require_prefix=True,
)
DEFAULT_RULE = ValueRule(direction="right", align_overlap=0.2, max_gap=20.0, max_values=2)


def value(x0: float, text: str, dy: float = 0.0) -> Box:
    offset = dy * 0.03
    return Box(x0, 0.500 - offset, x0 + 0.06, 0.530 - offset, text)


def test_a_drifted_neighbour_value_is_set_aside_under_the_family_rule() -> None:
    boxes = [LABEL, value(0.22, "A*02"), value(0.40, "A*24"), value(0.30, "B*44", 1.6)]
    result = resolve_locus(boxes, "A", FAMILY_RULE)
    assert result.status is ResolutionStatus.RESOLVED, result.reason
    assert result.values == ["A*02", "A*24"]
    assert [b.text for b in result.value_boxes] == ["A*02", "A*24"]
    assert result.reason == "1 candidate(s) naming another locus set aside"


def test_two_neighbour_values_are_set_aside_as_readily_as_one() -> None:
    boxes = [
        LABEL,
        value(0.22, "A*02"),
        value(0.40, "A*24"),
        value(0.24, "B*44", 1.6),
        value(0.42, "B*51", 1.6),
    ]
    assert resolve_locus(boxes, "A", FAMILY_RULE).values == ["A*02", "A*24"]


def test_gate_2_is_unchanged_when_the_cell_is_not_over_full() -> None:
    """One of two candidates names another locus: geometry and text disagree."""
    boxes = [LABEL, value(0.22, "A*02"), value(0.40, "B*44")]
    result = resolve_locus(boxes, "A", FAMILY_RULE)
    assert result.status is ResolutionStatus.REVIEW_REQUIRED
    assert "geometry and text disagree" in result.reason


def test_a_candidate_that_does_not_parse_is_kept_and_still_refuses_the_cell() -> None:
    """Only a candidate that NAMES another locus is set aside; noise is not."""
    boxes = [LABEL, value(0.22, "A*02"), value(0.40, "A*24"), value(0.58, "ALLELE", 1.0)]
    result = resolve_locus(boxes, "A", FAMILY_RULE)
    assert result.status is ResolutionStatus.REVIEW_REQUIRED
    assert "exceeds max_values" in result.reason


def test_the_default_rule_never_filters_by_prefix() -> None:
    """A form that does not print the locus on its values gives no licence to
    decide by prefix which of three candidates is foreign."""
    boxes = [LABEL, value(0.22, "A*02"), value(0.30, "A*24"), value(0.38, "B*44")]
    result = resolve_locus(boxes, "A", DEFAULT_RULE)
    assert result.status is ResolutionStatus.REVIEW_REQUIRED
    assert "exceeds max_values" in result.reason


def test_setting_aside_never_leaves_a_single_foreign_value_standing() -> None:
    """Three foreign candidates and none of ours: nothing resolves."""
    boxes = [LABEL, value(0.22, "B*44"), value(0.40, "B*51"), value(0.58, "C*07")]
    result = resolve_locus(boxes, "A", FAMILY_RULE)
    assert result.status is not ResolutionStatus.RESOLVED


def test_a_shape_refusal_means_every_other_box_passed_every_gate() -> None:
    """The geometric gates run over all boxes before any text is parsed, and
    the text gates over every box that parses: "does not parse" is emitted
    only when nothing else on the row was wrong. `promote_proposals.py`
    relies on exactly that."""
    label_on_row = Box(0.40, 0.500, 0.48, 0.530, "HLA-DRB1")
    result = resolve_locus([LABEL, value(0.22, "A*OZ"), label_on_row], "A", FAMILY_RULE)
    assert "locus label" in result.reason
    foreign = resolve_locus([LABEL, value(0.22, "A*OZ"), value(0.40, "B*44")], "A", FAMILY_RULE)
    assert "geometry and text disagree" in foreign.reason
    clean = resolve_locus([LABEL, value(0.22, "A*OZ"), value(0.40, "A*24")], "A", FAMILY_RULE)
    assert "does not parse" in clean.reason
