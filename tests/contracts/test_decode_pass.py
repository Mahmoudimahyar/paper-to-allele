"""The constrained-decode pass: what it is allowed to do to the facts.

A constrained decode can turn any crop into a valid-looking allele — measured,
200 of 200 locus-label crops do exactly that. Everything here pins the
boundaries that keep it useful instead of dangerous: it may withdraw a fact, it
may not invent or alter one, and it may never be consulted before geometry.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

pytestmark = pytest.mark.task("BOOT-001")

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/decode_pass.py"


def load():
    spec = importlib.util.spec_from_file_location("km_decode_pass", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_an_unexamined_fact_never_reads_as_one_that_passed(tmp_path: Path) -> None:
    """`stability` defaults to NOT_CHECKED, and publication requires UNANIMOUS.

    Re-running extraction rewrites the fact table; if the default were anything
    else, that would silently launder every fact this pass had demoted.
    """
    module = load()
    path = tmp_path / "facts.sqlite"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE fact (sha256 TEXT, field TEXT, extraction_version TEXT)")
    con.execute("INSERT INTO fact VALUES ('a', 'DRB1', 'facts/v1')")
    con.commit()
    module.ensure_stability_column(con)
    assert con.execute("SELECT stability FROM fact").fetchone()[0] == "NOT_CHECKED"
    con.close()


def test_the_pass_never_writes_a_value_into_the_fact_table() -> None:
    """It withdraws confidence; it does not author readings.

    The independent confirmer agrees with these decodes far less often than
    with the pipeline's existing contents, so a decode that could overwrite a
    value would make the database worse while improving the yield table.
    """
    body = source()
    updates = [line for line in body.splitlines() if "UPDATE fact" in line]
    assert updates, "the pass is expected to record stability"
    for line in updates:
        assert "SET stability=" in line
        assert "value" not in line.split("WHERE")[0]


def test_a_recovery_candidate_is_only_ever_recorded() -> None:
    """A cell the resolver refused stays refused. `PROPOSAL` is a note for the
    golden corpus, never a fact."""
    body = source()
    assert '"PROPOSAL"' in body
    # The only rows written for a non-RESOLVED cell go to the decode table.
    assert "INSERT OR REPLACE INTO decode" in body
    demote_block = body.split("demote.append")[1].split("\n")[0]
    assert "RESOLVED" not in demote_block or "status ==" in body.split("demote.append")[0][-300:]


def test_every_value_box_in_a_cell_is_decoded() -> None:
    """A heterozygous cell holds two alleles.

    Decoding only the first leaves the second unexamined while the cell is
    reported stable, which was true of the first version of this pass.
    """
    body = source()
    assert "for position, box in enumerate(boxes)" in body


def test_the_decode_is_never_consulted_before_geometry() -> None:
    """`resolve_locus`'s gates must keep seeing the raw text.

    200 of 200 label crops decode to a parseable allele, so a decode allowed to
    speak before gate 1 would turn every locus label in the corpus into a
    patient's allele.
    """
    resolver = (ROOT / "src/kidneymatch/ocr/anchors.py").read_text(encoding="utf-8")
    assert "ctc" not in resolver, "the resolver must not import the decoder"

    # What matters is that the extractor cannot CALL the decoder. Naming it in
    # a comment is how the coupling gets explained, so the check is on code:
    # no import of it, and no use of anything it defines.
    extractor = (ROOT / "scripts/extract_facts.py").read_text(encoding="utf-8")
    for line in extractor.splitlines():
        code = line.split("#", 1)[0]
        assert "decode_pass" not in code, line
        assert "ctc" not in code, line
        assert "digits_preserved" not in code, line


def test_the_pass_records_which_decoder_produced_a_verdict() -> None:
    """Thresholds are calibrated against one grammar; a verdict that cannot say
    which one produced it cannot be judged later."""
    module = load()
    assert module.DECODER_VERSION
    assert "hla-value-dfa" in module.DECODER_VERSION
    assert "decoder_version    TEXT NOT NULL" in module.SCHEMA


def test_the_stability_signal_needs_the_jitter_offsets() -> None:
    """One reading of one crop says nothing about stability, so the option to
    skip the offsets has to say that where someone will read it."""
    module = load()
    assert len(module.OFFSETS) == 9
    assert "there is no stability signal" in source()


def test_grammar_cost_is_not_used_as_a_label_detector() -> None:
    """Measured on this grammar, value cost reaches 14.38 while label cost
    starts at 6.14 — the bands overlap, so cost cannot separate them."""
    module = load()
    assert module.MAX_GRAMMAR_COST >= 25.0
    assert "legibility" in source()


def test_the_frame_ablation_can_be_limited_to_the_levelled_pages() -> None:
    """`--only-levelled` keeps the `+frame` pass to pages the extraction
    levelled: everywhere else the upright crop is the stored crop, and a
    verdict there would be a copy keyed under another decoder version."""
    body = source()
    assert "only_levelled" in body and '"--only-levelled"' in body
    assert 'row[6] == "ROTATE" and row[7]' in body, "the filter reads document.frame and tilt"
    assert "args.only_levelled" in body, "the flag must reach run()"
