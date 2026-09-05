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

`canonical_locus_label` repairs only the FINAL character. Interior damage —
`DRRI` for `DRB1`, where `B` was read as `R` — is refused. Measured, interior
repair would add about 1% more anchors, and it is the only mechanism by which
`DRB1` could canonicalise to `DPB1`. A 1% recall gain is not worth a mechanism
that can silently rename a gene.

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

_HLA_PREFIX = re.compile(r"^HLA[\s\-_]*", re.IGNORECASE)

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
_GROUPED_DRBX = re.compile(
    r"^[\s\-–—.,:;'\"]*"
    r"(?:[HI]{0,3}L?A[\s\-–—]*)?"
    r"DR[B8]\s*3[\s/,.\-\|'\"AMUV]*4[\s/,.\-\|'\"AMUV]*[5S]"
    r"[\s*:;.,)\-]*$"
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

    Strict by design. Repairs the final character only, and never the interior.
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
    if not body:
        return None

    # Class I: only ever with an explicit HLA- prefix.
    for locus in CLASS_I_LOCI:
        if body.upper() == locus.upper():
            return locus if had_prefix else None

    if len(body) != 4:
        return None
    repaired = (body[:-1] + _FINAL_DIGIT_REPAIRS.get(body[-1], body[-1])).upper()
    return repaired if repaired in CLASS_II_LOCI else None


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

    prefix = match.group("prefix")
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
    star_missing = bool(prefix) and match.group("star") is None
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
    )
