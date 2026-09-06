"""A refused value may be re-read, but only two agreeing engines may replace it.

`scripts/reread_refused.py` writes medical values into cells the resolver had
refused, so the gates below are the whole safety argument. Each test names the
way the pass could assert something untrue, which is the failure this project
exists to prevent.

The pass is deliberately asymmetric: the resolver's refusal stands unless two
independent recognizers, reading the same crop, arrive at the same value that
parses, is admissible for the locus, and is not the thing that was refused.
One engine agreeing with itself is not evidence, and neither is an engine
producing a family that merely exists.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from reread_refused import (  # noqa: E402
    MAX_VALUES,
    agreed_value,
    classify_refusal,
)

from kidneymatch.hla.vocabulary import load_vocabulary  # noqa: E402


@pytest.fixture(scope="module")
def vocabulary():
    return load_vocabulary()


def taken(reading: str, second: str, locus: str = "A", refused: str = "83", *, vocabulary):
    return agreed_value(reading, second, locus, refused, vocabulary)


def test_two_engines_reading_the_same_admissible_value_settle_the_cell(vocabulary) -> None:
    assert taken("A*03", "A*03", vocabulary=vocabulary) == "A*03"


def test_one_engine_alone_settles_nothing(vocabulary) -> None:
    """The pixels already defeated one reader; a second guess is not evidence."""
    assert taken("A*03", "A*11", vocabulary=vocabulary) is None
    assert taken("A*03", "", vocabulary=vocabulary) is None


def test_a_family_that_does_not_exist_is_still_refused(vocabulary) -> None:
    """Agreement does not override the vocabulary. `A*83` is not a thing."""
    assert taken("A*83", "A*83", vocabulary=vocabulary) is None


def test_repeating_the_refused_reading_settles_nothing(vocabulary) -> None:
    """Reading the same wrong thing again is the same error twice."""
    assert taken("A*83", "A*83", refused="83", vocabulary=vocabulary) is None


def test_a_value_prefixed_for_another_locus_is_refused(vocabulary) -> None:
    """Geometry owns the locus. A `B*35` in the A row means nobody knows."""
    assert taken("B*35", "B*35", locus="A", vocabulary=vocabulary) is None


def test_an_unparsable_agreement_settles_nothing(vocabulary) -> None:
    """Two engines can agree on nonsense; nonsense is not a value."""
    assert taken("ponias", "ponias", vocabulary=vocabulary) is None
    assert taken("...", "...", vocabulary=vocabulary) is None


def test_the_agreed_value_is_returned_in_canonical_form(vocabulary) -> None:
    """What is written is the parsed value, not the raw glyphs."""
    settled = taken("A*03", "A*03", vocabulary=vocabulary)
    assert settled is not None
    assert settled.startswith("A")


def test_both_reading_refusals_are_recognised() -> None:
    inadmissible = classify_refusal("'83' is not an allele family of A in IMGT 3620")
    unparsable = classify_refusal("candidate 'ponias' does not parse as an allele value")
    assert inadmissible == ("inadmissible family", "83")
    assert unparsable == ("unparsable candidate", "ponias")


def test_a_geometry_refusal_is_not_a_reading_refusal() -> None:
    """Re-reading cannot answer where a box sits, so those cells are left alone."""
    assert classify_refusal("candidate is closer to the A label; another locus owns it") is None
    assert classify_refusal("3 candidate values exceeds max_values=2") is None
    assert classify_refusal("anchor found but no box at all in its cell under this rule") is None
    assert classify_refusal(None) is None


def test_a_locus_holds_at_most_two_alleles() -> None:
    """The cardinality gate the pass applies to what it agreed on."""
    assert MAX_VALUES == 2


def test_the_readings_are_stored_under_named_columns() -> None:
    """A positional insert wrote every value one column to the left.

    This table gained `boxes` by ALTER TABLE, which appends it last, while the
    CREATE statement listed it seventh. The insert was positional, so for a
    time `readings` held the box list, `created_utc` held the values taken and
    `boxes` held the timestamp — on all 5,449 stored rows. The facts were never
    affected, because those writes name their columns; the provenance record
    was, and a derived medical fact has to point at what was actually read.
    """
    source = (ROOT / "scripts" / "reread_refused.py").read_text(encoding="utf-8")
    assert "INSERT OR REPLACE INTO reread_refused VALUES" not in source
    assert "INSERT OR REPLACE INTO reread_refused " in source
    for column in (
        "sha256",
        "field",
        "extraction_version",
        "reread_version",
        "refusal",
        "refused",
        "boxes",
        "readings",
        "readings_second",
        "taken",
        "created_utc",
    ):
        assert column in source


def test_the_schema_lists_boxes_where_the_migration_put_it() -> None:
    """The CREATE must describe the table a fresh run would meet."""
    source = (ROOT / "scripts" / "reread_refused.py").read_text(encoding="utf-8")
    create = source.split("CREATE TABLE IF NOT EXISTS reread_refused")[1].split(");")[0]
    order = [line.split()[0] for line in create.splitlines() if line.strip() and "(" not in line]
    assert order.index("boxes") > order.index("created_utc")
