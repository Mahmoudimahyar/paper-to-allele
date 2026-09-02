"""Contracts for template discovery, golden sampling and the Persian pass."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.task("BOOT-001")
ROOT = Path(__file__).resolve().parents[2]


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"km_{name}", ROOT / f"scripts/{name}.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_template_discovery_excludes_single_letter_loci() -> None:
    """A bare 'A'/'B'/'C' matches far too much incidental text to be a locus.

    The property is unchanged; the mechanism moved. Discovery used to carry its
    own `LOCUS_RE`, which matched a locus name ANYWHERE in a token and so placed
    the locus wherever a patient value happened to sit (ADR 0007). It now uses
    `glyphs.canonical_locus_label`, which matches whole tokens, repairs the
    recognizer's final-character confusions, and refuses a bare class I letter.
    """
    from kidneymatch.ocr.glyphs import canonical_locus_label
    from kidneymatch.ocr.templates import CONSTANT_LABELS

    mod = load("template_discovery")
    assert not hasattr(mod, "LOCUS_RE"), "the value-matching regex must not come back"
    assert not hasattr(mod, "LOCI"), "the signature is defined by CONSTANT_LABELS now"
    for stray in ("A", "B", "C", "CW", "DRB1*11"):
        assert canonical_locus_label(stray) not in CONSTANT_LABELS
    for real in ("DRB1", "DQB1", "DPA1", "HLA-DPBI"):
        assert canonical_locus_label(real) in CONSTANT_LABELS
    # DRB3/4/5 are excluded on purpose: on this corpus they are almost always
    # the grouped row's VALUES, and counting them split one form by genotype.
    for gene in ("DRB3", "DRB4", "DRB5"):
        assert gene not in CONSTANT_LABELS


def test_a_family_is_only_claimed_when_the_page_identifies_it() -> None:
    """Assigning a document to the wrong form applies that form's authored rule
    to a layout it was never measured on.

    The mechanism changed with the discovery rewrite: coherence lift over an
    absolute-coordinate clustering is gone, because clustering in page space is
    what fragmented one form into position blobs. What replaces it must still
    refuse rather than guess, so this asserts each guard.
    """
    from kidneymatch.ocr import templates

    # A fit has to be good, judged as a fraction of the form's own extent.
    assert 0 < templates.MAX_RESIDUAL < 0.2
    # Two points determine a scale and an offset exactly, so any pair "fits".
    assert templates.MIN_LABELS >= 3
    # A second form fitting nearly as well means the page does not identify one.
    assert templates.AMBIGUITY_MARGIN > 1.0

    mod = load("template_discovery")
    source = (ROOT / "scripts/template_discovery.py").read_text(encoding="utf-8")
    # Prototypes that fit each other are one form; not merging them made every
    # document ambiguous against its own family.
    assert "MAX_RESIDUAL" in source and "prints_locus_on_values" in source
    assert mod.MIN_PROTOTYPE_MEMBERS > 1


def test_the_family_rule_is_gated_on_a_measured_property() -> None:
    """The per-family rule reads a whole row band with no distance cap.

    What makes that safe is that the form prints the locus on every value, so it
    must be MEASURED per family rather than assumed, and the rule must apply
    only where the measurement holds.
    """
    extract = load("extract_facts")
    assert extract.FAMILY_RULE.require_prefix is True
    assert extract.FAMILY_RULE.max_gap is None
    assert extract.DEFAULT_RULE.require_prefix is False
    assert extract.DEFAULT_RULE.max_gap is not None
    source = (ROOT / "scripts/extract_facts.py").read_text(encoding="utf-8")
    assert "prints_locus_on_values" in source


def test_golden_sample_includes_strata_that_can_measure_false_acceptance() -> None:
    """A corpus of only clean reports cannot measure a false-acceptance rate."""
    src = (ROOT / "scripts/golden_sample.py").read_text(encoding="utf-8")
    for stratum in ("verified_template", "mixture_family", "non_report", "low_res_report"):
        assert stratum in src, f"golden sample must include a {stratum} stratum"


def test_golden_sample_uses_equal_allocation_across_verified_families() -> None:
    """Proportional allocation would starve small families that still need certifying."""
    src = (ROOT / "scripts/golden_sample.py").read_text(encoding="utf-8")
    assert "per_family" in src and "EQUALLY" in src


def test_persian_pass_writes_to_the_gitignored_derived_layer() -> None:
    import subprocess

    mod = load("persian_pass")
    assert "data/derived" in str(mod.DEFAULT_DB).replace("\\", "/")
    proc = subprocess.run(
        ["git", "check-ignore", "data/derived/persian_pass.sqlite"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0


def test_every_pass_is_resumable_by_engine_and_preproc_version() -> None:
    """An engine upgrade must invalidate the cache rather than silently reuse it."""
    for name in ("ocr_pass", "persian_pass"):
        mod = load(name)
        assert mod.ENGINE_VERSION and mod.PREPROC_VERSION
        src = (ROOT / f"scripts/{name}.py").read_text(encoding="utf-8")
        assert "engine_version=? AND preproc_version=?" in src
