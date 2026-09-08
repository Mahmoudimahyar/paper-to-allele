"""Run the pre-screen ranking over the Gold database.

`MATCH-001`. Policy: `docs/clinical/MATCHING_POLICY_V2.md`.

Two modes, and the default is the safe one:

    python scripts/rank_matches.py --summary
        Aggregate only: how many profiles are rankable, the distribution of KM
        levels and buckets over a sample. Prints no allele value and no profile
        identifier. This is what may appear in a transcript, a log or a report.

    python scripts/rank_matches.py --recipient <profile_id> --top 10
        One query, for an operator at a terminal. Prints mismatch counts and
        profile identifiers, so its output is medical data: it must not be
        pasted anywhere the archive itself would not go.

The policy is not adopted (HA-004), so every run says so. The script refuses to
present a result as clinically usable while `status` is `DESIGN_NOT_ADOPTED`.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kidneymatch.matching.abo import AboProvenance  # noqa: E402
from kidneymatch.matching.core import (  # noqa: E402
    Profile,
    Role,
    rank_donors_for,
    rank_recipients_for,
)
from kidneymatch.matching.policy import load_policy  # noqa: E402

GOLD = ROOT / "data" / "gold" / "gold.sqlite"
HLA_LOCI = ("A", "B", "C", "DRB1", "DQB1", "DQA1")
PRESENCE = ("DRB3", "DRB4", "DRB5")


def load_profiles(path: Path) -> dict[str, Profile]:
    """Read every Gold profile into the frozen view ranking may see.

    Only the fields matching is allowed to consider are read. Compensation is
    not in the Gold schema at all, and no query here could reach it.
    """
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    hla: dict[str, dict[str, tuple[str | None, str | None]]] = {}
    presence: dict[str, dict[str, str]] = {}
    tiers: dict[str, dict[str, str]] = {}
    role: dict[str, str] = {}
    abo: dict[str, str] = {}

    for pid, field, value, second, tier in con.execute(
        "SELECT profile_id, field, value, second_allele, tier FROM gold_fact"
    ):
        if field in HLA_LOCI:
            hla.setdefault(pid, {})[field] = (value, second)
            tiers.setdefault(pid, {})[field] = tier or "C"
        elif field in PRESENCE:
            presence.setdefault(pid, {})[field] = (value or "UNKNOWN").upper()
        elif field == "ROLE":
            role[pid] = value or "UNKNOWN"
        elif field == "ABO":
            abo[pid] = value

    # Sorted, because set iteration order for strings varies between processes
    # (hash randomisation) and the sample below must not move run to run.
    ids = sorted(set(hla) | set(role) | set(abo))
    profiles: dict[str, Profile] = {}
    for pid in ids:
        raw_role = role.get(pid, "UNKNOWN").upper()
        profiles[pid] = Profile(
            profile_id=pid,
            role=Role(raw_role) if raw_role in Role.__members__ else Role.UNKNOWN,
            hla=hla.get(pid, {}),
            presence=presence.get(pid, {}),
            abo=abo.get(pid),
            # The dominant letterhead disclaims the blood group (KI-014), so a
            # Gold ABO is treated as patient-reported unless a later pass proves
            # it was laboratory-measured. That keeps pairs in PROVISIONAL_ABO
            # rather than clearing them on evidence that may not clear.
            abo_provenance=(
                AboProvenance.PATIENT_REPORTED_ON_FORM if pid in abo else AboProvenance.UNKNOWN
            ),
            tiers=tiers.get(pid, {}),
        )
    con.close()
    return profiles


def _summary(profiles: dict[str, Profile], sample: int) -> int:
    policy = load_policy()
    donors = [p for p in profiles.values() if p.role is Role.DONOR]
    recipients = [p for p in profiles.values() if p.role is Role.RECIPIENT]
    unknown = [p for p in profiles.values() if p.role is Role.UNKNOWN]

    print(f"policy      : {policy.policy_id}  adopted={policy.is_adopted}")
    print(f"profiles    : {len(profiles):,}")
    print(f"  donors    : {len(donors):,}")
    print(f"  recipients: {len(recipients):,}")
    print(f"  role unknown (in neither direction): {len(unknown):,}")

    typed = [p for p in recipients if _fully_typed(p)]
    print(f"\nrecipients fully typed at A, B and DRB1: {len(typed):,}")
    if not typed:
        return 0

    step = max(1, len(typed) // sample)
    chosen = typed[::step][:sample]
    buckets: Counter[str] = Counter()
    levels: Counter[int] = Counter()
    top_levels: Counter[int] = Counter()
    sizes: list[int] = []

    for recipient in chosen:
        rows = rank_donors_for(recipient, donors, policy=policy)
        ranked = [r for r in rows if r.bucket.is_ranked]
        sizes.append(len(ranked))
        for row in rows:
            buckets[row.bucket.value] += 1
        for row in ranked:
            levels[row.key.km_level] += 1
        if ranked:
            top_levels[ranked[0].key.km_level] += 1

    print(f"\nsampled {len(chosen)} recipients against {len(donors):,} donors")
    print(
        f"ranked donors per recipient: min {min(sizes):,} median "
        f"{sorted(sizes)[len(sizes) // 2]:,} max {max(sizes):,}"
    )
    print("\nbucket distribution over all evaluated pairs:")
    total = sum(buckets.values())
    for name, n in buckets.most_common():
        print(f"   {name:<28} {n:>9,}  {100 * n / total:5.1f}%")
    print("\nKM level distribution over ranked pairs:")
    for level in sorted(levels):
        print(f"   KM-{level}  {levels[level]:>9,}")
    print("\nbest level reached, per sampled recipient:")
    for level in sorted(top_levels):
        print(f"   KM-{level}  {top_levels[level]:>4} recipients")
    return 0


def _fully_typed(p: Profile) -> bool:
    from kidneymatch.matching.mismatch import LocusTyping

    return all(p.locus(x).typing is LocusTyping.BOTH for x in ("A", "B", "DRB1"))


def _one_query(profiles: dict[str, Profile], pid: str, top: int, reverse: bool) -> int:
    policy = load_policy()
    anchor = profiles.get(pid)
    if anchor is None:
        print(f"no profile {pid!r}", file=sys.stderr)
        return 2
    if not policy.is_adopted:
        print(
            "WARNING: matching policy "
            f"{policy.policy_id} is {policy.status}. This ordering is a "
            "pre-screen proposal, not a clinical finding, and HA-004 is open.\n"
        )
    if reverse:
        rows = rank_recipients_for(anchor, [p for p in profiles.values()], policy=policy)
        other = "recipient"
    else:
        rows = rank_donors_for(anchor, [p for p in profiles.values()], policy=policy)
        other = "donor"

    ranked = [r for r in rows if r.bucket.is_ranked][:top]
    print(f"{other:<12}{'bucket':<20}{'level':<8}{'penalty':>8}   mismatches (A/B/DRB1/DQB1)")
    for row in ranked:
        mm = "/".join(str(row.vector.per_locus[x]) for x in ("A", "B", "DRB1", "DQB1"))
        print(
            f"{row.candidate_id:<12}{row.bucket.value:<20}"
            f"KM-{row.key.km_level:<5}{row.key.penalty:>8}   {mm}"
        )
    blocked = Counter(r.bucket.value for r in rows if not r.bucket.is_ranked)
    if blocked:
        print("\nnot ranked:", dict(blocked))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, default=GOLD)
    parser.add_argument("--summary", action="store_true", help="aggregate only, no identifiers")
    parser.add_argument("--sample", type=int, default=25)
    parser.add_argument("--recipient", help="rank donors for this profile id")
    parser.add_argument("--donor", help="rank recipients for this profile id")
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args(argv)

    if not args.gold.exists():
        print(f"no Gold database at {args.gold}", file=sys.stderr)
        return 2
    profiles = load_profiles(args.gold)

    if args.recipient:
        return _one_query(profiles, args.recipient, args.top, reverse=False)
    if args.donor:
        return _one_query(profiles, args.donor, args.top, reverse=True)
    return _summary(profiles, args.sample)


if __name__ == "__main__":
    raise SystemExit(main())
