"""A locus taken from the value's own printed prefix, and the gates on it.

Two passes assign a locus from nomenclature rather than from a template cell,
which qualifies a rule the project otherwise states flatly — "geometry/template
cell defines HLA locus; OCR text alone may not assign locus". The operator's
decision is recorded in `docs/ingestion/CV_RESEARCH_2026-09-05.md` s12, and the
gates below are the whole safety argument for it.

`prefix_bind.claims_for` runs where the page labels NOTHING: the printed prefix
is the only thing naming a gene, so geometry gets first refusal and the pass
only sees loci with no anchor anywhere.

`anchor_row_bind.on_the_anchors_row` runs where the label WAS read but the
computed cell held no box. There the claim is stronger, because two independent
signals must agree: the row comes from the printed anchor (geometry) and the
locus from the value's own prefix (nomenclature). Each test names a way the
pass could assert something untrue.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from anchor_row_bind import MAX_GAP, on_the_anchors_row  # noqa: E402
from prefix_bind import claims_for  # noqa: E402

from kidneymatch.hla.vocabulary import load_vocabulary  # noqa: E402
from kidneymatch.ocr.anchors import Box  # noqa: E402

ROW = 0.40
HEIGHT = 0.012


@pytest.fixture(scope="module")
def vocabulary():
    return load_vocabulary()


def at(text: str, x: float, y: float = ROW, *, height: float = HEIGHT) -> Box:
    return Box(x0=x, y0=y, x1=x + 0.08, y1=y + height, text=text)


def anchor(y: float = ROW) -> Box:
    return Box(x0=0.05, y0=y, x1=0.14, y1=y + HEIGHT, text="HLA-A")


# --- prefix_bind: the page names no row at all -----------------------------


def test_a_fully_qualified_pair_names_its_own_locus(vocabulary) -> None:
    boxes = [at("A*24", 0.30), at("A*02", 0.42)]
    assert claims_for(boxes, "A", vocabulary, 0.0) == boxes


def test_a_value_with_no_star_is_refused(vocabulary) -> None:
    """`B35` may be a serological spelling, not an allele (HLA_VALIDATION s4),
    and a bare number names nothing at all."""
    assert claims_for([at("B35", 0.30)], "B", vocabulary, 0.0) is None


def test_a_value_for_another_gene_does_not_claim_this_one(vocabulary) -> None:
    assert claims_for([at("B*35", 0.30)], "A", vocabulary, 0.0) is None


def test_two_rows_are_refused_because_they_may_be_two_people(vocabulary) -> None:
    """The most dangerous failure this pass could produce is the right gene of
    the wrong person, so a claim spanning rows is not a claim."""
    boxes = [at("A*24", 0.30), at("A*02", 0.30, ROW + 0.15)]
    assert claims_for(boxes, "A", vocabulary, 0.0) is None


def test_a_sloped_row_is_still_one_row(vocabulary) -> None:
    """The page is photographed, not scanned. Following the page's own slope is
    what stops a tilt from reading as two rows."""
    slope = 0.05
    far = at("A*02", 0.60, ROW + slope * (0.60 - 0.30))
    assert claims_for([at("A*24", 0.30), far], "A", vocabulary, slope) is not None
    assert claims_for([at("A*24", 0.30), far], "A", vocabulary, 0.0) is None


def test_more_values_than_a_locus_can_have_is_refused(vocabulary) -> None:
    boxes = [at("A*24", 0.30), at("A*02", 0.42), at("A*11", 0.54)]
    assert claims_for(boxes, "A", vocabulary, 0.0) is None


def test_an_inadmissible_value_taints_the_page(vocabulary) -> None:
    """A prefix that names a gene the value cannot belong to is evidence the
    reading is wrong, not evidence about the locus."""
    assert claims_for([at("A*999", 0.30)], "A", vocabulary, 0.0) is None


# --- anchor_row_bind: the label was read, the cell rectangle was not --------


def test_a_value_on_the_anchors_row_naming_the_anchors_gene_binds(vocabulary) -> None:
    # The label object must be the one inside `boxes`, as it is in the pass:
    # a distinct-but-equal copy competes with itself for ownership.
    label = anchor()
    boxes = [label, at("A*24", 0.30), at("A*02", 0.42)]
    found = on_the_anchors_row(boxes, label, "A", vocabulary, 0.0)
    assert found is not None and len(found) == 2


def test_a_value_naming_this_gene_from_another_row_is_refused(vocabulary) -> None:
    """This is the whole point of requiring both signals: the prefix alone would
    happily take a value six rows down."""
    boxes = [at("A*24", 0.30, ROW + 0.20)]
    assert on_the_anchors_row(boxes, anchor(), "A", vocabulary, 0.0) is None


def test_a_value_on_the_right_row_naming_another_gene_is_refused(vocabulary) -> None:
    """And the row alone would take whatever sits beside the label."""
    assert on_the_anchors_row([at("B*35", 0.30)], anchor(), "A", vocabulary, 0.0) is None


def test_a_star_less_value_on_the_row_is_refused(vocabulary) -> None:
    assert on_the_anchors_row([at("A24", 0.30)], anchor(), "A", vocabulary, 0.0) is None


def test_an_empty_row_binds_nothing(vocabulary) -> None:
    """Silence is the default; most of this refusal bucket is blank paper."""
    assert on_the_anchors_row([anchor()], anchor(), "A", vocabulary, 0.0) is None


def test_the_rows_slope_is_followed_here_too(vocabulary) -> None:
    """Within the gap cap, a sloped row is still one row: the lift is what
    stops a photographed tilt from reading as a different line."""
    slope = 0.20
    x = 0.30
    lifted = at("A*24", x, ROW + slope * (x + 0.04 - 0.095))
    assert on_the_anchors_row([lifted], anchor(), "A", vocabulary, slope) is not None
    assert on_the_anchors_row([lifted], anchor(), "A", vocabulary, 0.0) is None


def test_more_values_than_the_locus_can_have_is_refused(vocabulary) -> None:
    boxes = [at("A*24", 0.30), at("A*02", 0.42), at("A*11", 0.54)]
    assert on_the_anchors_row(boxes, anchor(), "A", vocabulary, 0.0) is None


def test_an_inadmissible_value_on_the_row_is_refused(vocabulary) -> None:
    assert on_the_anchors_row([at("A*999", 0.30)], anchor(), "A", vocabulary, 0.0) is None


# --- the gates an adversarial review forced ---------------------------------
#
# The first version of `anchor_row_bind` had no distance cap, no direction and
# no ownership check. Each test below reproduces the probe that confirmed one
# of those, so the gate cannot be removed without a red test.


def test_a_value_left_of_the_label_is_refused(vocabulary) -> None:
    """No rule in this pipeline reads leftwards. `_candidates` and
    `resolve_in_row` both require `x0 > anchor.x1`; the first version accepted
    a box at x=0.001, and twelve of its 458 corpus binds were on the wrong side
    of their own label."""
    assert on_the_anchors_row([at("A*24", 0.001)], anchor(), "A", vocabulary, 0.0) is None


def test_a_value_beyond_the_gap_cap_is_refused(vocabulary) -> None:
    """`DEFAULT_RULE` caps the gap at 20 anchor heights on these very pages.
    The first version had no cap: its binds ran to 69 heights, and 87% of them
    sat past the cap the ordinary resolver was enforcing beside them."""
    label = anchor()
    far = at("A*24", label.x1 + (MAX_GAP + 5) * label.height)
    assert on_the_anchors_row([far], label, "A", vocabulary, 0.0) is None
    near = at("A*24", label.x1 + (MAX_GAP - 5) * label.height)
    assert on_the_anchors_row([near], label, "A", vocabulary, 0.0) is not None


def test_the_gap_is_measured_from_the_previous_cell_not_the_anchor(vocabulary) -> None:
    """A heterozygous locus prints two alleles and the second sits two gaps
    out. Measuring both from the label would need a cap wide enough to reach
    the next column, which is how a value gets bound to the wrong locus."""
    label = anchor()
    step = (MAX_GAP - 2) * label.height
    first = at("A*24", label.x1 + step)
    second = at("A*02", first.x1 + step)
    found = on_the_anchors_row([first, second], label, "A", vocabulary, 0.0)
    assert found is not None and len(found) == 2


def test_a_value_inside_another_loci_cell_is_refused(vocabulary) -> None:
    """The finding that invalidated the first version. Two loci on one printed
    band is a normal layout; with HLA-A's own cell blank and `A*24` sitting in
    HLA-B's cell, `resolve_locus` refuses it as "geometry and text disagree"
    and sends it to a person. Agreeing prefixes do not overrule that."""
    a_label = Box(x0=0.05, y0=ROW, x1=0.14, y1=ROW + HEIGHT, text="HLA-A")
    b_label = Box(x0=0.50, y0=ROW, x1=0.59, y1=ROW + HEIGHT, text="HLA-B")
    stray = at("A*24", 0.61)
    assert on_the_anchors_row([a_label, b_label, stray], a_label, "A", vocabulary, 0.0) is None


def test_a_star_less_token_on_the_row_taints_it(vocabulary) -> None:
    """`A24` parses WITH a prefix and `separator_missing`. The first version
    skipped it past, which hid it from MAX_VALUES entirely: a row of three
    tokens could bind two and report a complete pair."""
    boxes = [at("A24", 0.20), at("A*02", 0.32), at("A*11", 0.44)]
    assert on_the_anchors_row(boxes, anchor(), "A", vocabulary, 0.0) is None


def test_the_comparison_sheet_guard_fails_closed() -> None:
    """It is the only thing standing between this pass and the right gene of
    the wrong person. Returning an empty set from a query that could not run is
    indistinguishable from a corpus with no comparison sheets, and this corpus
    has 450."""
    import sqlite3

    import anchor_row_bind

    con = sqlite3.connect(":memory:")
    with pytest.raises(sqlite3.OperationalError):
        anchor_row_bind.comparison_sheets(con)
    con.close()


def test_a_bound_fact_carries_the_boxes_it_was_read_from() -> None:
    """Without them `cell_crop_box` has nothing to crop and the review page
    shows a RESOLVED medical value with no pixels behind it — the defect that
    made 50 of one round's 220 answers unusable."""
    source = Path(__import__("anchor_row_bind").__file__).read_text(encoding="utf-8")
    write = source.split("UPDATE fact SET")[1].split(")")[0]
    assert "value_boxes=?" in write
    assert "anchor_box=?" in write
    assert "raw=?" in write


def test_the_pass_answers_only_the_empty_cell_refusal() -> None:
    """Every other refusal is a different question owned by another pass, and
    quietly answering them all is how a narrow rule becomes a wide one."""
    import anchor_row_bind

    assert anchor_row_bind.EMPTY_CELL == (
        "anchor found but no box at all in its cell under this rule"
    )
    assert anchor_row_bind.SOURCE == "anchor-row-prefix"
    # The work query must select on that reason alone.
    source = Path(anchor_row_bind.__file__).read_text(encoding="utf-8")
    assert "AND reason = ?" in source
