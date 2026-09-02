"""Which allele families exist for each locus.

The gate the resolver was missing. A skeptical review of ADR 0008 found **480
RESOLVED values whose first field does not exist for their locus** (KI-016),
dominated by the recognizer reading a leading `0` as `8` or `9`: `A*83`, `C*84`,
`DQB1*83`, `DRB1*93/97`. Both readings are two clean digits, so glyph repair
cannot see the error and every geometric gate passes it. A vocabulary is the
only thing that separates `DRB1*03` from `DRB1*83`.

**The table is data, not a lookup.** It is generated once by
`scripts/build_hla_vocabulary.py` from the IPD-IMGT/HLA allele table and
committed with its release stamped inside. A vocabulary that changed under the
repository's feet would silently change which values are accepted between two
runs of the same code, and every acceptance decision recorded against it would
become unreproducible.

**An unchecked value is never presented as a checked one.** A locus with no
table is not admissible; `covers()` says whether the question can be answered at
all, so a caller can route to review rather than quietly accepting.

`HLA_VALIDATION_SPEC.md` pins IMGT/HLA 3.65, which the locked py-ard 1.5.5
cannot load (HA-006, a human decision). The committed file records the release
that really produced it, and that is what a derived fact's provenance cites.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

SCHEMA = "hla-first-fields/v1"
DEFAULT_PATH = Path(__file__).resolve().parents[3] / "config/hla_first_fields.json"


class VocabularyUnavailable(RuntimeError):
    """The reference table is missing or unreadable.

    Raised rather than degrading to "accept everything": a gate that silently
    stops gating is worse than no gate, because the output still looks checked.
    """


@dataclass(frozen=True, slots=True)
class FirstFieldVocabulary:
    """Admissible first-field families per locus, with the release they came from."""

    imgt_version: str
    pyard_version: str
    _families: MappingProxyType[str, frozenset[str]]

    def covers(self, locus: str) -> bool:
        """Can this locus be checked at all?"""
        return locus in self._families

    def first_fields(self, locus: str) -> frozenset[str]:
        return self._families.get(locus, frozenset())

    def is_admissible(self, locus: str, first_field: str) -> bool:
        """True only if this family exists for this locus, in this release."""
        return first_field in self._families.get(locus, frozenset())


_cache: dict[Path, FirstFieldVocabulary] = {}


def load_vocabulary(path: Path | None = None) -> FirstFieldVocabulary:
    """Read the committed table. Raises `VocabularyUnavailable` rather than guessing."""
    resolved = (path or DEFAULT_PATH).resolve()
    cached = _cache.get(resolved)
    if cached is not None:
        return cached

    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except OSError as error:
        raise VocabularyUnavailable(
            f"no HLA first-field table at {resolved}; "
            "run scripts/build_hla_vocabulary.py --imgt-version <release>"
        ) from error
    except json.JSONDecodeError as error:
        raise VocabularyUnavailable(f"{resolved} is not valid JSON") from error

    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise VocabularyUnavailable(
            f"{resolved} is not {SCHEMA}; refusing to read a table of unknown shape"
        )
    families = payload.get("first_fields")
    if not isinstance(families, dict) or not families:
        raise VocabularyUnavailable(f"{resolved} carries no first_fields")

    vocabulary = FirstFieldVocabulary(
        imgt_version=str(payload.get("imgt_version", "")),
        pyard_version=str(payload.get("pyard_version", "")),
        _families=MappingProxyType(
            {locus: frozenset(fields) for locus, fields in families.items()}
        ),
    )
    if not vocabulary.imgt_version:
        raise VocabularyUnavailable(f"{resolved} does not record its IMGT release")
    _cache[resolved] = vocabulary
    return vocabulary
