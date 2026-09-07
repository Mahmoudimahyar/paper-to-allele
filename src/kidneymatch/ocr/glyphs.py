"""Repair the recognizer's known glyph confusions, inside a known cell grammar.

The OnnxTR recognizer confuses a small, measured set of glyphs. Two facts make
this the highest-yield accuracy change available:

* The locus label `DRB1` is read `DRBI` **3.5x more often than correctly**
  (12,679 boxes against 3,676). `DQA1`, `DQB1`, `DPA1`, `DPB1` and `DRB5` are
  the same story. Repairing the final character lifts anchored documents per
  locus by 4.5x to 8x.
* **20.7%** of the 88,643 allele-value-shaped boxes carry a letter in a digit
  slot: `I->1` 10,465, `L->1` 7,052, `S->5` 6,845, `l->1` 3,156, `o->0` 2,648,
  `O->0` 813. The `*` separator is read as `+ ° - " '` in ~3,700 boxes.

**Repair is only ever safe inside a cell whose grammar is known.** Turning `I`
into `1` in a numeric field is reading; doing the same to free text is
vandalism. Nothing here operates on a token whose role has not already been
established by geometry.

## The asymmetry

Accepting an anchor is **strict**; rejecting a value is **permissive**.

`canonical_locus_label` repairs the FINAL character and exactly one interior
confusion, `Q` read as `O`/`0`, on which the geometry is decisive (774 refused
`DOB…` values under DQB1 anchors against 1 under DRB1; 21% of DQB1 labels).
That repair can rename: a printed DRB1 or DPB1 whose second glyph read O
becomes DQB1, and a DPA1 becomes DQA1 — 1 case in 775 by the measurement,
accepted and pinned by the rename sweep in the tests. Other interior damage —
`DRRI` for `DRB1`, where `B` was read as `R` — is refused: repairing `R` or
`P` is the mechanism by which `DRB1` could canonicalise to `DPB1` on no
evidence at all.

`looks_like_locus_label` is deliberately broader: it recognises `DRRI` and a
bare `A`, neither of which is good enough to anchor a locus. It exists so the
resolver can refuse them as VALUES. Refusing a value costs recall; accepting a
label as a value emits a patient allele of `DRRI`.

ADR 0006 prescribes the stronger form of this — masking the recognizer's CTC
logits to the cell's alphabet at decode time, so the confusion never occurs.
That fixes errors this module cannot (a glyph that decodes to a *valid* wrong
digit), and this module fixes errors already committed to the stored pass. They
are complementary; this is not a substitute for that.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CLASS_II_LOCI = frozenset({"DRB1", "DRB3", "DRB4", "DRB5", "DQA1", "DQB1", "DPA1", "DPB1"})

# Class I labels are accepted ONLY with an `HLA-` prefix. Measured: 33,175 boxes
# are a bare `A` against 15,281 documents carrying `HLA-A`. Bare single letters
# are table headers, ABO groups and recognizer fragments far more often than
# they are the HLA-A locus, and a wrong class I anchor is as harmful as any
# other.
CLASS_I_LOCI = frozenset({"A", "B", "C", "Cw"})

# Glyphs the recognizer substitutes for a digit, in the FINAL position of a
# locus label.
#
# For `DQA`, `DQB`, `DPA` and `DPB` only one gene exists, so the final character
# carries no gene information and repairing it cannot rename anything. For `DRB`
# the final character IS the gene, so these substitutions CAN rename it: a
# printed `DRB3` whose `3` was read as `I` canonicalises to `DRB1`. An earlier
# comment here claimed no repair could move a label between the DRB genes; an
# exhaustive sweep disproves that, and `test_the_set_of_gene_renaming_repairs_is
# _exactly_the_accepted_one` now pins the six renames that are possible.
#
# They are accepted on measured evidence: P(DRB1 | "DRBI") is about 99.90% by
# likelihood ratio with 368 of 368 geometry checks consistent, and `DRBS`
# matches a DRB5-expecting genotype in 99.2% of 1,020 cases against 17.7% for
# DRB3. The residual — a printed 3/4/5 misread as one of these letters — is
# roughly 0.09% for `3` to `I`. Refusing the repair would cost 12,679 anchors,
# since `DRBI` outnumbers `DRB1` 3.5 to 1.
_FINAL_DIGIT_REPAIRS = {
    "I": "1",
    "i": "1",
    "l": "1",
    "L": "1",
    "|": "1",
    "T": "1",
    "t": "1",
    "!": "1",
    "S": "5",
    "s": "5",
}

# Inside a numeric field, the same confusions plus the zero lookalikes.
# `D` and `Q` were here too, on the theory that they resemble `0`. Measured, they
# occur 12 and 5 times corpus-wide in value bodies and none validates against
# nomenclature: pure false-accept surface, removed.
_DIGIT_REPAIRS = {**_FINAL_DIGIT_REPAIRS, "O": "0", "o": "0"}

# The `*` between locus and allele, as the recognizer renders it.
_STAR_VARIANTS = "*+°\"'`~^"

# `HLA-` and the recognizer's renderings of it: `ILA-`, `IILA-`, `HILA-`, and
# `LA-` only before a separator. Measured the hard way: accepting a bare `LA`
# made the letterhead's `LAB` (19,635 boxes) an HLA-B anchor and sent 9,817 B
# cells to review as "2 anchors found".
_HLA_PREFIX = re.compile(r"^(?:[HI]{1,3}LA|LA(?=[\s\-_]))[\s\-_]*", re.IGNORECASE)
# What a label carries after its name: a colon, a star, quote-shaped noise.
# `HLA-DRB1*:` (277 boxes), `HLA-DQB1":` (307), `HLA-A*:` (513), `HLA-B:` (261).
# Without an HLA prefix only the colon-shaped trail goes: a quote is one of
# the recognizer's renderings of the star (`_STAR_VARIANTS`), so `DRB1"` is
# `DRB1*` — a value whose digits were not read — and must not anchor.
_LABEL_TRAIL = re.compile(r"[\s:;.]+$")
_LABEL_STAR_TRAIL = re.compile(r"[\s*:;.'\"]+$")
# The one interior confusion of a class II label that is repaired: `Q` read as
# `O` or `0` in the second position. No locus has an O there, and the geometry
# is decisive: 774 refused `DOB…` values sat under a DQB1 anchor against 1
# under DRB1 (76 `DOA…` under DQA1 against 2 under DPA1), while the 2,410
# documents printing a `DOBI`-shaped token carry a DRB1 anchor 87% of the time
# and a DQB1 anchor 4.6% — the token IS the missing DQB1 label. Corpus-wide
# that is 3,101 documents gaining their DQB1 anchor and 1,029 their DQA1.
# `R` and `P` are never repaired: reading one as the other renames a gene, so
# `DRRI` and `DPRI` stay refused, and `8` in the third position is left alone
# (45 boxes, no geometry evidence gathered).
_INTERIOR_REPAIRS = {"O": "Q", "0": "Q"}

# A token that could be a locus label, however damaged. Used only to REJECT.
_LABEL_SHAPED = re.compile(
    r"^(?:HLA[\s\-_]*)?(?:D[RPQ][ABRPE]?[0-9A-Za-z|!]{0,2}|[ABC]w?)$",
    re.IGNORECASE,
)

# The combined DRB3/4/5 header. Kept here so `canonical_locus_label` refuses it
# and `looks_like_locus_label` recognises it; the row itself is read by
# `drbx.py`, which owns the authoritative pattern. Measured against 83 accepted
# spellings on the real corpus — an earlier, tighter version missed 2,560
# documents (`HLA-DRB345`, `HLA-DRB34/5`, `HLA-DR83/4/5`, leading-dash forms).
#
# This is `drbx.GROUPED_DRBX_HEADER` verbatim, widened to W5 on 2026-09-06, and
# a test pins the two copies equal. Note what the widening does NOT do here: a
# box this reaches is not a header until `drbx.find_grouped_headers` sees the
# page's geometry corroborate it. The looser shape is deliberately carried into
# this module anyway, because both uses here are REFUSALS — a header-shaped box
# may not anchor a locus and may not be read as a value — and refusing a box
# that turns out not to be a header costs a cell, while accepting one as a
# locus label assigns an allele to three genes.
_GROUPED_DRBX = re.compile(
    r"^[\s\-–—.,:;'\"]*"
    r"(?P<hla>[HIB]{0,3}L?A[\s\-–—]*)?"
    r"DR(?P<slot>[A-RT-Za-z?8$])?\s*3"
    r"(?P<mid>[\s/,.\-\\|'\"AMUV14]*4[\s/,.\-\\|'\"AMUV14]*"
    r"|(?(hla)[\s/,.\-\\|'\"1]*[AMUV][\s/,.\-\\|'\"AMUV14]*|(?!)))"
    r"(?P<final>[5S3])[\s*:;.,)\-]*$"
)

_DIGIT_SLOT = "0-9" + "".join(sorted(set(_DIGIT_REPAIRS)))
# The expression suffix is matched with a lookahead-anchored alternation so the
# greedy digit group cannot eat it. `A*02S` is a secreted allele, not `A*025` —
# and `S` is in the digit-repair table, so a naive grammar invents a different
# allele silently.
# The star after a prefix is optional. Measured corpus-wide, 3,153 cells were
# refused only because the recognizer read `A02` for `A*02` — the star lost
# entirely rather than rendered as one of the variants above — 45% of every
# shape refusal. A prefix that names a locus and two or three digits that face
# the admissibility gate carry the same information; the absence is recorded
# as a repair. A bare number never gains a prefix by this route: the prefix
# must be letters that `canonical_locus_label` accepts.
_VALUE = re.compile(
    rf"""^
    (?:(?P<prefix>[A-Za-z]{{1,4}}[0-9A-Za-z|!]?)\s*(?P<star>[{re.escape(_STAR_VARIANTS)}])?\s*
      |[{re.escape(_STAR_VARIANTS)}]\s*)?
    (?P<first>[{_DIGIT_SLOT}]{{2,3}}?)
    (?::(?P<second>[{_DIGIT_SLOT}]{{2,3}}?))?
    (?P<expression>[NLSQCA])?
    $""",
    re.VERBOSE,
)

# Both alleles of one locus printed in ONE box, each carrying its own star:
# `A*24,*02`. Measured over the corpus, 1,819 such tokens on 890 documents,
# commonest as `A*##,*##`, `DRB1*##,*##` and `B*##,*##`. The second star is
# what makes it unambiguous, and it is why nothing looser is accepted here:
# `A*24,02` has one star, and whether that is two alleles or the two-field
# `A*24:02` written with a comma is a question about the form, not about the
# glyphs — 1,025 tokens on 491 documents wait on that answer rather than being
# guessed at (HA-015).
_PAIR = re.compile(
    rf"""^
    (?P<first>.+?)
    \s*[,.;/]\s*
    (?P<second>[{re.escape(_STAR_VARIANTS)}]\s*[0-9A-Za-z]{{2,3}}(?::[0-9A-Za-z]{{2,3}})?[NLSQCA]?)
    $""",
    re.VERBOSE,
)

# The recognizer's B/8 confusion in the PREFIX slot: `8*44` for `B*44`,
# 56 cells corpus-wide. Repaired only when a star follows; a bare `844` is a
# number, and which locus a number belongs to is never decided from its text.
_EIGHT_FOR_B = re.compile(rf"^8(?=\s*[{re.escape(_STAR_VARIANTS)}])")


@dataclass(frozen=True, slots=True)
class AlleleValue:
    """A parsed allele value, with the raw token it came from.

    `raw` is kept because provenance is a project invariant: every derived
    medical fact must point back at what was actually read, not only at what we
    decided it meant.
    """

    raw: str
    locus_prefix: str | None
    first_field: str
    second_field: str | None
    expression: str | None
    repaired: bool
    # A locus prefix with no `*` at all between it and the digits. The
    # resolver admits this only on a form measured to print the locus on its
    # values; elsewhere `B35` may be a serological spelling
    # (HLA_VALIDATION_SPEC s4), and it goes to review.
    separator_missing: bool = False
    """True when ANY glyph had to be repaired to read this token.

    Digits, the `*` separator and the locus prefix all count. A reviewer
    deciding whether to trust a value needs to know the raw text differed at
    all, not only whether a digit did.
    """

    def text(self) -> str:
        """Canonical rendering. Never adds a field that was not printed."""
        body = self.first_field
        if self.second_field is not None:
            body = f"{body}:{self.second_field}"
        if self.expression:
            body += self.expression
        return f"{self.locus_prefix}*{body}" if self.locus_prefix else body


def canonical_locus_label(token: str) -> str | None:
    """The locus this token names, or None if it does not reliably name one.

    Strict by design. Repairs the final character and one interior confusion
    (`_INTERIOR_REPAIRS`: Q read as O/0), nothing else, and strips the
    punctuation a label carries after its name. The interior repair CAN move
    a damaged label between loci — `DOB1` is DQB1 whether the page printed
    DQB1, DRB1 or DPB1 — and is accepted on the geometry evidence recorded at
    that constant; the rename sweep in the tests names the crossings.
    """
    stripped = (token or "").strip()
    if not stripped:
        return None
    if _GROUPED_DRBX.match(stripped):
        # A presentation grouping, not a locus. It gets its own anchor type;
        # treating it as one locus would assign one allele to three genes.
        return None

    had_prefix = bool(_HLA_PREFIX.match(stripped))
    body = _HLA_PREFIX.sub("", stripped).strip()
    # A star is stripped only behind an HLA prefix: `DRB1*` on its own is as
    # likely a value whose digits were not read, and a value stub must never
    # anchor a locus.
    body = (_LABEL_STAR_TRAIL if had_prefix else _LABEL_TRAIL).sub("", body).strip()
    if not body:
        return None

    # Class I: only ever with an explicit HLA- prefix.
    for locus in CLASS_I_LOCI:
        if body.upper() == locus.upper():
            return locus if had_prefix else None

    if len(body) != 4:
        return None
    second = _INTERIOR_REPAIRS.get(body[1].upper(), body[1])
    repaired = (body[0] + second + body[2] + _FINAL_DIGIT_REPAIRS.get(body[-1], body[-1])).upper()
    return repaired if repaired in CLASS_II_LOCI else None


def is_grouped_drbx_header(token: str) -> bool:
    """Is this token the combined DRB3/4/5 header? `drbx.py` reads that row;
    `anchors.py` lets the header own its row like any label."""
    return bool(_GROUPED_DRBX.match((token or "").strip()))


def parse_allele_values(token: str) -> list[AlleleValue]:
    """Every allele this ONE box states: usually one, sometimes a printed pair.

    A cell that prints `A*24,*02` holds both of a locus's alleles in a single
    box, and reading it as one value or as none loses half the genotype. The
    pair is split only when the SECOND part carries its own star, which is what
    separates it from `A*24,02` — that could as easily be a two-field allele
    written with a comma, and guessing between them would either invent a
    second allele or silently upgrade the resolution of the first, both of
    which this project forbids.
    """
    stripped = (token or "").strip()
    single = parse_allele_value(stripped)
    if single is not None:
        return [single]
    found = _PAIR.match(stripped)
    if not found:
        return []
    first = parse_allele_value(found.group("first"))
    if first is None or first.locus_prefix is None:
        # Without a locus on the first half there is nothing to carry over, and
        # a bare pair of numbers names no gene.
        return []
    second = parse_allele_value(f"{first.locus_prefix}{found.group('second')}")
    if second is None or second.locus_prefix != first.locus_prefix:
        return []
    return [first, second]


def looks_like_locus_label(token: str) -> bool:
    """True if the token could be a locus label, however damaged.

    Permissive on purpose: this is the guard that stops a label being bound as
    a patient value. It must recognise forms too damaged to anchor.
    """
    stripped = (token or "").strip()
    if not stripped:
        return False
    if _GROUPED_DRBX.match(stripped):
        return True
    if canonical_locus_label(stripped) is not None:
        return True
    return bool(_LABEL_SHAPED.match(stripped))


def _repair_digits(field: str) -> tuple[str, bool]:
    out = "".join(_DIGIT_REPAIRS.get(ch, ch) for ch in field)
    return out, out != field


def parse_allele_value(token: str) -> AlleleValue | None:
    """Parse an allele value, repairing digit-slot glyphs. None if it is not one.

    A first field is never expanded to a second field: `OCR-001` forbids
    promoting low-resolution typing, and there is no such thing as an implied
    second field.
    """
    stripped = (token or "").strip()
    if not stripped or looks_like_locus_label(stripped):
        return None

    # `HLA-DRB1*15` is a value like any other. 44 boxes carry the prefix.
    body = _HLA_PREFIX.sub("", stripped).strip() or stripped
    eight_repaired = bool(_EIGHT_FOR_B.match(body))
    if eight_repaired:
        body = "B" + body[1:]
    match = _VALUE.match(body)
    if not match:
        return None

    prefix = match.group("prefix")
    star_missing = bool(prefix) and match.group("star") is None
    if star_missing and not (
        match.group("first").isdigit() and (match.group("second") or "0").isdigit()
    ):
        # Without the star, the digit-slot repairs would turn a WORD into a
        # value: `ALL` is A + `LL`, `BIS` is B + `IS`, `COS` is C + `OS` —
        # measured, 74 resolved cells carried a letters-only token under the
        # first version of this rule. The star is what licenses reading a
        # letter as a damaged digit; absent it, the digits must be digits.
        return None

    first, first_repaired = _repair_digits(match.group("first"))
    if not first.isdigit():
        return None
    second_raw = match.group("second")
    second, second_repaired = _repair_digits(second_raw) if second_raw else (None, False)
    if second is not None and not second.isdigit():
        return None

    if match.group("expression") and second is None:
        # WHO nomenclature never attaches an expression suffix to a
        # first-field-only name, so this parse is a misread accepted as a value.
        # `L` and `S` are also digit-slot repairs, so `10S` was read as the
        # family `10` plus a suffix rather than the family `105`, and `A` turned
        # the recognizer's `HLA` fragments (`ILA`, `IILA`) into alleles.
        # Measured: 3,062 boxes parsed this way against one with a real second
        # field, and 33 of them reached an anchored cell.
        return None

    # A bare `A` cannot ANCHOR a locus — a lone letter is a table header or an
    # ABO group far more often than a gene. But `A*02` has no such competition:
    # the star and the digits disambiguate it. Requiring `HLA-` here silently
    # dropped 68,577 of 126,028 self-identifying values, 54.4% of them.
    canonical_prefix = (
        canonical_locus_label(prefix) or canonical_locus_label(f"HLA-{prefix}") if prefix else None
    )
    if prefix and canonical_prefix is None:
        # A prefix we cannot name is not a licence to ignore it: it may be a
        # different locus, and binding the value would guess which.
        return None
    if canonical_prefix == "Cw":
        # `Cw07` is the serological spelling of the C locus's value, and the
        # confirmer already reads its digits as C's (KI-019). As a value prefix
        # it names C; the spelling is recorded as a repair.
        canonical_prefix = "C"

    separator_repaired = any(ch in stripped for ch in _STAR_VARIANTS.replace("*", ""))
    # A prefix with no star at all is the separator missing, which is a repair
    # like any other rendering of it: the reviewer must see the raw text differed.
    prefix_repaired = bool(prefix) and (prefix != canonical_prefix or eight_repaired)

    return AlleleValue(
        raw=stripped,
        locus_prefix=canonical_prefix,
        first_field=first,
        second_field=second,
        expression=(match.group("expression") or None),
        repaired=(
            first_repaired
            or second_repaired
            or separator_repaired
            or star_missing
            or prefix_repaired
        ),
        separator_missing=star_missing,
    )
