"""The region the second allele would be read from, and what may be read there.

This rule adds an allele to a cell that already has one, so every test below is
a way it could assert an allele that is not printed. The region is geometry's
(the ruled row, past the bound value); the reading is two engines' and must
agree exactly, parse, name THIS locus and be admissible in IMGT.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]


def load():
    spec = importlib.util.spec_from_file_location(
        "second_allele_reread", ROOT / "scripts" / "second_allele_reread.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@dataclass
class FakeBand:
    top: float
    bottom: float
    right: float


class FakeLattice:
    """A lattice that puts one row band wherever the test wants it."""

    def __init__(self, band: FakeBand | None) -> None:
        self._band = band

    def row_band(self, _cx: float, _cy: float, _height: float) -> FakeBand | None:
        return self._band


class Vocabulary:
    """Admits `01`-`99` for every locus except DPA1, which it does not cover."""

    imgt_version = "test"

    def covers(self, locus: str) -> bool:
        return locus != "DPA1"

    def is_admissible(self, locus: str, first_field: str) -> bool:
        return self.covers(locus) and first_field.isdigit() and first_field != "99"


ANCHOR = [0.10, 0.40, 0.19, 0.42]  # a label 0.02 high
BAND = FakeBand(top=0.395, bottom=0.425, right=0.90)


def test_the_region_starts_past_the_bound_value_and_ends_at_the_row() -> None:
    m = load()
    region = m.remainder_region(ANCHOR, [[0.30, 0.40, 0.40, 0.42]], FakeLattice(BAND))
    assert region is not None
    left, top, right, bottom = region
    assert left > 0.40, "the region must not overlap the value already read"
    assert (top, right, bottom) == (0.395, 0.90, 0.425)


def test_a_row_the_rulings_cannot_place_yields_no_region() -> None:
    m = load()
    assert m.remainder_region(ANCHOR, [[0.30, 0.40, 0.40, 0.42]], FakeLattice(None)) is None


def test_a_value_that_reaches_the_row_end_leaves_no_region() -> None:
    """No room for another allele is not the same as no allele; it is silence."""
    m = load()
    assert m.remainder_region(ANCHOR, [[0.30, 0.40, 0.89, 0.42]], FakeLattice(BAND)) is None


def test_the_region_never_starts_left_of_the_cell() -> None:
    """A value box left of the label's own column must not widen the crop back
    over the label, where the locus name would read as a value."""
    m = load()
    region = m.remainder_region(ANCHOR, [[0.01, 0.40, 0.05, 0.42]], FakeLattice(BAND))
    assert region is not None
    assert region[0] >= 0.19, "the crop reached back into the label column"


def test_two_engines_must_read_the_same_text() -> None:
    m = load()
    voc = Vocabulary()
    assert m.agreed_allele(["24", "24"], "A", voc) == ("A*24", "24")
    assert m.agreed_allele(["24", "27"], "A", voc) is None
    assert m.agreed_allele(["24", ""], "A", voc) is None
    assert m.agreed_allele(["", ""], "A", voc) is None


def test_a_printed_prefix_must_name_this_locus() -> None:
    """A crop that ran into the next column reads another gene, and is refused."""
    m = load()
    voc = Vocabulary()
    assert m.agreed_allele(["A*24", "A*24"], "A", voc) == ("A*24", "24")
    assert m.agreed_allele(["B*27", "B*27"], "A", voc) is None


def test_the_reading_must_be_admissible_for_this_locus() -> None:
    m = load()
    voc = Vocabulary()
    assert m.agreed_allele(["99", "99"], "A", voc) is None, "not in the vocabulary"
    assert m.agreed_allele(["24", "24"], "DPA1", voc) is None, "locus not covered"


def test_a_reading_that_is_not_one_allele_is_refused() -> None:
    m = load()
    voc = Vocabulary()
    assert m.agreed_allele(["24 27", "24 27"], "A", voc) is None, "two values is not one allele"
    assert m.agreed_allele(["Bw4", "Bw4"], "B", voc) is None, "an epitope is not an allele"
    assert m.agreed_allele(["-", "-"], "A", voc) is None


@pytest.mark.parametrize(
    "region,expected",
    [((0.0, 0.0, 1.0, 1.0), (100, 200)), ((0.5, 0.0, 1.0, 0.5), (50, 100))],
)
def test_the_crop_is_taken_in_the_stored_image_frame(region, expected) -> None:
    m = load()
    image = np.zeros((100, 200), dtype=np.uint8)
    patch = m.crop(image, region)
    assert patch is not None
    assert patch.shape == expected


def test_a_crop_too_small_to_hold_a_glyph_is_refused() -> None:
    m = load()
    image = np.zeros((100, 200), dtype=np.uint8)
    assert m.crop(image, (0.0, 0.0, 0.01, 0.01)) is None
