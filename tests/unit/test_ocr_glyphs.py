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


def test_no_repair_can_turn_one_locus_into_another() -> None:
    """The safety property the whole design rests on.

    Every locus name, damaged in every way the repair understands, must still
    canonicalise to itself or to nothing — never to a different gene.
    """
    substitutions = {"1": "IilL|Tt!", "5": "Ss"}
    for locus in sorted(CLASS_II_LOCI):
        head, last = locus[:-1], locus[-1]
        for glyph in substitutions.get(last, ""):
            damaged = head + glyph
            result = canonical_locus_label(damaged)
            assert result in (locus, None), f"{damaged!r} became {result!r}, expected {locus!r}"


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


# --- class I values, and the bugs a second reading found ------------------


@pytest.mark.parametrize(
    ("token", "prefix", "first"),
    [("A*02", "A", "02"), ("B*35", "B", "35"), ("C*07", "C", "07"), ("Cw*07", "Cw", "07")],
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


def test_an_expression_suffix_is_not_swallowed_into_the_digits() -> None:
    """`A*02S` is a secreted allele, not `A*025`.

    The digit-slot repair maps `S` to `5`, so a greedy numeric group eats the
    suffix and invents a different allele. The suffix must be recognised first.
    """
    value = parse_allele_value("A*02S")
    assert value is not None
    assert value.first_field == "02"
    assert value.expression == "S"


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
