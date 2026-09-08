"""How a mismatch is counted, and the refusals that make the count honest.

`MATCH-HLA-001`. Policy: `docs/clinical/MATCHING_POLICY_V2.md` section 3.

Three rules carry the whole module, and each exists because getting it wrong is
clinically meaningful rather than merely untidy.

**The count is directional.** A kidney recipient's immune system responds to
antigens on the graft that it has not seen, so the count is the number of the
DONOR's distinct alleles the RECIPIENT does not have. The reverse direction is
graft versus host, which is a haematopoietic-transplant question. Both ranking
directions call this function with the recipient in the recipient argument; the
arguments are never swapped to serve the other direction.

**Homozygosity is a property of the comparison, not of a profile.** The count is
over DISTINCT donor alleles, so a donor carrying one value twice contributes at
most one mismatch without any special case. Whether two stored values collapse
to one depends on the depth they are compared at, which depends on the other
side's typing, so zygosity can never be cached on a profile.

**One allele read is not homozygosity.** `gold_fact.second_allele` is a status
flag, `READ` or `UNREAD`, not a value. Measured (KI-015), 29 to 36 per cent of
resolved A/B/DRB1 cells carried a single value, far above any plausible
homozygosity rate: the second allele was usually printed just past the region
the reader covered. So a locus with one value read yields a RANGE, never a
point, and never a clean zero. Where a range has to decide something, the worse
end decides it: flattering a pair beyond what the data supports is the one
direction of error this system must not make.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

__all__ = [
    "LocusMismatch",
    "LocusTyping",
    "LocusValue",
    "MismatchStatus",
    "MismatchVector",
    "PresenceMismatch",
    "SCORED_LOCI",
    "mismatch_at_locus",
    "parse_locus_value",
]

#: The loci this policy scores. DQA1, DPA1 and DPB1 are carried for the
#: antibody gate but never scored (policy section 3.6).
SCORED_LOCI: tuple[str, ...] = ("A", "B", "C", "DRB1", "DQB1")

#: Genes compared at presence level only (`HLA_VALIDATION_SPEC` section 7).
PRESENCE_GENES: tuple[str, ...] = ("DRB3", "DRB4", "DRB5")

#: Allele tokens are separated by whitespace in `gold_fact.value`; measured
#: shapes are `A*02 A*11`, `DRB1*04 DRB1*11` and bare digit pairs `04 11`.
_TOKENS = re.compile(r"[,;/+]|\s+")

#: A trailing expression suffix (`N` not expressed, `Q` questionable, and the
#: rest of the IMGT set). It is part of the allele's identity and is never
#: stripped for comparison, but it is recognised so depth is computed correctly.
_SUFFIX = re.compile(r"[NQLSCA]$")


class LocusTyping(StrEnum):
    """How completely one side is typed at one locus."""

    BOTH = "BOTH"
    """Two allele values were read."""

    ONE = "ONE"
    """One value was read and the second is unknown. NOT homozygous."""

    ABSENT = "ABSENT"
    """The locus was not typed at all."""

    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    """The stored row contradicts itself and may not be used."""


class MismatchStatus(StrEnum):
    """What kind of answer a locus produced."""

    KNOWN = "KNOWN"
    RANGE = "RANGE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class LocusValue:
    """What one side has at one locus, as stored."""

    alleles: tuple[str, ...]
    typing: LocusTyping
    reason: str = ""

    def distinct_at(self, depth: int) -> frozenset[str]:
        """The distinct allele texts truncated to `depth` fields."""
        return frozenset(_truncate(a, depth) for a in self.alleles)

    @property
    def usable(self) -> bool:
        return self.typing in (LocusTyping.BOTH, LocusTyping.ONE) and bool(self.alleles)


@dataclass(frozen=True, slots=True)
class LocusMismatch:
    """The answer at one locus.

    `count` is set only when `status` is KNOWN. `lower` and `upper` are always
    set for KNOWN and RANGE, so a caller that needs a conservative number can
    read `upper` without branching.
    """

    status: MismatchStatus
    count: int | None = None
    lower: int | None = None
    upper: int | None = None
    compared_depth: int | None = None
    truncated: bool = False
    reason: str = ""

    @property
    def worst(self) -> int | None:
        """The conservative end: what the count could be at its worst."""
        return self.upper

    def __str__(self) -> str:
        if self.status is MismatchStatus.KNOWN:
            return str(self.count)
        if self.status is MismatchStatus.RANGE:
            return f"{self.lower}-{self.upper}"
        return "UNKNOWN"


@dataclass(frozen=True, slots=True)
class PresenceMismatch:
    """A DRB3/4/5 gene compared at presence level."""

    gene: str
    status: MismatchStatus
    conflict: bool = False
    reason: str = ""


@dataclass(frozen=True, slots=True)
class MismatchVector:
    """The sole interface between mismatch counting and ranking."""

    per_locus: dict[str, LocusMismatch]
    presence: tuple[PresenceMismatch, ...] = ()
    dq_mode: str = "DQB1_ONLY"
    notes: tuple[str, ...] = field(default=())

    def unknown_loci(self) -> tuple[str, ...]:
        unknown = [
            locus for locus, mm in self.per_locus.items() if mm.status is MismatchStatus.UNKNOWN
        ]
        unknown += [p.gene for p in self.presence if p.status is MismatchStatus.UNKNOWN]
        return tuple(sorted(unknown))

    def partial_loci(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                locus for locus, mm in self.per_locus.items() if mm.status is MismatchStatus.RANGE
            )
        )

    def presence_conflicts(self) -> int:
        return sum(1 for p in self.presence if p.conflict)


def _depth(allele: str) -> int:
    """Number of printed fields in an allele text.

    `A*02` is one field, `A*02:01` two. An expression suffix belongs to the last
    field and does not add one.
    """
    body = allele.split("*", 1)[-1]
    return len([part for part in body.split(":") if part])


def _truncate(allele: str, depth: int) -> str:
    """Truncate an allele text to `depth` fields, keeping any locus prefix.

    The expression suffix is dropped with the field it belongs to, and kept when
    that field survives: `A*24:02N` at depth 1 is `A*24`, at depth 2 unchanged.
    A suffix on a first field (`A*24N`) is preserved at depth 1, because it is
    part of that field's identity.
    """
    prefix, star, body = allele.partition("*")
    if not star:
        prefix, body = "", allele
    fields = [part for part in body.split(":") if part]
    kept = fields[:depth]
    if len(kept) < len(fields):
        # a deeper field was dropped, so any suffix it carried goes with it
        kept = [_SUFFIX.sub("", kept[-1]) if kept else ""] if len(kept) == 1 else kept
    joined = ":".join(kept)
    return f"{prefix}*{joined}" if star else joined


def _canonical_tokens(tokens: tuple[str, ...], locus: str) -> tuple[tuple[str, ...], str]:
    """Give every allele token its locus prefix, so stored shapes compare.

    The archive writes the same typing three ways: `DRB1*04 DRB1*11`, `A*02
    A*11`, and bare digit pairs `04 11` with no prefix at all (2,124 rows).
    Comparing the printed text directly makes an identical pair look maximally
    mismatched, which demotes the best pairs below the worst: a full DRB1 match
    stored bare against one stored prefixed reached KM-6, the exact inversion the
    KM re-cut exists to prevent.

    The prefix is written ON rather than stripped off, so the explanation keeps
    the printed identity. A token whose prefix disagrees with the row's locus is
    a locus-binding failure, not a formatting one, and is refused rather than
    rewritten.
    """
    if not locus:
        return tokens, ""
    canonical: list[str] = []
    for token in tokens:
        head, star, body = token.partition("*")
        if not star:
            canonical.append(f"{locus}*{token}")
            continue
        if head.upper() != locus.upper():
            return (), (
                f"a {locus} cell holds a value prefixed {head!r}; "
                "the locus is decided by geometry, not by the printed prefix"
            )
        canonical.append(f"{locus}*{body}")
    return tuple(canonical), ""


def parse_locus_value(
    raw: str | None,
    second_allele_flag: str | None,
    *,
    locus: str = "",
) -> LocusValue:
    """Turn a stored `gold_fact` row into a `LocusValue`.

    The allele count comes from the VALUE, never from the flag. 49 Gold rows
    carry `READ` while storing one allele; trusting the flag there would treat a
    half-typed locus as complete and miscount it. A disagreement is
    `REVIEW_REQUIRED`, which is neither a count nor a guess.
    """
    if raw is None or not raw.strip():
        return LocusValue((), LocusTyping.ABSENT, f"{locus or 'locus'} not typed")

    raw_tokens = tuple(t for t in _TOKENS.split(raw.strip()) if t)
    if not raw_tokens:
        return LocusValue((), LocusTyping.ABSENT, "no allele token in the stored value")
    if len(raw_tokens) > 2:
        return LocusValue(
            raw_tokens,
            LocusTyping.REVIEW_REQUIRED,
            f"{len(raw_tokens)} allele tokens stored at a diploid locus",
        )

    tokens, prefix_problem = _canonical_tokens(raw_tokens, locus)
    if prefix_problem:
        return LocusValue(raw_tokens, LocusTyping.REVIEW_REQUIRED, prefix_problem)

    flag = (second_allele_flag or "").strip().upper()
    if flag == "READ" and len(tokens) != 2:
        return LocusValue(
            tokens,
            LocusTyping.REVIEW_REQUIRED,
            "second_allele says READ but one allele is stored; the row contradicts itself",
        )
    if flag == "UNREAD" and len(tokens) == 2:
        return LocusValue(
            tokens,
            LocusTyping.REVIEW_REQUIRED,
            "second_allele says UNREAD but two alleles are stored; the row contradicts itself",
        )

    if len(tokens) == 2:
        return LocusValue(tokens, LocusTyping.BOTH)
    return LocusValue(
        tokens,
        LocusTyping.ONE,
        "one allele read; the second is unknown and is NOT assumed to repeat the first",
    )


def mismatch_at_locus(donor: LocusValue, recipient: LocusValue) -> LocusMismatch:
    """Host-versus-graft mismatch at one locus.

    Returns UNKNOWN when either side cannot be used, a RANGE when either side is
    partially typed, and a KNOWN count only when both sides carry both alleles.
    """
    for side, value in (("donor", donor), ("recipient", recipient)):
        if value.typing is LocusTyping.REVIEW_REQUIRED:
            return LocusMismatch(
                MismatchStatus.UNKNOWN,
                reason=f"{side}: {value.reason}",
            )
        if not value.usable:
            return LocusMismatch(
                MismatchStatus.UNKNOWN,
                reason=f"{side}: {value.reason or 'locus not typed'}",
            )

    depth = min(
        min(_depth(a) for a in donor.alleles),
        min(_depth(a) for a in recipient.alleles),
    )
    truncated = any(_depth(a) > depth for a in (*donor.alleles, *recipient.alleles))

    d = donor.distinct_at(depth)
    r = recipient.distinct_at(depth)
    known = len(d - r)

    if donor.typing is LocusTyping.BOTH and recipient.typing is LocusTyping.BOTH:
        return LocusMismatch(
            MismatchStatus.KNOWN,
            count=known,
            lower=known,
            upper=known,
            compared_depth=depth,
            truncated=truncated,
        )

    # Partial typing. The unread allele could be anything, so bound the count.
    lower, upper = known, known
    why = []
    if donor.typing is LocusTyping.ONE:
        # the donor's unread allele may be foreign, adding at most one
        upper += 1
        why.append("donor second allele not read")
    if recipient.typing is LocusTyping.ONE:
        # the recipient's unread allele may cover one foreign donor allele
        lower = max(0, lower - 1)
        why.append("recipient second allele not read")
    upper = min(2, upper)
    lower = min(lower, upper)
    return LocusMismatch(
        MismatchStatus.RANGE,
        lower=lower,
        upper=upper,
        compared_depth=depth,
        truncated=truncated,
        reason="; ".join(why),
    )
