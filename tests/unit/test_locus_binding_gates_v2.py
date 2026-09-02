"""The gates added after the skeptical review of ADR 0008.

Written before the code. Each test encodes a finding that survived three
independent refuters, with the corpus count that justifies it.

The review's headline: **a single resolved allele is not homozygosity.** In
two-allele cells the gap to the second allele is median 15.3 label heights, p90
18.4 and max *exactly* 20.0 — the configured cap. On 6,597 single-allele cells
the heterozygous second allele sits just beyond the chain, self-prefixed with
the same locus in 98-99% of cases. 29-36% of resolved A/B/DRB1 cells were
single-allele, far above any plausible homozygosity rate, and nothing in the
result said whether one allele was printed or one was read (KI-015).
"""

from __future__ import annotations

import pytest

from kidneymatch.ocr.anchors import (
    Box,
    LocusResolution,
    ResolutionStatus,
    SecondAllele,
    ValueRule,
    resolve_document,
    resolve_locus,
)

ROW = ValueRule(direction="right", align_overlap=0.2, max_gap=20.0, max_values=2)


def at(x0: float, text: str, y0: float = 0.50, w: float = 0.06, h: float = 0.03) -> Box:
    return Box(x0=x0, y0=y0, x1=x0 + w, y1=y0 + h, text=text)


DRB1 = at(0.10, "DRB1")


def resolve(boxes: list[Box], locus: str = "DRB1", rule: ValueRule = ROW) -> LocusResolution:
    return resolve_locus(boxes, locus=locus, rule=rule)


# --- W1: a single allele never implies homozygosity ----------------------


def test_two_alleles_read_is_a_complete_cell() -> None:
    result = resolve([DRB1, at(0.22, "11"), at(0.34, "15")])
    assert result.status is ResolutionStatus.RESOLVED
    assert result.second_allele is SecondAllele.READ


def test_one_allele_read_leaves_the_second_unread_not_absent() -> None:
    """We cannot tell from one box whether the form printed one allele or two.

    A consumer that read a one-element list as a homozygous genotype would
    miscount every mismatch for that locus.
    """
    result = resolve([DRB1, at(0.22, "11")])
    assert result.status is ResolutionStatus.RESOLVED
    assert result.second_allele is SecondAllele.UNREAD


def test_a_value_just_beyond_the_gap_forces_review() -> None:
    """The measured failure: the cap cut the second-allele column in half.

    A further allele-shaped box on the same row, past the chain, is the
    heterozygous partner. Resolving without it would publish half a genotype.
    """
    beyond = at(0.28 + 20.0 * 0.03 + 0.02, "15")
    result = resolve([DRB1, at(0.22, "11"), beyond])
    assert result.status is ResolutionStatus.REVIEW_REQUIRED
    assert "beyond" in result.reason.lower()


def test_a_label_beyond_the_gap_does_not_force_review() -> None:
    """The next row's label is not a missing allele."""
    beyond = at(0.28 + 20.0 * 0.03 + 0.02, "DQB1")
    result = resolve([DRB1, at(0.22, "11"), beyond])
    assert result.status is ResolutionStatus.RESOLVED


def test_a_value_beyond_the_gap_owned_by_another_locus_does_not_force_review() -> None:
    """A neighbouring locus's column is not this locus's missing allele."""
    far = 0.28 + 20.0 * 0.03 + 0.10
    result = resolve([DRB1, at(0.22, "11"), at(far - 0.08, "DQB1"), at(far, "03")])
    assert result.status is ResolutionStatus.RESOLVED


# --- W2: the first-field vocabulary gate ---------------------------------


@pytest.mark.parametrize("first_field", ["83", "93", "97", "81"])
def test_a_family_that_does_not_exist_for_this_locus_requires_review(first_field: str) -> None:
    """A leading `0` read as `8` or `9`. Both readings are clean digits, so no
    glyph repair and no geometric gate can see it: 480 values corpus-wide."""
    result = resolve([DRB1, at(0.22, first_field)])
    assert result.status is ResolutionStatus.REVIEW_REQUIRED
    assert "family" in result.reason.lower() or "vocabulary" in result.reason.lower()


def test_the_valid_partner_of_the_confusion_still_resolves() -> None:
    assert resolve([DRB1, at(0.22, "03")]).status is ResolutionStatus.RESOLVED


def test_a_family_belonging_to_a_different_locus_requires_review() -> None:
    """`DQB1*13` does not exist; `DRB1*13` does. Geometry says DQB1 here."""
    result = resolve([at(0.10, "DQB1"), at(0.22, "13")], locus="DQB1")
    assert result.status is ResolutionStatus.REVIEW_REQUIRED


def test_a_three_digit_number_on_a_two_digit_locus_requires_review() -> None:
    result = resolve([at(0.10, "HLA-B"), at(0.22, "308")], locus="B")
    assert result.status is ResolutionStatus.REVIEW_REQUIRED


def test_an_all_letter_token_is_not_a_value() -> None:
    """A token with no digit evidence is free text in the cell, not a damaged
    digit string. Measured: impossible 20x more often than clean digits."""
    result = resolve([DRB1, at(0.22, "SS")])
    assert result.status is ResolutionStatus.REVIEW_REQUIRED


# --- W3/W4: ownership ----------------------------------------------------


def test_a_tie_between_two_labels_never_resolves() -> None:
    """Stacked labels share an x1, so horizontal distance cannot separate them.

    A tall value box overlapping both rows was RESOLVED under both loci.
    """
    drb1 = Box(x0=0.10, y0=0.500, x1=0.16, y1=0.530, text="DRB1")
    dqb1 = Box(x0=0.10, y0=0.540, x1=0.16, y1=0.570, text="DQB1")
    tall = Box(x0=0.22, y0=0.505, x1=0.28, y1=0.565, text="03")
    assert resolve([drb1, dqb1, tall]).status is ResolutionStatus.REVIEW_REQUIRED
    assert resolve([drb1, dqb1, tall], locus="DQB1").status is ResolutionStatus.REVIEW_REQUIRED


def test_a_value_box_far_taller_than_its_label_is_not_a_line_of_text() -> None:
    """99.7% of legitimate values are 0.5-1.6 label heights tall."""
    blob = Box(x0=0.22, y0=0.40, x1=0.28, y1=0.70, text="11")
    assert resolve([DRB1, blob]).status is ResolutionStatus.REVIEW_REQUIRED


def test_a_normally_sized_value_still_resolves() -> None:
    taller = Box(x0=0.22, y0=0.495, x1=0.28, y1=0.540, text="11")
    assert resolve([DRB1, taller]).status is ResolutionStatus.RESOLVED


def test_the_vertically_nearer_label_owns_a_straddling_value() -> None:
    """When horizontal distance ties, vertical proximity decides.

    Values are boxed 0.5-0.75 label heights above their own label, so on tight
    forms a value overlaps the row above more than its own row.
    """
    drb1 = Box(x0=0.10, y0=0.500, x1=0.16, y1=0.530, text="DRB1")
    dqb1 = Box(x0=0.10, y0=0.540, x1=0.16, y1=0.570, text="DQB1")
    near_dqb1 = Box(x0=0.22, y0=0.541, x1=0.28, y1=0.569, text="03")
    assert resolve([drb1, dqb1, near_dqb1], locus="DQB1").status is ResolutionStatus.RESOLVED
    assert resolve([drb1, dqb1, near_dqb1]).status is ResolutionStatus.REVIEW_REQUIRED


# --- W10: the generic rule must not read the presence row ----------------


@pytest.mark.parametrize("locus", ["DRB3", "DRB4", "DRB5"])
def test_the_generic_resolver_refuses_the_drbx_genes(locus: str) -> None:
    """They are presence typing, read by `drbx.py` from the grouped header.

    Asking this resolver for them bound neighbouring numbers as alleles on four
    documents, all five values impossible. A caller that asks is wrong, so this
    raises rather than returning a quiet UNKNOWN that hides the bug.
    """
    with pytest.raises(ValueError, match="grouped"):
        resolve_locus([at(0.10, locus), at(0.22, "01")], locus=locus, rule=ROW)


# --- document-level exclusivity ------------------------------------------


def test_no_box_may_be_bound_by_two_loci_in_one_document() -> None:
    """The last line of defence: even if every per-locus gate passed, one box
    cannot be two patients' values for two genes."""
    dqa1 = Box(x0=0.10, y0=0.700, x1=0.18, y1=0.720, text="DQA1")
    dpa1 = Box(x0=0.10, y0=0.640, x1=0.18, y1=0.660, text="DPA1")
    shared = Box(x0=0.30, y0=0.630, x1=0.36, y1=0.730, text="01")
    results = resolve_document([dqa1, dpa1, shared], rule=ROW, loci=("DQA1", "DPA1"))
    assert all(r.status is not ResolutionStatus.RESOLVED for r in results.values())


def test_a_clean_document_resolves_every_locus() -> None:
    boxes = [
        at(0.10, "DRB1", y0=0.50),
        at(0.22, "11", y0=0.50),
        at(0.34, "15", y0=0.50),
        at(0.10, "DQB1", y0=0.60),
        at(0.22, "03", y0=0.60),
        at(0.34, "05", y0=0.60),
    ]
    results = resolve_document(boxes, rule=ROW, loci=("DRB1", "DQB1"))
    assert results["DRB1"].values == ["11", "15"]
    assert results["DQB1"].values == ["03", "05"]
    assert all(r.second_allele is SecondAllele.READ for r in results.values())


def test_resolve_document_never_asks_for_the_drbx_genes() -> None:
    """Its default locus set must be the ones this rule can legitimately read."""
    results = resolve_document([DRB1, at(0.22, "11")], rule=ROW)
    assert "DRB3" not in results and "DRB4" not in results and "DRB5" not in results
    assert "DRB1" in results


# --- P1: a per-family rule (ADR 0007 registry) ---------------------------

FAMILY_RULE = ValueRule(
    direction="right",
    align_overlap=0.2,
    max_gap=None,
    max_values=2,
    centre_band=1.9,
    require_prefix=True,
)


def test_a_family_rule_reaches_the_second_column_with_no_distance_cap() -> None:
    """On the dominant form the second allele column sits 8-25 label heights
    away, so a distance cap cuts it off for about a quarter of rows.

    What makes removing the cap safe is the prefix requirement below, not the
    distance: 99.9% of this form's values print their own locus.
    """
    far = at(0.80, "DRB1*15")
    result = resolve([DRB1, at(0.22, "DRB1*11"), far], rule=FAMILY_RULE)
    assert result.status is ResolutionStatus.RESOLVED
    assert result.values == ["DRB1*11", "DRB1*15"]
    assert result.second_allele is SecondAllele.READ


def test_a_family_rule_refuses_a_value_that_does_not_name_its_locus() -> None:
    """Without a distance cap, a bare number anywhere on the row band could be
    anything. The form prints the locus on every value, so a bare one is not
    this form's value."""
    result = resolve([DRB1, at(0.80, "11")], rule=FAMILY_RULE)
    assert result.status is ResolutionStatus.REVIEW_REQUIRED
    assert "prefix" in result.reason.lower() or "name" in result.reason.lower()


def test_the_default_rule_still_accepts_a_bare_value() -> None:
    """Forms that do not print the locus on each value must keep working."""
    assert resolve([DRB1, at(0.22, "11")]).status is ResolutionStatus.RESOLVED


def test_a_centre_band_admits_a_value_the_overlap_test_alone_would_drop() -> None:
    """Values are boxed half a line above their label; on a form whose rows are
    3.8 label heights apart, half a row pitch is the natural band."""
    high = Box(x0=0.22, y0=0.4550, x1=0.28, y1=0.4850, text="DRB1*11")
    result = resolve([DRB1, high], rule=FAMILY_RULE)
    assert result.status is ResolutionStatus.RESOLVED


def test_the_centre_band_still_stops_at_the_next_row() -> None:
    next_row = Box(x0=0.22, y0=0.62, x1=0.28, y1=0.65, text="DRB1*11")
    result = resolve([DRB1, next_row], rule=FAMILY_RULE)
    assert result.status is not ResolutionStatus.RESOLVED
