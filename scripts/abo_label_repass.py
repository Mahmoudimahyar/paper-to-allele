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
page falls to the centre band behind its gates. Three things follow for a
reviewer, and all three are written:

* the fact's `rule_id` becomes `abo/anchored-cell+band` or `+centre`, which is
  how this group is found and, if the labels turn against it, withdrawn;
* an uncorroborated ruled-row reading — one engine, no caption — is NOT
  published. It is written as REVIEW_REQUIRED carrying the candidate box, so
  the reviewer sees a crop of the value instead of "its cell could not be read";
* the reason names the two things the admission turned on: how tall the label's
  ruled row was, in anchor heights, and how many engines boxed the value.

**Where the caption half of that rule actually lives.** `reconcile_abo`
publishes a single-engine ruled-row value when a caption names the same letter,
and on this store that class is NOT in the unresolved work set: the caption
pass already answered those cells, so they are RESOLVED with
`source='CAPTION_CLAIM'`. They are re-read separately, against `--source`, and
where the form prints the same group the row keeps its VALUE and changes its
PROVENANCE — anchor box, value box, raw text, `rule_id`, and a source that says
the form rather than the poster. Measured on the live store: 12 rows. The
centre route is deliberately not upgraded that way; HA-019 blocks treating a
centre-band reading as something a match may rest on until a person has checked
some, and moving one off `CAPTION_CLAIM` would do exactly that.

Measured dry run over the live stores, with the grid and the messages:

    newly resolved (centre)                            31
    newly resolved (band)                              13
    caption row upgraded to a form reading (band)      12
    ruled-row candidate, uncorroborated: to review     13
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
from caption_pass import claim_for, messages_by_document  # noqa: E402

from kidneymatch.documents.abo import (  # noqa: E402
    AboReading,
    AboStatus,
    Rh,
    needs_corroboration,
    read_abo,
    reconcile_abo,
    rule_id_for,
)
from kidneymatch.ocr.anchors import Box  # noqa: E402

EV = "facts/v1"
REASON = (
    "the field label is printed in a spelling the reader now knows, and its cell holds one value"
)
UPGRADE_REASON = (
    "the form prints this group on the label's own ruled row, and the messages state the same "
    "letter; the value is unchanged and its provenance is now the form, not the poster"
)


def caption_claims(source_db: Path | None, keep: set[str]) -> dict[str, tuple[str, Rh]]:
    """The blood group every message a photograph was posted with agrees on.

    Read by `caption_pass.claim_for`, so the two passes can never drift: a
    message naming two groups, or asking FOR one, says nothing, and two
    messages naming different groups leave the document alone.

    Nothing here is PUBLISHED from a caption — that is `caption_pass.py`'s job
    and it writes `source='CAPTION_CLAIM'`. This is F1(b) only: a value the
    label's ruled ROW admitted on one engine's word is published as a FORM
    reading when, and only when, the caption independently names the same
    letter. Without this the caption half of F1 is unreachable and every
    single-box band reading goes to review.
    """
    if source_db is None or not source_db.exists():
        return {}
    out: dict[str, tuple[str, Rh]] = {}
    for sha, texts in messages_by_document(source_db).items():
        if sha not in keep:
            continue
        group, rh, _ = claim_for(texts)
        if group:
            out[sha] = (group, Rh(rh) if rh in set(Rh) else Rh.UNKNOWN)
    return out


def _json_box(b: Box | None) -> str | None:
    return json.dumps([b.x0, b.y0, b.x1, b.y1]) if b else None


def _json_boxes(reading: AboReading) -> str:
    boxes = list(reading.value_boxes) or ([reading.value_box] if reading.value_box else [])
    return json.dumps([[b.x0, b.y0, b.x1, b.y1] for b in boxes])


def run(
    facts: Path,
    persian_db: Path,
    ocr_db: Path,
    geometry_db: Path | None = None,
    source_db: Path | None = None,
    *,
    dry_run: bool,
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
    # A cell the caption already answered is NOT in `work`, because it is
    # RESOLVED. That is where F1(b)'s corroborated band readings live on this
    # store: the poster said the letter, the caption pass wrote it, and the
    # form was never read. They are worked separately and their VALUE is never
    # touched — only the provenance, which stops saying "a claim by whoever
    # posted it" about a group the form prints.
    upgrades = {
        sha: value
        for sha, value in con.execute(
            "SELECT sha256, value FROM fact WHERE extraction_version=? AND field='ABO' "
            "AND status = 'RESOLVED' AND source = 'CAPTION_CLAIM'",
            (EV,),
        )
    }
    wanted = set(work) | set(upgrades)
    P = {
        sha: boxes_of(b, t)
        for sha, b, t in persian.execute(
            "SELECT sha256, boxes_json, texts_json FROM persian_result WHERE n_boxes>0"
        )
        if sha in wanted
    }
    L: dict[str, list[Box]] = {}
    # The recognizer whose boxes the reading is made from. A row that says the
    # form printed the value must not keep `caption-abo/v1` beside it: that
    # names the reader of a chat message, and the value did not come from one.
    engines: dict[str, str] = {}
    for sha, rel, engine, b, t in ocr.execute(
        "SELECT sha256, rel_path, engine_version, boxes_json, texts_json FROM ocr_result "
        "WHERE n_boxes>0"
    ):
        if sha in wanted and "_thumb" not in rel and sha not in L:
            L[sha] = boxes_of(b, t)
            engines[sha] = engine
    persian.close()
    ocr.close()
    grids = raw_lattices(geometry_db, wanted) if geometry_db else {}
    said = caption_claims(source_db, wanted)

    tally: Counter[str] = Counter()
    tally["unresolved ABO cells examined"] = len(work)
    tally["cells a caption alone resolved, re-read against the form"] = len(upgrades)
    tally["of those, pages that print a grid"] = len(grids)
    tally["documents a caption states a group for"] = len(said)
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    for sha, (status, _reason) in sorted(work.items()):
        reading = read_abo(P.get(sha, []), L.get(sha, []), lattice=grids.get(sha))
        rule_id = rule_id_for(reading)
        if reading.status is AboStatus.RESOLVED:
            # F1(b). The caption is consulted for one thing: corroborating a
            # value only the label's ruled row admitted, boxed by one engine.
            # It is withheld everywhere else, so no cell here is resolved from
            # a chat claim and no conflict is raised that `caption_pass.py`
            # does not already record.
            claim = said.get(sha) if needs_corroboration(reading) else None
            if claim is not None:
                tally["band candidate with a caption stating a group"] += 1
            decision = reconcile_abo(reading, caption_claims={claim} if claim else None)
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
                + (", the caption agreeing" if claim is not None else "")
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
                "UPDATE fact SET status='RESOLVED', value=?, reason=?, rule_id=?, source=?, "
                "created_utc=? "
                "WHERE sha256=? AND field='RH' AND extraction_version=? AND status!='RESOLVED'",
                (
                    decision.rh.value,
                    "the Rh sign is printed in the same token as the group",
                    rule_id,
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

    # F1(b) on the rows the caption already answered. Only a value the label's
    # own ruled ROW admits, boxed by ONE engine, with the messages naming the
    # same letter — the exact class `reconcile_abo` refuses to publish on the
    # form's word alone and publishes with the caption behind it. The centre
    # route is deliberately NOT upgraded here: HA-019 blocks treating a
    # centre-band reading as something a match may rest on until a person has
    # checked one, and moving it off CAPTION_CLAIM would do exactly that.
    for sha, value in sorted(upgrades.items()):
        reading = read_abo(P.get(sha, []), L.get(sha, []), lattice=grids.get(sha))
        if not needs_corroboration(reading):
            continue
        claim = said.get(sha)
        if claim is None:
            tally["band candidate under a caption row, no claim re-derived"] += 1
            continue
        decision = reconcile_abo(reading, caption_claims={claim})
        if decision.status is not AboStatus.RESOLVED:
            tally[f"band candidate under a caption row, refused ({decision.status.value})"] += 1
            continue
        if (value or "") != (decision.group or ""):
            # Cannot happen while `reconcile_abo` conflicts on a different
            # letter, and it is asserted anyway: this pass never changes a
            # value, it only says where the value came from.
            tally["!! a caption row's value would CHANGE; refused"] += 1
            continue
        tally["caption row upgraded to a form reading (band)"] += 1
        if dry_run:
            continue
        con.execute(
            "UPDATE fact SET raw=?, reason=?, source=?, engine_version=?, repaired=?, "
            "rule_id=?, anchor_box=?, value_boxes=?, created_utc=? "
            "WHERE sha256=? AND field='ABO' AND extraction_version=? AND value=?",
            (
                reading.raw_value,
                f"{UPGRADE_REASON} ({reading.reason})",
                decision.source.value,
                engines.get(sha),
                int(reading.repaired),
                rule_id_for(reading),
                _json_box(reading.anchor_box),
                _json_boxes(reading),
                now,
                sha,
                EV,
                value,
            ),
        )
        con.execute(
            "UPDATE fact SET status='RESOLVED', value=?, reason=?, rule_id=?, source=?, "
            "engine_version=?, created_utc=? WHERE sha256=? AND field='RH' "
            "AND extraction_version=? "
            "AND (status!='RESOLVED' OR (source='CAPTION_CLAIM' AND value=?))",
            (
                decision.rh.value,
                "the Rh sign is printed in the same token as the group",
                rule_id_for(reading),
                decision.source.value,
                engines.get(sha),
                now,
                sha,
                EV,
                decision.rh.value,
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
    parser.add_argument(
        "--geometry",
        type=Path,
        default=ROOT / "data/derived/geometry.sqlite",
        help="page rulings; without them the cell window is the label's line alone",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=ROOT / "data/derived/source.sqlite",
        help="the messages; without them a one-engine ruled-row value cannot be corroborated",
    )
    parser.add_argument("--dry-run", action="store_true", help="count, change nothing")
    args = parser.parse_args()
    tally = run(
        args.facts, args.persian, args.ocr, args.geometry, args.source, dry_run=args.dry_run
    )
    print(f"{'would re-read' if args.dry_run else 're-read'} the unresolved blood-group cells")
    for name, count in sorted(tally.items(), key=lambda kv: -kv[1]):
        if count:
            print(f"  {name:<48}{count:>7,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
