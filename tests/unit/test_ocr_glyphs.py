"""Glyph repair for locus labels and allele values — written before the code.

The recognizer confuses a small, measured set of glyphs, and repairing them is
the single highest-yield accuracy change available: the label `DRB1` is read
`DRBI` **3.5x more often than correctly** (12,679 boxes vs 3,676), which hid
most of the corpus's anchors and made locus resolution look impossible.

But a repair that changes which GENE a label names is the most dangerous string
operation in this project. These tests fix the boundary:

* **Accepting an anchor is strict.** Only the FINAL character is repaired, only
  `1`-like glyphs to `1` and `S` to `5`. Interior damage (`DRRI` for `DRB1`,
  where `B` was read `R`) is refused: measured, interior repair would add ~1%
  more anchors, and it is the only mechanism by which `DRB1` could become
  `DPB1`.
* **Rejecting a value is permissive.** Anything that could be a label — bare
  `A`, damaged `DRRI` — is refused as a value even though it is not good enough
  to anchor. Refusing costs recall; accepting costs a wrong-locus binding.

The asymmetry is deliberate and is itself under test.
"""

from __future__ import annotations

import pytest

from kidneymatch.ocr.glyphs import (
    CLASS_I_LOCI,
    CLASS_II_LOCI,
    canonical_locus_label,
    looks_like_locus_label,
    parse_allele_value,
)

# --- locus labels: accepting an anchor -----------------------------------


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("DRB1", "DRB1"),
        ("HLA-DRB1", "DRB1"),
        ("HLA DRB1", "DRB1"),
        ("  DQB1  ", "DQB1"),
        # The measured confusions. `DRBI` outnumbers `DRB1` 3.5:1.
        ("DRBI", "DRB1"),
        ("DRBl", "DRB1"),
        ("DRBL", "DRB1"),
        ("DRB|", "DRB1"),
        ("DPAT", "DPA1"),
        ("DQAL", "DQA1"),
        ("HLA-DPBI", "DPB1"),
        ("DRBS", "DRB5"),
        ("DRBs", "DRB5"),
    ],
)
def test_a_damaged_final_character_is_repaired(token: str, expected: str) -> None:
    assert canonical_locus_label(token) == expected


@pytest.mark.parametrize(
    "token",
    [
        "DRRI",  # B read as R: interior damage
        "DRR3",
        "DPRI",
        "DRE3",
        "DRI",  # too short to be any locus
        "DRB",  # no gene number at all
        "DR",
        "",
    ],
)
def test_interior_damage_is_refused_not_guessed(token: str) -> None:
    """Repairing the interior is how `DRB1` becomes `DPB1`.

    Measured on the corpus, interior repair would add roughly 1% more anchors.
    That is not worth a mechanism that can silently rename a gene.
    """
    assert canonical_locus_label(token) is None


@pytest.mark.parametrize("token", ["DRB1*11", "DRB1*11:01", "DQB1*03", "*11", "11"])
def test_a_value_token_is_never_an_anchor(token: str) -> None:
    """`\\bDRB1\\b` also matches inside `DRB1*11`.

    Measured, that inflated apparent DRB1 presence 5.18x and placed the locus
    wherever a patient-specific value happened to sit (ADR 0007).
    """
    assert canonical_locus_label(token) is None


@pytest.mark.parametrize("token", ["A", "B", "C", "Cw", "a"])
def test_a_bare_class_I_letter_is_not_an_anchor(token: str) -> None:
    """One letter is not evidence of a locus.

    Measured: 33,175 boxes are a bare `A`, against 15,281 documents carrying a
    prefixed `HLA-A`. Bare letters are table headers, ABO groups, and
    recognizer fragments. The prefixed form is the reliable anchor.
    """
    assert canonical_locus_label(token) is None


@pytest.mark.parametrize(
    ("token", "expected"), [("HLA-A", "A"), ("HLA-B", "B"), ("HLA-C", "C"), ("HLA-Cw", "Cw")]
)
def test_a_prefixed_class_I_label_is_an_anchor(token: str, expected: str) -> None:
    assert canonical_locus_label(token) == expected


def test_the_combined_drb345_header_is_not_a_locus_label() -> None:
    """`HLA_VALIDATION_SPEC` section 7: DRB3/4/5 are three separate genes.

    Binding one value to it would assign the same allele to all three. It needs
    its own anchor type, not a locus label.
    """
    for token in ("DRB3/4/5", "DRB3/4/S", "HLA-DRB3/4/5"):
        assert canonical_locus_label(token) is None


@pytest.mark.parametrize("locus", sorted(CLASS_II_LOCI | CLASS_I_LOCI))
def test_every_canonical_locus_name_survives_a_round_trip(locus: str) -> None:
    prefixed = f"HLA-{locus}"
    assert canonical_locus_label(prefixed) == locus


def test_the_set_of_gene_renaming_repairs_is_exactly_the_accepted_one() -> None:
    """The safety property the whole design rests on, stated honestly.

    For `DQA`, `DQB`, `DPA` and `DPB` only one gene exists, so the final
    character carries no gene information and repairing it cannot rename
    anything. For `DRB` the final character IS the gene, so every repair there
    is a potential rename, and the module docstring used to deny this.

    Sweeping every single-character mutation over printable ASCII finds exactly
    30 renames, all within the DRB family and all of the form "a letter the
    repair table maps to `1` or `5`". They are accepted with evidence:

    * `I/i/l/L/T/t/!/|` to `1`: the likelihood ratio for a printed `1` over a
      printed `3` reading as `I` is about 891, giving P(DRB1 | "DRBI") ~ 99.90%,
      with 368 of 368 same-column geometry checks consistent. `DRBI` outnumbers
      `DRB1` 3.5 to 1, so refusing it would cost 12,679 anchors.
    * `S/s` to `5`: measured against the independently-read DRB1 row, standalone
      `DRBS` matches a genotype expecting DRB5 in 99.2% of 1,020 cases against
      17.7% for DRB3 (ADR 0008).

    The residual risk is a printed `3`, `4` or `5` misread as one of those
    letters, measured at roughly 0.09% for `3` to `I`. This test pins the set so
    that adding any new substitution has to confront the list rather than
    quietly widening it.
    """
    canonical_names = {name.upper() for name in CLASS_II_LOCI}
    renames = set()
    for locus in sorted(CLASS_II_LOCI):
        for position in range(len(locus)):
            for glyph in (chr(code) for code in range(33, 127)):
                damaged = locus[:position] + glyph + locus[position + 1 :]
                if damaged == locus or damaged.upper() in canonical_names:
                    # A mutation that spells another gene's real name is not a
                    # repair: reading `DQA1` as DQA1 is correct.
                    continue
                result = canonical_locus_label(damaged)
                if result is not None and result != locus:
                    renames.add((locus, result))

    assert renames == {
        ("DRB1", "DRB5"),  # the final 1 read as S
        ("DRB3", "DRB1"),  # the final 3 read as a 1-lookalike
        ("DRB3", "DRB5"),
        ("DRB4", "DRB1"),
        ("DRB4", "DRB5"),
        ("DRB5", "DRB1"),
    }, "a repair renames a gene in a way this test has not accepted"


def test_no_repair_renames_a_gene_outside_the_DRB_family() -> None:
    """The stems with only one gene can never be renamed by a repair."""
    single_gene = {"DQA1", "DQB1", "DPA1", "DPB1"}
    canonical_names = {name.upper() for name in CLASS_II_LOCI}
    for locus in sorted(single_gene):
        for position in range(len(locus)):
            for glyph in (chr(code) for code in range(33, 127)):
                damaged = locus[:position] + glyph + locus[position + 1 :]
                if damaged == locus or damaged.upper() in canonical_names:
                    continue
                assert canonical_locus_label(damaged) in (locus, None), damaged


# --- the permissive side: rejecting a value ------------------------------


@pytest.mark.parametrize("token", ["DRB1", "DRBI", "DRRI", "A", "HLA-B", "DRB3/4/5", "DPBI"])
def test_anything_label_shaped_is_rejected_as_a_value(token: str) -> None:
    """Rejection is permissive where acceptance is strict.

    `DRRI` is too damaged to anchor a locus, but a resolver that bound it as a
    VALUE would emit a patient allele of `DRRI`. Refusing costs recall;
    accepting costs a wrong fact.
    """
    assert looks_like_locus_label(token) is True


@pytest.mark.parametrize("token", ["11", "*11", "DRB1*11", "15:01", "03:01"])
def test_a_real_value_is_not_mistaken_for_a_label(token: str) -> None:
    assert looks_like_locus_label(token) is False


# --- allele values -------------------------------------------------------


@pytest.mark.parametrize(
    ("token", "first", "second"),
    [
        ("11", "11", None),
        ("*11", "11", None),
        ("DRB1*11", "11", None),
        ("DRB1 * 11", "11", None),
        ("11:01", "11", "01"),
        ("DRB1*11:01", "11", "01"),
        ("DPB1*104:01", "104", "01"),
    ],
)
def test_allele_values_parse_into_fields(token: str, first: str, second: str | None) -> None:
    value = parse_allele_value(token)
    assert value is not None
    assert value.first_field == first
    assert value.second_field == second


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("II", "11"),
        ("LS", "15"),
        ("SS", "55"),
        ("0S", "05"),
        ("o3", "03"),
        ("DRBI*II", "11"),
        ("DRB1+11", "11"),  # `*` read as `+`
        ("DRB1°11", "11"),
        ('DRB1"11', "11"),
    ],
)
def test_digit_slot_glyphs_are_repaired_inside_a_value(token: str, expected: str) -> None:
    """Measured: 20.7% of value-shaped boxes carry a letter in a digit slot.

    Safe here only because the cell's grammar is known to be numeric. The same
    substitution on free text would be vandalism.
    """
    value = parse_allele_value(token)
    assert value is not None
    assert value.first_field == expected
    assert value.repaired is True


def test_an_undamaged_value_is_not_marked_repaired() -> None:
    value = parse_allele_value("11:01")
    assert value is not None and value.repaired is False


def test_the_raw_token_is_always_preserved() -> None:
    """Provenance: every derived fact must point back at what was actually read."""
    value = parse_allele_value("DRBI*II")
    assert value is not None
    assert value.raw == "DRBI*II"


def test_a_locus_prefix_on_the_value_is_reported_for_cross_checking() -> None:
    """The prefix does not decide the locus — geometry does — but it must be
    available so the resolver can refuse a value that contradicts its anchor."""
    value = parse_allele_value("DQB1*03")
    assert value is not None and value.locus_prefix == "DQB1"
    assert parse_allele_value("*03").locus_prefix is None  # type: ignore[union-attr]


@pytest.mark.parametrize("token", ["DRB1", "YEKTA", "1234567", "", "-", "N/A", "12:34:56", "A+"])
def test_non_values_are_refused(token: str) -> None:
    assert parse_allele_value(token) is None


def test_a_first_field_is_never_expanded_to_two_fields() -> None:
    """`OCR-001`: low-resolution first-field typing is never promoted.

    A first-field-only value stays first-field-only. There is no "most common
    second field" and inventing one would fabricate a clinical fact.
    """
    value = parse_allele_value("DRB1*11")
    assert value is not None
    assert value.second_field is None
    assert value.text() == "DRB1*11"


def test_expression_suffixes_are_kept() -> None:
    """`DRB4*01:03N` is a NULL allele — the suffix changes the biology."""
    value = parse_allele_value("DRB4*01:03N")
    assert value is not None
    assert value.expression == "N"
    assert value.text() == "DRB4*01:03N"


# --- the star that was not read ------------------------------------------


@pytest.mark.parametrize(
    ("token", "prefix", "first"),
    [
        ("A02", "A", "02"),
        ("B44", "B", "44"),
        ("C04", "C", "04"),
        ("DQB102", "DQB1", "02"),
        ("DQBI02", "DQB1", "02"),  # the label's final 1 read as I, as anchors repair it
        ("DRB115", "DRB1", "15"),
        ("HLA-A02", "A", "02"),
        ("DPB1104", "DPB1", "104"),
        ("Cw07", "C", "07"),  # the serological spelling of the C locus, as the confirmer reads it
        ("Cw*07", "C", "07"),
    ],
)
def test_a_value_that_lost_its_star_still_parses_with_its_prefix(
    token: str, prefix: str, first: str
) -> None:
    """Measured corpus-wide: 3,153 cells were refused only because the `*`
    between the locus prefix and the digits was not read at all — 45% of every
    shape refusal, and 6 of the reviewer's 21 misses on the first 165 labels,
    where the constrained decode had read the same cells as `A*## A*##`.

    The prefix still names a locus, the digits still face the admissibility
    gate, and the anchor check still refuses a prefix that names another gene.
    So the missing star is a repair — the token is marked repaired — never a
    licence: nothing about WHICH locus is decided here.
    """
    value = parse_allele_value(token)
    assert value is not None, token
    assert value.locus_prefix == prefix
    assert value.first_field == first
    assert value.repaired is True


@pytest.mark.parametrize("token", ["ALL", "BIS", "COS", "Ali", "BSS", "AO2", "DQBIOS", "CII"])
def test_without_a_star_the_digits_must_be_digits(token: str) -> None:
    """The digit-slot repairs turn letters into digits because the star says a
    number follows. Without the star, `ALL` would be A + `LL` = A*11 and `BIS`
    B*15 — measured, 74 resolved cells carried a letters-only token under the
    first version of the star-less rule. A word on a row is not a value."""
    assert parse_allele_value(token) is None


def test_a_star_less_value_says_so_and_a_starred_one_does_not() -> None:
    """The resolver admits a star-less value only on a form measured to print
    the locus on its values; it needs to know which case it is looking at."""
    starless = parse_allele_value("A02")
    starred = parse_allele_value("A*02")
    assert starless is not None and starless.separator_missing is True
    assert starred is not None and starred.separator_missing is False
    apostrophe = parse_allele_value("A'02")
    assert apostrophe is not None and apostrophe.separator_missing is False


@pytest.mark.parametrize("token", ["DRB11", "DR15", "CW4", "A2", "B5", "N1", "DRB13", "DRB1"])
def test_a_star_less_token_is_refused_unless_its_prefix_names_a_locus(token: str) -> None:
    """`DR15` and `CW4` are serology, not a locus prefix plus digits; `DRB11`
    cannot say where the label ends and the value begins; a single digit is
    not a first field. None of these may become a value by losing a star."""
    assert parse_allele_value(token) is None


def test_a_B_read_as_8_before_the_star_is_repaired_and_marked() -> None:
    """`8*44`: the recognizer's measured B/8 confusion in the prefix slot,
    56 cells corpus-wide. Only with a star following — a bare `844` stays a
    bare number, which no locus admits and the family rule refuses."""
    value = parse_allele_value("8*44")
    assert value is not None
    assert value.locus_prefix == "B"
    assert value.first_field == "44"
    assert value.repaired is True
    bare = parse_allele_value("844")
    assert bare is not None and bare.locus_prefix is None and bare.first_field == "844"


# --- class I values, and the bugs a second reading found ------------------


@pytest.mark.parametrize(
    ("token", "prefix", "first"),
    [
        ("A*02", "A", "02"),
        ("B*35", "B", "35"),
        ("C*07", "C", "07"),
        # `Cw` is the serological spelling of the C locus; as a value prefix it
        # names C, exactly as the confirmer already reads `Cw07`'s digits as C's.
        ("Cw*07", "C", "07"),
    ],
)
def test_a_class_I_value_carries_its_locus_without_an_HLA_prefix(
    token: str, prefix: str, first: str
) -> None:
    """A bare `A` cannot ANCHOR a locus; `A*02` is unambiguously a value.

    The `HLA-` requirement exists because a lone letter is a table header or an
    ABO group far more often than a locus. A letter followed by `*` and two
    digits has no such competition. Requiring the prefix here dropped 68,577 of
    126,028 self-identifying values — 54.4%.
    """
    value = parse_allele_value(token)
    assert value is not None
    assert value.locus_prefix == prefix
    assert value.first_field == first


def test_an_HLA_prefix_on_a_value_is_stripped() -> None:
    value = parse_allele_value("HLA-DRB1*15")
    assert value is not None and value.locus_prefix == "DRB1" and value.first_field == "15"


def test_a_suffix_is_never_swallowed_into_the_digits() -> None:
    """The digit-slot repair maps `S` to `5`, so a greedy numeric group would
    eat a suffix and invent a different allele.

    This test originally asserted that `A*02S` parses as the family `02` with a
    secreted suffix. That was wrong: WHO nomenclature attaches an expression
    suffix only to a complete allele name, so `A*02S` is not a designation at
    all and is now refused outright. What must still hold is that no reading
    silently turns the suffix into a digit.
    """
    assert parse_allele_value("A*02S") is None
    complete = parse_allele_value("A*02:01N")
    assert complete is not None
    assert complete.first_field == "02" and complete.second_field == "01"
    assert complete.expression == "N"


@pytest.mark.parametrize("token", ["DRB1*D2", "DRB1*Q2"])
def test_letters_that_were_never_measured_as_digits_are_refused(token: str) -> None:
    """`D` and `Q` were in the repair table with 12 and 5 occurrences corpus-wide
    and zero that validated against nomenclature. Pure false-accept surface."""
    assert parse_allele_value(token) is None


def test_DRBS_names_DRB5_and_the_evidence_is_direct() -> None:
    """A second design pass argued `DRBS` should abstain, from a prior-odds
    model giving 92% confidence. Direct measurement against independent ground
    truth refutes it.

    Taking the DRB1 row — read by a different anchor, a different rule and a
    different part of the page — as truth, and using the haplotype constraint
    that DRB1*15/*16 carry DRB5 while *03/*11/*12/*13/*14 carry DRB3:

    | standalone label | n | DRB1 expects DRB5 | expects DRB3 |
    |---|---|---|---|
    | `DRB5` | 1,142 | 99.6% | 48.4% |
    | `DRBS` | 1,020 | **99.2%** | 47.8% |
    | `DRB3` | 5,830 | 17.7% | 99.9% |

    `DRBS` is indistinguishable from `DRB5` and nothing like `DRB3`. The prior
    the model assumed does not describe the `DRBS` population.
    """
    assert canonical_locus_label("DRBS") == "DRB5"


# --- W11: the expression suffix ------------------------------------------


@pytest.mark.parametrize("token", ["10S", "13S", "35S", "42L", "SOSS", "ILA", "IILA", "TILA"])
def test_a_suffix_after_a_first_field_alone_is_not_a_value(token: str) -> None:
    """WHO nomenclature never attaches an expression suffix to a first-field-only
    name, so every such parse is a misread accepted as a value.

    `L` and `S` are also digit-slot repairs, so a three-character token ending
    in one was read as a two-digit family plus a suffix; `A` turned the `HLA`
    fragments the recognizer emits (`ILA`, `IILA`) into alleles. Measured: 3,062
    boxes parse this way against exactly one with a real second field, and 33
    reached an anchored cell.
    """
    assert parse_allele_value(token) is None


def test_a_suffix_after_two_fields_is_kept() -> None:
    """`DRB4*01:03N` is a null allele: the suffix changes the biology."""
    value = parse_allele_value("DRB4*01:03N")
    assert value is not None and value.expression == "N"


def test_a_three_digit_family_is_not_split_into_digits_and_a_suffix() -> None:
    """`10S` must not become `10` + suffix; with the repair it is the family 105."""
    value = parse_allele_value("DPB1*10S:01")
    assert value is not None and value.first_field == "105" and value.second_field == "01"
