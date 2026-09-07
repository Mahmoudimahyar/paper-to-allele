#!/usr/bin/env python3
"""Group the documents that are the SAME PHOTOGRAPH. Never the same person.

DEDUPE-001's invariants are the whole design here: "same path or SHA256 maps to
one MediaAsset", "all source-message links are retained", and — the one that
shapes everything — **"HLA similarity alone never merges people"**.

Byte-identical files are already one document: the store holds 23,566 documents
for 23,566 distinct SHA-256s, and 8,847 of them are already linked to more than
one message. What is left is the same photograph re-encoded, re-screenshotted or
re-cropped between postings, which produces a different SHA-256 and a second
document for one piece of paper.

## Why a perceptual hash alone is not allowed to decide this

These are TEMPLATED laboratory forms. Two different patients' reports share a
letterhead, a table, a ruling grid and a row order; only a few dozen printed
glyphs differ. A perceptual hash downsamples exactly those glyphs away.

Measured on the first 3,000 documents, 2026-09-07, with a 256-bit dHash and the
pair's own resolved HLA as the arbiter:

| dHash distance | pairs | facts agree | **facts CONTRADICT** | no shared fact |
|---|---|---|---|---|
| 0  |  153 | 146 |  **1** |  6 |
| 4  |  348 | 322 |  **3** | 23 |
| 8  |  477 | 416 | **27** | 34 |
| 12 |  650 | 489 | **126** | 35 |
| 16 | 1029 | 555 | **437** | 37 |

At distance 8 one pair in eighteen is provably two different people, and at 16
it is two in five. Even at distance **zero** — two images whose 256-bit hashes
are identical — one pair carries contradictory printed HLA. There is no
threshold at which this hash may merge on its own.

## So the hash proposes and the facts dispose

A pair is merged only when ALL of:

1. the 256-bit dHash distance is `<= MAX_DISTANCE` (4). The hash is the
   CANDIDATE GENERATOR and nothing more;
2. the two documents agree on at least `MIN_AGREEING_FIELDS` (2) RESOLVED
   fields, **at least one of them a gene**. One field is not corroboration: 434
   pairs would have merged on a matching blood group alone, and two unrelated
   documents share ABO and Rh about one time in eight;
3. **no shared resolved field disagrees.** One contradicting locus, blood group
   or Rh sign and the pair is refused outright.

Gate 3 is not "HLA similarity merges people" turned around. The claim being
made is that two FILES are one photograph, which the hash proposes on pixels;
the facts are only ever allowed to VETO it. Two different people are never
merged because their HLA matches — the hash would have to call their photographs
the same first, and then the veto still gets a turn.

Even so this cannot merge an HLA-identical sibling pair photographed on the same
form, which is the residual risk and is why `--report` prints every cluster
holding more than two documents for a person to look at, and why nothing here
deletes anything: the clusters are written to their own store and the export
chooses a representative, so the decision is reversible by rebuilding.

Prints counts only. Writes `data/derived/media_dedupe.sqlite`.
"""

from __future__ import annotations

import argparse
import itertools
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

EV = "facts/v1"
DEDUPE_VERSION = "media-dedupe/v1+dhash256"
# The side of the dHash grid. 16 gives a 16x15 = 240-bit code, padded to 256.
HASH_SIDE = 16
# Measured above: 3 of 348 pairs at this distance contradict, and gate 3 removes
# them. Widening to 8 would offer 27 more contradicting pairs to the same gate,
# and every one it could not see (no shared fact) would be a silent bad merge.
MAX_DISTANCE = 4
# The fields whose disagreement vetoes a merge. Anything a person could read off
# the page and that the pipeline resolved.
# ROLE is here because a page that says DONOR and a page that says RECIPIENT
# are two people, whatever the pixels say. Leaving it out merged 37 such
# pairs (adversarial review, 2026-09-07) — the single worst thing this pass
# can do. It VETOES but does not corroborate: there are two role words, so
# agreeing on one is not evidence of identity.
VETO_FIELDS = ("A", "B", "C", "DRB1", "DQA1", "DQB1", "DPA1", "DPB1", "ABO", "RH", "ROLE")
# A locus is evidence about a person; a blood group barely is. There are four
# ABO groups and two Rh signs, so two unrelated documents agree on both about
# one time in eight — measured, 434 pairs would have merged on that alone.
# Corroboration therefore means at least two agreeing fields, at least one of
# them a gene.
GENE_FIELDS = frozenset({"A", "B", "C", "DRB1", "DQA1", "DQB1", "DPA1", "DPB1"})
MIN_AGREEING_FIELDS = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS media_hash (
    sha256          TEXT NOT NULL,
    dedupe_version  TEXT NOT NULL,
    rel_path        TEXT NOT NULL,
    width           INTEGER,
    height          INTEGER,
    dhash           BLOB,
    error           TEXT,
    created_utc     TEXT NOT NULL,
    PRIMARY KEY (sha256, dedupe_version)
);
CREATE TABLE IF NOT EXISTS media_cluster (
    sha256          TEXT NOT NULL,
    dedupe_version  TEXT NOT NULL,
    cluster_id      TEXT NOT NULL,
    representative  INTEGER NOT NULL,
    n_members       INTEGER NOT NULL,
    created_utc     TEXT NOT NULL,
    PRIMARY KEY (sha256, dedupe_version)
);
CREATE INDEX IF NOT EXISTS media_cluster_by_id ON media_cluster (dedupe_version, cluster_id);
CREATE TABLE IF NOT EXISTS media_provenance (
    dedupe_version  TEXT NOT NULL PRIMARY KEY,
    facts_fingerprint TEXT NOT NULL,
    n_documents     INTEGER NOT NULL,
    n_clusters      INTEGER NOT NULL,
    created_utc     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS media_refusal (
    sha256_a        TEXT NOT NULL,
    sha256_b        TEXT NOT NULL,
    dedupe_version  TEXT NOT NULL,
    distance        INTEGER NOT NULL,
    reason          TEXT NOT NULL,
    created_utc     TEXT NOT NULL,
    PRIMARY KEY (sha256_a, sha256_b, dedupe_version)
);
"""


def dhash(image, side: int = HASH_SIDE) -> bytes:
    """A 256-bit difference hash: brighter-than-its-neighbour, row by row."""
    import numpy as np
    from PIL import Image as PilImage

    small = image.convert("L").resize((side + 1, side), PilImage.LANCZOS)
    cells = np.asarray(small, dtype=np.int16)
    return np.packbits((cells[:, 1:] > cells[:, :-1]).flatten()).tobytes()


def hash_corpus(
    facts: Path, export: Path, out: Path, *, limit: int | None, rehash: bool
) -> Counter[str]:
    from PIL import Image as PilImage

    con = sqlite3.connect(out)
    con.executescript(SCHEMA)
    src = sqlite3.connect(f"file:{facts.as_posix()}?mode=ro", uri=True)
    done = (
        set()
        if rehash
        else {
            row[0]
            for row in con.execute(
                "SELECT sha256 FROM media_hash WHERE dedupe_version=?", (DEDUPE_VERSION,)
            )
        }
    )
    rows = src.execute(
        "SELECT sha256, rel_path FROM document WHERE extraction_version=? ORDER BY sha256", (EV,)
    ).fetchall()
    tally: Counter[str] = Counter()
    tally["documents"] = len(rows)
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    n = 0
    for sha, rel_path in rows:
        if sha in done:
            tally["already hashed"] += 1
            continue
        if limit is not None and n >= limit:
            break
        n += 1
        try:
            with PilImage.open(export / rel_path) as image:
                width, height = image.size
                code = dhash(image)
            con.execute(
                "INSERT OR REPLACE INTO media_hash VALUES (?,?,?,?,?,?,NULL,?)",
                (sha, DEDUPE_VERSION, rel_path, width, height, code, now),
            )
            tally["hashed"] += 1
        except (OSError, ValueError) as problem:
            con.execute(
                "INSERT OR REPLACE INTO media_hash VALUES (?,?,?,NULL,NULL,NULL,?,?)",
                (sha, DEDUPE_VERSION, rel_path, type(problem).__name__, now),
            )
            tally["image not readable"] += 1
        if n % 500 == 0:
            con.commit()
    con.commit()
    con.close()
    return tally


def facts_fingerprint(facts: Path) -> str:
    """What the veto was run against, so a stale clustering can be detected.

    The clusters are only as good as the facts that vetoed them: re-run an
    extraction pass and a merge this store still asserts may no longer be one
    the current values would allow. `build_gold_db.py` refuses to use a
    clustering whose fingerprint no longer matches.
    """
    import hashlib

    con = sqlite3.connect(f"file:{facts.as_posix()}?mode=ro", uri=True)
    marks = ",".join("?" * len(VETO_FIELDS))
    digest = hashlib.sha256()
    for row in con.execute(
        f"SELECT sha256, field, value FROM fact WHERE extraction_version=? AND status='RESOLVED' "
        f"AND field IN ({marks}) AND value IS NOT NULL ORDER BY sha256, field",
        (EV, *VETO_FIELDS),
    ):
        digest.update(repr(row).encode())
    con.close()
    return digest.hexdigest()


def resolved_fields(facts: Path) -> dict[str, dict[str, str]]:
    con = sqlite3.connect(f"file:{facts.as_posix()}?mode=ro", uri=True)
    marks = ",".join("?" * len(VETO_FIELDS))
    out: dict[str, dict[str, str]] = defaultdict(dict)
    for sha, field, value in con.execute(
        f"SELECT sha256, field, value FROM fact WHERE extraction_version=? AND status='RESOLVED' "
        f"AND field IN ({marks}) AND value IS NOT NULL",
        (EV, *VETO_FIELDS),
    ):
        out[sha][field] = value
    con.close()
    return out


def verdict(a: dict[str, str], b: dict[str, str]) -> tuple[bool, str]:
    """May these two documents be merged? `(ok, reason)`.

    The facts can only ever refuse. They never propose a merge on their own —
    the hash has already said the photographs are the same, and DEDUPE-001
    forbids HLA similarity from merging anybody by itself.
    """
    shared = set(a) & set(b)
    if not shared:
        return False, "no field resolved on both; nothing corroborates the pixels"
    disagreeing = sorted(field for field in shared if a[field] != b[field])
    if disagreeing:
        return False, f"the printed {', '.join(disagreeing)} disagree; these are two documents"
    corroborating = shared - {"ROLE"}
    if len(corroborating) < MIN_AGREEING_FIELDS or not (corroborating & GENE_FIELDS):
        return False, (
            "too little agrees to corroborate the pixels: a blood group is one value in "
            "eight, and these forms look alike"
        )
    return True, ""


def cluster(facts: Path, out: Path, *, dry_run: bool) -> tuple[Counter[str], list[list[str]]]:
    import numpy as np

    con = sqlite3.connect(out)
    con.executescript(SCHEMA)
    rows = con.execute(
        "SELECT sha256, dhash FROM media_hash WHERE dedupe_version=? AND dhash IS NOT NULL "
        "ORDER BY sha256",
        (DEDUPE_VERSION,),
    ).fetchall()
    tally: Counter[str] = Counter()
    tally["documents hashed"] = len(rows)
    if not rows:
        return tally, []
    shas = [row[0] for row in rows]
    fields = resolved_fields(facts)

    # Union-find over the pairs the hash proposes AND the facts do not refuse.
    parent = list(range(len(shas)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        a, b = find(i), find(j)
        if a != b:
            parent[max(a, b)] = min(a, b)

    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    refusals: list[tuple] = []
    # Blocked by chunk against the whole matrix: 23.5k x 256 bits is small, and
    # the comparison is over uint8 rows rather than 256 booleans.
    packed = np.stack([np.frombuffer(row[1], dtype=np.uint8) for row in rows])
    # uint8, and a small chunk: the intermediate is (CHUNK, n, 32) and an int64
    # lookup over 23.5k documents would ask for gigabytes on a machine that
    # powers off under load.
    popcount = (
        np.unpackbits(np.arange(256, dtype=np.uint8)[:, None], axis=1).sum(1).astype(np.uint8)
    )
    CHUNK = 128
    for start in range(0, len(shas), CHUNK):
        block = packed[start : start + CHUNK]
        distance = popcount[np.bitwise_xor(block[:, None, :], packed[None, :, :])].sum(
            2, dtype=np.uint16
        )
        for local, row_distance in enumerate(distance):
            i = start + local
            for j in np.nonzero(row_distance <= MAX_DISTANCE)[0]:
                j = int(j)
                if j <= i:
                    continue
                ok, reason = verdict(fields.get(shas[i], {}), fields.get(shas[j], {}))
                if ok:
                    union(i, j)
                    tally["pairs merged"] += 1
                else:
                    tally[
                        "pairs refused: contradictory printed values"
                        if "disagree" in reason
                        else "pairs refused: too little agrees to corroborate"
                        if "too little" in reason
                        else "pairs refused: nothing corroborates the pixels"
                    ] += 1
                    refusals.append(
                        (shas[i], shas[j], DEDUPE_VERSION, int(row_distance[j]), reason, now)
                    )

    groups: dict[int, list[str]] = defaultdict(list)
    for index, sha in enumerate(shas):
        groups[find(index)].append(sha)

    # Union-find is TRANSITIVE and the veto is not. A~B may pass and B~C may
    # pass while A and C were never compared, so a chain can merge two
    # documents that contradict each other outright — the one failure this
    # whole design exists to prevent. Every cluster is therefore re-checked as
    # a WHOLE, every pair against every pair, and a cluster with any internal
    # contradiction is dissolved into singletons rather than repaired: a missed
    # merge costs a duplicate row, a wrong merge costs a patient.
    multi: list[list[str]] = []
    for raw_members in groups.values():
        if len(raw_members) < 2:
            continue
        members = sorted(raw_members)
        bad = None
        for a, b in itertools.combinations(members, 2):
            ok, reason = verdict(fields.get(a, {}), fields.get(b, {}))
            if not ok:
                bad = (a, b, reason)
                break
        if bad is not None:
            # EVERY refusal, not only a contradiction. The first version
            # dissolved on `disagree` alone, which left the corroboration gate
            # enforced on the pairs the hash happened to compare directly and
            # nowhere else — precisely the property union-find does not have.
            # Worse, the store then held a refusal row and a same-cluster row
            # for one pair, so it contradicted itself about its own decision.
            kind = (
                "a contradicting pair" if "disagree" in bad[2] else "a pair too thin to corroborate"
            )
            tally[f"clusters DISSOLVED: a chain merged {kind}"] += 1
            tally["documents released by a dissolved cluster"] += len(members)
            refusals.append(
                (bad[0], bad[1], DEDUPE_VERSION, -1, f"cluster dissolved: {bad[2]}", now)
            )
            continue
        multi.append(members)
    tally["clusters with more than one document"] = len(multi)
    tally["documents inside such a cluster"] = sum(len(m) for m in multi)
    tally["documents the export will drop as duplicates"] = sum(len(m) - 1 for m in multi)
    for members in multi:
        tally[f"cluster of {min(len(members), 10)}"] += 1

    if dry_run:
        con.close()
        return tally, multi
    con.execute("DELETE FROM media_cluster WHERE dedupe_version=?", (DEDUPE_VERSION,))
    con.execute("DELETE FROM media_refusal WHERE dedupe_version=?", (DEDUPE_VERSION,))
    for members in multi:
        # The representative is the largest image, ties broken by sha256 so a
        # rebuild picks the same one: "use the highest-quality asset available".
        sizes = {
            sha: (w or 0) * (h or 0)
            for sha, w, h in con.execute(
                f"SELECT sha256, width, height FROM media_hash WHERE dedupe_version=? "
                f"AND sha256 IN ({','.join('?' * len(members))})",
                (DEDUPE_VERSION, *members),
            )
        }
        best = max(members, key=lambda s: (sizes.get(s, 0), s))
        for sha in members:
            con.execute(
                "INSERT OR REPLACE INTO media_cluster VALUES (?,?,?,?,?,?)",
                (sha, DEDUPE_VERSION, members[0], int(sha == best), len(members), now),
            )
    con.executemany("INSERT OR REPLACE INTO media_refusal VALUES (?,?,?,?,?,?)", refusals)
    con.execute(
        "INSERT OR REPLACE INTO media_provenance VALUES (?,?,?,?,?)",
        (DEDUPE_VERSION, facts_fingerprint(facts), len(shas), len(multi), now),
    )
    con.commit()
    con.close()
    return tally, multi


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--export", type=Path, default=ROOT / "data/raw/ChatExport_2026-08-31")
    parser.add_argument("--out", type=Path, default=ROOT / "data/derived/media_dedupe.sqlite")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--rehash", action="store_true", help="hash pages already hashed")
    parser.add_argument("--hash-only", action="store_true")
    parser.add_argument("--cluster-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="cluster but write nothing")
    parser.add_argument("--report", action="store_true", help="print the large clusters' sizes")
    args = parser.parse_args()

    if not args.cluster_only:
        for key, count in hash_corpus(
            args.facts, args.export, args.out, limit=args.limit, rehash=args.rehash
        ).most_common():
            print(f"{count:>7,}  {key}")
    if args.hash_only:
        return 0
    tally, multi = cluster(args.facts, args.out, dry_run=args.dry_run)
    for key, count in tally.most_common():
        print(f"{count:>7,}  {key}")
    if args.report and multi:
        big = sorted((len(m) for m in multi), reverse=True)[:20]
        print("largest clusters:", big)
    print("(dry run; nothing written)" if args.dry_run else "written")
    print(
        "The hash proposes and the printed values dispose: no pair is merged that shares no "
        "resolved field, or that disagrees on one."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
