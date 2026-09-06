#!/usr/bin/env python3
"""Bind a cell our own detector never boxed, from boxes read off the whole page.

Every second opinion this project has bought so far has been an opinion about
OUR boxes: `confirm_pass.py` and `reread_refused.py` hand a recognizer the crop
our detector drew. That cannot help a cell whose box was never drawn, and the
reviewer named the gap — "you are just feeding them the cropped image, what if
we give them the entire image? there are some OCR models that understand the
structure very well."

`page_ocr_pass.py` reads whole pages with PP-OCRv5-server detection and
recognition, locally. Measured on the reviewer's 160 labelled non-DRB3/4/5
cells, through the identical binding rule:

    boxes from                  correct   missed   locus label found
    our detector                     67       16                 138
    PaddleOCR, whole page            63       20                 142

The two disagree in both directions: the whole page is correct on 7 cells ours
misses, and ours is correct on 11 the whole page misses. Neither dominates, so
this pass takes the union rather than a side. Our detector's reading always
stands; the whole page is asked ONLY about cells our pipeline left unresolved,
and only its own anchor may place the locus.

Every gate the resolver applies applies here, because this calls the resolver:
the locus comes from a printed label found in the whole-page boxes and never
from the text of a value, a value must parse and be admissible, a candidate
nearer another label belongs to that label, and a locus holds at most two
alleles. What the pass adds is the honest provenance that these boxes are a
different detector's, so a reviewer can tell them apart and withdraw them as a
group if they do not hold up.
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
from page_ocr_pass import ENGINE_VERSION as PAGE_ENGINE  # noqa: E402

from kidneymatch.hla.vocabulary import load_vocabulary  # noqa: E402
from kidneymatch.ocr.anchors import Box, ResolutionStatus, resolve_locus  # noqa: E402
from kidneymatch.ocr.layout import reading_direction  # noqa: E402
from kidneymatch.ocr.rows import page_slopes  # noqa: E402

EV = "facts/v1"
LOCI = ("A", "B", "C", "DRB1", "DQA1", "DQB1", "DPA1", "DPB1")
SOURCE = "page-ocr+wholepage"
REASON = (
    "our detector drew no usable box in this cell; the locus label and its value were both "
    "found by a second detector reading the whole page, and every binding gate ran on them"
)
BELOW_REASON = (
    "read from the whole page as a COLUMN of a form whose locus labels are headers: the "
    "labels stand side by side on one printed line and the value sits in its label's own "
    "column beneath it"
)


class Document:
    """The little of a document the geometry helpers need."""

    __slots__ = ("height", "sha256", "width")

    def __init__(self, sha256: str, width: int, height: int) -> None:
        self.sha256, self.width, self.height = sha256, width, height


def page_boxes(con: sqlite3.Connection, sha: str) -> tuple[list[Box], int, int]:
    row = con.execute(
        "SELECT boxes_json, texts_json, width, height FROM page_ocr_result "
        "WHERE sha256=? AND engine_version=? AND error IS NULL",
        (sha, PAGE_ENGINE),
    ).fetchone()
    if not row:
        return [], 1, 1
    boxes = json.loads(row[0] or "[]")
    texts = json.loads(row[1] or "[]")
    return (
        [Box(b[0], b[1], b[2], b[3], t) for b, t in zip(boxes, texts, strict=False)],
        int(row[2] or 1),
        int(row[3] or 1),
    )


def unresolved(con: sqlite3.Connection, shas: set[str]) -> dict[str, list[str]]:
    """Loci each document has NOT resolved. Our own reading is never touched."""
    out: dict[str, list[str]] = {}
    placeholders = ",".join("?" * len(LOCI))
    for sha, field in con.execute(
        f"SELECT sha256, field FROM fact WHERE extraction_version=? AND field IN ({placeholders}) "
        "AND status != 'RESOLVED'",
        (EV, *LOCI),
    ):
        if sha in shas:
            out.setdefault(sha, []).append(field)
    return out


def slopes_for(document: Document, rulings, frame) -> tuple[float, float]:
    """This page's row fall and column lean, from its own stored rulings."""
    stored = rulings.get(document.sha256)
    if stored is None:
        return 0.0, 0.0
    width, height, horizontal, _ = stored
    try:
        segments = json.loads(horizontal or "[]")
    except ValueError:
        return 0.0, 0.0
    return page_slopes(segments, width, height, frame) or (0.0, 0.0)


def rule_for(con: sqlite3.Connection, sha: str):
    rule_id = (
        con.execute(
            "SELECT rule_id FROM fact WHERE sha256=? AND extraction_version=? "
            "AND rule_id IS NOT NULL LIMIT 1",
            (sha, EV),
        ).fetchone()
        or [""]
    )[0]
    return FAMILY_RULE if (rule_id or "").startswith("family/") else DEFAULT_RULE


def run(facts_db: Path, page_db: Path, geometry_db: Path, *, dry_run: bool = False) -> Counter[str]:
    vocabulary = load_vocabulary()
    con = sqlite3.connect(facts_db)
    page = sqlite3.connect(f"file:{page_db.as_posix()}?mode=ro", uri=True)
    read = {
        row[0]
        for row in page.execute(
            "SELECT sha256 FROM page_ocr_result WHERE engine_version=? AND error IS NULL",
            (PAGE_ENGINE,),
        )
    }
    geometry = load_geometry(geometry_db)
    rulings = load_rulings(geometry_db)
    work = unresolved(con, read)
    tally: Counter[str] = Counter()
    tally["documents read whole"] = len(read)
    tally["cells our pipeline left unresolved"] = sum(len(v) for v in work.values())
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    for sha, loci in sorted(work.items()):
        boxes, width, height = page_boxes(page, sha)
        if not boxes:
            continue
        document = Document(sha, width, height)
        frame = frame_for(document, geometry)
        if frame is not None:
            boxes = frame.rectify(boxes)[0]
        rows, columns = slopes_for(document, rulings, frame)
        # Which way does this form read? Asked of the page, not assumed: a page
        # whose labels are column headers binds nothing at all under a rule
        # that looks rightwards (`ocr/layout.py`).
        layout = reading_direction(boxes, rows, columns)
        rule = BELOW_RULE if layout.direction == "below" else rule_for(con, sha)
        rule = replace(rule, row_slope=rows, column_slope=columns)
        reason = BELOW_REASON if layout.direction == "below" else REASON
        tally[f"read {layout.direction}"] += 1
        for locus in loci:
            result = resolve_locus(boxes, locus, rule, vocabulary=vocabulary)
            if result.status is not ResolutionStatus.RESOLVED or not result.values:
                tally["the whole page settles nothing either"] += 1
                continue
            tally[f"bound from the whole page: {locus}"] += 1
            if dry_run:
                continue
            con.execute(
                "UPDATE fact SET status='RESOLVED', value=?, reason=?, source=?, repaired=1, "
                "second_allele=?, created_utc=? WHERE sha256=? AND field=? "
                "AND extraction_version=?",
                (
                    " ".join(str(v) for v in result.values),
                    reason,
                    SOURCE,
                    result.second_allele.value if result.second_allele else None,
                    now,
                    sha,
                    locus,
                    EV,
                ),
            )
        con.commit()
    con.commit()
    con.close()
    return tally


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--page", type=Path, default=ROOT / "data/derived/page_ocr.sqlite")
    parser.add_argument("--geometry", type=Path, default=ROOT / "data/derived/geometry.sqlite")
    parser.add_argument("--dry-run", action="store_true", help="count, change nothing")
    args = parser.parse_args()
    if not args.page.exists():
        print(f"missing {args.page.name}; run scripts/page_ocr_pass.py first")
        return 2
    tally = run(args.facts, args.page, args.geometry, dry_run=args.dry_run)
    verb = "would bind" if args.dry_run else "bound"
    print(f"{verb} cells from pages read whole ({PAGE_ENGINE})")
    for name, count in sorted(tally.items()):
        print(f"  {name:<52}{count:>8,}")
    print(
        "Our own detector's readings are never touched: only cells the pipeline left "
        "unresolved are offered to the whole-page boxes, and every binding gate still runs."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
