#!/usr/bin/env python3
"""Re-read every unresolved blood-group cell with the current label reader.

`documents/abo.py` now reads the field label in the spellings the recognizer
actually produces — a damaged group word immediately followed by a damaged blood
word, inside one box (CV_RESEARCH s16 Tier 1, verified with placebo controls).
That widening reaches cells the extraction refused as "no blood-group field
label on this document", and this applies it to the extracted corpus without a
full refresh.

Measured A/B over all 23,566 documents, the pair route on against off:

    newly RESOLVED                 291
    UNKNOWN -> REVIEW_REQUIRED     322   (a label found, its cell still unread)
    RESOLVED -> REVIEW_REQUIRED      1   (a new anchor made one cell doubled)

That one loss is the verifier's own predicted cost and it is accepted: the cell
goes to a person rather than being guessed, and 291 documents gain a group.

Only cells that are NOT resolved are touched, and only when the reader now
resolves them. A cell that resolves to a value already written by the caption
pass is left as the caption wrote it if the two agree, and refused to review if
they do not — a chat claim and a printed form disagreeing is a question for a
person. Provenance travels: anchor box, value boxes, raw text.

**The cell window as well, since s19 item 1.** Given `--geometry`, this pass
hands `read_abo` the page's RAW-frame lattice, so a value on the label's own
ruled row is read even where its box misses the label's line, and an unruled
page falls to the centre band behind its gates. Two things follow for a
reviewer, and both are written:

* the fact's `rule_id` becomes `abo/anchored-cell+band` or `+centre`, which is
  how this group is found and, if the labels turn against it, withdrawn;
* an uncorroborated ruled-row reading — one engine, no caption — is NOT
  published. It is written as REVIEW_REQUIRED carrying the candidate box, so
  the reviewer sees a crop of the value instead of "its cell could not be read".
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

from abo_repass import boxes_of, raw_lattices  # noqa: E402

from kidneymatch.documents.abo import AboReading, AboStatus, read_abo, reconcile_abo  # noqa: E402
from kidneymatch.ocr.anchors import Box  # noqa: E402

EV = "facts/v1"
REASON = (
    "the field label is printed in a spelling the reader now knows, and its cell holds one value"
)


def rule_id_of(reading: AboReading) -> str:
    """How the value box entered the cell, as part of the rule's identity."""
    return "abo/anchored-cell" + (f"+{reading.rescued.value.lower()}" if reading.rescued else "")


def _json_box(b: Box | None) -> str | None:
    return json.dumps([b.x0, b.y0, b.x1, b.y1]) if b else None


def _json_boxes(reading: AboReading) -> str:
    boxes = list(reading.value_boxes) or ([reading.value_box] if reading.value_box else [])
    return json.dumps([[b.x0, b.y0, b.x1, b.y1] for b in boxes])


def run(
    facts: Path, persian_db: Path, ocr_db: Path, geometry_db: Path | None = None, *, dry_run: bool
) -> Counter[str]:
    con = sqlite3.connect(facts)
    persian = sqlite3.connect(f"file:{persian_db.as_posix()}?mode=ro", uri=True)
    ocr = sqlite3.connect(f"file:{ocr_db.as_posix()}?mode=ro", uri=True)
    work = {
        sha: (status, reason)
        for sha, status, reason in con.execute(
            "SELECT sha256, status, reason FROM fact WHERE extraction_version=? AND field='ABO' "
            "AND status != 'RESOLVED'",
            (EV,),
        )
    }
    P = {
        sha: boxes_of(b, t)
        for sha, b, t in persian.execute(
            "SELECT sha256, boxes_json, texts_json FROM persian_result WHERE n_boxes>0"
        )
        if sha in work
    }
    L: dict[str, list[Box]] = {}
    for sha, rel, b, t in ocr.execute(
        "SELECT sha256, rel_path, boxes_json, texts_json FROM ocr_result WHERE n_boxes>0"
    ):
        if sha in work and "_thumb" not in rel and sha not in L:
            L[sha] = boxes_of(b, t)
    persian.close()
    ocr.close()
    grids = raw_lattices(geometry_db, set(work)) if geometry_db else {}

    tally: Counter[str] = Counter()
    tally["unresolved ABO cells examined"] = len(work)
    tally["of those, pages that print a grid"] = len(grids)
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    for sha, (status, _reason) in sorted(work.items()):
        reading = read_abo(P.get(sha, []), L.get(sha, []), lattice=grids.get(sha))
        rule_id = rule_id_of(reading)
        if reading.status is AboStatus.RESOLVED:
            decision = reconcile_abo(reading)
            if decision.status is AboStatus.REVIEW_REQUIRED and reading.rescued:
                # F1: a value on the label's ruled row that nothing corroborates
                # is not published. The candidate travels so the reviewer gets a
                # crop of the value rather than "its cell could not be read".
                tally["ruled-row candidate, uncorroborated: to review"] += 1
                if dry_run:
                    continue
                con.execute(
                    "UPDATE fact SET status='REVIEW_REQUIRED', reason=?, rule_id=?, "
                    "anchor_box=?, value_boxes=?, created_utc=? "
                    "WHERE sha256=? AND field='ABO' AND extraction_version=?",
                    (
                        decision.reason,
                        rule_id,
                        _json_box(reading.anchor_box),
                        _json_boxes(reading),
                        now,
                        sha,
                        EV,
                    ),
                )
                continue
            if decision.status is not AboStatus.RESOLVED:
                tally["reader resolved; reconciliation refused"] += 1
                continue
            tally[
                "newly resolved"
                + (f" ({reading.rescued.value.lower()})" if reading.rescued else "")
            ] += 1
            if dry_run:
                continue
            con.execute(
                "UPDATE fact SET status='RESOLVED', value=?, raw=?, reason=?, source=?, "
                "repaired=?, rule_id=?, anchor_box=?, value_boxes=?, created_utc=? "
                "WHERE sha256=? AND field='ABO' AND extraction_version=?",
                (
                    decision.group,
                    reading.raw_value,
                    decision.reason or REASON,
                    decision.source.value,
                    int(reading.repaired),
                    rule_id,
                    _json_box(reading.anchor_box),
                    _json_boxes(reading),
                    now,
                    sha,
                    EV,
                ),
            )
            con.execute(
                "UPDATE fact SET status='RESOLVED', value=?, reason=?, source=?, created_utc=? "
                "WHERE sha256=? AND field='RH' AND extraction_version=? AND status!='RESOLVED'",
                (
                    decision.rh.value,
                    "the Rh sign is printed in the same token as the group",
                    decision.source.value,
                    now,
                    sha,
                    EV,
                ),
            )
        elif reading.status is AboStatus.REVIEW_REQUIRED and status == "UNKNOWN":
            # A label is now found and the cell still cannot be read: the page
            # moves from "nothing here" to "a person should look", with the
            # anchor recorded so the reviewer's crop lands on the field.
            tally["label now found, cell unread: to review"] += 1
            if dry_run:
                continue
            con.execute(
                "UPDATE fact SET status='REVIEW_REQUIRED', reason=?, anchor_box=?, created_utc=? "
                "WHERE sha256=? AND field='ABO' AND extraction_version=?",
                (
                    reading.reason,
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
                    now,
                    sha,
                    EV,
                ),
            )
        else:
            tally["unchanged"] += 1
    con.commit()
    con.close()
    return tally


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--persian", type=Path, default=ROOT / "data/derived/persian_pass.sqlite")
    parser.add_argument("--ocr", type=Path, default=ROOT / "data/derived/ocr_pass.sqlite")
    parser.add_argument(
        "--geometry",
        type=Path,
        default=ROOT / "data/derived/geometry.sqlite",
        help="page rulings; without them the cell window is the label's line alone",
    )
    parser.add_argument("--dry-run", action="store_true", help="count, change nothing")
    args = parser.parse_args()
    tally = run(args.facts, args.persian, args.ocr, args.geometry, dry_run=args.dry_run)
    print(f"{'would re-read' if args.dry_run else 're-read'} the unresolved blood-group cells")
    for name, count in sorted(tally.items(), key=lambda kv: -kv[1]):
        if count:
            print(f"  {name:<48}{count:>7,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
