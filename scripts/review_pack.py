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

from kidneymatch.ocr.lattice import Lattice  # noqa: E402
from kidneymatch.ocr.lattice import lattice_for as build_lattice  # noqa: E402
from kidneymatch.ocr.lattice import load_rulings as load_stored_rulings  # noqa: E402
from kidneymatch.ocr.rows import row_slope as measure_row_slope  # noqa: E402
from kidneymatch.ocr.rulings import GEOMETRY_VERSION  # noqa: E402

PACK_SCHEMA = "hla-review-pack/v1"
# Two DRB3/4/5 routes that assert values no person has checked. Both are keyed
# by their RULE id rather than by the `source` string a pass happens to write:
# a rule_id is emitted by `ocr/drbx.py` itself and therefore survives a full
# re-extraction, while a source written by a one-off pass does not, and a
# stratum keyed on a vanishing source silently draws zero.
TOKEN_ANCHORED_RULE = "TOKEN_ANCHORED_DRBX/v1"
# The same route where the page's DRB1 VALUE was never resolved, so it rests on
# G2b (no allele value on the placed row) instead of on DRB1's corroboration.
# Its own group, and its own stratum: nothing has measured it.
TOKEN_ANCHORED_UNRESOLVED_RULE = "TOKEN_ANCHORED_DRBX_UNRESOLVED_DRB1/v1"
WIDENED_HEADER_RULE = "GROUPED_DRBX_WIDENED/v1"
# The `source` on a widened-header cell is `widened-drbx-header:<branch>[+...]`
# — which of the four widenings let the header in. The pack spreads that
# stratum across BRANCHES the way every other stratum is spread across layout
# families, because the four are four different kinds of damage.
WIDENED_HEADER_SOURCE = "widened-drbx-header"
HLA_LOCI = ("A", "B", "C", "DRB1", "DQA1", "DQB1", "DPA1", "DPB1")
DRBX_LOCI = ("DRB3", "DRB4", "DRB5")
CELL_FIELDS = HLA_LOCI + DRBX_LOCI
DOC_FIELDS = ("ROLE", "ABO", "RH")

# (tag, weight, what it means). Order = priority when a document carries
# several tags. Weights are relative quotas; `--n` scales them.
STRATA: tuple[tuple[str, int, str], ...] = (
    # FIRST, because every stratum in this block asserts a value NO PERSON HAS
    # EVER CHECKED. Each comes from a pass added after the first labelling
    # round, and each is a way the pipeline could now be confidently wrong,
    # which is the worst thing it can be. A document is pooled by its FIRST
    # matching tag, so putting them here is what aims a second round at them.
    #
    # The strata BELOW this block keep the order they had in the first round.
    # That order is load-bearing: a document usually carries several tags, and
    # moving one above another silently empties the lower pool.
    #
    # The two blood-group rescue routes are SEPARATE strata, because they rest on
    # different evidence and only one of them is blocked. Pooling them put
    # roughly two centre documents in a 150-document pack, and HA-019 asks for
    # twenty before the group may be promoted. The centre weight is sized for
    # exactly that and is expected to come down once a round has answered it —
    # the arithmetic is written out in HA-019.
    (
        "abo_centre_rescue",
        # The weight only tops this stratum up; `MIN_DRAW` is what guarantees
        # the 20 readings HA-019 blocks promotion on, because a share of the
        # total silently shrinks whenever a stratum lands beside it.
        40,
        "this page rules no row around the blood-group field, so nothing but distance places "
        "the value: its box missed the label's LINE and was admitted by a 0.75 label-height "
        "band above the label's centre, behind six gates. 38 documents on the live store, ZERO "
        "of them ever checked by a person; the pipeline may not rest a match on one until some "
        "have been, which is what this quota is sized to end (21 at the default --n 150)",
    ),
    (
        "abo_band_rescue",
        12,
        "the blood group's box missed its label's LINE and was admitted by the label's own "
        "ruled ROW — the page prints a grid and the value is inside the label's cell. 42 "
        "documents on the live store: 29 published, because two engines boxed the same ink or "
        "the messages name the same letter, and 13 that nothing corroborates, which are here "
        "as REVIEW items carrying a crop of the candidate rather than as values",
    ),
    (
        "new_rule_repaired",
        16,
        "a cell one of the four no-family findings resolved whose value ALSO went through "
        "glyph repair. Measured on the cells the repass writes: 467 of 1,376 carry a repair "
        "(34%) — prefix 117 of 204 (57%), loo 105 of 258 (41%), tie 216 of 550 (39%), below "
        "29 of 364 (8%) — against 30% of every RESOLVED HLA cell in the store, so only the "
        "prefix repair's own cells are unusually repair-heavy. Repaired values that split "
        "under jitter are wrong 21% of the time corpus-wide, and without this stratum the "
        "signal is pooled away: a document belongs to its RAREST tag, and every one of these "
        "findings is rarer than repaired_glyph's 11,555 documents",
    ),
    # The below-rule sample the direction's safety case needs is >=100 CELLS,
    # and the pack is drawn in DOCUMENTS. Measured on the MERGED build, against
    # the live store with `family_repass.py --no-dry-run` applied to a copy and
    # the two floors in `MIN_DRAW` below: `--n 150` (the default) draws 21
    # documents carrying 41 column-read cells; `--n 300` draws 35 and 66;
    # `--n 600` draws 64 and 116. So the >= 100 cells arrive at `--n 600` and
    # the default pack is a sighting shot, not the evidence — HA-020 records
    # that run as the step the direction may not be promoted without.
    #
    # Without the floors the same build draws 8 documents and 13 cells at the
    # default, because two blood-group strata landed above these in a merge and
    # the weights alone shrank them. That is the failure `MIN_DRAW` exists for,
    # and it is why these two carry a count rather than a share.
    (
        "below_rule_unruled",
        26,
        "read down a column, with two values stacked under one header and NO closed ruled "
        "cell around them. 195 of the 197 two-box column cells the shipped rule resolves are "
        "in this state — 198 before the ruling gate refuses one (a closed cell means one row "
        "band holds both boxes and a vertical ruling stands each side) — and it is the only "
        "shape in which a two-subject table is invisible to every gate: two boxes, two "
        "alleles, both under the header, no printed line between them. The ruling gate "
        "catches the ruled case, 1 cell of 365, and cannot see these. One contradiction here "
        "refutes the direction for this stratum",
    ),
    (
        "below_rule_role_unknown",
        26,
        "read down a column on a page whose ROLE nobody could read. 51 of the 290 column "
        "pages have no resolved ROLE fact; 35 of those gain a cell and they hold 59 of the "
        "364. By the criterion the gate itself uses — no printed role word read anywhere on "
        "the page — it is 211 pages and 249 cells "
        "(.artifacts/no-family/below-rule-population-and-placebo.log). The Persian role "
        "words are what refuse a donor/recipient comparison table, and here that guard "
        "never fires",
    ),
    (
        "family_tie",
        18,
        "the page fits one printed form but a second prototype of that form, leaning "
        "differently, fitted nearly as well; the tie used to refuse the page and now the "
        "form's own cell rule reads it. 975 pages, 651 cells, and 3 labelled documents. "
        "Their 24 labelled HLA cells read 12 correct / 11 abstained / 1 contradicted "
        "(66fca7c6 DQB1, contradicted under the old rule too) — unchanged by the tie and "
        "far too few to say whether the lean argument holds",
    ),
    (
        "family_prefix",
        18,
        "the recognizer boxed a label's HLA- prefix apart; joined back into the word the "
        "form prints, the page fits at the ORDINARY template tolerance and is read from the "
        "repaired boxes. 162 pages, 267 cells. The direct repair of what the left-out fit "
        "accommodates, and it holds the ONE labelled page of that population — 6eeb314e, "
        "whose 8 labelled HLA cells go 4 abstained / 2 missed / 2 partial to 4 abstained / "
        "2 CORRECT / 2 partial when the pass runs, so 2 cells missed -> correct and 0 worse",
    ),
    (
        "family_loo",
        18,
        "the page's label stack fits a form except at ONE label and no fragment on the page "
        "explains it, so the fit without that label carried the form's rule. The residue "
        "after the prefix repair: 209 pages, 259 cells, and NOT ONE of them labelled — the "
        "single labelled page of the old 263 is now read by the repair instead",
    ),
    (
        "below_rule",
        18,
        "the page's locus labels are column HEADERS and the value was read from the cell "
        "beneath its own label, not along a row. 290 pages, 364 cells, NONE of them "
        "labelled and none read by any second detector — this stratum is the only evidence "
        "that exists for the direction. Forced on 290 right-reading pages matched by anchor "
        "count the same rule binds 4 cells, so the direction is doing the work, not the "
        "tolerances",
    ),
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
        "token_anchored_drbx",
        20,
        "the page printed NO readable DRB3/4/5 header and the row was placed from the page's "
        "own label pitch, one row below DRB1; the gene is PRESENT because a token on that row "
        "names it. 479 pages, and only one of them carries an existing label — this stratum is "
        "the only thing that can measure whether the row was the right row",
    ),
    (
        "second_allele_reread",
        20,
        "the cell was RESOLVED with ONE allele and no second; the rest of its ruled row held "
        "ink, and two independent recognizers read the same admissible allele of this locus "
        "out of it. UNMEASURED: the one labelled partial this route can reach is a cell the "
        "two engines refused to agree on, so no person has ever checked one of these. The "
        "second value is the one to look at",
    ),
    (
        "token_anchored_drbx_unresolved",
        20,
        "the DRB3/4/5 row was placed from the page's own label pitch on a page whose DRB1 "
        "VALUE was never resolved, so the corroboration the sibling stratum rests on is "
        "absent and G2b stands in its place: no allele value may stand on the placed row. "
        "116 cells on 92 pages (W2(a), 2026-09-07), not one of them read by a person. This "
        "stratum is the only thing that can say whether lifting that gate was right; cut "
        "with `--only token_anchored_drbx_unresolved` to measure it alone",
    ),
    (
        "widened_drbx_header",
        20,
        "the DRB3/4/5 header was read ONLY by the damage-tolerant pattern, and the page's own "
        "row pitch then put it where a header belongs. 104 pages, 312 gene cells, 119 PRESENT "
        "and 60 ABSENT — and an ABSENT here is a clinical negative resting on a glyph the "
        "recognizer got wrong. No labelled page carries one; the nearest labelled stratum "
        "(damaged header, add-on source) is wrong 5 times in 20. Cut with `--only "
        "widened_drbx_header`, which spreads the sample across the four widenings",
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
    (
        "column_bound",
        20,
        "a comparison sheet with only ONE column filled: the values were bound to the person "
        "named by the heading above that column, checked against the document's own role fact "
        "(`column-bound`, 276 documents / 699 cells). It reverses s12's flat refusal of these "
        "pages under s12-b, the role agreement is the whole wrong-person defence, and 54% of it "
        "rests on a caption claim and 30% on a bare printed role word",
    ),
    (
        "column_named",
        14,
        "the same geometry, but nothing was resolved: either no independent role confirms the "
        "person (`column-named+role-unconfirmed`, 50 documents / 108 cells) or the page itself "
        "prints two (`column-bind-refused` with `rule_id='column/two-subjects'`, 15 documents / "
        "26 cells). Both now carry the tokens and the header box where the reviewer previously "
        "saw no crop at all, and the question asked of them is the ROLE",
    ),
    (
        "column_crowded",
        10,
        "the same sheet, refused because the column that should be empty is not blank — but what "
        "is in it is a date, a frequency or an identifier, not anything shaped like a typing "
        "(`rule_id='column/other-column-unread'`, 25 documents / 53 cells). Kept apart from "
        "`column_named` on purpose: these pages do NOT assert a second subject, and the pass "
        "cannot tell the form's own printing from a second person's values",
    ),
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
        "drbx_addon",
        22,
        "DRB3/4/5 taken from a re-read or from the ink measure rather than the row rule. "
        "Split by the grouped header's spelling, this holds EVERY contradiction the pipeline "
        "has: 37/37 right on a clean header, 15/20 on a damaged one. n=20 is deciding whether "
        "1,461 cells go to review, and that is far too few",
    ),
    (
        "abo_doubled",
        16,
        "two DIFFERENT blood-group values in one printed cell — the 117 the two-engine collapse "
        "refuses. Whether these are one damaged reading or genuinely two subjects is unmeasured",
    ),
    (
        "abo_unreadable",
        16,
        "the blood-group label was found and its cell read as nothing: 2,736 documents, and 14 "
        "of the reviewer's 29 ABO misses. Is the cell empty, or is the window in the wrong place?",
    ),
    (
        "upright",
        18,
        "the photograph was a quarter turn off upright; turned, the page anchors its loci and "
        "these values were read from it (`upright+rotated`). 801 cells on 425 pages that had "
        "ZERO before, and none of them is labelled, so this stratum is the only measure",
    ),
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
# A stratum whose promotion gate names a COUNT gets that count, not a share of
# the total weight. `abo_centre_rescue` is weighted 112 of 603 and drew 21 when
# it was written; two strata then landed beside it in the same merge sequence,
# the total grew, and the same weight drew 19 — twice. HA-019 blocks promoting
# the centre-band route until 20 of its readings have been read by a person, so
# 20 is what the pack draws, whatever else is added later.
#
# The same thing then happened to the two below-rule sub-strata, in the merge
# that brought the blood-group strata in: measured on the merged build against
# the live store with the repass applied to a copy, `--n 150` drew 8 documents
# carrying 13 column-read cells where the direction had been sized for 14 and
# 24. A floor of 8 on each of the two populations where a two-subject table is
# invisible restores it — measured, `--n 150` then draws 21 documents and 41
# column-read cells, `--n 300` 35 and 66, and `--n 600` 64 and 116, which is
# the >= 100 cells the direction's safety case names (HA-020). The floor costs
# `abo_centre_rescue` one document (24 -> 23), still above its own 20.
MIN_DRAW = {"abo_centre_rescue": 20, "below_rule_unruled": 8, "below_rule_role_unknown": 8}
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
    # Whether every multi-box cell this page resolved under the column rule
    # sits inside a CLOSED ruled cell of the printed table. False is the state
    # that matters: two values stacked under one header with no line around
    # them is the one shape in which a two-subject table is invisible to every
    # gate the column rule has, so it is sampled as its own stratum.
    ruled_below_cells: bool = True

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
            # No measured rulings at all: nothing on this page is inside a
            # closed cell, and a column reading here has no printed line to
            # separate two subjects.
            doc.ruled_below_cells = False
            continue
        width, height, horizontal, _ = found
        try:
            segments = json.loads(horizontal or "[]")
        except ValueError:
            # Rulings that cannot be parsed are rulings this pack cannot see,
            # which is the same position as a page with none — and the default
            # here is True, so falling through would call the page fully ruled
            # and keep it OUT of the stratum that samples the unruled ones.
            # Four lines above, the no-rulings branch says False for exactly
            # this reason; an unreadable measurement must not be safer than an
            # absent one.
            doc.ruled_below_cells = False
            continue
        doc.row_slope = measure_row_slope(segments, width, height) or 0.0
        doc.ruled_below_cells = _below_cells_are_ruled(doc, build_lattice(sha, stored, None))


def _below_cells_are_ruled(doc: Doc, lattice: Lattice | None) -> bool:
    """Does every stacked column reading on this page sit in a closed ruled cell?

    "Closed" means the printed table draws all four sides: one row band holds
    every value box of the cell, and a vertical ruling stands on each side of
    them. That is the shape in which the extraction's ruling gate could have
    seen a two-subject table and did not have to — and its absence is what the
    `below_rule_unruled` stratum exists to sample, because there the direction
    rests on nothing but the geometry.
    """
    stacked = [
        cell
        for cell in doc.cells.values()
        if cell.locus in HLA_LOCI
        and cell.status == "RESOLVED"
        and len(cell.value_boxes) >= 2
        and "below" in _new_rule_findings(cell)
    ]
    if not stacked:
        return True
    if lattice is None:
        return False
    for cell in stacked:
        centres = [((b[0] + b[2]) / 2, (b[1] + b[3]) / 2) for b in cell.value_boxes]
        heights = [b[3] - b[1] for b in cell.value_boxes]
        x = sum(c[0] for c in centres) / len(centres)
        band = lattice.row_band(x, centres[0][1], max(heights))
        if band is None or not all(band.contains_y(c[1]) for c in centres):
            return False
        crossing = lattice.verticals_crossing(band)
        left = min(b[0] for b in cell.value_boxes)
        right = max(b[2] for b in cell.value_boxes)
        if not any(v <= left for v in crossing) or not any(v >= right for v in crossing):
            return False
    return True


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
            # `rule_id` carries how the value box entered the cell, which is
            # the only thing that separates a rescued reading from an ordinary
            # one once the row is written.
            doc.abo = {
                "status": status,
                "value": value,
                "source": src,
                "reason": reason,
                "rule_id": rule,
            }
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


# How a cell says which of the four no-family findings read it. The source is
# what `family_repass.py` writes; the rule id is what a re-extraction writes,
# and a stratum keyed on the source alone would empty itself the first time the
# corpus was re-extracted.
_NEW_RULE_SOURCES = {
    "family-tie": "tie",
    "family-loo": "loo",
    "family-prefix": "prefix",
    "below-rule": "below",
}


def _new_rule_findings(cell: Cell) -> set[str]:
    """Which of the four no-family findings read this cell. Usually one.

    The rule id carries EVERY accommodation the assignment used, so a page
    whose prefix was repaired and which then tied between two leans names
    both, and both strata must be able to find it: the sample is also the
    withdrawal list.
    """
    found = set()
    named = _NEW_RULE_SOURCES.get(cell.source or "")
    if named is not None:
        found.add(named)
    rule = cell.rule_id or ""
    if rule == "ADR0008/below-rule":
        found.add("below")
    for marker, name in (("(loo:", "loo"), ("(tie:", "tie"), ("(prefix:", "prefix")):
        if marker in rule:
            found.add(name)
    return found


# `scripts/column_bind.py` writes these, and every one of them is a REVIEW or a
# RESOLVED cell that the two generic refusal strata below would otherwise
# swallow: `review_refused` is 7,798 documents at quota 15, so a page pooled
# there is never sampled, and `zero_fact_refused` ("labels anchored but every
# cell refused") is not even true of a page that anchors nothing.
COLUMN_SOURCES = frozenset({"column-bound", "column-named+role-unconfirmed", "column-bind-refused"})
# The sub-marker inside `column-bind-refused`: a column that is not blank and
# holds nothing shaped like a typing. A separate stratum, because the answer a
# reviewer gives it is a different answer.
COLUMN_UNREAD_RULE = "column/other-column-unread"


def tag_document(doc: Doc, export: Path) -> list[str]:
    """Every stratum this document belongs to, in `STRATA` order."""
    hla = [c for c in doc.cells.values() if c.locus in HLA_LOCI]
    resolved = [c for c in hla if c.status == "RESOLVED"]
    generic = [c for c in hla if c.source not in COLUMN_SOURCES]
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
    if any(c.status == "REVIEW_REQUIRED" and c.value_boxes for c in generic):
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
        anchored = any(c.status == "REVIEW_REQUIRED" for c in generic)
        tags.add("zero_fact_refused" if anchored else "zero_fact_no_anchor")
    if any((c.reason or "").find("and its own label height") >= 0 for c in resolved):
        tags.add("template_band")
    # The four answers for a page that had no layout family. Each is keyed on
    # BOTH the rule the extraction records and the source `family_repass.py`
    # writes, because the same reading reaches the database by two routes: a
    # re-extraction writes the rule id with no source, and the repass writes
    # its own source onto a cell the extraction refused. Keying on the rule id
    # is what makes the stratum survive a re-extraction, which sets no source
    # at all.
    new_rule = [c for c in resolved if _new_rule_findings(c)]
    findings = {name for c in new_rule for name in _new_rule_findings(c)}
    for name, tag in (("tie", "family_tie"), ("loo", "family_loo"), ("prefix", "family_prefix")):
        if name in findings:
            tags.add(tag)
    below = [c for c in resolved if "below" in _new_rule_findings(c)]
    if below:
        tags.add("below_rule")
        # The two sub-strata the direction's own safety case needs. A flat
        # sample of the 290 pages is drawn mostly from pages where a ruled
        # cell or a printed role word would have caught a two-subject table;
        # these two are the populations where neither would.
        if any(len(c.value_boxes) >= 2 and not doc.ruled_below_cells for c in below):
            tags.add("below_rule_unruled")
        if (doc.role or {}).get("value") in (None, "", "UNKNOWN"):
            tags.add("below_rule_role_unknown")
    # A repaired value from one of those findings carries TWO signals, and the
    # rarer stratum would otherwise swallow the other: `choose` pools a
    # document by its rarest tag, and every one of these tags is rarer than
    # `repaired_glyph` (11,555 documents once this pass has run; 11,442 before,
    # measured on the live store). Marked rather than gated, the way
    # `ocr/boxsize.py` marks an odd box.
    if any(c.repaired for c in new_rule):
        tags.add("new_rule_repaired")
    if any(c.source == "rerecognised+ppocrv6" for c in resolved):
        tags.add("second_reading")
    if any(c.source == "page-ocr+wholepage" for c in resolved):
        tags.add("whole_page")
    if any(c.source == "reread-refused+two-engine-agreement" for c in resolved):
        tags.add("two_engine_reread")
    if any(c.source == "drbx-reread+ppocrv6" for c in doc.cells.values() if c.locus in DRBX_LOCI):
        tags.add("drbx_reread")
    if any(c.rule_id == TOKEN_ANCHORED_RULE for c in doc.cells.values() if c.locus in DRBX_LOCI):
        # The row placed from geometry alone on a page whose printed enumeration
        # was never read. Nothing else in the pipeline can say whether it was
        # the right row: no header text corroborates it and the labels do not
        # reach it.
        #
        # Keyed on the RULE, not on the `source` string. The source was written
        # only by the one-off `scripts/drbx_token_repass.py`; the extraction
        # path writes the same rule_id but used to leave `source` NULL, so
        # after any full re-extraction this stratum would have drawn zero — the
        # exact failure this module's own header warns about.
        tags.add("token_anchored_drbx")
    if any("second-allele-reread/v1" in (c.source or "") for c in doc.cells.values()):
        # W3(a): an allele appended to a cell that already had one, read from
        # the rest of the row. Nothing labelled has measured it.
        tags.add("second_allele_reread")
    if any(
        c.rule_id == TOKEN_ANCHORED_UNRESOLVED_RULE
        for c in doc.cells.values()
        if c.locus in DRBX_LOCI
    ):
        # W2(a): the same geometry with DRB1's own value unread, so the only
        # thing standing where the corroboration was is G2b. 116 cells on 92
        # pages, and no labelled page carries one.
        tags.add("token_anchored_drbx_unresolved")
    if any(c.rule_id == WIDENED_HEADER_RULE for c in doc.cells.values() if c.locus in DRBX_LOCI):
        # The DRB3/4/5 header was read only by the damage-tolerant pattern and
        # then corroborated by the page's geometry (route (c)). No labelled page
        # carries one, so nothing has ever measured whether the widening reads a
        # header or something else standing where one belongs — and these pages
        # write ABSENT, which is a clinical negative.
        tags.add("widened_drbx_header")
    if any(
        c.source in ("drbx-reread+ppocrv6", "ink-certified")
        for c in doc.cells.values()
        if c.locus in DRBX_LOCI and c.status == "RESOLVED"
    ):
        tags.add("drbx_addon")
    abo_reason = (doc.abo or {}).get("reason") or ""
    abo_rule = (doc.abo or {}).get("rule_id") or ""
    # The value box was not on its label's line. Whether that cell is the
    # label's is a question only a person can answer, and no person has
    # answered it for any of the centre-band readings. The two routes are
    # tagged apart so the centre route can be given its own quota: pooled, it
    # drew about two documents a pack and HA-019 needs twenty.
    if abo_rule.startswith("abo/anchored-cell+centre"):
        tags.add("abo_centre_rescue")
    elif abo_rule.startswith("abo/anchored-cell+band"):
        tags.add("abo_band_rescue")
    if abo_reason.startswith("more than one blood-group value"):
        tags.add("abo_doubled")
    elif abo_reason.startswith("the blood-group field is printed but its cell"):
        tags.add("abo_unreadable")
    if any(c.source == "upright+rotated" for c in resolved):
        tags.add("upright")
    if (doc.role or {}).get("source") == "FORM_FIELD_BARE":
        tags.add("bare_role")
    if any(c.source == "anchor-row-prefix" for c in resolved):
        tags.add("anchor_row")
    if any(c.source == "column-bound" for c in resolved):
        tags.add("column_bound")
    # Keyed on `rule_id`, not only on `source`: the refusal family shares one
    # source so the whole group stays withdrawable, and the rule id is what
    # separates a page that prints two subjects from one this pass merely could
    # not certify. `column_bind.py` writes both on every run, so a
    # re-extraction that re-runs the pass reproduces both strata.
    if any(c.rule_id == COLUMN_UNREAD_RULE for c in hla):
        tags.add("column_crowded")
    elif any(c.source in ("column-named+role-unconfirmed", "column-bind-refused") for c in hla):
        tags.add("column_named")
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


def prior_labels(sources: list[Path]) -> tuple[dict[str, dict], dict[str, dict]]:
    """The reviewer's earlier answers: per cell and per document. Later rounds win.

    A cell answer is `{"state", "alleles", "unsure", "note"}`; a document answer
    is `{"role", "abo", "rh"}`. Used by `--disagreements-only`, which builds a
    pack of exactly the documents where the pipeline now disagrees with one of
    these, so the reviewer can re-check the disagreeing cells — and only those —
    against the crop. Labels are the scarcest thing this project has, and a
    label that was wrong costs twice: once as a false miss, once as a rule tuned
    to reproduce it.
    """
    cells: dict[str, dict] = {}
    documents: dict[str, dict] = {}
    for source in sources:
        try:
            payload = json.loads(Path(source).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        notes = payload.get("notes") or {}
        for cell_id, answer in (payload.get("cells") or {}).items():
            if not isinstance(answer, dict):
                continue
            cells[cell_id] = {
                "state": answer.get("state"),
                "alleles": list(answer.get("alleles") or []),
                "unsure": bool(answer.get("unsure")),
                "note": notes.get(cell_id) or "",
            }
        for short, answer in (payload.get("documents") or {}).items():
            if isinstance(answer, dict):
                documents.setdefault(short, {}).update(
                    {k: v for k, v in answer.items() if k in ("role", "abo", "rh") and v}
                )
    return cells, documents


def disagreement(cell: Cell, prior: dict | None) -> bool:
    """Does the pipeline's CURRENT reading disagree with the reviewer's answer?

    Scored with the golden rule (`review/golden.classify`), so "disagrees" here
    is exactly `missed`, `partial` or `contradicted` in `label_score.py`; an
    abstention the reviewer also abstained on, or a correct value, is agreement.
    """
    if not prior or not prior.get("state"):
        return False
    from kidneymatch.review.golden import CellLabel, LabelState, Outcome, classify

    try:
        label = CellLabel(state=LabelState(prior["state"]), alleles=tuple(prior["alleles"]))
    except (ValueError, TypeError):
        return False
    values = tuple(part.split("*")[-1] for part in (cell.value or "").split() if part)
    outcome = classify(label, (cell.status, cell.locus, values, cell.second_allele))
    return outcome in (Outcome.MISSED, Outcome.PARTIAL, Outcome.FALSE_ACCEPTANCE)


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


def spread_key(doc: Doc, tag: str) -> str | None:
    """What a stratum is round-robined across, so one pool is not one thing.

    Layout family everywhere, except the widened-header stratum, where the
    thing that must not dominate the sample is the BRANCH — which of the four
    widenings let this page's header in. They are four different kinds of
    recognizer damage, and the pack exists to tell them apart; a sample that is
    all `slash-as-4` measures one of them and is silent about the other three.
    """
    if tag != "widened_drbx_header":
        return doc.family
    branches = {
        (c.source or "").split(":", 1)[1]
        for c in doc.cells.values()
        if c.locus in DRBX_LOCI and (c.source or "").startswith(f"{WIDENED_HEADER_SOURCE}:")
    }
    return "+".join(sorted(branches)) or None


def choose(
    docs: dict[str, Doc],
    n: int,
    seed: int,
    export: Path,
    pin: set[str] | None = None,
    only: str | None = None,
) -> list[Doc]:
    """Stratified, deterministic, spread across layout families inside a stratum.

    `only` cuts a pack of ONE stratum: every document carrying that tag is
    pooled there whatever rarer signal it also carries, and no other stratum is
    drawn. That is how a route with no labelled page gets the >= 40 rows a
    promotion decision needs, instead of the handful a weight would give it in
    a general pack.
    """
    rng = random.Random(seed)
    present: list[Doc] = []
    for doc in docs.values():
        doc.tags = tag_document(doc, export)
        if only is not None:
            doc.tags = [t for t in doc.tags if t == only]
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
    #
    # Rarity alone is not enough, and the mirror of that bug bit next: a COMMON
    # stratum every one of whose documents also carries a rarer tag is pooled
    # away entirely. `drbx_addon` holds 3,737 documents and drew ZERO, and it
    # is the stratum deciding whether 1,461 cells go to review. So `carriers`
    # keeps every document that bears a tag, and the one-per-stratum pass below
    # falls back to it when a pool is empty. Exclusivity still holds: a
    # document is chosen once, and `seen` is what enforces that.
    frequency = Counter(tag for doc in present for tag in doc.tags)
    pools: dict[str, list[Doc]] = defaultdict(list)
    carriers: dict[str, list[Doc]] = defaultdict(list)
    for doc in present:
        doc.tags = sorted(doc.tags, key=lambda tag: (frequency[tag], STRATA_ORDER[tag]))
        pools[doc.tags[0]].append(doc)
        for tag in doc.tags:
            carriers[tag].append(doc)
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
            grouped[spread_key(doc, tag)].append(doc)
        for group in grouped.values():
            rng.shuffle(group)
        by_family[tag] = grouped

    def take(tag: str, want: int) -> None:
        # Round-robin across layout families inside one stratum, so a stratum
        # held by one printed form does not fill with that form alone.
        grouped = by_family[tag]
        already = {d.sha256 for d in chosen}
        for family in list(grouped):
            grouped[family] = [d for d in grouped[family] if d.sha256 not in already]
        families = sorted(grouped, key=lambda f: (f is None, str(f)))
        taken = 0
        while taken < want and len(chosen) < n and any(grouped[f] for f in families):
            for family in families:
                if grouped[family] and taken < want and len(chosen) < n:
                    chosen.append(grouped[family].pop())
                    taken += 1

    if only is not None:
        # One stratum, so there is nothing for the one-per-stratum pass or the
        # weights to balance, and the top-up would fill the rest of the pack at
        # random. The whole of `n` goes to this stratum in ONE round-robin over
        # its branches — running the one-per pass first would restart that
        # round-robin and take the first branch twice.
        take(only, n)
        return chosen[:n]

    # ONE document from every stratum that has any, before a single stratum
    # takes a second. A pack is a diagnostic instrument, and a signal with no
    # document in it is a signal nobody can check — which is what happened
    # when six strata were added and the weights alone starved the smallest.
    for tag, _, _ in sorted(STRATA, key=lambda e: (len(pools[e[0]]), STRATA_ORDER[e[0]])):
        before = len(chosen)
        take(tag, 1)
        if len(chosen) > before or not carriers[tag]:
            continue
        # Its own pool is empty because every document carrying this signal was
        # pooled to a rarer one. Borrow a carrier instead: a stratum nobody can
        # see is a question nobody can answer.
        taken = {d.sha256 for d in chosen}
        spare = [d for d in carriers[tag] if d.sha256 not in taken]
        if spare and len(chosen) < n:
            chosen.append(rng.choice(spare))
    # A promotion gate's own count comes before the weights, so that adding a
    # stratum elsewhere cannot quietly take it below the number it names.
    for tag, floor in MIN_DRAW.items():
        already = sum(1 for doc in chosen if tag in doc.tags)
        take(tag, max(0, min(floor, n) - already))
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
    if cell.anchor_box and not (cell.source in COLUMN_SOURCES and cell.value_boxes):
        # On a comparison sheet the "anchor" is the column HEADING, and it sits
        # a long way above the row. Measured over the 807 cells this pass
        # writes on a bound or named page, unioning it in gives a strip with a
        # median height of 5.7 header heights (p90 12.1) at 0.11 page widths,
        # 60% of which swallow at least one OTHER locus's row — unreadable at
        # the 58px the page shows a crop at, and an invitation to read the
        # wrong row. The heading is still stored, and `highlight()` draws and
        # zooms to it on the full image, which is where it can be read.
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


def pack_document(
    doc: Doc,
    export: Path,
    out: Path,
    prior_cells: dict[str, dict] | None = None,
    prior_docs: dict[str, dict] | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
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
                # The reviewer's earlier answer, and whether the pipeline now
                # disagrees with it. Present only in a disagreements pack.
                "prior_label": (prior_cells or {}).get(cell_id),
                "disagrees": disagreement(cell, (prior_cells or {}).get(cell_id)),
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
        # The reviewer's earlier whole-page answers, with a flag per field where
        # the pipeline now disagrees. NOT_PRINTED / UNREADABLE / UNKNOWN answers
        # describe the page, not the person, so they never count as disagreement.
        "prior_doc": (prior_docs or {}).get(doc.short),
        "doc_disagrees": {
            field: bool(
                (prior_docs or {}).get(doc.short, {}).get(field)
                and (prior_docs or {})[doc.short][field]
                not in ("NOT_PRINTED", "UNREADABLE", "UNKNOWN")
                and (getattr(doc, field) or {}).get("status") == "RESOLVED"
                and str((getattr(doc, field) or {}).get("value") or "").upper()
                != str((prior_docs or {})[doc.short][field]).upper()
            )
            for field in ("role", "abo", "rh")
        },
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
    only: str | None = None,
    prior_cells: dict[str, dict] | None = None,
    prior_docs: dict[str, dict] | None = None,
    disagreements_only: bool = False,
) -> dict[str, int]:
    con = sqlite3.connect(facts_db)
    docs = load_documents(con)
    if disagreements_only:
        # Exactly the documents where the pipeline now disagrees with an earlier
        # answer — a cell (missed / partial / contradicted) or a whole-page
        # field — and nothing else. `n` becomes that count; the strata are not
        # consulted, because this pack is not a sample of anything.
        wanted: set[str] = set()
        for doc in docs.values():
            for locus, cell in doc.cells.items():
                if disagreement(cell, (prior_cells or {}).get(f"{doc.short}:{locus}")):
                    wanted.add(doc.short)
                    break
            else:
                for field in ("role", "abo", "rh"):
                    want = (prior_docs or {}).get(doc.short, {}).get(field)
                    got = getattr(doc, field) or {}
                    if (
                        want
                        and want not in ("NOT_PRINTED", "UNREADABLE", "UNKNOWN")
                        and got.get("status") == "RESOLVED"
                        and str(got.get("value") or "").upper() != str(want).upper()
                    ):
                        wanted.add(doc.short)
                        break
        docs = {sha: d for sha, d in docs.items() if d.short in wanted}
        pin = set(wanted)
        n = len(wanted)
        print(f"disagreements only: {n} documents carry a cell or field the pipeline now disputes")
    attach_signals(docs, con, geometry_db)
    con.close()
    if drop:
        docs = {sha: doc for sha, doc in docs.items() if doc.short not in drop}
    chosen = choose(docs, n, seed, export, pin, only=only)
    if len({d.short for d in chosen}) != len(chosen):
        raise ValueError("two chosen documents share a 16-character id prefix")
    out.mkdir(parents=True, exist_ok=True)
    (out / "images").mkdir(exist_ok=True)
    (out / "crops").mkdir(exist_ok=True)
    records: list[dict[str, object]] = []
    pipeline: dict[str, object] = {}
    for doc in chosen:
        record, cells = pack_document(
            doc, export, out, prior_cells=prior_cells, prior_docs=prior_docs
        )
        records.append(record)
        pipeline.update(cells)
    attach_messages(records, source_db)
    extra: dict[str, dict[str, str]] = {}
    if suggestions_dir and suggestions_dir.exists():
        for path in sorted(suggestions_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            extra[str(payload.get("engine") or path.stem)] = dict(payload.get("cells", {}))
    strata_counts = Counter(str(r["primary_tag"]) for r in records)
    # How many packed documents CARRY each signal, which is not the same as how
    # many were pooled under it: a document belongs to its rarest stratum, and
    # one borrowed to represent a common stratum keeps its own primary tag. The
    # primary count alone read `drbx_addon 0` on a pack carrying 12 of them.
    carried_counts = Counter(tag for r in records for tag in (r["tags"] or []))
    pack = {
        "schema": PACK_SCHEMA,
        "pack_id": f"{seed}-{n}-{time.strftime('%Y%m%d', time.gmtime())}",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        "strata": [
            {
                "tag": t,
                "weight": w,
                "meaning": m,
                "n": strata_counts.get(t, 0),
                "carried_by": carried_counts.get(t, 0),
            }
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
    return {t: carried_counts.get(t, 0) for t, _, _ in STRATA}


def write_launcher(out: Path, port: int = 8765) -> None:
    """A double-clickable server for the pack.

    Opened straight off the disk, a browser may refuse this page `localStorage`,
    and the page would then forget the labels on reload. It says so when that
    happens, but the better answer is not to depend on it: serving the folder
    over localhost makes storage ordinary, and costs the reader one click.
    """
    # `python` on the reader's PATH is not this project's interpreter — on the
    # box that built the first packs it resolved to a Python 2 that has no
    # `http.server`, and the window closed before the error could be read. The
    # project's own interpreter is three directories up from a pack; it is
    # used when it is there, and the PATH one only as the fallback.
    venv = r"%~dp0..\..\..\.venv\Scripts\python.exe"
    windows = [
        "@echo off",
        'cd /d "%~dp0"',
        f'set "PY={venv}"',
        'if not exist "%PY%" set "PY=python"',
        f'start "" http://localhost:{port}/index.html',
        f'"%PY%" -m http.server {port} --bind 127.0.0.1',
        "if errorlevel 1 pause",
        "",
    ]
    posix = [
        "#!/bin/sh",
        'cd "$(dirname "$0")"',
        'PY="$(dirname "$0")/../../../.venv/bin/python"',
        '[ -x "$PY" ] || PY=python3',
        f'"$PY" -m http.server {port} --bind 127.0.0.1',
        "",
    ]
    # newline="" or the platform translates these again and cmd.exe gets \r\r\n.
    (out / "serve.cmd").write_text("\r\n".join(windows), encoding="ascii", newline="")
    (out / "serve.sh").write_text("\n".join(posix), encoding="ascii", newline="")


def refresh_page(out: Path, page: Path, port: int = 8765) -> int:
    """Replace only the page in an existing pack.

    Rebuilding a pack re-cuts thousands of crops, which makes iterating on the
    page itself slow enough that one stops testing it. The pack's data is
    untouched, so a labeller's stored progress survives.
    """
    if not (out / "pack.json").exists():
        print(f"no pack at {out}; build one first")
        return 2
    shutil.copyfile(page, out / "index.html")
    # The launcher is rewritten with the pack's OWN port. It used to take the
    # default, so a `--page-only --port 8766` refresh quietly pointed
    # `serve.cmd` at 8765 while the reader was told 8766.
    write_launcher(out, port)
    print(f"page refreshed in {out}; reload the browser (Ctrl+F5) at http://localhost:{port}")
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
        "--disagreements-only",
        nargs="+",
        type=Path,
        metavar="EXPORT",
        help="build a pack of ONLY the documents where the pipeline now disagrees with an "
        "answer in these golden-labels/v1 exports; every cell carries the earlier answer "
        "and a `disagrees` flag so the reviewer re-checks just those",
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
        "--only",
        default=None,
        choices=[t for t, _, _ in STRATA],
        help="cut a pack of ONE stratum. A route with no labelled page needs tens of rows "
        "before its calls can be promoted, and a weight in a general pack gives it a handful",
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
        return refresh_page(args.out, args.page, args.port)
    if args.augment_messages:
        return augment_messages(args.out, args.source)
    if not args.facts.exists():
        print(f"missing {args.facts}; run scripts/extract_facts.py first")
        return 2
    prior_cells, prior_docs = prior_labels(
        list(args.keep_labelled or []) + list(args.disagreements_only or [])
    )
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
        only=args.only,
        prior_cells=prior_cells,
        prior_docs=prior_docs,
        disagreements_only=bool(args.disagreements_only),
    )
    packed = json.loads((args.out / "pack.json").read_text(encoding="utf-8"))["n_documents"]
    print(f"packed {packed} documents into {args.out}")
    print("  (a document carries several signals, so the counts below sum to more than that)")
    for tag, count in counts.items():
        print(f"  {tag:<24}{count:>5}")
    print(f"Run serve.cmd in that directory, then label at http://localhost:{args.port} .")
    print("Labels export as golden-labels/v1 and are scored by scripts/golden_score.py.")
    print("Nothing in this directory may be committed: it is the patients' reports.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
