"""One box, both alleles: `A*24,*02`.

Some forms print a locus's two alleles in a single cell. Measured over the
corpus there are 1,819 such tokens on 890 documents, commonest as `A*##,*##`,
`DRB1*##,*##` and `B*##,*##`. Read as one value they lose half a genotype; read
as none they lose all of it.

The line these tests hold is the SECOND star. `A*24,*02` states two alleles and
nothing else. `A*24,02` does not: it is either two alleles written without
repeating the star, or the two-field allele `A*24:02` written with a comma
instead of a colon, and there is no way to tell from the glyphs. Guessing
either way breaks a rule this project states outright — invent a second allele,
or promote a first-field reading to a second field. So 1,025 tokens on 491
documents stay unread until a person settles what that form means (HA-015).
"""

from __future__ import annotations

from kidneymatch.ocr.glyphs import parse_allele_values


def named(token: str) -> list[str]:
    return [f"{value.locus_prefix}*{value.first_field}" for value in parse_allele_values(token)]


def test_one_allele_is_still_one_allele() -> None:
    assert named("A*24") == ["A*24"]


def test_a_second_star_states_a_second_allele() -> None:
    assert named("A*24,*02") == ["A*24", "A*02"]
    assert named("B*35,*51") == ["B*35", "B*51"]
    assert named("DRB1*15,*01") == ["DRB1*15", "DRB1*01"]


def test_the_locus_carries_over_to_the_second_allele() -> None:
    """`*02` alone names no gene; it inherits the one printed beside it."""
    assert named("DQB1*03,*05") == ["DQB1*03", "DQB1*05"]


def test_the_separators_a_form_actually_prints_are_read() -> None:
    """Comma dominates the corpus; a period and a slash also occur."""
    assert named("A*24,*02") == named("A*24.*02") == named("A*24/*02")
    assert named("A*24, *02") == ["A*24", "A*02"]


def test_an_hla_prefix_does_not_hide_the_pair() -> None:
    assert named("HLA-B*35,*51") == ["B*35", "B*51"]


def test_one_star_with_a_separator_stays_unread() -> None:
    """`A*24,02`: two alleles, or `A*24:02` with the wrong separator? Unknown."""
    assert parse_allele_values("A*24,02") == []
    assert parse_allele_values("DRB1*15,01") == []


def test_a_pair_with_no_locus_on_the_first_half_names_no_gene() -> None:
    """Which gene a bare number belongs to is never decided from its text."""
    assert parse_allele_values("24,*02") == []
    assert parse_allele_values("*24,*02") == []


def test_a_two_field_allele_is_not_a_pair() -> None:
    values = parse_allele_values("A*24:02")
    assert len(values) == 1
    assert values[0].first_field == "24"
    assert values[0].second_field == "02"


def test_a_label_is_never_a_pair() -> None:
    assert parse_allele_values("HLA-A") == []
    assert parse_allele_values("DRB1") == []


def test_nonsense_does_not_become_two_alleles() -> None:
    assert parse_allele_values("") == []
    assert parse_allele_values("ponias,*02") == []
    assert parse_allele_values("A*24,*") == []
