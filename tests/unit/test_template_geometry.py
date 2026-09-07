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
    AMBIGUITY_MARGIN,
    CONSTANT_LABELS,
    LOO_MAX_RESIDUAL,
    MAX_RESIDUAL,
    LayoutPrototype,
    assign_prototype,
    constant_label_positions,
    fit_similarity,
    fit_y_only,
    merge_prefix_fragments,
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


# --- a tie between prototypes that are one form under lean -----------------
#
# Measured over the 11,210 pages with no family: 987 fit a prototype inside
# MAX_RESIDUAL and were refused only because a second prototype fitted nearly
# as well. On those pages the tied prototypes are FORM#0/#1/#3, which are one
# printed form leaning different ways — their y-only residuals against each
# other are 0.016, 0.001 and 0.017, all inside MAX_RESIDUAL, and forcing the
# runner-up instead of the best changes one cell of 7,896. A tie between
# prototypes that author the same cell rule AND agree on the row order is
# therefore not ambiguity about which rule to apply. A tie between two
# genuinely different layouts still is.


def leaning(lean: float, name: str) -> LayoutPrototype:
    """The same row stack with its column leaning: one form, photographed askew."""
    return LayoutPrototype.from_positions(
        name,
        {
            locus: (0.15 + lean * index, 0.20 + index * PITCH)
            for index, locus in enumerate(ROW_ORDER)
        },
    )


def leaning_page(lean: float) -> list[Box]:
    """A page whose own lean sits between two prototypes' — the measured case."""
    return [
        Box(
            x0=0.15 + lean * index,
            y0=0.20 + index * PITCH,
            x1=0.25 + lean * index,
            y1=0.225 + index * PITCH,
            text=f"HLA-{locus}",
        )
        for index, locus in enumerate(ROW_ORDER)
    ]


TWINS = [leaning(0.0, "LEAN#0"), leaning(0.002, "LEAN#1")]


def test_a_tie_between_prototypes_that_author_one_rule_and_one_layout_assigns() -> None:
    rule_of = dict.fromkeys((p.prototype_id for p in TWINS), "family")
    assignment = assign_prototype(leaning_page(0.001), TWINS, rule_of=rule_of)
    assert assignment is not None
    assert {assignment.prototype_id, *assignment.tied_with} == {"LEAN#0", "LEAN#1"}, (
        "the tie is visible in provenance"
    )
    assert assignment.runner_up_residual == pytest.approx(assignment.residual, rel=1e-3)


def test_a_tie_between_prototypes_that_author_different_rules_is_refused() -> None:
    """Two rules cannot both be applied to one page's cells."""
    rule_of = {"LEAN#0": "family", "LEAN#1": "default"}
    assert assign_prototype(leaning_page(0.001), TWINS, rule_of=rule_of) is None


def test_a_tie_between_the_same_rule_but_a_different_row_order_is_refused() -> None:
    """Rule-id equality is not layout agreement.

    The virtual-anchor path places an unreadable label where the prototype
    says the form prints it, so two prototypes that tie must also agree on
    WHICH ROW each label is on — including the labels this page does not
    print, which are exactly the ones that path would place. Here the two
    prototypes agree on the three labels the page does print and disagree on
    the rest: the page fits both perfectly and identifies neither.
    """
    stack = {locus: (0.15, 0.20 + index * PITCH) for index, locus in enumerate(ROW_ORDER)}
    reordered = list(ROW_ORDER)
    reordered[3], reordered[7] = reordered[7], reordered[3]
    twins = [
        LayoutPrototype.from_positions("STACK#0", stack),
        LayoutPrototype.from_positions(
            "PERMUTED",
            {locus: (0.15, 0.20 + index * PITCH) for index, locus in enumerate(reordered)},
        ),
    ]
    rule_of = dict.fromkeys((p.prototype_id for p in twins), "family")
    class_i = [b for b in form() if b.text.removeprefix("HLA-") in ("A", "B", "C")]
    assert assign_prototype(class_i, twins, rule_of=rule_of) is None


def test_without_a_rule_map_a_tie_is_still_refused() -> None:
    """`template_discovery.py` calls this with no rule map; nothing moves there."""
    assert assign_prototype(leaning_page(0.001), TWINS) is None


def test_the_registry_prototypes_are_one_form_under_lean() -> None:
    """The y-only residuals measured between FORM#1 and FORM#0's stored rows."""
    one = {"A": (0.0065, -1.4265), "B": (0.007, -1.0595), "C": (0.009, -0.6921)}
    zero = {"A": (0.0752, -1.4002), "B": (0.0623, -1.051), "C": (0.0461, -0.6973)}
    residual = fit_y_only(one, zero)
    assert residual is not None and residual <= MAX_RESIDUAL


# --- the left-out fit ------------------------------------------------------
#
# The rule reaches 209 pages of the no-family population on this build, because
# the `HLA-` repair is tried first; with the repair disabled the same pass
# assigns 263 by this fit. The survey that authored the rule looked at 318 such
# pages and found the dropped label to be a MIDDLE label of the printed stack on
# 241 of them, with its deviation under the full fit in x on 310: the recognizer
# boxed that label's `HLA-` prefix separately, or did not box it at all, which
# moves the label's centre right. It is not a perspective effect and not the end
# of the stack.


def displaced(locus: str, dx: float, dy: float = 0.0) -> list[Box]:
    """The form with one label's box moved: its `HLA-` prefix boxed apart."""
    boxes = []
    for index, name in enumerate(ROW_ORDER):
        y = 0.20 + index * PITCH + (dy if name == locus else 0.0)
        x = 0.15 + (dx if name == locus else 0.0)
        boxes.append(Box(x0=x, y0=y, x1=x + 0.10, y1=y + 0.025, text=f"HLA-{name}"))
    return boxes


def test_a_stack_that_fits_except_at_one_label_is_assigned_without_it() -> None:
    prototype = LayoutPrototype.from_positions("YEKTA#0", constant_label_positions(form()))
    page = displaced("DQB1", dx=0.055)
    assert assign_prototype(page, [prototype]) is None, "the full fit must refuse it"
    assignment = assign_prototype(page, [prototype], leave_one_out=True)
    assert assignment is not None
    assert assignment.prototype_id == "YEKTA#0"
    assert assignment.dropped_label == "DQB1"
    assert assignment.residual <= LOO_MAX_RESIDUAL
    assert assignment.n_labels == len(ROW_ORDER) - 1


def test_a_label_displaced_out_of_the_label_column_is_not_a_left_out_fit() -> None:
    """The 44 far pages: the dropped box sits in the VALUE area, a median 26
    label heights right of the column — a value read as a bare locus name, not
    a label whose printed prefix was boxed apart."""
    prototype = LayoutPrototype.from_positions("YEKTA#0", constant_label_positions(form()))
    assert assign_prototype(displaced("DQB1", dx=0.40), [prototype], leave_one_out=True) is None


def test_a_label_displaced_down_the_page_is_not_a_left_out_fit() -> None:
    """A deviation in y is a different row order, not a split prefix."""
    prototype = LayoutPrototype.from_positions("YEKTA#0", constant_label_positions(form()))
    page = displaced("DQB1", dx=0.004, dy=0.055)
    assert assign_prototype(page, [prototype], leave_one_out=True) is None


def test_five_labels_are_too_few_to_leave_one_out() -> None:
    """Fitting four remaining points to a prototype is the weakest case there is."""
    prototype = LayoutPrototype.from_positions("YEKTA#0", constant_label_positions(form()))
    page = [b for b in displaced("DQB1", dx=0.055) if b.text.removeprefix("HLA-") in ROW_ORDER[:5]]
    assert len(page) == 5
    assert assign_prototype(page, [prototype], leave_one_out=True) is None


def test_a_left_out_fit_two_prototypes_share_is_refused() -> None:
    """The mainline ambiguity margin applies to the left-out fit too."""
    positions = constant_label_positions(form())
    twins = [
        LayoutPrototype.from_positions("A#0", positions),
        LayoutPrototype.from_positions("A#1", positions),
    ]
    rule_of = dict.fromkeys((p.prototype_id for p in twins), "family")
    page = displaced("DQB1", dx=0.055)
    assert assign_prototype(page, twins, leave_one_out=True, rule_of=rule_of) is None


def test_a_scrambled_prototype_admits_nothing_through_the_left_out_fit() -> None:
    scrambled = list(ROW_ORDER)
    scrambled[0], scrambled[3] = scrambled[3], scrambled[0]
    scrambled[2], scrambled[6] = scrambled[6], scrambled[2]
    prototype = LayoutPrototype.from_positions(
        "SCRAMBLED",
        {locus: (0.15, 0.20 + index * PITCH) for index, locus in enumerate(scrambled)},
    )
    assert assign_prototype(displaced("DQB1", dx=0.055), [prototype], leave_one_out=True) is None


def test_the_left_out_fit_records_the_runner_up_it_beat() -> None:
    prototype = LayoutPrototype.from_positions("YEKTA#0", constant_label_positions(form()))
    other = LayoutPrototype.from_positions(
        "OTHER",
        {locus: (0.15, 0.20 + (index**1.6) * PITCH) for index, locus in enumerate(ROW_ORDER)},
    )
    assignment = assign_prototype(
        displaced("DQB1", dx=0.055), [prototype, other], leave_one_out=True
    )
    assert assignment is not None and assignment.prototype_id == "YEKTA#0"
    assert assignment.runner_up_residual is not None
    assert assignment.runner_up_residual > assignment.residual * AMBIGUITY_MARGIN


# --- what the page prints that the prototype does not ----------------------


def test_a_page_printing_a_label_the_prototype_lacks_is_not_that_form() -> None:
    """Measured on the two-column five-label form: 18 pages printing DPA1,
    DPB1 or DQA1 were assigned to a prototype that prints none of them,
    because the fit only ever sees the labels the two have in common."""
    five = LayoutPrototype.from_positions(
        "FIVE#0",
        {
            locus: point
            for locus, point in constant_label_positions(form()).items()
            if locus in ("A", "B", "C", "DRB1", "DQB1")
        },
    )
    assert assign_prototype(form(), [five]) is None
    prints_five = [b for b in form() if b.text.removeprefix("HLA-") in five.positions]
    assert assign_prototype(prints_five, [five]) is not None


def test_a_subset_prototype_competes_only_on_a_distinguishing_label() -> None:
    """A three-label collinear fit against a five-label prototype outcompeted
    an eight-point fit and took 66-103 documents away from their own family.

    A prototype whose labels are a strict subset of another's may compete only
    when the page shows enough of them to tell the two forms apart. For the
    two-column form that means one of its second-column labels: A, B and C
    alone stand in one line and identify nothing.
    """
    eight = LayoutPrototype.from_positions("YEKTA#0", constant_label_positions(form()))
    class_i = [b for b in form() if b.text.removeprefix("HLA-") in ("A", "B", "C")]
    two_column = [
        *class_i,
        Box(x0=0.55, y0=0.20, x1=0.65, y1=0.225, text="HLA-DRB1"),
        Box(x0=0.55, y0=0.26, x1=0.65, y1=0.285, text="HLA-DQB1"),
    ]
    five = LayoutPrototype.from_positions("FIVE#0", constant_label_positions(two_column))

    on_three = assign_prototype(class_i, [five, eight])
    assert on_three is None or on_three.prototype_id != "FIVE#0", (
        "three labels in one line do not identify the two-column form"
    )
    assignment = assign_prototype(two_column, [five, eight])
    assert assignment is not None and assignment.prototype_id == "FIVE#0"


# --- the placebo the left-out fit has to survive ---------------------------


def test_a_prototype_translated_by_one_row_is_refused_at_the_plain_stage() -> None:
    """Translation is a SYMMETRY of a uniformly-pitched stack.

    Take the true form and move every label onto the next row down, wrapping
    the last one to the top. Seven of the eight correspondences are then a
    pure translation, which a scale-and-offset fit absorbs exactly; only the
    wrapped label disagrees. Leaving that one out gives a perfect fit to a
    form whose rows are all one place out — and a cell rule applied under it
    reads every value off the wrong row.

    The plain fit must refuse it (the wrapped label is eight pitches out), and
    the left-out fit must refuse it too: the dropped box stands in the label
    column, so only the x-dominance test separates this from the population
    the rule is for.
    """
    rotated = ROW_ORDER[-1:] + ROW_ORDER[:-1]
    prototype = LayoutPrototype.from_positions(
        "TRANSLATED",
        {locus: (0.15, 0.20 + index * PITCH) for index, locus in enumerate(rotated)},
    )
    page = form()
    plain = fit_similarity(constant_label_positions(page), prototype)
    assert plain is not None and plain.residual > MAX_RESIDUAL, "the plain fit must refuse it"
    assert assign_prototype(page, [prototype]) is None
    assert assign_prototype(page, [prototype], leave_one_out=True) is None


# --- putting a boxed-apart `HLA-` prefix back on its label -----------------
#
# The direct repair of the population the left-out fit accommodates. Measured
# over the no-family pages on this build: joining the fragment back assigns 162
# pages at the ORDINARY tolerance and leaves 209 for that fit — the residue. Of
# those 162, 54 are pages the left-out fit would otherwise have taken by
# dropping a printed label (it reaches 263 with the repair disabled, 209 with
# it), and the other 108 were refused outright before the repair existed.


def split_prefix(locus: str, gap: float = 0.004) -> list[Box]:
    """The form, with one label's `HLA-` boxed apart from the rest of the word.

    The fragment keeps the label's printed left edge, and what is left of the
    label starts where `HLA-` ended, so the label's CENTRE moves right — which
    is what pushes the page's stack past the template tolerance.
    """
    boxes = []
    for index, name in enumerate(ROW_ORDER):
        y = 0.20 + index * PITCH
        if name != locus:
            boxes.append(Box(x0=0.15, y0=y, x1=0.25, y1=y + 0.025, text=f"HLA-{name}"))
            continue
        boxes.append(Box(x0=0.15, y0=y, x1=0.19, y1=y + 0.025, text="HLA-"))
        boxes.append(Box(x0=0.19 + gap, y0=y, x1=0.25, y1=y + 0.025, text=name))
    return boxes


def test_a_label_whose_prefix_was_boxed_apart_fits_at_the_ordinary_tolerance() -> None:
    prototype = LayoutPrototype.from_positions("YEKTA#0", constant_label_positions(form()))
    page = split_prefix("DQB1")
    assignment = assign_prototype(page, [prototype], leave_one_out=True)
    assert assignment is not None
    assert assignment.merged_prefixes == ("DQB1",)
    assert assignment.dropped_label is None, "nothing was left out; the word was put back"
    assert assignment.residual <= MAX_RESIDUAL


def test_the_repair_is_not_tried_before_the_ordinary_fit() -> None:
    """A page that fits outright is assigned exactly as it was before this
    existed: the merge runs only after the plain fit has refused."""
    prototype = LayoutPrototype.from_positions("YEKTA#0", constant_label_positions(form()))
    assignment = assign_prototype(form(scale=0.9), [prototype], leave_one_out=True)
    assert assignment is not None
    assert assignment.merged_prefixes == ()


def test_the_repair_is_off_when_the_left_out_fit_is() -> None:
    """`template_discovery.py` gets neither: a prototype must not be built
    from a page whose labels the pipeline reassembled."""
    prototype = LayoutPrototype.from_positions("YEKTA#0", constant_label_positions(form()))
    assert assign_prototype(split_prefix("DQB1"), [prototype]) is None


def test_a_fragment_that_is_not_touching_a_label_is_left_alone() -> None:
    """`HLA-` printed as a heading somewhere else on the page is not the
    prefix of any label, and joining it would move a label arbitrarily."""
    page = [*form(), Box(x0=0.60, y0=0.05, x1=0.66, y1=0.075, text="HLA-")]
    merged, repaired, sources = merge_prefix_fragments(page)
    assert repaired == () and sources == {}
    assert merged is page


def test_the_joined_box_keeps_the_label_text_it_had() -> None:
    """Geometry is what the repair changes. The locus a box names must go on
    coming from the same characters it came from before."""
    merged, repaired, sources = merge_prefix_fragments(split_prefix("DQB1"))
    assert repaired == ("DQB1",)
    assert len(merged) == len(ROW_ORDER), "the fragment is no longer a box of its own"
    joined = next(box for box in merged if box.text == "DQB1")
    assert joined.x0 == pytest.approx(0.15) and joined.x1 == pytest.approx(0.25)
    assert len(sources) == 1
