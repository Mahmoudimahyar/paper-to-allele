"""The default rule's tolerance band: a fallback for a cell that read empty.

Measured over the 11,140 documents on the default rule: the nearest
allele-shaped box to a label whose cell read empty sits one anchor height off
the label's centre on 1,406 of 5,302 such cells — a photograph's drift, or a
label box the detector stretched over a ruling. A band of 1.5 anchor heights
resolves 949 of them with no box bound to two loci. The same band applied as
a first criterion also added candidates to 799 cells that already resolved and
refused them, so it is a FALLBACK: the strict overlap test runs first, and the
band is consulted only when that test read nothing, or one allele with its
partner unread, and the wider reading is kept only when it resolves.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from kidneymatch.ocr.anchors import (
    Box,
    ResolutionStatus,
    ValueRule,
    resolve_document,
    resolve_locus,
)

pytestmark = pytest.mark.task("OCR-001")

LABEL = Box(0.10, 0.500, 0.18, 0.530, "HLA-A")  # height 0.03
STRICT = ValueRule(direction="right", align_overlap=0.2, max_gap=20.0, max_values=2)
TOLERANT = replace(STRICT, fallback_band=1.5)


def value(x0: float, text: str, dy: float) -> Box:
    """A value box `dy` anchor heights above the label's centre."""
    offset = dy * 0.03
    return Box(x0, 0.500 - offset, x0 + 0.06, 0.530 - offset, text)


def test_a_value_one_height_above_its_label_resolves_within_the_band() -> None:
    boxes = [LABEL, value(0.22, "A*02", 1.0), value(0.40, "A*24", 1.0)]
    assert resolve_locus(boxes, "A", STRICT).status is ResolutionStatus.REVIEW_REQUIRED
    result = resolve_locus(boxes, "A", TOLERANT)
    assert result.status is ResolutionStatus.RESOLVED, result.reason
    assert result.values == ["A*02", "A*24"]


def test_the_band_has_an_edge() -> None:
    """1.5 anchor heights, not "somewhere above"; the next row is 3.8 away."""
    inside = [LABEL, value(0.22, "A*02", 1.4)]
    outside = [LABEL, value(0.22, "A*02", 1.6)]
    assert resolve_locus(inside, "A", TOLERANT).status is ResolutionStatus.RESOLVED
    assert resolve_locus(outside, "A", TOLERANT).status is ResolutionStatus.REVIEW_REQUIRED


def test_a_partner_read_only_within_the_band_completes_the_pair() -> None:
    """One allele on the line and the second drifted: 853 cells corpus-wide."""
    boxes = [LABEL, value(0.22, "A*02", 0.0), value(0.40, "A*24", 1.2)]
    strict = resolve_locus(boxes, "A", STRICT)
    assert strict.values == ["A*02"] and strict.second_allele.value == "UNREAD"
    tolerant = resolve_locus(boxes, "A", TOLERANT)
    assert tolerant.values == ["A*02", "A*24"]
    assert tolerant.second_allele.value == "READ"


def test_a_strict_result_is_never_made_worse_by_the_band() -> None:
    """Within the band sits a token that does not parse: the strict single
    allele stands, exactly as the rule read it before the band existed."""
    boxes = [LABEL, value(0.22, "A*02", 0.0), value(0.40, "ALLELE", 1.2)]
    tolerant = resolve_locus(boxes, "A", TOLERANT)
    assert tolerant.status is ResolutionStatus.RESOLVED
    assert tolerant.values == ["A*02"]


def test_the_band_never_admits_a_third_box() -> None:
    """Two on the band beside one strict value: more than the locus can have,
    so the wider reading is not taken and the strict single allele stands."""
    boxes = [
        LABEL,
        value(0.22, "A*02", 0.0),
        value(0.40, "A*24", 1.2),
        value(0.58, "A*11", 1.2),
    ]
    tolerant = resolve_locus(boxes, "A", TOLERANT)
    assert tolerant.status is ResolutionStatus.RESOLVED
    assert tolerant.values == ["A*02"]


def test_a_cell_that_resolved_two_values_strictly_is_untouched() -> None:
    boxes = [LABEL, value(0.22, "A*02", 0.0), value(0.40, "A*24", 0.0), value(0.58, "A*11", 1.2)]
    assert resolve_locus(boxes, "A", STRICT).values == resolve_locus(boxes, "A", TOLERANT).values


def test_without_a_band_the_rule_is_byte_for_byte_the_old_one() -> None:
    boxes = [LABEL, value(0.22, "A*02", 1.0)]
    assert STRICT.fallback_band is None
    assert resolve_locus(boxes, "A", STRICT).status is ResolutionStatus.REVIEW_REQUIRED


# --- what the band must not reach -------------------------------------------


def test_a_competing_label_decides_ownership_under_the_band_too() -> None:
    """The band admits a box the overlap test refused; the ownership gate must
    then compare the SAME box against the other labels under the same
    alignment, or a value nearer to another label binds here."""
    other = Box(0.10, 0.455, 0.18, 0.485, "HLA-B")  # the B label, 1.5 heights above
    drifted = value(0.22, "24", 1.2)  # nearer to B than to A; a bare number, so no prefix gate
    assert resolve_locus([LABEL, drifted], "A", TOLERANT).status is ResolutionStatus.RESOLVED
    result = resolve_locus([LABEL, other, drifted], "A", TOLERANT)
    assert result.status is not ResolutionStatus.RESOLVED


def test_the_grouped_header_owns_its_row_against_the_band() -> None:
    """A bare digit on the DRB3/4/5 row, 1.2 heights below the DRB1 label on a
    tight form: the header is not a locus anchor, but it owns that row."""
    drb1 = Box(0.10, 0.500, 0.18, 0.530, "HLA-DRB1")
    header = Box(0.10, 0.531, 0.24, 0.561, "HLA-DRB3/4/5")
    digit = Box(0.40, 0.533, 0.46, 0.563, "03")  # on the header's line
    assert resolve_locus([drb1, digit], "DRB1", TOLERANT).status is ResolutionStatus.RESOLVED
    result = resolve_locus([drb1, header, digit], "DRB1", TOLERANT)
    assert result.status is not ResolutionStatus.RESOLVED


def test_a_tall_anchor_gets_no_band() -> None:
    """A label box the detector stretched over a ruling is twice the height of
    the page's other labels; a band in its units would reach the next row."""
    tall = Box(0.10, 0.485, 0.18, 0.545, "HLA-A")  # 0.06 high, the others 0.03
    others = [
        Box(0.10, 0.60, 0.18, 0.63, "HLA-B"),
        Box(0.10, 0.70, 0.18, 0.73, "HLA-C"),
        Box(0.10, 0.80, 0.18, 0.83, "HLA-DRB1"),
    ]
    drifted = Box(0.22, 0.44, 0.28, 0.47, "A*02")  # 1.2 tall-heights above the tall label
    assert resolve_locus([tall, *others, drifted], "A", TOLERANT).status is not (
        ResolutionStatus.RESOLVED
    )
    # the same geometry with a normal-height label resolves under the band
    normal = Box(0.10, 0.500, 0.18, 0.530, "HLA-A")
    near = Box(0.22, 0.464, 0.28, 0.494, "A*02")
    assert resolve_locus([normal, *others, near], "A", TOLERANT).status is ResolutionStatus.RESOLVED


def test_one_box_is_never_bound_by_two_loci_under_the_band() -> None:
    """Two labels a line apart with one value box exactly between them: the
    band reaches it from both, ownership ties, and neither locus keeps it."""
    a = Box(0.10, 0.500, 0.18, 0.530, "HLA-A")
    b = Box(0.10, 0.560, 0.18, 0.590, "HLA-B")
    between = Box(0.22, 0.530, 0.28, 0.560, "24")
    results = resolve_document([a, b, between], TOLERANT, loci=("A", "B"))
    assert results["A"].status is not ResolutionStatus.RESOLVED
    assert results["B"].status is not ResolutionStatus.RESOLVED
