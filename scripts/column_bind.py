#!/usr/bin/env python3
"""Bind one person's HLA off a comparison sheet, when only their column is filled.

`prefix_bind.py` refuses a comparison sheet outright, and says why: "two
patients on one page means a prefix cannot say whose value it is, and that is
the wrong-locus failure in its most dangerous form — a value bound to the
correct gene of the wrong person". That refusal is the operator's recorded
decision (`CV_RESEARCH_2026-09-05.md` s12), and 3,535 cells sit behind it.

It is right about a sheet that carries two typings. It is wrong about the 450
pages of ONE laboratory template, on which — measured — only one column is ever
filled on 419 of them. Such a page prints two headings and describes ONE
person, and the heading above the filled column is the only thing on the page
that says which. The operator instructed this session to resolve all eight
segments of the s18 loss; s12-b records the amendment, and the condition on it
is the SUBJECT-AGREEMENT GATE below.

## What decides what

* the **person** comes from geometry: which column of the printed table the
  values sit in, plus the document's own independent ROLE fact agreeing with
  the heading above that column. Two signals, and neither is trusted alone;
* the **locus** comes from the value's own printed prefix — the s12 exception,
  exactly as `prefix_bind.py` uses it, and fenced the same way: only where the
  page anchors no label for that locus.

Nothing here is keyed by subject. The page describes one person, so it writes
one fact set; a two-person page is refused (`column-bind-refused`), never
split. `docs/architecture/DATA_MODEL.md`'s `FieldClaim.subject_candidate_id`
anticipates subject-keyed claims, but today's `fact` table is keyed
`(sha256, field, extraction_version)` with no subject, and ENTITY-001's "a
conflicting blood group or role blocks a link rather than weakening it" is
written for one subject per document. Adding a second subject is a design
decision for a person (HA-022), not a thing this pass may assume.

## The gates, and the counterexample each one exists for

Every one of these was constructed and measured before it was written down; the
tests in `tests/contracts/test_column_binding.py` reproduce them.

* **the template's own loci only** — `{A, B, DRB1, DQB1}`. Rewriting every A
  prefix on the corpus to `C` bound 28 cells as C, 21 on pages a human has
  labelled: nothing in the row order or the vocabulary refuses a C token
  sitting between A/B and DRB1 on a form that never prints C. A token naming a
  locus outside the whitelist refuses the whole PAGE, not just the cell,
  because it is evidence the reading is wrong;
* **no repaired prefix.** The letters before the star must equal the locus
  exactly. `DOB1*03` reaches DQB1 through `canonical_locus_label`'s interior
  O->Q repair, which was justified on geometry measured UNDER ANCHORS; here
  there is no anchor and the prefix is the sole locus evidence. `Cw`, `8*` and
  lower case go the same way;
* **`*`, `'` and `"` only** as the star. `+` is the blood-group sign, and this
  page carries bare `A+`/`O-` tokens inside the column bands;
* **the band is a cliff, so the page falls off it.** Three pages carried a
  fully-qualified token OUTSIDE the 0.5-16 header-height band — two C tokens at
  16.0 and 16.3, invisible to the row-order gate that would have refused them
  at 15.9. ANY qualified token outside the band refuses the page;
* **the other column must be EMPTY, and emptiness is not "nothing parsed".**
  Rewriting the second column of the twelve real two-people pages into shapes
  the corpus actually produces — `*02,*24`, `'02,'24`, `02,24`, `*02:01,*24:02`,
  none of which `parse_allele_values` accepts — bound five of them. A box in
  the other column counts as content when it parses, carries a star variant
  beside a digit, or holds two digits at all;
* **...and a COLUMN is not a half-page.** That predicate is asked of the boxes
  reaching the value band left-aligned under the VACANT heading — the same test
  the bound values themselves must pass, `ALIGN` header heights, applied to a
  box's whole span rather than to its left edge. Asked instead of everything on
  the far side of the midline it fires on the `Frequency` column this template
  prints BETWEEN the two headings: 77 of 450 pages, against 20 for the column
  test. Mirroring the filled column into the vacant one still refuses 276 of
  276 bound pages, so nothing was given up for that;
* **...and it does not stop at the band's lower edge** (P2 fix 5b). A
  fully-qualified token below 16 header heights already refuses the page; an
  unqualified allele-shaped one did not, and 31 of the 241 pages an earlier
  build bound carried one in the column it had called empty. Below the table
  the two-digit clause is the wrong instrument — it matches every date and
  telephone number, on 217 of those 241 pages — so what is looked for there is
  the shape a typing has: something the parser reads, or a star before a digit;
* **every refusal is review work with a crop, and says which kind it is.** Six
  gates reach the queue and they do not all mean the same thing. 15 pages / 26
  cells are refused because the PAGE prints two subjects — a third role word,
  two columns of values, a typing in the vacant column — and carry
  `TWO_SUBJECT_REASON` under `rule_id='column/two-subjects'`. 25 pages / 53
  cells are refused because the vacant column is not blank and what is in it is
  a date, a frequency or an 11-digit identifier: those carry `CROWDED_REASON`
  under `rule_id='column/other-column-unread'`, because asserting a second
  subject over a reference number is a false statement about a patient's
  record. `review_pack` samples the two as separate strata;
* **a token that names a locus but is not strictly qualified TAINTS it.** A
  star-less `A24`, a repaired `DOB1*03`, a `DRB1+15`, or a bare `DRB1*` stub
  whose digits were never read: each is a value of that locus the pass cannot
  read, hidden from `MAX_VALUES`, and it withdraws the locus rather than being
  skipped past. `find_anchors` does not see `DRB1*` — the star stops it being a
  label — so without this the "geometry gets first refusal" fence has a hole in
  it;
* **the subject-agreement gate.** Sliding every token under the OTHER heading
  bound 333 pages with 272 flipped people when this gate was off, and four
  (unflipped) with it on. It is the whole wrong-person defence, and it is
  weaker than "independent" suggests: measured over the 276 binds it rests on
  `CAPTION_CLAIM` for 150 of them (54%), on the bare-role-word tier
  `FORM_FIELD_BARE` for 84 (30%), and on a strong printed field for 42 (15%),
  against a 4:276 real-world contradiction residue. So the ROLE fact's source
  is written into `rule_id` and named in the reason: each group can be
  withdrawn on its own, and the operator can ship the strong tier alone.

## When there is no independent role

The geometry can be perfect and the document still have no ROLE fact. Fifty
pages are in that state. They are NEVER resolved — the naming rests entirely on
the OCR of one English word, sliding the tokens under the other heading flips
it on every page it is tried on, and no page carries a Persian role word on
that row to corroborate it. Instead the cells
move from UNKNOWN "no anchor on this document" to REVIEW_REQUIRED with the
tokens boxed and the header box stored, under `column-named+role-unconfirmed`,
so a reviewer sees the crop the pipeline was previously showing them nothing
for. The reason deliberately does NOT name the role: `tools/hla_review.html`
prints it beside the Role select the reviewer is meant to answer independently.

## What it is worth

Every number here is from THIS code, `--dry-run`, against the live stores with
every connection forced read-only. The 450 sheets are fully accounted for:
276 + 50 + 15 + 25 + 84 = 450.

* **276 pages bind, 699 cells** — A 219, DRB1 216, DQB1 146, B 118. Applied to
  a copy of the database: 699 rows written, every one RESOLVED, every one
  UNKNOWN "no anchor on this document" beforehand, and no already-RESOLVED
  cell anywhere in the database changed;
* **50 pages / 108 cells named** for review with no value (A 39, DRB1 33,
  DQB1 24, B 12);
* **15 pages / 26 cells** refused as two subjects the page itself prints, and
  **25 pages / 53 cells** because the vacant column is not blank and this pass
  cannot read what is in it;
* **84 pages refused outright**, the largest groups being 31 for a value not
  aligned under its heading and 29 for a typing-shaped box below the band;
* **89 printed rows on 77 pages get no crop** because the second allele is
  printed without its own star — said in each cell's own reason, not left in
  this docstring;
* on the human labels (1,287 from four rounds, 774 of them judged), **616 to
  618 correct, 121 to 119 missed, 18 to 18 contradicted**, nothing lost. Both
  gains are a cell the pipeline had missed entirely, one A and one B.

B binds only because `glyphs.py` now parses the Bw4/Bw6 tail this template
prints after the B pair. That parser change on its own is provably inert on the
mainline: a full corpus extraction with it, compared by `refresh_facts.compare`
against a full corpus extraction without it, moves 0 RESOLVED cells on every
one of the eleven loci, swaps no value, and gains or drops no second allele.

## Where it runs

AFTER `prefix_bind.py` and `anchor_row_bind.py` — it answers only cells they
left as UNKNOWN "no anchor on this document", and it never touches a RESOLVED,
NOT_TESTED or already-reviewed row. Also after anything that writes a ROLE
fact (`caption_pass.py`, `role_repass.py`, a refresh): the role agreement is
the wrong-person defence, so `withdraw_stale` re-checks every column-bound cell
against the CURRENT role fact at the head of every run and takes back the ones
that no longer agree. Re-running this pass in the documented order is the
repair. `extract_facts.py`'s own comparison-sheet downgrade is untouched.

## What it is NOT

Not measured, and stated so the next reader does not assume otherwise: pixels
cannot certify the other column blank. A second column no engine boxed at ALL
is gated by ROLE agreement alone, and that agreement is 54% a caption claim.

Nor is `withdraw_stale` symmetric. A withdrawn cell keeps `source='column-bound'`
with status REVIEW_REQUIRED, so `unanchored()` will never offer it again and it
cannot be re-bound when the role fact recovers. That is a yield and repair
question rather than a safety one, and it is not answered here.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from extract_facts import frame_for, load_geometry, load_rulings  # noqa: E402
from page_ocr_bind import Document, slopes_for  # noqa: E402
from prefix_bind import page_boxes  # noqa: E402

from kidneymatch.documents.role import ColumnHeaderRow, Role, comparison_columns  # noqa: E402
from kidneymatch.hla.vocabulary import load_vocabulary  # noqa: E402
from kidneymatch.ocr.anchors import Box, find_anchors  # noqa: E402
from kidneymatch.ocr.glyphs import (  # noqa: E402
    _STAR_VARIANTS,
    AlleleValue,
    canonical_locus_label,
    parse_allele_values,
)

EV = "facts/v1"
LOCI = ("A", "B", "C", "DRB1", "DQA1", "DQB1", "DPA1", "DPB1")

SOURCE = "column-bound"
NAMED_SOURCE = "column-named+role-unconfirmed"
REFUSED_SOURCE = "column-bind-refused"

# The rows this template prints. A qualified token naming anything else refuses
# the page: on a form that never prints C, a `C*07` is a misread A, and the row
# order cannot see it because C sorts between B and DRB1.
TEMPLATE_LOCI = ("A", "B", "DRB1", "DQB1")
TEMPLATE_ORDER = {locus: i for i, locus in enumerate(TEMPLATE_LOCI)}

# Below the header row, in header heights. Bound tokens were measured at 1.0 to
# 13.4; the three pages carrying a qualified token outside it were the only
# place the measured wrong-locus signal escaped.
BAND = (0.5, 16.0)
# Values are left-aligned under their heading (median offset -0.37 header
# heights) against a header pitch of 11.1 to 51.8, so this separates the
# columns with room to spare.
ALIGN = 3.0
MAX_HEADER_ROWS = 3
MAX_VALUES = 2
# Two boxes are on one printed row when their centres, followed at the page's
# own slope, sit within this many box heights of each other — as `prefix_bind`.
ROW_TOLERANCE = 1.0

# The star, on this pass only. `+` is the blood-group sign and these pages print
# bare `A+`/`O-` tokens inside the column bands; one corpus value uses it as a
# star and is refused here rather than read.
STRICT_STARS = "*'\""

# The mainline string, reused verbatim so `review_pack`'s comparison_sheet
# handling and any query written against it keep matching.
TWO_SUBJECT_REASON = "this page prints donor and recipient columns for two subjects"
# ...and this is what the same refusal says when the page does NOT print that.
# The emptiness predicate is deliberately wider than the parser, so it also
# catches the form's own printing: an 11-digit identifier, a date, a frequency.
# 22 of the 40 pages refused for a non-empty column hold nothing shaped like a
# typing, and writing `TWO_SUBJECT_REASON` on them puts a claim about a
# patient's record into the medical review queue that the page does not
# support. They are still review work — the page bound nothing and a reviewer
# with the crop can settle it — under a reason that says what was seen.
CROWDED_REASON = (
    "the column that must be empty on this comparison sheet is not blank: a box there holds "
    "digits this pass cannot read as a typing, so it cannot tell a second person's values from "
    "the form's own printing"
)
NAMED_REASON = (
    "values printed under one header of a comparison table; the header word is boxed beside "
    "them and the other column holds nothing; no independent role reading confirms the person"
)
# Said on the cell, not left in a docstring: a reviewer looking at this page
# will see a printed row that the pipeline proposed nothing for, and the reason
# they are owed is why. `parse_allele_values` refuses `A*02,24` because it
# cannot tell a pair from one two-field allele, so the row is not boxed here
# and is not a proposal at all.
UNBOXED_ROW_CLAUSE = (
    "; {n} further printed row(s) in this column are not boxed here, because the second allele "
    "is printed without its own star and the parser will not guess between a pair and one "
    "two-field value"
)
WORK_REASON_PREFIX = "no anchor on this document"

# --- what counts as content in the column that must be empty ----------------
#
# `parse_allele_values` alone is not enough: the corpus produces `*02,*24`,
# `'02,'24`, `02,24` and `*02:01,*24:02`, none of which it accepts, and each of
# them is a second person's typing.
_STARRED = re.compile(rf"\s*[{re.escape(_STAR_VARIANTS)}]\s*[0-9A-Za-z]{{2,3}}")
_TWO_DIGITS = re.compile(r"\d.*\d")
_STAR_THEN_DIGIT = re.compile(r"[*\"'’`]\s*\d")

# A printed pair whose SECOND allele lost its star: `A*02,24`. The parser
# refuses it (`A*24,02` could as easily be one two-field allele), so the row is
# never boxed and never proposed — measured below, and said out loud in
# `NAMED_REASON` rather than left for the reviewer to notice.
_SECOND_STAR_MISSING = re.compile(
    rf"^\s*(?:HLA[\s\-_]*)?[A-Za-z][A-Za-z0-9]{{0,3}}\s*[{re.escape(_STAR_VARIANTS)}]"
    rf"\s*[0-9A-Za-z]{{2,3}}(?::[0-9A-Za-z]{{2,3}})?\s*[,.;/]\s*"
    rf"(?![{re.escape(_STAR_VARIANTS)}])[0-9]{{2,3}}\s*$"
)

# The letters before the star, as PRINTED. Compared against the locus the
# parser named, so that a repaired prefix cannot be the only locus evidence.
_RAW_PREFIX = re.compile(r"^\s*(?:HLA[\s\-_]*)?(?P<prefix>[A-Za-z][A-Za-z0-9]{0,3})\s*(?P<star>.)")
# `DRB1*` with no digits: `find_anchors` refuses it as a label (the star stops
# `canonical_locus_label`) and `parse_allele_values` refuses it as a value, so
# it is invisible to both fences while naming a locus out loud.
_LABEL_STUB = re.compile(
    rf"^\s*(?P<name>[^{re.escape(_STAR_VARIANTS)}]+)[{re.escape(_STAR_VARIANTS)}]\s*$"
)


def holds_a_value(text: str | None) -> bool:
    """Is there a typed value in this box, however badly the engines read it?

    Deliberately wider than the parser. This decides whether the OTHER column
    is empty, and a false "empty" binds a page that describes two people.
    """
    stripped = (text or "").strip()
    if not stripped:
        return False
    if parse_allele_values(stripped):
        return True
    if _STARRED.match(stripped):
        return True
    if _TWO_DIGITS.search(stripped):
        return True
    return bool(_STAR_THEN_DIGIT.search(stripped))


def could_be_a_typing(text: str | None) -> bool:
    """`holds_a_value` without its bare-two-digit clause, for BELOW the table.

    The band stops at 16 header heights and the bound rows end at 13.4, so
    everything this predicate sees is page furniture or a second table: dates,
    telephone numbers, laboratory reference numbers, a signature line. Measured
    on the 241 pages the pass bound before this gate existed, `holds_a_value`
    itself calls 217 of them non-empty — it is the right predicate INSIDE the
    band, where the only thing printed is the two columns, and the wrong one
    below it. What is left is the shape a second person's HLA typing has:
    something the parser reads as an allele, or a star followed by a digit.
    31 of those 241 pages carry one, and none of them binds now.
    """
    stripped = (text or "").strip()
    if not stripped:
        return False
    if parse_allele_values(stripped):
        return True
    return bool(_STAR_THEN_DIGIT.search(stripped))


def qualified(text: str | None) -> tuple[str, list[AlleleValue]] | None:
    """The locus this box states outright, or None.

    "Outright" is strict here in three ways the ordinary parser is not, because
    the printed prefix is the ONLY evidence of the gene on these pages: the
    letters must be the locus as printed, every star must be one of the three
    the laboratory actually prints, and every allele must carry its own.
    """
    stripped = (text or "").strip()
    values = parse_allele_values(stripped)
    if not values or len(values) > MAX_VALUES:
        return None
    locus = values[0].locus_prefix
    if locus is None or any(v.locus_prefix != locus for v in values):
        return None
    if any(v.separator_missing for v in values):
        return None
    if any(ch in _STAR_VARIANTS and ch not in STRICT_STARS for ch in stripped):
        return None
    printed = _RAW_PREFIX.match(stripped)
    if printed is None or printed.group("star") not in STRICT_STARS:
        return None
    if printed.group("prefix") != locus:
        return None  # a repaired prefix cannot be the only thing naming a gene
    return locus, values


def names_a_locus(text: str | None) -> str | None:
    """The locus a box mentions at all — parsed, repaired, or as a bare stub.

    Used to TAINT: a box naming a locus that `qualified` refuses is a value of
    that locus this pass cannot read, and reading the other two boxes on the
    row as a complete pair would be a lie about how many there were.
    """
    stripped = (text or "").strip()
    values = parse_allele_values(stripped)
    if values and values[0].locus_prefix:
        return values[0].locus_prefix
    stub = _LABEL_STUB.match(stripped)
    if stub:
        return canonical_locus_label(stub.group("name")) or canonical_locus_label(
            f"HLA-{stub.group('name')}"
        )
    return None


@dataclass(frozen=True, slots=True)
class Reading:
    """What this page says, before anything is written."""

    verdict: str  # BIND | NAME | REFUSE
    gate: str
    two_subject: bool = False
    # Does the PAGE state a second subject, or does this pass merely fail to
    # certify the column blank? A third role word and a second column of values
    # are the page's own printing; an 11-digit identifier crossing an empty
    # column is not, and the two must not be filed under the same reason.
    two_subject_printed: bool = False
    subject: Role = Role.UNKNOWN
    side: str = ""
    header: ColumnHeaderRow | None = None
    role_source: str | None = None
    claims: dict[str, list[Box]] = field(default_factory=dict)
    evidence: dict[str, list[Box]] = field(default_factory=dict)
    # Printed rows in the filled column that this pass does NOT box, because
    # the second allele lost its star and the parser will not guess between a
    # pair and one two-field value. Counted so `NAMED_REASON` can say so.
    second_star_missing: int = 0

    @property
    def anchor_box(self) -> Box | None:
        """The heading this cell hangs from, which is ONE word when there is one.

        `highlight()` draws and zooms to this box on the full image, so a
        rectangle spanning both headings would show the reviewer the whole
        table and tell them nothing about which column the value came from
        (P2 fix 4). A cell that names a subject stores that subject's heading;
        only a refusal that is ABOUT both columns — no subject was settled —
        stores the pair, because there the two columns are the finding.
        """
        if self.header is None:
            return None
        if self.subject in (Role.DONOR, Role.RECIPIENT):
            return self.header.header_for(self.subject)
        pair = (self.header.donor, self.header.recipient)
        return Box(
            x0=min(b.x0 for b in pair),
            y0=min(b.y0 for b in pair),
            x1=max(b.x1 for b in pair),
            y1=max(b.y1 for b in pair),
            text="",
        )


def _refuse(gate: str, *, two_subject: bool = False, **kw) -> Reading:
    return Reading("REFUSE", gate, two_subject=two_subject, **kw)


def _lifted_gap(box: Box, header: ColumnHeaderRow, slope: float) -> float:
    """How far below the header row a box sits, in header heights.

    Followed at the page's own slope: these are photographs, and a tilt of a
    degree turns the far end of a band into a different row.
    """
    centre_x = (header.donor.centre_x + header.recipient.centre_x) / 2
    lift = slope * (box.centre_x - centre_x)
    return (box.centre_y - lift - header.centre_y) / header.height


def _reaches_column(box: Box, heading: Box, height: float) -> bool:
    """Does this box's x-span reach the value band left-aligned under a heading?

    The same `ALIGN` tolerance the alignment gate applies to a value's left
    edge, applied instead to a box's whole span — so it answers "could this box
    contain something printed in that column", not "which column is it in".
    """
    return box.x0 <= heading.x0 + ALIGN * height and box.x1 >= heading.x0 - ALIGN * height


def _one_row(boxes: list[Box], slope: float) -> bool:
    first = boxes[0]
    for box in boxes[1:]:
        lift = slope * (box.centre_x - first.centre_x)
        if abs(box.centre_y - lift - first.centre_y) > ROW_TOLERANCE * max(
            first.height, box.height
        ):
            return False
    return True


def read_columns(
    boxes: list[Box],
    vocabulary,
    slope: float = 0.0,
    *,
    role: Role = Role.UNKNOWN,
    role_resolved: bool = False,
    role_source: str | None = None,
) -> Reading:
    """Read one person's alleles off a two-column sheet, or say why not.

    Pure: it touches no database and writes nothing. `run` calls it once per
    page and decides what that answer is worth.
    """
    headers = comparison_columns(boxes)
    if not headers:
        return _refuse("the page prints no donor and recipient header pair")
    if len(headers) > MAX_HEADER_ROWS:
        return _refuse("more than three header rows on this page")
    # First, and before anything about columns: a third role word means more
    # than two subjects, and no geometry here can say whose column is whose.
    if any(h.extra for h in headers):
        return _refuse(
            "more than two subjects on the header row",
            two_subject=True,
            two_subject_printed=True,
            header=headers[0],
            evidence=_by_locus(
                [b for b in boxes if qualified(b.text)]
                or [b for b in boxes if names_a_locus(b.text)]
            ),
        )

    strict = [(b, *q) for b in boxes if (q := qualified(b.text)) is not None]
    if not strict:
        return _no_qualified_token(boxes, headers, slope)

    topmost = min((b for b, _, _ in strict), key=lambda b: b.centre_y)
    above = [h for h in headers if _lifted_gap(topmost, h, slope) >= BAND[0]]
    if not above:
        return _refuse("no header row sits above the values")
    header = max(above, key=lambda h: h.centre_y)

    if not header.recipient_is_left:
        # 445 of 449 pages print Recipient left, Donor right. Without this the
        # four real pages whose independent role contradicts their column bind.
        return _refuse("the headings are not in this template's order", header=header)

    # The band edge is a cliff, so the PAGE falls off it, not the cell.
    outside = [b for b, _, _ in strict if not BAND[0] <= _lifted_gap(b, header, slope) <= BAND[1]]
    if outside:
        return _refuse("a fully qualified value lies outside the header's band", header=header)

    in_band = [b for b in boxes if BAND[0] <= _lifted_gap(b, header, slope) <= BAND[1]]
    # A box straddles when it reaches BOTH columns' value bands. That is the
    # only shape that can be two people's values merged into one OCR box, and
    # it is not what `x0 < midline < x1` asks: `midline` is halfway between the
    # two headings' LEFT edges, and on a `Recipient | Frequency | Donor |
    # Frequency` template that point lies inside the FREQUENCY column. Keyed on
    # it, this gate fired on 85 of 450 pages and 9 of them had a box reaching
    # both value bands; the other 76 were furniture crossing an empty column —
    # median width 13.7 header heights, 67 of 112 boxes "other text with two
    # digits", 10 an 11-digit identifier — and each was written into the
    # medical review queue as evidence of a second subject. The CONTENT
    # predicate is unchanged (P4 fix 1, verbatim); what changed is where a box
    # has to be before that predicate is asked about it. Nothing is dropped: a
    # box reaching the VACANT column's band only is judged by the emptiness
    # gate below, on the same band test, under a reason that is true; and none
    # of the nine reaching both is itself typing-shaped, so all nine are filed
    # under `column/other-column-unread` rather than as two subjects.
    straddling = [
        b
        for b in in_band
        if holds_a_value(b.text)
        and _reaches_column(b, header.donor, header.height)
        and _reaches_column(b, header.recipient, header.height)
    ]
    if straddling:
        return _refuse(
            "a value box reaches both columns",
            two_subject=True,
            two_subject_printed=any(could_be_a_typing(b.text) for b in straddling),
            header=header,
            evidence=_by_locus([b for b, _, _ in strict] + straddling),
        )

    sides = {header.role_at(b.x0) for b, _, _ in strict}
    if len(sides) > 1:
        return _refuse(
            "both columns hold values",
            two_subject=True,
            two_subject_printed=True,
            header=header,
            evidence=_by_locus([b for b, _, _ in strict]),
        )
    subject = next(iter(sides))
    filled = header.header_for(subject)
    vacant = header.header_for(Role.DONOR if subject is Role.RECIPIENT else Role.RECIPIENT)
    # "In the other column" is the SAME test the alignment gate applies to the
    # values this pass binds — reach the band left-aligned under that heading —
    # and not `role_at`, which splits the page in half at the midline and so
    # puts the whole `Frequency` column, and everything else printed between
    # the two headings, in one subject's column or the other. Judged by the
    # half-plane this gate fired on 77 of 450 pages once the midline straddle
    # gate stopped absorbing them, and it was the same false statement in a
    # different reason. `_reaches_column` is the WIDER of the two tests the
    # page's own values must pass: a box need only reach the band, not begin
    # inside it, so a second person's value boxed a little off its column is
    # still caught.
    other = [
        b for b in in_band if _reaches_column(b, vacant, header.height) and holds_a_value(b.text)
    ]
    if other:
        return _refuse(
            "the other column is not empty",
            two_subject=True,
            two_subject_printed=any(could_be_a_typing(b.text) for b in other),
            header=header,
            evidence=_by_locus([b for b, _, _ in strict] + other),
        )

    # ...and emptiness does not stop at the band's lower edge. A fully-qualified
    # token below it already refuses the page (the cliff, above); an UNQUALIFIED
    # allele-shaped one did not, and that is the same class the emptiness
    # predicate exists for. Measured: 31 of the 241 pages that bound before this
    # gate carry, in the column the pass called empty, a box below 16 header
    # heights that parses as an allele or prints a star before a digit. Each is
    # a candidate second person's typing, so the page is refused rather than
    # bound. It is refused, not filed as a two-subject page: at a median 30.5
    # header heights below the heading these are as often a date or a reference
    # number as a typing, and asserting a second subject over one would be the
    # same false statement the midline gate used to write.
    below_band = [
        b
        for b in boxes
        if _lifted_gap(b, header, slope) > BAND[1]
        and _reaches_column(b, vacant, header.height)
        and could_be_a_typing(b.text)
    ]
    if below_band:
        return _refuse(
            "the column that must be empty holds a typed value below the header's band",
            header=header,
            subject=subject,
        )

    if any(abs(b.x0 - filled.x0) > ALIGN * header.height for b, _, _ in strict):
        return _refuse("a value is not aligned under its heading", header=header)

    off_template = {locus for _, locus, _ in strict if locus not in TEMPLATE_LOCI}
    if off_template:
        return _refuse("a value names a locus this template does not print", header=header)

    for _, locus, values in strict:
        if not vocabulary.covers(locus) or any(
            not vocabulary.is_admissible(locus, v.first_field) for v in values
        ):
            # As `prefix_bind`: a claim the vocabulary refuses is evidence the
            # reading is wrong, and it taints the page rather than one cell.
            return _refuse("a value is not admissible for the locus it names", header=header)

    claims: dict[str, list[Box]] = defaultdict(list)
    counts: Counter[str] = Counter()
    for box, locus, values in strict:
        claims[locus].append(box)
        counts[locus] += len(values)

    side = "left" if filled.x0 < header.midline else "right"
    withdrawn = _withdraw(claims, counts, boxes, in_band, header, subject, slope)
    for locus in withdrawn:
        claims.pop(locus, None)
    if not claims:
        return _refuse("nothing survived the per-locus gates", header=header, subject=subject)

    if not _in_template_order(claims):
        return _refuse("the loci are not in this template's vertical order", header=header)

    unboxed = sum(
        1
        for b in in_band
        if header.role_at(b.x0) is subject and _SECOND_STAR_MISSING.match((b.text or "").strip())
    )

    if role_resolved and role is subject:
        return Reading(
            "BIND",
            "the column and the document's own role fact name the same person",
            subject=subject,
            side=side,
            header=header,
            role_source=role_source,
            claims=dict(claims),
            second_star_missing=unboxed,
        )
    if role_resolved:
        return _refuse(
            "the document's own role fact contradicts the filled column",
            header=header,
            subject=subject,
        )
    return Reading(
        "NAME",
        "no independent role reading confirms the person",
        subject=subject,
        side=side,
        header=header,
        claims=dict(claims),
        second_star_missing=unboxed,
    )


def _no_qualified_token(boxes: list[Box], headers: list[ColumnHeaderRow], slope: float) -> Reading:
    """No column is filled with anything this pass can read.

    Usually an unreadable page. Sometimes BOTH columns hold typed values that
    no engine resolved into an allele, which is a two-subject page and belongs
    in the queue with a crop like every other one.
    """
    # The LOWEST header pair: a page printing two of them prints the identity
    # block's first and the table's own second, and the table is what the
    # values sit under.
    header = headers[-1]
    in_band = [
        b
        for b in boxes
        if BAND[0] <= _lifted_gap(b, header, slope) <= BAND[1] and holds_a_value(b.text)
    ]
    sides = {header.role_at(b.x0) for b in in_band}
    if len(sides) > 1:
        return _refuse(
            "neither column holds a fully qualified value and both hold typed ones",
            two_subject=True,
            two_subject_printed=all(
                any(could_be_a_typing(b.text) for b in in_band if header.role_at(b.x0) is side)
                for side in sides
            ),
            header=header,
            evidence=_by_locus(in_band),
        )
    return _refuse("no fully qualified value on this page", header=header)


def _by_locus(boxes: list[Box]) -> dict[str, list[Box]]:
    """Group the evidence of a refusal under the fact rows it can be filed at.

    A refusal is addressed to a cell, and a cell is a locus. Boxes that name no
    locus ride along with every locus that IS named, because on a two-subject
    page the unreadable box is often the whole point.
    """
    named: dict[str, list[Box]] = defaultdict(list)
    loose: list[Box] = []
    for box in boxes:
        locus = names_a_locus(box.text)
        if locus in LOCI:
            named[locus].append(box)
        else:
            loose.append(box)
    return {locus: found + loose for locus, found in named.items()}


def _withdraw(
    claims: dict[str, list[Box]],
    counts: Counter[str],
    boxes: list[Box],
    in_band: list[Box],
    header: ColumnHeaderRow,
    subject: Role,
    slope: float,
) -> set[str]:
    """Every locus that must not be bound, and the reason is always the same:
    something on this page states that locus and this pass could not read it."""
    out: set[str] = set()
    claimed = {id(b) for found in claims.values() for b in found}
    for locus, found in claims.items():
        if counts[locus] > MAX_VALUES or not _one_row(found, slope):
            out.add(locus)
        if find_anchors(boxes, locus):
            out.add(locus)  # geometry gets first refusal, always
    # One locus per row: two genes on one printed band is a layout this pass
    # cannot tell from a misread prefix. Every box against every other, not the
    # first of each — a misread prefix puts the stray token wherever it likes,
    # and comparing only the topmost box misses it exactly when it matters.
    for locus, found in claims.items():
        for other, others in claims.items():
            if other == locus:
                continue
            if any(_one_row([mine, theirs], slope) for mine in found for theirs in others):
                out.add(locus)
                out.add(other)
    for box in in_band:
        if id(box) in claimed or header.role_at(box.x0) is not subject:
            continue
        named = names_a_locus(box.text)
        if named in claims:
            out.add(named)
    return out


def _in_template_order(claims: dict[str, list[Box]]) -> bool:
    ordered = sorted(claims.items(), key=lambda kv: min(b.centre_y for b in kv[1]))
    ranks = [TEMPLATE_ORDER[locus] for locus, _ in ordered]
    return all(a < b for a, b in zip(ranks, ranks[1:], strict=False))


# --- the database ----------------------------------------------------------


def comparison_sheets(con: sqlite3.Connection) -> set[str]:
    """Pages holding two people. Raises rather than returning an empty set.

    Every page this pass touches is one of them, so a query that cannot run
    must stop the pass, not silently hand it an empty corpus.
    """
    return {
        row[0]
        for row in con.execute(
            "SELECT sha256 FROM document WHERE extraction_version=? AND comparison_sheet=1",
            (EV,),
        )
    }


def unanchored(con: sqlite3.Connection) -> dict[str, list[str]]:
    """Loci a page did not resolve and for which it printed no label at all."""
    out: dict[str, list[str]] = defaultdict(list)
    placeholders = ",".join("?" * len(LOCI))
    for sha, field_name in con.execute(
        f"SELECT sha256, field FROM fact WHERE extraction_version=? AND field IN ({placeholders}) "
        f"AND status='UNKNOWN' AND reason LIKE '{WORK_REASON_PREFIX}%'",
        (EV, *LOCI),
    ):
        out[sha].append(field_name)
    return dict(out)


def role_facts(con: sqlite3.Connection) -> dict[str, tuple[str, str | None, str | None]]:
    return {
        sha: (status, value, source)
        for sha, status, value, source in con.execute(
            "SELECT sha256, status, value, source FROM fact WHERE field='ROLE' "
            "AND extraction_version=?",
            (EV,),
        )
    }


def rule_id_for(reading: Reading) -> str:
    if reading.verdict == "BIND":
        return f"column/{reading.subject.value}+{reading.side}+{reading.role_source or 'NONE'}"
    return "column/role-unconfirmed"


def bind_reason(reading: Reading) -> str:
    reason = (
        f"the values sit under the {reading.subject.value} heading of a comparison table's "
        f"{reading.side} column and the other column holds nothing; the document's own role "
        f"fact ({reading.role_source or 'NONE'}) names the same person, and the locus is the "
        "value's own printed prefix (CV_RESEARCH s12-b)"
    )
    return reason + _unboxed_clause(reading)


def named_reason(reading: Reading) -> str:
    return NAMED_REASON + _unboxed_clause(reading)


def _unboxed_clause(reading: Reading) -> str:
    if not reading.second_star_missing:
        return ""
    return UNBOXED_ROW_CLAUSE.format(n=reading.second_star_missing)


def _write(
    con: sqlite3.Connection,
    sha: str,
    locus: str,
    *,
    status: str,
    value: str | None,
    raw: str | None,
    second: str | None,
    reason: str,
    rule_id: str,
    source: str,
    anchor: Box | None,
    value_boxes: list[Box],
    now: str,
) -> None:
    """One cell, and never anything but an UNKNOWN "no anchor" one.

    The WHERE clause is the gate: a RESOLVED value, a NOT_TESTED row and a cell
    already in review belong to other passes and to other arguments.
    """
    con.execute(
        "UPDATE fact SET status=?, value=?, raw=?, reason=?, rule_id=?, source=?, "
        "repaired=1, second_allele=?, anchor_box=?, value_boxes=?, created_utc=? "
        "WHERE sha256=? AND field=? AND extraction_version=? AND status='UNKNOWN' "
        f"AND reason LIKE '{WORK_REASON_PREFIX}%'",
        (
            status,
            value,
            raw,
            reason,
            rule_id,
            source,
            second,
            json.dumps([anchor.x0, anchor.y0, anchor.x1, anchor.y1]) if anchor else None,
            json.dumps([[b.x0, b.y0, b.x1, b.y1] for b in value_boxes]),
            now,
            sha,
            locus,
            EV,
        ),
    )


def withdraw_stale(con: sqlite3.Connection, roles, *, dry_run: bool) -> int:
    """Take back a bind whose ROLE fact no longer agrees with its column.

    The role agreement IS the wrong-person defence, so it cannot be checked
    once and forgotten: `caption_pass`, `role_repass` and a refresh all rewrite
    ROLE facts. A column-bound cell whose document has since lost its role, or
    changed it, goes back to REVIEW_REQUIRED. This runs at the head of every
    pass, so re-running the pass in the documented order is the repair.
    """
    stale = 0
    for sha, field_name, rule in con.execute(
        "SELECT sha256, field, rule_id FROM fact WHERE source=? AND extraction_version=?",
        (SOURCE, EV),
    ).fetchall():
        parts = (rule or "").split("/")[-1].split("+")
        subject = parts[0] if parts else ""
        status, value, _ = roles.get(sha, ("UNKNOWN", None, None))
        if status == "RESOLVED" and value == subject:
            continue
        stale += 1
        if dry_run:
            continue
        con.execute(
            "UPDATE fact SET status='REVIEW_REQUIRED', value=NULL, second_allele=NULL, "
            "reason=?, created_utc=? WHERE sha256=? AND field=? AND extraction_version=?",
            (
                "the column this value was read from was named by the document's role fact, "
                "and that fact no longer says so",
                time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
                sha,
                field_name,
                EV,
            ),
        )
    return stale


def run(facts: Path, ocr_db: Path, geometry_db: Path, *, dry_run: bool) -> Counter[str]:
    vocabulary = load_vocabulary()
    con = (
        sqlite3.connect(f"file:{facts.as_posix()}?mode=ro", uri=True)
        if dry_run
        else sqlite3.connect(facts)
    )
    ocr = sqlite3.connect(f"file:{ocr_db.as_posix()}?mode=ro", uri=True)
    geometry = load_geometry(geometry_db)
    rulings = load_rulings(geometry_db)
    sheets = comparison_sheets(con)
    work = unanchored(con)
    roles = role_facts(con)
    tally: Counter[str] = Counter()
    tally["comparison sheets with an unanchored locus"] = len(sheets & set(work))
    tally["binds withdrawn; the role fact no longer agrees"] = withdraw_stale(
        con, roles, dry_run=dry_run
    )
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())

    for sha in sorted(sheets & set(work)):
        loci = set(work[sha])
        boxes, width, height = page_boxes(ocr, sha)
        if not boxes:
            tally["no stored boxes for this page"] += 1
            continue
        document = Document(sha, width, height)
        frame = frame_for(document, geometry)
        if frame is not None:
            boxes = frame.rectify(boxes)[0]
        slope, _ = slopes_for(document, rulings, frame)
        status, value, source = roles.get(sha, ("UNKNOWN", None, None))
        reading = read_columns(
            boxes,
            vocabulary,
            slope,
            role=Role(value) if value in (Role.DONOR, Role.RECIPIENT) else Role.UNKNOWN,
            role_resolved=status == "RESOLVED" and value in (Role.DONOR, Role.RECIPIENT),
            role_source=source,
        )

        if reading.verdict == "REFUSE" and not reading.two_subject:
            tally[f"refused: {reading.gate}"] += 1
            continue
        if reading.verdict == "REFUSE":
            printed = reading.two_subject_printed
            tally[
                f"two subjects, and the page prints them: {reading.gate}"
                if printed
                else f"the empty column is not blank, and not a typing: {reading.gate}"
            ] += 1
            wrote = 0
            for locus, found in sorted(reading.evidence.items()):
                if locus not in loci:
                    continue
                wrote += 1
                if dry_run:
                    continue
                _write(
                    con,
                    sha,
                    locus,
                    status="REVIEW_REQUIRED",
                    value=None,
                    raw=" ".join((b.text or "").strip() for b in found),
                    second=None,
                    reason=(
                        f"{TWO_SUBJECT_REASON}; {reading.gate}"
                        if printed
                        else f"{CROWDED_REASON}; {reading.gate}"
                    ),
                    rule_id="column/two-subjects" if printed else "column/other-column-unread",
                    source=REFUSED_SOURCE,
                    anchor=reading.anchor_box,
                    value_boxes=found,
                    now=now,
                )
            tally[
                "cells sent to review, two subjects"
                if printed
                else "cells sent to review, the empty column is not blank"
            ] += wrote
            if not wrote:
                tally["refused, but no cell to file the refusal at"] += 1
            if not dry_run:
                con.commit()
            continue

        binding = reading.verdict == "BIND"
        tally["pages bound" if binding else "pages named, role unconfirmed"] += 1
        if reading.second_star_missing:
            tally["printed rows left unboxed; the second allele has no star"] += (
                reading.second_star_missing
            )
            tally["pages with such a row, which their reason now says"] += 1
        for locus, found in sorted(reading.claims.items()):
            if locus not in loci:
                tally["claimed, but that cell is not ours to answer"] += 1
                continue
            values = [
                v.text() for box in found for v in parse_allele_values((box.text or "").strip())
            ]
            tally[
                f"bound from its column: {locus}" if binding else f"named for review: {locus}"
            ] += 1
            if dry_run:
                continue
            _write(
                con,
                sha,
                locus,
                status="RESOLVED" if binding else "REVIEW_REQUIRED",
                value=" ".join(values) if binding else None,
                raw=" ".join((b.text or "").strip() for b in found),
                second=("READ" if len(values) > 1 else "UNREAD") if binding else None,
                reason=bind_reason(reading) if binding else named_reason(reading),
                rule_id=rule_id_for(reading),
                source=SOURCE if binding else NAMED_SOURCE,
                anchor=reading.anchor_box,
                value_boxes=found,
                now=now,
            )
        if not dry_run:
            con.commit()
    con.close()
    ocr.close()
    return tally


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--ocr", type=Path, default=ROOT / "data/derived/ocr_pass.sqlite")
    parser.add_argument("--geometry", type=Path, default=ROOT / "data/derived/geometry.sqlite")
    # Counting is the DEFAULT here, unlike `prefix_bind.py` and
    # `anchor_row_bind.py`. This pass reverses a recorded operator decision
    # (`CV_RESEARCH_2026-09-05.md` s12) on 450 pages of real patient facts, so
    # a bare `python scripts/column_bind.py` must not commit one of them; the
    # write is a thing the operator asks for by name.
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="count, change nothing (the default)",
    )
    parser.add_argument(
        "--write",
        dest="dry_run",
        action="store_false",
        help="commit the binds; reverses s12 on this corpus, so it is opt-in",
    )
    args = parser.parse_args()
    tally = run(args.facts, args.ocr, args.geometry, dry_run=args.dry_run)
    print(f"{'would bind' if args.dry_run else 'bound'} one person's column on a comparison sheet")
    for name, count in sorted(tally.items()):
        if count:
            print(f"  {name:<62}{count:>8,}")
    print(
        "The column is the person and the prefix is the gene; a bind needs the document's own "
        "role fact to name the same person, and a two-subject page is review work, not a value."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
