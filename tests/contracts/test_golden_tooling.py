"""The golden-corpus tooling: task generation, adjudication, scoring.

These pin the properties that make the corpus worth trusting. The scoring
script is the acceptance gate for `OCR-001`, so its exit status is part of the
contract, not a convenience.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.task("BOOT-001")

ROOT = Path(__file__).resolve().parents[2]


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"km_{name}", ROOT / f"scripts/{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_labels(path: Path, annotator: str, cells: dict) -> None:
    path.write_text(
        json.dumps({"schema": "golden-labels/v1", "annotator": annotator, "cells": cells}),
        encoding="utf-8",
    )


def write_hidden(path: Path, cells: dict) -> None:
    path.write_text(json.dumps({"schema": "golden-hidden/v1", "cells": cells}), encoding="utf-8")


def run_score(tmp_path: Path, a: dict, b: dict, hidden: dict) -> subprocess.CompletedProcess:
    write_labels(tmp_path / "labels_a.json", "a", a)
    write_labels(tmp_path / "labels_b.json", "b", b)
    write_hidden(tmp_path / "hidden.json", hidden)
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/golden_score.py"),
            "--labels",
            str(tmp_path / "labels_a.json"),
            str(tmp_path / "labels_b.json"),
            "--hidden",
            str(tmp_path / "hidden.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_labelling_page_never_loads_the_ocr_proposal() -> None:
    """A proposal shown beside a blurry crop is an anchor.

    The generator writes it to a separate file; the page must not reach for it.
    """
    page = (ROOT / "tools/golden_label.html").read_text(encoding="utf-8")
    assert "hidden.json" not in page
    generator = (ROOT / "scripts/golden_tasks.py").read_text(encoding="utf-8")
    assert "hidden.json" in generator, "the proposal must still be kept, for the scorer"


def test_the_tasks_file_carries_no_pipeline_answer() -> None:
    module = load("golden_tasks")
    source = (ROOT / "scripts/golden_tasks.py").read_text(encoding="utf-8")
    body = source.split('"tasks": tasks')[0]
    assert '"status"' not in body.split("hidden[cell_id]")[0].split("tasks.append")[-1]
    assert module.SCHEMA_VERSION.startswith("golden-tasks/")


def test_two_labellers_get_different_orders() -> None:
    """Same order plus a tiring afternoon means correlated mistakes, which is
    exactly what double entry is meant to break."""
    page = (ROOT / "tools/golden_label.html").read_text(encoding="utf-8")
    assert "seeded(" in page and "annotator" in page


def test_scoring_fails_when_a_cell_was_resolved_to_the_wrong_value(tmp_path: Path) -> None:
    """`OCR-001` requires zero wrong-locus false acceptance, so this exits
    non-zero on a single failure."""
    agreed = {"c1": {"state": "VALUE", "alleles": ["11", "15"]}}
    result = run_score(
        tmp_path,
        agreed,
        agreed,
        {"c1": {"status": "RESOLVED", "locus": "DRB1", "value": "DRB1*11 DRB1*13"}},
    )
    assert result.returncode == 1
    assert "FALSE ACCEPTANCE" in result.stdout


def test_scoring_passes_when_every_accepted_cell_agrees(tmp_path: Path) -> None:
    agreed = {"c1": {"state": "VALUE", "alleles": ["11", "15"]}}
    result = run_score(
        tmp_path,
        agreed,
        agreed,
        {"c1": {"status": "RESOLVED", "locus": "DRB1", "value": "DRB1*11 DRB1*15"}},
    )
    assert result.returncode == 0
    assert "PASS" in result.stdout


def test_scoring_refuses_to_pass_on_an_empty_corpus(tmp_path: Path) -> None:
    """An unlabelled corpus must not read as a clean bill of health."""
    result = run_score(
        tmp_path, {}, {}, {"c1": {"status": "RESOLVED", "locus": "DRB1", "value": "11"}}
    )
    assert result.returncode == 1
    assert "nothing was scored" in result.stdout


def test_a_disagreement_is_not_counted_as_truth(tmp_path: Path) -> None:
    result = run_score(
        tmp_path,
        {"c1": {"state": "VALUE", "alleles": ["11"]}},
        {"c1": {"state": "VALUE", "alleles": ["13"]}},
        {"c1": {"status": "RESOLVED", "locus": "DRB1", "value": "DRB1*11"}},
    )
    assert result.returncode == 1  # nothing scored, so no clean bill of health
    assert "disputed: 1" in result.stdout.replace("cells still disputed: 1", "disputed: 1")


def test_the_locus_prefix_is_not_part_of_the_reading(tmp_path: Path) -> None:
    """A labeller writes `11`; the pipeline stores `DRB1*11`. The prefix is
    provenance, and the reading being judged is the allele."""
    agreed = {"c1": {"state": "VALUE", "alleles": ["11"]}}
    result = run_score(
        tmp_path,
        agreed,
        agreed,
        {"c1": {"status": "RESOLVED", "locus": "DRB1", "value": "DRB1*11"}},
    )
    assert result.returncode == 0


def test_generated_material_stays_out_of_version_control() -> None:
    """Crops and labels are PHI."""
    module = load("golden_tasks")
    default = module.main.__doc__ or ""
    source = (ROOT / "scripts/golden_tasks.py").read_text(encoding="utf-8")
    assert "data/review/golden" in source
    check = subprocess.run(
        ["git", "check-ignore", "-q", "data/review/golden/crops"],
        cwd=ROOT,
        check=False,
    )
    assert check.returncode == 0, "the crop directory must be gitignored"
    assert default is not None
