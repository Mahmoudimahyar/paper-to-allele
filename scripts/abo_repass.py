#!/usr/bin/env python3
"""Re-read ABO and Rh where a doubled cell was one printed token, not two values.

`read_abo` refused any cell holding more than one parsing box, on the reasoning
that two values in one cell means the cell is wrong. Measured, 1,113 documents
reach that branch and **996 of them are one printed token that both engines
boxed** — the Latin pass (onnxtr) and the Persian pass (easyocr) each drew a
rectangle around the same ink, and their two readings AGREE. Refusing those cost
993 documents a blood group and 760 an Rh for no safety at all.

`documents/abo.py::_one_token_read_twice` now collapses that case behind three
gates, of which the first does all the work: identical parsed values, boxes
overlapping by `_MIN_IOU`, and two different engines. The genuinely different
cells — 117 of them — still go to a person.

Measured A/B over all 23,566 documents, the gate on against the gate off:
**993 gained, 0 lost, 0 values changed on a document already resolved.**

Against every independent check available:

    282 chat claims          0 letter contradictions, 0 sign
    the reviewer's answers   6 of 6 correct
    PP-OCRv5 whole-page     14 of 14 agree
    PP-OCRv6 on our boxes   14 of 14 agree
    control: what already ships   10 letter errors in 1,003 (1.0%)

So the collapsed readings are measurably no worse than the readings the
pipeline already trusts. The 95% upper bound is 1.06%, not zero, which is why
the disagreeing cells stay in review and why every fact here records BOTH boxes
it agreed on, so a reviewer can see the agreement rather than take it on trust.

This applies the reading to the extracted corpus rather than running
`refresh_facts.py`, which rebuilds every fact and resets the later passes.

**The cell window, since s19 item 1.** Given `--geometry` this pass hands
`read_abo` the page RAW-frame lattice, so some of the cells it collapses were
admitted by the label ruled ROW or by the centre band rather than by the label
own line. Those rows are marked: `rule_id` becomes `abo/anchored-cell+band` or
`+centre` on the ABO row and on the RH row beside it. Measured on the live
store, 34 of the rows this pass writes come from a rescued reading (17 band, 17
centre) and 4 documents are resolved by the grid that are not resolved without
it (23 against 19). Without the marker those 4 published values would be
invisible to `rule_id LIKE 'abo/anchored-cell+%'`, which is the handle HA-019
withdraws the group by, and to the review strata that sample it.

**Comparison sheets.** 2 of the 993 are pages carrying two subjects. They are
written, because `extract_facts` applies its comparison-sheet downgrade only to
HLA loci and 64 such pages ALREADY ship a resolved ABO — refusing the 2 while
leaving the 64 would be an inconsistency dressed as a safeguard. The exposure is
66 documents and it is recorded as HA-018 for a person to decide, not silently
changed here.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from kidneymatch.documents.abo import (  # noqa: E402
    AboStatus,
    read_abo,
    reconcile_abo,
    rule_id_for,
)
from kidneymatch.ocr.anchors import Box  # noqa: E402
from kidneymatch.ocr.lattice import Lattice, lattice_for  # noqa: E402
from kidneymatch.ocr.rulings import GEOMETRY_VERSION  # noqa: E402

EV = "facts/v1"
DOUBLED = "more than one blood-group value in a single cell"
COLLAPSED_REASON = "one printed value that both engines boxed, and they agree"


def boxes_of(geometry_json: str | None, texts_json: str | None) -> list[Box]:
    geometry = json.loads(geometry_json or "[]")
    texts = json.loads(texts_json or "[]")
    return [Box(b[0], b[1], b[2], b[3], t) for b, t in zip(geometry, texts, strict=False)]


def raw_lattices(geometry_db: Path, keep: set[str] | None = None) -> dict[str, Lattice]:
    """Every page's printed grid in the frame the STORED boxes are in.

    RAW, never levelled: `read_abo` is handed the boxes as the two passes wrote
    them, so a grid rotated into the level frame would place the row band
    somewhere the boxes are not. Measured on the ruled-row rescue, the levelled
    grid gives 45 documents instead of 43 — three ROTATE pages gained on a row
    that is not theirs and one lost.
    """
    if not geometry_db.exists():
        return {}
    con = sqlite3.connect(f"file:{geometry_db.as_posix()}?mode=ro", uri=True)
    try:
        rows = {
            sha: (int(w), int(h), hj, vj)
            for sha, w, h, hj, vj in con.execute(
                "SELECT sha256, width, height, h_rulings_json, v_rulings_json FROM page_geometry "
                "WHERE geometry_version=? AND h_rulings_json IS NOT NULL AND width IS NOT NULL",
                (GEOMETRY_VERSION,),
            )
            if keep is None or sha in keep
        }
    except sqlite3.OperationalError:
        return {}
    finally:
        con.close()
    built = ((sha, lattice_for(sha, rows, None)) for sha in rows)
    return {sha: lattice for sha, lattice in built if lattice is not None}


def run(
    facts: Path, persian_db: Path, ocr_db: Path, geometry_db: Path | None = None, *, dry_run: bool
) -> Counter:
    con = sqlite3.connect(facts)
    tally: Counter[str] = Counter()
    # Only the cells this change can affect: the ones refused as doubled, plus
    # the ones a caption resolved while the image itself was refused as doubled.
    work = {
        sha: (status, value, source)
        for sha, status, value, source in con.execute(
            "SELECT sha256, status, value, source FROM fact WHERE extraction_version=? "
            "AND field='ABO'",
            (EV,),
        )
    }
    persian = sqlite3.connect(f"file:{persian_db.as_posix()}?mode=ro", uri=True)
    ocr = sqlite3.connect(f"file:{ocr_db.as_posix()}?mode=ro", uri=True)
    P = {
        sha: boxes_of(b, t)
        for sha, b, t in persian.execute(
            "SELECT sha256, boxes_json, texts_json FROM persian_result WHERE n_boxes>0"
        )
    }
    L: dict[str, list[Box]] = {}
    # The recognizer the reading is made from. 15 of the rows this pass writes
    # were resolved by the caption pass first, and a row that now says the form
    # printed the value must not keep `caption-abo/v1` beside it: that names
    # the reader of a chat message, and the value did not come from one.
    engines: dict[str, str] = {}
    for sha, rel, engine, b, t in ocr.execute(
        "SELECT sha256, rel_path, engine_version, boxes_json, texts_json FROM ocr_result "
        "WHERE n_boxes>0"
    ):
        if "_thumb" not in rel and sha not in L:
            L[sha] = boxes_of(b, t)
            engines[sha] = engine
    persian.close()
    ocr.close()
    grids = raw_lattices(geometry_db, set(work)) if geometry_db else {}

    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    for sha, (status, value, source) in sorted(work.items()):
        reading = read_abo(P.get(sha, []), L.get(sha, []), lattice=grids.get(sha))
        if reading.status is not AboStatus.RESOLVED:
            continue
        if len(reading.value_boxes) < 2:
            continue  # not a collapsed cell; this pass has nothing to say
        decision = reconcile_abo(reading)
        if decision.status is not AboStatus.RESOLVED:
            continue
        if status == "RESOLVED":
            if (value or "") != (decision.group or ""):
                tally["!! a resolved value would CHANGE; refused"] += 1
                continue
            tally[f"already resolved, now read from the form ({source})"] += 1
        else:
            tally["newly resolved from a doubled cell"] += 1
        # How the value box entered the cell, on the row it is written to.
        # Without it a value this pass publishes from a rescued reading is
        # indistinguishable from an ordinary anchored read: `rule_id LIKE
        # 'abo/anchored-cell+%'` would not find it, the `abo_band_rescue`
        # stratum would not sample it, and the group could not be withdrawn.
        rule_id = rule_id_for(reading)
        if reading.rescued:
            tally[f"...admitted by the {reading.rescued.value.lower()} route"] += 1
        if dry_run:
            continue
        con.execute(
            "UPDATE fact SET status='RESOLVED', value=?, raw=?, reason=?, source=?, "
            "engine_version=?, repaired=?, rule_id=?, anchor_box=?, value_boxes=?, created_utc=? "
            "WHERE sha256=? AND field='ABO' AND extraction_version=?",
            (
                decision.group,
                reading.raw_value,
                f"{COLLAPSED_REASON}; {reading.reason}" if reading.reason else COLLAPSED_REASON,
                decision.source.value,
                engines.get(sha),
                int(reading.repaired),
                rule_id,
                json.dumps(
                    [
                        reading.anchor_box.x0,
                        reading.anchor_box.y0,
                        reading.anchor_box.x1,
                        reading.anchor_box.y1,
                    ]
                )
                if reading.anchor_box
                else None,
                json.dumps([[b.x0, b.y0, b.x1, b.y1] for b in reading.value_boxes]),
                now,
                sha,
                EV,
            ),
        )
        con.execute(
            "UPDATE fact SET status='RESOLVED', value=?, reason=?, rule_id=?, source=?, "
            "engine_version=?, created_utc=? "
            "WHERE sha256=? AND field='RH' AND extraction_version=? AND status!='RESOLVED'",
            (
                decision.rh.value,
                "the Rh sign is printed in the same token as the group",
                rule_id,
                decision.source.value,
                engines.get(sha),
                now,
                sha,
                EV,
            ),
        )
    con.commit()
    con.close()
    return tally


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--persian", type=Path, default=ROOT / "data/derived/persian_pass.sqlite")
    parser.add_argument("--ocr", type=Path, default=ROOT / "data/derived/ocr_pass.sqlite")
    parser.add_argument("--geometry", type=Path, default=ROOT / "data/derived/geometry.sqlite")
    parser.add_argument("--dry-run", action="store_true", help="count, change nothing")
    args = parser.parse_args()
    tally = run(args.facts, args.persian, args.ocr, args.geometry, dry_run=args.dry_run)
    print(f"{'would re-read' if args.dry_run else 're-read'} the doubled blood-group cells")
    for name, count in sorted(tally.items(), key=lambda kv: -kv[1]):
        if count:
            print(f"  {name[:64]:<66}{count:>7,}")
    print(
        "Only cells where both engines boxed ONE token and agreed. A cell holding two "
        "genuinely different values still goes to a person, and every fact records both boxes."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
