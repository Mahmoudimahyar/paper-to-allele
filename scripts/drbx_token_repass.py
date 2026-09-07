#!/usr/bin/env python3
"""Place the DRB3/4/5 row from the page's own geometry where no header was read.

9,207 documents carry no box the grouped-header pattern reaches, and all three
genes UNKNOWN with the reason `no grouped DRB3/4/5 header on this document`.

The yield, MEASURED 2026-09-07 against the live stores with every gate the rule
now ships (an earlier 578/579 in this docstring described no build that ever
shipped, and is corrected here): the rule places the row on **479 pages and
writes 621 PRESENT cells** — DRB3 349, DRB4 230, DRB5 42. On 476 of those 479
accepted rows a box DOES stand in the label column of the placed row; 394 carry
the header's `DR` stem in a spelling no header pattern reads and 6 more spell an
enumeration the damage-tolerant pattern reads but standing where the geometry
gate will not call it a header. What is missing on those pages is the READING of
the enumeration, not the enumeration.

Against the DRB1 row on the same 479 pages: 479 CONSISTENT, 0
FORBIDDEN_GENE_PRESENT, 0 EXPECTED_GENE_ABSENT, with 438 pages whose DRB1 read
two fields corroborating 573 of the 621 genes. Zero failures in 573 is a
rule-of-three upper bound of 3/573 = 0.52% on the corroborated share, which is
the ONLY bound this route has: no labelled page carries one of its calls.

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
  the route. Both now come from the RULE as well as from this pass, so a full
  re-extraction reproduces them; the review stratum is keyed on the rule_id,
  which is the half that a re-extraction cannot drop.

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
    TOKEN_ANCHORED_UNRESOLVED_RULE_ID,
    GeneCall,
    resolve_token_anchored_drbx,
)

EV = "facts/v1"
GENES = ("DRB3", "DRB4", "DRB5")
SOURCE = "token-anchored-drbx"
# The relaxed route (W2(a), 2026-09-07) is its own source as well as its own
# rule id, so one statement finds it, one review stratum shows it, and one
# statement withdraws it without touching the corroborated route beside it.
UNRESOLVED_SOURCE = "token-anchored-drbx+unresolved-drb1"


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
    corpus with no comparison sheets in it, and the second is not true here:
    450 documents carry the flag today. A missing table or column raises on its
    own; an EMPTY RESULT does not, and that is the shape this fails closed on —
    a `document` table populated under a different `extraction_version` answers
    the query perfectly well and answers it with nothing. 444 of the 456
    refusals this pass makes come from the stored flag, so losing it silently
    would put the right gene of the wrong person into the store.
    """
    sheets = {
        sha
        for (sha,) in con.execute(
            "SELECT sha256 FROM document WHERE extraction_version=? AND comparison_sheet=1",
            (EV,),
        )
    }
    if not sheets:
        raise RuntimeError(
            f"no comparison sheets found under extraction_version={EV!r}; the corpus has 450, "
            "so this is a query that ran and found nothing rather than a corpus without them. "
            "Refusing to run: a row on a two-subject sheet cannot say whose gene it prints."
        )
    return sheets


def run(
    facts: Path,
    ocr_db: Path,
    geometry_db: Path,
    *,
    dry_run: bool = True,
    limit: int | None = None,
    allow_unresolved_drb1: bool = False,
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
        drb1_resolved = sha in keep
        if not drb1_resolved and not allow_unresolved_drb1:
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
            boxes,
            drb1_resolved=drb1_resolved,
            row_slope=slope,
            lattice=lattice,
            allow_unresolved_drb1=allow_unresolved_drb1,
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
        # The relaxed route's facts never borrow the corroborated route's
        # provenance: the rule already stamps the id, and the source follows it.
        relaxed = not drb1_resolved
        rule_id = TOKEN_ANCHORED_UNRESOLVED_RULE_ID if relaxed else TOKEN_ANCHORED_RULE_ID
        source = UNRESOLVED_SOURCE if relaxed else SOURCE
        for gene, fact in named.items():
            tally[f"PRESENT{' (DRB1 unresolved)' if relaxed else ''}: {gene}"] += 1
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
                    rule_id,
                    source,
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
        "--allow-unresolved-drb1",
        action="store_true",
        help="also read the row on pages whose DRB1 VALUE was never resolved, under G2b "
        "(no allele value may stand on the placed row); its own rule id and source",
    )
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
    tally = run(
        args.facts,
        args.ocr,
        args.geometry,
        dry_run=args.dry_run,
        limit=args.limit,
        allow_unresolved_drb1=args.allow_unresolved_drb1,
    )
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
