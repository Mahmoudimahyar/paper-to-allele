"""The gates that stop a value being bound to the wrong locus.

Written before the code. These encode what a shape audit of the existing
resolver found on 2026-09-02: of 2,977 `DRB1` bindings it called RESOLVED, only
185 were allele-shaped and **988 were the next row's locus label**. `DPA1` and
`DPB1` produced zero real values. Every one of those would have entered the
database as a patient's HLA typing.

Nothing in the previous test suite could catch it, because every test asked
"did the rule bind the box I expected?" and none asked "is the thing it bound
even a value?". These do.

Four gates, each with its own failure it exists to prevent:

1. **Value shape** — a bound token must parse as an allele value.
2. **Prefix consistency** — a value carrying its own locus name must agree with
   the anchor, or nobody knows which gene it belongs to.
3. **Nearest-anchor ownership** — a value closer to a different locus's label
   belongs to that label, not to this one.
4. **Cardinality** — a locus has at most two alleles.
"""

from __future__ import annotations

import pytest

from kidneymatch.ocr.anchors import (
    Box,
    ResolutionStatus,
    ValueRule,
    resolve_locus,
)

ROW = ValueRule(direction="right", align_overlap=0.2, max_gap=20.0, max_values=2)


def row_box(x0: float, text: str, y: float = 0.50, width: float = 0.06) -> Box:
    return Box(x0=x0, y0=y, x1=x0 + width, y1=y + 0.03, text=text)


DRB1_LABEL = row_box(0.10, "DRB1")


def resolve(boxes: list[Box], locus: str = "DRB1", rule: ValueRule = ROW):
    return resolve_locus(boxes, locus=locus, rule=rule)


# --- gate 1: value shape -------------------------------------------------


def test_a_locus_label_is_never_bound_as_a_value() -> None:
    """The measured failure: 988 of 2,977 DRB1 bindings were the next row's label.

    A form is a stack of rows. A rule aimed the wrong way walks straight into
    the following label and reports it as this patient's allele.
    """
    next_row_label = row_box(0.22, "DQB1")
    result = resolve([DRB1_LABEL, next_row_label])
    assert result.status is ResolutionStatus.REVIEW_REQUIRED
    assert result.values == []
    assert "label" in result.reason.lower()


def test_a_damaged_label_is_also_refused_as_a_value() -> None:
    """`DRRI` is too damaged to anchor DRB1, and must not become an allele either.

    Rejection is permissive where acceptance is strict: the resolver must
    recognise more label spellings than it would ever trust to name a locus.
    """
    result = resolve([DRB1_LABEL, row_box(0.22, "DRRI")])
    assert result.status is ResolutionStatus.REVIEW_REQUIRED


def test_free_text_in_the_value_position_requires_review() -> None:
    result = resolve([DRB1_LABEL, row_box(0.22, "YEKTA")])
    assert result.status is ResolutionStatus.REVIEW_REQUIRED


def test_a_repaired_value_is_bound_and_flagged() -> None:
    """`II` is `11`. Repair is safe here because geometry established the cell."""
    result = resolve([DRB1_LABEL, row_box(0.22, "II")])
    assert result.status is ResolutionStatus.RESOLVED
    assert result.values == ["11"]
    assert result.repaired is True


def test_an_undamaged_value_is_not_flagged_as_repaired() -> None:
    result = resolve([DRB1_LABEL, row_box(0.22, "11")])
    assert result.status is ResolutionStatus.RESOLVED
    assert result.repaired is False


def test_the_raw_token_survives_repair() -> None:
    """Provenance: a reviewer must see what was on the page, not only our reading."""
    result = resolve([DRB1_LABEL, row_box(0.22, "II")])
    assert [v.raw for v in result.parsed_values] == ["II"]


# --- gate 2: prefix consistency ------------------------------------------


def test_a_value_naming_another_locus_requires_review() -> None:
    """`OCR_SPEC` section 2: geometry decides the locus, not the token's text.

    So a `DQB1*03` sitting in the DRB1 row cannot simply be relabelled DRB1 —
    but nor can it be trusted. The two sources of truth disagree, and a human
    must look.
    """
    result = resolve([DRB1_LABEL, row_box(0.22, "DQB1*03")])
    assert result.status is ResolutionStatus.REVIEW_REQUIRED
    assert result.locus == "DRB1"


def test_a_value_naming_its_own_anchor_is_accepted() -> None:
    result = resolve([DRB1_LABEL, row_box(0.22, "DRB1*11")])
    assert result.status is ResolutionStatus.RESOLVED
    assert result.values == ["DRB1*11"]


def test_a_bare_value_is_accepted_without_a_prefix() -> None:
    result = resolve([DRB1_LABEL, row_box(0.22, "11")])
    assert result.status is ResolutionStatus.RESOLVED


# --- gate 3: nearest-anchor ownership ------------------------------------


def test_a_label_reached_by_the_chain_stops_the_binding() -> None:
    """Reading rightwards with a generous gap walks into the next cell.

    `DRB1 ... DQB1 03`: the chain from `DRB1` reaches `DQB1`'s own label before
    its value. Gate 1 stops it — the label is not an allele.
    """
    result = resolve([DRB1_LABEL, row_box(0.40, "DQB1"), row_box(0.50, "03")])
    assert result.status is ResolutionStatus.REVIEW_REQUIRED
    assert "label" in result.reason.lower()


def test_a_value_closer_to_another_locus_label_is_not_taken() -> None:
    """The wrong-locus failure mode in pure geometry, with no label in the chain.

    A value that straddles two printed rows falls inside this anchor's row band
    while the label that actually owns it sits just outside the band. Nothing
    about the token's own text reveals the problem: only the distance does.
    """
    # A tall value box straddling two printed lines. It overlaps DRB1's line
    # (top half) and DQB1's line (bottom half), so both labels could claim it;
    # only the distance says which one does. DQB1's label ends at x=0.46, ours
    # at x=0.16, so DQB1 is nearer.
    dqb1_label = Box(x0=0.40, y0=0.540, x1=0.46, y1=0.570, text="DQB1")
    value = Box(x0=0.50, y0=0.515, x1=0.56, y1=0.565, text="03")
    result = resolve([DRB1_LABEL, dqb1_label, value])
    assert result.status is ResolutionStatus.REVIEW_REQUIRED
    assert "closer" in result.reason.lower()
    assert "DQB1" in result.reason


def test_the_nearer_anchor_does_take_the_value() -> None:
    dqb1_label = Box(x0=0.40, y0=0.540, x1=0.46, y1=0.570, text="DQB1")
    value = Box(x0=0.50, y0=0.515, x1=0.56, y1=0.565, text="03")
    result = resolve([DRB1_LABEL, dqb1_label, value], locus="DQB1")
    assert result.status is ResolutionStatus.RESOLVED
    assert result.values == ["03"]


def test_a_value_between_two_labels_of_the_same_locus_is_ambiguous() -> None:
    result = resolve([DRB1_LABEL, row_box(0.40, "DRB1"), row_box(0.50, "03")])
    assert result.status is ResolutionStatus.REVIEW_REQUIRED


# --- gate 4: cardinality and abstention ----------------------------------


def test_three_candidate_values_require_review() -> None:
    """A locus has two alleles. Three readings mean the row was misread."""
    result = resolve([DRB1_LABEL, row_box(0.22, "11"), row_box(0.30, "15"), row_box(0.38, "04")])
    assert result.status is ResolutionStatus.REVIEW_REQUIRED


def test_both_alleles_of_a_heterozygous_locus_are_still_captured() -> None:
    result = resolve([DRB1_LABEL, row_box(0.22, "11"), row_box(0.30, "15")])
    assert result.status is ResolutionStatus.RESOLVED
    assert result.values == ["11", "15"]


def test_a_missing_label_is_unknown_not_review() -> None:
    """UNKNOWN and REVIEW_REQUIRED are different states.

    UNKNOWN means the form does not report this locus; REVIEW_REQUIRED means it
    does and we could not read it. Merging them would either bury real gaps in
    a review queue or silently drop unreadable fields.
    """
    result = resolve([row_box(0.22, "11")])
    assert result.status is ResolutionStatus.UNKNOWN


def test_a_label_with_nothing_readable_beside_it_requires_review() -> None:
    result = resolve([DRB1_LABEL])
    assert result.status is ResolutionStatus.REVIEW_REQUIRED


def test_the_anchor_is_found_through_glyph_damage() -> None:
    """`DRBI` outnumbers `DRB1` 3.5:1 on this corpus."""
    result = resolve([row_box(0.10, "HLA-DRBI"), row_box(0.22, "11")])
    assert result.status is ResolutionStatus.RESOLVED
    assert result.locus == "DRB1"


def test_provenance_boxes_are_recorded_for_every_outcome() -> None:
    result = resolve([DRB1_LABEL, row_box(0.22, "11")])
    assert result.anchor_box == DRB1_LABEL
    assert [b.text for b in result.value_boxes] == ["11"]


@pytest.mark.parametrize(
    ("locus", "family"),
    # A family that really exists for that gene. `01` is not a DQB1 family, and
    # the vocabulary gate now says so — the earlier fixture only passed because
    # nothing checked.
    [("DRB1", "01"), ("DQB1", "03"), ("DPA1", "01"), ("DPB1", "04"), ("DQA1", "05")],
)
def test_every_supported_locus_resolves_the_same_way(locus: str, family: str) -> None:
    result = resolve([row_box(0.10, locus), row_box(0.22, family)], locus=locus)
    assert result.status is ResolutionStatus.RESOLVED
    assert result.locus == locus
