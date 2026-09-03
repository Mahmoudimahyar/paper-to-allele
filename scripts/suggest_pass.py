#!/usr/bin/env python3
"""Read the review pack's cells with another engine, so the page can show it.

`tools/hla_review.html` shows one row per cell with what each engine read. The
pipeline, the Tesseract confirmer and the constrained decode are already stored
in `facts.sqlite`. This adds any *other* recognizer, in the shape
`scripts/review_pack.py --suggestions` consumes:

    {"engine": "<name>", "cells": {"<sha16>:<LOCUS>": "<reading>"}}

## Two modes, because of the dependency rule

An engine that is already a repository dependency runs here directly (`--engine
onnxtr:<architecture>`, `--engine tesseract5`). Adding a new one would need the
OSS register and the lockfile updated, which is not a decision this script may
take, so an engine that lives outside the repository is served by `--dump-crops`
instead: the crops and a manifest are written to a local directory, whatever
environment owns that engine reads them and writes the JSON back, and nothing
new enters the repository.

Crops are PHI. Everything this writes belongs under the gitignored
`data/review/`, and the summary printed here is counts only.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from PIL.Image import Image as PilImage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SUGGESTIONS_SCHEMA = "hla-suggestions/v1"
MANIFEST_SCHEMA = "hla-crop-manifest/v1"

# The same padding the Tesseract confirmer measured best with: enough not to
# clip a glyph, little enough not to pull in the neighbouring cell.
PAD_X, PAD_Y = 0.004, 0.006


def cells_with_boxes(pack: dict[str, Any]) -> list[tuple[str, str, list[list[float]]]]:
    """(cell_id, image path inside the pack, value boxes) for every packed cell.

    The pack carries its own copy of each photo, so this reads from the pack and
    never needs the archive. Boxes are page fractions, so they land identically
    on the copy.
    """
    out: list[tuple[str, str, list[list[float]]]] = []
    for document in pack["documents"]:
        for cell in document["cells"]:
            boxes = cell.get("value_boxes") or []
            if boxes:
                out.append((cell["cell_id"], document["image"], boxes))
    return out


def crop_of(image: PilImage, boxes: list[list[float]]) -> PilImage | None:
    """One crop covering every value box in the cell, with a little padding."""
    width, height = image.size
    x0 = max(0, int((min(b[0] for b in boxes) - PAD_X) * width))
    y0 = max(0, int((min(b[1] for b in boxes) - PAD_Y) * height))
    x1 = min(width, int((max(b[2] for b in boxes) + PAD_X) * width))
    y1 = min(height, int((max(b[3] for b in boxes) + PAD_Y) * height))
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    return image.crop((x0, y0, x1, y1))


def read_pack(pack_dir: Path) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads((pack_dir / "pack.json").read_text(encoding="utf-8"))
    if payload.get("schema") != "hla-review-pack/v1":
        raise ValueError(f"{pack_dir / 'pack.json'} is not a review pack")
    return payload


def load_confirm_pass() -> ModuleType:
    """`scripts/confirm_pass.py` owns the Tesseract invocation and its measured
    preprocessing; loading it keeps one copy of both."""
    spec = importlib.util.spec_from_file_location(
        "km_confirm_pass", ROOT / "scripts/confirm_pass.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load scripts/confirm_pass.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["km_confirm_pass"] = module
    spec.loader.exec_module(module)
    return module


def dump_crops(pack_dir: Path, out: Path, limit: int | None) -> int:
    """Write one PNG per cell plus a manifest, for an engine living elsewhere."""
    from PIL import Image

    pack = read_pack(pack_dir)
    work = cells_with_boxes(pack)
    if limit:
        work = work[:limit]
    out.mkdir(parents=True, exist_ok=True)
    (out / "crops").mkdir(exist_ok=True)
    manifest: list[dict[str, str]] = []
    cache: dict[str, PilImage | None] = {}
    for cell_id, rel_path, boxes in work:
        if rel_path not in cache:
            try:
                cache[rel_path] = Image.open(pack_dir / rel_path).convert("RGB")
            except OSError:
                cache[rel_path] = None
        image = cache[rel_path]
        if image is None:
            continue
        piece = crop_of(image, boxes)
        if piece is None:
            continue
        name = f"crops/{cell_id.replace(':', '_')}.png"
        piece.save(out / name)
        manifest.append({"cell_id": cell_id, "crop": name})
    (out / "manifest.json").write_text(
        json.dumps({"schema": MANIFEST_SCHEMA, "pack": pack["pack_id"], "cells": manifest}),
        encoding="utf-8",
    )
    print(f"wrote {len(manifest):,} crops and a manifest to {out}")
    print("An engine outside the repository reads manifest.json and writes")
    print('  {"engine": "<name>", "cells": {"<cell_id>": "<reading>"}}')
    print("into a suggestions directory; nothing new needs to enter the lockfile.")
    return 0


def read_with_onnxtr(crops: list[PilImage], architecture: str) -> list[str]:
    from onnxtr.models import recognition_predictor

    recognizer = recognition_predictor(architecture, batch_size=64)
    import numpy as np

    return [str(text) for text, _ in recognizer([np.asarray(c) for c in crops])]


def read_with_tesseract(crops: list[PilImage], module: ModuleType) -> list[str]:
    import tempfile

    from PIL import Image

    with tempfile.TemporaryDirectory(prefix="km-suggest-") as work_dir:
        paths = []
        for index, crop in enumerate(crops):
            grey = crop.convert("L")
            grey = grey.resize(
                (grey.width * module.UPSCALE, grey.height * module.UPSCALE),
                Image.Resampling.LANCZOS,
            )
            path = Path(work_dir) / f"{index:05d}.png"
            grey.save(path)
            paths.append(path)
        return list(module.read_crops(module.find_tesseract(None), paths))


def run(pack_dir: Path, engine: str, out: Path, limit: int, batch: int) -> int:
    from PIL import Image

    pack = read_pack(pack_dir)
    work = cells_with_boxes(pack)
    if limit:
        work = work[:limit]
    print(f"cells to read with {engine}: {len(work):,}", flush=True)
    readings: dict[str, str] = {}
    started = time.perf_counter()
    cache: dict[str, PilImage | None] = {}
    for start in range(0, len(work), batch):
        chunk = work[start : start + batch]
        crops, ids = [], []
        for cell_id, rel_path, boxes in chunk:
            if rel_path not in cache:
                try:
                    cache[rel_path] = Image.open(pack_dir / rel_path).convert("RGB")
                except OSError:
                    cache[rel_path] = None
            image = cache[rel_path]
            if image is None:
                continue
            piece = crop_of(image, boxes)
            if piece is not None:
                crops.append(piece)
                ids.append(cell_id)
        if not crops:
            continue
        if engine.startswith("onnxtr:"):
            texts = read_with_onnxtr(crops, engine.split(":", 1)[1])
        elif engine == "tesseract5":
            texts = read_with_tesseract(crops, load_confirm_pass())
        else:
            raise ValueError(
                f"unknown engine {engine!r}; use onnxtr:<architecture>, tesseract5, "
                "or --dump-crops for an engine outside this repository"
            )
        readings.update(dict(zip(ids, texts, strict=True)))
        seen = min(start + batch, len(work))
        rate = seen / max(time.perf_counter() - started, 1e-9)
        print(f"  {seen:>7,}/{len(work):,}  {rate:5.1f} cell/s", flush=True)

    out.mkdir(parents=True, exist_ok=True)
    name = engine.replace(":", "-")
    path = out / f"{name}.json"
    path.write_text(
        json.dumps({"schema": SUGGESTIONS_SCHEMA, "engine": name, "cells": readings}),
        encoding="utf-8",
    )
    empty = sum(1 for text in readings.values() if not text.strip())
    print(f"\nwrote {len(readings):,} readings to {path}  ({empty:,} empty)")
    print("Rebuild the pack with --suggestions to show them:")
    print(f"  python scripts/review_pack.py --suggestions {out}")
    print("These are suggestions for a person to judge. Nothing here becomes a fact.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, default=ROOT / "data/review/hla_pack")
    parser.add_argument("--out", type=Path, default=ROOT / "data/review/suggestions")
    parser.add_argument(
        "--engine",
        default="onnxtr:parseq",
        help="onnxtr:<architecture> or tesseract5; anything else needs --dump-crops",
    )
    parser.add_argument("--dump-crops", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=128)
    args = parser.parse_args()
    if not (args.pack / "pack.json").exists():
        print(f"missing {args.pack / 'pack.json'}; run scripts/review_pack.py first")
        return 2
    if args.dump_crops:
        return dump_crops(args.pack, args.dump_crops, args.limit)
    return run(args.pack, args.engine, args.out, args.limit, args.batch_size)


if __name__ == "__main__":
    raise SystemExit(main())
