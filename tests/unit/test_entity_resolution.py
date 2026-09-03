"""Linking documents to people, and refusing to when the evidence is arithmetic.

`ENTITY-001`. The archive is per image; matching needs it per person. The
tempting rule is "same HLA on three loci means the same person", and the
measured frequencies say it would fabricate people: DQB1 has thirty observed
genotypes in this corpus, and 10,032 documents make 50.3 million pairs, so a
per-pair probability above 2e-8 already yields an expected false merge.

A fabricated person in a transplant database is a person matched to a stranger's
kidney, so every test here is about what the module REFUSES.
"""

from __future__ import annotations

import pytest

from kidneymatch.domain.entity_resolution import (
    Fingerprint,
    LinkTier,
    load_frequencies,
    match_probability,
    propose_link,
    salted_hash,
)

pytestmark = pytest.mark.task("ENTITY-001")


@pytest.fixture(scope="module")
def frequencies():
    return load_frequencies()


def fingerprint(**loci: str) -> Fingerprint:
    return Fingerprint(genotypes=dict(loci))


# --- the arithmetic -------------------------------------------------------


def test_one_locus_identifies_almost_nothing(frequencies) -> None:
    """DQB1 alone: one document in ten matches by chance."""
    probability = match_probability(
        fingerprint(DQB1="03 05"), fingerprint(DQB1="03 05"), frequencies
    )
    assert 0.05 < probability < 0.2


def test_the_probability_is_the_product_over_shared_loci(frequencies) -> None:
    shared = fingerprint(A="02 24", B="35 51", DRB1="11 15")
    probability = match_probability(shared, shared, frequencies)
    assert probability == pytest.approx(
        frequencies["A"] * frequencies["B"] * frequencies["DRB1"], rel=1e-9
    )


def test_a_locus_only_one_side_resolved_contributes_nothing(frequencies) -> None:
    """Absence of evidence is not evidence. A locus the other document never
    reported cannot make the pair more likely to be one person."""
    both = fingerprint(A="02 24", B="35 51")
    one_sided = fingerprint(A="02 24", B="35 51", DRB1="11 15")
    assert match_probability(both, one_sided, frequencies) == pytest.approx(
        match_probability(both, both, frequencies), rel=1e-9
    )


def test_a_disagreeing_locus_makes_the_pair_impossible(frequencies) -> None:
    """One locus read differently is not a weaker match: it is a different
    person, or a misreading. Either way it is not a link."""
    a = fingerprint(A="02 24", B="35 51", DRB1="11 15")
    b = fingerprint(A="02 24", B="35 51", DRB1="04 07")
    assert match_probability(a, b, frequencies) is None


# --- what the score is allowed to do --------------------------------------


@pytest.mark.invariant("ENTITY-001", "HLA similarity alone never merges people")
def test_hla_alone_never_auto_links_however_improbable(frequencies) -> None:
    """The doctrine's rule, and the arithmetic agrees with it. Even five loci
    matching — 1 in 86 million — is a review candidate and nothing more."""
    five = fingerprint(A="02 24", B="35 51", C="04 07", DRB1="11 15", DQB1="03 05")
    link = propose_link(five, five, frequencies)
    assert link is not None
    assert link.tier is LinkTier.REVIEW_CANDIDATE
    assert link.auto_linkable is False


def test_a_weak_fingerprint_proposes_nothing_at_all(frequencies) -> None:
    """A queue that holds every coincidence is a queue nobody reads. A+DQB1 is
    about 1 in 550, which over this corpus is ~90,000 coincidental pairs."""
    weak = fingerprint(A="02 24", DQB1="03 05")
    assert propose_link(weak, weak, frequencies) is None


def test_a_non_hla_identifier_is_what_makes_a_link_automatic(frequencies) -> None:
    """The sender is evidence about who posted, and posting the same report
    twice is the commonest duplication in this archive. HLA then CONFIRMS."""
    four = fingerprint(A="02 24", B="35 51", C="04 07", DRB1="11 15")
    link = propose_link(four, four, frequencies, same_sender=True)
    assert link.tier is LinkTier.SAME_SENDER
    assert link.auto_linkable is True


def test_a_sender_alone_does_not_link_two_different_people(frequencies) -> None:
    """A broker posts for many patients. Same sender is not same subject."""
    a = fingerprint(A="02 24", B="35 51", DRB1="11 15")
    b = fingerprint(A="01 03", B="07 08", DRB1="04 07")
    assert propose_link(a, b, frequencies, same_sender=True) is None


# --- conflicts block, they do not weaken ----------------------------------


@pytest.mark.parametrize(
    ("field", "left", "right"),
    [("abo", "O", "A"), ("role", "DONOR", "RECIPIENT")],
)
@pytest.mark.invariant(
    "ENTITY-001", "a conflicting blood group or role blocks a link rather than weakening it"
)
def test_a_conflicting_document_fact_blocks_the_link(frequencies, field, left, right) -> None:
    """Two blood groups on one person is a contradiction, not a weak signal.
    It stops the link and goes to a person."""
    five = fingerprint(A="02 24", B="35 51", C="04 07", DRB1="11 15", DQB1="03 05")
    link = propose_link(five, five, frequencies, same_sender=True, **{field: (left, right)})
    assert link.tier is LinkTier.BLOCKED
    assert link.auto_linkable is False
    assert field in link.reason


def test_an_unknown_on_one_side_is_not_a_conflict(frequencies) -> None:
    five = fingerprint(A="02 24", B="35 51", C="04 07", DRB1="11 15", DQB1="03 05")
    link = propose_link(five, five, frequencies, same_sender=True, abo=("O", None))
    assert link.tier is LinkTier.SAME_SENDER


# --- names (HA-005) -------------------------------------------------------


@pytest.mark.invariant("ENTITY-001", "the printed name is stored only as a salted hash")
def test_a_name_is_stored_only_as_a_salted_hash() -> None:
    """HA-005, decided 2026-09-03: the name field is the highest-exposure item
    in the archive and contributes nothing to compatibility. It is kept as a
    hash so it can link, and never as text."""
    digest = salted_hash("مریم", salt="a-secret-salt")
    assert digest != "مریم"
    assert len(digest) == 32
    assert salted_hash("مریم", salt="a-secret-salt") == digest
    assert salted_hash("مریم", salt="another-salt") != digest


def test_hashing_refuses_to_run_without_a_salt() -> None:
    """An unsalted hash of a short name list is reversible by brute force, so
    it would be plaintext wearing a costume."""
    with pytest.raises(ValueError, match="salt"):
        salted_hash("مریم", salt="")


def test_a_name_hash_is_never_sufficient_on_its_own(frequencies) -> None:
    """Two people share a name, and the name field is the most misread field on
    the form. It corroborates; it does not conclude."""
    a = fingerprint(A="02 24", B="35 51", DRB1="11 15")
    b = fingerprint(A="01 03", B="07 08", DRB1="04 07")
    assert propose_link(a, b, frequencies, same_name_hash=True) is None


# --- the module refuses to run on guesses ---------------------------------


def test_two_documents_sharing_no_locus_are_not_a_pair(frequencies) -> None:
    """Nothing in common is not a weak match; there is no evidence at all."""
    assert match_probability(fingerprint(A="02 24"), fingerprint(DRB1="11 15"), frequencies) is None
    assert propose_link(fingerprint(A="02 24"), fingerprint(DRB1="11 15"), frequencies) is None


def test_a_name_hash_link_names_the_name_hash_as_its_evidence(frequencies) -> None:
    """Provenance: a merge a reviewer cannot trace is a merge they cannot undo."""
    four = fingerprint(A="02 24", B="35 51", C="04 07", DRB1="11 15")
    link = propose_link(four, four, frequencies, same_name_hash=True)
    assert link.tier is LinkTier.SAME_NAME_HASH
    assert link.auto_linkable is True
    assert "name" in link.reason


def test_missing_frequencies_are_fatal(tmp_path) -> None:
    """Every threshold here is stated in terms of the measured table. Guessing
    one would silently change who gets merged with whom."""
    from kidneymatch.domain.entity_resolution import FrequenciesUnavailable

    with pytest.raises(FrequenciesUnavailable, match="missing"):
        load_frequencies(tmp_path / "absent.json")


def test_frequencies_of_the_wrong_schema_are_refused(tmp_path) -> None:
    import json as _json

    path = tmp_path / "f.json"
    path.write_text(_json.dumps({"schema": "other/v1", "loci": {}}), encoding="utf-8")
    from kidneymatch.domain.entity_resolution import FrequenciesUnavailable

    with pytest.raises(FrequenciesUnavailable):
        load_frequencies(path)
