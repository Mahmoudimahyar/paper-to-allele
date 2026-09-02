"""Recognising which printed form a document is, from its label geometry.

Written before the implementation. Template discovery assigned 707 of 23,485
documents to a verified family while one laboratory alone accounts for about
two thirds of the corpus. The review diagnosed three causes, all reproduced:

1. **The signature counted the grouped row's VALUES as labels.** 12,178 of
   12,641 standalone `DRB3` boxes sit on the `DRB3/4/5` header's row, where they
   are the patient's presence typing. One form therefore split into at least
   seven "templates" by genotype. This also explains ADR 0007's `DRB4` in two
   columns 0.285 apart: `DRB4` sits at x 0.709 when `DRB3` shares the row and
   0.474 when it is alone.
2. **Absolute page coordinates on hand-held photographs.** The `HLA-A` label
   spans y 0.165 to 0.408 between the 10th and 90th percentiles, so clustering
   in page space fragments one form into position blobs.
3. Purity then failed on those value-bearing "labels".

The fix is to build the signature from labels the FORM prints in fixed places,
and to compare documents in a frame derived from the document itself rather
than from the page.
"""

from __future__ import annotations

import pytest

from kidneymatch.ocr.anchors import Box
from kidneymatch.ocr.templates import (
    CONSTANT_LABELS,
    MAX_RESIDUAL,
    LayoutPrototype,
    assign_prototype,
    constant_label_positions,
    fit_similarity,
)

# A form: eight label rows in one column, evenly spaced, with the grouped
# DRB3/4/5 header between DRB1 and DPB1 as on the dominant letterhead.
ROW_ORDER = ("A", "B", "C", "DQB1", "DRB1", "DPB1", "DPA1", "DQA1")
PITCH = 0.06


def form(scale: float = 1.0, dx: float = 0.0, dy: float = 0.0) -> list[Box]:
    boxes = []
    for index, locus in enumerate(ROW_ORDER):
        y = (0.20 + index * PITCH) * scale + dy
        x = 0.15 * scale + dx
        boxes.append(
            Box(x0=x, y0=y, x1=x + 0.10 * scale, y1=y + 0.025 * scale, text=f"HLA-{locus}")
        )
    return boxes


def test_only_labels_the_form_prints_in_a_fixed_place_are_in_the_signature() -> None:
    assert set(CONSTANT_LABELS) == {"A", "B", "C", "DRB1", "DQA1", "DQB1", "DPA1", "DPB1"}
    assert "DRB3" not in CONSTANT_LABELS
    assert "DRB4" not in CONSTANT_LABELS
    assert "DRB5" not in CONSTANT_LABELS


def test_a_gene_name_on_the_grouped_row_is_not_a_label() -> None:
    """It is the patient's presence typing, and it moves with the genotype.

    Counting it split one laboratory's single form into at least seven
    "templates" and produced ADR 0007's two-column `DRB4`.
    """
    header = Box(x0=0.15, y0=0.50, x1=0.29, y1=0.525, text="HLA-DRB3/4/5")
    on_the_row = Box(x0=0.45, y0=0.502, x1=0.51, y1=0.527, text="DRB4")
    positions = constant_label_positions([*form(), header, on_the_row])
    assert "DRB4" not in positions
    assert set(positions) == set(ROW_ORDER)


def test_a_label_is_taken_once_even_if_it_appears_twice() -> None:
    duplicate = Box(x0=0.60, y0=0.90, x1=0.70, y1=0.925, text="HLA-A")
    positions = constant_label_positions([*form(), duplicate])
    assert positions.get("A") is None, "an ambiguous label position is not a signature point"


# --- the similarity fit --------------------------------------------------


def test_the_same_form_photographed_closer_still_fits() -> None:
    """A hand-held photograph changes scale and offset, not the layout."""
    prototype = LayoutPrototype.from_positions("P", constant_label_positions(form()))
    zoomed = constant_label_positions(form(scale=1.4, dx=0.05, dy=-0.03))
    fit = fit_similarity(zoomed, prototype)
    assert fit is not None
    assert fit.residual < 1e-6


def test_a_form_with_a_different_row_order_does_not_fit() -> None:
    """Reordering the rows is a different printed form, and no scale or offset
    can absorb it."""
    reordered = list(ROW_ORDER)
    reordered[0], reordered[4] = reordered[4], reordered[0]
    boxes = [
        Box(x0=0.15, y0=0.20 + i * PITCH, x1=0.25, y1=0.225 + i * PITCH, text=f"HLA-{locus}")
        for i, locus in enumerate(reordered)
    ]
    prototype = LayoutPrototype.from_positions("P", constant_label_positions(form()))
    fit = fit_similarity(constant_label_positions(boxes), prototype)
    assert fit is None or fit.residual > MAX_RESIDUAL


def test_uneven_row_spacing_is_a_different_form() -> None:
    """A similarity absorbs scale and offset, so the rows must differ in a way
    that a uniform rescale cannot explain."""
    boxes = [
        Box(
            x0=0.15,
            y0=0.20 + (i**1.6) * PITCH,
            x1=0.25,
            y1=0.225 + (i**1.6) * PITCH,
            text=f"HLA-{locus}",
        )
        for i, locus in enumerate(ROW_ORDER)
    ]
    prototype = LayoutPrototype.from_positions("P", constant_label_positions(form()))
    fit = fit_similarity(constant_label_positions(boxes), prototype)
    assert fit is None or fit.residual > MAX_RESIDUAL


def test_a_document_with_too_few_labels_is_not_assigned() -> None:
    """Two points fix a scale and an offset exactly, so they always "fit"."""
    prototype = LayoutPrototype.from_positions("P", constant_label_positions(form()))
    two = {
        label: position
        for label, position in constant_label_positions(form()).items()
        if label in ("A", "B")
    }
    assert fit_similarity(two, prototype) is None


def test_three_labels_are_enough() -> None:
    prototype = LayoutPrototype.from_positions("P", constant_label_positions(form()))
    three = {
        label: position
        for label, position in constant_label_positions(form()).items()
        if label in ("A", "DRB1", "DQA1")
    }
    fit = fit_similarity(three, prototype)
    assert fit is not None and fit.residual < 1e-6


# --- assignment ----------------------------------------------------------


def test_a_document_is_assigned_to_the_prototype_it_matches() -> None:
    """The alternative must be a genuinely different LAYOUT.

    A copy of the same form shifted across the page is the same form: the fit
    absorbs translation on purpose, because that is what moving the paper under
    the camera does.
    """
    prototype = LayoutPrototype.from_positions("YEKTA#0", constant_label_positions(form()))
    reordered = list(ROW_ORDER)
    reordered[1], reordered[6] = reordered[6], reordered[1]
    other = LayoutPrototype.from_positions(
        "OTHER",
        {locus: (0.15, 0.20 + index * PITCH) for index, locus in enumerate(reordered)},
    )
    assignment = assign_prototype(form(scale=1.2), [prototype, other])
    assert assignment is not None and assignment.prototype_id == "YEKTA#0"


def test_the_same_form_moved_across_the_page_is_still_that_form() -> None:
    prototype = LayoutPrototype.from_positions("YEKTA#0", constant_label_positions(form()))
    assignment = assign_prototype(form(dx=0.30, dy=0.12), [prototype])
    assert assignment is not None and assignment.prototype_id == "YEKTA#0"


def test_a_document_matching_nothing_stays_unassigned() -> None:
    """An unassigned document is not a failure: it gets the default rule.

    Claiming a family it does not belong to would apply that family's authored
    value rule to a layout it was never measured on.
    """
    prototype = LayoutPrototype.from_positions("YEKTA#0", constant_label_positions(form()))
    scattered = [
        Box(x0=0.1, y0=0.1, x1=0.2, y1=0.12, text="HLA-A"),
        Box(x0=0.8, y0=0.5, x1=0.9, y1=0.52, text="HLA-B"),
        Box(x0=0.2, y0=0.9, x1=0.3, y1=0.92, text="HLA-DRB1"),
    ]
    assert assign_prototype(scattered, [prototype]) is None


def test_a_document_that_fits_two_prototypes_equally_is_unassigned() -> None:
    """Two families cannot both author the cell rule for one page."""
    positions = constant_label_positions(form())
    twins = [
        LayoutPrototype.from_positions("A#0", positions),
        LayoutPrototype.from_positions("A#1", positions),
    ]
    assert assign_prototype(form(), twins) is None


def test_the_assignment_records_what_it_fitted() -> None:
    """Provenance: which prototype, how well, and on how many labels."""
    prototype = LayoutPrototype.from_positions("YEKTA#0", constant_label_positions(form()))
    assignment = assign_prototype(form(scale=0.8), [prototype])
    assert assignment is not None
    assert assignment.n_labels == len(ROW_ORDER)
    assert assignment.residual < 1e-6
    # The scale carries the DOCUMENT onto the PROTOTYPE, so a page photographed
    # at 0.8 needs 1.25 to get there.
    assert assignment.scale == pytest.approx(1.25, abs=1e-6)
