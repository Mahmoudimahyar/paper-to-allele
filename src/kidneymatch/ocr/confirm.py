"""A second, independent recognizer must agree before a value is auto-accepted.

ADR 0006 requires unanimity across architecturally INDEPENDENT engines, and
measured why: a 2-of-3 majority across neural recognizers was *worse* than
unanimity — 3.50% against 4.50% false acceptance — because engines that share an
architecture share their mistakes, so a majority of them is one opinion counted
three times.

Tesseract is the independent one available here: a different era, a different
approach, no shared training data with the neural recognizer. Measured on 300
resolved DRB1/DQB1 cells it agrees with the repaired reading on 86.3%. Of the
rest, 11.3% are its abstentions on narrow crops and 1.7% are contradictions —
and **every measured contradiction was Tesseract reading a family that does not
exist for that locus**.

That drives the one design decision here. The vocabulary gate applies to *both*
engines, so a confirmer producing an impossible family withholds its opinion
instead of voting against a possible one. Otherwise the confirmer would move
sound values into the review queue on the strength of a reading we already know
to be wrong, and a confirmer that does that is worse than none.

Three outcomes, and the difference between the last two matters:

* `CONFIRMED` — both engines read the same admissible value. Auto-acceptable.
* `CONTRADICTED` — both read something admissible, and they differ. A human
  must look: the engines disagree about what is printed.
* `UNCONFIRMED` — the confirmer could not read it, or read something impossible.
  That is the absence of a second opinion, not evidence against the first.
"""

from __future__ import annotations

import re
from enum import StrEnum

from kidneymatch.hla.vocabulary import FirstFieldVocabulary
from kidneymatch.ocr.glyphs import parse_allele_value


class Confirmation(StrEnum):
    CONFIRMED = "CONFIRMED"
    CONTRADICTED = "CONTRADICTED"
    UNCONFIRMED = "UNCONFIRMED"


def _read(
    reading: str, locus: str, vocabulary: FirstFieldVocabulary
) -> tuple[list[str] | None, bool]:
    """The confirmer's reading as first fields, plus whether it named another gene.

    The two are separate outcomes. A reading that says nothing usable is the
    absence of a second opinion; a reading that clearly names a different gene
    is a disagreement about the page, and collapsing them into one `None` would
    hide the second inside the first.
    """
    if not vocabulary.covers(locus):
        return None, False

    fields: list[str] = []
    for token in reading.split():
        value = parse_allele_value(token)
        if value is not None and value.locus_prefix is not None and value.locus_prefix != locus:
            # A prefix the confirmer read CLEARLY, naming another gene.
            return None, True
        if value is None:
            # The confirmer confirms DIGITS: the locus came from geometry, and
            # the primary pipeline has already refused any value naming a
            # different one. Requiring the confirmer's PREFIX to parse threw
            # away most of its opinions — 130 of 400 cells were withheld
            # because `DRB1*11` had been rendered `RB1*11` while the digits
            # were perfectly clear — so a body after a star is read on its own.
            body = token.split("*")[-1] if "*" in token else token
            value = parse_allele_value(body)
            if value is None and "*" not in token:
                # No star at all: the locus name is glued to the digits (`A02`,
                # `Cw07`, `DRB111`). Measured on FORM#1, this is most of the
                # class I "no opinion" verdicts. The letters go; the locus's
                # own digit goes if the rest still reads as a value.
                stripped = re.sub(r"^[A-Za-z]+", "", token)
                if locus[-1].isdigit() and stripped.startswith(locus[-1]):
                    value = parse_allele_value(stripped[1:])
                if value is None:
                    value = parse_allele_value(stripped)
            if value is None:
                continue
        if not vocabulary.is_admissible(locus, value.first_field):
            # An impossible family is not evidence against a possible one.
            return None, False
        fields.append(value.first_field)
    return (fields or None), False


def confirm_value(
    locus: str,
    accepted: tuple[str, ...],
    confirmer_reading: str,
    vocabulary: FirstFieldVocabulary,
) -> Confirmation:
    """Does the independent engine agree with the value already bound?

    `accepted` is what the primary pipeline resolved; the locus is not in
    question — geometry fixed it — so only the characters are compared.
    """
    confirmed, named_another_locus = _read(confirmer_reading, locus, vocabulary)
    if named_another_locus:
        return Confirmation.CONTRADICTED
    if confirmed is None:
        return Confirmation.UNCONFIRMED

    ours = [value.split("*")[-1] for value in accepted]
    return (
        Confirmation.CONFIRMED if sorted(ours) == sorted(confirmed) else Confirmation.CONTRADICTED
    )
