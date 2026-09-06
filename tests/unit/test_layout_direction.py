"""Which way a form reads, asked of the page rather than assumed.

The reviewer set out the procedure, and these tests are it in order: know the
slope, find the locus names, ask whether a line at that slope from one locus
name reaches another (they are column headers) or whether it takes a line down
the page instead (they are row labels), then ask the same of the values.

The default matters as much as the detection. `right` is the layout of the
overwhelming majority of this corpus, and a form read the wrong way round binds
one locus's value to another — the worst failure this project can produce — so
a page gets `below` only when both questions agree, and `right` whenever it
cannot tell.
"""

from __future__ import annotations

from kidneymatch.ocr.anchors import Box
from kidneymatch.ocr.layout import (
    reading_direction,
    share_a_column,
    share_a_row,
    value_along_the_row,
    value_under_the_label,
)

UNIT = 0.02


def box(text: str, x0: float, y0: float, *, width: float = 0.09) -> Box:
    return Box(x0=x0, y0=y0, x1=x0 + width, y1=y0 + UNIT, text=text)


def row_labelled_form(slope: float = 0.0) -> list[Box]:
    """Labels stacked down the left, values to the right: the common layout."""
    page: list[Box] = []
    for index, (label, first, second) in enumerate(
        [("HLA-A", "A*24", "A*02"), ("HLA-B", "B*35", "B*51"), ("HLA-C", "C*04", "C*07")]
    ):
        top = 0.20 + index * 4 * UNIT
        page.append(box(label, 0.10, top))
        page.append(box(first, 0.35, top + slope * 0.25))
        page.append(box(second, 0.60, top + slope * 0.50))
    return page


def header_form(lean: float = 0.0) -> list[Box]:
    """Labels side by side across the top, each value in the column beneath."""
    page: list[Box] = []
    for index, (label, value) in enumerate(
        [("HLA-A", "A*24"), ("HLA-B", "B*35"), ("HLA-C", "C*04")]
    ):
        left = 0.15 + index * 0.28
        page.append(box(label, left, 0.10))
        page.append(box(value, left + lean * 0.06, 0.16))
    return page


def test_a_line_at_the_pages_slope_reaches_the_next_label_on_a_header_form() -> None:
    page = header_form()
    labels = [b for b in page if b.text.startswith("HLA")]
    assert share_a_row(labels[0], labels[1])
    assert not share_a_column(labels[0], labels[1])


def test_it_takes_a_vertical_line_on_a_row_labelled_form() -> None:
    page = row_labelled_form()
    labels = [b for b in page if b.text.startswith("HLA")]
    assert share_a_column(labels[0], labels[1])
    assert not share_a_row(labels[0], labels[1])


def test_two_labels_stacked_on_one_another_do_not_share_a_row() -> None:
    """Whatever they are, boxes that overlap in x are not side by side."""
    assert not share_a_row(box("HLA-A", 0.10, 0.20), box("HLA-B", 0.11, 0.22))


def test_the_slope_is_what_makes_a_tilted_header_row_one_row() -> None:
    """A header 0.40 across on a page falling 0.15 per unit width sits three
    label heights below its neighbour, and a flat comparison loses the pair."""
    first = box("HLA-A", 0.15, 0.100)
    second = box("HLA-B", 0.55, 0.100 + 0.15 * 0.40)
    assert not share_a_row(first, second, 0.0)
    assert share_a_row(first, second, 0.15)


def test_the_column_lean_is_what_keeps_a_tilted_column_one_column() -> None:
    lean = 1.2
    label = box("HLA-A", 0.15, 0.10)
    value = box("A*24", 0.15 + lean * 0.06, 0.16)
    assert not share_a_column(label, value, 0.0)
    assert share_a_column(label, value, lean)


def test_the_values_are_found_where_each_form_puts_them() -> None:
    rows = row_labelled_form()
    headers = header_form()
    label_of = lambda page: next(b for b in page if b.text == "HLA-A")  # noqa: E731
    assert value_along_the_row(label_of(rows), rows)
    assert not value_under_the_label(label_of(rows), rows)
    assert value_under_the_label(label_of(headers), headers)
    assert not value_along_the_row(label_of(headers), headers)


def test_a_row_labelled_form_reads_rightwards() -> None:
    found = reading_direction(row_labelled_form())
    assert found.direction == "right"
    assert found.loci_sharing_a_column > found.loci_sharing_a_row


def test_a_header_form_reads_downwards() -> None:
    """The reviewer's page: 'it writes each allele in the cell under the loci'."""
    found = reading_direction(header_form())
    assert found.direction == "below"
    assert found.loci_sharing_a_row >= 2
    assert found.values_under_the_label > found.values_along_the_row


def test_a_tilted_header_form_still_reads_downwards() -> None:
    page = []
    for index, (label, value) in enumerate(
        [("HLA-A", "A*24"), ("HLA-B", "B*35"), ("HLA-C", "C*04")]
    ):
        left = 0.15 + index * 0.28
        page.append(box(label, left, 0.10 + 0.05 * left))
        page.append(box(value, left, 0.16 + 0.05 * left))
    assert reading_direction(page, 0.05, 0.0).direction == "below"


def test_too_few_labels_to_read_a_layout_keeps_the_default() -> None:
    """One label says nothing about a form, and guessing would be a coin toss."""
    page = [box("HLA-A", 0.15, 0.10), box("A*24", 0.15, 0.16)]
    found = reading_direction(page)
    assert found.direction == "right"
    assert "too few" in found.reason


def test_a_page_with_no_values_anywhere_keeps_the_default() -> None:
    page = [box("HLA-A", 0.15, 0.10), box("HLA-B", 0.43, 0.10), box("HLA-C", 0.71, 0.10)]
    assert reading_direction(page).direction == "right"
