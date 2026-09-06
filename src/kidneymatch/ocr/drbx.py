"""The combined `DRB3/4/5` row: three separate genes printed as one row.

`HLA_VALIDATION_SPEC.md` section 7 forbids treating `DRB3/4/5` as one locus —
binding one value to it would assign the same allele to three genes. The row
therefore needs its own anchor type, which is what this is.

## What the row actually contains

**Presence typing, not alleles.** Measured over 23,485 true originals: the box
at rank 0 to the right of the header is a gene NAME 95.7% of the time and an
allele 0.1% (11 boxes corpus-wide). Reading DOWNWARD from the header — what the
previous rule did — lands on the next row's locus label in 88.9% of documents
that have a box there (`HLA-DPBI` alone 9,130 times). That rule resolved 3
documents in the whole corpus; this one resolves 12,488, emitting three
per-gene facts each.

## Why reading the gene from the token is licensed here

`OCR_SPEC.md` section 2 forbids inferring which field a value belongs to from
what the value says. That is not what happens here:

1. **Geometry alone fixes the field.** The header box fixes the row; the row
   band and the rightward relation fix the value cells. Nothing about the
   token's text decides which cell is being read.
2. **The cell's grammar is a closed, printed enumeration.** The header prints
   the admissible set `{DRB3, DRB4, DRB5}`. That is why all three digits are
   mandatory in the header pattern and why every partial header is refused: the
   moment the enumeration is not printed, the licence is gone.
3. A gene name here is the patient-varying content of a cell, exactly as
   `A*02:01` is in the HLA-A cell. The form does presence typing, so the value
   is spelled as a name.
4. The failure this rule guards against — a value migrating to the wrong locus
   — cannot occur, because one row emits three independent per-gene facts and a
   token outside the alphabet binds nothing at all.

## The counting rule, and why ABSENT is gated

A person carries at most one DRB3/4/5 gene per haplotype, so at most two across
both. Measured at the chosen row band, **zero** documents print more than two
gene tokens. The emission is gated on how many were read, because "the row
printed one gene" and "the row printed one gene and the other slot is empty"
are not the same claim:

| tokens | emission | measured discordance against the DRB1 row |
|---|---|---|
| 2 | named genes PRESENT, the third ABSENT | 0.09% |
| 2, one repaired S | named PRESENT, others REVIEW | 7 of 10 labelled "absent" genes were printed |
| 1 | that gene PRESENT, the other two UNKNOWN | calling them ABSENT is wrong 5.90% of the time |
| 0 | all three UNKNOWN, never ABSENT | 63.2% of empty rows have a DRB1 that expects a gene |
| >2 | all three REVIEW_REQUIRED | never truncate to the first two |

## `DRBS` is `DRB5`

Three independent measurements, none circular. In the header's own digits —
which must be 3, 4, 5 — `S` is a misread of `5` in 5.40% of headers, of `3` in
0.26%, and of `4` never. Documents whose header misread its own final `5` show
a halved `5` share and a nearly doubled `S` share among gene tokens while the
`3` and `4` shares are unchanged, so `S` is drawn from the `5` pool. And `DRBS`
rows match a DRB1 genotype expecting DRB5 in 99.5% of cases against a 54.1%
base rate for DRB3. The residual error attributable to the repair is at most
0.43 percentage points; abstaining instead would cost 13.7% of the corpus.

The repair is bounded: final character only, `S` to `5` only, only inside a cell
already fixed by the header. `DRBS` in the header's own FIRST position is NOT
repaired to `3` — there is no comparable evidence base.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import StrEnum

from kidneymatch.ocr.anchors import Box, ResolutionStatus

GENES = ("DRB3", "DRB4", "DRB5")

# The header. Case-sensitive on purpose: lowercase `s`/`a` are not in the
# measured confusion set for this cell, and ignoring case would widen the accept
# surface for nothing. The digits 3 and [5S] in that order are mandatory, and
# the 4 too unless an HLA prefix and a slash-misread letter stand in for it —
# they ARE the printed enumeration that licenses reading a gene name from the
# row. v2 (2026-09-05): measured on the 9,648 documents without a recognised
# header, the B slot reads R (88), E (29), $ (38), H (14) or D (12) and the
# slashes read as 1 (98); 605 documents gain a header, 505 of them with a gene
# token then on the band. `glyphs._GROUPED_DRBX` mirrors this pattern.
GROUPED_DRBX_HEADER = re.compile(
    r"^[\s\-–—.,:;'\"]*"  # leading punctuation and crop noise
    r"(?P<hla>[HI]{0,3}L?A[\s\-–—]*)?"  # HLA- and its misreads: ILA, IILA, HILA, LA, A
    r"DR[B8RE$HD]\s*"  # B is read as 8, R, E, $, H, D — the stem's own letters never
    r"3"
    # The printed 4 with its separators (`/` is read as A M U V, and as 1) —
    # or, behind an HLA prefix only, a slash-misread letter standing where the
    # 4 was: `HLA-DRB3AS`, `HLA-DRB3A/S` (99 documents). Without the prefix a
    # 4-less token is refused: `DRB3/5` is a pair of gene names on the row.
    r"(?:[\s/,.\-\\|'\"AMUV1]*4[\s/,.\-\\|'\"AMUV1]*"
    r"|(?(hla)[\s/,.\-\\|'\"1]*[AMUV][\s/,.\-\\|'\"AMUV1]*|(?!)))"
    r"[5S]"  # the final 5 read as S
    r"[\s*:;.,)\-]*$"
)

# A gene NAME: the row's value under presence typing. The literal `DR[B8]`
# prefix is required — a bare `3`, `4` or `5` in that cell is never a gene,
# because no geometry says the digit names a locus rather than an allele
# fragment.
DRBX_GENE_TOKEN = re.compile(
    r"^(?:HLA[\s\-]*)?DR[B8](?P<gene>[345S])[\s*+°\"'`]*[.,:;)]?$", re.IGNORECASE
)

# An allele for one of these genes. Essentially does not occur (16 boxes
# corpus-wide), but a DAMAGED one on a presence row means the row was misread.
DRBX_ALLELE_TOKEN = re.compile(
    r"^(?:HLA[\s\-]*)?DR[B8](?P<gene>[345S])\s*[*+°\-\"'`~^]\s*"
    r"(?P<first>[0-9OoIilLSs]{2,3})(?:\s*:\s*(?P<second>[0-9OoIilLSs]{2,3}))?"
    r"[NLSQ]?[.,;)]?$",
    re.IGNORECASE,
)

# A gene token shares the header's printed LINE. Measured centre-to-centre
# distance was used first and cuts through the real distribution: a third token
# on the same line fell just outside it, so the row emitted ABSENT where it must
# REVIEW (7 documents), and 1,036 documents lost a token that was on the line.
# Vertical overlap is what `anchors.py` uses and what actually identifies a row.
ROW_OVERLAP = 0.2

# The band a box joins on its own: centre within one header height, which is the
# knee of the measured sweep. Boxes further out join only by overlapping a box
# already on the line (see `_row_band`).
ROW_BAND_CENTRE = 1.0

# The outer bound on that chain, so following the line cannot reach the next
# printed row. Rows are 3.8 header-heights apart on the dominant form.
ROW_BAND = 1.5

# A pair of genes printed in one box instead of two: 333 documents.
DRBX_PAIR_TOKEN = re.compile(
    r"^(?:HLA[\s\-]*)?DR[B8](?P<first>[345S])\s*[/,]\s*(?:DR[B8])?(?P<second>[345S])"
    r"[\s*+°\"'`]*[.,:;)]?$",
    re.IGNORECASE,
)

RULE_ID = "GROUPED_DRBX/v1"


class GeneCall(StrEnum):
    """What this row says about one gene.

    `ABSENT` is a positive finding — the row accounted for both haplotypes and
    this gene was not among them. `UNKNOWN` is the absence of a finding. They
    must never be merged: `AGENTS.md` requires a missing value to stay UNKNOWN
    rather than becoming a zero mismatch downstream.
    """

    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class DrbxFact:
    """One gene's outcome, with provenance to the box that named it."""

    gene: str
    call: GeneCall
    status: ResolutionStatus
    header_box: Box | None = None
    gene_box: Box | None = None
    raw_text: str | None = None
    repaired: bool = False
    # Every box on the row that named THIS gene, `gene_box` first. A row can
    # print one gene twice, once per haplotype, and until this existed the
    # second box was discarded: 4,115 rows corpus-wide, and on 224 of them the
    # discarded box was the only one carrying the S-for-5 repair, so the
    # re-read pass never saw it and the row could certify nothing.
    gene_boxes: tuple[Box, ...] = ()
    tokens_on_row: int = 0
    reason: str = ""
    rule_id: str = RULE_ID


def _all(
    call: GeneCall,
    status: ResolutionStatus,
    reason: str,
    header: Box | None = None,
    tokens: int = 0,
) -> dict[str, DrbxFact]:
    return {
        gene: DrbxFact(
            gene=gene,
            call=call,
            status=status,
            header_box=header,
            reason=reason,
            tokens_on_row=tokens,
        )
        for gene in GENES
    }


def find_grouped_headers(boxes: list[Box]) -> list[Box]:
    """Every box whose whole text is a combined DRB3/4/5 header."""
    return [b for b in boxes if GROUPED_DRBX_HEADER.match((b.text or "").strip())]


def _row_band(boxes: list[Box], header: Box) -> list[Box]:
    """Boxes on the header's row, to its right, in reading order.

    There is deliberately no maximum gap: the second gene column sits a median
    33 header-heights away, far past any distance limit that would be safe
    elsewhere. The row band is what bounds this rule.
    """
    outer = ROW_BAND * header.height

    def overlaps(a: Box, b: Box) -> bool:
        shared = min(a.y1, b.y1) - max(a.y0, b.y0)
        shorter = min(max(a.y1 - a.y0, 1e-6), max(b.y1 - b.y0, 1e-6))
        return shared / shorter >= ROW_OVERLAP

    candidates = [
        b
        for b in boxes
        if b is not header and b.x0 > header.x1 and abs(b.centre_y - header.centre_y) <= outer
    ]
    # A printed line is a CHAIN of overlapping boxes, not a set of boxes that
    # each overlap the header. Text drifts on a hand-held photograph, so by the
    # second value column a token may share no pixels with the header while
    # plainly sitting on its line — measured, such a token overlapped its in-band
    # neighbour by 0.70-0.75 while lying 1.18 header-heights from the centre.
    # Testing only against the header dropped it, and the row then reported its
    # gene ABSENT. The outer bound above still keeps the next printed row out.
    band = [
        b
        for b in candidates
        if overlaps(header, b)
        or abs(b.centre_y - header.centre_y) <= ROW_BAND_CENTRE * header.height
    ]
    changed = True
    while changed:
        changed = False
        for b in candidates:
            if any(b is seen for seen in band):
                continue
            if any(overlaps(b, seen) for seen in band):
                band.append(b)
                changed = True
    return sorted(band, key=lambda b: b.x0)


def _digits_damaged(text: str) -> bool:
    match = DRBX_ALLELE_TOKEN.match(text)
    if not match:
        return False
    fields = (match.group("first") or "") + (match.group("second") or "")
    return not fields.isdigit()


def resolve_grouped_drbx(boxes: list[Box]) -> dict[str, DrbxFact]:
    """Read the combined DRB3/4/5 row into one fact per gene."""
    headers = find_grouped_headers(boxes)

    if not headers:
        # The form may type these genes as three standalone rows instead. No
        # header is absence of evidence about the layout, never evidence that
        # the patient lacks the genes.
        return _all(
            GeneCall.UNKNOWN,
            ResolutionStatus.UNKNOWN,
            "no grouped DRB3/4/5 header on this document",
        )

    if len(headers) > 1:
        return _all(
            GeneCall.UNKNOWN,
            ResolutionStatus.REVIEW_REQUIRED,
            f"{len(headers)} grouped headers; cannot decide which row owns the value",
            header=headers[0],
        )

    header = headers[0]
    band = _row_band(boxes, header)

    damaged = [b for b in band if _digits_damaged((b.text or "").strip())]
    if damaged:
        return _all(
            GeneCall.UNKNOWN,
            ResolutionStatus.REVIEW_REQUIRED,
            "an allele on this presence row has damaged digits",
            header=header,
            tokens=len(band),
        )

    named: list[tuple[str, Box, bool]] = []
    for box in band:
        text = (box.text or "").strip()
        symbols: list[str] = []
        pair = DRBX_PAIR_TOKEN.match(text)
        if pair:
            # `DRB3/4` in one box names both genes: 333 documents print the pair
            # this way instead of in two boxes.
            symbols = [pair.group("first").upper(), pair.group("second").upper()]
        else:
            match = DRBX_GENE_TOKEN.match(text) or DRBX_ALLELE_TOKEN.match(text)
            # An allele names its gene as surely as a bare gene name does. It
            # matched neither branch before, so it was invisible to the count and
            # its gene was reported ABSENT.
            if match:
                symbols = [match.group("gene").upper()]
        for symbol in symbols:
            repaired = symbol == "S"
            named.append((f"DRB{'5' if repaired else symbol}", box, repaired))

    if len(named) > 2:
        # Biologically impossible: at most one DRBX gene per haplotype. Zero
        # documents reach this state, so reaching it means an assumption broke.
        return _all(
            GeneCall.UNKNOWN,
            ResolutionStatus.REVIEW_REQUIRED,
            f"{len(named)} DRBX gene tokens on one row; at most two are possible",
            header=header,
            tokens=len(named),
        )

    if not named:
        # One policy across the codebase: a printed label whose cell we could
        # not read is a failure a human must see, not an UNKNOWN. `anchors.py`
        # already said so, and 63.2% of empty grouped rows have a DRB1 genotype
        # that expects at least one gene, so this is a read failure far more
        # often than a true triple negative. The CALL stays UNKNOWN — nothing is
        # claimed about the genes — while the STATUS asks for a human.
        return _all(
            GeneCall.UNKNOWN,
            ResolutionStatus.REVIEW_REQUIRED,
            "header present but no gene token was read on its row",
            header=header,
            tokens=0,
        )

    # Both haplotype slots are only accounted for when two tokens were read.
    # With one, the second column is far more often unread than empty.
    others = GeneCall.ABSENT if len(named) == 2 else GeneCall.UNKNOWN
    others_status = ResolutionStatus.RESOLVED if len(named) == 2 else ResolutionStatus.UNKNOWN
    others_reason = (
        "both haplotypes accounted for by two gene tokens"
        if len(named) == 2
        else "only one gene token read; the second column is unread or empty"
    )
    if len(named) == 2 and any(repaired for _, _, repaired in named):
        # A slot that rests on the S-for-5 repair does not account for a
        # haplotype. The repair names DRB5 reliably (5 of 6 labelled PRESENT
        # calls stood), but an S is also how a final 3 reads: on the labelled
        # pack the reviewer found a gene printed that such a row had called
        # ABSENT on 7 of 10 cells — `DRBS DRBS` was `DRB3 DRB5`, `DRBS/S` was
        # `DRB3/5`. The named genes stay PRESENT; the others are a question.
        others = GeneCall.UNKNOWN
        others_status = ResolutionStatus.REVIEW_REQUIRED
        others_reason = (
            "a slot on this row rests on an S read as 5; the other genes' absence "
            "is not certified (7 of 10 such labelled cells printed the gene)"
        )

    facts: dict[str, DrbxFact] = {}
    for gene, box, repaired in named:
        if gene in facts:
            # A duplicated gene means both haplotypes carry it. Copy number is
            # still not emitted — it would be derived from a correlation rather
            # than from ground truth — but the second BOX is kept now. It is a
            # printed token like any other, and discarding it hid it from every
            # pass that re-reads a gene box.
            first = facts[gene]
            facts[gene] = replace(
                first,
                gene_boxes=(*first.gene_boxes, box),
                repaired=first.repaired or repaired,
            )
            continue
        facts[gene] = DrbxFact(
            gene=gene,
            call=GeneCall.PRESENT,
            status=ResolutionStatus.RESOLVED,
            header_box=header,
            gene_box=box,
            raw_text=(box.text or "").strip(),
            repaired=repaired,
            gene_boxes=(box,),
            tokens_on_row=len(named),
        )

    for gene in GENES:
        if gene not in facts:
            facts[gene] = DrbxFact(
                gene=gene,
                call=others,
                status=others_status,
                header_box=header,
                tokens_on_row=len(named),
                reason=others_reason,
            )

    return {gene: facts[gene] for gene in GENES}
