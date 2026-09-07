"""What may merge two documents into one, and what may never.

DEDUPE-001: "HLA similarity alone never merges people". The hash proposes on
pixels; the printed values only ever VETO. These are templated laboratory forms,
so at a 256-bit dHash distance of 0 one measured pair of 153 already carries
contradictory printed HLA — every test below is a way a person could be merged
into another person.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load():
    spec = importlib.util.spec_from_file_location(
        "media_dedupe", ROOT / "scripts" / "media_dedupe.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# --- the veto ---------------------------------------------------------------


def test_two_agreeing_genes_corroborate_the_pixels() -> None:
    m = load()
    ok, _ = m.verdict({"A": "A*01 A*02", "B": "B*07"}, {"A": "A*01 A*02", "B": "B*07"})
    assert ok


def test_one_disagreeing_locus_refuses_the_pair_outright() -> None:
    """The whole design: these are two people, however alike the paper looks."""
    m = load()
    ok, reason = m.verdict(
        {"A": "A*01 A*02", "B": "B*07", "DRB1": "DRB1*15"},
        {"A": "A*01 A*02", "B": "B*08", "DRB1": "DRB1*15"},
    )
    assert not ok and "disagree" in reason


def test_a_blood_group_alone_is_not_corroboration() -> None:
    """Four groups and two Rh signs: two unrelated pages agree about one time in
    eight, and 434 pairs would have merged on exactly that."""
    m = load()
    ok, reason = m.verdict({"ABO": "O", "RH": "POSITIVE"}, {"ABO": "O", "RH": "POSITIVE"})
    assert not ok and "too little" in reason


def test_one_agreeing_gene_alone_is_not_enough() -> None:
    m = load()
    ok, reason = m.verdict({"A": "A*01 A*02"}, {"A": "A*01 A*02"})
    assert not ok and "too little" in reason
    # ... but a gene plus a blood group is two fields, one of them a gene.
    ok, _ = m.verdict({"A": "A*01 A*02", "ABO": "O"}, {"A": "A*01 A*02", "ABO": "O"})
    assert ok


def test_nothing_in_common_never_merges() -> None:
    m = load()
    assert not m.verdict({}, {})[0]
    assert not m.verdict({"A": "A*01"}, {"B": "B*07"})[0], "no field is shared"


def test_the_veto_never_proposes_a_merge_on_its_own() -> None:
    """`verdict` is only ever consulted about a pair the HASH already proposed.
    Identical genotypes are not a merge; they are permission for one."""
    m = load()
    ok, _ = m.verdict({"A": "A*01", "B": "B*07"}, {"A": "A*01", "B": "B*07"})
    assert ok, "the veto's answer is 'not refused', which is not the same as 'merge'"


# --- the clustering ---------------------------------------------------------


def dedupe_store(module, entries):
    """`entries` is `(sha, dhash bytes)`; the store the clusterer reads."""
    con = sqlite3.connect(":memory:")
    con.executescript(module.SCHEMA)
    for sha, code in entries:
        con.execute(
            "INSERT INTO media_hash VALUES (?,?,?,?,?,?,NULL,'')",
            (sha, module.DEDUPE_VERSION, f"{sha}.jpg", 100, 100, code),
        )
    con.commit()
    return con


def code(bits: str) -> bytes:
    """A 256-bit hash from a short bit prefix, zero-padded."""
    padded = (bits + "0" * 256)[:256]
    return bytes(int(padded[i : i + 8], 2) for i in range(0, 256, 8))


def test_a_chain_may_not_merge_two_contradicting_documents(monkeypatch, tmp_path) -> None:
    """Union-find is transitive and the veto is not. A~B passes and B~C passes
    while A and C were never compared — and A and C are different people. On the
    live corpus this dissolved 3 clusters holding 27 documents."""
    m = load()
    con = dedupe_store(
        m,
        [("a", code("0" * 256)), ("b", code("0" * 254 + "11")), ("c", code("0" * 252 + "1111"))],
    )
    # `b` carries no B locus, so it agrees with BOTH neighbours and neither pair
    # is refused; `a` and `c` are never compared by the union and contradict on
    # the very locus `b` is silent about.
    fields = {
        "a": {"A": "A*01", "DQB1": "DQB1*02", "B": "B*07"},
        "b": {"A": "A*01", "DQB1": "DQB1*02", "DRB1": "DRB1*15"},
        "c": {"A": "A*01", "DRB1": "DRB1*15", "B": "B*44"},
    }
    monkeypatch.setattr(m, "resolved_fields", lambda _facts: fields)
    monkeypatch.setattr(m, "sqlite3", sqlite3)
    original = sqlite3.connect

    def fake_connect(target, *args, **kwargs):
        return con if str(target).endswith("dedupe.sqlite") else original(target, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", fake_connect)
    tally, multi = m.cluster(tmp_path / "facts.sqlite", Path("dedupe.sqlite"), dry_run=True)
    assert multi == [], "a chain merged two documents whose printed values disagree"
    assert tally["clusters DISSOLVED: a chain merged two contradicting documents"] == 1


def test_a_consistent_chain_survives(monkeypatch, tmp_path) -> None:
    m = load()
    con = dedupe_store(
        m,
        [("a", code("0" * 256)), ("b", code("0" * 254 + "11")), ("c", code("0" * 252 + "1111"))],
    )
    agree = {"A": "A*01", "B": "B*07", "DRB1": "DRB1*15"}
    monkeypatch.setattr(m, "resolved_fields", lambda _facts: {"a": agree, "b": agree, "c": agree})
    original = sqlite3.connect

    def fake_connect(target, *args, **kwargs):
        return con if str(target).endswith("dedupe.sqlite") else original(target, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", fake_connect)
    _tally, multi = m.cluster(tmp_path / "facts.sqlite", Path("dedupe.sqlite"), dry_run=True)
    assert multi == [["a", "b", "c"]]


def test_distant_hashes_are_never_paired(monkeypatch, tmp_path) -> None:
    """The hash is the candidate generator; beyond its threshold there is no
    candidate, whatever the values say."""
    m = load()
    con = dedupe_store(m, [("a", code("0" * 256)), ("b", code("1" * 256))])
    agree = {"A": "A*01", "B": "B*07"}
    monkeypatch.setattr(m, "resolved_fields", lambda _facts: {"a": agree, "b": agree})
    original = sqlite3.connect

    def fake_connect(target, *args, **kwargs):
        return con if str(target).endswith("dedupe.sqlite") else original(target, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", fake_connect)
    _tally, multi = m.cluster(tmp_path / "facts.sqlite", Path("dedupe.sqlite"), dry_run=True)
    assert multi == []


def test_the_hash_is_stable_and_sized() -> None:
    import numpy as np
    from PIL import Image as PilImage

    m = load()
    rng = np.random.default_rng(20260907)
    array = rng.integers(0, 255, size=(80, 60), dtype=np.uint8)
    image = PilImage.fromarray(array)
    first = m.dhash(image)
    assert len(first) == 32, "256 bits"
    assert first == m.dhash(image), "the same image must hash the same way twice"
