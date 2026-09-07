"""Reading DOWN a column: the three gates the direction needs before it ships.

Written before the code. `ocr/layout.py` has been able to say "this form's
locus labels are column headers" since the reviewer described one, and three
add-on passes acted on it — `page_ocr_bind.py`, `rerecognise_pass.py` and
`upright_bind.py`, all importing the same `BELOW_RULE` object — while the
EXTRACTION did not. Wiring it in was measured over the corpus (290 pages read
as a column layout, +364 cells) and an adversarial review then constructed
four readings the code path RESOLVES and should not:

1. **Four alleles in one cell.** `_bind` caps the number of BOXES at
   `max_values` but never counts the alleles parsed out of them, and one box
   can print a whole pair. A header with two pair-token boxes beneath it —
   which is what a two-subject column table looks like — resolved with four
   values, i.e. two people's genotypes merged into one. 0 of the 383 gained
   cells are lost by counting them, and no RESOLVED fact in the corpus holds
   more than two alleles.
2. **The wrong header owns the value.** `_owned_by_another_anchor` breaks a
   near-tie by comparing centre `y` offsets. Reading down, `y` IS the reading
   axis, so two headers printed on one line are separated by nothing but
   detector noise, and the value goes to whichever header the recognizer
   happened to box a fraction lower. Across the reading axis — the column —
   is the question that has an answer.
3. **A bare number under a header.** `BELOW_RULE` does not require the value
   to print its locus (`require_prefix=False`), and with the prefix stripped a
   value moved under the neighbouring column still binds. All 727 values on
   the corpus's column pages DO print their locus, so refusing the bare ones
   costs nothing here and closes the case where the column alone is wrong.
   Because the rule object is shared, this changed the three add-on passes as
   well; dry-run against today's database they bind exactly what they bound
   before.
4. **Two people's alleles stacked in one column.** Two boxes under one header,
   one allele each, both naming the locus: the cardinality gate, the ownership
   gate and the bare-value gate all pass, and the cell resolved as one
   person's genotype. The printed form is what separates them, so the page's
   horizontal rulings travel with the rule and a ruling running between the
   two boxes at the header's x refuses the cell. Measured cost on the corpus:
   1 cell of the 365 (a DRB1), on a page whose table really does draw the
   line.

Synthetic geometry throughout; the allele values are fabricated.
"""

from __future__ import annotations

from dataclasses import replace

from kidneymatch.ocr.anchors import (
    Box,
    ResolutionStatus,
    ValueRule,
    resolve_locus,
)
from kidneymatch.ocr.lattice import Ruling

# The two rules, as `extract_facts.py` authors them.
ROW_RULE = ValueRule(direction="right", align_overlap=0.2, max_gap=20.0, max_values=2)
COLUMN_RULE = ValueRule(
    direction="below", align_overlap=0.3, max_gap=3.0, max_values=2, refuse_bare=True
)


def header(x0: float, text: str, y0: float = 0.20) -> Box:
    return Box(x0=x0, y0=y0, x1=x0 + 0.10, y1=y0 + 0.025, text=text)


def under(x0: float, text: str, y0: float) -> Box:
    return Box(x0=x0, y0=y0, x1=x0 + 0.10, y1=y0 + 0.025, text=text)


# --- gate 1: alleles, not boxes ------------------------------------------


def test_two_pair_tokens_under_one_header_are_more_alleles_than_a_locus_has() -> None:
    """Two subjects' pairs, one under the other, in one printed column."""
    boxes = [
        header(0.20, "HLA-A"),
        under(0.20, "A*01,*02", 0.26),
        under(0.20, "A*11,*24", 0.30),
    ]
    result = resolve_locus(boxes, "A", COLUMN_RULE)
    assert result.status is ResolutionStatus.REVIEW_REQUIRED
    assert "exceeds max_values" in (result.reason or "")
    assert result.value_boxes, "the reviewer needs the crop of what was refused"


def test_the_allele_count_is_checked_reading_rightwards_too() -> None:
    boxes = [
        header(0.10, "HLA-A", y0=0.50),
        Box(0.22, 0.50, 0.32, 0.525, "A*01,*02"),
        Box(0.40, 0.50, 0.50, 0.525, "A*11,*24"),
    ]
    result = resolve_locus(boxes, "A", ROW_RULE)
    assert result.status is ResolutionStatus.REVIEW_REQUIRED
    assert "exceeds max_values" in (result.reason or "")


def test_one_pair_token_under_a_header_still_resolves() -> None:
    """The commonest column cell in the corpus: one box printing both alleles."""
    boxes = [header(0.20, "HLA-A"), under(0.20, "A*01,*02", 0.26)]
    result = resolve_locus(boxes, "A", COLUMN_RULE)
    assert result.status is ResolutionStatus.RESOLVED
    assert result.values == ["A*01", "A*02"]


# --- gate 2: the column decides ownership when reading down ---------------


def _two_headers_one_value(text: str = "DQB1*03") -> list[Box]:
    """DQB1 and DRB1 side by side, DRB1 boxed 0.3 label heights lower.

    The value's centre stands in DQB1's column and overlaps DRB1's x extent by
    30% — the alignment threshold — so both headers see it. Reading down, the
    only thing separating the two headers along the reading axis is the 0.3
    heights of detector noise.
    """
    return [
        Box(0.20, 0.2000, 0.30, 0.2250, "HLA-DQB1"),
        Box(0.13, 0.2075, 0.23, 0.2325, "HLA-DRB1"),
        Box(0.20, 0.2600, 0.30, 0.2850, text),
    ]


def test_the_nearer_column_owns_the_value_not_the_lower_header() -> None:
    boxes = _two_headers_one_value()
    resolved = resolve_locus(boxes, "DQB1", COLUMN_RULE)
    assert resolved.status is ResolutionStatus.RESOLVED, resolved.reason
    assert resolved.values == ["DQB1*03"]


def test_the_header_of_another_column_refuses_the_value() -> None:
    boxes = _two_headers_one_value()
    refused = resolve_locus(boxes, "DRB1", COLUMN_RULE)
    assert refused.status is ResolutionStatus.REVIEW_REQUIRED
    assert "DQB1" in (refused.reason or "")


def test_a_bare_value_goes_to_the_column_it_stands_in() -> None:
    """The ownership question with nothing else to answer it.

    A value that prints its locus is refused by the prefix gate when the wrong
    header claims it, so the ownership rule is only load-bearing for a bare
    one — which is exactly the case that resolved to the wrong gene before,
    because a header boxed 0.3 heights lower was 'nearer' down the page.
    """
    bare = replace(COLUMN_RULE, refuse_bare=False)
    boxes = _two_headers_one_value("03")
    assert resolve_locus(boxes, "DQB1", bare).status is ResolutionStatus.RESOLVED
    refused = resolve_locus(boxes, "DRB1", bare)
    assert refused.status is ResolutionStatus.REVIEW_REQUIRED
    assert "DQB1" in (refused.reason or "")


def test_two_headers_over_the_same_column_are_a_conflict() -> None:
    """Neither column is nearer, so nobody may take the value."""
    boxes = [
        Box(0.20, 0.2000, 0.30, 0.2250, "HLA-DQB1"),
        Box(0.20, 0.1000, 0.30, 0.1250, "HLA-DRB1"),
        Box(0.20, 0.2600, 0.30, 0.2850, "DQB1*03"),
    ]
    assert resolve_locus(boxes, "DQB1", COLUMN_RULE).status is ResolutionStatus.REVIEW_REQUIRED


def test_reading_rightwards_still_breaks_a_tie_by_the_row() -> None:
    """The y tie-break is right for a rule whose reading axis is x, and the
    two values it saved on the reviewer's labels must not move."""
    boxes = [
        Box(0.10, 0.500, 0.20, 0.530, "HLA-A"),
        Box(0.10, 0.560, 0.20, 0.590, "HLA-B"),
        Box(0.30, 0.560, 0.40, 0.590, "B*07"),
    ]
    assert resolve_locus(boxes, "B", ROW_RULE).status is ResolutionStatus.RESOLVED
    refused = resolve_locus(boxes, "A", ROW_RULE)
    assert refused.status is not ResolutionStatus.RESOLVED


# --- gate 3: a bare number in a column ------------------------------------


def test_a_bare_value_under_a_column_header_is_refused() -> None:
    """Nothing but the column says which gene it is, and a column is what a
    photograph shears. Measured: 765 of 765 values on the corpus's column
    pages print their locus, so this costs nothing."""
    boxes = [header(0.20, "HLA-A"), under(0.20, "01", 0.26)]
    result = resolve_locus(boxes, "A", COLUMN_RULE)
    assert result.status is ResolutionStatus.REVIEW_REQUIRED
    assert "names no locus" in (result.reason or "")
    assert result.value_boxes


def test_refusing_bare_values_is_not_the_prefix_requirement() -> None:
    """`require_prefix=True` would also change what the star-less gate does
    and would switch on the ruled-row branch of `bind_in_lattice`."""
    assert COLUMN_RULE.require_prefix is False
    starless = [header(0.20, "HLA-A"), under(0.20, "A01", 0.26)]
    result = resolve_locus(starless, "A", COLUMN_RULE)
    assert result.status is ResolutionStatus.REVIEW_REQUIRED
    assert "without a star" in (result.reason or "")


def test_a_row_rule_page_still_reads_its_bare_values() -> None:
    """The default rule reads forms that print bare numbers; only a column
    form refuses them."""
    boxes = [
        Box(0.10, 0.50, 0.20, 0.53, "HLA-A"),
        Box(0.30, 0.50, 0.40, 0.53, "01"),
        Box(0.50, 0.50, 0.60, 0.53, "02"),
    ]
    assert resolve_locus(boxes, "A", ROW_RULE).status is ResolutionStatus.RESOLVED
    assert resolve_locus(boxes, "A", replace(ROW_RULE, refuse_bare=True)).status is (
        ResolutionStatus.REVIEW_REQUIRED
    )


# --- gate 4: a ruling between two values stacked under one header ---------


def _two_subject_column(top: str = "A*01", bottom: str = "A*24") -> list[Box]:
    """One header over two rows, each holding one allele of this locus.

    The shape a donor/recipient table makes: the header at the top, the
    donor's value under it and the recipient's under that. It is also exactly
    the shape ONE person's two alleles make when the form prints them stacked,
    and no gate in `anchors.py` can tell the two apart from the boxes alone.
    """
    return [
        Box(0.20, 0.2000, 0.30, 0.2250, "HLA-A"),
        Box(0.20, 0.2400, 0.30, 0.2650, top),
        Box(0.20, 0.2750, 0.30, 0.3000, bottom),
    ]


def test_two_values_stacked_under_one_header_resolve_when_nothing_separates_them() -> None:
    """The reading the corpus's column pages actually hold: one cell, two alleles."""
    result = resolve_locus(_two_subject_column(), "A", COLUMN_RULE)
    assert result.status is ResolutionStatus.RESOLVED, result.reason
    assert result.values == ["A*01", "A*24"]


def test_a_ruling_between_the_two_values_refuses_the_cell() -> None:
    """The counterexample the review constructed against this branch.

    Two boxes, two alleles, both under the header, both naming the locus: the
    cardinality gate, the ownership gate and the bare-value gate all pass, and
    the cell resolved as one person's genotype. On a ruled two-subject table
    the form itself says they are different rows, and that ruling is the only
    thing on the page that does.
    """
    boxes = _two_subject_column()
    lattice_ruled = replace(
        COLUMN_RULE, row_rulings=(Ruling(start=0.05, end=0.95, at_start=0.270, at_end=0.270),)
    )
    result = resolve_locus(boxes, "A", lattice_ruled)
    assert result.status is ResolutionStatus.REVIEW_REQUIRED
    assert "ruling" in (result.reason or "")
    assert len(result.value_boxes) == 2, "the reviewer is shown both crops"


def test_the_ruling_is_read_at_the_header_and_not_at_its_middle() -> None:
    """A ruling on a page tilted a degree moves half a row's height across the
    page, so a ruling that passes between the values at the header's x counts
    even when its mean sits above both of them."""
    boxes = _two_subject_column()
    sloped = Ruling(start=0.00, end=1.00, at_start=0.295, at_end=0.195)
    # Its mean lands inside the upper value's own box; at the header's x it
    # runs between the two.
    assert 0.2400 < sloped.at < 0.2650
    assert 0.2525 < sloped.at_x(0.25) < 0.2875
    result = resolve_locus(boxes, "A", replace(COLUMN_RULE, row_rulings=(sloped,)))
    assert result.status is ResolutionStatus.REVIEW_REQUIRED


def test_a_ruling_that_does_not_reach_the_header_says_nothing() -> None:
    """`spans` is a real gate: a ruling from another part of the page that
    stops short of this column has not been drawn between these two values."""
    elsewhere = Ruling(start=0.60, end=0.95, at_start=0.270, at_end=0.270)
    result = resolve_locus(
        _two_subject_column(), "A", replace(COLUMN_RULE, row_rulings=(elsewhere,))
    )
    assert result.status is ResolutionStatus.RESOLVED, result.reason


def test_the_ruling_gate_is_for_the_column_rule_only() -> None:
    """Reading rightwards, the values of one cell sit side by side and the
    rulings of the table run between ROWS, not between them."""
    boxes = [
        Box(0.10, 0.50, 0.20, 0.53, "HLA-A"),
        Box(0.30, 0.50, 0.40, 0.53, "A*01"),
        Box(0.50, 0.50, 0.60, 0.53, "A*24"),
    ]
    crossing = Ruling(start=0.0, end=1.0, at_start=0.515, at_end=0.515)
    assert (
        resolve_locus(boxes, "A", replace(ROW_RULE, row_rulings=(crossing,))).status
        is ResolutionStatus.RESOLVED
    )
