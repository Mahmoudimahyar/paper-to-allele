"""A bare `A`, `B` or `C` becomes a locus label only where structure says so.

`glyphs.canonical_locus_label` refuses a bare Class I letter and must go on
refusing it: `A` is also a blood group, an initial, a list marker and a column
heading, and one character cannot name a locus by what it says. The
constitution already settles who may: the printed cell assigns the locus, never
the text. These tests pin the structural conditions that let the page promote
the letter, and — more importantly — the ones that must not.

Measured on the corpus before this rule existed, a form printing its Class I
labels bare left A, B and C unread on every page it produced; on the reviewer's
220 labels it was the largest single cause of a locus never being looked for.
"""

from __future__ import annotations

from kidneymatch.ocr.anchors import (
    Box,
    ResolutionStatus,
    ValueRule,
    _bare_class_i_column,
    find_anchors,
    resolve_locus,
)

RULE = ValueRule(direction="right", align_overlap=0.2, max_gap=12.0, max_values=2)
UNIT = 0.02  # one label height, the scale every tolerance is written in


def label(text: str, row: int, *, x0: float = 0.10) -> Box:
    """A label box in the left-hand column, one row pitch apart."""
    top = 0.10 + row * 2 * UNIT
    return Box(x0=x0, y0=top, x1=x0 + 0.06, y1=top + UNIT, text=text)


def value(text: str, row: int, *, x0: float = 0.22) -> Box:
    top = 0.10 + row * 2 * UNIT
    return Box(x0=x0, y0=top, x1=x0 + 0.08, y1=top + UNIT, text=text)


# A form printing Class I bare and Class II spelled out: the case this exists
# for. The Class I rows sit four row pitches above the Class II labels, which
# is why proximity alone cannot be the test.
TABLE = [
    label("A", 0),
    value("A*24", 0),
    value("A*02", 0, x0=0.34),
    label("B", 1),
    value("B*35", 1),
    value("B*51", 1, x0=0.34),
    label("HLA-DRB1", 4),
    value("DRB1*15", 4),
    label("HLA-DQB1", 5),
    value("DQB1*03", 5),
]


def test_two_bare_letters_stacked_in_the_label_column_are_labels() -> None:
    found = _bare_class_i_column(TABLE)
    assert sorted(found) == ["A", "B"]


def test_the_promoted_letter_binds_its_own_row() -> None:
    result = resolve_locus(TABLE, "A", RULE)
    assert result.status is ResolutionStatus.RESOLVED
    assert result.values == ["A*24", "A*02"]


def test_a_spelled_out_label_is_preferred_over_a_bare_letter() -> None:
    """A page printing `HLA-A` is never re-read from a stray `A` elsewhere."""
    spelled = label("HLA-A", 0, x0=0.10)
    stray = label("A", 8, x0=0.10)
    anchors = find_anchors([spelled, value("A*24", 0), stray, *TABLE[3:]], "A")
    assert anchors == [spelled]


def test_a_lone_letter_far_from_every_printed_label_is_refused() -> None:
    """One letter is a blood group as easily as a locus. Two are a table."""
    lone = [
        label("A", 0),
        value("A*24", 0),
        label("HLA-DRB1", 4),
        value("DRB1*15", 4),
        label("HLA-DQB1", 5),
        value("DQB1*03", 5),
    ]
    assert _bare_class_i_column(lone) == {}
    assert resolve_locus(lone, "A", RULE).status is not ResolutionStatus.RESOLVED


def test_a_lone_letter_beside_a_printed_label_is_allowed() -> None:
    """Inside the block, one letter has the page's own labels vouching for it."""
    beside = [
        label("A", 3),
        value("A*24", 3),
        label("HLA-DRB1", 4),
        value("DRB1*15", 4),
        label("HLA-DQB1", 5),
        value("DQB1*03", 5),
    ]
    assert sorted(_bare_class_i_column(beside)) == ["A"]


def test_a_letter_outside_the_label_column_is_refused() -> None:
    """A letter in the value columns is a value, or a footnote marker."""
    off = [b for b in TABLE if b.text != "A"] + [label("A", 0, x0=0.55)]
    assert "A" not in _bare_class_i_column(off)


def test_a_letter_whose_row_holds_no_allele_is_refused() -> None:
    """`Blood group   A   Rh   positive` prints letters in a column too."""
    grouped = [
        label("A", 0),
        value("positive", 0),
        label("B", 1),
        value("negative", 1),
        label("HLA-DRB1", 4),
        value("DRB1*15", 4),
        label("HLA-DQB1", 5),
        value("DQB1*03", 5),
    ]
    assert _bare_class_i_column(grouped) == {}


def test_a_page_that_prints_no_locus_at_all_promotes_nothing() -> None:
    """Without two spelled-out labels there is no evidence of an HLA table."""
    bare_only = [label("A", 0), value("A*24", 0), label("B", 1), value("B*35", 1)]
    assert _bare_class_i_column(bare_only) == {}


def test_only_class_i_letters_are_ever_promoted() -> None:
    """`D` and `E` are not loci however well placed they are."""
    others = [b for b in TABLE if b.text not in ("A", "B")] + [
        label("D", 0),
        label("E", 1),
    ]
    assert _bare_class_i_column(others) == {}
