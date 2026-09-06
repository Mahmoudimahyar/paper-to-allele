#!/usr/bin/env python3
"""Bind a locus from the allele's own printed prefix, where the page names none.

The reviewer, against a page whose loci go unread: "This is a unique report, it
doesn't specify the loci, but we still can find the info from the alleles name.
For example A*11 belong to HLA-A."

That is a change to a rule the project states outright — "geometry/template cell
defines HLA locus; OCR text alone may not assign locus" — and it is recorded as
the operator's decision in `docs/ingestion/CV_RESEARCH_2026-09-05.md` s12. The
rule exists because a nearby WORD must never decide a gene: measured, matching
`\\bDRB1\\b` inside a value inflated apparent DRB1 presence 5.18x and put the
locus wherever a patient's allele happened to sit (KI-010). A fully-qualified
allele is a different kind of thing. `A*11` is nomenclature, not proximity: the
token states its own gene, in the notation the laboratory printed it in.

It is still the weakest evidence the pipeline accepts, so it is the last thing
tried and it is fenced:

* the locus must have **no anchor anywhere on the page**. Geometry gets first
  refusal, always, and this never overrules a printed label;
* the token must carry its own star. `B35` without one may be a serological
  spelling (HLA_VALIDATION_SPEC s4), and a bare number names nothing;
* the value must be admissible for the locus it claims;
* every box taken for one locus must sit on **one printed row**, because two
  rows are two people as easily as two alleles;
* a **comparison sheet is refused outright**. Two patients on one page means a
  prefix cannot say whose value it is, and that is the wrong-locus failure in
  its most dangerous form — a value bound to the correct gene of the wrong
  person;
* a box claimed by two loci withdraws both, as everywhere else.

Every fact it writes carries `source='prefix-bound'` and a reason that says the
locus came from the printed prefix rather than from the page's geometry, so the
whole group can be found and withdrawn if the decision is reversed.
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

from extract_facts import frame_for, load_geometry, load_rulings  # noqa: E402
from page_ocr_bind import Document, slopes_for  # noqa: E402

from kidneymatch.hla.vocabulary import load_vocabulary  # noqa: E402
from kidneymatch.ocr.anchors import Box, find_anchors  # noqa: E402
from kidneymatch.ocr.glyphs import parse_allele_values  # noqa: E402

EV = "facts/v1"
LOCI = ("A", "B", "C", "DRB1", "DQA1", "DQB1", "DPA1", "DPB1")
SOURCE = "prefix-bound"
MAX_VALUES = 2
# Two boxes are on one printed row when their centres, after following the
# page's own slope, sit within this many box heights of each other.
ROW_TOLERANCE = 1.0
REASON = (
    "the page prints no label for this locus; the value names the locus itself in its own "
    "printed prefix, and geometry was given first refusal (CV_RESEARCH s12)"
)


def page_boxes(ocr: sqlite3.Connection, sha: str) -> tuple[list[Box], int, int]:
    for rel, boxes_json, texts_json, width, height in ocr.execute(
        "SELECT rel_path, boxes_json, texts_json, width, height FROM ocr_result "
        "WHERE sha256=? AND n_boxes>0",
        (sha,),
    ):
        if "_thumb" in rel:
            continue
        boxes = json.loads(boxes_json)
        texts = json.loads(texts_json)
        return (
            [Box(b[0], b[1], b[2], b[3], t) for b, t in zip(boxes, texts, strict=False)],
            int(width or 1),
            int(height or 1),
        )
    return [], 1, 1


def unanchored(con: sqlite3.Connection) -> dict[str, list[str]]:
    """Loci a page did not resolve and for which it printed no label at all."""
    out: dict[str, list[str]] = defaultdict(list)
    placeholders = ",".join("?" * len(LOCI))
    for sha, field in con.execute(
        f"SELECT sha256, field FROM fact WHERE extraction_version=? AND field IN ({placeholders}) "
        "AND status != 'RESOLVED' AND reason LIKE 'no anchor on this document%'",
        (EV, *LOCI),
    ):
        out[sha].append(field)
    return dict(out)


def comparison_sheets(con: sqlite3.Connection) -> set[str]:
    try:
        return {
            row[0]
            for row in con.execute(
                "SELECT sha256 FROM document WHERE extraction_version=? AND comparison_sheet=1",
                (EV,),
            )
        }
    except sqlite3.OperationalError:
        return set()


def claims_for(boxes: list[Box], locus: str, vocabulary, slope: float) -> list[Box] | None:
    """The boxes on one row whose printed prefix names this locus, or None.

    None whenever the evidence is not clean: nothing claims the locus, the
    claims do not share a row, a value is not admissible, or there are more of
    them than a locus can have.
    """
    claiming: list[tuple[Box, list[str]]] = []
    for box in boxes:
        values = parse_allele_values((box.text or "").strip())
        if not values:
            continue
        if any(v.locus_prefix is None or v.locus_prefix.upper() != locus.upper() for v in values):
            continue
        if any(v.separator_missing for v in values):
            continue  # `B35` may be a serological spelling, not an allele
        if not vocabulary.covers(locus) or any(
            not vocabulary.is_admissible(locus, v.first_field) for v in values
        ):
            return None  # a claim the vocabulary refuses taints the whole page
        claiming.append((box, [v.text() for v in values]))
    if not claiming:
        return None
    first = claiming[0][0]
    for box, _ in claiming[1:]:
        lift = slope * (box.centre_x - first.centre_x)
        if abs(box.centre_y - lift - first.centre_y) > ROW_TOLERANCE * max(
            first.height, box.height
        ):
            return None  # two rows are two people as easily as two alleles
    if sum(len(values) for _, values in claiming) > MAX_VALUES:
        return None
    return [box for box, _ in claiming]


def run(facts: Path, ocr_db: Path, geometry_db: Path, *, dry_run: bool) -> Counter[str]:
    vocabulary = load_vocabulary()
    con = sqlite3.connect(facts)
    ocr = sqlite3.connect(f"file:{ocr_db.as_posix()}?mode=ro", uri=True)
    geometry = load_geometry(geometry_db)
    rulings = load_rulings(geometry_db)
    sheets = comparison_sheets(con)
    work = unanchored(con)
    tally: Counter[str] = Counter()
    tally["pages with an unanchored locus"] = len(work)
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    for sha, loci in sorted(work.items()):
        if sha in sheets:
            tally["comparison sheet; a prefix cannot say whose value it is"] += len(loci)
            continue
        boxes, width, height = page_boxes(ocr, sha)
        if not boxes:
            continue
        document = Document(sha, width, height)
        frame = frame_for(document, geometry)
        if frame is not None:
            boxes = frame.rectify(boxes)[0]
        slope, _ = slopes_for(document, rulings, frame)
        taken: dict[str, list[Box]] = {}
        for locus in loci:
            if find_anchors(boxes, locus):
                tally["the page does print this label after all"] += 1
                continue
            claimed = claims_for(boxes, locus, vocabulary, slope)
            if claimed is None:
                tally["no clean claim on this page"] += 1
                continue
            taken[locus] = claimed
        owners: dict[int, list[str]] = defaultdict(list)
        for locus, claimed in taken.items():
            for box in claimed:
                owners[id(box)].append(locus)
        contested = {locus for claims in owners.values() if len(claims) > 1 for locus in claims}
        for locus in contested:
            tally["one box claimed by two loci; both withdrawn"] += 1
            taken.pop(locus, None)
        for locus, claimed in taken.items():
            values = [
                v.text() for box in claimed for v in parse_allele_values((box.text or "").strip())
            ]
            tally[f"bound from its own prefix: {locus}"] += 1
            if dry_run:
                continue
            con.execute(
                "UPDATE fact SET status='RESOLVED', value=?, reason=?, source=?, repaired=1, "
                "second_allele=?, created_utc=? WHERE sha256=? AND field=? "
                "AND extraction_version=?",
                (
                    " ".join(values),
                    REASON,
                    SOURCE,
                    "READ" if len(values) > 1 else "UNREAD",
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
    parser.add_argument("--geometry", type=Path, default=ROOT / "data/derived/geometry.sqlite")
    parser.add_argument("--dry-run", action="store_true", help="count, change nothing")
    args = parser.parse_args()
    tally = run(args.facts, args.ocr, args.geometry, dry_run=args.dry_run)
    print(f"{'would bind' if args.dry_run else 'bound'} loci from the value's own prefix")
    for name, count in sorted(tally.items()):
        if count:
            print(f"  {name:<56}{count:>8,}")
    print(
        "This is the weakest evidence the pipeline accepts and the last thing tried: a printed "
        "label always wins, and every fact here says so in its reason."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
