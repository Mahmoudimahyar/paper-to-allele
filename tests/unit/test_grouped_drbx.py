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


@pytest.mark.parametrize("text", ["DRB3/5", "HLA-DRB3/5", "DRB3AS", "DRB35", "DRB3/4"])
def test_a_four_less_token_is_a_pair_or_nothing_never_a_header(text: str) -> None:
    """`DRB3/5` names two genes on the row. Reading it as a header would make
    a second header of it and refuse the whole row; without the HLA prefix
    and a slash-misread letter standing in for the 4, no 4-less token is one.

    `DR3/4/5` left this list when the B slot was widened (route (c)): it prints
    all three digits and has lost only its `B`, which is a stem misread and not
    a partial enumeration. It is a header where the geometry corroborates one.
    """
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


# --- header W5: damage the strict pattern does not reach, and its gate -------
#
# Route (c), 2026-09-06. 213 boxes corpus-wide match the widening and not the
# strict pattern, and a box the widening alone reads is a header only where the
# page's geometry corroborates one. The measured placebos are what make that
# gate necessary: any box in the label column at 0.6-1.3 pitches below DRB1,
# read as a header regardless of its text, emits 1,613 PRESENT with 1.21%
# forbidden by the page's own DRB1 — so on most no-header pages row+1 is NOT a
# DRB3/4/5 row, and the TEXT is load-bearing. In the other direction, the same
# looseness with the wrong digits or the wrong locus (`DR?1/2/3`, `DQ?3/4/5`)
# matches zero boxes corpus-wide: the W5 shape is specific to this header.

W5_H = 0.012
W5_PITCH = 0.040


def w5_label(text: str, centre_y: float, x0: float = 0.10, x1: float = 0.19) -> Box:
    return Box(x0=x0, y0=centre_y - W5_H / 2, x1=x1, y1=centre_y + W5_H / 2, text=text)


def w5_page(
    header_text: str, *, header_y: float = 0.480, x0: float = 0.10, header_h: float = W5_H
) -> list[Box]:
    """A page whose grouped header only the widening reads, with the label
    column that corroborates it and a gene token on its row."""
    return [
        w5_label("DQB1", 0.400),
        w5_label("DRB1", 0.440),
        Box(
            x0=x0,
            y0=header_y - header_h / 2,
            x1=x0 + 0.09,
            y1=header_y + header_h / 2,
            text=header_text,
        ),
        Box(x0=0.40, y0=header_y - W5_H / 2, x1=0.46, y1=header_y + W5_H / 2, text="DRB3"),
        w5_label("DPB1", 0.520),
    ]


@pytest.mark.parametrize(
    "text",
    [
        "DRd3/4/5",  # the B slot read as another letter
        "DR3/4/5",  # the B slot lost
        "DR?3/4/5",
        "DRI3/4/5",
        "HLA-DRA345",
        "HLA-DRB3445",  # a separator read as 4
        "HLA-DRB344/5",
        "HLA-DRB3/4/3",  # the final 5 read as 3
        "BLA-DRB3/4/5",  # the HLA prefix read as BLA
    ],
)
def test_the_widened_header_spellings_are_read_where_geometry_agrees(text: str) -> None:
    facts = resolve_grouped_drbx(w5_page(text))
    assert facts["DRB3"].call is GeneCall.PRESENT, text


@pytest.mark.parametrize(
    "text",
    [
        "DRB3/B4/B5",  # 21 boxes, and every one of them on a DRB1 line
        "HLA-DRB3/5",  # a printed PAIR of gene names, not a header
        "DRB34",  # truncations: ADR 0008 Decision 4 refuses partial enumerations
        "HLA-DRB35",
        "HLA-DRB3/4/",
        "DRB3/4",
        "HLA-DRB3//5",  # the double separator: nothing at all in the 4 slot
        "DRBS3/4/5",  # the stem's own digit misread, not a B-slot substitution
        "DRB1*03",  # a DRB1 value
        "DRB3*01:01",
        "DR?1/2/3",  # the same looseness, the wrong digits: 0 boxes corpus-wide
        "DQ?3/4/5",  # the same looseness, the wrong locus
    ],
)
def test_the_widening_does_not_reach_these(text: str) -> None:
    from kidneymatch.ocr.drbx import GROUPED_DRBX_HEADER

    assert GROUPED_DRBX_HEADER.match(text) is None, text


def test_the_widening_reaches_everything_the_strict_pattern_reads() -> None:
    """The widened pattern must be a SUPERSET of the strict one.

    `glyphs._GROUPED_DRBX` mirrors the widened pattern, and both of its uses are
    refusals: a header-shaped box may not anchor a locus and may not be read as
    a value. A box that is a header to `drbx.py` and a locus label to
    `glyphs.py` is how one allele reaches three genes.

    Caught by a corpus measurement, not by reading: the letter class the
    verifier specified (`[A-RT-Za-z?]`) drops the `8` and `$` the shipped
    pattern accepts in the B slot, and `HLA-DR83/4/5` is one of the spellings
    that pattern was widened for in the first place.
    """
    from kidneymatch.ocr.drbx import GROUPED_DRBX_HEADER, STRICT_GROUPED_DRBX_HEADER

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
        "HLA-DRH3/4/5",
        "IILA-DRD3/4/S",
        "HLA-DRB3145",
        "HLA-DRB314/5",
        "HLA-DRB3/415",
        "HLA-DRB3AS",
        "HLA-DRB3A/S",
        "HLA-DRB3AUS",
    ]
    for text in spellings:
        if STRICT_GROUPED_DRBX_HEADER.match(text):
            assert GROUPED_DRBX_HEADER.match(text), text


def test_a_widened_header_out_of_the_label_column_is_not_a_header() -> None:
    """The column test is relative to the DRB1 LABEL, not to the page's median
    label x0: 12,363 of 14,359 current headers pass the first, and a median-x0
    test rejects 12,120 of them because the dominant form centres its labels.
    (`tests/fixtures/drbx_header_gate.json` is the shipped gate's own
    re-measurement of the same thing: 12,245 of 14,315.)"""
    facts = resolve_grouped_drbx(w5_page("DR3/4/5", x0=0.40))
    assert all(f.status is ResolutionStatus.UNKNOWN for f in facts.values())


@pytest.mark.parametrize("ratio", [0.25, 0.5, 1.5, 2.0])
def test_a_widened_header_on_the_wrong_row_is_not_a_header(ratio: float) -> None:
    facts = resolve_grouped_drbx(w5_page("DR3/4/5", header_y=0.440 + ratio * W5_PITCH))
    assert all(f.call is GeneCall.UNKNOWN for f in facts.values())


def test_a_widened_header_with_no_single_DRB1_label_is_not_a_header() -> None:
    """Of the 151 widened-only boxes on no-strict-header pages, 32 are not
    measurable at all — no single DRB1 label, or no label-column pitch — and
    every one of those is refused. The one DRB1-forbidden gene among the
    widened calls was on such a page."""
    boxes = [b for b in w5_page("DR3/4/5") if (b.text or "") != "DRB1"]
    assert all(f.call is GeneCall.UNKNOWN for f in resolve_grouped_drbx(boxes).values())
    doubled = [*w5_page("DR3/4/5"), w5_label("DRB1", 0.700)]
    assert all(f.call is GeneCall.UNKNOWN for f in resolve_grouped_drbx(doubled).values())


def test_a_strict_header_needs_no_corroboration() -> None:
    """The strict pattern reads the printed enumeration; the widening reads
    damage, and damage is where a box that is not a header gets in."""
    stray = [
        Box(x0=0.55, y0=0.20, x1=0.70, y1=0.23, text="HLA-DRB3/4/5"),
        at(0.75, "DRB4", y0=0.205),
    ]
    assert resolve_grouped_drbx(stray)["DRB4"].call is GeneCall.PRESENT


def test_a_counted_token_nearer_DRB1_than_a_widened_header_goes_to_review() -> None:
    """The leak guard. Re-measured 2026-09-07 against the live stores: on 6 of
    the 90 gated widened pages that count a token at all — 6.7%, against 88 of
    12,322 strict single-header pages, 0.71%, so 9.3x — a counted token sat
    nearer the DRB1 label's line than the header's. That is a DRB1 value read
    as a gene name, which
    the DRB1 concordance check cannot catch because a gene name derived from a
    DRB1 allele agrees with DRB1 by construction. All six were two-token rows
    writing ABSENT for the third gene."""
    # A damaged header is often boxed tall, and its row band then reaches back
    # over the DRB1 row: that is how the DRB1 value gets counted as a gene.
    boxes = w5_page("DR3/4/5", header_h=0.030)
    leaked = Box(x0=0.40, y0=0.4515, x1=0.46, y1=0.4635, text="DRB4")  # nearer DRB1's line
    facts = resolve_grouped_drbx([*boxes, leaked])
    assert all(f.status is ResolutionStatus.REVIEW_REQUIRED for f in facts.values())
    assert all(f.call is GeneCall.UNKNOWN for f in facts.values())


def test_the_leak_guard_does_not_fire_on_a_strict_header() -> None:
    """It is the widening that is untrusted, not the row band."""
    facts = resolve_grouped_drbx([HEADER, at(0.40, "DRB3"), at(0.70, "DRB4")])
    assert facts["DRB3"].call is GeneCall.PRESENT


# --- the widened header is MARKED, and its final-3 branch certifies no absence ---
#
# Route (c) required fixes 2 and 6. Two things had to be true before a widened
# header could keep writing ABSENT on 104 pages nobody has ever checked:
#
# 1. the group must be FINDABLE — a distinct `rule_id` and a `source` naming
#    which widening let the header in, so `review_pack.py` can cut a stratum and
#    one statement can withdraw all 312 cells if HA-011 (d2) says no;
# 2. the `final-3` branch may not certify an absence. Every other widening
#    damages a slot the enumeration does not depend on; that one substitutes a
#    `3` for the printed final `5`, and the ABSENT this row writes rests on the
#    enumeration having been read. Measured 2026-09-07, the header's final slot
#    reads `5` 13,555 times corpus-wide, `S` 975 and `3` 25 — nothing like the
#    three independent measurements that license S-for-5 inside a cell.


def w5_two_token_page(header_text: str) -> list[Box]:
    """A widened-header page whose row prints TWO gene tokens.

    Two tokens is the only shape that writes ABSENT, so it is the only shape in
    which the final-3 question has an answer to give.
    """
    boxes = w5_page(header_text)
    return [*boxes, Box(x0=0.70, y0=0.480 - W5_H / 2, x1=0.76, y1=0.480 + W5_H / 2, text="DRB4")]


@pytest.mark.parametrize(
    ("text", "branches"),
    [
        ("HLA-DRB3/4/5", ()),  # the strict pattern reads it; nothing was widened
        ("DRB3/4/5", ()),
        ("HLA-DRB3/4/S", ()),  # S-for-5 is the STRICT pattern's, not a widening
        ("DR3/4/5", ("b-slot-empty",)),
        ("DRI3/4/5", ("b-slot-glyph",)),
        ("HLA-DRA345", ("b-slot-glyph",)),
        ("HLA-DRB3445", ("slash-as-4",)),
        ("HLA-DRB344/5", ("slash-as-4",)),
        ("HLA-DRB3/4/3", ("final-3",)),
        ("HLA-DRB343", ("final-3",)),
        ("BLA-DRB345", ("bla",)),
        ("BLA-DRB3A/S", ("bla",)),
    ],
)
def test_the_branch_classifier_names_the_widening_that_let_the_header_in(
    text: str, branches: tuple[str, ...]
) -> None:
    """The four widenings are four different kinds of damage with four different
    risks. A pack that samples them as one pool cannot tell them apart, so the
    branch travels on the fact rather than being re-derived from the spelling."""
    from kidneymatch.ocr.drbx import widened_header_branches

    assert widened_header_branches(text) == branches


def test_a_final_3_header_writes_no_absence() -> None:
    """Route (c) required fix 2, second clause. The named genes are still
    PRESENT — a token spelling `DRB4` spells it whatever the header's last digit
    read as — but the third gene's ABSENT is withdrawn to a human.

    Measured on the corpus: 16 gated pages take this branch, 24 PRESENT cells
    are kept and 15 ABSENT cells move here."""
    facts = resolve_grouped_drbx(w5_two_token_page("HLA-DRB3/4/3"))
    assert facts["DRB3"].call is GeneCall.PRESENT
    assert facts["DRB4"].call is GeneCall.PRESENT
    assert facts["DRB5"].status is ResolutionStatus.REVIEW_REQUIRED
    assert facts["DRB5"].call is GeneCall.UNKNOWN
    assert "substituting a 3 for its printed final 5" in facts["DRB5"].reason


def test_the_other_widenings_still_certify_absence() -> None:
    """The placebo for the fix above: it must be the final digit that stops the
    absence, not the widening in general. A B-slot substitution damages a slot
    the printed enumeration does not depend on, and its ABSENT stands."""
    for header in ("DR3/4/5", "DRI3/4/5", "HLA-DRB3445", "BLA-DRB345"):
        facts = resolve_grouped_drbx(w5_two_token_page(header))
        assert facts["DRB5"].call is GeneCall.ABSENT, header
        assert facts["DRB5"].status is ResolutionStatus.RESOLVED, header


def test_an_S_on_the_row_still_beats_the_final_3_reason() -> None:
    """Both downgrades land on the same cell. The S-for-5 one is the stronger
    evidence — 7 of 10 such labelled cells printed the gene the row called
    absent — so it is the reason the reviewer is shown."""
    boxes = w5_page("HLA-DRB3/4/3")
    boxes.append(Box(x0=0.70, y0=0.480 - W5_H / 2, x1=0.76, y1=0.480 + W5_H / 2, text="DRBS"))
    facts = resolve_grouped_drbx(boxes)
    assert facts["DRB4"].status is ResolutionStatus.REVIEW_REQUIRED
    assert "rests on an S read as 5" in facts["DRB4"].reason


@pytest.mark.parametrize(
    ("header", "branch"),
    [("DR3/4/5", "b-slot-empty"), ("HLA-DRB3445", "slash-as-4"), ("HLA-DRB3/4/3", "final-3")],
)
def test_every_widened_fact_carries_the_rule_and_the_branch(header: str, branch: str) -> None:
    """Route (c) required fix 6. Without a marker the 312 cells these pages
    carry cannot be sampled as a stratum and cannot be withdrawn as a group —
    nothing else in a stored fact distinguishes a widened header from a strict
    one."""
    from kidneymatch.ocr.drbx import WIDENED_RULE_ID

    facts = resolve_grouped_drbx(w5_two_token_page(header))
    assert {f.rule_id for f in facts.values()} == {WIDENED_RULE_ID}
    assert {f.source for f in facts.values()} == {f"widened-drbx-header:{branch}"}


def test_a_widened_header_that_resolves_nothing_is_marked_too() -> None:
    """A widened page that ends in REVIEW is still a page whose header the
    recognizer damaged, and the reviewer must see those beside the ones it
    resolved — otherwise the stratum measures only the route's successes."""
    from kidneymatch.ocr.drbx import WIDENED_RULE_ID

    bare = [b for b in w5_page("DR3/4/5") if (b.text or "") != "DRB3"]
    facts = resolve_grouped_drbx(bare)
    assert all(f.status is ResolutionStatus.REVIEW_REQUIRED for f in facts.values())
    assert {f.rule_id for f in facts.values()} == {WIDENED_RULE_ID}


def test_a_strict_header_gains_neither_the_new_rule_nor_a_source() -> None:
    """The placebo for the marker. `drbx_ink_pass.py` and `drbx_reread.py`
    select `rule_id='GROUPED_DRBX/v1'`; if the new id leaked onto the ~12,000
    strict-header pages it would silently switch those passes off corpus-wide."""
    from kidneymatch.ocr.drbx import RULE_ID

    facts = resolve_grouped_drbx([HEADER, at(0.40, "DRB3"), at(0.70, "DRB4")])
    assert {f.rule_id for f in facts.values()} == {RULE_ID}
    assert {f.source for f in facts.values()} == {None}


# Every distinct spelling the geometry gate admits today, measured read-only
# over the corpus 2026-09-07. A header is a printed constant of the form, so
# these are form vocabulary and not anybody's data.
GATED_WIDENED_SPELLINGS = (
    "HLA-DRB3445",
    "DR3/4/5",
    "HLA-DRB3/4/3",
    "DRI3/4/5",
    "HLA-DRB344/5",
    "HLA-DRA345",
    "HLA-DRB343",
    "BLA-DRB3A/S",
    "LA-DRA3/45",
    "DRK3/4/5",
    "BLA-DRB345",
    "HLA-DRI3/45",
    "HLA-DRA3A45",
    "DRJ3/4/5",
    "IILA-DRI3/4/5",
    "HLA-DRI3/4/S",
    "HLA-DRE3/4/3",
    "HLA-DRI345",
    "HLA-DRA3AS",
    "HLA-DRB34/3",
    "HLA-DRA3/4/5",
    "HLA-DRA3/4/S",
    "DRU3/45",
    "LA-DRA345",
    "HLA-DRI3A4/S",
    "HLA-DRI3/4S",
    "HLA-DRA3/AS",
    "IILA-DRI3/45",
    "DRA3/4S",
    "DRA345",
    "HLA-DRB344/S",
    "HLA-DRI3AS",
)


def test_every_widened_spelling_the_corpus_admits_has_a_named_branch() -> None:
    """The pack is stratified by branch, so a spelling with no branch is a page
    that would be sampled as "the widening, unspecified" — which is the pooling
    the stratum exists to undo. Measured over the whole corpus: no widened
    spelling anywhere falls through to `unclassified`."""
    from kidneymatch.ocr.drbx import UNCLASSIFIED, widened_header_branches

    named = {"b-slot-glyph", "b-slot-empty", "slash-as-4", "final-3", "bla"}
    for text in GATED_WIDENED_SPELLINGS:
        branches = widened_header_branches(text)
        assert branches, text
        assert UNCLASSIFIED not in branches, text
        assert set(branches) <= named, text


def test_the_final_3_branch_is_exactly_the_spellings_whose_last_digit_is_a_3() -> None:
    """The placebo for the branch classifier itself. `final-3` is the one branch
    that withdraws an absence, so a spelling wrongly put in it costs a fact and
    a spelling wrongly kept out of it publishes a clinical negative on a glyph
    substitution. 4 of the 32 gated spellings end in a 3; on the corpus they are
    16 of the 104 pages."""
    from kidneymatch.ocr.drbx import FINAL_3, widened_header_branches

    ends_in_3 = {t for t in GATED_WIDENED_SPELLINGS if t.rstrip("]).:; *").endswith("3")}
    in_branch = {t for t in GATED_WIDENED_SPELLINGS if FINAL_3 in widened_header_branches(t)}
    assert in_branch == ends_in_3
    assert len(in_branch) == 4


def test_two_widened_headers_are_marked_with_the_union_of_their_branches() -> None:
    """One page corpus-wide carries both a strict header box and a widened-only
    one, and 14,359 carry a strict box the add-on passes are meant to reach. A
    page with more than one header refuses either way — but it must still be
    findable as a widened page, and its `source` must name every widening that
    got a box in, because the reviewer is being shown all of them at once."""
    from kidneymatch.ocr.drbx import WIDENED_RULE_ID

    second = w5_label("HLA-DRB3/4/3", 0.476, x0=0.10, x1=0.19)
    facts = resolve_grouped_drbx([*w5_page("DR3/4/5"), second])
    assert all(f.status is ResolutionStatus.REVIEW_REQUIRED for f in facts.values())
    assert "2 grouped headers" in facts["DRB3"].reason
    assert {f.rule_id for f in facts.values()} == {WIDENED_RULE_ID}
    assert {f.source for f in facts.values()} == {"widened-drbx-header:b-slot-empty+final-3"}
