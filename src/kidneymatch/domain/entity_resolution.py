"""Deciding when two documents describe one person — and mostly deciding not to.

`ENTITY-001`. The archive is per image and matching needs it per person: 10,032
documents carry about 4,246 distinct HLA fingerprints, and the most repeated one
appears on 67 documents. Those repeats are real — within a locus set, identical
pairs run 177 to 1,982 times above chance, and the largest groups are internally
consistent on role and blood group. People repost.

## Why the obvious rule is unsafe

Measured (`config/locus_genotype_frequencies.json`), the chance two unrelated
documents share a first-field genotype:

    DQB1 1 in 10    C 1 in 40    DRB1 1 in 44    A 1 in 55    B 1 in 90

10,032 documents make 50.3 million pairs, so **any per-pair probability above
2e-8 gives an expected false merge**. "Identical on three loci" reaches 1 in
22,000 to 1 in 218,000 for the triples that occur — on the order of 200 to 2,300
coincidental pairs corpus-wide.

A fabricated person in a transplant database is a person matched to a stranger's
kidney. So:

* **HLA never auto-links, at any probability.** It scores a link, and a score
  only ever proposes a review candidate.
* **A non-HLA identifier is what makes a link automatic** — the sender who
  posted both, or (HA-005) a salted hash of the printed name. HLA then confirms.
* **A conflict blocks.** Two blood groups or two roles is a contradiction, not
  a weaker match, and it goes to a person rather than being averaged away.

That is `DEDUPE-001`'s invariant "HLA similarity alone never merges people",
stated as arithmetic rather than as a preference.

## Names (HA-005, decided 2026-09-03)

The printed name is the highest-exposure item in the archive and contributes
nothing to compatibility. It is kept as a **salted hash**: enough to link the
same person's repeated posts, not enough to read. `salted_hash` refuses to run
without a salt, because an unsalted hash over a short name distribution is
reversible by brute force and would be plaintext wearing a costume.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

FREQUENCIES_SCHEMA = "locus-genotype-frequencies/v1"
DEFAULT_FREQUENCIES = Path(__file__).resolve().parents[3] / "config/locus_genotype_frequencies.json"

# A link this improbable by chance is worth a person's time. Below it, the
# corpus would produce more coincidences than real pairs and the queue becomes
# unreadable. A+B+DRB1 is 1 in 218,000 and qualifies; A+DQB1, at 1 in 550,
# does not.
MAX_COINCIDENCE = 1e-5

# Even the most improbable fingerprint match stays a proposal. Stated as a
# constant so that the intent is greppable, not so that it can be tuned.
HLA_ALONE_EVER_AUTO_LINKS = False


class FrequenciesUnavailable(RuntimeError):
    """The measured genotype frequencies are missing.

    Fatal on purpose: every threshold here is stated in terms of them, and
    guessing them would silently change who gets merged with whom.
    """


class LinkTier(StrEnum):
    """What kind of evidence supports this link."""

    SAME_SENDER = "SAME_SENDER"
    SAME_NAME_HASH = "SAME_NAME_HASH"
    REVIEW_CANDIDATE = "REVIEW_CANDIDATE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class Fingerprint:
    """One document's resolved first-field genotypes, order-independent."""

    genotypes: dict[str, str] = field(default_factory=dict)

    def shared_loci(self, other: Fingerprint) -> list[str]:
        return sorted(set(self.genotypes) & set(other.genotypes))


@dataclass(frozen=True, slots=True)
class ProposedLink:
    """A proposal. Nothing here merges anything by itself."""

    tier: LinkTier
    auto_linkable: bool
    probability: float | None
    shared_loci: tuple[str, ...]
    reason: str


def load_frequencies(path: Path | None = None) -> dict[str, float]:
    """Per-locus probability that two unrelated documents match."""
    source = path or DEFAULT_FREQUENCIES
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except OSError as error:
        raise FrequenciesUnavailable(
            f"{source} is missing; run scripts/build_genotype_frequencies.py"
        ) from error
    if payload.get("schema") != FREQUENCIES_SCHEMA:
        raise FrequenciesUnavailable(f"{source} is not {FREQUENCIES_SCHEMA}")
    return {
        locus: float(stats["match_probability"]) for locus, stats in payload.get("loci", {}).items()
    }


def match_probability(
    left: Fingerprint, right: Fingerprint, frequencies: dict[str, float]
) -> float | None:
    """The chance two unrelated documents would agree this well.

    `None` when a shared locus DISAGREES: that is not a weaker match, it is a
    different person or a misreading, and either way there is no link to score.
    """
    shared = left.shared_loci(right)
    if not shared:
        return None
    probability = 1.0
    for locus in shared:
        if left.genotypes[locus] != right.genotypes[locus]:
            return None
        probability *= frequencies.get(locus, 1.0)
    return probability


def propose_link(
    left: Fingerprint,
    right: Fingerprint,
    frequencies: dict[str, float],
    *,
    same_sender: bool = False,
    same_name_hash: bool = False,
    abo: tuple[str | None, str | None] = (None, None),
    role: tuple[str | None, str | None] = (None, None),
) -> ProposedLink | None:
    """Propose a link between two documents, or decline to.

    Returns `None` when there is nothing worth a person's attention. A
    non-HLA identifier can make a link automatic, but only while the HLA also
    agrees: a broker posts for many patients, so the same sender alone is not
    the same subject.
    """
    probability = match_probability(left, right, frequencies)
    if probability is None:
        return None

    shared = tuple(left.shared_loci(right))
    conflicts = []
    for name, (a, b) in (("abo", abo), ("role", role)):
        if a is not None and b is not None and a != b:
            conflicts.append(f"{name} conflict: {a} against {b}")

    corroborated = same_sender or same_name_hash
    if not corroborated and probability > MAX_COINCIDENCE:
        # Too likely by chance to be worth reading, and far too likely to merge.
        return None

    if conflicts:
        return ProposedLink(
            tier=LinkTier.BLOCKED,
            auto_linkable=False,
            probability=probability,
            shared_loci=shared,
            reason="; ".join(conflicts) + " — a contradiction goes to a person",
        )

    if same_sender:
        return ProposedLink(
            tier=LinkTier.SAME_SENDER,
            auto_linkable=True,
            probability=probability,
            shared_loci=shared,
            reason=(
                f"the same sender posted both and the HLA agrees on {'+'.join(shared)} "
                f"(1 in {round(1 / probability):,} by chance)"
            ),
        )
    if same_name_hash:
        return ProposedLink(
            tier=LinkTier.SAME_NAME_HASH,
            auto_linkable=True,
            probability=probability,
            shared_loci=shared,
            reason=(
                f"the printed name hashes alike and the HLA agrees on {'+'.join(shared)} "
                f"(1 in {round(1 / probability):,} by chance)"
            ),
        )

    return ProposedLink(
        tier=LinkTier.REVIEW_CANDIDATE,
        auto_linkable=HLA_ALONE_EVER_AUTO_LINKS,
        probability=probability,
        shared_loci=shared,
        reason=(
            f"HLA agrees on {'+'.join(shared)} (1 in {round(1 / probability):,} by chance), "
            "and HLA alone never merges people"
        ),
    )


def salted_hash(value: str, *, salt: str, digest_size: int = 16) -> str:
    """A name, kept only as something that can be compared.

    HA-005. The salt lives in the secret store and never in this repository; an
    unsalted hash over the distribution of Iranian given names is reversible by
    brute force in seconds.
    """
    if not salt:
        raise ValueError("a name hash without a salt is reversible; refusing to produce one")
    normalised = " ".join(value.split()).casefold()
    return hashlib.blake2b(
        normalised.encode("utf-8"), salt=salt.encode("utf-8")[:16], digest_size=digest_size
    ).hexdigest()
