"""The combined `DRB3/4/5` row: three genes, one printed row.

Written before the implementation, from a measured design (session artefact
`design_drbx.md`, all figures from the 23,485 analysable true originals).

The row is **presence typing**: it prints gene NAMES, not alleles. Measured, the
box at rank 0 to the right of the header is a gene name 95.7% of the time and an
allele 0.1% of the time (11 boxes corpus-wide). The old rule read DOWNWARD from
the header, where the box is the next row's locus label in 88.9% of cases
(`HLA-DPBI` alone 9,130 times) — so it resolved 3 documents in the entire
corpus.

Reading the gene from the token is licensed here, and only here, because the
header prints the admissible set `{DRB3, DRB4, DRB5}`. Geometry still fixes the
cell; the cell's grammar is a three-symbol alphabet rather than free text. That
is why every partial header is refused: the moment the enumeration is not
printed, the licence is gone.
"""

from __future__ import annotations

import pytest

from kidneymatch.ocr.anchors import Box, ResolutionStatus
from kidneymatch.ocr.drbx import GeneCall, resolve_grouped_drbx

HEADER = Box(x0=0.10, y0=0.50, x1=0.24, y1=0.53, text="HLA-DRB3/4/5")


def at(x0: float, text: str, y0: float = 0.505, height: float = 0.028) -> Box:
    return Box(x0=x0, y0=y0, x1=x0 + 0.06, y1=y0 + height, text=text)


def calls(boxes: list[Box]) -> dict[str, GeneCall]:
    return {gene: fact.call for gene, fact in resolve_grouped_drbx(boxes).items()}


# --- the header ----------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "HLA-DRB3/4/5",  # 9,532 documents
        "DRB3/4/5",  # 1,042
        "HLA-DRB3/45",  # 862
        "HLA-DRB3/4/S",  # 522 — the final 5 read as S
        "HLA-DRB345",  # 380
        "-DRB3/4/5",  # 274
        "HLA-DRB34/5",  # 172
        "DRB3,4,5",  # 159
        "HLA-DR83/4/5",  # 36 — B read as 8
    ],
)
def test_the_measured_header_spellings_are_recognised(text: str) -> None:
    header = Box(x0=0.10, y0=0.50, x1=0.24, y1=0.53, text=text)
    assert calls([header, at(0.40, "DRB3"), at(0.70, "DRB4")])["DRB3"] is GeneCall.PRESENT


@pytest.mark.parametrize("text", ["DRB3/4", "DRB4/5", "DRB3", "DRB1/3/4/5", "DRB3/4/5/6", "DR345"])
def test_a_partial_or_wrong_enumeration_is_not_a_header(text: str) -> None:
    """The licence to read a gene name comes from the printed admissible set.

    A header that does not enumerate exactly 3, 4 and 5 does not establish that
    set, so the cell has no closed grammar and nothing may be read from it.
    """
    header = Box(x0=0.10, y0=0.50, x1=0.24, y1=0.53, text=text)
    assert calls([header, at(0.40, "DRB3")])["DRB3"] is GeneCall.UNKNOWN


def test_no_header_means_unknown_not_absent() -> None:
    """A form may type the three genes as three standalone rows instead.

    Absence of the grouped header is absence of evidence about this document's
    layout, never evidence that the patient lacks the genes.
    """
    assert calls([at(0.40, "DRB3")]) == {
        "DRB3": GeneCall.UNKNOWN,
        "DRB4": GeneCall.UNKNOWN,
        "DRB5": GeneCall.UNKNOWN,
    }


def test_two_headers_require_review() -> None:
    """Measured on 404 documents. Which row owns the value is undecidable."""
    second = Box(x0=0.10, y0=0.70, x1=0.24, y1=0.73, text="HLA-DRB3/4/5")
    facts = resolve_grouped_drbx([HEADER, second, at(0.40, "DRB3")])
    assert all(f.status is ResolutionStatus.REVIEW_REQUIRED for f in facts.values())


# --- the count rule ------------------------------------------------------


def test_two_gene_tokens_make_the_third_gene_absent() -> None:
    """Both haplotype slots were read, so the unnamed gene is genuinely absent.

    Measured discordance against the independently-read DRB1 row: 0.09%.
    """
    assert calls([HEADER, at(0.40, "DRB3"), at(0.70, "DRB4")]) == {
        "DRB3": GeneCall.PRESENT,
        "DRB4": GeneCall.PRESENT,
        "DRB5": GeneCall.ABSENT,
    }


def test_one_gene_token_leaves_the_others_unknown_not_absent() -> None:
    """The second column is far more often UNREAD than empty.

    Measured: calling the others ABSENT here is contradicted by the DRB1 row
    5.90% of the time, against 0.09% when two tokens were read — 65x worse. One
    token is evidence about one gene and about nothing else.
    """
    assert calls([HEADER, at(0.40, "DRB3")]) == {
        "DRB3": GeneCall.PRESENT,
        "DRB4": GeneCall.UNKNOWN,
        "DRB5": GeneCall.UNKNOWN,
    }


def test_an_empty_row_is_unknown_never_absent() -> None:
    """675 documents print the header with nothing on the row.

    Of those where DRB1 was also read, 63.2% have a DRB1 genotype that expects
    at least one DRBX gene — so an empty row is a read failure far more often
    than a true triple negative.
    """
    assert calls([HEADER]) == {
        "DRB3": GeneCall.UNKNOWN,
        "DRB4": GeneCall.UNKNOWN,
        "DRB5": GeneCall.UNKNOWN,
    }


def test_three_gene_tokens_are_biologically_impossible_and_must_review() -> None:
    """A person carries at most one DRBX gene per haplotype, so at most two.

    Zero documents violate this at the measured row band. An unreachable state
    means a broken assumption, so it must scream rather than be truncated to
    the first two.
    """
    facts = resolve_grouped_drbx([HEADER, at(0.40, "DRB3"), at(0.60, "DRB4"), at(0.80, "DRB5")])
    assert all(f.status is ResolutionStatus.REVIEW_REQUIRED for f in facts.values())


def test_a_duplicated_gene_is_legitimate_not_an_error() -> None:
    """`DRB3 DRB3` means both haplotypes carry DRB3, on 2,861 documents.

    Where the DRB1 row expects two DRB3 copies, this row prints the pair in
    89.8% of cases; where it expects one, in 0.6%. The pair is real.
    """
    assert calls([HEADER, at(0.40, "DRB3"), at(0.70, "DRB3")]) == {
        "DRB3": GeneCall.PRESENT,
        "DRB4": GeneCall.ABSENT,
        "DRB5": GeneCall.ABSENT,
    }


def test_copy_number_is_not_emitted() -> None:
    """PRESENT twice is still PRESENT.

    The correlation with DRB1 zygosity is strong but a copy-number field must
    come from labelled ground truth, not from a correlation. The token count is
    kept in provenance so it can be derived later.
    """
    facts = resolve_grouped_drbx([HEADER, at(0.40, "DRB3"), at(0.70, "DRB3")])
    assert facts["DRB3"].call is GeneCall.PRESENT
    assert facts["DRB3"].tokens_on_row == 2


# --- the S -> 5 repair ---------------------------------------------------


def test_DRBS_is_read_as_DRB5_and_flagged() -> None:
    """Three independent measurements support this, none of them circular.

    In the header's own digits, `S` stands for `5` 21x more often than for `3`
    and never for `4`. Documents whose header misread its own final `5` show a
    halved `5` share and a doubled `S` share with the `3` and `4` shares
    unchanged. And `DRBS` rows match a DRB1 genotype expecting DRB5 in 99.5% of
    cases, against a 54.1% base rate for DRB3.
    """
    facts = resolve_grouped_drbx([HEADER, at(0.40, "DRBS")])
    assert facts["DRB5"].call is GeneCall.PRESENT
    assert facts["DRB5"].repaired is True


def test_an_unrepaired_gene_is_not_flagged() -> None:
    facts = resolve_grouped_drbx([HEADER, at(0.40, "DRB5")])
    assert facts["DRB5"].call is GeneCall.PRESENT
    assert facts["DRB5"].repaired is False


@pytest.mark.parametrize("text", ["DRRS", "DRIS", "DRES", "DRB", "RB3", "DR3"])
def test_interior_damage_in_a_gene_token_is_not_a_gene(text: str) -> None:
    """Only `B`->`8` and a final `5`->`S` are tolerated. Everything else is noise."""
    assert calls([HEADER, at(0.40, text)])["DRB3"] is GeneCall.UNKNOWN


@pytest.mark.parametrize("text", ["3", "4", "5", "45", "345"])
def test_a_bare_number_on_the_row_is_never_a_gene(text: str) -> None:
    """No geometry says a bare `5` in that cell means DRB5 rather than a fragment."""
    assert calls([HEADER, at(0.40, text)]) == {
        "DRB3": GeneCall.UNKNOWN,
        "DRB4": GeneCall.UNKNOWN,
        "DRB5": GeneCall.UNKNOWN,
    }


# --- geometry ------------------------------------------------------------


def test_the_box_below_the_header_is_never_read() -> None:
    """It is the next row's locus label in 88.9% of documents that have one."""
    below = Box(x0=0.10, y0=0.56, x1=0.24, y1=0.59, text="HLA-DPB1")
    assert calls([HEADER, below]) == {
        "DRB3": GeneCall.UNKNOWN,
        "DRB4": GeneCall.UNKNOWN,
        "DRB5": GeneCall.UNKNOWN,
    }


def test_a_gene_token_on_another_row_is_not_taken() -> None:
    other_row = at(0.40, "DRB3", y0=0.62)
    assert calls([HEADER, other_row])["DRB3"] is GeneCall.UNKNOWN


def test_tokens_to_the_left_of_the_header_are_not_read() -> None:
    """The header starts the row: measured empty to its left on 13,082 of 13,550."""
    left = at(0.02, "DRB3")
    assert calls([HEADER, left])["DRB3"] is GeneCall.UNKNOWN


def test_the_second_column_is_reached_without_a_gap_limit() -> None:
    """Gene slot 2 sits a median 33 header-heights away — far past any max_gap.

    The row band, not the gap, is what keeps this rule safe.
    """
    far = at(0.85, "DRB4")
    assert calls([HEADER, at(0.30, "DRB3"), far])["DRB4"] is GeneCall.PRESENT


# --- provenance ----------------------------------------------------------


def test_each_gene_fact_points_at_the_box_that_named_it() -> None:
    """The header alone is not provenance for a per-gene fact."""
    gene_box = at(0.40, "DRB3")
    facts = resolve_grouped_drbx([HEADER, gene_box, at(0.70, "DRB4")])
    assert facts["DRB3"].gene_box == gene_box
    assert facts["DRB3"].header_box == HEADER
    assert facts["DRB5"].gene_box is None  # ABSENT by row, not by a box
    assert facts["DRB5"].header_box == HEADER


# --- fixes from the skeptical review -------------------------------------


def test_a_gene_token_sharing_the_printed_line_is_counted() -> None:
    """The row band used centre distance where the resolver uses overlap.

    A third gene token on the same physical line fell just outside it, so the
    row emitted ABSENT where it must REVIEW (7 documents), and 1,036 documents
    lost a gene token that was on the line.
    """
    a = Box(x0=0.40, y0=0.513, x1=0.46, y1=0.541, text="DRB3")
    b = Box(x0=0.50, y0=0.474, x1=0.56, y1=0.502, text="DRB4")
    c = Box(x0=0.80, y0=0.466, x1=0.86, y1=0.494, text="DRB5")
    facts = resolve_grouped_drbx([HEADER, a, b, c])
    assert all(f.status is ResolutionStatus.REVIEW_REQUIRED for f in facts.values())


def test_a_token_on_the_next_printed_row_is_still_excluded() -> None:
    """Widening the band must not reach the row below."""
    below = Box(x0=0.40, y0=0.60, x1=0.46, y1=0.628, text="DRB4")
    assert calls([HEADER, at(0.40, "DRB3"), below])["DRB4"] is GeneCall.UNKNOWN


def test_an_undamaged_allele_on_the_row_names_its_gene() -> None:
    """`DRB5*01:01` matched neither the gene-token pattern nor the damage check,
    so it was invisible to the count and its gene was called ABSENT."""
    facts = resolve_grouped_drbx([HEADER, at(0.40, "DRB3"), at(0.60, "DRB5*01:01")])
    assert facts["DRB3"].call is GeneCall.PRESENT
    assert facts["DRB5"].call is GeneCall.PRESENT
    assert facts["DRB4"].call is GeneCall.ABSENT


def test_an_allele_only_row_is_not_reported_as_unread() -> None:
    """11 documents print an allele and no bare gene name; the row said 'no gene
    token was read', which is false — an allele naming the gene was read."""
    facts = resolve_grouped_drbx([HEADER, at(0.40, "DRB3*02:02")])
    assert facts["DRB3"].call is GeneCall.PRESENT


@pytest.mark.parametrize(
    ("text", "genes"),
    [("DRB3/4", ("DRB3", "DRB4")), ("DRB4/5", ("DRB4", "DRB5")), ("DRB3/5", ("DRB3", "DRB5"))],
)
def test_a_compact_two_gene_token_names_both_genes(text: str, genes: tuple[str, str]) -> None:
    """333 documents print the pair in one box instead of two."""
    facts = resolve_grouped_drbx([HEADER, at(0.40, text)])
    for gene in genes:
        assert facts[gene].call is GeneCall.PRESENT
    absent = ({"DRB3", "DRB4", "DRB5"} - set(genes)).pop()
    assert facts[absent].call is GeneCall.ABSENT


def test_a_compact_token_naming_all_three_genes_requires_review() -> None:
    """A person carries at most two. Three is the header spelled again."""
    facts = resolve_grouped_drbx([HEADER, at(0.40, "DRB3/4/5"), at(0.60, "DRB3")])
    assert all(f.status is ResolutionStatus.REVIEW_REQUIRED for f in facts.values())


def test_a_printed_header_whose_row_reads_nothing_needs_review() -> None:
    """One policy across the codebase: a printed label we could not read is a
    failure a human must see, not an UNKNOWN.

    `anchors.py` already said so. Measured, 63.2% of empty grouped rows have a
    DRB1 genotype that expects at least one gene, so it is a read failure far
    more often than a true triple negative. 1,305 documents.
    """
    facts = resolve_grouped_drbx([HEADER])
    assert all(f.status is ResolutionStatus.REVIEW_REQUIRED for f in facts.values())
    assert all(f.call is GeneCall.UNKNOWN for f in facts.values())


def test_no_header_at_all_is_still_unknown_not_review() -> None:
    """A form that types these genes as three standalone rows is not a failure."""
    facts = resolve_grouped_drbx([at(0.40, "DRB3")])
    assert all(f.status is ResolutionStatus.UNKNOWN for f in facts.values())


# --- header v2: the B slot's misreads and the slash read as 1 ----------------


@pytest.mark.parametrize(
    "text",
    [
        "HLA-DRR3/4/5",  # 88 documents without a v1 header
        "DR$3/4/5",  # 38
        "DRE3/4/5",  # 29
        "HLA-DRH3/4/5",  # 14
        "IILA-DRD3/4/S",  # 12
        "HLA-DRB3145",  # 46 — the slashes read as 1
        "HLA-DRB314/5",  # 26
        "HLA-DRB3/415",  # 26
        "HLA-DRB3AS",  # 60 — the 4 lost, a slash-misread letter in its place
        "HLA-DRB3A/S",  # 28
        "HLA-DRB3AUS",  # 11
    ],
)
def test_the_v2_header_spellings_are_recognised(text: str) -> None:
    """Measured on the 9,648 documents without a v1 header: 605 gain one."""
    header = Box(x0=0.10, y0=0.50, x1=0.24, y1=0.53, text=text)
    assert calls([header, at(0.40, "DRB3"), at(0.70, "DRB4")])["DRB3"] is GeneCall.PRESENT


@pytest.mark.parametrize("text", ["DRB3/5", "HLA-DRB3/5", "DRB3AS", "DRB35", "DR3/4/5", "DRB3/4"])
def test_a_four_less_token_is_a_pair_or_nothing_never_a_header(text: str) -> None:
    """`DRB3/5` names two genes on the row. Reading it as a header would make
    a second header of it and refuse the whole row; without the HLA prefix
    and a slash-misread letter standing in for the 4, no 4-less token is one."""
    from kidneymatch.ocr.drbx import GROUPED_DRBX_HEADER

    assert GROUPED_DRBX_HEADER.match(text) is None


def test_the_pair_token_on_a_v2_header_row_still_names_both_genes() -> None:
    header = Box(x0=0.10, y0=0.50, x1=0.24, y1=0.53, text="HLA-DRR3/4/5")
    assert calls([header, at(0.40, "DRB3/5")]) == {
        "DRB3": GeneCall.PRESENT,
        "DRB4": GeneCall.ABSENT,
        "DRB5": GeneCall.PRESENT,
    }


def test_glyphs_and_drbx_agree_on_what_a_grouped_header_is() -> None:
    """Two copies of one pattern: `glyphs` refuses the header as a locus label
    and recognises it as label-shaped; `drbx` reads the row. They must agree
    on every measured spelling, or a header could anchor a locus."""
    from kidneymatch.ocr.drbx import GROUPED_DRBX_HEADER
    from kidneymatch.ocr.glyphs import _GROUPED_DRBX, canonical_locus_label

    spellings = [
        "HLA-DRB3/4/5",
        "DRB3/4/5",
        "HLA-DRB3/45",
        "HLA-DRB3/4/S",
        "HLA-DRB345",
        "-DRB3/4/5",
        "HLA-DRB34/5",
        "DRB3,4,5",
        "HLA-DR83/4/5",
        "HLA-DRR3/4/5",
        "DR$3/4/5",
        "DRE3/4/5",
        "HLA-DRB3145",
        "HLA-DRB3AS",
        "HLA-DRB3A/S",
        "DRB3/5",
        "HLA-DRB3/5",
        "DRB3/4",
        "DR345",
        "DRB3",
        "DRBS",
        "DRB1",
        "HLA-DRB1",
    ]
    assert GROUPED_DRBX_HEADER.pattern == _GROUPED_DRBX.pattern, (
        "the two copies of the grouped-header pattern have diverged"
    )
    for text in spellings:
        assert bool(GROUPED_DRBX_HEADER.match(text)) == bool(_GROUPED_DRBX.match(text)), text
        if GROUPED_DRBX_HEADER.match(text):
            assert canonical_locus_label(text) is None, text


# --- a slot that rests on the S-for-5 repair certifies no absence ------------


def test_two_tokens_both_read_DRBS_leave_the_other_genes_a_question() -> None:
    """Labelled: `DRBS DRBS` was the printed `DRB3 DRB5`. DRB5 stands, repaired;
    DRB3 and DRB4 are neither PRESENT nor ABSENT, and a human looks."""
    facts = resolve_grouped_drbx([HEADER, at(0.40, "DRBS"), at(0.70, "DRBS")])
    assert facts["DRB5"].call is GeneCall.PRESENT
    assert facts["DRB5"].status is ResolutionStatus.RESOLVED
    assert facts["DRB5"].repaired is True
    for gene in ("DRB3", "DRB4"):
        assert facts[gene].call is GeneCall.UNKNOWN
        assert facts[gene].status is ResolutionStatus.REVIEW_REQUIRED
        assert "S read as 5" in facts[gene].reason


def test_one_repaired_token_beside_a_clean_one_certifies_no_absence_either() -> None:
    facts = resolve_grouped_drbx([HEADER, at(0.40, "DRB3"), at(0.70, "DRBS")])
    assert facts["DRB3"].call is GeneCall.PRESENT
    assert facts["DRB5"].call is GeneCall.PRESENT and facts["DRB5"].repaired
    assert facts["DRB4"].call is GeneCall.UNKNOWN
    assert facts["DRB4"].status is ResolutionStatus.REVIEW_REQUIRED


def test_a_pair_token_read_DRBS_S_is_the_same_question() -> None:
    """Labelled: `DRBS/S` was the printed `DRB3/5`."""
    facts = resolve_grouped_drbx([HEADER, at(0.40, "DRBS/S")])
    assert facts["DRB5"].call is GeneCall.PRESENT
    assert facts["DRB3"].status is ResolutionStatus.REVIEW_REQUIRED
    assert facts["DRB4"].status is ResolutionStatus.REVIEW_REQUIRED


def test_two_clean_tokens_still_certify_the_third_gene_absent() -> None:
    """3,761 rows print the same clean gene twice and 4,073 two different ones;
    no labelled evidence contradicts their ABSENT calls, and they stand."""
    facts = resolve_grouped_drbx([HEADER, at(0.40, "DRB3"), at(0.70, "DRB3")])
    assert facts["DRB3"].call is GeneCall.PRESENT
    assert (
        facts["DRB4"].call is GeneCall.ABSENT and facts["DRB4"].status is ResolutionStatus.RESOLVED
    )
    assert facts["DRB5"].call is GeneCall.ABSENT
    facts = resolve_grouped_drbx([HEADER, at(0.40, "DRB3"), at(0.70, "DRB4")])
    assert (
        facts["DRB5"].call is GeneCall.ABSENT and facts["DRB5"].status is ResolutionStatus.RESOLVED
    )
