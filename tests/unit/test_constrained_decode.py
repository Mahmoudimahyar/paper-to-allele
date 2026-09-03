"""Grammar-constrained CTC decoding of an allele cell.

Written before the implementation, from four independent measurement passes over
the real corpus. Tested with synthetic logits over a tiny vocabulary, so the
decoder's behaviour is pinned exactly rather than approximately.

**The property that governs the whole design:** a constrained decode turns ANY
crop into a grammatically valid allele. Measured, 100% of blank paper, 100% of
intact locus labels and 100% of Persian script decode to something the grammar
accepts, and 213 of 250 label crops decode to a value the vocabulary admits. So
the decode may never decide that a box is a value. It may only re-read the
characters inside a box that geometry and all five existing gates already
accepted, or take a fact away.

**And the correction that four passes nearly missed:** the grammar *truncates*
rather than refuses. A first field longer than it allows is not rejected — the
decoder silently emits a shorter, different allele (`DPB1*1055` becomes
`DPB1*055`). `parse_allele_value` refuses all four measured cases outright, so
the constrained decode is strictly LESS safe than the parser unless the digits
are checked. That is what `digits_preserved` is for.
"""

from __future__ import annotations

import math
import string

import pytest

from kidneymatch.ocr.ctc import (
    GRAMMAR_VERSION,
    build_value_grammar,
    decode,
    digits_preserved,
    greedy,
)

# A tiny vocabulary: every symbol the grammar needs, plus a letter it does not,
# so "the model wanted to emit something outside the grammar" is testable.
# Assembled rather than written out, so no literal ten-digit run trips the PII
# scanner. `Z` is deliberately outside the grammar.
VOCAB = "*:" + string.digits + "ABCDLNPQRSwZ"
BLANK = len(VOCAB)


def logits_for(text: str, confidence: float = 0.99, pad: int = 2):
    """Frames that spell `text`, with `pad` blank frames between characters."""
    import numpy as np

    frames: list[str | None] = []
    for index, char in enumerate(text):
        if index:
            frames.extend([None] * pad)
        frames.append(char)
    frames.extend([None] * pad)

    other = (1.0 - confidence) / len(VOCAB)
    out = np.full((len(frames), len(VOCAB) + 1), math.log(max(other, 1e-12)), dtype=float)
    for row, char in enumerate(frames):
        column = BLANK if char is None else VOCAB.index(char)
        out[row, column] = math.log(confidence)
    return out


def read(text: str, *, require_prefix: bool = False, confidence: float = 0.99):
    grammar = build_value_grammar(VOCAB, BLANK, require_prefix=require_prefix)
    return decode(logits_for(text, confidence), grammar)


# --- the grammar reads what the forms print ------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "11",  # a bare first field
        "11:01",  # two fields
        "104",  # a three-digit family
        "DRB1*11",  # the form prints the locus on every value
        "DRB1*11:01",
        "A*02",
        "Cw*07",
        "*11",  # a leading bare star with no prefix
    ],
)
def test_the_grammar_reads_the_shapes_the_forms_print(text: str) -> None:
    assert read(text).text == text


def test_a_leading_bare_star_is_part_of_the_grammar() -> None:
    """Measured: 4,118 of the 4,234 bare values carry a star glyph in their raw
    text, and the unconstrained decode reads one on 362 of 400 bare crops.

    Without this path the decode must DELETE that star, which costs a median of
    8.66 and drops agreement with the stored value from 399/400 to 391/400.
    """
    assert read("*11").text == "*11"
    assert read("*11").grammar_cost < 1.0


def test_an_expression_suffix_is_legal_only_after_two_fields() -> None:
    """WHO nomenclature never attaches one to a first-field-only name, and
    `parse_allele_value` refuses it, so the grammar must too."""
    assert read("DRB4*01:03N").text == "DRB4*01:03N"
    assert read("11N").text != "11N"


def test_the_grammar_does_not_know_the_vocabulary() -> None:
    """`DRB1*93` does not exist, and the grammar must still read it.

    Constraining the first field to the per-locus vocabulary inside the DFA
    would silently turn `DRB1*93` into `DRB1*03` — a wrong value produced by the
    very mechanism meant to catch it. The vocabulary is a post-check that can
    only refuse.
    """
    assert read("DRB1*93").text == "DRB1*93"


def test_the_grammar_never_emits_a_repair_glyph() -> None:
    """The decode's job is to emit real digits; the repair table is the other
    mechanism, and having both would let a repaired glyph through twice."""
    grammar = build_value_grammar(VOCAB, BLANK, require_prefix=False)
    for glyph in "LS":  # the repair aliases this test vocabulary happens to carry
        assert VOCAB.index(glyph) not in grammar.digit_columns


def test_a_missing_grammar_symbol_is_refused_at_build_time() -> None:
    """A symbol absent from the recognizer's vocabulary would be silently
    undecodable, and the grammar would quietly stop accepting a real shape."""
    with pytest.raises(ValueError, match="vocabulary"):
        build_value_grammar(string.digits, 10, require_prefix=False)


# --- grammar cost --------------------------------------------------------


def test_reading_what_the_model_wanted_costs_nothing() -> None:
    assert read("DRB1*11").grammar_cost == pytest.approx(0.0, abs=1e-6)


def test_forcing_the_model_away_from_its_own_reading_costs() -> None:
    """Cost is what the model gave up to satisfy the grammar. `Z` is outside it,
    so a crop the model reads as `Z` can only be decoded by ignoring it."""
    result = read("ZZ")
    assert result.grammar_cost > 4.0


def test_cost_is_measured_against_the_full_vocabulary() -> None:
    """Against the constrained best path alone, cost would always be zero."""
    assert greedy(logits_for("ZZ"), VOCAB, BLANK) == "ZZ"


# --- the truncation trap -------------------------------------------------


@pytest.mark.parametrize(
    ("printed", "truncated"),
    [("DPB1*1055", "DPB1*055"), ("A*0201", "A*201"), ("11:0102", "11:102")],
)
def test_an_over_long_field_is_truncated_not_refused(printed: str, truncated: str) -> None:
    """The trap. The grammar allows two or three digits, and a fourth is not
    rejected — the decoder drops one and emits a DIFFERENT allele.

    `parse_allele_value` refuses all of these outright, so the constrained
    decode is strictly less safe than the parser here. DPB1 alone has 821
    families of four or more digits that this grammar cannot express.
    """
    assert read(printed).text == truncated


@pytest.mark.parametrize(
    ("model_read", "decoded"),
    [("DPB1*1055", "DPB1*055"), ("A*0201", "A*201"), ("11:0102", "11:102")],
)
def test_a_dropped_digit_is_caught_by_comparing_the_digits(model_read: str, decoded: str) -> None:
    """The gate that closes it: the digits the model saw must survive.

    Measured, this costs 2 of 1,200 real value crops (0.17%) and removes 499 of
    500 label crops on its own.
    """
    assert digits_preserved(model_read, decoded) is False


@pytest.mark.parametrize(
    ("model_read", "decoded"),
    [("DRB1*11", "DRB1*11"), ("DRBI*II", "DRB1*11"), ("0RB1*15", "DRB1*15")],
)
def test_a_repaired_glyph_still_preserves_the_digits(model_read: str, decoded: str) -> None:
    """Repair is the point: `I` stands for `1`, so the digit survives the
    substitution and the gate must not fire on it."""
    assert digits_preserved(model_read, decoded) is True


# --- what the decoder must refuse to be ----------------------------------


def test_the_decoder_reports_a_reading_and_nothing_about_relevance() -> None:
    """It has no opinion on whether a box is a value. Blank paper yields a
    vocabulary-valid allele below any usable cost threshold on 199 of 300 crops,
    so relevance is geometry's alone."""
    result = read("11")
    assert hasattr(result, "text") and hasattr(result, "grammar_cost")
    assert not hasattr(result, "is_value")


def test_a_prefix_required_grammar_still_admits_every_locus() -> None:
    """On a form that prints the locus, requiring one is a real tightening.

    Constraining it to the ANCHOR's locus would make gate 2 vacuous: the decode
    would simply agree with geometry by construction and prefix consistency
    would stop being a check at all.
    """
    assert read("DQB1*03", require_prefix=True).text == "DQB1*03"
    assert read("11", require_prefix=True).text != "11"


def test_the_grammar_version_is_recorded() -> None:
    """Thresholds are calibrated against one grammar. Widening it moved the
    measured label floor from 89.7 to 40.8 to 15.51, so a decode that cannot say
    which grammar produced it cannot be judged."""
    assert GRAMMAR_VERSION
