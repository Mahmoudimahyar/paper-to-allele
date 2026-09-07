#!/usr/bin/env python3
"""Place the DRB3/4/5 row from the page's own geometry where no header was read.

9,207 documents carry no box the grouped-header pattern reaches, and all three
genes UNKNOWN with the reason `no grouped DRB3/4/5 header on this document`.
Measured over that population, 578 of them still print a gene token standing on
the row the page's own label pitch puts one row below `DRB1`, and on 578 of 579
accepted rows a box DOES stand in the label column — header-shaped on 534 of
them, the header with its digits misread. What is missing on those pages is the
READING of the enumeration, not the enumeration.

`ocr/drbx.resolve_token_anchored_drbx` is the rule and carries the twelve gates
and the evidence for each; this script is only the pass that applies it to the
corpus. What matters here is what it is allowed to touch:

* **only cells this exact abstention left behind.** A cell is rewritten only
  when it is UNKNOWN with the no-header reason and no `source` has claimed it,
  so nothing this pass does can overwrite a value any other rule produced;
* **PRESENT only.** No cell is ever written ABSENT here, and a gene the row did
  not name is left exactly as it was;
* **the same page conditions the extraction applies** — the page's DRB1 fact
  RESOLVED, no comparison sheet, the boxes levelled by the stored frame and the
  row followed along the page's own slope;
* **the comparison-sheet guard fails CLOSED.** If the query that names those
  pages cannot run, no page is processed at all: the alternative is publishing
  the right gene of the wrong person;
* **every fact records the boxes it was read from**, so the reviewer sees a
  crop rather than a value with no pixels behind it;
* `source='token-anchored-drbx'` and `rule_id='TOKEN_ANCHORED_DRBX/v1'` on
  every fact, so the whole group can be found, reviewed as its own stratum
  (`review_pack.py`) and withdrawn in one statement if HA-011 decides against
  the route.

`--dry-run` is the DEFAULT. Pass `--no-dry-run` to write.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from extract_facts import frame_for, lattice_for, load_geometry, load_rulings  # noqa: E402
from page_ocr_bind import Document, slopes_for  # noqa: E402
from prefix_bind import page_boxes  # noqa: E402

from kidneymatch.ocr.drbx import (  # noqa: E402
    NO_GROUPED_HEADER_REASON,
    TOKEN_ANCHORED_RULE_ID,
    GeneCall,
    resolve_token_anchored_drbx,
)

EV = "facts/v1"
GENES = ("DRB3", "DRB4", "DRB5")
SOURCE = "token-anchored-drbx"


def open_read_only(path: Path) -> sqlite3.Connection:
    """A derived store this pass only measures. Read-only, and enforced."""
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)


def untouched_cells(con: sqlite3.Connection) -> dict[str, set[str]]:
    """Genes still holding the header route's own no-header abstention.

    `source IS NULL` is what keeps this pass off every other rule's work: a
    cell some later pass has already claimed is not this one's to rewrite.
    """
    out: dict[str, set[str]] = defaultdict(set)
    placeholders = ",".join("?" * len(GENES))
    for sha, field in con.execute(
        f"SELECT sha256, field FROM fact WHERE extraction_version=? AND field IN ({placeholders}) "
        "AND status='UNKNOWN' AND reason=? AND source IS NULL",
        (EV, *GENES, NO_GROUPED_HEADER_REASON),
    ):
        out[sha].add(field)
    return dict(out)


def resolved_drb1(con: sqlite3.Connection, shas: set[str]) -> set[str]:
    """Pages whose DRB1 row the extraction resolved, as it finally stands.

    Load-bearing, not decorative: measured, 0 of 21,764 DRB1 value boxes on
    DRB1-RESOLVED pages fall inside this rule's row window, and all 116 pages
    that have one are pages whose DRB1 the resolver refused — a DRB1 chain that
    walked into the grouped row.
    """
    return {
        sha
        for (sha,) in con.execute(
            "SELECT sha256 FROM fact WHERE extraction_version=? AND field='DRB1' "
            "AND status='RESOLVED'",
            (EV,),
        )
        if sha in shas
    }


def comparison_sheets(con: sqlite3.Connection) -> set[str]:
    """Pages holding two people. Raises rather than returning an empty set.

    An empty set from a query that could not run is indistinguishable from a
    corpus with no comparison sheets in it, and the second is not true here.
    """
    return {
        sha
        for (sha,) in con.execute(
            "SELECT sha256 FROM document WHERE extraction_version=? AND comparison_sheet=1",
            (EV,),
        )
    }


def run(
    facts: Path,
    ocr_db: Path,
    geometry_db: Path,
    *,
    dry_run: bool = True,
    limit: int | None = None,
) -> Counter[str]:
    # A dry run opens the store READ-ONLY. It has no business holding a write
    # handle on a live database, and the mode is the proof rather than the
    # promise.
    con = open_read_only(facts) if dry_run else sqlite3.connect(facts)
    ocr = open_read_only(ocr_db)
    geometry = load_geometry(geometry_db)
    rulings = load_rulings(geometry_db)
    sheets = comparison_sheets(con)
    work = untouched_cells(con)
    keep = resolved_drb1(con, set(work))
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())

    tally: Counter[str] = Counter()
    tally["pages holding the no-header abstention"] = len(work)
    seen = 0
    for sha, fields in sorted(work.items()):
        if limit is not None and seen >= limit:
            break
        seen += 1
        if sha in sheets:
            tally["G0: a comparison sheet; a row cannot say whose gene it is"] += 1
            continue
        if sha not in keep:
            tally["G2: the DRB1 row is not resolved on this page"] += 1
            continue
        boxes, width, height = page_boxes(ocr, sha)
        if not boxes:
            tally["no stored boxes for this page"] += 1
            continue
        document = Document(sha, width, height)
        frame = frame_for(document, geometry)
        back: dict[int, object] = {}
        if frame is not None:
            boxes, back = frame.rectify(boxes)
        slope, _ = slopes_for(document, rulings, frame)
        lattice = lattice_for(document, rulings, frame)
        row = resolve_token_anchored_drbx(
            boxes, drb1_resolved=True, row_slope=slope, lattice=lattice
        )
        if row.facts is None:
            tally[row.reason] += 1
            continue

        named = {
            gene: fact
            for gene, fact in row.facts.items()
            if fact.call is GeneCall.PRESENT and gene in fields
        }
        if not named:
            tally["the row named a gene another pass has already claimed"] += 1
            continue
        tally["pages the row was placed on"] += 1
        for gene, fact in named.items():
            tally[f"PRESENT: {gene}"] += 1
            if dry_run:
                continue
            gene_boxes = [back.get(id(box), box) for box in fact.gene_boxes]
            anchor = back.get(id(fact.header_box), fact.header_box)
            con.execute(
                "UPDATE fact SET status='RESOLVED', value='PRESENT', raw=?, reason=?, "
                "rule_id=?, source=?, repaired=0, anchor_box=?, value_boxes=?, created_utc=? "
                "WHERE sha256=? AND field=? AND extraction_version=? AND status='UNKNOWN' "
                "AND source IS NULL",
                (
                    fact.raw_text,
                    fact.reason,
                    TOKEN_ANCHORED_RULE_ID,
                    SOURCE,
                    json.dumps([anchor.x0, anchor.y0, anchor.x1, anchor.y1]),
                    json.dumps([[b.x0, b.y0, b.x1, b.y1] for b in gene_boxes]),
                    now,
                    sha,
                    gene,
                    EV,
                ),
            )
        if not dry_run:
            con.commit()
    if not dry_run:
        con.commit()
    con.close()
    ocr.close()
    return tally


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--ocr", type=Path, default=ROOT / "data/derived/ocr_pass.sqlite")
    parser.add_argument("--geometry", type=Path, default=ROOT / "data/derived/geometry.sqlite")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="count and change nothing (the default); --no-dry-run writes",
    )
    args = parser.parse_args()
    for path in (args.facts, args.ocr):
        if not path.exists():
            print(f"missing {path}")
            return 2
    tally = run(args.facts, args.ocr, args.geometry, dry_run=args.dry_run, limit=args.limit)
    print(f"{'would place' if args.dry_run else 'placed'} the DRB3/4/5 row from page geometry")
    for name, count in sorted(tally.items()):
        if count:
            print(f"  {name:<72}{count:>8,}")
    print(
        "PRESENT only: no absence is certified on a page whose printed enumeration was never "
        "read. Every fact carries source='token-anchored-drbx' and can be withdrawn as a group."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
