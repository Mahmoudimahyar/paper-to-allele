#!/usr/bin/env python3
"""Re-decide ROLE where the printed form names one and the pipeline refused it.

The operator, on the archive's own Persian:

> "whenever you see something like اهدا کننده this means donner and whenever
> you see گیرنده or any other variations you should extract that the role is
> reciever. So do not miss these obvious evidence."

They were being missed, and for one reason: a role word with no `نسبت:` field
label beside it and no other form word on its row is Tier C, and Tier C alone
was refused as "a bare role word needs corroboration". Measured, that cost
**2,423 documents** whose page prints exactly one role word and nothing that
disagrees with it.

The refusal had a real number behind it — the weakest tier contradicts
recipient-only serology 20% of the time against 0% for the anchored tiers — but
that contradiction has its OWN gate two branches earlier in
`decide_document_role`, and so does a caption that disagrees, and so does a page
printing both words. Refusing again at the end charged the same evidence twice.
Against the reviewer's 50 labelled roles a bare word agrees 13 times and
disagrees once.

So `decide_document_role` now resolves it, under the distinct source
`FORM_FIELD_BARE`. This script applies that decision to the documents already
extracted, instead of a full refresh: `refresh_facts.py` rebuilds every fact in
the corpus and resets the later passes' writes, which is a much larger and
riskier operation than one field needs.

Every contradiction gate still runs first, unchanged:

* a page printing BOTH role words stays REVIEW_REQUIRED;
* a caption naming the other role vetoes the reading;
* a recipient-only test on a donor form means two subjects and refuses;
* the Persian and English fields disagreeing refuses.

`source='FORM_FIELD_BARE'` marks the whole group so it can be found, drawn into
a review stratum, and withdrawn if the reviewer's answers say it should be.
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

from caption_pass import messages_by_document, role_for  # noqa: E402

from kidneymatch.documents.role import (  # noqa: E402
    Role,
    decide_document_role,
    read_form_role,
)
from kidneymatch.ocr.anchors import Box  # noqa: E402

EV = "facts/v1"
SOURCE = "FORM_FIELD_BARE"
REASON = (
    "the form prints this role word, once, with nothing on the page or in the chat "
    "contradicting it; no field label anchors it, so this is the weakest printed evidence"
)


def boxes_from(row: tuple[str | None, str | None]) -> list[Box]:
    geometry = json.loads(row[0] or "[]")
    texts = json.loads(row[1] or "[]")
    return [Box(b[0], b[1], b[2], b[3], t) for b, t in zip(geometry, texts, strict=False)]


def unresolved_roles(con: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in con.execute(
            "SELECT sha256 FROM fact WHERE extraction_version=? AND field='ROLE' "
            "AND status != 'RESOLVED'",
            (EV,),
        )
    }


def run(facts: Path, persian_db: Path, ocr_db: Path, source_db: Path, *, dry_run: bool) -> Counter:
    con = sqlite3.connect(facts)
    work = unresolved_roles(con)
    tally: Counter[str] = Counter()
    tally["documents with no resolved role"] = len(work)

    captions: dict[str, Role] = {}
    if source_db.exists():
        # Recomputed from the messages rather than read from
        # `document_caption_claim`, whose stored claims predate the widened
        # spellings and would veto with an out-of-date reading.
        for sha, texts in messages_by_document(source_db).items():
            if sha in work:
                found = role_for(texts)
                if found is not None:
                    captions[sha] = found
    tally["of those, a caption states a role"] = len(captions)

    persian = sqlite3.connect(f"file:{persian_db.as_posix()}?mode=ro", uri=True)
    ocr = sqlite3.connect(f"file:{ocr_db.as_posix()}?mode=ro", uri=True)
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())

    for sha, boxes_json, texts_json in persian.execute(
        "SELECT sha256, boxes_json, texts_json FROM persian_result WHERE n_boxes>0"
    ):
        if sha not in work:
            continue
        persian_boxes = boxes_from((boxes_json, texts_json))
        latin_boxes: list[Box] = []
        for rel, bj, tj in ocr.execute(
            "SELECT rel_path, boxes_json, texts_json FROM ocr_result WHERE sha256=? AND n_boxes>0",
            (sha,),
        ):
            if "_thumb" in rel:
                continue
            latin_boxes = boxes_from((bj, tj))
            break
        reading = read_form_role(persian_boxes, latin_boxes)
        decision = decide_document_role(reading, caption_role=captions.get(sha, Role.UNKNOWN))
        if not decision.is_finding:
            tally[f"still refused: {decision.reason or decision.source}"] += 1
            continue
        tally[f"resolved from the form: {decision.role.value} ({decision.source})"] += 1
        if dry_run:
            continue
        con.execute(
            "UPDATE fact SET status='RESOLVED', value=?, reason=?, source=?, "
            "rule_id=?, anchor_box=?, value_boxes=?, created_utc=? "
            "WHERE sha256=? AND field='ROLE' AND extraction_version=?",
            (
                decision.role.value,
                REASON if decision.source == SOURCE else (decision.reason or REASON),
                decision.source,
                f"role/{reading.tier.value}",
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
                json.dumps([[t.box.x0, t.box.y0, t.box.x1, t.box.y1] for t in reading.tokens]),
                now,
                sha,
                EV,
            ),
        )
    con.commit()
    con.close()
    persian.close()
    ocr.close()
    return tally


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--persian", type=Path, default=ROOT / "data/derived/persian_pass.sqlite")
    parser.add_argument("--ocr", type=Path, default=ROOT / "data/derived/ocr_pass.sqlite")
    parser.add_argument("--source", type=Path, default=ROOT / "data/derived/source.sqlite")
    parser.add_argument("--dry-run", action="store_true", help="count, change nothing")
    args = parser.parse_args()
    tally = run(args.facts, args.persian, args.ocr, args.source, dry_run=args.dry_run)
    print(f"{'would re-decide' if args.dry_run else 're-decided'} ROLE from the printed form")
    for name, count in sorted(tally.items(), key=lambda kv: -kv[1]):
        if count:
            print(f"  {name[:66]:<68}{count:>7,}")
    print(
        "Every contradiction gate still runs first: both words printed, a caption naming the "
        "other role, and a recipient-only test on a donor form all still refuse."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
