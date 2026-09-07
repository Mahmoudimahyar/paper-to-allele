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


# --- the B row's Bw4/Bw6 epitope tail ---------------------------------------
#
# One laboratory prints `B*35,*51,Bw4,Bw6`. The pair pattern returns nothing for
# it, so B was unreachable on 279 pages of that form. A SECOND pattern, tried
# only after the pair pattern fails, reads the two alleles and drops the
# epitopes — they are serology, not alleles. Every refusal below was
# constructed before the pattern was written.


def test_the_epitope_tail_does_not_hide_the_pair() -> None:
    assert named("B*35,*51,Bw4") == ["B*35", "B*51"]
    assert named("B*35,*51,Bw4,Bw6") == ["B*35", "B*51"]


def test_the_tail_is_dropped_not_read_as_an_allele() -> None:
    """Bw4 and Bw6 are serological epitopes of the B locus. Writing them into a
    genotype would be inventing a third allele out of a public specificity."""
    values = parse_allele_values("B*35,*51,Bw4,Bw6")
    assert [v.first_field for v in values] == ["35", "51"]
    assert all(v.second_field is None for v in values)


def test_the_tail_is_read_however_it_is_cased_and_spaced() -> None:
    assert named("B*35,*51,bw4,BW6") == named("B*35, *51, Bw4, Bw6") == ["B*35", "B*51"]
    assert named("B*35,*51,Bw6,Bw4") == ["B*35", "B*51"]


def test_case_insensitivity_stops_at_the_tail() -> None:
    """`A*02:01S` is the secreted allele; `A*02:01s` is `A*02:015`, because `s`
    is a digit-slot repair. Compiling the whole pattern with IGNORECASE to
    reach `bw4` would have made those two the same value."""
    assert parse_allele_values("A*02:01S")[0].expression == "S"
    lower = parse_allele_values("A*02:01s")[0]
    assert lower.expression is None and lower.second_field == "015"


def test_the_forms_the_pair_already_refused_are_still_refused_with_a_tail() -> None:
    """The tail widens nothing else. A single allele stays single, and the
    one-star form stays unread until a person settles what it means (HA-015)."""
    assert parse_allele_values("B*35,Bw6") == []
    assert parse_allele_values("B*35,51,Bw4") == []
    assert parse_allele_values("B35,*51,Bw4") == []
    assert parse_allele_values("*35,*51,Bw4") == []


def test_a_tail_after_another_gene_is_a_misread_not_a_wider_grammar() -> None:
    for token in ("A*24,*02,Bw4", "C*07,*04,Bw4", "Cw*07,*04,Bw4", "DRB1*15,*01,Bw4"):
        assert parse_allele_values(token) == [], token


def test_the_eight_for_b_prefix_repair_still_reaches_b_through_the_tail() -> None:
    """Pinned deliberately: `8*` is the recognizer's B, repaired by the same
    rule that repairs it without a tail. Three corpus tokens, all on comparison
    sheets — where `column_bind.py` refuses them anyway, because a REPAIRED
    prefix may not be the only evidence of a gene."""
    assert named("8*35,*51,Bw4") == ["B*35", "B*51"]


def test_only_bw4_and_bw6_are_a_tail() -> None:
    for token in ("B*35,*51,Bw5", "B*35,*51,BWE", "B*35,*51,Bd6", "B*35,*51,Bw"):
        assert parse_allele_values(token) == [], token


def test_a_third_tail_is_not_a_tail_at_all() -> None:
    """A B allele carries at most one Bw4 and one Bw6. With a bounded repeat the
    non-greedy pair group simply swallowed the surplus and this parsed clean."""
    assert parse_allele_values("B*35,*51,Bw4,Bw6,Bw4") == []
    assert parse_allele_values("B*35,*51,Bw4,Bw6,Bw4,Bw6") == []


def test_only_a_comma_introduces_the_tail() -> None:
    for token in ("B*35,*51.Bw4", "B*35,*51 Bw4", "B*35,*51;Bw4", "B*35,*51/Bw4"):
        assert parse_allele_values(token) == [], token


def test_a_decorated_or_truncated_tail_is_refused() -> None:
    for token in ("B*35,*51,(Bw4)", "B*35,*51,Bw4:", "B*35,*51,Bw4,", "B*35,*51,Bw4."):
        assert parse_allele_values(token) == [], token


def test_the_tail_may_not_sit_between_the_alleles() -> None:
    assert parse_allele_values("B*35,Bw4,*51,Bw6") == []
    assert parse_allele_values("B*35,Bw6,*51,Bw4") == []
    assert parse_allele_values("B*35,*Bw4") == []


def test_two_subjects_merged_into_one_box_are_not_one_genotype() -> None:
    """The failure this shape makes possible: two people's B rows read as a
    single token would put one person's allele in the other's record."""
    assert parse_allele_values("B*35,*51,Bw4,Bw6,B*07,*44,Bw6") == []
    assert parse_allele_values("B*35,*51,Bw4,Bw6 B*07,*44,Bw6") == []


def test_the_tail_survives_the_forms_the_parser_already_accepted() -> None:
    assert named("HLA-B*35,*51,Bw4") == ["B*35", "B*51"]
    assert named('B"35,"51,Bw4') == ["B*35", "B*51"]
    assert all(v.repaired for v in parse_allele_values('B"35,"51,Bw4'))
    two_field = parse_allele_values("B*35:01,*51:01,Bw4")
    assert [v.second_field for v in two_field] == ["01", "01"]
