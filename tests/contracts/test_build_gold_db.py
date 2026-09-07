"""What the Gold database promises, checked on a store small enough to read.

GOLD-001's invariants are the tests: a profile defaults HISTORICAL_UNCLAIMED, a
canonical value carries its provenance, a conflict stays a conflict, and the
rebuild is reproducible. The dedupe rule beside them is DEDUPE-001's: profiles
that merely share a genotype are FLAGGED, never merged.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EV = "facts/v1"


def load():
    spec = importlib.util.spec_from_file_location(
        "build_gold_db", ROOT / "scripts" / "build_gold_db.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def facts_store(path: Path, documents, facts) -> None:
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE fact (sha256 TEXT, field TEXT, extraction_version TEXT, status TEXT,
            value TEXT, raw TEXT, second_allele TEXT, reason TEXT, rule_id TEXT,
            anchor_box TEXT, value_boxes TEXT, source TEXT, imgt_version TEXT,
            PRIMARY KEY (sha256, field, extraction_version));
        CREATE TABLE document (sha256 TEXT, extraction_version TEXT, rel_path TEXT,
            quality_band TEXT, comparison_sheet INTEGER DEFAULT 0,
            PRIMARY KEY (sha256, extraction_version));
        """
    )
    for sha, band, sheet in documents:
        con.execute("INSERT INTO document VALUES (?,?,?,?,?)", (sha, EV, f"{sha}.jpg", band, sheet))
    for sha, field, status, value, source in facts:
        con.execute(
            "INSERT INTO fact (sha256, field, extraction_version, status, value, source, "
            "anchor_box, value_boxes, rule_id, reason, imgt_version) "
            "VALUES (?,?,?,?,?,?,'[0,0,1,1]','[[0,0,1,1]]','R/v1','a reason','3.62')",
            (sha, field, EV, status, value, source),
        )
    con.commit()
    con.close()


def dedupe_store(module, path: Path, clusters) -> None:
    """`clusters` is `(sha, cluster_id, is_representative)`."""
    con = sqlite3.connect(path)
    con.executescript(
        "CREATE TABLE media_cluster (sha256 TEXT, dedupe_version TEXT, cluster_id TEXT,"
        " representative INTEGER, n_members INTEGER, created_utc TEXT);"
    )
    for sha, cluster, rep in clusters:
        con.execute(
            "INSERT INTO media_cluster VALUES (?,?,?,?,?,'')",
            (sha, module.DEDUPE_VERSION, cluster, rep, 2),
        )
    con.commit()
    con.close()


def build(module, tmp_path, documents, facts, clusters=()):
    tmp_path.mkdir(parents=True, exist_ok=True)
    facts_path = tmp_path / "facts.sqlite"
    facts_store(facts_path, documents, facts)
    dedupe = tmp_path / "dedupe.sqlite"
    if clusters:
        dedupe_store(module, dedupe, clusters)
    out = tmp_path / "gold.sqlite"
    tally = module.build(facts_path, tmp_path / "missing_source.sqlite", dedupe, out, [])
    return out, tally


def rows(out: Path, sql: str):
    con = sqlite3.connect(f"file:{out.as_posix()}?mode=ro", uri=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def test_a_profile_defaults_unclaimed_and_carries_its_provenance(tmp_path) -> None:
    m = load()
    out, _ = build(
        m,
        tmp_path,
        [("d1", "HIGH", 0)],
        [("d1", "A", "RESOLVED", "A*01 A*02", None)],
    )
    (status,) = rows(out, "SELECT status FROM gold_profile")[0]
    assert status == m.UNCLAIMED
    fact = rows(
        out,
        "SELECT field, value, sha256, anchor_box, value_boxes, rule_id, imgt_version, tier "
        "FROM gold_fact",
    )[0]
    assert fact[0] == "A" and fact[1] == "A*01 A*02"
    assert fact[2] == "d1", "the value must name the document it was read from"
    assert fact[3] and fact[4], "and the crop boxes a reviewer would look at"
    assert fact[5] == "R/v1" and fact[6] == "3.62"
    assert fact[7] == "C", "no label has tested this rule group"


def test_two_documents_of_one_cluster_become_one_profile(tmp_path) -> None:
    m = load()
    out, tally = build(
        m,
        tmp_path,
        [("d1", "HIGH", 0), ("d2", "HIGH", 0)],
        [
            ("d1", "A", "RESOLVED", "A*01 A*02", None),
            ("d2", "A", "RESOLVED", "A*01 A*02", None),
        ],
        clusters=[("d1", "c1", 1), ("d2", "c1", 0)],
    )
    assert tally["profiles"] == 1
    assert tally["documents folded into another as a duplicate"] == 1
    assert len(rows(out, "SELECT * FROM gold_document")) == 2, "both documents are kept"
    assert len(rows(out, "SELECT * FROM gold_fact")) == 1, "one value, not two"


def test_a_conflict_between_two_members_stays_a_conflict(tmp_path) -> None:
    """GOLD-001: 'conflicting critical evidence remains conflict'. Nothing picks."""
    m = load()
    out, tally = build(
        m,
        tmp_path,
        [("d1", "HIGH", 0), ("d2", "HIGH", 0)],
        [
            ("d1", "ABO", "RESOLVED", "A", "LABORATORY_PRINTED"),
            ("d2", "ABO", "RESOLVED", "O", "LABORATORY_PRINTED"),
        ],
        clusters=[("d1", "c1", 1), ("d2", "c1", 0)],
    )
    assert tally["conflict kept as a conflict: ABO"] == 1
    assert rows(out, "SELECT COUNT(*) FROM gold_fact WHERE field='ABO'")[0][0] == 0
    assert rows(out, "SELECT COUNT(*) FROM gold_conflict")[0][0] == 1


def test_review_and_unknown_are_held_apart_from_the_facts(tmp_path) -> None:
    m = load()
    out, _ = build(
        m,
        tmp_path,
        [("d1", "HIGH", 0)],
        [
            ("d1", "A", "RESOLVED", "A*01", None),
            ("d1", "B", "REVIEW_REQUIRED", None, None),
            ("d1", "C", "NOT_TESTED", None, None),
        ],
    )
    assert [r[0] for r in rows(out, "SELECT field FROM gold_fact")] == ["A"]
    assert ("B",) in rows(out, "SELECT field FROM gold_review")
    states = dict(rows(out, "SELECT field, state FROM gold_unknown"))
    assert states["C"] == "NOT_TESTED"
    assert "A" not in states and "B" not in states, "a field appears in exactly one place"


def test_profiles_sharing_a_genotype_are_flagged_and_never_merged(tmp_path) -> None:
    """DEDUPE-001: 'HLA similarity alone never merges people'. An HLA-identical
    sibling pair is the most valuable pair in this corpus."""
    m = load()
    genotype = [
        ("A", "A*01"),
        ("B", "B*07"),
        ("C", "C*07"),
        ("DRB1", "DRB1*15"),
        ("DQB1", "DQB1*06"),
    ]
    out, tally = build(
        m,
        tmp_path,
        [("d1", "HIGH", 0), ("d2", "HIGH", 0)],
        [(sha, f, "RESOLVED", v, None) for sha in ("d1", "d2") for f, v in genotype],
    )
    assert tally["profiles"] == 2, "two people, not one"
    pairs = rows(
        out,
        "SELECT profile_id, other_profile_id, shared_loci, shared_abo "
        "FROM gold_duplicate_candidate",
    )
    assert len(pairs) == 1 and pairs[0][2] == 5
    assert pairs[0][0] != pairs[0][1]


def test_a_partial_genotype_is_not_a_duplicate_candidate(tmp_path) -> None:
    m = load()
    out, _ = build(
        m,
        tmp_path,
        [("d1", "HIGH", 0), ("d2", "HIGH", 0)],
        [(sha, "A", "RESOLVED", "A*01", None) for sha in ("d1", "d2")],
    )
    assert rows(out, "SELECT COUNT(*) FROM gold_duplicate_candidate")[0][0] == 0


def test_the_build_is_reproducible(tmp_path) -> None:
    """GOLD-001 acceptance: 'rebuild is reproducible from evidence+review decisions'."""
    m = load()
    documents = [("d1", "HIGH", 0), ("d2", "MID", 0), ("d3", "HIGH", 0)]
    facts = [
        ("d1", "A", "RESOLVED", "A*01 A*02", None),
        ("d2", "A", "RESOLVED", "A*01 A*02", None),
        ("d3", "B", "REVIEW_REQUIRED", None, None),
    ]
    first, _ = build(m, tmp_path / "one", documents, facts, [("d1", "c1", 1), ("d2", "c1", 0)])
    second, _ = build(m, tmp_path / "two", documents, facts, [("d1", "c1", 1), ("d2", "c1", 0)])
    for table in ("gold_profile", "gold_document", "gold_fact", "gold_review", "gold_unknown"):
        assert rows(first, f"SELECT * FROM {table} ORDER BY 1,2") == rows(
            second, f"SELECT * FROM {table} ORDER BY 1,2"
        ), table


def test_verify_reports_a_failure_rather_than_passing_quietly(tmp_path) -> None:
    """The self-check is what everyone will trust, so it must be able to fail."""
    m = load()
    out, _ = build(m, tmp_path, [("d1", "HIGH", 0)], [("d1", "A", "RESOLVED", "A*01", None)])
    checks, failures = m.verify(out, tmp_path / "facts.sqlite")
    assert not failures
    con = sqlite3.connect(out)
    con.execute("INSERT INTO gold_document VALUES ('another','d1',1)")
    con.commit()
    con.close()
    _checks, failures = m.verify(out, tmp_path / "facts.sqlite")
    assert failures, "a document in two profiles must be reported"
