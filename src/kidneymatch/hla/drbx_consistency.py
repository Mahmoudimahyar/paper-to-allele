"""Check the DRB1 row against the DRB3/4/5 row. An assertion, never an inference.

Two rows of the same form are read by different anchors, different relations and
different parts of the page. Biology links them: a DRB1 haplotype determines
which DRB3/4/5 gene, if any, sits beside it. So each row can check the other,
and that is the **only external check on locus binding available before the
golden corpus is labelled**.

Measured over 5,326 documents where both rows were read: 99.62% consistent, 20
flagged.

## The line this module does not cross

py-ard's `dr_blender` is a *blending* function. Its return value imputes a
merged DRBX genotype and collapses a homozygous pair to one copy. Calling it for
that value would be exactly the inference `HLA_VALIDATION_SPEC.md` forbids. Here
it is used only for **whether it raises**, and its return value is discarded.

Four things must never happen, and each has a test:

* **Never fill.** DRB1 `*11/*15` with an empty DRBX row does not yield DRB3 and
  DRB5 present. It yields a flag.
* **Never choose.** If the row is ambiguous between two genes, the constraint
  must not pick the one DRB1 predicts. That turns a coin flip into a confident
  wrong answer with a plausible audit trail.
* **Never correct a DRB1 digit.** The rows are independent evidence; a
  disagreement invalidates both until a human looks.
* **Never upgrade evidence state.** Consistency removes a document from the
  queue; it does not verify it.

`dr_blender` also only raises in ONE direction — a gene present that the DRB1
pair forbids. Verified: `dr_blender("DRB1*11+DRB1*13", "", "", "")` returns
silently though DRB3 was expected. The other direction is a set comparison here.
Measured, py-ard raised on 30 documents where the set comparison found 156.

Exceptions to the haplotype rule are real (`DRB4*01:03N` is a null allele, so a
DR7 haplotype can lack a functional DRB4), which is why every outcome is a
review flag and never a rejection.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pyard.blender import DRBXBlenderError, blender, expdrbx

GENES = ("DRB3", "DRB4", "DRB5")


class ConsistencyOutcome(StrEnum):
    CONSISTENT = "CONSISTENT"
    FORBIDDEN_GENE_PRESENT = "FORBIDDEN_GENE_PRESENT"
    EXPECTED_GENE_ABSENT = "EXPECTED_GENE_ABSENT"
    NOT_CHECKABLE = "NOT_CHECKABLE"


@dataclass(frozen=True, slots=True)
class ConsistencyResult:
    outcome: ConsistencyOutcome
    reason: str = ""

    @property
    def implied_genes(self) -> set[str]:
        """Always empty. The check states nothing; it only agrees or objects."""
        return set()

    @property
    def is_review_flag(self) -> bool:
        return self.outcome in (
            ConsistencyOutcome.FORBIDDEN_GENE_PRESENT,
            ConsistencyOutcome.EXPECTED_GENE_ABSENT,
        )

    @property
    def flags_drb1_row(self) -> bool:
        return self.is_review_flag

    @property
    def flags_drbx_row(self) -> bool:
        return self.is_review_flag

    @property
    def verifies(self) -> bool:
        """Never true. Agreement between two readings is not a laboratory result."""
        return False


def expected_drbx_genes(drb1_first_fields: list[str]) -> set[str]:
    """Which DRB3/4/5 genes this DRB1 pair implies, per the haplotype table.

    A first field py-ard does not recognise contributes nothing rather than a
    guess.
    """
    out: set[str] = set()
    for field in drb1_first_fields:
        try:
            symbol = expdrbx(field)
        except Exception:  # pragma: no cover - py-ard raises on malformed input
            continue
        if symbol and symbol != "0":
            out.add(f"DRB{symbol}")
    return out


def check_drb1_drbx(
    drb1_first_fields: list[str],
    present: set[str],
    absent: set[str],
) -> ConsistencyResult:
    """Compare the two rows. `present` and `absent` come from the grouped row.

    A gene that is neither present nor absent is UNKNOWN, and UNKNOWN is not
    checkable: the grouped row emits it when only one gene token was read, and
    treating it as absent would manufacture a contradiction out of a gap.
    """
    if len(drb1_first_fields) < 1:
        return ConsistencyResult(ConsistencyOutcome.NOT_CHECKABLE, "the DRB1 row was not read")
    if not present and not absent:
        return ConsistencyResult(
            ConsistencyOutcome.NOT_CHECKABLE, "the DRB3/4/5 row produced no call"
        )

    expected = expected_drbx_genes(drb1_first_fields)

    if len(drb1_first_fields) == 1:
        # Only ONE haplotype was read. Duplicating it into a homozygous pair
        # reported a gene that the UNREAD partner may perfectly well carry:
        # measured, 1,315 of 1,332 forbidden flags were single-value reads, 57%
        # of all such documents. ADR 0008's 99.62% was the two-value subset.
        #
        # What survives with one allele is the counting argument. Each haplotype
        # contributes at most one DRB3/4/5 gene, so two genes on the row means
        # BOTH haplotypes contributed, and one of them must be this allele's.
        own = expected_drbx_genes(drb1_first_fields)
        if len(present) >= 2 and not (own & present):
            carried = next(iter(own)) if own else "no DRBX gene"
            return ConsistencyResult(
                ConsistencyOutcome.FORBIDDEN_GENE_PRESENT,
                f"{len(present)} genes on the row need both haplotypes, but the one "
                f"DRB1 allele read carries {carried}",
            )
        missing = sorted(gene for gene in own if gene in absent)
        if missing:
            return ConsistencyResult(
                ConsistencyOutcome.EXPECTED_GENE_ABSENT,
                f"the DRB1 allele read expects {', '.join(missing)}, which the row calls absent",
            )
        return ConsistencyResult(ConsistencyOutcome.CONSISTENT)

    pair = list(drb1_first_fields)
    try:
        # Used ONLY for whether it raises. The return value is an imputation and
        # is deliberately not bound to a name.
        blender(
            f"DRB1*{pair[0]}+DRB1*{pair[1]}",
            drb3="DRB3*01:01" if "DRB3" in present else "",
            drb4="DRB4*01:01" if "DRB4" in present else "",
            drb5="DRB5*01:01" if "DRB5" in present else "",
        )
    except DRBXBlenderError as error:
        return ConsistencyResult(
            ConsistencyOutcome.FORBIDDEN_GENE_PRESENT,
            f"{error.found} on the row, but the DRB1 pair expects {error.expected}",
        )
    except Exception:  # pragma: no cover - malformed input is not a finding
        return ConsistencyResult(
            ConsistencyOutcome.NOT_CHECKABLE, "the DRB1 pair could not be evaluated"
        )

    missing = sorted(gene for gene in expected if gene in absent)
    if missing:
        return ConsistencyResult(
            ConsistencyOutcome.EXPECTED_GENE_ABSENT,
            f"the DRB1 pair expects {', '.join(missing)}, which the row calls absent",
        )
    return ConsistencyResult(ConsistencyOutcome.CONSISTENT)
