"""Adding another engine's readings to the review pack.

Runs on the synthetic pack built by `test_review_pack`; nothing here reads the
archive.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.task("BOOT-001")

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/suggest_pass.py"
PAGE = ROOT / "tools/hla_review.html"


def load():
    spec = importlib.util.spec_from_file_location("km_suggest_pass", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["km_suggest_pass"] = module
    spec.loader.exec_module(module)
    return module


def pack_at(tmp_path: Path) -> Path:
    """A synthetic pack, built by the same fixture the pack's own tests use."""
    spec = importlib.util.spec_from_file_location(
        "km_review_pack_x", ROOT / "scripts/review_pack.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["km_review_pack_x"] = module
    spec.loader.exec_module(module)
    fixture = importlib.util.spec_from_file_location(
        "km_pack_fixture", Path(__file__).with_name("test_review_pack.py")
    )
    fixture_module = importlib.util.module_from_spec(fixture)
    assert fixture is not None and fixture.loader is not None
    sys.modules["km_pack_fixture"] = fixture_module
    fixture.loader.exec_module(fixture_module)
    db, export = fixture_module.synthetic_corpus(tmp_path, n_docs=10)
    out = tmp_path / "pack"
    module.build_pack(db, export, out, 6, 1, PAGE)
    return out


def test_the_crops_come_from_the_pack_not_the_archive(tmp_path: Path) -> None:
    """The pack carries its own copy of every photo. Reading the archive again
    would mean the suggestions could silently be cut from a different file than
    the one the reviewer is looking at."""
    module = load()
    source = SCRIPT.read_text(encoding="utf-8")
    assert "ChatExport" not in source and "--export" not in source
    pack = json.loads((pack_at(tmp_path) / "pack.json").read_text(encoding="utf-8"))
    for _cell_id, image, boxes in module.cells_with_boxes(pack):
        assert image.startswith("images/")
        assert boxes


def test_dumping_crops_names_every_cell_it_wrote(tmp_path: Path) -> None:
    """An engine outside this repository gets a manifest, not a guess at the
    file naming."""
    module = load()
    pack_dir = pack_at(tmp_path)
    out = tmp_path / "dump"
    assert module.dump_crops(pack_dir, out, None) == 0
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "hla-crop-manifest/v1"
    assert manifest["cells"]
    for entry in manifest["cells"]:
        assert (out / entry["crop"]).exists()
        assert ":" not in entry["crop"], "a colon is not a legal filename on Windows"


def test_an_engine_outside_the_repository_is_refused_here(tmp_path: Path) -> None:
    """Adding a dependency needs the OSS register and the lockfile updated,
    which is not this script's decision."""
    module = load()
    pack_dir = pack_at(tmp_path)
    with pytest.raises(ValueError, match="dump-crops"):
        module.run(pack_dir, "paddleocr-v5", tmp_path / "out", 1, 8)


def test_readings_are_written_in_the_shape_the_pack_consumes(tmp_path: Path) -> None:
    """`review_pack.py --suggestions` reads {engine, cells:{cell_id: text}}, and
    the page shows one row per engine per cell."""
    module = load()
    pack_dir = pack_at(tmp_path)
    out = tmp_path / "suggestions"
    assert module.run(pack_dir, "onnxtr:crnn_mobilenet_v3_small", out, 4, 8) == 0
    written = list(out.glob("*.json"))
    assert len(written) == 1
    payload = json.loads(written[0].read_text(encoding="utf-8"))
    assert payload["schema"] == "hla-suggestions/v1"
    assert payload["engine"] == "onnxtr-crnn_mobilenet_v3_small"
    assert payload["cells"]
    pack = json.loads((pack_dir / "pack.json").read_text(encoding="utf-8"))
    known = {c["cell_id"] for d in pack["documents"] for c in d["cells"]}
    assert set(payload["cells"]) <= known


def test_a_suggestion_never_becomes_a_fact() -> None:
    """It is shown to a person and judged, and that is all it can be.

    The other engines in this pipeline write verdicts into the database; this
    one holds no database handle at all, so a reading it produces cannot reach
    a fact by any path short of a person typing it.
    """
    source = SCRIPT.read_text(encoding="utf-8")
    assert "import sqlite3" not in source and "sqlite3.connect" not in source
    for line in source.splitlines():
        code = line.lstrip()
        if code.startswith("#"):
            continue
        for statement in ("INSERT INTO", "UPDATE fact", "DELETE FROM"):
            assert statement not in code.upper()
