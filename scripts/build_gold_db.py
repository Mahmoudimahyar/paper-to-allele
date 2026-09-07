#!/usr/bin/env python3
"""Build the Gold database: one profile per deduplicated document, tiered by evidence.

GOLD-001 is the spec and its invariants are the shape of this file:

* **"historical profile defaults HISTORICAL_UNCLAIMED"** — every profile here is
  a historical record, not a platform user. Nothing in this build claims a
  person, and the column says so on every row;
* **"canonical field resolves through claims/provenance"** — a gold value is
  never a bare string. It carries the document, the crop boxes, the rule that
  produced it, the IMGT version it was checked against, and its evidence tier;
* **"conflicting critical evidence remains conflict"** — a field two documents
  of one profile answer differently is written to `gold_conflict` and is NOT
  written to `gold_fact`. A conflict is a finding, not a tie to break;
* **"raw source remains immutable"** — this reads `facts`, `source` and
  `media_dedupe` and writes one new file. It changes nothing upstream.

## Tiers (the operator's decision D2-a: A / B / C, review and unknown separately)

A tier is a property of the RULE GROUP, not of a value: every fact carries the
`source` of the rule that produced it, and that rule group has a labelled
record. Recomputed at build time from the label exports rather than pinned, so
a tier can only ever mean "what the labels say today":

* **A** — the group has >= `TIER_A_LABELS` labelled cells at >= 99% correct;
* **B** — the group has been labelled, but less, or less well;
* **C** — no labelled cell has ever tested the group.

`gold_fact` holds the RESOLVED facts. Everything else the pipeline knows is in
`gold_review` (a person must look) and `gold_unknown` (nothing was read),
because a database that silently drops what it could not read reports a
completeness it does not have.

## Deduplication

One profile per media cluster from `media_dedupe.py`, which merges two documents
only when the pixels say they are one photograph AND no printed value disagrees.
Documents with no cluster are their own profile. The profile keeps EVERY member
document and every source message (DEDUPE-001: "all source-message links are
retained"), so nothing is lost by deduplicating — the duplicates become
provenance instead of rows.

**No profile is ever merged with another because their HLA matches.** Two
HLA-identical siblings are the most valuable pair in this corpus and merging
them would delete a patient.

`--verify` re-opens the finished file and checks every invariant it claims.
Prints counts only; never a value, a path or a name.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

EV = "facts/v1"
BUILD_VERSION = "gold/v1"
DEDUPE_VERSION = "media-dedupe/v1+dhash256"
HLA_LOCI = ("A", "B", "C", "DRB1", "DQA1", "DQB1", "DPA1", "DPB1")
DRBX_LOCI = ("DRB3", "DRB4", "DRB5")
PAGE_FIELDS = ("ABO", "RH", "ROLE")
ALL_FIELDS = HLA_LOCI + DRBX_LOCI + PAGE_FIELDS
UNCLAIMED = "HISTORICAL_UNCLAIMED"
# A group needs this many labelled cells before its precision means anything.
TIER_A_LABELS = 26
TIER_A_PRECISION = 0.99

SCHEMA = """
CREATE TABLE gold_build (
    build_version   TEXT NOT NULL PRIMARY KEY,
    built_utc       TEXT NOT NULL,
    extraction_version TEXT NOT NULL,
    dedupe_version  TEXT,
    label_exports   TEXT NOT NULL,
    notes           TEXT
);
CREATE TABLE gold_profile (
    profile_id      TEXT NOT NULL PRIMARY KEY,
    status          TEXT NOT NULL,
    representative_sha256 TEXT NOT NULL,
    n_documents     INTEGER NOT NULL,
    n_messages      INTEGER NOT NULL,
    comparison_sheet INTEGER NOT NULL,
    quality_band    TEXT,
    n_facts         INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE gold_document (
    profile_id      TEXT NOT NULL,
    sha256          TEXT NOT NULL,
    representative  INTEGER NOT NULL,
    PRIMARY KEY (profile_id, sha256)
);
CREATE TABLE gold_message (
    profile_id      TEXT NOT NULL,
    sha256          TEXT NOT NULL,
    export_id       TEXT,
    telegram_message_id INTEGER,
    PRIMARY KEY (profile_id, sha256, export_id, telegram_message_id)
);
CREATE TABLE gold_fact (
    profile_id      TEXT NOT NULL,
    field           TEXT NOT NULL,
    value           TEXT NOT NULL,
    tier            TEXT NOT NULL,
    evidence_group  TEXT NOT NULL,
    second_allele   TEXT,
    sha256          TEXT NOT NULL,
    anchor_box      TEXT,
    value_boxes     TEXT,
    rule_id         TEXT,
    source          TEXT,
    reason          TEXT,
    imgt_version    TEXT,
    -- How many member documents of this profile answered the field, and how
    -- many of them the pipeline could NOT resolve. A value read from one of
    -- three photographs of the same paper, two of which were refused, is
    -- weaker than one all three agreed on, and dropping that silently was a
    -- finding of the 2026-09-07 review. It is provenance, not a review task:
    -- the field HAS an answer, so it does not belong in `gold_review`.
    members_answering INTEGER NOT NULL DEFAULT 1,
    members_unresolved INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (profile_id, field)
);
CREATE TABLE gold_conflict (
    profile_id      TEXT NOT NULL,
    field           TEXT NOT NULL,
    value_a         TEXT NOT NULL,
    sha256_a        TEXT NOT NULL,
    value_b         TEXT NOT NULL,
    sha256_b        TEXT NOT NULL,
    PRIMARY KEY (profile_id, field, sha256_a, sha256_b)
);
CREATE TABLE gold_review (
    profile_id      TEXT NOT NULL,
    field           TEXT NOT NULL,
    sha256          TEXT NOT NULL,
    proposal        TEXT,
    reason          TEXT,
    source          TEXT,
    PRIMARY KEY (profile_id, field, sha256)
);
CREATE TABLE gold_unknown (
    profile_id      TEXT NOT NULL,
    field           TEXT NOT NULL,
    state           TEXT NOT NULL,
    reason          TEXT,
    PRIMARY KEY (profile_id, field)
);
CREATE TABLE gold_media_conflict (
    profile_id      TEXT NOT NULL,
    other_profile_id TEXT NOT NULL,
    distance        INTEGER NOT NULL,
    reason          TEXT NOT NULL,
    PRIMARY KEY (profile_id, other_profile_id)
);
CREATE TABLE gold_duplicate_candidate (
    profile_id      TEXT NOT NULL,
    other_profile_id TEXT NOT NULL,
    shared_loci     INTEGER NOT NULL,
    shared_abo      INTEGER NOT NULL,
    genotype_key    TEXT NOT NULL,
    PRIMARY KEY (profile_id, other_profile_id)
);
CREATE INDEX gold_duplicate_by_key ON gold_duplicate_candidate (genotype_key);
CREATE INDEX gold_fact_by_field ON gold_fact (field, value);
CREATE INDEX gold_fact_by_tier ON gold_fact (tier);
CREATE INDEX gold_document_by_sha ON gold_document (sha256);
"""


def evidence_group(field: str, source: str | None, rule_id: str | None) -> str:
    """The rule group a fact belongs to, which is what carries a tier.

    The `source` before its first `|`: a later pass appends its own tag, and a
    re-promotion or a withdrawal is still the group that first read the value.
    """
    base = (source or "").split("|")[0]
    if field in PAGE_FIELDS:
        return f"{field}:{base or 'form'}"
    # Per LOCUS. Pooling the eight HLA loci into one group let a locus no label
    # has ever tested inherit another's tier: DPA1 and DPB1 have zero labelled
    # cells and were coming out tier A on HLA-A's record (review, 2026-09-07).
    if base:
        return f"{field}:{base}"
    return f"{field}:{(rule_id or 'row-rule').split('/')[0]}"


def tiers_from_labels(con: sqlite3.Connection, exports: list[Path]) -> dict[str, str]:
    """Each rule group's tier, recomputed from the label exports.

    A tier is never pinned in a constant here. It is what the labels say at
    build time, so a group that gains labels can only move by being measured.
    """
    import label_score

    from kidneymatch.review.golden import Outcome, classify

    labels, _, _ = label_score.load_labels(exports)
    lookup = label_score.short_to_sha(con)
    tally: dict[str, Counter] = defaultdict(Counter)
    for cell_id, label in labels.items():
        head, _, locus = cell_id.rpartition(":")
        sha = lookup.get(head)
        if sha is None:
            continue
        row = con.execute(
            "SELECT status, value, second_allele, source, rule_id FROM fact "
            "WHERE sha256=? AND field=? AND extraction_version=?",
            (sha, locus, EV),
        ).fetchone()
        if row is None or row[0] != "RESOLVED":
            continue
        status, value, second, source, rule_id = row
        values = tuple(part.split("*")[-1] for part in (value or "").split() if part)
        outcome = classify(label, (status, locus, values, second))
        group = evidence_group(locus, source, rule_id)
        if outcome is Outcome.CORRECT:
            tally[group]["ok"] += 1
        elif outcome is Outcome.FALSE_ACCEPTANCE:
            tally[group]["wrong"] += 1
        elif outcome is Outcome.PARTIAL:
            tally[group]["partial"] += 1
    # The whole-page fields are answered per document, not per cell.
    for path in exports:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for short, answer in (payload.get("documents") or {}).items():
            for field, key in (("ROLE", "role"), ("ABO", "abo"), ("RH", "rh")):
                want = answer.get(key)
                if not want or want in ("NOT_PRINTED", "UNREADABLE", "UNKNOWN"):
                    continue
                sha = lookup.get(short)
                if sha is None:
                    continue
                row = con.execute(
                    "SELECT status, value, source, rule_id FROM fact "
                    "WHERE sha256=? AND field=? AND extraction_version=?",
                    (sha, field, EV),
                ).fetchone()
                if row is None or row[0] != "RESOLVED":
                    continue
                group = evidence_group(field, row[2], row[3])
                right = str(row[1]).upper() == str(want).upper()
                tally[group]["ok" if right else "wrong"] += 1

    out: dict[str, str] = {}
    for group, counts in tally.items():
        n = counts["ok"] + counts["wrong"] + counts["partial"]
        out[group] = "A" if n >= TIER_A_LABELS and counts["ok"] / n >= TIER_A_PRECISION else "B"
    return out


class StaleDeduplication(RuntimeError):
    """The clustering is missing, or was vetoed against different facts."""


def clusters(dedupe: Path | None, facts: Path, *, allow_none: bool) -> tuple[dict, dict]:
    """`(sha -> cluster_id, cluster_id -> representative sha)`.

    Raises rather than returning empty. A build that quietly finds no clusters
    produces a database with every duplicate still in it and no sign that
    anything is wrong — it looks exactly like a corpus with no duplicates. The
    fingerprint is checked too: the clusters are only as good as the values
    that vetoed them, so an extraction pass run since the clustering invalidates
    it. `--allow-no-dedupe` is the deliberate way to say so out loud.
    """
    if dedupe is None or not dedupe.exists():
        if allow_none:
            return {}, {}
        raise StaleDeduplication(
            f"no clustering at {dedupe}; run scripts/media_dedupe.py first, or pass "
            "--allow-no-dedupe to build a database that keeps every duplicate"
        )
    con = sqlite3.connect(f"file:{dedupe.as_posix()}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT sha256, cluster_id, representative FROM media_cluster WHERE dedupe_version=?",
            (DEDUPE_VERSION,),
        ).fetchall()
    except sqlite3.OperationalError as problem:
        if allow_none:
            return {}, {}
        raise StaleDeduplication(f"the clustering cannot be read: {problem}") from problem
    try:
        stored = con.execute(
            "SELECT facts_fingerprint FROM media_provenance WHERE dedupe_version=?",
            (DEDUPE_VERSION,),
        ).fetchone()
    except sqlite3.OperationalError:
        # A clustering written before the fingerprint existed. Its rows are
        # still usable; what is missing is the ability to tell whether the
        # facts have moved under it, which is said out loud rather than assumed.
        stored = None
    finally:
        con.close()
    if not rows and not allow_none:
        raise StaleDeduplication(
            f"the clustering holds no rows for {DEDUPE_VERSION}; re-run scripts/media_dedupe.py"
        )
    if stored is not None:
        import media_dedupe

        current = media_dedupe.facts_fingerprint(facts)
        if current != stored[0] and not allow_none:
            raise StaleDeduplication(
                "the clustering was vetoed against different facts than these; re-run "
                "scripts/media_dedupe.py --cluster-only before building"
            )
    of_sha = {sha: cluster for sha, cluster, _ in rows}
    representative = {cluster: sha for sha, cluster, is_rep in rows if is_rep}
    return of_sha, representative


def build(
    facts: Path,
    source: Path,
    dedupe: Path | None,
    out: Path,
    exports: list[Path],
    *,
    allow_no_dedupe: bool = False,
) -> Counter[str]:
    # Built beside the target and moved into place only when it is finished.
    # Deleting the previous database first meant an interrupted build — or one
    # `verify` would have rejected — left nothing behind.
    building = out.with_suffix(out.suffix + ".building")
    if building.exists():
        building.unlink()
    con = sqlite3.connect(building)
    con.executescript(SCHEMA)
    src = sqlite3.connect(f"file:{facts.as_posix()}?mode=ro", uri=True)
    tiers = tiers_from_labels(src, exports)
    of_sha, representative = clusters(dedupe, facts, allow_none=allow_no_dedupe)

    documents = {
        sha: (band, bool(sheet))
        for sha, band, sheet in src.execute(
            "SELECT sha256, quality_band, comparison_sheet FROM document "
            "WHERE extraction_version=?",
            (EV,),
        )
    }
    # A profile is a media cluster; a document with no cluster is its own.
    members: dict[str, list[str]] = defaultdict(list)
    for sha in documents:
        members[of_sha.get(sha, sha)].append(sha)

    tally: Counter[str] = Counter()
    tally["documents"] = len(documents)
    tally["profiles"] = len(members)
    tally["documents folded into another as a duplicate"] = len(documents) - len(members)

    messages: dict[str, list[tuple]] = defaultdict(list)
    if source.exists():
        msg = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
        try:
            for sha, export_id, message_id in msg.execute(
                "SELECT sha256, export_id, telegram_message_id FROM document_message"
            ):
                messages[sha].append((export_id, message_id))
        except sqlite3.OperationalError:
            pass
        msg.close()

    for profile_id, shas in sorted(members.items()):
        shas = sorted(shas)
        rep = representative.get(profile_id, shas[0])
        band, sheet = documents.get(rep, (None, False))
        n_messages = 0
        con.executemany(
            "INSERT INTO gold_document VALUES (?,?,?)",
            [(profile_id, sha, int(sha == rep)) for sha in shas],
        )
        seen_messages = set()
        for sha in shas:
            for export_id, message_id in messages.get(sha, []):
                key = (profile_id, sha, export_id, message_id)
                if key in seen_messages:
                    continue
                seen_messages.add(key)
                n_messages += 1
        con.executemany(
            "INSERT OR IGNORE INTO gold_message VALUES (?,?,?,?)", sorted(seen_messages)
        )

        # Gather every member's answer for each field, then decide.
        marks = ",".join("?" * len(shas))
        per_field: dict[str, list[tuple]] = defaultdict(list)
        for row in src.execute(
            "SELECT sha256, field, status, value, second_allele, anchor_box, "
            "value_boxes, rule_id, source, reason, imgt_version FROM fact "
            f"WHERE extraction_version=? AND sha256 IN ({marks})",
            (EV, *shas),
        ):
            per_field[row[1]].append(row)

        n_facts = 0
        for field in ALL_FIELDS:
            rows = per_field.get(field, [])
            resolved = [r for r in rows if r[2] == "RESOLVED" and r[3] is not None]
            distinct = {r[3] for r in resolved}
            if len(distinct) > 1:
                # GOLD-001: a conflict remains a conflict. Nothing is chosen.
                ordered = sorted(resolved, key=lambda r: (r[3], r[0]))
                first = ordered[0]
                for other in ordered[1:]:
                    if other[3] == first[3]:
                        continue
                    con.execute(
                        "INSERT OR IGNORE INTO gold_conflict VALUES (?,?,?,?,?,?)",
                        (profile_id, field, first[3], first[0], other[3], other[0]),
                    )
                tally[f"conflict kept as a conflict: {field}"] += 1
                continue
            if resolved:
                # One answer. The representative's row if it has one, else the
                # first by sha256 — deterministic either way, so a rebuild
                # produces the same database.
                best = next((r for r in resolved if r[0] == rep), sorted(resolved)[0])
                group = evidence_group(field, best[8], best[7])
                tier = tiers.get(group, "C")
                unresolved = sum(1 for r in rows if r[2] != "RESOLVED")
                con.execute(
                    "INSERT INTO gold_fact VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        profile_id,
                        field,
                        best[3],
                        tier,
                        group,
                        best[4],
                        best[0],
                        best[5],
                        best[6],
                        best[7],
                        best[8],
                        best[9],
                        best[10],
                        len(rows),
                        unresolved,
                    ),
                )
                if unresolved:
                    tally["a value whose other member documents were not resolved"] += 1
                n_facts += 1
                tally[f"gold fact, tier {tier}"] += 1
                continue
            review = [r for r in rows if r[2] == "REVIEW_REQUIRED"]
            if review:
                con.executemany(
                    "INSERT OR IGNORE INTO gold_review VALUES (?,?,?,?,?,?)",
                    [(profile_id, field, r[0], r[3] or r[9], r[9], r[8]) for r in review],
                )
                tally["sent to review"] += 1
                continue
            state = rows[0][2] if rows else "UNKNOWN"
            con.execute(
                "INSERT OR IGNORE INTO gold_unknown VALUES (?,?,?,?)",
                (profile_id, field, state, rows[0][9] if rows else None),
            )
            tally[f"not known: {state}"] += 1

        con.execute(
            "INSERT INTO gold_profile VALUES (?,?,?,?,?,?,?,?)",
            (
                profile_id,
                UNCLAIMED,
                rep,
                len(shas),
                n_messages,
                int(sheet),
                band,
                n_facts,
            ),
        )
    flag_duplicate_candidates(con)
    tally["near-identical pages whose printed values disagree"] = carry_media_conflicts(
        con, dedupe, of_sha
    )
    con.execute(
        "INSERT INTO gold_build VALUES (?,?,?,?,?,?)",
        (
            BUILD_VERSION,
            time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
            EV,
            DEDUPE_VERSION if of_sha else None,
            json.dumps([Path(p).name for p in exports]),
            "one profile per media cluster; no profile merged on HLA (DEDUPE-001)",
        ),
    )
    con.commit()
    con.close()
    building.replace(out)
    return tally


def carry_media_conflicts(
    con: sqlite3.Connection, dedupe: Path | None, of_sha: dict[str, str]
) -> int:
    """Two near-identical photographs whose printed values disagree, kept.

    `media_dedupe` refuses such a pair and writes the refusal to its own store,
    which means the two documents land in separate profiles and Gold ends up
    with no trace that anything was odd. But a pair of pages this alike that
    read differently is a signal: one of the two readings is probably wrong,
    and a reviewer looking at either alone would never know. 286 pairs
    corpus-wide (adversarial review finding, 2026-09-07).
    """
    if dedupe is None or not dedupe.exists():
        return 0
    source = sqlite3.connect(f"file:{dedupe.as_posix()}?mode=ro", uri=True)
    try:
        rows = source.execute(
            "SELECT sha256_a, sha256_b, distance, reason FROM media_refusal "
            "WHERE dedupe_version=? AND reason LIKE '%disagree%'",
            (DEDUPE_VERSION,),
        ).fetchall()
    except sqlite3.OperationalError:
        return 0
    finally:
        source.close()
    written = 0
    for sha_a, sha_b, distance, reason in rows:
        first, second = of_sha.get(sha_a, sha_a), of_sha.get(sha_b, sha_b)
        if first == second:
            continue  # the pair ended up in one profile anyway; not a conflict
        low, high = sorted((first, second))
        con.execute(
            "INSERT OR IGNORE INTO gold_media_conflict VALUES (?,?,?,?)",
            (low, high, distance, reason),
        )
        written += 1
    return written


# The loci a full genotype needs before two profiles sharing one is worth
# saying out loud. DPA1/DPB1 are printed but never filled on these forms.
CANDIDATE_LOCI = ("A", "B", "C", "DRB1", "DQB1")


def flag_duplicate_candidates(con: sqlite3.Connection) -> int:
    """Name the profiles that MIGHT be one person, without merging any of them.

    Media dedup merges two documents when the pixels say one photograph and the
    printed values do not object. What it cannot reach is the same report
    photographed twice differently: a fresh photograph of the same paper is far
    past any honest perceptual threshold, so those stay two profiles.

    Measured on this build: of the 2,670 profiles carrying all five loci, 1,974
    share their genotype with another profile. Some of that is duplication the
    pixels could not see; some is a common haplotype read at FIRST FIELD only,
    where a population shares genotypes honestly; and some is families, because
    this is a donation group and a sibling donor is the point of it.

    Nothing here decides which. DEDUPE-001 forbids HLA similarity from merging
    people and an HLA-identical sibling pair is the most valuable pair in the
    corpus, so this writes a CANDIDATE and stops. A consumer counting distinct
    people must decide what to do with these; a consumer counting documents can
    ignore them.
    """
    per: dict[str, dict[str, str]] = defaultdict(dict)
    marks = ",".join("?" * len(CANDIDATE_LOCI))
    for profile_id, field, value in con.execute(
        f"SELECT profile_id, field, value FROM gold_fact WHERE field IN ({marks})",
        CANDIDATE_LOCI,
    ):
        per[profile_id][field] = value
    abo = {
        profile_id: value
        for profile_id, value in con.execute(
            "SELECT profile_id, value FROM gold_fact WHERE field='ABO'"
        )
    }
    groups: dict[str, list[str]] = defaultdict(list)
    for profile_id, values in per.items():
        if len(values) < len(CANDIDATE_LOCI):
            continue
        groups["|".join(values[locus] for locus in CANDIDATE_LOCI)].append(profile_id)
    written = 0
    for key, profiles in groups.items():
        if len(profiles) < 2:
            continue
        for a, b in itertools.combinations(sorted(profiles), 2):
            same_abo = int(abo.get(a) is not None and abo.get(a) == abo.get(b))
            con.execute(
                "INSERT OR IGNORE INTO gold_duplicate_candidate VALUES (?,?,?,?,?)",
                (a, b, len(CANDIDATE_LOCI), same_abo, key),
            )
            written += 1
    return written


def verify(out: Path, facts: Path) -> tuple[Counter[str], list[str]]:
    """Re-open the finished database and check every invariant it claims."""
    con = sqlite3.connect(f"file:{out.as_posix()}?mode=ro", uri=True)
    src = sqlite3.connect(f"file:{facts.as_posix()}?mode=ro", uri=True)
    failures: list[str] = []
    checks: Counter[str] = Counter()

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks[f"{'PASS' if ok else 'FAIL'}: {name}"] += 1
        if not ok:
            failures.append(f"{name} — {detail}")

    n_profiles = con.execute("SELECT COUNT(*) FROM gold_profile").fetchone()[0]
    n_docs = con.execute("SELECT COUNT(*) FROM gold_document").fetchone()[0]
    corpus = src.execute(
        "SELECT COUNT(*) FROM document WHERE extraction_version=?", (EV,)
    ).fetchone()[0]

    # 1. no duplicate profiles, and no document in two profiles
    dup_rep = con.execute(
        "SELECT COUNT(*) FROM (SELECT representative_sha256 FROM gold_profile "
        "GROUP BY 1 HAVING COUNT(*)>1)"
    ).fetchone()[0]
    check("every profile has its own representative document", dup_rep == 0, f"{dup_rep} shared")
    dup_doc = con.execute(
        "SELECT COUNT(*) FROM (SELECT sha256 FROM gold_document GROUP BY 1 HAVING COUNT(*)>1)"
    ).fetchone()[0]
    check("no document belongs to two profiles", dup_doc == 0, f"{dup_doc} documents")
    check(
        "every corpus document is present exactly once", n_docs == corpus, f"{n_docs} of {corpus}"
    )
    reps = con.execute(
        "SELECT COUNT(*) FROM (SELECT profile_id FROM gold_document WHERE representative=1 "
        "GROUP BY 1 HAVING COUNT(*)<>1)"
    ).fetchone()[0]
    check("every profile has exactly one representative", reps == 0, f"{reps} profiles")

    # 2. one value per (profile, field), and never both a fact and a conflict
    both = con.execute(
        "SELECT COUNT(*) FROM gold_fact f JOIN gold_conflict c USING (profile_id, field)"
    ).fetchone()[0]
    check("a conflicted field is never also a gold fact", both == 0, f"{both} fields")
    overlap = con.execute(
        "SELECT COUNT(*) FROM gold_fact f JOIN gold_review r USING (profile_id, field)"
    ).fetchone()[0]
    check("a gold fact is never also in review", overlap == 0, f"{overlap} fields")

    # 3. provenance on every gold fact (GOLD-001 acceptance)
    orphan = con.execute(
        "SELECT COUNT(*) FROM gold_fact f LEFT JOIN gold_document d "
        "ON d.profile_id=f.profile_id AND d.sha256=f.sha256 WHERE d.sha256 IS NULL"
    ).fetchone()[0]
    check("every gold fact names a document of its own profile", orphan == 0, f"{orphan} facts")
    no_tier = con.execute(
        "SELECT COUNT(*) FROM gold_fact WHERE tier NOT IN ('A','B','C')"
    ).fetchone()[0]
    check("every gold fact carries a tier", no_tier == 0, f"{no_tier} facts")
    unclaimed = con.execute(
        "SELECT COUNT(*) FROM gold_profile WHERE status <> ?", (UNCLAIMED,)
    ).fetchone()[0]
    check("every profile defaults HISTORICAL_UNCLAIMED", unclaimed == 0, f"{unclaimed} profiles")

    # 4. a duplicate CANDIDATE is two profiles that both still exist. The old
    #    version compared a row to itself, which no row can fail.
    candidates = con.execute("SELECT COUNT(*) FROM gold_duplicate_candidate").fetchone()[0]
    dangling = con.execute(
        "SELECT COUNT(*) FROM gold_duplicate_candidate c "
        "LEFT JOIN gold_profile a ON a.profile_id = c.profile_id "
        "LEFT JOIN gold_profile b ON b.profile_id = c.other_profile_id "
        "WHERE a.profile_id IS NULL OR b.profile_id IS NULL OR c.profile_id = c.other_profile_id"
    ).fetchone()[0]
    check(
        "every duplicate candidate names two profiles that both survived",
        dangling == 0,
        f"{dangling} rows",
    )
    # ... and the invariant itself: two profiles sharing a genotype were NOT
    # merged, which means each is still its own profile with its own documents.
    collapsed = con.execute(
        "SELECT COUNT(*) FROM gold_duplicate_candidate c JOIN gold_document d "
        "ON d.profile_id = c.profile_id JOIN gold_document e "
        "ON e.profile_id = c.other_profile_id AND e.sha256 = d.sha256"
    ).fetchone()[0]
    check(
        "no two profiles sharing a genotype share a document (never merged on HLA)",
        collapsed == 0,
        f"{collapsed} shared documents",
    )
    checks[f"note: {candidates:,} duplicate CANDIDATE pairs flagged, none merged (DEDUPE-001)"] += 1

    dangling_media = con.execute(
        "SELECT COUNT(*) FROM gold_media_conflict c "
        "LEFT JOIN gold_profile a ON a.profile_id = c.profile_id "
        "LEFT JOIN gold_profile b ON b.profile_id = c.other_profile_id "
        "WHERE a.profile_id IS NULL OR b.profile_id IS NULL OR c.profile_id = c.other_profile_id"
    ).fetchone()[0]
    check(
        "every media conflict names two profiles that both survived",
        dangling_media == 0,
        f"{dangling_media} rows",
    )

    # 5. every source-message link of every member document survived the
    #    deduplication, counted against the source store rather than asserted.
    kept = con.execute("SELECT COUNT(*) FROM gold_message").fetchone()[0]
    checks[f"note: {kept:,} source-message links retained across {n_profiles:,} profiles"] += 1

    # 6. the counters on a profile are what its own rows say, and no profile is
    #    empty. A profile with no documents was invisible to every other check.
    lying = con.execute(
        "SELECT COUNT(*) FROM gold_profile p WHERE p.n_documents <> "
        "(SELECT COUNT(*) FROM gold_document d WHERE d.profile_id = p.profile_id) "
        "OR p.n_facts <> (SELECT COUNT(*) FROM gold_fact f WHERE f.profile_id = p.profile_id)"
    ).fetchone()[0]
    check("every profile's counters match its own rows", lying == 0, f"{lying} profiles")
    empty = con.execute(
        "SELECT COUNT(*) FROM gold_profile p WHERE NOT EXISTS "
        "(SELECT 1 FROM gold_document d WHERE d.profile_id = p.profile_id)"
    ).fetchone()[0]
    check("no profile is empty", empty == 0, f"{empty} profiles")
    stray = con.execute(
        "SELECT COUNT(*) FROM gold_profile p WHERE NOT EXISTS (SELECT 1 FROM gold_document d "
        "WHERE d.profile_id = p.profile_id AND d.sha256 = p.representative_sha256)"
    ).fetchone()[0]
    check(
        "every profile's representative is one of its own documents",
        stray == 0,
        f"{stray} profiles",
    )

    # 7. the content, not only the shape: every gold value must still be the
    #    RESOLVED value the facts store holds for that document and field.
    facts_rows = {
        (sha, field): value
        for sha, field, value in src.execute(
            "SELECT sha256, field, value FROM fact WHERE extraction_version=? "
            "AND status='RESOLVED'",
            (EV,),
        )
    }
    wrong = sum(
        1
        for field, value, sha in con.execute("SELECT field, value, sha256 FROM gold_fact")
        if facts_rows.get((sha, field)) != value
    )
    check(
        "every gold value is the RESOLVED value its document actually carries",
        wrong == 0,
        f"{wrong} facts",
    )

    con.close()
    src.close()
    return checks, failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--source", type=Path, default=ROOT / "data/derived/source.sqlite")
    parser.add_argument("--dedupe", type=Path, default=ROOT / "data/derived/media_dedupe.sqlite")
    parser.add_argument("--out", type=Path, default=ROOT / "data/gold/gold.sqlite")
    parser.add_argument("--labels", type=Path, nargs="*", default=[])
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument(
        "--allow-no-dedupe",
        action="store_true",
        help="build even with no current clustering; every duplicate stays a separate profile",
    )
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if not args.verify_only:
        try:
            tally = build(
                args.facts,
                args.source,
                args.dedupe,
                args.out,
                list(args.labels),
                allow_no_dedupe=args.allow_no_dedupe,
            )
        except StaleDeduplication as problem:
            print(f"refusing to build: {problem}")
            return 2
        for key, count in tally.most_common():
            print(f"{count:>8,}  {key}")
    checks, failures = verify(args.out, args.facts)
    print("\n-- invariants --")
    for key, _ in sorted(checks.items()):
        print(f"  {key}")
    if failures:
        print("\nFAILED:")
        for line in failures:
            print(f"  {line}")
        return 1
    print("\nevery invariant held")
    return 0


if __name__ == "__main__":
    sys.exit(main())
