#!/usr/bin/env python3
"""Choose the documents a person should read, and pack them for the review page.

The golden protocol (ADR 0009) labels cells blind. This pack is the other
instrument: a person sees the whole report, every cell's crop, and what each
engine read, and either approves or corrects. It is faster and it anchors the
reader on the suggestions, so the output is recorded as APPROVED / EDITED /
ADDED per cell and is scored with `scripts/golden_score.py` like any labels.

## How the documents are chosen

A random sample would be almost all easy cells. The point is to find where the
pipeline is wrong, so documents are drawn from strata defined by the failure
signals the pipeline already emits, with quotas that over-represent the rare
ones, plus a clean-control stratum that measures how often "every signal
agrees" is still wrong. A document is assigned to its RAREST stratum, counted
on the corpus being packed; every tag it carries is kept on the record.

Rarest as MEASURED, not as written: the assignment used to follow the order of
`STRATA`, and that silently emptied the two newest strata, because `odd_box`
holds 22 documents corpus-wide and sits below `repaired_glyph`, which holds
11,179. Every odd box was pooled as a repaired glyph and the stratum the
reviewer had asked for drew nothing.

## What the pack contains (PHI: lands under the gitignored `data/review/`)

    <out>/index.html      the review page (a copy of tools/hla_review.html)
    <out>/pack.js         window.PACK = {...}  (the page loads this, no server)
    <out>/pack.json       the same data
    <out>/pipeline.json   the pipeline's readings in golden_score's hidden format
    <out>/images/<id>.jpg the original photo
    <out>/crops/<id>_<locus>.png  one crop per cell that had a box

Cell ids are `<sha256[:16]>:<LOCUS>`, the golden corpus convention.

## The messages posted with the photo

The caption often says what the report does not: whether the person is a donor
or a recipient, and their blood group. So each document record also carries
the Telegram messages that posted the image (`document_message`) and the text
sitting on their bundle siblings (`bundle_message`), read from the source
database. Sender names never enter the pack: the page needs only "same poster
or a different one", so a sender is an 8-character hash (HA-005).

`--augment-messages` adds these to a pack already being labelled, in place;
labels are keyed by cell id, so nothing the reviewer has done moves.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import shutil
import sqlite3
import statistics
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kidneymatch.ocr.lattice import load_rulings as load_stored_rulings  # noqa: E402
from kidneymatch.ocr.rows import row_slope as measure_row_slope  # noqa: E402
from kidneymatch.ocr.rulings import GEOMETRY_VERSION  # noqa: E402

PACK_SCHEMA = "hla-review-pack/v1"
HLA_LOCI = ("A", "B", "C", "DRB1", "DQA1", "DQB1", "DPA1", "DPB1")
DRBX_LOCI = ("DRB3", "DRB4", "DRB5")
CELL_FIELDS = HLA_LOCI + DRBX_LOCI
DOC_FIELDS = ("ROLE", "ABO", "RH")

# (tag, weight, what it means). Order = priority when a document carries
# several tags. Weights are relative quotas; `--n` scales them.
STRATA: tuple[tuple[str, int, str], ...] = (
    # FIRST, because they assert a value NO PERSON HAS EVER CHECKED. Each is a
    # pass added after the first labelling round, and each is a way the pipeline
    # could now be confidently wrong, which is the worst thing it can be. A
    # document is pooled by its FIRST matching tag, so putting them here is what
    # aims a second round at them.
    #
    # The strata BELOW keep the order they had in the first round. That order is
    # load-bearing: a document usually carries several tags, and moving one
    # above another silently empties the lower pool.
    (
        "template_band",
        22,
        "the label was unreadable and the form's template placed it where the page "
        "prints no ruling; the band came from the label's own height",
    ),
    (
        "second_reading",
        18,
        "our own recognizer could not read the cell, and PP-OCRv6 re-reading the same "
        "boxes settled it",
    ),
    (
        "whole_page",
        18,
        "our detector drew no usable box; the value came from a second detector "
        "reading the whole page",
    ),
    (
        "two_engine_reread",
        18,
        "the resolver refused the reading and two independent engines then agreed on "
        "a different one",
    ),
    (
        "drbx_reread",
        16,
        "a DRB3/4/5 gene rested on the S-for-5 repair and a second engine re-read the "
        "printed gene box",
    ),
    (
        "sloped_row",
        14,
        "the page's rulings slope enough that the row test follows them; the binding "
        "depends on that slope being right",
    ),
    ("consistency_flag", 10, "DRB1 and the DRB3/4/5 row contradict each other"),
    ("low_res", 5, "quality band LOW"),
    ("digits_lost", 15, "the constrained decode dropped a digit the recognizer saw"),
    ("proposal", 10, "the resolver refused the cell for shape; the decode reads a clean allele"),
    ("review_refused", 15, "boxes sat on the row but the resolver refused the cell"),
    ("unread_second", 10, "a second allele the pipeline could not read"),
    ("decode_split", 20, "the reading changes under one-pixel jitter"),
    ("confirmer_contradicted", 20, "an independent reader read different digits"),
    ("repaired_glyph", 15, "the accepted value went through glyph repair"),
    ("promoted", 10, "the decode's proposal became a fact because PP-OCRv5 read the same"),
    ("ink_certified", 10, "a DRB3/4/5 gene called ABSENT because its slot measured as paper"),
    (
        "tilted",
        10,
        "the rulings measured the page tilted 1.5 deg or more and the extraction levelled it",
    ),
    ("comparison_sheet", 5, "donor and recipient on one sheet"),
    ("mid_res", 10, "quality band MID"),
    ("default_rule", 10, "no layout family; the generic rule bound the values"),
    (
        "zero_fact_no_anchor",
        10,
        "no locus label anchored anywhere; measured, most of these are not reports",
    ),
    ("zero_fact_refused", 10, "labels anchored but every cell refused; nothing extracted"),
    (
        "bare_role",
        14,
        "the role came from a role word the form prints with no field label beside it "
        "(`FORM_FIELD_BARE`); 2,390 documents, and on the 50 labelled roles it is right "
        "5 times and wrong once — this stratum is what settles the rate",
    ),
    (
        "anchor_row",
        18,
        "the label was read but its cell held no box, and the value was taken from the anchor's "
        "own row by its printed prefix; 458 cells corpus-wide and NONE in the 561 existing "
        "labels, so this stratum is the only thing that can measure the rule",
    ),
    (
        "odd_box",
        16,
        "one allele's box is not the size of the others on its page; measured on 561 "
        "labels, such a cell is wrong 25% of the time against 5% for an ordinary box",
    ),
    (
        "blank_paper",
        6,
        "several printed cells are empty and the ink measure calls them paper; whether "
        "that means the laboratory did not test them is HA-012, and only a person can say",
    ),
    ("clean_control", 20, "every signal agrees; measures how often 'clean' is still wrong"),
)
# Ties in rarity fall back to the order STRATA is written in, so a pack stays
# reproducible for a seed.
STRATA_ORDER = {name: i for i, (name, _, _) in enumerate(STRATA)}
FLAGGED_CONSISTENCY = {"EXPECTED_GENE_ABSENT", "FORBIDDEN_GENE_PRESENT"}
# Nearly every report leaves SOME printed cell empty, so one is no signal at
# all. Three is a form the laboratory filled in only partly, which is the
# case HA-012 has to decide.
MIN_BLANK_CELLS = 3
# A page needs this many bound allele boxes before their median means anything,
# and a box this far from it is not the size of its neighbours.
ODD_BOX_MIN = 3
ODD_BOX_TALL = 1.6
ODD_BOX_SHORT = 0.6
# Padding around a cell crop, as a fraction of the page.
PAD_X, PAD_Y = 0.012, 0.008
MIN_CROP_HEIGHT = 44  # px; smaller crops are upscaled for the eye
# The messages shown with a document: how many, and how much of each.
#
# The reviewer asked for all of them: "a person can send the image multiple time
# each with different text so I want you to show all those texts so we extract
# the maximum information out of it." Measured over the archive, a document has
# a median of 1 posting and a mean of 4.7, but 2,406 of 23,565 carry more than
# eight and one carries 466. Eight truncated a tenth of the corpus, and the
# truncated part is exactly where a repost adds the blood group the form never
# printed. Sixty covers 97.6% of documents whole; the page still says "n of m"
# when it does not, so a reader can see that something was cut.
MAX_MESSAGES = 60
MAX_MESSAGE_CHARS = 1500
SENDER_HASH_SALT = "km-sender|"
# Telegram's title attribute: "31.08.2026 12:34:56 UTC+03:30". Sorted as a
# string that puts the 1st of every month before the 2nd of any other.
_RAW_TIME = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})[ T](\d{2}:\d{2}(?::\d{2})?)")


@dataclass(slots=True)
class Cell:
    locus: str
    status: str
    value: str | None
    raw: str | None
    repaired: bool
    second_allele: str | None
    reason: str | None
    rule_id: str | None
    stability: str | None
    source: str | None
    anchor_box: list[float] | None
    value_boxes: list[list[float]]
    confirmations: dict[str, dict[str, str | None]] = field(default_factory=dict)
    decode: dict[str, object] | None = None


@dataclass(slots=True)
class Doc:
    sha256: str
    rel_path: str
    quality_band: str | None
    family: str | None
    comparison_sheet: bool
    consistency: str | None
    consistency_reason: str | None
    cells: dict[str, Cell] = field(default_factory=dict)
    role: dict[str, str | None] = field(default_factory=dict)
    abo: dict[str, str | None] = field(default_factory=dict)
    rh: dict[str, str | None] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    # The frame the extraction ran the row rules in (`extract_facts.py`):
    # "ROTATE" with the levelling angle, or "identity". None for a facts
    # database from before the geometry pass existed.
    tilt_deg: float | None = None
    frame: str | None = None
    # Printed cells this page leaves empty that the ink measure calls paper
    # (`cell_ink_pass.py`). Whether an empty printed cell means the laboratory
    # did not test the locus is HA-012, a per-laboratory decision no measure
    # can make, and these are the cells a person has to look at to make it.
    blank_cells: int = 0
    # How far this page's printed rows fall per unit of width, from its own
    # rulings (`ocr/rows.py`). Non-zero means the row test followed the slope.
    row_slope: float = 0.0

    @property
    def short(self) -> str:
        return self.sha256[:16]


def _loads(text: str | None) -> Any:
    return json.loads(text) if text else None


def _boxes(text: str | None) -> list[list[float]]:
    raw = _loads(text)
    if not raw:
        return []
    return [raw] if isinstance(raw[0], (int, float)) else list(raw)


def attach_signals(docs: dict[str, Doc], con: sqlite3.Connection, geometry: Path | None) -> None:
    """The two signals a stratum needs that the `fact` table does not carry.

    How many printed cells a page leaves empty that measured as paper, and how
    far its own rulings slope. Both are the subject of a stratum, and both come
    from passes that write no fact, so nothing in `fact` records them.
    """
    if con.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='cell_ink'"
    ).fetchone()[0]:
        # `decision`, not `verdict`: asking for the wrong column here once cost
        # the whole `blank_paper` stratum, because a blanket `except
        # OperationalError` reported it as an absent pass rather than as the bug
        # it was. Presence is checked instead, so a real query error is heard.
        for sha, blanks in con.execute(
            "SELECT sha256, COUNT(*) FROM cell_ink WHERE decision='BLANK' GROUP BY sha256"
        ):
            if sha in docs:
                docs[sha].blank_cells = int(blanks)
    if geometry is None or not geometry.exists():
        return
    stored = load_stored_rulings(geometry, GEOMETRY_VERSION)
    for sha, doc in docs.items():
        found = stored.get(sha)
        if found is None:
            continue
        width, height, horizontal, _ = found
        try:
            segments = json.loads(horizontal or "[]")
        except ValueError:
            continue
        doc.row_slope = measure_row_slope(segments, width, height) or 0.0


def load_documents(con: sqlite3.Connection) -> dict[str, Doc]:
    docs: dict[str, Doc] = {}
    columns = {row[1] for row in con.execute("PRAGMA table_info(document)")}
    framed = {"tilt_deg", "frame"} <= columns
    frame_columns = ", tilt_deg, frame" if framed else ", NULL, NULL"
    for row in con.execute(
        "SELECT sha256, rel_path, quality_band, family, comparison_sheet, consistency, "
        f"consistency_reason{frame_columns} FROM document"
    ):
        docs[row[0]] = Doc(
            row[0],
            row[1],
            row[2],
            row[3],
            bool(row[4]),
            row[5],
            row[6],
            tilt_deg=row[7],
            frame=row[8],
        )
    for (
        sha,
        fld,
        status,
        value,
        raw,
        repaired,
        second,
        reason,
        rule,
        stab,
        abox,
        vboxes,
        src,
    ) in con.execute(
        "SELECT sha256, field, status, value, raw, repaired, second_allele, reason, rule_id, "
        "stability, anchor_box, value_boxes, source FROM fact"
    ):
        doc = docs.get(sha)
        if doc is None:
            continue
        if fld in CELL_FIELDS:
            doc.cells[fld] = Cell(
                fld,
                status,
                value,
                raw,
                bool(int(repaired or 0)),
                second,
                reason,
                rule,
                stab,
                src,
                _loads(abox),
                _boxes(vboxes),
            )
        elif fld == "ROLE":
            doc.role = {"status": status, "value": value, "source": src}
        elif fld == "ABO":
            doc.abo = {"status": status, "value": value, "source": src, "reason": reason}
        elif fld == "RH":
            doc.rh = {"status": status, "value": value, "source": src}
    # One row PER CONFIRMER. Keying them all onto one field would show the
    # reader whichever engine the database happened to return last, and there
    # are two of them now.
    for sha, fld, confirmer, verdict, reading in con.execute(
        "SELECT sha256, field, confirmer_version, verdict, reading FROM confirmation"
    ):
        cell = docs[sha].cells.get(fld) if sha in docs else None
        if cell is not None:
            name = str(confirmer).split("/")[0]
            cell.confirmations[name] = {"verdict": verdict, "reading": reading}
    for sha, fld, verdict, reading, jitter in con.execute(
        "SELECT sha256, field, verdict, reading, jitter_readings FROM decode "
        "WHERE decoder_version LIKE 'ctc-viterbi%'"
    ):
        cell = docs[sha].cells.get(fld) if sha in docs else None
        if cell is not None:
            votes = _loads(jitter) or {}
            cell.decode = {"verdict": verdict, "reading": reading, "votes": votes}
    return docs


def odd_value_box(resolved: list[Cell]) -> bool:
    """Is one bound allele box not the size of the others on this page?

    The reviewer's signal: "most of the time all of them should have the same
    size... if we see one or two of them have unusually short length or very
    large width we may want to assume that the shape is different." A laboratory
    prints its values in one font, so a box that disagrees is usually the
    detector's mistake. Measured on 561 labels, a cell whose box is unlike its
    page's others is wrong 25% of the time against 5% for an ordinary one.

    Compared against the page's OWN bound boxes rather than against every box on
    it, which is what the reviewer described and needs nothing the pack does not
    already carry.
    """
    heights = [
        box[3] - box[1] for cell in resolved for box in (cell.value_boxes or []) if len(box) >= 4
    ]
    if len(heights) < ODD_BOX_MIN:
        return False
    middle = statistics.median(heights)
    if middle <= 0:
        return False
    return any(h / middle > ODD_BOX_TALL or h / middle < ODD_BOX_SHORT for h in heights)


def tag_document(doc: Doc, export: Path) -> list[str]:
    """Every stratum this document belongs to, in `STRATA` order."""
    hla = [c for c in doc.cells.values() if c.locus in HLA_LOCI]
    resolved = [c for c in hla if c.status == "RESOLVED"]
    verdicts = {c.locus: (c.decode or {}).get("verdict") for c in hla}
    # A cell is "contradicted" when ANY independent reader disputes it; a
    # stratum keyed on one engine would go quiet the moment that engine did.
    disputed = {
        c.locus
        for c in hla
        if any(v.get("verdict") == "CONTRADICTED" for v in c.confirmations.values())
    }
    confirmed = {
        c.locus
        for c in hla
        if c.confirmations
        and all(v.get("verdict") == "CONFIRMED" for v in c.confirmations.values())
    }
    tags: set[str] = set()
    if doc.consistency in FLAGGED_CONSISTENCY:
        tags.add("consistency_flag")
    if doc.quality_band == "LOW":
        tags.add("low_res")
    if doc.quality_band == "MID":
        tags.add("mid_res")
    if any(v == "DIGITS_LOST" for v in verdicts.values()):
        tags.add("digits_lost")
    if any(v == "SPLIT" for v in verdicts.values()):
        tags.add("decode_split")
    if any(v == "PROPOSAL" for v in verdicts.values()):
        tags.add("proposal")
    if any(c.status == "REVIEW_REQUIRED" and c.value_boxes for c in hla):
        tags.add("review_refused")
    if any(c.second_allele == "UNREAD" for c in resolved):
        tags.add("unread_second")
    if disputed:
        tags.add("confirmer_contradicted")
    if any(c.repaired for c in resolved):
        tags.add("repaired_glyph")
    if any(c.source == "decode+ppocrv5" for c in resolved):
        # Two engines agreed on a value the primary text did not parse; the
        # labels are the only thing that can say how often both were wrong.
        tags.add("promoted")
    if any(c.source == "ink-certified" for c in doc.cells.values() if c.locus in DRBX_LOCI):
        tags.add("ink_certified")
    if doc.frame == "ROTATE":
        # The extraction levelled this page before binding its rows; whether
        # that helped or hurt is exactly what a labelled sample must say.
        tags.add("tilted")
    if doc.comparison_sheet:
        tags.add("comparison_sheet")
    if doc.family is None and resolved:
        tags.add("default_rule")
    if not resolved:
        anchored = any(c.status == "REVIEW_REQUIRED" for c in hla)
        tags.add("zero_fact_refused" if anchored else "zero_fact_no_anchor")
    if any((c.reason or "").find("and its own label height") >= 0 for c in resolved):
        tags.add("template_band")
    if any(c.source == "rerecognised+ppocrv6" for c in resolved):
        tags.add("second_reading")
    if any(c.source == "page-ocr+wholepage" for c in resolved):
        tags.add("whole_page")
    if any(c.source == "reread-refused+two-engine-agreement" for c in resolved):
        tags.add("two_engine_reread")
    if any(c.source == "drbx-reread+ppocrv6" for c in doc.cells.values() if c.locus in DRBX_LOCI):
        tags.add("drbx_reread")
    if (doc.role or {}).get("source") == "FORM_FIELD_BARE":
        tags.add("bare_role")
    if any(c.source == "anchor-row-prefix" for c in resolved):
        tags.add("anchor_row")
    if odd_value_box(resolved):
        tags.add("odd_box")
    if doc.blank_cells >= MIN_BLANK_CELLS:
        tags.add("blank_paper")
    if doc.row_slope:
        tags.add("sloped_row")
    if (
        not tags
        and len(resolved) >= 3
        and all(c.stability == "UNANIMOUS" for c in resolved)
        and not disputed
        and any(c.locus in confirmed for c in resolved)
    ):
        tags.add("clean_control")
    return [t for t, _, _ in STRATA if t in tags]


def pinned_shas(sources: list[Path]) -> set[str]:
    """The 16-character document ids a labeller has already answered cells on.

    A pack's sample is stratified by what the pipeline currently says about a
    document, so a refresh moves documents between strata and the round-robin
    picks a different 150. Measured after the 2026-09-05 refresh: 11 of 220
    existing labels still landed on a chosen document. Labels are the scarcest
    thing this project has, so any document a person has already answered is
    pinned into the next pack and the sample fills up around it.

    Each source is a `golden-labels/v1` export, whose cell ids are
    `<sha256[:16]>:<locus>`.
    """
    shas: set[str] = set()
    for source in sources:
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for key in ("cells", "labels"):
            for cell_id in payload.get(key) or {}:
                head = str(cell_id).rsplit(":", 1)[0]
                if len(head) == 16:
                    shas.add(head)
    return shas


def choose(
    docs: dict[str, Doc], n: int, seed: int, export: Path, pin: set[str] | None = None
) -> list[Doc]:
    """Stratified, deterministic, spread across layout families inside a stratum."""
    rng = random.Random(seed)
    present: list[Doc] = []
    for doc in docs.values():
        doc.tags = tag_document(doc, export)
        if doc.tags and (export / doc.rel_path).exists():
            present.append(doc)
    # A document belongs to its RAREST stratum, measured on this corpus rather
    # than assumed from the order STRATA happens to be written in. It was
    # written order before, and that silently emptied the two newest strata:
    # `odd_box` holds 22 documents corpus-wide and sits below `repaired_glyph`,
    # which holds 11,179, so every odd box was claimed as a repaired glyph and
    # the reviewer's own signal drew nothing. Rarity is the property that
    # matters — a document that is one of 22 witnesses to a signal is worth far
    # more there than as one of 11,179.
    frequency = Counter(tag for doc in present for tag in doc.tags)
    pools: dict[str, list[Doc]] = defaultdict(list)
    for doc in present:
        doc.tags = sorted(doc.tags, key=lambda tag: (frequency[tag], STRATA_ORDER[tag]))
        pools[doc.tags[0]].append(doc)
    # Documents someone has already labelled come first and are never dropped:
    # their answers are the only ground truth the project has.
    held = [doc for doc in docs.values() if doc.short in (pin or set())]
    chosen: list[Doc] = list(held)
    for doc in held:
        for tag in list(pools):
            pools[tag] = [d for d in pools[tag] if d.sha256 != doc.sha256]

    by_family: dict[str, dict[str | None, list[Doc]]] = {}
    for tag, _, _ in STRATA:
        grouped: dict[str | None, list[Doc]] = defaultdict(list)
        for doc in pools[tag]:
            grouped[doc.family].append(doc)
        for group in grouped.values():
            rng.shuffle(group)
        by_family[tag] = grouped

    def take(tag: str, want: int) -> None:
        # Round-robin across layout families inside one stratum, so a stratum
        # held by one printed form does not fill with that form alone.
        grouped = by_family[tag]
        families = sorted(grouped, key=lambda f: (f is None, str(f)))
        taken = 0
        while taken < want and len(chosen) < n and any(grouped[f] for f in families):
            for family in families:
                if grouped[family] and taken < want and len(chosen) < n:
                    chosen.append(grouped[family].pop())
                    taken += 1

    # ONE document from every stratum that has any, before a single stratum
    # takes a second. A pack is a diagnostic instrument, and a signal with no
    # document in it is a signal nobody can check — which is what happened
    # when six strata were added and the weights alone starved the smallest.
    for tag in sorted(pools, key=lambda t: (len(pools[t]), STRATA_ORDER[t])):
        take(tag, 1)
    # Then the weights, over whatever room is left.
    total_weight = sum(w for _, w, _ in STRATA)
    room = max(0, n - len(chosen))
    for tag, weight, _ in STRATA:
        take(tag, max(0, round(room * weight / total_weight) - 1))
    # Top up from the biggest pools if rounding or empty strata left room.
    seen = {d.sha256 for d in chosen}
    while len(chosen) < n:
        spare = [d for t, _, _ in STRATA for d in pools[t] if d.sha256 not in seen]
        if not spare:
            break
        pick = rng.choice(spare)
        chosen.append(pick)
        seen.add(pick.sha256)
    return chosen[:n]


def cell_crop_box(cell: Cell, width: int, height: int) -> tuple[int, int, int, int] | None:
    boxes = list(cell.value_boxes)
    if cell.anchor_box:
        boxes.append(cell.anchor_box)
    if not boxes:
        return None
    x0 = min(b[0] for b in boxes) - PAD_X
    y0 = min(b[1] for b in boxes) - PAD_Y
    x1 = max(b[2] for b in boxes) + PAD_X
    y1 = max(b[3] for b in boxes) + PAD_Y
    if not cell.value_boxes and cell.anchor_box:
        # The resolver saw the label but bound nothing: show the whole row to
        # the right of it so the reader can see what was there.
        x1 = min(1.0, cell.anchor_box[2] + 0.45)
    return (
        max(0, int(x0 * width)),
        max(0, int(y0 * height)),
        min(width, int(x1 * width)),
        min(height, int(y1 * height)),
    )


def _time_key(raw: str | None) -> str:
    """Chronological sort key for a raw Telegram timestamp; the raw text otherwise."""
    if not raw:
        return ""
    m = _RAW_TIME.match(raw.strip())
    if not m:
        return raw
    day, month, year, clock = m.groups()
    return f"{year}-{month}-{day} {clock}"


def sender_hash(name: str | None) -> str | None:
    """HA-005: a poster is an 8-character hash, never a display name."""
    if not name:
        return None
    return hashlib.sha256((SENDER_HASH_SALT + name).encode("utf-8")).hexdigest()[:8]


def _clip(text: str | None) -> str:
    text = (text or "").strip()
    if len(text) > MAX_MESSAGE_CHARS:
        return text[: MAX_MESSAGE_CHARS - 1].rstrip() + "…"
    return text


def _chunks(items: list[Any], size: int = 900) -> list[list[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _tables(con: sqlite3.Connection) -> set[str]:
    return {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def load_messages(
    source_db: Path, shas: set[str], totals: dict[str, int] | None = None
) -> dict[str, list[dict[str, object]]]:
    """The messages posted with each document, keyed by sha256.

    Posting messages come first (`on_photo`), then the bundle siblings that
    carry text; each group in time order. A posting message with no text is
    kept only when none of them has any, so the reader sees "no caption"
    rather than nothing. At most `MAX_MESSAGES` per document, each clipped to
    `MAX_MESSAGE_CHARS`. Every document in `shas` gets a key, possibly empty;
    a missing database or a database without the link tables yields all-empty.
    `totals`, when given, receives the count before the cap, per document.
    """
    result: dict[str, list[dict[str, object]]] = {sha: [] for sha in shas}
    if not shas or not source_db.exists():
        return result
    con = sqlite3.connect(f"file:{source_db.as_posix()}?mode=ro", uri=True)
    try:
        tables = _tables(con)
        if not {"document_message", "source_message"} <= tables:
            return result
        # sha -> {(export_id, message_id)} posting it, and the bundles they sit in.
        posting: dict[str, set[tuple[str, int]]] = defaultdict(set)
        bundles: dict[str, set[tuple[str, str]]] = defaultdict(set)
        for chunk in _chunks(sorted(shas)):
            marks = ",".join("?" * len(chunk))
            for sha, export_id, message_id, bundle_id in con.execute(
                "SELECT sha256, export_id, telegram_message_id, bundle_id FROM document_message "
                f"WHERE sha256 IN ({marks})",
                chunk,
            ):
                posting[sha].add((export_id, int(message_id)))
                if bundle_id:
                    bundles[sha].add((export_id, str(bundle_id)))
        siblings: dict[str, set[tuple[str, int]]] = defaultdict(set)
        if "bundle_message" in tables and bundles:
            wanted = sorted({b for group in bundles.values() for b in group})
            members: dict[tuple[str, str], set[int]] = defaultdict(set)
            for chunk in _chunks(wanted, 450):
                clause = " OR ".join("(export_id = ? AND bundle_id = ?)" for _ in chunk)
                params = [v for pair in chunk for v in pair]
                for export_id, bundle_id, message_id in con.execute(
                    "SELECT export_id, bundle_id, telegram_message_id FROM bundle_message "
                    f"WHERE {clause}",
                    params,
                ):
                    members[(export_id, str(bundle_id))].add(int(message_id))
            for sha, group in bundles.items():
                for export_id, bundle_id in group:
                    for message_id in members.get((export_id, bundle_id), ()):
                        if (export_id, message_id) not in posting[sha]:
                            siblings[sha].add((export_id, message_id))
        # One read of every message any document needs.
        keys = sorted({k for group in posting.values() for k in group}) + sorted(
            {k for group in siblings.values() for k in group}
        )
        # (sort key, record): time order first, and the id breaks ties.
        rows: dict[tuple[str, int], tuple[tuple[str, int], dict[str, object]]] = {}
        by_export: dict[str, list[int]] = defaultdict(list)
        for export_id, message_id in keys:
            by_export[export_id].append(message_id)
        for export_id, ids in by_export.items():
            for chunk in _chunks(sorted(set(ids))):
                marks = ",".join("?" * len(chunk))
                for (
                    message_id,
                    sent_at,
                    sender,
                    forwarded_from,
                    is_joined,
                    raw_text,
                ) in con.execute(
                    "SELECT telegram_message_id, sent_at_raw, sender_display_name, "
                    "forwarded_from_display_name, is_joined, raw_text FROM source_message "
                    f"WHERE export_id = ? AND telegram_message_id IN ({marks})",
                    [export_id, *chunk],
                ):
                    key = (export_id, int(message_id))
                    if key in rows:
                        continue
                    record: dict[str, object] = {
                        "message_id": int(message_id),
                        "sent_at": sent_at or None,
                        "text": _clip(raw_text),
                        "forwarded": bool(forwarded_from),
                        "joined": bool(int(is_joined or 0)),
                        "sender": sender_hash(sender),
                    }
                    rows[key] = ((_time_key(sent_at), int(message_id)), record)
    finally:
        con.close()

    def ordered(keys: set[tuple[str, int]], on_photo: bool) -> list[dict[str, object]]:
        # Sorted on the key alone: two exports can share a message id, and
        # Python cannot order the dicts that would then break the tie.
        found = sorted((rows[k] for k in keys if k in rows), key=lambda item: item[0])
        return [{**record, "on_photo": on_photo} for _, record in found]

    for sha in shas:
        posted = ordered(posting.get(sha, set()), True)
        with_text = [m for m in posted if m["text"]]
        kept = with_text if with_text else posted[:1]
        kept += [m for m in ordered(siblings.get(sha, set()), False) if m["text"]]
        # A chat exported twice is two export_ids holding the same messages;
        # the same post must not appear twice or spend the cap on itself.
        seen: set[tuple[int, str]] = set()
        unique = []
        for message in kept:
            key = (int(message["message_id"]), str(message["text"]))
            if key in seen:
                continue
            seen.add(key)
            unique.append(message)
        result[sha] = unique[:MAX_MESSAGES]
        if totals is not None:
            # The page says "8 of 12" rather than passing eight posts off as all.
            totals[sha] = len(unique)
    return result


def load_caption_claims(source_db: Path, shas: set[str]) -> dict[str, dict[str, str | None] | None]:
    """What `read_caption_role` concluded from the posting caption, per sha256.

    None when there is no claim (the common case: refusal is by design), no
    database, or no claim table.
    """
    result: dict[str, dict[str, str | None] | None] = {sha: None for sha in shas}
    if not shas or not source_db.exists():
        return result
    con = sqlite3.connect(f"file:{source_db.as_posix()}?mode=ro", uri=True)
    try:
        if "document_caption_claim" not in _tables(con):
            return result
        for chunk in _chunks(sorted(shas)):
            marks = ",".join("?" * len(chunk))
            for sha, role, tier, reason in con.execute(
                "SELECT sha256, role, tier, reason FROM document_caption_claim "
                f"WHERE sha256 IN ({marks}) ORDER BY sha256, export_id",
                chunk,
            ):
                if result.get(sha) is None:
                    result[sha] = {"role": role, "tier": tier, "reason": reason or None}
    finally:
        con.close()
    return result


def attach_messages(records: list[dict[str, object]], source_db: Path | None) -> dict[str, int]:
    """Set `messages`, `n_messages_total` and `caption_claim` on every record;
    replaces any present. Without a source database the messages are None —
    "not loaded" — never an empty list, which the page would render as "no
    message posted this image", a statement about the archive."""
    shas = {str(r["sha256"]) for r in records}
    loaded = bool(source_db and source_db.exists())
    totals: dict[str, int] = {}
    messages = load_messages(source_db, shas, totals) if loaded else {}
    claims = load_caption_claims(source_db, shas) if loaded else {s: None for s in shas}
    for record in records:
        sha = str(record["sha256"])
        record["messages"] = messages.get(sha, []) if loaded else None
        record["n_messages_total"] = totals.get(sha, 0) if loaded else None
        record["caption_claim"] = claims.get(sha)
    return {
        "with_messages": sum(1 for r in records if r["messages"]),
        "with_caption_claim": sum(1 for r in records if r["caption_claim"]),
    }


def write_pack_files(out: Path, pack: dict[str, object]) -> None:
    """`pack.json` and `pack.js` are the same bytes two ways; the page loads the latter."""
    text = json.dumps(pack, ensure_ascii=False)
    (out / "pack.json").write_text(text, encoding="utf-8")
    (out / "pack.js").write_text("window.PACK = " + text + ";\n", encoding="utf-8")


def pack_document(doc: Doc, export: Path, out: Path) -> tuple[dict[str, object], dict[str, object]]:
    """Copy the image, cut the crops, and return (record, pipeline_cells)."""
    from PIL import Image

    image = Image.open(export / doc.rel_path).convert("RGB")
    width, height = image.size
    image_name = f"images/{doc.short}.jpg"
    shutil.copyfile(export / doc.rel_path, out / image_name)
    cells: list[dict[str, object]] = []
    pipeline: dict[str, object] = {}
    for locus in CELL_FIELDS:
        cell = doc.cells.get(locus)
        if cell is None:
            continue
        cell_id = f"{doc.short}:{locus}"
        crop_name: str | None = None
        box = cell_crop_box(cell, width, height)
        if box and box[2] - box[0] > 3 and box[3] - box[1] > 3:
            piece = image.crop(box)
            if piece.height < MIN_CROP_HEIGHT:
                scale = MIN_CROP_HEIGHT / piece.height
                piece = piece.resize(
                    (int(piece.width * scale), MIN_CROP_HEIGHT), Image.Resampling.LANCZOS
                )
            crop_name = f"crops/{doc.short}_{locus}.png"
            piece.save(out / crop_name)
        suggestions: dict[str, object] = {
            "pipeline": {
                "value": cell.value,
                "raw": cell.raw,
                "repaired": cell.repaired,
                "status": cell.status,
                "reason": cell.reason,
                "rule": cell.rule_id,
                "second_allele": cell.second_allele,
                "stability": cell.stability,
            },
        }
        for name, confirmation in sorted(cell.confirmations.items()):
            suggestions[name] = confirmation
        if cell.decode:
            suggestions["decode"] = cell.decode
        cells.append(
            {
                "cell_id": cell_id,
                "locus": locus,
                "kind": "DRBX" if locus in DRBX_LOCI else "HLA",
                "status": cell.status,
                "value": cell.value,
                "crop": crop_name,
                "anchor_box": cell.anchor_box,
                "value_boxes": cell.value_boxes,
                "suggestions": suggestions,
            }
        )
        pipeline[cell_id] = {
            "status": cell.status,
            "locus": locus,
            "value": cell.value,
            "rule": cell.rule_id,
            # The pipeline's own declaration of whether it read a second
            # allele (KI-015), so `golden_score.py` and `pack_score.py` score
            # a declared partial read the same way.
            "second_allele": cell.second_allele,
        }
    record: dict[str, object] = {
        "id": doc.short,
        "sha256": doc.sha256,
        "image": image_name,
        "width": width,
        "height": height,
        "quality_band": doc.quality_band,
        "family": doc.family,
        "comparison_sheet": doc.comparison_sheet,
        "tilt_deg": doc.tilt_deg,
        "frame": doc.frame,
        "consistency": doc.consistency,
        "consistency_reason": doc.consistency_reason,
        "tags": doc.tags,
        "primary_tag": doc.tags[0] if doc.tags else None,
        "role": doc.role,
        "abo": doc.abo,
        "rh": doc.rh,
        # Filled by `attach_messages` when a source database is at hand.
        "messages": [],
        "caption_claim": None,
        "cells": cells,
    }
    return record, pipeline


def build_pack(
    facts_db: Path,
    export: Path,
    out: Path,
    n: int,
    seed: int,
    page: Path,
    suggestions_dir: Path | None = None,
    source_db: Path | None = None,
    pin: set[str] | None = None,
    drop: set[str] | None = None,
    geometry_db: Path | None = None,
    port: int = 8765,
) -> dict[str, int]:
    con = sqlite3.connect(facts_db)
    docs = load_documents(con)
    attach_signals(docs, con, geometry_db)
    con.close()
    if drop:
        docs = {sha: doc for sha, doc in docs.items() if doc.short not in drop}
    chosen = choose(docs, n, seed, export, pin)
    if len({d.short for d in chosen}) != len(chosen):
        raise ValueError("two chosen documents share a 16-character id prefix")
    out.mkdir(parents=True, exist_ok=True)
    (out / "images").mkdir(exist_ok=True)
    (out / "crops").mkdir(exist_ok=True)
    records: list[dict[str, object]] = []
    pipeline: dict[str, object] = {}
    for doc in chosen:
        record, cells = pack_document(doc, export, out)
        records.append(record)
        pipeline.update(cells)
    attach_messages(records, source_db)
    extra: dict[str, dict[str, str]] = {}
    if suggestions_dir and suggestions_dir.exists():
        for path in sorted(suggestions_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            extra[str(payload.get("engine") or path.stem)] = dict(payload.get("cells", {}))
    strata_counts = Counter(str(r["primary_tag"]) for r in records)
    pack = {
        "schema": PACK_SCHEMA,
        "pack_id": f"{seed}-{n}-{time.strftime('%Y%m%d', time.gmtime())}",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        "strata": [
            {"tag": t, "weight": w, "meaning": m, "n": strata_counts.get(t, 0)}
            for t, w, m in STRATA
        ],
        "n_documents": len(records),
        "n_cells": len(pipeline),
        "engines": sorted(extra),
        "suggestions": extra,
        "documents": records,
    }
    write_pack_files(out, pack)
    (out / "pipeline.json").write_text(
        json.dumps({"schema": "golden-hidden/v1", "cells": pipeline}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    shutil.copyfile(page, out / "index.html")
    write_launcher(out, port)
    return {t: strata_counts.get(t, 0) for t, _, _ in STRATA}


def write_launcher(out: Path, port: int = 8765) -> None:
    """A double-clickable server for the pack.

    Opened straight off the disk, a browser may refuse this page `localStorage`,
    and the page would then forget the labels on reload. It says so when that
    happens, but the better answer is not to depend on it: serving the folder
    over localhost makes storage ordinary, and costs the reader one click.
    """
    windows = [
        "@echo off",
        'cd /d "%~dp0"',
        f'start "" http://localhost:{port}/index.html',
        f"python -m http.server {port} --bind 127.0.0.1",
        "",
    ]
    posix = [
        "#!/bin/sh",
        'cd "$(dirname "$0")"',
        f"python -m http.server {port} --bind 127.0.0.1",
        "",
    ]
    # newline="" or the platform translates these again and cmd.exe gets \r\r\n.
    (out / "serve.cmd").write_text("\r\n".join(windows), encoding="ascii", newline="")
    (out / "serve.sh").write_text("\n".join(posix), encoding="ascii", newline="")


def refresh_page(out: Path, page: Path) -> int:
    """Replace only the page in an existing pack.

    Rebuilding a pack re-cuts thousands of crops, which makes iterating on the
    page itself slow enough that one stops testing it. The pack's data is
    untouched, so a labeller's stored progress survives.
    """
    if not (out / "pack.json").exists():
        print(f"no pack at {out}; build one first")
        return 2
    shutil.copyfile(page, out / "index.html")
    write_launcher(out)
    print(f"page refreshed in {out}; reload the browser (Ctrl+F5)")
    return 0


def augment_messages(out: Path, source_db: Path) -> int:
    """Add the posting messages and caption claim to a pack already in progress.

    Only `pack.json` and `pack.js` are rewritten. The crops, the images,
    `pipeline.json` and the page are not touched, and labels are keyed by
    cell id, so a reviewer's stored progress survives. Running it twice
    replaces the two keys with the same values.
    """
    pack_path = out / "pack.json"
    if not pack_path.exists():
        print(f"no pack at {out}; build one first")
        return 2
    if not source_db.exists():
        print(f"missing {source_db}; run scripts/ingest_export.py and link_documents.py first")
        return 2
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    records = list(pack.get("documents", []))
    counts = attach_messages(records, source_db)
    pack["documents"] = records
    write_pack_files(out, pack)
    print(
        f"augmented {len(records)} documents in {out}: "
        f"{counts['with_messages']} with messages, "
        f"{counts['with_caption_claim']} with a caption claim; reload the browser (Ctrl+F5)"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument(
        "--source",
        type=Path,
        default=ROOT / "data/derived/source.sqlite",
        help="the source database; when present, each document carries its posting messages",
    )
    parser.add_argument("--export", type=Path, default=ROOT / "data/raw/ChatExport_2026-08-31")
    parser.add_argument("--out", type=Path, default=ROOT / "data/review/hla_pack")
    parser.add_argument("--n", type=int, default=150)
    parser.add_argument("--seed", type=int, default=20260902)
    parser.add_argument("--page", type=Path, default=ROOT / "tools/hla_review.html")
    parser.add_argument(
        "--suggestions",
        type=Path,
        default=None,
        help="directory of <engine>.json files {engine, cells:{cell_id: text}} to show as well",
    )
    parser.add_argument(
        "--keep-labelled",
        type=Path,
        nargs="*",
        default=None,
        help="golden-labels exports whose documents must appear in the new pack; "
        "a refresh moves documents between strata and would otherwise orphan the answers",
    )
    parser.add_argument(
        "--geometry",
        type=Path,
        default=ROOT / "data/derived/geometry.sqlite",
        help="page geometry, for the sloped-row stratum; skipped when absent",
    )
    parser.add_argument(
        "--skip-labelled",
        type=Path,
        nargs="*",
        default=None,
        help="golden-labels exports whose documents must be LEFT OUT; a second round "
        "should not spend a reader's time on pages they have already answered",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="the port the launcher serves on; a second pack needs its own, because "
        "the page keeps a reader's answers in the browser's storage for one origin",
    )
    parser.add_argument(
        "--page-only",
        action="store_true",
        help="replace index.html in an existing pack and touch nothing else",
    )
    parser.add_argument(
        "--augment-messages",
        action="store_true",
        help="add the posting messages and caption claim to an existing pack; "
        "rewrites pack.json and pack.js only",
    )
    args = parser.parse_args()
    if args.page_only:
        return refresh_page(args.out, args.page)
    if args.augment_messages:
        return augment_messages(args.out, args.source)
    if not args.facts.exists():
        print(f"missing {args.facts}; run scripts/extract_facts.py first")
        return 2
    pin = pinned_shas(list(args.keep_labelled or []))
    if pin:
        print(f"pinning {len(pin)} already-labelled documents into the sample")
    drop = pinned_shas(list(args.skip_labelled or []))
    if drop:
        print(f"leaving out {len(drop)} documents that have already been answered")
    counts = build_pack(
        args.facts,
        args.export,
        args.out,
        args.n,
        args.seed,
        args.page,
        args.suggestions,
        source_db=args.source,
        pin=pin,
        drop=drop,
        geometry_db=args.geometry,
        port=args.port,
    )
    print(f"packed {sum(counts.values())} documents into {args.out}")
    for tag, count in counts.items():
        print(f"  {tag:<24}{count:>5}")
    print(f"Run serve.cmd in that directory, then label at http://localhost:{args.port} .")
    print("Labels export as golden-labels/v1 and are scored by scripts/golden_score.py.")
    print("Nothing in this directory may be committed: it is the patients' reports.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
