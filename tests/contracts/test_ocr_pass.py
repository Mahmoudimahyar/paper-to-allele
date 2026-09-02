"""The OCR pass must be resumable and must never assign a locus.

A multi-hour run that cannot resume is a run that must be restarted from zero
after any interruption, which at 33,147 images is a real cost.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

# Acceptance for BOOT-001 selects on this marker: pytest --task BOOT-001
pytestmark = pytest.mark.task("BOOT-001")

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ocr_pass.py"


def load():
    spec = importlib.util.spec_from_file_location("km_ocr_pass", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_results_are_keyed_by_content_and_versions(tmp_path: Path) -> None:
    """Cache identity must include engine and preprocessing, or a model upgrade
    would silently reuse results produced by the previous model."""
    mod = load()
    conn = mod.connect(tmp_path / "t.sqlite")
    cols = [r[1] for r in conn.execute("PRAGMA table_info(ocr_result)")]
    pk = [r[1] for r in conn.execute("PRAGMA table_info(ocr_result)") if r[5]]
    assert set(pk) == {"sha256", "engine_version", "preproc_version"}
    for required in ("boxes_json", "texts_json", "confs_json", "error", "created_utc"):
        assert required in cols
    conn.close()


def test_completed_set_drives_resume(tmp_path: Path) -> None:
    mod = load()
    db = tmp_path / "t.sqlite"
    conn = mod.connect(db)
    assert mod.completed(conn) == set()
    conn.execute(
        "INSERT INTO ocr_result VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "abc",
            mod.ENGINE_VERSION,
            mod.PREPROC_VERSION,
            "photos/x.jpg",
            520,
            390,
            3,
            "[]",
            "[]",
            "[]",
            1.0,
            None,
            "2026-09-02T00:00:00+00:00",
        ),
    )
    conn.commit()
    assert mod.completed(conn) == {"abc"}
    conn.close()


def test_a_different_engine_version_is_not_treated_as_done(tmp_path: Path) -> None:
    mod = load()
    conn = mod.connect(tmp_path / "t.sqlite")
    conn.execute(
        "INSERT INTO ocr_result VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "abc",
            "SOME-OLDER-ENGINE",
            mod.PREPROC_VERSION,
            "photos/x.jpg",
            520,
            390,
            3,
            "[]",
            "[]",
            "[]",
            1.0,
            None,
            "2026-09-02T00:00:00+00:00",
        ),
    )
    conn.commit()
    assert mod.completed(conn) == set(), "rows from another engine must be re-done"
    conn.close()


def test_the_pass_does_not_assign_an_hla_locus() -> None:
    """ADR 0006: this stage extracts text and geometry only.

    Geometry decides the locus, and geometry comes from the template registry,
    which does not exist yet. A locus assigned here would violate OCR-001.
    """
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in ("DRB1", "DQB1", "locus", "HLA_VALUE"):
        assert f'"{forbidden}"' not in source and f"'{forbidden}'" not in source, (
            f"ocr_pass.py must not reference {forbidden}; it extracts text, not medical fields"
        )


def test_output_goes_to_the_gitignored_derived_layer() -> None:
    """OCR text from this archive is PHI and must never be committed."""
    mod = load()
    assert "data/derived" in str(mod.DEFAULT_DB).replace("\\", "/")
    import subprocess

    proc = subprocess.run(
        ["git", "check-ignore", "data/derived/ocr_pass.sqlite"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, "the OCR output path is not gitignored"


def test_the_manifest_uses_the_shared_photo_definition() -> None:
    """The script must not carry its own idea of what a corpus photo is.

    It did, and the two drifted: `endswith("_thumb.jpg")` admitted 9,581
    thumbnail copies (KI-009). The definition and its tests now live in
    `kidneymatch.ingestion.photos`; this asserts the script uses that one.
    """
    from kidneymatch.ingestion import photos

    assert load().is_original_photo is photos.is_original_photo
