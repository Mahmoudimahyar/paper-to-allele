#!/usr/bin/env python3
"""Same rules, different eyes: our detector against Google Vision's.

`vision_pass.py` reads whole pages with Google Cloud Vision and stores the word
boxes in the frame `ocr_pass.sqlite` uses. This script points `ocr/anchors.py`
at one store and then the other and asks the identical question of both, so the
only variable is which engine drew and read the boxes.

It answers three things, in the order they matter:

1. **Recall on the labelled cells.** For every cell a human answered, what does
   the binding rule conclude from our boxes, and what from Vision's? Scored by
   `review/golden.py`, the same rule the golden gate uses.
2. **The empty-cell bucket.** The largest refusal in the pipeline is
   "anchor found but no box at all in its cell under this rule" — 23,719 cells
   where we located the printed label and never detected a value beside it.
   For a sample of those, does Vision put a box in that cell? That is the
   question the whole-page permission (HA-013) was granted to answer.
3. **What it would cost to be wrong.** Any labelled cell where Vision's boxes
   produce a value the human read differently is counted and shown as a shape,
   because a better detector that is confidently wrong is worse than ours.

This script writes no fact. A cloud reading is evidence about our detector, not
a laboratory value (`CV_RESEARCH_2026-09-05.md` s7). Output is counts, outcomes
and shapes: no value, caption or path of a real report is printed.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from extract_facts import DEFAULT_RULE, FAMILY_RULE  # noqa: E402
from pack_score import OUTCOME_NAMES, read_export, read_pipeline  # noqa: E402

from kidneymatch.hla.vocabulary import load_vocabulary  # noqa: E402
from kidneymatch.ocr.anchors import (  # noqa: E402
    Box,
    ResolutionStatus,
    find_anchors,
    resolve_locus,
)
from kidneymatch.review.golden import classify  # noqa: E402

EV = "facts/v1"
VISION_ENGINE = "google-vision/v1+DOCUMENT_TEXT_DETECTION"
# How far right of a label a value may sit, and how far off its line, both in
# label heights. Deliberately generous: this asks whether a box EXISTS in the
# cell at all, not whether the binding rule would accept it.
CELL_REACH = 20.0
CELL_BAND = 1.0


def shape(text: str | None) -> str:
    """A value as its shape. No printed value ever leaves this script."""
    return re.sub(r"[A-Za-z]", "L", re.sub(r"\d", "#", str(text or "")))


def boxes_from(rows: list[tuple[str, str]]) -> list[Box]:
    out: list[Box] = []
    for boxes_json, texts_json in rows:
        raw, texts = json.loads(boxes_json or "[]"), json.loads(texts_json or "[]")
        out = [Box(b[0], b[1], b[2], b[3], t) for b, t in zip(raw, texts, strict=False)]
        break
    return out


def our_boxes(ocr: sqlite3.Connection, sha: str) -> list[Box]:
    for rel, boxes_json, texts_json in ocr.execute(
        "SELECT rel_path, boxes_json, texts_json FROM ocr_result WHERE sha256=? AND n_boxes>0",
        (sha,),
    ):
        if "_thumb" in rel:
            continue
        return boxes_from([(boxes_json, texts_json)])
    return []


def vision_boxes(vision: sqlite3.Connection, sha: str) -> list[Box]:
    row = vision.execute(
        "SELECT boxes_json, texts_json FROM vision_result WHERE sha256=? AND engine_version=? "
        "AND error IS NULL",
        (sha, VISION_ENGINE),
    ).fetchone()
    return boxes_from([row]) if row else []


def rule_for(facts: sqlite3.Connection, sha: str):
    rule_id = (
        facts.execute(
            "SELECT rule_id FROM fact WHERE sha256=? AND extraction_version=? "
            "AND rule_id IS NOT NULL LIMIT 1",
            (sha, EV),
        ).fetchone()
        or [""]
    )[0]
    return FAMILY_RULE if (rule_id or "").startswith("family/") else DEFAULT_RULE


def outcome_of(label, locus: str, resolution) -> str:
    values = tuple(str(v).split("*")[-1] for v in (resolution.values or ()))
    status = "RESOLVED" if resolution.status is ResolutionStatus.RESOLVED else "REVIEW_REQUIRED"
    second = resolution.second_allele.value if resolution.second_allele else None
    return OUTCOME_NAMES[classify(label, (status, locus, values, second))]


def box_in_cell(boxes: list[Box], anchor: list[float]) -> bool:
    """Is there any box in the cell to the right of this label's box?

    The anchor is the label rectangle the resolver recorded, so this asks the
    question the refusal asked: did anything at all get detected there?
    """
    height = max(anchor[3] - anchor[1], 1e-6)
    centre = (anchor[1] + anchor[3]) / 2
    return any(
        box.x0 > anchor[2]
        and box.x0 - anchor[2] <= CELL_REACH * height
        and abs(box.centre_y - centre) <= CELL_BAND * height
        for box in boxes
    )


def compare_labels(export: Path, facts, ocr, vision, vocabulary) -> None:
    labels, _ = read_export(export)
    pipeline = read_pipeline(ROOT / "data/review/hla_pack/pipeline.json")
    pack = json.loads((ROOT / "data/review/hla_pack/pack.json").read_text(encoding="utf-8"))
    cell_doc = {c["cell_id"]: d for d in pack["documents"] for c in d["cells"]}
    grid: Counter[tuple[str, str]] = Counter()
    boxes_seen: Counter[str] = Counter()
    newly_wrong: list[str] = []
    missing = 0
    for cell_id, label in sorted(labels.items()):
        locus = pipeline.get(cell_id, ("", "?"))[1]
        if locus == "?" or cell_id not in cell_doc:
            continue
        sha = cell_doc[cell_id]["sha256"]
        theirs_boxes = vision_boxes(vision, sha)
        if not theirs_boxes:
            missing += 1
            continue
        ours_boxes = our_boxes(ocr, sha)
        rule = rule_for(facts, sha)
        ours = resolve_locus(ours_boxes, locus, rule, vocabulary=vocabulary)
        theirs = resolve_locus(theirs_boxes, locus, rule, vocabulary=vocabulary)
        a, b = outcome_of(label, locus, ours), outcome_of(label, locus, theirs)
        grid[(a, b)] += 1
        boxes_seen["ours: anchor found"] += 1 if find_anchors(ours_boxes, locus) else 0
        boxes_seen["vision: anchor found"] += 1 if find_anchors(theirs_boxes, locus) else 0
        if b == "contradicted" and a != "contradicted":
            newly_wrong.append(
                f"{locus}: human {label.state.value} vs {shape(' '.join(theirs.values or ()))}"
            )
    print("\n== the labelled cells: our boxes against Vision's, same binding rule ==")
    if missing:
        print(f"  {missing} cells skipped: no Vision reading stored for their page")
    order = ["correct", "partial", "abstained", "missed", "contradicted"]
    print(f"  {'ours \\\\ vision':<16}" + "".join(f"{k:>14}" for k in order))
    for a in order:
        if not any(grid[(a, b)] for b in order):
            continue
        print(f"  {a:<16}" + "".join(f"{grid[(a, b)] or '':>14}" for b in order))
    ours_correct = sum(n for (a, _), n in grid.items() if a == "correct")
    theirs_correct = sum(n for (_, b), n in grid.items() if b == "correct")
    scored = sum(grid.values())
    print(f"\n  correct: ours {ours_correct} / {scored}, Vision {theirs_correct} / {scored}")
    for name, count in sorted(boxes_seen.items()):
        print(f"  {name:<28}{count:>5} of {scored}")
    if newly_wrong:
        print(f"\n  cells Vision resolves against the human that we did not ({len(newly_wrong)}):")
        for line in newly_wrong[:12]:
            print(f"    {line}")


def compare_empty_cells(facts, ocr, vision, sample: int, seed: int) -> None:
    """The 23,719 cells whose label was found and whose value was never boxed."""
    rows = facts.execute(
        "SELECT f.sha256, f.field, f.anchor_box FROM fact f "
        "WHERE f.status='REVIEW_REQUIRED' AND f.extraction_version=? "
        "AND f.reason LIKE 'anchor found but no box at all%' AND f.anchor_box IS NOT NULL",
        (EV,),
    ).fetchall()
    have = {
        r[0]
        for r in vision.execute(
            "SELECT sha256 FROM vision_result WHERE engine_version=? AND error IS NULL",
            (VISION_ENGINE,),
        )
    }
    rows = [r for r in rows if r[0] in have]
    random.Random(seed).shuffle(rows)
    rows = rows[:sample]
    tally: Counter[str] = Counter()
    per_locus: Counter[str] = Counter()
    cache: dict[str, list[Box]] = {}
    for sha, field, anchor_json in rows:
        if sha not in cache:
            cache[sha] = vision_boxes(vision, sha)
        anchor = json.loads(anchor_json)
        anchor = anchor[0] if anchor and isinstance(anchor[0], list) else anchor
        found = box_in_cell(cache[sha], anchor)
        tally["Vision boxes something in the cell" if found else "Vision sees nothing either"] += 1
        if found:
            per_locus[field] += 1
    print("\n== the empty-cell bucket: label found, value never detected ==")
    print(f"  {len(rows)} such cells sampled from pages Vision has read")
    for name, count in tally.most_common():
        share = 100 * count / max(1, len(rows))
        print(f"  {name:<42}{count:>6,}  ({share:.1f}%)")
    if per_locus:
        print(f"  recovered by locus: {dict(per_locus.most_common())}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--ocr", type=Path, default=ROOT / "data/derived/ocr_pass.sqlite")
    parser.add_argument("--vision", type=Path, default=ROOT / "data/derived/vision_pass.sqlite")
    parser.add_argument("--export", type=Path, required=True, help="a golden-labels export")
    parser.add_argument("--sample", type=int, default=400)
    parser.add_argument("--seed", type=int, default=20260905)
    args = parser.parse_args()
    if not args.vision.exists():
        print(f"missing {args.vision.name}; run scripts/vision_pass.py first")
        return 2
    facts = sqlite3.connect(f"file:{args.facts.as_posix()}?mode=ro", uri=True)
    ocr = sqlite3.connect(f"file:{args.ocr.as_posix()}?mode=ro", uri=True)
    vision = sqlite3.connect(f"file:{args.vision.as_posix()}?mode=ro", uri=True)
    read, failed = vision.execute(
        "SELECT SUM(error IS NULL), SUM(error IS NOT NULL) FROM vision_result "
        "WHERE engine_version=?",
        (VISION_ENGINE,),
    ).fetchone()
    print(f"Vision has read {read or 0} pages ({failed or 0} failed)")
    if not read:
        print("nothing to compare yet")
        return 2
    vocabulary = load_vocabulary()
    compare_labels(args.export, facts, ocr, vision, vocabulary)
    compare_empty_cells(facts, ocr, vision, args.sample, args.seed)
    print("\nThis script writes no fact: a cloud reading is evidence about our detector.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
