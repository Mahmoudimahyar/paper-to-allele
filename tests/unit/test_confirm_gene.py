"""A second engine over the DRB3/4/5 gene tokens.

The primary pipeline repairs `DRBS` to DRB5 on measured evidence, and the
labelled pack showed the residual is real: on 7 of 10 rows that called a gene
ABSENT beside a repaired token, the reviewer found that gene printed. The
confirmer reads the gene box again; the locus is never in question, only which
of the three printed names the box holds.
"""

from __future__ import annotations

import pytest

from kidneymatch.ocr.confirm import Confirmation, confirm_gene

pytestmark = pytest.mark.task("OCR-001")


@pytest.mark.parametrize(
    ("gene", "reading", "expected"),
    [
        ("DRB3", "DRB3", Confirmation.CONFIRMED),
        ("DRB4", "HLA-DRB4", Confirmation.CONFIRMED),
        ("DRB5", "DRBS", Confirmation.UNCONFIRMED),  # an S is the ambiguity itself
        ("DRB3", "DRBS", Confirmation.UNCONFIRMED),  # ...whichever gene was printed
        ("DRB4", "DRB3/S", Confirmation.UNCONFIRMED),
        ("DRB5", "DR85", Confirmation.CONFIRMED),  # B read as 8
        ("DRB3", "DRB3/4", Confirmation.CONFIRMED),  # a pair in one box names both
        ("DRB4", "DRB3/4", Confirmation.CONFIRMED),
        ("DRB5", "DRB3/4", Confirmation.CONTRADICTED),
        ("DRB3", "5/3", Confirmation.CONFIRMED),
        ("DRB3", "3", Confirmation.CONFIRMED),  # the crop IS the gene cell
        ("DRB3", "DRB3*01:01", Confirmation.CONFIRMED),  # an allele names its gene
        ("DRB5", "DRB3", Confirmation.CONTRADICTED),
        ("DRB4", "5", Confirmation.CONTRADICTED),
        ("DRB3", "DRB1", Confirmation.UNCONFIRMED),  # not a gene of this row
        ("DRB3", "34", Confirmation.UNCONFIRMED),  # not one digit standing alone
        ("DRB3", "", Confirmation.UNCONFIRMED),
        ("DRB3", "Donor", Confirmation.UNCONFIRMED),
    ],
)
def test_the_gene_verdicts(gene: str, reading: str, expected: Confirmation) -> None:
    assert confirm_gene(gene, reading) is expected


def test_the_gene_digit_is_never_taken_from_inside_a_number() -> None:
    """`103` is not DRB3 with noise in front of it: the first digit decides."""
    assert confirm_gene("DRB3", "103") is Confirmation.UNCONFIRMED
    assert confirm_gene("DRB3", "DRB13") is Confirmation.UNCONFIRMED
