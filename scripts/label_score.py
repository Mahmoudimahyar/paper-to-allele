#!/usr/bin/env python3
"""Score the pipeline against every label a person has given, from any round.

`pack_score.py` scores one export against the pack it came from, and reports
what that pack showed the reviewer at the time it was cut. That is the right
instrument for judging a round, and the wrong one for judging the pipeline: the
pack is a frozen snapshot, and by the time a second round exists the first one's
`pipeline.json` describes a system that no longer runs.

This scores the LIVE database against the union of every export. It needs no
pack at all, because a cell id already carries what is needed — it is
`<sha256[:16]>:<locus>` — so a label from any round, cut from any pack, is
scored the same way by `review/golden.py`, the same rule the golden gate uses.

Nothing here is a published accuracy: the labels are one person's, unadjudicated
(KI-012, HA-007). It is the fastest honest signal the project has.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from pack_score import OUTCOME_NAMES, read_export  # noqa: E402

from kidneymatch.review.golden import classify  # noqa: E402

EV = "facts/v1"
ORDER = ("correct", "abstained", "missed", "partial", "contradicted")


def load_labels(exports: list[Path]) -> tuple[dict[str, object], dict[str, str], list[Path]]:
    """Every label, and every note, keyed by cell id. Later rounds win."""
    labels: dict[str, object] = {}
    notes: dict[str, str] = {}
    failed: list[Path] = []
    for path in exports:
        try:
            found, payload = read_export(path)
        except (OSError, ValueError, KeyError):
            failed.append(path)
            continue
        labels.update(found)
        for key, text in (payload.get("notes") or {}).items():
            if str(text).strip():
                notes[key] = str(text)
    return labels, notes, failed


def short_to_sha(con: sqlite3.Connection) -> dict[str, str]:
    return {
        row[0][:16]: row[0]
        for row in con.execute(
            "SELECT DISTINCT sha256 FROM document WHERE extraction_version=?", (EV,)
        )
    }


#: What the reviewer may enter in the document-level blood-group box. Only the
#: four letters are a READING; every other value says "there is nothing on this
#: page to read", which is a different claim and must never be scored as a
#: disagreement. Scoring `NOT_PRINTED` against a group the CHAT supplied
#: produced 13 false contradictions the first time this was measured by hand.
ABO_LETTERS = frozenset({"A", "B", "AB", "O"})
ROLE_VALUES = frozenset({"DONOR", "RECIPIENT"})


def score_document_fields(exports: list[Path], facts: Path) -> dict[str, Counter]:
    """Score ABO and ROLE, which sit on the document rather than on a cell.

    The rest of this script scores the eleven HLA cells. The blood group and the
    role are entered once per document, and they are the two fields the matcher
    gates on BEFORE it reads a single allele: an unknown group sends a pair to
    `INSUFFICIENT_ABO` and an unknown role removes it from both directions. So
    leaving them unscored measured the cheap half of the pipeline and not the
    half that decides whether a pair can be ranked at all.
    """
    entered: dict[str, dict[str, str]] = {}
    for path in exports:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if payload.get("schema") != "golden-labels/v1":
            continue
        for short, record in (payload.get("documents") or {}).items():
            entered.setdefault(short, {}).update({k: v for k, v in record.items() if v})

    out: dict[str, Counter] = {"ABO": Counter(), "ROLE": Counter()}
    con = sqlite3.connect(f"file:{facts.as_posix()}?mode=ro", uri=True)
    full = short_to_sha(con)
    held: dict[tuple[str, str], tuple[str, str | None]] = {}
    for sha, field, status, value in con.execute(
        "SELECT sha256, field, status, value FROM fact "
        "WHERE extraction_version=? AND field IN ('ABO','ROLE')",
        (EV,),
    ):
        held[(sha, field)] = (status, value)
    con.close()

    for short, record in entered.items():
        sha = full.get(short)
        if sha is None:
            continue
        for field, allowed in (("ABO", ABO_LETTERS), ("ROLE", ROLE_VALUES)):
            read = record.get(field.lower())
            if not read:
                continue
            status, value = held.get((sha, field), ("ABSENT", None))
            if read not in allowed:
                # The person says the page carries nothing. The pipeline may
                # still hold a value read from the chat, and that is not a
                # conflict: the two are answering different questions.
                out[field]["person read nothing on the page"] += 1
            elif status == "RESOLVED" and value == read:
                out[field]["correct"] += 1
            elif status == "RESOLVED":
                out[field]["CONTRADICTED"] += 1
            else:
                out[field]["missed"] += 1
    return out


def score(labels: dict[str, object], facts: Path) -> tuple[Counter, dict, list[tuple]]:
    con = sqlite3.connect(f"file:{facts.as_posix()}?mode=ro", uri=True)
    lookup = short_to_sha(con)
    total: Counter[str] = Counter()
    per_locus: dict[str, Counter] = defaultdict(Counter)
    wrong: list[tuple] = []
    for cell_id, label in sorted(labels.items()):
        head, _, locus = cell_id.rpartition(":")
        sha = lookup.get(head)
        if sha is None:
            total["document not in this extraction"] += 1
            continue
        row = con.execute(
            "SELECT status, value, second_allele, reason, source FROM fact "
            "WHERE sha256=? AND field=? AND extraction_version=?",
            (sha, locus, EV),
        ).fetchone()
        if row is None:
            total["no fact row"] += 1
            continue
        status, value, second, reason, source = row
        values = tuple(part.split("*")[-1] for part in (value or "").split() if part)
        outcome = OUTCOME_NAMES[classify(label, (status, locus, values, second))]
        total[outcome] += 1
        per_locus[locus][outcome] += 1
        if outcome in ("missed", "partial", "contradicted"):
            wrong.append((outcome, locus, label.state.value, status, reason, source))
    con.close()
    return total, per_locus, wrong


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exports", type=Path, nargs="+", help="golden-labels/v1 exports")
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--why", action="store_true", help="one line per non-correct cell")
    args = parser.parse_args()

    labels, notes, failed = load_labels(list(args.exports))
    if failed:
        print("could not read, so the score would have been over fewer labels:")
        for path in failed:
            print(f"  {path}")
        return 2
    if not labels:
        print("no labels in those exports")
        return 2
    total, per_locus, wrong = score(labels, args.facts)

    scored = sum(total[k] for k in ORDER)
    print(f"{len(labels)} labels from {len(args.exports)} round(s); {scored} scored\n")
    for key in ORDER:
        print(f"  {key:<14}{total[key]:>5}")
    other = {k: v for k, v in total.items() if k not in ORDER}
    if other:
        print(f"  other: {other}")
    print(f"\n{'locus':<7}" + "".join(f"{k:>13}" for k in ORDER))
    for locus in sorted(per_locus):
        row = per_locus[locus]
        print(f"{locus:<7}" + "".join(f"{row[k]:>13}" for k in ORDER))
    judged = total["correct"] + total["missed"] + total["partial"] + total["contradicted"]
    if judged:
        print(
            f"\ncorrect on {total['correct']} of {judged} cells a person read "
            f"({100 * total['correct'] / judged:.1f}%); "
            f"{total['contradicted']} contradicted"
        )
    if args.why:
        print("\nevery cell that is neither correct nor a correct abstention:")
        for outcome, locus, human, status, reason, source in wrong:
            trimmed = json.dumps(reason or "")[1:60]
            print(f"  {outcome:<13}{locus:<6}human={human:<13}{status:<16}{source or ''} {trimmed}")
    fields = score_document_fields(args.exports, args.facts)
    print("\nthe two fields the matcher gates on, entered once per document:")
    for field, counts in fields.items():
        judged = counts["correct"] + counts["missed"] + counts["CONTRADICTED"]
        if not judged:
            continue
        recall = 100 * counts["correct"] / judged
        print(
            f"  {field:<5} read by a person on {judged:>4}: "
            f"correct {counts['correct']:>4}, missed {counts['missed']:>4}, "
            f"contradicted {counts['CONTRADICTED']:>3}   recall {recall:.0f}%"
        )
        nothing = counts["person read nothing on the page"]
        if nothing:
            print(
                f"        plus {nothing} where the person read nothing on the "
                "page; a value held from the chat is not a contradiction there"
            )
    if notes:
        print(
            f"\n{len(notes)} notes in these exports; read them, they are the best "
            "diagnostic this project gets"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
