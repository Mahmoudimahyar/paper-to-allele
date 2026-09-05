"""The geometry pass is resumable, versioned, and writes nothing but geometry.

Everything runs on synthetic pages rendered here; nothing touches the corpus.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")
from PIL import Image, ImageDraw  # noqa: E402

pytestmark = pytest.mark.task("OCR-001")

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/geometry_pass.py"


def load():
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("km_geometry_pass", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def ruled(width: int = 900, height: int = 1200, angle: float = 0.0) -> Image.Image:
    image = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(image)
    x0, y0, x1, y1 = 90, 180, width - 90, height - 180
    for r in range(13):
        y = y0 + (y1 - y0) * r // 12
        draw.line([(x0, y), (x1, y)], fill=0, width=3)
    for c in range(5):
        x = x0 + (x1 - x0) * c // 4
        draw.line([(x, y0), (x, y1)], fill=0, width=3)
    for r in range(12):
        y = y0 + (y1 - y0) * r // 12 + 20
        draw.text((x0 + 10, y), "HLA-A", fill=0)
        draw.text((x0 + 220, y), "A*02", fill=0)
    if angle:
        image = image.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255)
    return image


def export_with(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """Three originals and one thumbnail; returns the export and name->sha."""
    export = tmp_path / "export"
    photos = export / "photos"
    photos.mkdir(parents=True)
    ruled(angle=7.0).save(photos / "photo_tilted.jpg", quality=90)
    ruled().save(photos / "photo_straight.jpg", quality=90)
    Image.new("L", (900, 1200), 255).save(photos / "photo_blank.jpg", quality=90)
    ruled().resize((180, 240)).save(photos / "photo_straight_thumb.jpg", quality=80)
    load()
    from ocr_pass import sha256_file  # noqa: PLC0415 - sibling script

    shas = {p.name: sha256_file(p) for p in photos.iterdir()}
    return export, shas


def test_the_pass_classifies_and_is_keyed_by_version(tmp_path: Path) -> None:
    mod = load()
    export, shas = export_with(tmp_path)
    db = tmp_path / "geometry.sqlite"
    assert mod.run(export, db, None, 2) == 0

    conn = sqlite3.connect(db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "page_geometry" in tables
    assert "ocr_result" not in tables, "the geometry pass must never write OCR results"
    pk = [r[1] for r in conn.execute("PRAGMA table_info(page_geometry)") if r[5]]
    assert set(pk) == {"sha256", "geometry_version"}

    rows = {
        r[0]: r
        for r in conn.execute(
            "SELECT rel_path, decision, theta_deg, n_horizontal, h_rulings_json, error "
            "FROM page_geometry WHERE geometry_version=?",
            (mod.GEOMETRY_VERSION,),
        )
    }
    conn.close()
    # the thumbnail is not a document of the corpus
    assert set(rows) == {
        "photos/photo_tilted.jpg",
        "photos/photo_straight.jpg",
        "photos/photo_blank.jpg",
    }
    tilted = rows["photos/photo_tilted.jpg"]
    assert tilted[1] == "ROTATE"
    assert tilted[2] == pytest.approx(-7.0, abs=0.3)
    assert tilted[3] >= 6
    rulings = json.loads(tilted[4])
    assert rulings and all(len(seg) == 4 for seg in rulings)
    assert rows["photos/photo_straight.jpg"][1] == "STRAIGHT"
    assert rows["photos/photo_straight.jpg"][2] == 0.0
    assert rows["photos/photo_blank.jpg"][1] == "UNCERTAIN"
    assert all(r[5] is None for r in rows.values())


def test_a_second_run_does_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    mod = load()
    export, _ = export_with(tmp_path)
    db = tmp_path / "geometry.sqlite"
    mod.run(export, db, None, 10)
    capsys.readouterr()
    mod.run(export, db, None, 10)
    out = capsys.readouterr().out
    assert "0 to analyse" in out


def test_a_pack_restricts_the_pass_to_its_documents(tmp_path: Path) -> None:
    mod = load()
    export, shas = export_with(tmp_path)
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "pack.json").write_text(
        json.dumps({"documents": [{"sha256": shas["photo_tilted.jpg"]}]}), encoding="utf-8"
    )
    db = tmp_path / "geometry.sqlite"
    mod.run(export, db, None, 10, only=mod.pack_documents(pack))
    conn = sqlite3.connect(db)
    paths = [r[0] for r in conn.execute("SELECT rel_path FROM page_geometry")]
    conn.close()
    assert paths == ["photos/photo_tilted.jpg"]


def test_an_unreadable_image_is_recorded_not_fatal(tmp_path: Path) -> None:
    mod = load()
    export = tmp_path / "export"
    (export / "photos").mkdir(parents=True)
    (export / "photos" / "photo_bad.jpg").write_bytes(b"not an image")
    db = tmp_path / "geometry.sqlite"
    assert mod.run(export, db, None, 10) == 0
    conn = sqlite3.connect(db)
    (decision, error) = conn.execute("SELECT decision, error FROM page_geometry").fetchone()
    conn.close()
    assert decision == "UNCERTAIN"
    assert error
