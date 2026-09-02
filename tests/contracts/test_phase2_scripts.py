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
    """A bare 'A'/'B'/'C' matches far too much incidental text to be a locus."""
    mod = load("template_discovery")
    assert mod.LOCI == ["DRB1", "DRB3", "DRB4", "DRB5", "DQA1", "DQB1", "DPA1", "DPB1"]
    for stray in ("A", "B", "C", "CW"):
        assert not mod.LOCUS_RE.fullmatch(stray)
    for real in ("DRB1", "DQB1", "DPA1"):
        assert mod.LOCUS_RE.fullmatch(real)


def test_a_family_is_only_verified_when_an_independent_signal_agrees() -> None:
    """Verification must use layout coherence, not the space it clustered in.

    Authoring cell boxes against a mixture would map cells to the wrong locus on
    part of the family - the failure OCR_SPEC forbids.
    """
    mod = load("template_discovery")
    src = (ROOT / "scripts/template_discovery.py").read_text(encoding="utf-8")
    assert "coherence_lift" in src and "verified_single_template" in src
    assert mod.MIN_LIFT > 0, "verification must require a positive coherence lift"
    assert mod.TIGHT_SD > 0


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
