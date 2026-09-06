"""A DRB3/4/5 gene is taken from a second reader only when it reads a digit.

`ocr/drbx.py` repairs a final `S` to `5` because, over the corpus, `DRBS`
matches a DRB5-expecting DRB1 genotype 99.5% of the time. But `S` is also how a
printed `3` reads, and KI-026 measured the cost: rows resting on that repair
were wrong often enough that the row could certify no absence, which left the
whole row abstaining.

`scripts/drbx_reread.py` asks a second recognizer instead of guessing. These
tests pin the one rule that makes it safe: the reading counts only when the
digit it returns IS a digit. An `S` from the second engine is the same
ambiguity twice and settles nothing, and a row that settles nothing keeps
whatever the row rule decided.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from drbx_reread import _separate, genes_in  # noqa: E402


def test_a_named_gene_is_read() -> None:
    assert genes_in("DRB3") == ["DRB3"]
    assert genes_in("DRB4") == ["DRB4"]
    assert genes_in("DRB5") == ["DRB5"]


def test_a_pair_box_names_both_of_its_genes() -> None:
    """One printed box reading `DRB3/5` accounts for both haplotype slots."""
    assert genes_in("DRB3/5") == ["DRB3", "DRB5"]


def test_an_ambiguous_s_settles_nothing() -> None:
    """The whole point: `DRBS` is the question, not the answer."""
    assert genes_in("DRBS") is None
    assert genes_in("HLA-DRBS") is None


def test_an_empty_or_missing_reading_settles_nothing() -> None:
    assert genes_in("") is None
    assert genes_in("   ") is None
    assert genes_in(None) is None  # type: ignore[arg-type]


def test_a_gene_outside_the_printed_enumeration_is_refused() -> None:
    """DRB1 is a different locus and is never one of the three."""
    assert genes_in("DRB1") is None
    assert genes_in("DRB2") is None


def test_the_same_gene_read_twice_is_one_gene() -> None:
    """Two mentions in one box are one name, not a haplotype count."""
    assert genes_in("DRB3 DRB3") == ["DRB3"]


def test_more_than_two_genes_in_one_box_settles_nothing() -> None:
    """A box naming the whole enumeration is the header, not a result."""
    assert genes_in("DRB3/4/5") is None


def test_a_leading_hla_prefix_does_not_hide_the_ambiguity() -> None:
    """Stripping `HLA` must not let the `S` through as a letter of the prefix."""
    assert genes_in("HLA-DRBS") is None
    assert genes_in("HLA-DRB3") == ["DRB3"]


def test_two_gene_boxes_standing_apart_are_two_haplotype_slots() -> None:
    """A row may print one gene twice, once per haplotype.

    Until the box of a duplicated gene was kept, only the first survived: on
    4,115 rows corpus-wide the second was discarded, and on 224 of them it
    carried the only S-for-5 repair, so this pass never saw the token it exists
    to settle.
    """
    left = [0.30, 0.50, 0.38, 0.52]
    right = [0.60, 0.50, 0.68, 0.52]
    assert _separate([("DRB5", right), ("DRB5", left)]) == [("DRB5", left), ("DRB5", right)]


def test_one_printed_token_boxed_twice_is_one_slot() -> None:
    """Two slots is what certifies the third gene ABSENT, so a detector that
    boxed one token twice would manufacture an absence."""
    box = [0.30, 0.50, 0.38, 0.52]
    overlapping = [0.32, 0.50, 0.40, 0.52]
    assert _separate([("DRB5", box), ("DRB5", overlapping)]) == [("DRB5", box)]


def test_boxes_come_back_in_reading_order() -> None:
    """Left to right, so the crops and their genes stay in step."""
    a = [0.10, 0.50, 0.18, 0.52]
    b = [0.40, 0.50, 0.48, 0.52]
    c = [0.70, 0.50, 0.78, 0.52]
    order = [field for field, _ in _separate([("DRB4", c), ("DRB3", a), ("DRB5", b)])]
    assert order == ["DRB3", "DRB5", "DRB4"]


def test_an_empty_row_separates_to_nothing() -> None:
    assert _separate([]) == []
