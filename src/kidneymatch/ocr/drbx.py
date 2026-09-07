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
import statistics
from dataclasses import dataclass, replace
from enum import StrEnum
from itertools import combinations
from typing import TYPE_CHECKING

from kidneymatch.documents.role import is_comparison_sheet
from kidneymatch.ocr.anchors import Box, ResolutionStatus, find_anchors, locus_anchors
from kidneymatch.ocr.glyphs import canonical_locus_label

if TYPE_CHECKING:  # `lattice` imports `geometry`, which imports this module.
    from kidneymatch.ocr.lattice import Lattice

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
STRICT_GROUPED_DRBX_HEADER = re.compile(
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

# W5, the damage the strict pattern above does not reach (route (c),
# 2026-09-06). 213 boxes corpus-wide match this and not the strict pattern; on
# 156 of the 162 measurable ones the box sits at exactly 1.00 DRB1 row pitch,
# which is what a header does and what nothing else on these pages does. Four
# widenings, each with its own measured shape, and one deliberate refusal:
#
# * the B slot reads as any LETTER or `?` or is lost entirely — `DRd3/4/5`,
#   `DR3/4/5`, `DR?3/4/5`, `HLA-DRA345`. The class is written out rather than
#   "any non-S glyph": a literal any-glyph class also admits digits, slashes
#   and brackets, which added 37 gated pages of which 35 had NO DRB1 label read
#   at all — the widest class buying yield exactly where corroboration is
#   weakest. `S` is excluded because `DRBS3/4/5` is the stem with its own
#   digit misread, not a B-slot substitution;
# * a separator read as `4` — `HLA-DRB3445`, `HLA-DRB344/5`;
# * the final 5 read as `3` — `HLA-DRB3/4/3`;
# * the HLA prefix read as `BLA`.
#
# NOT widened: a double separator with nothing in the 4 slot (`HLA-DRB3//5`).
# ADR 0008 Decision 4 refuses every partial enumeration, which is why the
# strict pattern already refuses `HLA-DRB3/4/`; accepting the same absence
# spelled with two separators would contradict the ADR and this pattern's own
# neighbouring branch. Reopening it is HA-011's, not a regex's.
#
# A box matched ONLY by this widening is not a header until the page's geometry
# corroborates it: see `find_grouped_headers`.
GROUPED_DRBX_HEADER = re.compile(
    r"^[\s\-–—.,:;'\"]*"  # leading punctuation and crop noise
    r"(?P<hla>[HIB]{0,3}L?A[\s\-–—]*)?"  # HLA- and its misreads, BLA among them
    # The B slot: any letter but S, a `?`, or nothing — plus the `8` and `$`
    # the strict pattern above already accepts, because this pattern must be a
    # SUPERSET of that one. Without them `HLA-DR83/4/5` and `DR$3/4/5` would be
    # headers to `drbx.py` and not to `glyphs.py`, and a box that is a header to
    # one and a locus label to the other is how an allele reaches three genes.
    r"DR(?:[A-RT-Za-z?8$])?\s*"
    r"3"
    r"(?:[\s/,.\-\\|'\"AMUV14]*4[\s/,.\-\\|'\"AMUV14]*"
    r"|(?(hla)[\s/,.\-\\|'\"1]*[AMUV][\s/,.\-\\|'\"AMUV14]*|(?!)))"
    r"[5S3]"  # the final 5 read as S, or as 3
    r"[\s*:;.,)\-]*$"
)

# The geometry that corroborates a widened header, all of it relative to the
# page's own DRB1 label (verifier fix 3, calibrated on the 14,359 pages that
# already have a header):
#
# * the header sits 0.6-1.3 label pitches below the DRB1 label, the same window
#   the token route uses. Real headers sit at 1.018 (p1 0.941, p99 1.095);
# * it stands in the label column, measured against the DRB1 LABEL rather than
#   against the page's median label x0 — 12,363 of 14,359 current headers pass
#   the DRB1-relative test, while a median-x0 column test rejects 12,120 of
#   them, because the dominant form centres its labels.
GROUPED_HEADER_ROW_RATIO = (0.6, 1.3)
GROUPED_HEADER_COLUMN_WIDTHS = 0.6
# The pitch is the median gap between adjacent locus labels standing in the
# label column, which needs at least two of them to exist at all.
MIN_COLUMN_LABELS = 2
LABEL_COLUMN_HEIGHTS = 1.0

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
# The row placed from the page's own geometry when no header was read at all.
# Distinct on purpose: `drbx_ink_pass.py` and `drbx_reread.py` select
# `rule_id='GROUPED_DRBX/v1'`, so neither touches these facts, and the whole
# group can be found and withdrawn by rule or by `source`.
TOKEN_ANCHORED_RULE_ID = "TOKEN_ANCHORED_DRBX/v1"

# The reason the header route gives when it read no header. The token route
# runs only where this is what the page holds, so the string is shared rather
# than spelled twice.
NO_GROUPED_HEADER_REASON = "no grouped DRB3/4/5 header on this document"


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


def _label_column_pitch(boxes: list[Box]) -> float | None:
    """The row pitch of this page's label column, from the labels themselves.

    Every box whose text names a locus is a label; the ones standing within a
    label height of their median `x0` are the label COLUMN, and the median gap
    between adjacent members of that column is the pitch of the printed rows.
    `None` when fewer than two labels stand in the column, because one label
    measures no gap and a pitch invented from a single box would place a row
    wherever the arithmetic landed.
    """
    labels = [box for _, box in locus_anchors(boxes)]
    if len(labels) < MIN_COLUMN_LABELS:
        return None
    unit = statistics.median(box.height for box in labels) or 1e-6
    column_x0 = statistics.median(box.x0 for box in labels)
    column = sorted(
        (box for box in labels if abs(box.x0 - column_x0) <= LABEL_COLUMN_HEIGHTS * unit),
        key=lambda box: box.centre_y,
    )
    if len(column) < MIN_COLUMN_LABELS:
        return None
    gaps = [b.centre_y - a.centre_y for a, b in zip(column, column[1:], strict=False)]
    pitch = statistics.median(gaps) if gaps else 0.0
    return pitch if pitch > 0 else None


def _geometry_corroborates_header(box: Box, boxes: list[Box]) -> bool:
    """Does the page's own layout put this box where its header belongs?

    Asked only of a box the WIDENED branch alone matches. The strict pattern
    reads the printed enumeration and needs no corroboration; the widening
    reads damage, and damage is where a box that is not a header gets in.
    """
    anchors = find_anchors(boxes, "DRB1")
    if len(anchors) != 1:
        return False
    drb1 = anchors[0]
    pitch = _label_column_pitch(boxes)
    if pitch is None:
        return False
    low, high = GROUPED_HEADER_ROW_RATIO
    if not low <= (box.centre_y - drb1.centre_y) / pitch <= high:
        return False
    return abs(box.x0 - drb1.x0) <= GROUPED_HEADER_COLUMN_WIDTHS * (drb1.x1 - drb1.x0)


def find_grouped_headers(boxes: list[Box]) -> list[Box]:
    """Every box whose whole text is a combined DRB3/4/5 header.

    A box the strict pattern reads is a header wherever it stands. A box only
    the damage-tolerant widening reads is a header only where the page's own
    geometry puts one (`_geometry_corroborates_header`).
    """
    found: list[Box] = []
    for box in boxes:
        text = (box.text or "").strip()
        if (
            STRICT_GROUPED_DRBX_HEADER.match(text)
            or GROUPED_DRBX_HEADER.match(text)
            and _geometry_corroborates_header(box, boxes)
        ):
            found.append(box)
    return found


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


def _named_symbols(text: str) -> list[str]:
    """The gene symbols this ONE box names: `3`, `4`, `5` or the misread `S`.

    Empty for anything that is not a gene name, a printed pair or an allele of
    one of these genes. The stem is strictly `DR[B8]`: a bare digit in the cell
    is never a gene, because no geometry says the digit names a locus rather
    than an allele fragment.
    """
    pair = DRBX_PAIR_TOKEN.match(text)
    if pair:
        # `DRB3/4` in one box names both genes: 333 documents print the pair
        # this way instead of in two boxes.
        return [pair.group("first").upper(), pair.group("second").upper()]
    # An allele names its gene as surely as a bare gene name does. It matched
    # neither branch before, so it was invisible to the count and its gene was
    # reported ABSENT.
    match = DRBX_GENE_TOKEN.match(text) or DRBX_ALLELE_TOKEN.match(text)
    return [match.group("gene").upper()] if match else []


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
        return _all(GeneCall.UNKNOWN, ResolutionStatus.UNKNOWN, NO_GROUPED_HEADER_REASON)

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
        for symbol in _named_symbols((box.text or "").strip()):
            repaired = symbol == "S"
            named.append((f"DRB{'5' if repaired else symbol}", box, repaired))

    if named and not STRICT_GROUPED_DRBX_HEADER.match((header.text or "").strip()):
        # The leak guard on a WIDENED header (verifier fix 4). The widening
        # reads a header the recognizer damaged, and on 6 of 159 such pages a
        # counted gene token sat nearer the DRB1 label's line than the header's
        # — 5.6x the 0.67% rate on pages whose header the strict pattern reads.
        # Two-token rows write ABSENT for the third gene, and the DRB1
        # concordance check cannot see this failure: a gene name derived from a
        # DRB1 allele agrees with DRB1 by construction.
        anchors = find_anchors(boxes, "DRB1")
        if len(anchors) == 1 and any(
            abs(box.centre_y - anchors[0].centre_y) < abs(box.centre_y - header.centre_y)
            for _, box, _ in named
        ):
            return _all(
                GeneCall.UNKNOWN,
                ResolutionStatus.REVIEW_REQUIRED,
                "the grouped header was read only by the damage-tolerant pattern and a gene "
                "token on its band lies nearer the DRB1 label's line than the header's",
                header=header,
                tokens=len(named),
            )

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


# --- the same row on a page whose header was never read ----------------------
#
# 9,207 documents hold no box the header pattern reaches, and all three genes
# UNKNOWN. On 578 of them a gene token still stands on the row the page's own
# geometry places one label pitch below the DRB1 label — and on 578 of 579
# accepted rows there IS a box in the label column, header-shaped on 534 of
# them (the header with its digits misread). What is missing is the READING of
# the enumeration, not the enumeration.
#
# ADR 0008 Decision 4 licenses reading a gene name from this row because the
# printed header fixes the admissible set. Here that header was not read, so
# the licence is thinner and the emission is cut down to match it:
#
# * **PRESENT only.** The counting argument that turns two tokens into an
#   ABSENT for the third gene rests on the enumeration having been read. It has
#   not been, so no absence is ever certified on this route — the other genes
#   stay UNKNOWN, which is the absence of a finding.
# * **No repair.** An `S` anywhere refuses the page. S-for-5 was measured
#   against the header's own digits, and those digits are what is missing.
# * **The strict stem only.** `DR[B8]`; the damage-tolerant stem belongs to the
#   header, which is a printed constant, not to a patient-varying value.
# * **The row must be the row.** The pitch comes from a second printed label,
#   the window is the one 20,107 true gene tokens were measured in, and the
#   page's own rulings can veto but never place the row on their own except in
#   the one adjacency case below.
#
# HA-011 holds the grammar question this route sharpens: whether a row that
# prints gene names without a readable header may be read at all. Until it is
# answered these facts carry their own `rule_id` and `source`, so the whole
# group can be withdrawn in one statement.

# G4. The row window, calibrated on 20,107 true gene tokens against their own
# header's pitch: p0.1 0.53, p1 0.68, p50 0.84, p99 1.07, p99.9 1.26. (0.6,
# 1.3) keeps 99.68% of them.
TOKEN_ROW_RATIO = (0.6, 1.3)
# G4. What a plausible one-row pitch is, in DRB1 label heights (p50 3.68). A
# DQB1 label outside it is not one row from DRB1: on ~200 no-header pages it
# sits BELOW DRB1 (-2 to -10 heights), which is a form whose row order is not
# the one measured here, and the row below DRB1 on it is not the grouped row.
TOKEN_PITCH_HEIGHTS = (1.5, 6.0)
# G6. How far right of the DRB1 label a box must start before it can be a
# VALUE rather than a fragment of the label column, in DRB1 label heights.
# True tokens sit 6.09h out at p1 and only 0.38% of them below 4h. At the 1.0h
# the proposal first proposed, a grouped header split by the recognizer at its
# spaces (`HLA-DRB3,` | `DRB4,` | `DRB5`) wrote DRB5 PRESENT on 316 pages, 145
# of them rows that printed no gene at all. At 4.0h: none, for one lost page.
TOKEN_COLUMN_GAP_HEIGHTS = 4.0
# G5. Two rows share a ruling when the gap between their ruled bands is under
# this many label heights: the grouped row's top ruling IS the DRB1 row's
# bottom one. This is the only thing that places the row when no pitch exists.
SHARED_RULING_HEIGHTS = 0.25
# G5. A ruled space this many label heights deep between the DRB1 label's band
# and the token's band is another printed row standing between them, whatever
# the arithmetic says.
INTERVENING_BAND_HEIGHTS = 2.0
# G10. At most one DRB3/4/5 gene per haplotype, so at most two on a row.
MAX_TOKEN_SYMBOLS = 2

TOKEN_PRESENT_REASON = (
    "no grouped header was read; the row was placed one label pitch below the DRB1 label "
    "and this gene is printed on it"
)
TOKEN_UNKNOWN_REASON = "no grouped header read; row placed one label pitch below DRB1"


class _Rulings(StrEnum):
    """What the page's printed rulings say about two boxes' rows."""

    SILENT = "SILENT"  # no lattice, or no band for one of them
    SAME_BAND = "SAME_BAND"  # the token is inside the DRB1 label's own row
    ADJACENT = "ADJACENT"  # the two bands share a ruling
    NEAR = "NEAR"  # a gap, but not one a printed row fits in
    APART = "APART"  # a ruled space of two label heights or more between them


@dataclass(frozen=True, slots=True)
class TokenAnchoredRow:
    """The outcome of trying to place the grouped row from the page's geometry.

    `facts` is `None` whenever any gate refused, which is the default: this
    route says nothing unless every gate was passed, and `reason` records which
    one stopped it so a pass can tally its refusals.
    """

    facts: dict[str, DrbxFact] | None
    reason: str


def _refused(reason: str) -> TokenAnchoredRow:
    return TokenAnchoredRow(None, reason)


def _lift(anchor: Box, box: Box, slope: float) -> float:
    """How far the printed row has fallen by the time it reaches this box."""
    return slope * (box.centre_x - anchor.centre_x)


def _shares_line(anchor: Box, box: Box, slope: float) -> bool:
    """Do these two boxes sit on one printed line, along the page's slope?"""
    lift = _lift(anchor, box, slope)
    top, bottom = box.y0 - lift, box.y1 - lift
    overlap = min(anchor.y1, bottom) - max(anchor.y0, top)
    shorter = min(anchor.height, max(bottom - top, 1e-6))
    return overlap / shorter >= ROW_OVERLAP


def _token_pitch(boxes: list[Box], drb1: Box, slope: float) -> tuple[float | None, str | None]:
    """The page's row pitch from a second printed label, or a refusal.

    A single DQB1 label is the measurement; when the page reads none, DPB1
    stands two rows from DRB1 and half that gap is one row. A DQB1 label that
    is not one plausible row from DRB1 REFUSES the page rather than falling
    through to DPB1: the fallback admitted 26 pages of a form whose row order
    differs and whose label column prints star-suffixed gene names, a layout
    nobody has measured (verifier fix 3).

    `(None, None)` means no pitch could be measured at all, which is not a
    refusal — the rulings may still place the row by adjacency.
    """
    low, high = TOKEN_PITCH_HEIGHTS
    height = drb1.height
    for locus, rows in (("DQB1", 1), ("DPB1", 2)):
        anchors = find_anchors(boxes, locus)
        if len(anchors) != 1:
            if anchors:
                # Two labels of the same locus: which row is a row is exactly
                # the ambiguity this pipeline refuses to paper over. No pitch.
                return None, None
            continue
        other = anchors[0]
        pitch = (drb1.centre_y - (other.centre_y - _lift(drb1, other, slope))) / rows
        if not low <= pitch / height <= high:
            return None, (
                f"the single {locus} label is not {rows} printed row(s) from DRB1; this page's "
                "row order is not the one this rule was measured on"
            )
        return pitch, None
    return None, None


def _ruling_verdict(lattice: Lattice | None, drb1: Box, box: Box, slope: float) -> _Rulings:
    """What the printed rulings say about the DRB1 label's row and this box's."""
    if lattice is None:
        return _Rulings.SILENT
    height = drb1.height
    band = lattice.row_band(drb1.centre_x, drb1.centre_y, height)
    other = lattice.row_band(box.centre_x, box.centre_y, height)
    if band is None or other is None:
        return _Rulings.SILENT
    lift = _lift(drb1, box, slope)
    if band.contains_y(box.centre_y - lift):
        return _Rulings.SAME_BAND
    gap = (other.top - lift) - band.bottom
    if abs(gap) <= SHARED_RULING_HEIGHTS * height:
        return _Rulings.ADJACENT
    if gap >= INTERVENING_BAND_HEIGHTS * height:
        return _Rulings.APART
    return _Rulings.NEAR


def resolve_token_anchored_drbx(
    boxes: list[Box],
    *,
    drb1_resolved: bool,
    row_slope: float = 0.0,
    lattice: Lattice | None = None,
) -> TokenAnchoredRow:
    """The grouped row placed from the page's own geometry, PRESENT only.

    Called only where `resolve_grouped_drbx` returned
    `NO_GROUPED_HEADER_REASON`. Twelve gates, each measured, each a way this
    could assert something untrue:

    * **G0** not a comparison sheet — a row cannot say whose gene it is;
    * **G1** no box matches `GROUPED_DRBX_HEADER`: the header route keeps first
      refusal, always;
    * **G2** exactly one DRB1 label, and the page's DRB1 fact RESOLVED. Load
      bearing, not decorative: 0 of 21,764 DRB1 value boxes on DRB1-RESOLVED
      pages fall in this window, and all 116 pages that have one are pages
      whose DRB1 the resolver refused — a DRB1 chain that walked into the
      grouped row;
    * **G3** no other locus label shares DRB1's printed line, or the labels are
      column headings and "one pitch below" is not a row of that table;
    * **G4** the pitch (`_token_pitch`) and the row window `TOKEN_ROW_RATIO`;
    * **G5** the rulings may veto (`_ruling_verdict`), and where no pitch
      exists they are the only thing that can place the row;
    * **G6** a gene-token-shaped box nearer than `TOKEN_COLUMN_GAP_HEIGHTS` to
      the label is a fragment of the label column: excluded from the count,
      never PRESENT;
    * **G7** every gene token ON THE PAGE must sit on the placed row, or the
      page belongs to another form and is refused entire;
    * **G8** the counted tokens share one printed line;
    * **G9** beats G6: a label-column box on the row that
      `glyphs.canonical_locus_label` NAMES (`DRB3`, `HLA-DRB3`) is a form that
      types these genes as standalone rows, and refuses the page. G6's
      exclusion is only for fragments that matcher does not name (`DRB3,`,
      `HLA-DRB3/4`);
    * **G10** at most two symbols, and any `S` refuses the page;
    * **G11** the strict `DR[B8]` stem only.
    """
    if is_comparison_sheet(boxes):
        return _refused("G0: donor and recipient on one sheet; a row cannot say whose gene it is")
    if find_grouped_headers(boxes):
        return _refused("G1: this page has a grouped header; the header route owns the row")
    if not drb1_resolved:
        return _refused("G2: the DRB1 row was not resolved on this page")
    anchors = find_anchors(boxes, "DRB1")
    if len(anchors) != 1:
        return _refused(f"G2: {len(anchors)} DRB1 labels; no single row to measure from")
    drb1 = anchors[0]
    height = drb1.height

    for _, other in locus_anchors(boxes):
        if other is not drb1 and _shares_line(drb1, other, row_slope):
            return _refused("G3: another locus label stands on DRB1's line; these are columns")

    pitch, refusal = _token_pitch(boxes, drb1, row_slope)
    if refusal is not None:
        return _refused(f"G4: {refusal}")
    if pitch is None and lattice is None:
        return _refused("G4: no second label to measure the row pitch from, and no rulings either")

    low, high = TOKEN_ROW_RATIO

    def on_the_row(box: Box) -> bool:
        verdict = _ruling_verdict(lattice, drb1, box, row_slope)
        if pitch is None:
            # No pitch: the printed rulings are the only evidence, and only
            # one shape of it counts — the grouped row's top ruling is the
            # DRB1 row's bottom one.
            return verdict is _Rulings.ADJACENT
        if verdict in (_Rulings.SAME_BAND, _Rulings.APART):
            return False
        ratio = (box.centre_y - _lift(drb1, box, row_slope) - drb1.centre_y) / pitch
        return low <= ratio <= high

    gate = drb1.x1 + TOKEN_COLUMN_GAP_HEIGHTS * height
    counted: list[tuple[Box, list[str]]] = []
    for box in boxes:
        if box is drb1:
            continue
        text = (box.text or "").strip()
        symbols = _named_symbols(text)
        on_row = on_the_row(box)
        if symbols and not on_row:
            # G7. A gene token somewhere else on the page is another form's
            # row, and ignoring it cost +1 label contradiction when measured.
            return _refused("G7: a gene token on this page is not on the placed row")
        if not on_row:
            continue
        if box.x0 >= gate:
            if symbols:
                counted.append((box, symbols))
            continue
        # On the row and in the LABEL column. G9 beats G6 here: a box the
        # label matcher NAMES is a form that types these genes as standalone
        # rows and refuses the page; a fragment it does not name (`DRB3,`,
        # `HLA-DRB3/4`) is a piece of the header and is merely skipped.
        if canonical_locus_label(text) is not None:
            return _refused("G9: a locus label stands in the label column of the placed row")

    if not counted:
        return _refused("G6: no gene token in this row's value columns")

    named: list[tuple[str, Box]] = []
    for box, symbols in counted:
        for symbol in symbols:
            if symbol == "S":
                # No S-for-5 repair here. The three measurements that license
                # it are all about the header's own digits, and this page's
                # header was never read.
                return _refused("G10: a gene token reads S; no repair is licensed on this route")
            named.append((f"DRB{symbol}", box))
    if len(named) > MAX_TOKEN_SYMBOLS:
        return _refused(f"G10: {len(named)} gene symbols on one row; at most two are possible")
    for first, second in combinations([box for box, _ in counted], 2):
        if not _shares_line(first, second, row_slope):
            return _refused("G8: the accepted tokens do not share one printed line")

    facts: dict[str, DrbxFact] = {}
    for gene, box in named:
        if gene in facts:
            # The same gene printed once per haplotype. Copy number is still
            # not emitted; the second BOX is kept so every pass that re-reads a
            # gene box can see it.
            first_fact = facts[gene]
            facts[gene] = replace(first_fact, gene_boxes=(*first_fact.gene_boxes, box))
            continue
        facts[gene] = DrbxFact(
            gene=gene,
            call=GeneCall.PRESENT,
            status=ResolutionStatus.RESOLVED,
            # The DRB1 label is the row's reference, and it is the anchor only
            # on the facts that also carry a value box. On the UNKNOWN genes it
            # would make `review_pack.cell_crop_box` show a reviewer the DRB1
            # row for a cell about DRB4 (verifier fix 4).
            header_box=drb1,
            gene_box=box,
            raw_text=(box.text or "").strip(),
            repaired=False,
            gene_boxes=(box,),
            tokens_on_row=len(named),
            reason=TOKEN_PRESENT_REASON,
            rule_id=TOKEN_ANCHORED_RULE_ID,
        )
    for gene in GENES:
        if gene not in facts:
            facts[gene] = DrbxFact(
                gene=gene,
                call=GeneCall.UNKNOWN,
                status=ResolutionStatus.UNKNOWN,
                header_box=None,
                tokens_on_row=len(named),
                reason=TOKEN_UNKNOWN_REASON,
                rule_id=TOKEN_ANCHORED_RULE_ID,
            )
    return TokenAnchoredRow({gene: facts[gene] for gene in GENES}, "the row was placed")
