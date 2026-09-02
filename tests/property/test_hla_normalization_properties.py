"""Property-based tests for HLA normalization.

P2-2 of the harness readiness review. A property test explores inputs a
hand-written example never reaches, which matters most here: this function will
be fed OCR output from low-resolution photographs, so the interesting inputs are
malformed ones, not the tidy ones a developer thinks of.

The properties below are the medical safety rules from
`docs/product/PRODUCT_CONSTITUTION.md` section 6, stated as invariants over all
inputs rather than over a handful of examples.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from kidneymatch.hla.models import HLALocus
from kidneymatch.hla.normalize import normalize_reported_hla

# Well-formed-looking allele strings, plus deliberate junk.
FIELDS = st.lists(st.integers(min_value=0, max_value=999), min_size=1, max_size=4).map(
    lambda parts: ":".join(f"{p:02d}" for p in parts)
)
LOCI = st.sampled_from(list(HLALocus))
JUNK = st.text(max_size=40)


@given(locus=LOCI, fields=FIELDS)
def test_a_low_resolution_value_is_never_promoted(locus: HLALocus, fields: str) -> None:
    """`A*02` must never become `A*02:01`.

    Constitution: "Low-resolution allele A*02 must never be expanded to A*02:01
    without new evidence." Promotion would invent a donor-recipient mismatch
    difference that the source document does not support.
    """
    value = normalize_reported_hla(locus, f"{locus.value}*{fields}")
    if value.normalized_value is None:
        return
    had_colon = ":" in fields
    assert (":" in value.normalized_value) == had_colon
    assert value.is_low_resolution is (not had_colon)


@given(locus=LOCI, other=LOCI, fields=FIELDS)
def test_a_value_is_never_reassigned_to_a_different_locus(
    locus: HLALocus, other: HLALocus, fields: str
) -> None:
    """Geometry decides the locus; the token text may never override it.

    A DQB1 string read from an HLA-B cell must be refused, not relabelled.
    """
    value = normalize_reported_hla(locus, f"{other.value}*{fields}")
    if other is locus:
        return
    assert value.normalized_value is None
    assert value.requires_review is True


@given(locus=LOCI, raw=JUNK)
def test_arbitrary_text_never_produces_an_allele_for_another_locus(
    locus: HLALocus, raw: str
) -> None:
    """OCR garbage must abstain, never fabricate.

    Whatever comes out, it is either "no value, needs review" or a string that
    genuinely belongs to the requested locus.
    """
    value = normalize_reported_hla(locus, raw)
    if value.normalized_value is None:
        assert value.requires_review is True
    else:
        assert value.normalized_value.startswith(f"{locus.value}*")


@given(locus=LOCI, raw=st.one_of(JUNK, FIELDS.map(lambda f: f"*{f}")))
def test_normalization_is_deterministic(locus: HLALocus, raw: str) -> None:
    """Matching must be reproducible: same input, same policy, same result."""
    first = normalize_reported_hla(locus, raw)
    second = normalize_reported_hla(locus, raw)
    assert first == second


@given(locus=LOCI, raw=st.one_of(JUNK, FIELDS.map(lambda f: f"*{f}")))
def test_the_raw_value_is_always_preserved_verbatim(locus: HLALocus, raw: str) -> None:
    """Provenance: the source string survives whatever normalization decides."""
    assert normalize_reported_hla(locus, raw).raw_value == raw


@given(locus=LOCI, fields=FIELDS)
def test_normalization_is_idempotent_on_its_own_output(locus: HLALocus, fields: str) -> None:
    """Re-normalizing an accepted value must not change it.

    Otherwise a value could drift each time it passes through the pipeline.
    """
    first = normalize_reported_hla(locus, f"{locus.value}*{fields}")
    if first.normalized_value is None:
        return
    second = normalize_reported_hla(locus, first.normalized_value)
    assert second.normalized_value == first.normalized_value
    assert second.is_low_resolution == first.is_low_resolution


@pytest.mark.parametrize("separator", ["", " ", "  "])
def test_a_bare_star_value_adopts_the_cell_locus(separator: str) -> None:
    """The template cell supplies the locus when the printed token omits it."""
    value = normalize_reported_hla(HLALocus.DQB1, f"{separator}*06{separator}")
    assert value.normalized_value == "DQB1*06"
    assert value.is_low_resolution is True
