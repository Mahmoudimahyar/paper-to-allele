"""The DRB1 -> DRB3/4/5 haplotype check: a cross-row consistency test.

Written before the implementation. Two rows of the same form are read by
different anchors, different relations and different parts of the page. Biology
links them, so they can check each other — the only external check on locus
binding available before the golden corpus is labelled.

Measured on 5,326 documents where both rows were read: **99.62% consistent**,
with 20 documents flagged.

**This is an assertion, never an inference.** py-ard's `dr_blender` is a
*blending* function: its return value imputes a merged DRBX genotype and even
collapses a homozygous pair. Calling it for that value would be exactly the
inference the project forbids. It is used here only for whether it raises, and
its return value is discarded.
"""

from __future__ import annotations

import pytest

from kidneymatch.hla.drbx_consistency import (
    ConsistencyOutcome,
    check_drb1_drbx,
    expected_drbx_genes,
)

# DRB1*03/11/12/13/14 haplotypes carry DRB3; *04/07/09 carry DRB4;
# *15/16 carry DRB5; *01/08/10 carry none.


@pytest.mark.parametrize(
    ("first_field", "expected"),
    [
        ("03", "DRB3"),
        ("11", "DRB3"),
        ("13", "DRB3"),
        ("04", "DRB4"),
        ("07", "DRB4"),
        ("09", "DRB4"),
        ("15", "DRB5"),
        ("16", "DRB5"),
    ],
)
def test_a_drb1_family_expects_its_haplotype_gene(first_field: str, expected: str) -> None:
    assert expected_drbx_genes([first_field]) == {expected}


@pytest.mark.parametrize("first_field", ["01", "08", "10"])
def test_some_drb1_families_expect_no_drbx_gene(first_field: str) -> None:
    assert expected_drbx_genes([first_field]) == set()


def test_a_heterozygous_pair_expects_both_genes() -> None:
    assert expected_drbx_genes(["11", "15"]) == {"DRB3", "DRB5"}


def test_an_unknown_first_field_expects_nothing_rather_than_guessing() -> None:
    assert expected_drbx_genes(["99"]) == set()


# --- the check itself ----------------------------------------------------


def test_a_consistent_pair_of_rows_passes() -> None:
    result = check_drb1_drbx(["11", "15"], present={"DRB3", "DRB5"}, absent={"DRB4"})
    assert result.outcome is ConsistencyOutcome.CONSISTENT


def test_a_gene_the_drb1_row_forbids_is_flagged() -> None:
    """DRB1*01/*08 carry no DRBX gene, so a DRB4 on the row contradicts them."""
    result = check_drb1_drbx(["01", "08"], present={"DRB4"}, absent=set())
    assert result.outcome is ConsistencyOutcome.FORBIDDEN_GENE_PRESENT
    assert "DRB4" in result.reason


def test_a_gene_the_drb1_row_expects_but_the_row_calls_absent_is_flagged() -> None:
    """py-ard raises only in one direction; this one is ours to detect.

    Verified: `dr_blender("DRB1*11+DRB1*13", "", "", "")` returns silently even
    though DRB3 was expected. Relying on the library alone would miss it —
    measured, py-ard raised on 30 documents where a set comparison found 156.
    """
    result = check_drb1_drbx(["11", "13"], present=set(), absent={"DRB3", "DRB4", "DRB5"})
    assert result.outcome is ConsistencyOutcome.EXPECTED_GENE_ABSENT


def test_an_unknown_gene_is_not_treated_as_absent() -> None:
    """Absence of a fact is not a fact of absence.

    The grouped row emits UNKNOWN when only one gene token was read. Checking
    that against the DRB1 row would manufacture a contradiction out of a gap.
    """
    result = check_drb1_drbx(["11", "13"], present=set(), absent=set())
    assert result.outcome is ConsistencyOutcome.NOT_CHECKABLE


def test_an_unreadable_drb1_row_makes_the_check_impossible() -> None:
    result = check_drb1_drbx([], present={"DRB3"}, absent=set())
    assert result.outcome is ConsistencyOutcome.NOT_CHECKABLE


def test_the_check_never_fills_a_missing_gene() -> None:
    """DRB1*11/*15 with an empty DRBX row does NOT yield DRB3 and DRB5 present.

    It yields a flag. Filling would convert a read failure into a confident
    clinical claim with a plausible audit trail — the worst available outcome.
    """
    result = check_drb1_drbx(["11", "15"], present=set(), absent={"DRB3", "DRB4", "DRB5"})
    assert result.outcome is ConsistencyOutcome.EXPECTED_GENE_ABSENT
    assert result.implied_genes == set(), "the check must not propose values"


def test_a_flag_lands_on_both_rows_not_one() -> None:
    """The rows are read by different anchors and different relations.

    A disagreement localises to neither, so neither may be preferred — least of
    all by re-reading a DRB1 digit to make the contradiction go away.
    """
    # Both alleles read and both carry DRB4, so a DRB3 on the row contradicts
    # them. (With only ONE allele read this would be consistent: the unread
    # partner could carry DRB3 — see the single-allele tests below.)
    result = check_drb1_drbx(["04", "04"], present={"DRB3"}, absent=set())
    assert result.flags_drb1_row is True
    assert result.flags_drbx_row is True


def test_a_passing_check_does_not_upgrade_the_evidence_state() -> None:
    """Consistency removes a document from the queue. It does not verify it."""
    result = check_drb1_drbx(["11"], present={"DRB3"}, absent={"DRB4", "DRB5"})
    assert result.outcome is ConsistencyOutcome.CONSISTENT
    assert result.verifies is False


def test_a_known_biological_exception_does_not_become_a_hard_error() -> None:
    """DRB4*01:03N is a null allele: DR7 haplotypes can lack a functional DRB4.

    Exceptions to the haplotype rule exist, so the check produces a review flag
    and never a rejection.
    """
    result = check_drb1_drbx(["07", "07"], present=set(), absent={"DRB3", "DRB4", "DRB5"})
    assert result.outcome is ConsistencyOutcome.EXPECTED_GENE_ABSENT
    assert result.is_review_flag is True


# --- N1: one allele read is not a homozygous pair ------------------------


def test_one_read_allele_does_not_manufacture_a_forbidden_flag() -> None:
    """The check duplicated a single first field into a homozygous pair.

    A gene explained by the UNREAD second haplotype was then reported as
    forbidden: 1,315 of 1,332 flags were single-value reads (57% of them). The
    99.62% consistency figure in ADR 0008 was the two-value subset only.
    """
    # DRB1*01 carries no DRBX gene, but the unread partner may carry DRB3.
    result = check_drb1_drbx(["01"], present={"DRB3"}, absent=set())
    assert result.outcome is ConsistencyOutcome.CONSISTENT


def test_two_genes_with_one_allele_that_carries_none_is_a_contradiction() -> None:
    """Each haplotype contributes at most one DRBX gene.

    Two genes present means both haplotypes contributed, so an allele that
    carries none cannot be one of them however the other allele reads.
    """
    result = check_drb1_drbx(["01"], present={"DRB3", "DRB4"}, absent=set())
    assert result.outcome is ConsistencyOutcome.FORBIDDEN_GENE_PRESENT


def test_two_genes_must_include_the_read_alleles_own_gene() -> None:
    """DRB1*04 carries DRB4. If both haplotype slots are filled and DRB4 is not
    among them, the two rows disagree."""
    result = check_drb1_drbx(["04"], present={"DRB3", "DRB5"}, absent=set())
    assert result.outcome is ConsistencyOutcome.FORBIDDEN_GENE_PRESENT


def test_two_genes_including_the_read_alleles_gene_is_consistent() -> None:
    result = check_drb1_drbx(["04"], present={"DRB3", "DRB4"}, absent=set())
    assert result.outcome is ConsistencyOutcome.CONSISTENT


def test_a_gene_the_read_allele_expects_but_the_row_calls_absent_still_flags() -> None:
    """This direction survives with one allele: the read haplotype's own gene
    cannot be absent."""
    result = check_drb1_drbx(["11"], present=set(), absent={"DRB3", "DRB4", "DRB5"})
    assert result.outcome is ConsistencyOutcome.EXPECTED_GENE_ABSENT


def test_a_homozygous_pair_is_still_checked_as_a_pair() -> None:
    """Two values that happen to be equal are two reads, not one."""
    result = check_drb1_drbx(["01", "01"], present={"DRB3"}, absent=set())
    assert result.outcome is ConsistencyOutcome.FORBIDDEN_GENE_PRESENT
