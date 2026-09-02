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
# locus label. `1` and `5` are the only locus-final digits that have letter
# lookalikes; `3` and `4` have none in the measured confusion set, which is why
# no repair can move a label between the DRB genes.
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
_DIGIT_REPAIRS = {**_FINAL_DIGIT_REPAIRS, "O": "0", "o": "0", "Q": "0", "D": "0"}

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
_VALUE = re.compile(
    rf"""^
    (?:(?P<prefix>[A-Za-z]{{1,4}}[0-9A-Za-z|!]?)\s*[{re.escape(_STAR_VARIANTS)}]\s*
      |[{re.escape(_STAR_VARIANTS)}]\s*)?
    (?P<first>[{_DIGIT_SLOT}]{{2,3}})
    (?::(?P<second>[{_DIGIT_SLOT}]{{2,3}}))?
    (?P<expression>[NLSQCA])?
    $""",
    re.VERBOSE,
)


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

    match = _VALUE.match(stripped)
    if not match:
        return None

    first, first_repaired = _repair_digits(match.group("first"))
    if not first.isdigit():
        return None
    second_raw = match.group("second")
    second, second_repaired = _repair_digits(second_raw) if second_raw else (None, False)
    if second is not None and not second.isdigit():
        return None

    prefix = match.group("prefix")
    canonical_prefix = canonical_locus_label(prefix) if prefix else None
    if prefix and canonical_prefix is None:
        # A prefix we cannot name is not a licence to ignore it: it may be a
        # different locus, and binding the value would guess which.
        return None

    separator_repaired = any(ch in stripped for ch in _STAR_VARIANTS.replace("*", ""))
    prefix_repaired = bool(prefix) and prefix != canonical_prefix

    return AlleleValue(
        raw=stripped,
        locus_prefix=canonical_prefix,
        first_field=first,
        second_field=second,
        expression=(match.group("expression") or None),
        repaired=first_repaired or second_repaired or separator_repaired or prefix_repaired,
    )
