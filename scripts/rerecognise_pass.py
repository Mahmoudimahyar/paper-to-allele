#!/usr/bin/env python3
"""Read our own boxes again with the best recognizer, and bind what it settles.

The primary reading of this corpus comes from `crnn_mobilenet_v3_small`, which
is the weakest engine in the building. Measured on 67 labelled value cells
(`docs/ingestion/ENGINE_BENCH_2026-09-05.md`): PP-OCRv6-medium 65 exact,
PP-OCRv5-server 55, Tesseract 32, and our own recognizer **14**. Every text in
`ocr_pass.sqlite` is its work, and everything downstream reads those texts.

The obvious move — swap the recognizer — was measured and is wrong. On the same
boxes and the same binding rule, PP-OCRv6 scores 68 of 160 labelled cells
against the shipped 67: it wins 8 and loses 7. The losses are not noise, they
are structural. Four of them are cells where **v6 lost a locus label we had**,
because `glyphs.py`'s repairs are calibrated on the measured confusions of OUR
recognizer — `DRBI` for `DRB1` is read 3.5 times more often than the truth, and
the repair for it does nothing for a different engine's different mistakes.

So the two readings are kept side by side and the union is taken, the same way
`page_ocr_bind.py` takes the union with the whole-page detector:

* our reading always stands. A cell the pipeline resolved is never re-read
  here, and our locus labels are never replaced;
* only cells the pipeline left unresolved are offered the second reading;
* every gate the resolver applies runs on it, because this calls the resolver.

Of the 10 cells still missed on the reviewer's labels after every other pass,
this settles 4: a locus label our recognizer garbled, two rows whose second
allele was unreadable, and a star our recognizer did not see.

Cost, measured: about 2 seconds a page, against 15 for reading a whole page
with a detector. The corpus is roughly 13 hours; the 150-page pack is minutes.

Usage:
    uv run --frozen --extra confirm python scripts/rerecognise_pass.py --pack
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from extract_facts import (  # noqa: E402
    BELOW_RULE,
    DEFAULT_RULE,
    FAMILY_RULE,
    frame_for,
    load_geometry,
    load_rulings,
)
from page_ocr_bind import LOCI, Document, slopes_for, unresolved  # noqa: E402
from vision_pass import (  # noqa: E402
    ALLOWED_OUTPUT_ROOT,
    documents_from_export,
    documents_from_pack,
)

from kidneymatch.hla.vocabulary import load_vocabulary  # noqa: E402
from kidneymatch.ocr.anchors import Box, ResolutionStatus, resolve_locus  # noqa: E402
from kidneymatch.ocr.crops import CONFIRMER_PADDED, prepare_crop  # noqa: E402
from kidneymatch.ocr.glyphs import canonical_locus_label  # noqa: E402
from kidneymatch.ocr.layout import reading_direction  # noqa: E402

EV = "facts/v1"
ENGINE = "ppocrv6/medium-rec+our-boxes"
SOURCE = "rerecognised+ppocrv6"
REASON = (
    "our own recognizer could not read this cell; the same boxes read again by PP-OCRv6 "
    "settled it, and every binding gate ran on that reading"
)
COMPLETED_REASON = (
    "our own recognizer read one allele of this pair and declared the other unread; the same "
    "boxes read again by PP-OCRv6 state both, and the one we already had is one of them"
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS rerecognised (
    sha256      TEXT NOT NULL,
    engine      TEXT NOT NULL,
    n_boxes     INTEGER,
    texts_json  TEXT,
    elapsed_ms  INTEGER,
    created_utc TEXT NOT NULL,
    PRIMARY KEY (sha256, engine)
);
"""


def stored_boxes(ocr: sqlite3.Connection, sha: str):
    """Our detector's boxes, its texts, and the page size."""
    for rel, boxes_json, texts_json, width, height in ocr.execute(
        "SELECT rel_path, boxes_json, texts_json, width, height FROM ocr_result "
        "WHERE sha256=? AND n_boxes>0",
        (sha,),
    ):
        if "_thumb" in rel:
            continue
        return json.loads(boxes_json), json.loads(texts_json), int(width), int(height), rel
    return None, None, 1, 1, None


def keep_our_labels(ours: list[str], fresh: list[str]) -> list[str]:
    """Our text wherever it names a locus, the second reading everywhere else.

    Our repairs are calibrated on our recognizer's confusions and rescue labels
    another engine garbles differently; on the labelled cells this is worth
    four locus anchors. The values are the other engine's, which is what it is
    better at.
    """
    return [
        ours[index] if canonical_locus_label(ours[index] or "") else fresh[index]
        for index in range(min(len(ours), len(fresh)))
    ]


def read_documents(
    documents: list[tuple[str, str]],
    export_dir: Path,
    ocr_db: Path,
    out: Path,
    *,
    limit: int | None = None,
) -> Counter[str]:
    """Re-read every stored box of each document with PP-OCRv6."""
    import numpy as np  # noqa: PLC0415
    from confirm_pass import PPOCRV6_MODEL, build_ppocr_reader  # noqa: PLC0415
    from PIL import Image, UnidentifiedImageError  # noqa: PLC0415

    ocr = sqlite3.connect(f"file:{ocr_db.as_posix()}?mode=ro", uri=True)
    con = sqlite3.connect(out)
    con.executescript(SCHEMA)
    done = {r[0] for r in con.execute("SELECT sha256 FROM rerecognised WHERE engine=?", (ENGINE,))}
    work = [(sha, rel) for sha, rel in documents if sha not in done]
    if limit is not None:
        work = work[:limit] if limit > 0 else []
    tally: Counter[str] = Counter()
    tally["already read on an earlier run"] = len(documents) - len(work)
    if not work:
        return tally
    read = build_ppocr_reader(PPOCRV6_MODEL)
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    for index, (sha, rel) in enumerate(work, 1):
        boxes, _, _, _, stored_rel = stored_boxes(ocr, sha)
        if not boxes:
            tally["no boxes to re-read"] += 1
            continue
        try:
            image = np.asarray(Image.open(export_dir / (stored_rel or rel)).convert("L"))
        except (OSError, UnidentifiedImageError):
            tally["image unreadable"] += 1
            continue
        started = time.monotonic()
        crops, kept = [], []
        for position, box in enumerate(boxes):
            crop = prepare_crop(image, box, frame=None, profile=CONFIRMER_PADDED)
            if crop is not None and crop.pixels.size:
                crops.append(Image.fromarray(crop.pixels))
                kept.append(position)
        texts = [""] * len(boxes)
        for position, reading in zip(kept, read(crops), strict=True):
            texts[position] = str(reading or "").strip()
        con.execute(
            "INSERT OR REPLACE INTO rerecognised VALUES (?,?,?,?,?,?)",
            (
                sha,
                ENGINE,
                len(boxes),
                json.dumps(texts),
                int((time.monotonic() - started) * 1000),
                now,
            ),
        )
        con.commit()
        tally["pages re-read"] += 1
        tally["boxes re-read"] += len(crops)
        if index % 10 == 0 or index == len(work):
            print(f"  {index}/{len(work)} pages", flush=True)
    con.close()
    return tally


def incomplete(con: sqlite3.Connection, shas: set[str]) -> dict[str, list[str]]:
    """Cells RESOLVED with one allele and the other declared unread.

    Not a failure — a partial read is honest, and the golden scorer counts it
    apart from both correct and wrong. But it is half a genotype, and the
    second reading is exactly the thing that may hold the other half. What is
    already read is never contradicted here: see `completes`.
    """
    out: dict[str, list[str]] = {}
    placeholders = ",".join("?" * len(LOCI))
    for sha, field in con.execute(
        f"SELECT sha256, field FROM fact WHERE extraction_version=? AND field IN ({placeholders}) "
        "AND status='RESOLVED' AND second_allele='UNREAD'",
        (EV, *LOCI),
    ):
        if sha in shas:
            out.setdefault(sha, []).append(field)
    return out


def completes(existing: str | None, found: list[str]) -> bool:
    """Does this reading ADD the missing allele rather than replace the known one?

    Both conditions matter. A reading naming two alleles neither of which we
    already had is a contradiction, not a completion, and belongs in front of a
    person rather than in the database.
    """
    had = {part for part in (existing or "").split() if part}
    return len(found) == 2 and bool(had) and had < set(found)


def bind(
    facts_db: Path, ocr_db: Path, store_db: Path, geometry_db: Path, *, dry_run: bool
) -> Counter[str]:
    """Offer the second reading to every cell the pipeline left unresolved."""
    vocabulary = load_vocabulary()
    con = sqlite3.connect(facts_db)
    ocr = sqlite3.connect(f"file:{ocr_db.as_posix()}?mode=ro", uri=True)
    store = sqlite3.connect(f"file:{store_db.as_posix()}?mode=ro", uri=True)
    read = {
        r[0] for r in store.execute("SELECT sha256 FROM rerecognised WHERE engine=?", (ENGINE,))
    }
    geometry = load_geometry(geometry_db)
    rulings = load_rulings(geometry_db)
    work = unresolved(con, read)
    half = incomplete(con, read)
    for sha, loci in half.items():
        work.setdefault(sha, []).extend(loci)
    tally: Counter[str] = Counter()
    tally["documents re-read"] = len(read)
    tally["cells the pipeline left unresolved"] = sum(len(v) for v in work.values())
    tally["cells read as half a pair"] = sum(len(v) for v in half.values())
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    for sha, loci in sorted(work.items()):
        raw, ours, width, height, _ = stored_boxes(ocr, sha)
        row = store.execute(
            "SELECT texts_json FROM rerecognised WHERE sha256=? AND engine=?", (sha, ENGINE)
        ).fetchone()
        if not raw or not row:
            continue
        fresh = json.loads(row[0])
        texts = keep_our_labels(ours, fresh)
        boxes = [Box(b[0], b[1], b[2], b[3], t) for b, t in zip(raw, texts, strict=False)]
        whole = [Box(b[0], b[1], b[2], b[3], t) for b, t in zip(raw, fresh, strict=False)]
        document = Document(sha, width, height)
        frame = frame_for(document, geometry)
        if frame is not None:
            boxes = frame.rectify(boxes)[0]
            whole = frame.rectify(whole)[0]
        rows, columns = slopes_for(document, rulings, frame)
        layout = reading_direction(boxes, rows, columns)
        rule_id = (
            con.execute(
                "SELECT rule_id FROM fact WHERE sha256=? AND extraction_version=? "
                "AND rule_id IS NOT NULL LIMIT 1",
                (sha, EV),
            ).fetchone()
            or [""]
        )[0]
        base = (
            BELOW_RULE
            if layout.direction == "below"
            else (FAMILY_RULE if (rule_id or "").startswith("family/") else DEFAULT_RULE)
        )
        rule = replace(base, row_slope=rows, column_slope=columns)
        for locus in loci:
            was = con.execute(
                "SELECT status, value FROM fact WHERE sha256=? AND field=? "
                "AND extraction_version=?",
                (sha, locus, EV),
            ).fetchone() or ("UNKNOWN", None)
            partial = was[0] == "RESOLVED"
            # Two views of the same boxes: our labels with the second reading's
            # values, and the second reading throughout. Our repairs rescue
            # labels it garbles and it reads labels ours garbles, so both are
            # offered, each fully gated, and only to a cell we could not read.
            result = None
            for view in (boxes, whole):
                candidate = resolve_locus(view, locus, rule, vocabulary=vocabulary)
                if candidate.status is ResolutionStatus.RESOLVED and candidate.values:
                    result = candidate
                    break
            if result is None:
                tally["the second reading settles nothing either"] += 1
                continue
            values = [str(v) for v in result.values]
            if partial and not completes(was[1], values):
                tally["the second reading contradicts the half we had; left alone"] += 1
                continue
            tally[f"{'completed' if partial else 'settled'}: {locus}"] += 1
            if dry_run:
                continue
            con.execute(
                "UPDATE fact SET status='RESOLVED', value=?, reason=?, source=?, repaired=1, "
                "second_allele=?, created_utc=? WHERE sha256=? AND field=? "
                "AND extraction_version=?",
                (
                    " ".join(values),
                    COMPLETED_REASON if partial else REASON,
                    SOURCE,
                    result.second_allele.value if result.second_allele else None,
                    now,
                    sha,
                    locus,
                    EV,
                ),
            )
        con.commit()
    con.close()
    return tally


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--ocr", type=Path, default=ROOT / "data/derived/ocr_pass.sqlite")
    parser.add_argument("--out", type=Path, default=ALLOWED_OUTPUT_ROOT / "rerecognised.sqlite")
    parser.add_argument("--geometry", type=Path, default=ROOT / "data/derived/geometry.sqlite")
    parser.add_argument("--export", type=Path, default=ROOT / "data/raw/ChatExport_2026-08-31")
    parser.add_argument("--pack-json", type=Path, default=ROOT / "data/review/hla_pack/pack.json")
    parser.add_argument("--from-export", type=Path, nargs="*", default=None)
    parser.add_argument("--pack", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--bind-only", action="store_true", help="skip the reading, bind what is stored"
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.out.resolve().is_relative_to(ALLOWED_OUTPUT_ROOT.resolve()):
        print("--out must be under data/derived/, the ignored tree.")
        return 2
    if not args.bind_only:
        documents: list[tuple[str, str]] = []
        failed: list[Path] = []
        if args.from_export:
            found, bad = documents_from_export(list(args.from_export), args.facts)
            documents += found
            failed += bad
        if args.pack:
            found, bad = documents_from_pack(args.pack_json, args.facts)
            documents += found
            failed += bad
        if failed:
            print("could not read, and the sample would have been silently smaller:")
            for path in failed:
                print(f"  {path}")
            return 2
        documents = sorted(set(documents))
        if not documents:
            print("no documents named: pass --from-export <labels.json> or --pack.")
            return 2
        print(f"re-reading {len(documents)} pages of our own boxes with {ENGINE}")
        for name, count in sorted(
            read_documents(documents, args.export, args.ocr, args.out, limit=args.limit).items()
        ):
            if count:
                print(f"  {name:<50}{count:>8,}")
    tally = bind(args.facts, args.ocr, args.out, args.geometry, dry_run=args.dry_run)
    print(f"{'would settle' if args.dry_run else 'settled'} cells from the second reading")
    for name, count in sorted(tally.items()):
        if count:
            print(f"  {name:<50}{count:>8,}")
    print(
        "Our own reading always stands, and our locus labels are never replaced: only cells "
        "the pipeline left unresolved are offered the second reading."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
