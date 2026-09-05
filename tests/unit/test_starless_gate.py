"""A value whose star was not read resolves only where the form is known to print one.

`A02` for `A*02` is the recognizer dropping the separator on a form that prints
`LOCUS*NN` on every value — measured at 99.8-99.9% on the three families the
family rule serves, and 1,958 recovered cells corpus-wide. On a form nobody has
measured, the same token may be a serological spelling, which
`HLA_VALIDATION_SPEC.md` s4 keeps apart from allele notation. The parser marks
the case; the resolver decides by the rule it is running under.
"""

from __future__ import annotations

import pytest

from kidneymatch.ocr.anchors import Box, ResolutionStatus, ValueRule, resolve_locus

pytestmark = pytest.mark.task("OCR-001")

LABEL = Box(0.10, 0.50, 0.18, 0.53, "HLA-A")
DEFAULT_RULE = ValueRule(direction="right", align_overlap=0.2, max_gap=20.0, max_values=2)
FAMILY_RULE = ValueRule(
    direction="right",
    align_overlap=0.2,
    max_gap=None,
    max_values=2,
    centre_band=1.9,
    require_prefix=True,
)


def value(x0: float, text: str) -> Box:
    return Box(x0, 0.50, x0 + 0.07, 0.53, text)


def test_a_star_less_value_resolves_on_a_form_that_prints_the_locus_on_its_values() -> None:
    result = resolve_locus([LABEL, value(0.22, "A02"), value(0.40, "A11")], "A", FAMILY_RULE)
    assert result.status is ResolutionStatus.RESOLVED, result.reason
    assert result.values == ["A*02", "A*11"]
    assert result.repaired is True


def test_a_star_less_value_goes_to_review_under_the_default_rule() -> None:
    """Unmeasured form: `B35` may be serology. A human decides, never the parser."""
    result = resolve_locus([LABEL, value(0.22, "A02")], "A", DEFAULT_RULE)
    assert result.status is ResolutionStatus.REVIEW_REQUIRED
    assert "without a star" in result.reason
    assert result.value_boxes  # the box is kept so the queue can show the row


def test_a_starred_value_is_unaffected_under_the_default_rule() -> None:
    result = resolve_locus([LABEL, value(0.22, "A*02")], "A", DEFAULT_RULE)
    assert result.status is ResolutionStatus.RESOLVED
    assert result.values == ["A*02"]


@pytest.mark.parametrize("word", ["ALL", "BIS", "AOS"])
def test_a_word_on_the_row_never_resolves_under_either_rule(word: str) -> None:
    for rule in (DEFAULT_RULE, FAMILY_RULE):
        result = resolve_locus([LABEL, value(0.22, word)], "A", rule)
        assert result.status is not ResolutionStatus.RESOLVED, (word, rule.require_prefix)
