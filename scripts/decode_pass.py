#!/usr/bin/env python3
"""Re-read every resolved cell under the grammar, and abstain where it wobbles.

The recognizer's greedy path can spell things the cell's grammar forbids, and
the post-hoc repair then guesses what was meant. Constraining the decode to the
grammar removes the guess. What that buys is **not** a better value — measured,
the constrained decode agrees with the stored first field on 296 of 300 real
cells — but an abstention signal the pipeline does not otherwise have: a cell
whose reading changes when the crop moves by one pixel is being accepted today
on a coin toss.

## What this pass may and may not do

It may **take a fact away**. It may not create one, and it may not change one.

A constrained decode turns ANY crop into a grammatically valid allele: measured
here, **200 of 200** locus-label crops decode to a parseable allele. So the
decode never runs before geometry, and `resolve_locus`'s gates keep seeing the
raw text. This pass reads only boxes those gates already accepted.

## The two signals, and which one actually works

**Digit preservation is the gate.** The grammar allows a two- or three-digit
field and TRUNCATES a longer one rather than refusing it, so `DPB1*1055` decodes
as `DPB1*055` — a different allele. Comparing the digits the model saw against
the digits it emitted catches that, and on real crops it removes **200 of 200**
label crops while keeping 96.7% of values.

**Grammar cost does not separate labels from values**, contrary to what a design
pass reported. Measured on this grammar: value cost has p50 0.00, p90 1.47 and a
maximum of 14.38, while label cost has a minimum of 6.14. The bands overlap, so
cost is recorded as a legibility number and is never used as a gate on its own.

## The verdicts

* `UNANIMOUS` — the nine one-pixel offsets all read the same value, and the
  digits survived. The cell stands.
* `SPLIT` — the offsets disagree. The cell is demoted to review, with every
  reading recorded so a person sees "this is 15 or 16" rather than "look again".
* `DIGITS_LOST` — the constraint dropped a digit the model saw. Demoted.
* `PROPOSAL` — a cell the resolver refused for value shape that now decodes
  cleanly. **Recorded only.** It is never promoted to a fact by this pass or any
  other without the golden corpus, because the independent confirmer agrees with
  these readings far less often than with the pipeline's existing contents.

Nothing here picks between competing readings. Of the unstable cells where the
independent engine had an opinion, none endorsed a minority reading, so choosing
the majority would be a model making a final finding.

Needs the `ocr` extra. Output is PHI and lands in gitignored facts.sqlite.
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

from kidneymatch.ocr.crops import RAW, prepare_crop  # noqa: E402
from kidneymatch.ocr.ctc import (  # noqa: E402
    GRAMMAR_VERSION,
    build_value_grammar,
    decode,
    digits_preserved,
    greedy,
)
from kidneymatch.ocr.geometry import PageFrame  # noqa: E402
from kidneymatch.ocr.glyphs import parse_allele_value  # noqa: E402

DECODER_VERSION = f"ctc-viterbi/v1+crnn_mobilenet_v3_small+{GRAMMAR_VERSION}"

LOCI = ("A", "B", "C", "DRB1", "DQA1", "DQB1", "DPA1", "DPB1")

# The nine one-pixel neighbours. A reading that survives all nine is stable
# against the arbitrariness of where the detector drew the box.
OFFSETS = tuple((dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1))

# A legibility floor, not a label/value discriminator: the two cost bands
# overlap on real crops, so this only catches a crop nothing could read.
MAX_GRAMMAR_COST = 25.0

SCHEMA = """
CREATE TABLE IF NOT EXISTS decode (
    sha256             TEXT NOT NULL,
    field              TEXT NOT NULL,
    extraction_version TEXT NOT NULL,
    decoder_version    TEXT NOT NULL,
    verdict            TEXT NOT NULL,
    reading            TEXT,
    jitter_readings    TEXT,
    grammar_cost       REAL,
    created_utc        TEXT NOT NULL,
    PRIMARY KEY (sha256, field, extraction_version, decoder_version)
);
"""


def ensure_stability_column(con: sqlite3.Connection) -> None:
    """`fact.stability` defaults to NOT_CHECKED, and that is not acceptable.

    A fact this pass has not examined must never read as one it passed. Anything
    that publishes to Gold requires `UNANIMOUS`; `NOT_CHECKED` and `SPLIT` both
    fail that test, so re-running extraction cannot silently launder a fact.
    """
    columns = {row[1] for row in con.execute("PRAGMA table_info(fact)")}
    if "stability" not in columns:
        con.execute("ALTER TABLE fact ADD COLUMN stability TEXT DEFAULT 'NOT_CHECKED'")
        con.execute("UPDATE fact SET stability='NOT_CHECKED' WHERE stability IS NULL")
        con.commit()


def crop(image, box: list[float], dx: int, dy: int, frame: PageFrame | None = None):
    """The stored box, cut by `ocr.crops`.

    The `RAW` profile is byte for byte what this pass always cut (pinned by
    `tests/unit/test_crops.py` against the old arithmetic). With a frame — only
    on a page the extraction levelled, only under `--frame` — the same box is
    cut upright through the page rotation instead of as an axis-aligned slice.
    """
    result = prepare_crop(image, box, frame=frame, profile=RAW, dx=dx, dy=dy)
    return result.pixels if result is not None else image[0:0, 0:0]


def run(
    facts_db: Path,
    export: Path,
    limit: int | None,
    batch: int,
    jitter: bool,
    use_frame: bool = False,
    only_levelled: bool = False,
) -> int:
    import numpy as np
    from onnxtr.models import recognition_predictor
    from onnxtr.utils import VOCABS
    from PIL import Image

    vocabulary = list(VOCABS["french"])
    blank = len(vocabulary)
    grammar = build_value_grammar(vocabulary, blank, require_prefix=False)
    recognizer = recognition_predictor("crnn_mobilenet_v3_small", batch_size=64)

    # Upright crops on levelled pages change what the recognizer sees, so
    # their verdicts are keyed apart from the axis-aligned ones.
    version = DECODER_VERSION + ("+frame" if use_frame else "")

    con = sqlite3.connect(facts_db)
    con.executescript(SCHEMA)
    ensure_stability_column(con)

    done = {
        (sha, field)
        for sha, field in con.execute(
            "SELECT sha256, field FROM decode WHERE decoder_version=?", (version,)
        )
    }
    placeholders = ",".join("?" * len(LOCI))
    select = (
        "SELECT f.sha256, f.field, f.status, f.value, f.value_boxes, d.rel_path, "
        "{frame_columns} FROM fact f JOIN document d ON d.sha256 = f.sha256 "
        f"WHERE f.field IN ({placeholders}) AND f.value_boxes IS NOT NULL "
        "AND (f.status='RESOLVED' OR f.reason LIKE '%does not parse%') "
        "ORDER BY f.sha256, f.field"
    )
    try:
        # The frame the extraction levelled this page in (`extract_facts.py`).
        rows = con.execute(select.format(frame_columns="d.frame, d.tilt_deg"), LOCI).fetchall()
    except sqlite3.OperationalError:
        # A facts database from before the frame existed: every page identity.
        rows = con.execute(select.format(frame_columns="NULL, NULL"), LOCI).fetchall()
    work = [row for row in rows if (row[0], row[1]) not in done]
    if only_levelled:
        # The ablation: only the pages the extraction levelled, where an
        # upright crop differs from the stored one. Everywhere else the two
        # crops are the same pixels and the verdicts would only be copies.
        work = [row for row in work if row[6] == "ROTATE" and row[7]]
    if limit:
        work = work[:limit]
    offsets = OFFSETS if jitter else ((0, 0),)
    print(f"cells to decode: {len(work):,}  (already done {len(done):,})", flush=True)
    print(f"offsets per cell: {len(offsets)}", flush=True)
    if not work:
        print("nothing to do")
        return 0

    started = time.perf_counter()
    tally: Counter[str] = Counter()
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())

    for start in range(0, len(work), batch):
        chunk = work[start : start + batch]
        crops: list = []
        index: list[tuple] = []
        cache: dict[str, object] = {}
        for sha, field, status, value, value_boxes, rel_path, doc_frame, tilt in chunk:
            boxes = json.loads(value_boxes)
            if not boxes:
                continue
            if rel_path not in cache:
                try:
                    cache[rel_path] = np.asarray(Image.open(export / rel_path).convert("RGB"))
                except OSError:
                    cache[rel_path] = None
            image = cache[rel_path]
            if image is None:
                continue
            frame = None
            if use_frame and doc_frame == "ROTATE" and tilt:
                frame = PageFrame(float(tilt), int(image.shape[1]), int(image.shape[0]))
            # EVERY value box, not just the first. A heterozygous cell holds two,
            # and checking only one leaves the second allele unexamined while the
            # cell is reported stable.
            for position, box in enumerate(boxes):
                for dx, dy in offsets:
                    piece = crop(image, box, dx, dy, frame)
                    if piece.size and piece.shape[0] > 3 and piece.shape[1] > 3:
                        crops.append(piece)
                        index.append((sha, field, status, value, position, dx, dy))

        if not crops:
            continue
        logits = np.concatenate([recognizer.model.run(b) for b in recognizer.pre_processor(crops)])

        # Group by cell, then by which value box within the cell.
        readings: dict[tuple[str, str], dict[int, list]] = {}
        meta: dict[tuple[str, str], tuple[str, str]] = {}
        for (sha, field, status, value, position, dx, dy), frame in zip(index, logits, strict=True):
            result = decode(frame, grammar)
            model_said = greedy(frame, vocabulary, blank)
            parsed = parse_allele_value(result.text)
            meta[(sha, field)] = (status, value)
            readings.setdefault((sha, field), {}).setdefault(position, []).append(
                (result, model_said, parsed, dx == 0 and dy == 0)
            )

        rows: list[tuple] = []
        demote: list[tuple] = []
        for (sha, field), boxes_seen in readings.items():
            status, value = meta[(sha, field)]
            verdict = "UNANIMOUS" if status == "RESOLVED" else "PROPOSAL"
            cost = 0.0
            centre_text: list[str] = []
            votes: Counter[str] = Counter()

            # A cell is only as stable as its least stable box.
            for position in sorted(boxes_seen):
                seen = boxes_seen[position]
                centre = next((s for s in seen if s[3]), seen[0])
                cost = max(cost, max(s[0].grammar_cost for s in seen))
                centre_text.append(centre[0].text)
                distinct = {(s[2].text() if s[2] else None) for s in seen}
                votes.update(f"{position}:{s[2].text() if s[2] else ''}" for s in seen)
                if not digits_preserved(centre[1], centre[0].text):
                    verdict = "DIGITS_LOST"
                elif cost > MAX_GRAMMAR_COST:
                    verdict = "ILLEGIBLE"
                elif len(distinct) > 1 or None in distinct:
                    verdict = "SPLIT"

            tally[verdict] += 1
            rows.append(
                (
                    sha,
                    field,
                    "facts/v1",
                    version,
                    verdict,
                    " ".join(centre_text),
                    json.dumps(dict(votes)),
                    round(cost, 3),
                    now,
                )
            )
            if status == "RESOLVED":
                demote.append(("UNANIMOUS" if verdict == "UNANIMOUS" else verdict, sha, field))

        con.executemany("INSERT OR REPLACE INTO decode VALUES (?,?,?,?,?,?,?,?,?)", rows)
        con.executemany(
            "UPDATE fact SET stability=? WHERE sha256=? AND field=? "
            "AND extraction_version='facts/v1'",
            demote,
        )
        con.commit()

        seen_count = min(start + batch, len(work))
        elapsed = time.perf_counter() - started
        print(
            f"  {seen_count:>7,}/{len(work):,}  {seen_count / elapsed:5.1f} cell/s  "
            f"eta {(len(work) - seen_count) / max(seen_count / elapsed, 1e-9) / 60:5.1f} min",
            flush=True,
        )

    con.close()
    total = sum(tally.values())
    print(f"\ncells decoded: {total:,}")
    for verdict, count in tally.most_common():
        print(f"  {verdict:<14}{count:>8,}  ({count / max(total, 1):6.1%})")
    print(
        "\nSPLIT, DIGITS_LOST and ILLEGIBLE cells were accepted silently before this "
        "pass. PROPOSAL cells are recorded only: nothing here promotes one to a fact."
    )
    print("None of this is an accuracy. Only the golden corpus can produce one (HA-007).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--export", type=Path, default=ROOT / "data/raw/ChatExport_2026-08-31")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument(
        "--no-jitter",
        action="store_true",
        help="decode the stored crop only; without the nine offsets there is no stability signal",
    )
    parser.add_argument(
        "--only-levelled",
        action="store_true",
        help="with --frame: decode only the cells of pages the extraction levelled",
    )
    parser.add_argument(
        "--frame",
        action="store_true",
        help="cut upright crops on pages the extraction levelled (document.frame = ROTATE); "
        "verdicts are keyed under a '+frame' decoder version",
    )
    args = parser.parse_args()
    if not args.facts.exists():
        print(f"missing {args.facts}; run scripts/extract_facts.py first")
        return 2
    return run(
        args.facts,
        args.export,
        args.limit,
        args.batch_size,
        not args.no_jitter,
        args.frame,
        args.only_levelled,
    )


if __name__ == "__main__":
    raise SystemExit(main())
