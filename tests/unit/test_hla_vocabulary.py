"""Per-locus first-field vocabulary — the gate the resolver was missing.

Written before the implementation. The skeptical review of ADR 0008 found 480
RESOLVED values carrying a first field that does not exist for their locus
(KI-016). They are dominated by the recognizer reading a leading `0` as `8` or
`9` — `A*83`, `C*84`, `DQB1*83`, `DRB1*93` — where the digits are clean, so no
glyph repair can see the error. Only a vocabulary can.

The table is generated once by `scripts/build_hla_vocabulary.py` and committed
with its IMGT version stamped inside it. A vocabulary that changed under the
repository's feet would silently change which values are accepted between two
runs of the same code, and every acceptance decision recorded against it would
become unreproducible.
"""

from __future__ import annotations

import json

import pytest

from kidneymatch.hla.vocabulary import (
    FirstFieldVocabulary,
    VocabularyUnavailable,
    load_vocabulary,
)


@pytest.fixture(scope="module")
def vocabulary() -> FirstFieldVocabulary:
    return load_vocabulary()


@pytest.mark.parametrize(
    ("locus", "first_field"),
    [("DRB1", "11"), ("DRB1", "15"), ("DQB1", "03"), ("DQA1", "05"), ("A", "02"), ("B", "35")],
)
def test_a_real_family_is_admissible(
    vocabulary: FirstFieldVocabulary, locus: str, first_field: str
) -> None:
    assert vocabulary.is_admissible(locus, first_field) is True


@pytest.mark.parametrize(
    ("locus", "first_field"),
    [
        # The measured error: a leading 0 read as 8 or 9.
        ("A", "83"),
        ("C", "84"),
        ("DQB1", "83"),
        ("DQB1", "93"),
        ("DRB1", "93"),
        ("DRB1", "97"),
        # A family that exists, but for a different gene.
        ("DQB1", "13"),
        ("DRB1", "02"),
    ],
)
def test_an_impossible_family_is_refused(
    vocabulary: FirstFieldVocabulary, locus: str, first_field: str
) -> None:
    assert vocabulary.is_admissible(locus, first_field) is False


def test_the_dangerous_confusion_is_actually_separated(vocabulary: FirstFieldVocabulary) -> None:
    """`DRB1*03` misread as `*83` must be refused, and `*03` accepted.

    This pair is the whole point of the gate: both are two clean digits, so
    every other check in the pipeline passes them equally.
    """
    assert vocabulary.is_admissible("DRB1", "03") is True
    assert vocabulary.is_admissible("DRB1", "83") is False


def test_an_unknown_locus_is_not_silently_admitted(vocabulary: FirstFieldVocabulary) -> None:
    """A locus with no table cannot be checked, and an unchecked value must not
    be presented as a checked one."""
    assert vocabulary.is_admissible("DRB9", "01") is False
    assert vocabulary.covers("DRB9") is False
    assert vocabulary.covers("DRB1") is True


def test_the_table_records_which_reference_release_produced_it(
    vocabulary: FirstFieldVocabulary,
) -> None:
    """Every accepted value's provenance must be able to cite the release.

    `HLA_VALIDATION_SPEC.md` pins IMGT/HLA 3.65, which the locked py-ard cannot
    load (HA-006). Until that is settled, the file says what was really used
    rather than what the spec wishes had been.
    """
    assert vocabulary.imgt_version
    assert vocabulary.pyard_version


def test_a_missing_table_fails_loudly(tmp_path) -> None:
    """Silently skipping the gate would remove a safety check without a trace."""
    with pytest.raises(VocabularyUnavailable):
        load_vocabulary(tmp_path / "absent.json")


def test_a_table_from_an_unknown_schema_is_refused(tmp_path) -> None:
    path = tmp_path / "v.json"
    path.write_text(json.dumps({"schema": "something-else/v9"}), encoding="utf-8")
    with pytest.raises(VocabularyUnavailable):
        load_vocabulary(path)


def test_serology_names_are_not_in_the_molecular_table(vocabulary: FirstFieldVocabulary) -> None:
    """Serology and molecular naming are different systems.

    `HLA_VALIDATION_SPEC.md` forbids mixing them, so a serologic antigen number
    must not be admissible merely because it looks like a family.
    """
    # Cw is a serology name; the molecular locus is C and has no `Cw` entry.
    assert vocabulary.covers("Cw") is False


def test_the_committed_table_matches_the_generator(vocabulary: FirstFieldVocabulary) -> None:
    """Guards against a hand-edited vocabulary.

    Counts as generated from IMGT 3620. If a regeneration changes them, this
    test is the place the change is noticed and justified.
    """
    assert len(vocabulary.first_fields("DRB1")) == 13
    assert len(vocabulary.first_fields("DQB1")) == 5
    assert len(vocabulary.first_fields("A")) == 21
    assert len(vocabulary.first_fields("B")) == 36


# --- every refusal path, because a gate that stops gating is worse than none --


def test_malformed_json_is_refused(tmp_path) -> None:
    path = tmp_path / "v.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(VocabularyUnavailable, match="valid JSON"):
        load_vocabulary(path)


@pytest.mark.parametrize(
    "payload",
    [
        {"schema": "hla-first-fields/v1"},
        {"schema": "hla-first-fields/v1", "first_fields": {}},
        {"schema": "hla-first-fields/v1", "first_fields": []},
    ],
)
def test_a_table_with_no_families_is_refused(tmp_path, payload) -> None:
    path = tmp_path / "v.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(VocabularyUnavailable, match="first_fields"):
        load_vocabulary(path)


def test_a_table_that_does_not_name_its_release_is_refused(tmp_path) -> None:
    """Provenance is not optional: an accepted value must be able to cite the
    release that admitted it."""
    path = tmp_path / "v.json"
    path.write_text(
        json.dumps({"schema": "hla-first-fields/v1", "first_fields": {"DRB1": ["01"]}}),
        encoding="utf-8",
    )
    with pytest.raises(VocabularyUnavailable, match="IMGT release"):
        load_vocabulary(path)


def test_a_non_object_payload_is_refused(tmp_path) -> None:
    path = tmp_path / "v.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(VocabularyUnavailable):
        load_vocabulary(path)


def test_the_table_is_read_once_and_reused(tmp_path) -> None:
    """Re-reading per value would make the gate the pipeline's slowest step."""
    path = tmp_path / "v.json"
    path.write_text(
        json.dumps(
            {
                "schema": "hla-first-fields/v1",
                "imgt_version": "9999",
                "pyard_version": "0",
                "first_fields": {"DRB1": ["01"]},
            }
        ),
        encoding="utf-8",
    )
    first = load_vocabulary(path)
    path.unlink()
    assert load_vocabulary(path) is first
