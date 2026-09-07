#!/usr/bin/env python3
"""Run every document through every rule and write the facts, with provenance.

Until now nothing assembled the pipeline. `anchors`, `drbx`, `role`, `abo` and
`drbx_consistency` were imported by their tests and by nothing else, and every
corpus figure quoted in ADR 0008 came from a throwaway session script. That is
how a measurement stops being reproducible, and it is why the review could not
be answered by re-running anything.

This is the one place a document becomes facts. Its output is what the
labelling tool scores against, what the review queue is drawn from, and what
Gold would eventually be published from.

**Nothing here decides anything.** Every rule lives in `src/`, is unit-tested,
and is called as-is. This script only sequences them, applies the two
document-level gates that need a whole page, and records the result.

The two page-level gates:

* **Comparison sheets.** 450 documents print `Donor | Recipient` as column
  headings and carry two people's typings side by side. Which column a value
  belongs to is exactly what a row-based rule cannot tell, so every locus on
  such a page goes to review.
* **Exclusivity.** Each locus resolves with no memory of what another bound, so
  `resolve_document` withdraws both readings when one box is claimed twice.

Resumable and batch-committed, like `ocr_pass.py`: a multi-hour run that cannot
resume is a run that restarts from zero after any interruption.

Output is PHI and lands in gitignored `data/derived/facts.sqlite`.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from kidneymatch.documents.abo import (  # noqa: E402
    AboStatus,
    Rh,
    needs_corroboration,
    read_abo,
    reconcile_abo,
    rule_id_for,
)
from kidneymatch.documents.role import (  # noqa: E402
    Role,
    decide_document_role,
    is_comparison_sheet,
    read_form_role,
)
from kidneymatch.hla.drbx_consistency import ConsistencyOutcome, check_drb1_drbx  # noqa: E402
from kidneymatch.hla.testing_policy import (  # noqa: E402
    LocusTestingPolicy,
    load_testing_policy,
)
from kidneymatch.hla.vocabulary import load_vocabulary  # noqa: E402
from kidneymatch.ocr.anchors import (  # noqa: E402
    Box,
    LocusResolution,
    ResolutionStatus,
    ValueRule,
    enforce_exclusivity,
    resolve_document,
    resolve_in_row,
)
from kidneymatch.ocr.drbx import (  # noqa: E402
    NO_GROUPED_HEADER_REASON,
    GeneCall,
    resolve_grouped_drbx,
    resolve_token_anchored_drbx,
)
from kidneymatch.ocr.geometry import (  # noqa: E402
    PageFrame,
    restore,
    restore_drbx,
    unrectify_box,
)
from kidneymatch.ocr.glyphs import canonical_locus_label  # noqa: E402
from kidneymatch.ocr.lattice import Lattice, RowBand  # noqa: E402
from kidneymatch.ocr.lattice import lattice_for as build_lattice  # noqa: E402
from kidneymatch.ocr.lattice import load_rulings as load_stored_rulings  # noqa: E402
from kidneymatch.ocr.layout import reading_direction  # noqa: E402
from kidneymatch.ocr.rows import page_slopes  # noqa: E402
from kidneymatch.ocr.rows import row_slope as measure_row_slope  # noqa: E402
from kidneymatch.ocr.rulings import GEOMETRY_VERSION  # noqa: E402
from kidneymatch.ocr.store import read_corpus  # noqa: E402
from kidneymatch.ocr.templates import (  # noqa: E402
    LayoutPrototype,
    assign_prototype,
    constant_label_positions,
    fit_similarity,
    merge_prefix_fragments,
)

EXTRACTION_VERSION = "facts/v1"

# The default relation (ADR 0008), used for any document whose form is not
# recognised. The numbers must be validated against the golden corpus rather
# than tuned by yield.
# `fallback_band`: when the overlap test reads nothing in a labelled cell, the
# row is tried once more within 1.5 anchor heights (see `ValueRule`). Measured
# over the 11,140 default-rule documents as a fallback: +901 cells and 890
# second alleles, 0 boxes bound twice, no resolved cell changed.
DEFAULT_RULE = ValueRule(
    direction="right", align_overlap=0.2, max_gap=20.0, max_values=2, fallback_band=1.5
)

# The relation for a recognised form that prints the locus on every value
# (ADR 0007's per-family registry). The second allele column sits 8-25 anchor
# heights away, so the default cap cuts it off on about a quarter of rows; what
# makes reading the whole row band safe instead is the prefix requirement, and
# `template_discovery.py` measures that property per family rather than assuming
# it (99.8-99.9% on the three forms found). Measured over the 12,300 assigned
# documents against the default: resolved cells 28,783 -> 39,606, two-allele
# cells 24,983 -> 39,511, single-allele cells 3,800 -> 95, with impossible
# families and double-bound boxes both still zero.
FAMILY_RULE = ValueRule(
    direction="right",
    align_overlap=0.2,
    max_gap=None,
    max_values=2,
    centre_band=1.9,
    require_prefix=True,
)

# The relation for a form whose locus labels are COLUMN HEADERS, with each
# value in the cell beneath its own label. `ocr/layout.py` decides that from the
# page's geometry rather than from a family, because the property is visible
# without recognising the form: the labels stand side by side on one printed
# line instead of stacked down one column.
#
# The tolerances are the default's, turned through ninety degrees. `max_gap` is
# a vertical reach in label heights, and 3 is ample — on the labelled example
# the value sits between three and four heights under its header — because the
# gate that keeps this honest is not the distance but `align_overlap`: a value
# must stand in its label's own column, measured along the page's column lean.
#
# `refuse_bare`: on a column form the only thing naming the gene is which
# column the value stands in, and a column is what a photographed page shears.
# Measured over the pages the layout reader calls a column form, 727 of 727
# values print their locus, so refusing the bare ones costs nothing here and
# closes the case where the column alone is wrong. It is deliberately NOT
# `require_prefix=True`, which would also admit star-less spellings nobody has
# measured on this layout and switch on `bind_in_lattice`'s ruled-row branch —
# a branch that reads the row to the RIGHT of a header.
#
# This object is SHARED: `page_ocr_bind.py`, `rerecognise_pass.py` and
# `upright_bind.py` all import it, so `refuse_bare` changed their behaviour
# too and had to be measured on them. Dry-run against today's database, this
# build against the pre-change one, byte-identical on all three: page_ocr_bind
# 204 documents (1 read below) and the same 13 cells; rerecognise 204
# documents re-read and the same 18 cells; upright_bind 425 pages (14 read
# below) binding 0 either way. The rulings the ruling gate needs are threaded
# in by each caller, so a pass that has no lattice for a page (upright_bind,
# whose page was turned) simply has no such gate.
#
# The placebo, corrected. The direction's safety story used to rest on
# "forcing BELOW on right-reading pages binds nothing", and that is false.
# Forced on 290 right-reading no-family pages matched to the column pages by
# locus-anchor count (seed 20260907), the rule WITHOUT these gates binds 7
# cells (C 3, DRB1 2, A 1, DQB1 1); the shipped rule binds 4 (DRB1 2, A 1,
# DQB1 1), refuse_bare taking all three C. So `reading_direction` is the
# operative gate, not the rule's own tolerances — which is exactly why the
# direction gets its own review strata.
BELOW_RULE = ValueRule(
    direction="below", align_overlap=0.3, max_gap=3.0, max_values=2, refuse_bare=True
)

# What a value read down a column carries in its provenance. `page_ocr_bind.py`
# has its own wording because the boxes it binds come from a second detector
# reading the whole page; these are our own.
COLUMN_REASON = (
    "read as a COLUMN of a form whose locus labels are headers: the labels stand side by "
    "side on one printed line and the value sits in its label's own column beneath it"
)

# The refusal the page-level fallback answers. On a form measured to print the
# locus on every value, a value that names none is refused (`anchors.py` gate
# 2 under `require_prefix`). Measured on 18 pages, all of them newly assigned
# by the tie clause, that refusal is the family rule being wrong about the page
# rather than the page being unreadable: the default rule reads them, and read
# them before the tie clause assigned them a family at all. So the page goes
# back to the default rule whole — +3/-10 cells under the family rule there,
# so the fallback nets +7.
NAMES_NO_LOCUS = "does not name one"

# The columns `extract` produces, in order. Named explicitly so that a column
# added by a later pass (`decode_pass.py` adds `stability`) cannot silently
# break re-extraction.
FACT_COLUMNS = (
    "sha256, field, extraction_version, status, value, raw, repaired, second_allele, "
    "reason, rule_id, anchor_box, value_boxes, source, engine_version, preproc_version, "
    "imgt_version, created_utc"
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS fact (
    sha256             TEXT NOT NULL,
    field              TEXT NOT NULL,
    extraction_version TEXT NOT NULL,
    status             TEXT NOT NULL,
    value              TEXT,
    raw                TEXT,
    repaired           INTEGER NOT NULL DEFAULT 0,
    second_allele      TEXT,
    reason             TEXT,
    rule_id            TEXT,
    anchor_box         TEXT,
    value_boxes        TEXT,
    source             TEXT,
    engine_version     TEXT,
    preproc_version    TEXT,
    imgt_version       TEXT,
    created_utc        TEXT NOT NULL,
    PRIMARY KEY (sha256, field, extraction_version)
);
CREATE TABLE IF NOT EXISTS document (
    sha256             TEXT NOT NULL,
    extraction_version TEXT NOT NULL,
    rel_path           TEXT NOT NULL,
    quality_band       TEXT,
    family             TEXT,
    comparison_sheet   INTEGER NOT NULL DEFAULT 0,
    consistency        TEXT,
    consistency_reason TEXT,
    n_facts            INTEGER NOT NULL DEFAULT 0,
    created_utc        TEXT NOT NULL,
    PRIMARY KEY (sha256, extraction_version)
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.executescript(SCHEMA)
    # Columns added after the table first existed. `CREATE TABLE IF NOT EXISTS`
    # leaves an older database without them, and a positional insert would then
    # break the moment they were expected — so they are added here, named.
    columns = {row[1] for row in con.execute("PRAGMA table_info(document)")}
    for name, ddl in (
        ("tilt_deg", "REAL"),
        ("frame", "TEXT"),
        # What `ocr/layout.py` counted on this page. The direction it decides
        # settles which way 365 cells are read, and without the counts stored
        # there is no per-page record of WHY: a later reader can see that a
        # page was read down a column but not that 12 pairs of labels shared a
        # line against 1 sharing a column. Four integers, written for every
        # page whether or not the direction changed, so the population that
        # nearly qualified is visible too.
        ("loci_sharing_a_row", "INTEGER"),
        ("loci_sharing_a_column", "INTEGER"),
        ("values_along_the_row", "INTEGER"),
        ("values_under_the_label", "INTEGER"),
        # The label left out of the template fit, when one was — so which
        # label the accommodation dropped is a column, not something to be
        # recovered by parsing the rule ids of the cells it happened to gain.
        ("dropped_label", "TEXT"),
    ):
        if name not in columns:
            con.execute(f"ALTER TABLE document ADD COLUMN {name} {ddl}")
    con.commit()
    return con


def load_geometry(path: Path | None, read_only: bool = False) -> dict[str, tuple[str, float]]:
    """Per-document page geometry from `scripts/geometry_pass.py`: (decision, theta).

    Absent, the identity frame applies everywhere, which is the pipeline of
    today. Only a ROTATE decision — two estimators agreeing — moves anything.

    `read_only`: a pass that only measures opens it that way, so a dry run
    holds no writable handle on a store it never writes to.
    """
    if path is None or not path.exists():
        return {}
    con = (
        sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        if read_only
        else sqlite3.connect(path)
    )
    try:
        return {
            sha: (str(decision), float(theta))
            for sha, decision, theta in con.execute(
                "SELECT sha256, decision, theta_deg FROM page_geometry WHERE geometry_version=?",
                (GEOMETRY_VERSION,),
            )
        }
    except sqlite3.OperationalError:
        return {}
    finally:
        con.close()


# Below this tilt the frame is a wash. Measured on the 53 ROTATE pages of the
# review pack: under 1.5 degrees the row rules already tolerate the drift and
# the estimator's own error is as large as the tilt, so cells were gained and
# lost in equal numbers (9 each); from 2 degrees the frame gained 5 cells and
# lost none. The geometry pass still records ROTATE from half a degree — that
# is measurement — but the extraction only acts on it from here.
MIN_FRAME_TILT_DEG = 1.5


def load_rulings(
    path: Path | None, read_only: bool = False
) -> dict[str, tuple[int, int, str, str]]:
    """The stored rulings of every page under this geometry version (see `ocr.lattice`)."""
    return load_stored_rulings(path, GEOMETRY_VERSION, read_only)


def lattice_for(
    document, rulings: dict[str, tuple[int, int, str, str]], frame: PageFrame | None
) -> Lattice | None:
    return build_lattice(document.sha256, rulings, frame)


def slopes_for(
    document, rulings: dict[str, tuple[int, int, str, str]], frame: PageFrame | None
) -> tuple[float, float]:
    """How this page's printed rows fall and how its printed columns lean.

    Not the same number and not derivable from each other: rows are normalised
    by width over height and columns by height over width, which on a portrait
    page differ by more than four times (`ocr/rows.py`). A rule that reads DOWN
    a column needs the second one, so both are measured here and the row slope
    alone is what `row_slope_for` returns for the callers that only want it.
    """
    stored = rulings.get(document.sha256)
    if stored is None:
        return 0.0, 0.0
    width, height, h_json, _ = stored
    try:
        segments = json.loads(h_json or "[]")
    except ValueError:
        return 0.0, 0.0
    return page_slopes(segments, width, height, frame) or (0.0, 0.0)


def row_slope_for(
    document, rulings: dict[str, tuple[int, int, str, str]], frame: PageFrame | None
) -> float:
    """The slope of this page's printed rows, in the frame the boxes live in.

    Read from the same stored rulings the lattice is built from, and rectified
    by the same frame, so what comes back on a rotated page is the RESIDUAL
    slope the rotation did not remove — which under perspective is not zero.
    Zero whenever the page printed no measurable grid, which is the row test
    exactly as it was (`ocr/rows.py`).
    """
    stored = rulings.get(document.sha256)
    if stored is None:
        return 0.0
    width, height, h_json, _ = stored
    try:
        segments = json.loads(h_json or "[]")
    except ValueError:
        return 0.0
    return measure_row_slope(segments, width, height, frame) or 0.0


# A label the recognizer could not read is placed by the form's template only
# when the page fits that template this well (a fraction of the labels'
# spread; `assign_prototype` accepts up to 0.04) — a row off is a row wrong.
MAX_TEMPLATE_RESIDUAL = 0.04

# Where the template places a label and the page prints NO ruling around it,
# the band is taken from the label's own height instead. Measured: the row
# pitch of these templates is a median 3.35-3.38 label heights, so a band of
# plus/minus 1.5 spans nine tenths of one row and two adjacent bands never
# touch. It is not a tuned yield knob either — 1.0 gives 479 cells, 1.5 gives
# 491 and 2.0 gives 476.
TEMPLATE_BAND_HEIGHTS = 1.5
# The virtual label box: the page's median label size, centred where the
# template puts the label.
_LABEL_SIZE_FALLBACK = (0.08, 0.025)


def _label_size(boxes: list[Box]) -> tuple[float, float]:
    labels = [b for b in boxes if canonical_locus_label(b.text or "")]
    if len(labels) < 3:
        return _LABEL_SIZE_FALLBACK
    widths = sorted(b.x1 - b.x0 for b in labels)
    heights = sorted(b.height for b in labels)
    return widths[len(widths) // 2], heights[len(heights) // 2]


def _grid_contradicts(
    lattice: Lattice,
    boxes: list[Box],
    xc: float,
    yc: float,
    label_h: float,
    band: RowBand,
) -> bool:
    """Does the page's own grid say this placement is on the wrong row?

    No ruling around the label is not evidence against the placement; a ruling
    around the VALUE that excludes the label is. Measured over the 491 cells
    this fallback reaches, 31 are contradicted that way against 4 of the 1,698
    the ruled path already binds — a rate 24 times higher — and on two of them
    the contradicting row holds a different printed locus label. Those are the
    cells where the template fit is good across the page and wrong here.
    """
    for box in boxes:
        if not (band.top <= box.centre_y <= band.bottom) or box.x0 <= xc:
            continue
        theirs = lattice.row_band(box.centre_x, box.centre_y, label_h)
        if theirs is not None and not theirs.contains_y(yc):
            return True
    return False


def bind_in_lattice(
    boxes: list[Box],
    results: dict[str, LocusResolution],
    rule: ValueRule,
    lattice: Lattice,
    prototype: LayoutPrototype | None,
    vocabulary,
    frame: PageFrame | None = None,
    back: dict[int, Box] | None = None,
) -> tuple[dict[str, LocusResolution], set[str]]:
    """Second pass over the row rule's abstentions, with the printed table.

    Two cases, both bound by `resolve_in_row` under every gate:
    * "no anchor": the label glyphs were unreadable. The form's template says
      where that label is printed; if a ruled row sits there, a virtual label
      box is placed and the row's boxes are read. Only on a page that fits the
      template, and the form must print the locus on its values (the family
      rule), so a value from a wrong row names another locus and is refused.
    * "anchor found but no box": the label was read, the overlap test found
      nothing. The ruled row around the label is the printed cell; its boxes
      are the candidates. Also only under the family rule: the row has no
      distance cap, so on a form that prints bare numbers anything in the band
      would bind.
    A lattice reading replaces the row rule's only when it RESOLVES; anything
    less keeps the abstention the row rule gave, so nothing is made worse.
    Returns the results and the loci the lattice bound.
    """
    out = dict(results)
    bound: set[str] = set()
    label_w, label_h = _label_size(boxes)
    fit = None
    if prototype is not None and rule.require_prefix:
        fit = fit_similarity(constant_label_positions(boxes), prototype)
        if fit is not None and fit.residual > MAX_TEMPLATE_RESIDUAL:
            fit = None
    for locus, result in results.items():
        if result.status is ResolutionStatus.RESOLVED:
            continue
        reason = result.reason or ""
        if reason == "no anchor on this document":
            if fit is None or locus not in prototype.positions:
                continue
            px, py = prototype.positions[locus]
            xc, yc = (px - fit.dx) / fit.scale, (py - fit.dy) / fit.scale
            band = lattice.row_band(xc, yc, label_h)
            ruled = band is not None
            if band is None:
                # The template places the label on a page that prints no ruling
                # there. The placement is still evidence — the fit residual is
                # inside `MAX_TEMPLATE_RESIDUAL` and the form prints its locus
                # on every value, so a value from the wrong row names another
                # locus and gate 2 refuses it. So the label's own height gives
                # the band. What is NOT allowed is a placement the page's own
                # grid contradicts, which `_grid_contradicts` measures.
                half = TEMPLATE_BAND_HEIGHTS * label_h
                band = RowBand(yc - half, yc + half)
                if _grid_contradicts(lattice, boxes, xc, yc, label_h, band):
                    continue
            anchor = Box(xc - label_w / 2, yc - label_h / 2, xc + label_w / 2, yc + label_h / 2, "")
            if frame is not None and back is not None and not frame.is_identity:
                # This box was drawn on the LEVEL page; provenance names the
                # stored one, like every box the recognizer produced.
                back[id(anchor)] = unrectify_box(frame, anchor)
            placed = resolve_in_row(boxes, locus, rule, anchor, (band.top, band.bottom), vocabulary)
            if placed.status is ResolutionStatus.RESOLVED:
                out[locus] = replace(
                    placed,
                    reason=(
                        f"label unread; placed by the form's template ({prototype.prototype_id}) "
                        + (
                            "and the ruled row"
                            if ruled
                            else "and its own label height, the page printing no ruling there"
                        )
                        + (f"; {placed.reason}" if placed.reason else "")
                    ),
                )
                bound.add(locus)
        elif (
            reason.startswith("anchor found but no box")
            and result.anchor_box is not None
            and rule.require_prefix
        ):
            # Only on a form measured to print the locus on every value. The
            # ruled row has no distance cap and no overlap test, so on a form
            # that prints bare numbers any number in the band would bind; the
            # value's own prefix is what corroborates the row (gate 2), the
            # same licence the virtual anchor runs under.
            anchor = result.anchor_box
            band = lattice.row_band(anchor.centre_x, anchor.centre_y, anchor.height)
            if band is None:
                continue
            rowed = resolve_in_row(boxes, locus, rule, anchor, (band.top, band.bottom), vocabulary)
            if rowed.status is ResolutionStatus.RESOLVED:
                out[locus] = replace(
                    rowed,
                    reason="bound in the ruled row" + (f"; {rowed.reason}" if rowed.reason else ""),
                )
                bound.add(locus)
    if bound:
        out = enforce_exclusivity(out)
    return out, bound


def frame_for(document, geometry: dict[str, tuple[str, float]]) -> PageFrame | None:
    """The frame the row rules run in for this document, or None for identity."""
    decision, theta = geometry.get(document.sha256, ("NONE", 0.0))
    if decision != "ROTATE" or not document.width or not document.height:
        return None
    if abs(theta) < MIN_FRAME_TILT_DEG:
        return None
    return PageFrame(theta_deg=theta, width=int(document.width), height=int(document.height))


def _box(box: Box | None) -> str | None:
    """Provenance: where on the page this fact came from."""
    return None if box is None else json.dumps([box.x0, box.y0, box.x1, box.y1])


def _boxes(boxes: list[Box]) -> str | None:
    return json.dumps([[b.x0, b.y0, b.x1, b.y1] for b in boxes]) if boxes else None


def persian_boxes(db: Path, read_only: bool = False) -> dict[str, list[Box]]:
    """Persian-pass geometry, keyed by image, thumbnails excluded.

    `read_only` is for the passes that only measure: a store this function
    never writes to should not be opened writable by a script whose whole
    contract is that it changes nothing.
    """
    if not db.exists():
        return {}
    con = (
        sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        if read_only
        else sqlite3.connect(db)
    )
    out: dict[str, list[Box]] = {}
    for sha, rel, boxes_json, texts_json in con.execute(
        "SELECT sha256, rel_path, boxes_json, texts_json FROM persian_result WHERE n_boxes>0"
    ):
        if "_thumb" in rel:
            continue
        raw = json.loads(boxes_json)
        texts = json.loads(texts_json)
        if len(raw) != len(texts):
            continue
        out[sha] = [Box(b[0], b[1], b[2], b[3], t) for b, t in zip(raw, texts, strict=True)]
    con.close()
    return out


def load_families(path: Path) -> tuple[list[LayoutPrototype], set[str]]:
    """The printed forms found by `template_discovery.py`, and which of them
    print the locus on every value."""
    if not path.exists():
        return [], set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    prototypes = [
        LayoutPrototype.from_positions(
            family["family_id"],
            {locus: (point[0], point[1]) for locus, point in family["label_positions"].items()},
        )
        for family in payload.get("families", [])
    ]
    prefixed = {
        family["family_id"]
        for family in payload.get("families", [])
        if family.get("prints_locus_on_values")
    }
    return prototypes, prefixed


def extract(
    document,
    persian: list[Box],
    vocabulary,
    now: str,
    prototypes: list[LayoutPrototype] | None = None,
    prefixed_families: set[str] | None = None,
    caption_role: Role = Role.UNKNOWN,
    testing_policy: LocusTestingPolicy | None = None,
    frame: PageFrame | None = None,
    lattice: Lattice | None = None,
    row_slope: float = 0.0,
    column_slope: float = 0.0,
    raw_lattice: Lattice | None = None,
    caption_abo: tuple[str, Rh] | None = None,
) -> tuple[list[tuple], dict]:
    """Every fact this document yields. Pure: no I/O, so it is testable.

    `lattice` is levelled with `frame`, because the HLA rules run on rectified
    boxes. `raw_lattice` is the same grid in the frame the STORED boxes are in,
    and it is what the blood-group reader needs: `read_abo` is given the boxes
    as stored. Passing the levelled one instead changes which row the rescue
    reads on the ROTATE pages. Measured over 23,485 documents: the raw frame
    gains 93 readings (42 band, 51 centre), the levelled frame 88 (44 band, 44
    centre). The pair is the discriminator and
    `scripts/abo_window_check.py --levelled` prints it.

    `caption_abo` is the blood group every message this photograph was posted
    with agrees on, and it is consulted for ONE purpose: corroborating a value
    that only the label's ruled row admitted (`needs_corroboration`). Weighing a
    chat claim against a printed form in general is `scripts/caption_pass.py`'s
    job; handing it to `reconcile_abo` unconditionally here would also let it
    resolve cells the form does not read and raise conflicts the caption pass
    records instead, neither of which this rule is about.
    """
    latin = document.boxes
    rows: list[tuple] = []
    comparison = is_comparison_sheet(latin)

    # The row rules read a LEVEL page. Where the geometry pass declared the
    # photograph ROTATE — two estimators agreeing on the tilt — the stored
    # boxes are straightened first and every rule runs unchanged on them;
    # provenance is restored to the boxes as stored below. Without a frame this
    # is the identity and byte-for-byte the pipeline of before.
    level = frame if frame is not None else PageFrame.identity(1, 1)
    latin_level, back = level.rectify(latin)

    # Which printed form is this? An unrecognised one gets the conservative
    # default; claiming a family would apply its authored cell rule to a layout
    # it was never measured on.
    #
    # `rule_of` is what lets a near-tie between prototypes be assigned instead
    # of refused: the tie clause needs to know that the tied prototypes author
    # ONE cell rule, and only this caller knows which rule each one authors.
    # `leave_one_out` admits a page whose stack fits except at one label, which
    # is a reading accommodation and never evidence for building a form —
    # `template_discovery.py` therefore leaves it off.
    prefixed_families = prefixed_families or set()
    rule_of = {
        proto.prototype_id: ("family" if proto.prototype_id in prefixed_families else "default")
        for proto in prototypes or []
    }
    assignment = assign_prototype(
        latin_level, prototypes or [], rule_of=rule_of, leave_one_out=True
    )
    if assignment is not None and assignment.merged_prefixes:
        # The page fitted once the `HLA-` fragments the recognizer boxed apart
        # were put back. It must then be READ from the repaired boxes: the same
        # displacement that broke the template fit also drags the label's own
        # centre right, and the ownership gate hands its value to the next
        # locus down (measured: 9 DRB1 cells refused as "closer to the DQB1
        # label"). The joined box keeps the label's text, so no locus comes
        # from anything but the characters that named it before.
        latin_level, _, sources = merge_prefix_fragments(latin_level)
        for merged_id, (label_box, fragment) in sources.items():
            # Provenance must name the boxes as STORED, so the joined box gets
            # a way back of its own: the union of what the two halves were
            # before the page was levelled.
            first = back.get(id(label_box), label_box)
            second = back.get(id(fragment), fragment)
            back[merged_id] = Box(
                min(first.x0, second.x0),
                min(first.y0, second.y0),
                max(first.x1, second.x1),
                max(first.y1, second.y1),
                first.text,
            )
    family = assignment.prototype_id if assignment else None
    family_path = family is not None and family in prefixed_families
    rule = FAMILY_RULE if family_path else DEFAULT_RULE
    rule_id = f"family/{family}" if family_path else "ADR0008/default-row-rule"
    if family_path and assignment is not None:
        # Provenance for the three accommodations, so the review pack can
        # stratify on them and a reviewer sees which pages they hold up.
        if assignment.merged_prefixes:
            rule_id += f"(prefix:{','.join(assignment.merged_prefixes)})"
        if assignment.tied_with:
            rule_id += f"(tie:{','.join(assignment.tied_with)})"
        if assignment.dropped_label:
            rule_id += f"(loo:{assignment.dropped_label})"

    # Which WAY does this page read? Measured from its own geometry rather
    # than from a family, because the property is visible without recognising
    # the form: the labels stand side by side on one printed line instead of
    # stacked down one column. Asked only where no family was recognised — a
    # recognised form has an authored rule, and that rule reads rightwards.
    role_reading = read_form_role(persian, latin)
    two_subjects = len({token.role for token in role_reading.tokens}) > 1
    layout = reading_direction(latin_level, row_slope, column_slope)
    reads_down = family is None and layout.direction == "below"
    if reads_down and not two_subjects:
        # A header row over two subject rows is exactly what a column layout
        # looks like from the geometry, and the page's own role words are the
        # only thing that can tell them apart. Measured on THIS build with the
        # gate neutralised (`family_repass.py --dry-run`, live stores, read-only):
        # 305 pages read as a column layout and claim 381 cells without it, 290
        # and 364 with it — so the role words cost 15 pages and 17 cells, and
        # they are what stands between this direction and a comparison table.
        #
        # The page's own rulings travel with the rule: reading down a column,
        # a ruling between two stacked values is the only thing on the page
        # that separates one person's pair from two people's singles.
        rule = replace(
            BELOW_RULE,
            row_slope=row_slope,
            column_slope=column_slope,
            row_rulings=lattice.horizontal if lattice is not None else (),
        )
        rule_id = "ADR0008/below-rule"
    # The rows of this page, along the slope this page prints them at. On a
    # level page, or one whose rulings could not be measured, this is the rule
    # unchanged.
    elif row_slope:
        rule = replace(rule, row_slope=row_slope)

    def add(field, status, **kwargs):
        rows.append(
            (
                document.sha256,
                field,
                EXTRACTION_VERSION,
                status,
                kwargs.get("value"),
                kwargs.get("raw"),
                int(kwargs.get("repaired", False)),
                kwargs.get("second_allele"),
                kwargs.get("reason"),
                kwargs.get("rule_id"),
                kwargs.get("anchor_box"),
                kwargs.get("value_boxes"),
                kwargs.get("source"),
                document.engine_version,
                document.preproc_version,
                vocabulary.imgt_version,
                now,
            )
        )

    def read_page(rule: ValueRule) -> tuple[dict[str, LocusResolution], set[str]]:
        results = resolve_document(latin_level, rule, vocabulary=vocabulary)
        bound: set[str] = set()
        if lattice is not None:
            prototype = next((p for p in prototypes or [] if p.prototype_id == family), None)
            results, bound = bind_in_lattice(
                latin_level, results, rule, lattice, prototype, vocabulary, level, back
            )
        return results, bound

    results, lattice_bound = read_page(rule)
    policy_family = family
    newly_assigned = assignment is not None and bool(
        assignment.tied_with or assignment.dropped_label or assignment.merged_prefixes
    )
    if (
        family_path
        and newly_assigned
        and any(NAMES_NO_LOCUS in (r.reason or "") for r in results.values())
    ):
        # This page's values do not name their locus, and the family rule can
        # only refuse them. The default rule reads the page — it is the rule
        # the page had before the tie or the left-out fit recognised a form on
        # it — so the page goes back to it whole rather than cell by cell, and
        # the testing policy goes with it: a policy measured per family must
        # not be applied to a page the family's own rule could not read.
        #
        # Only for a page one of those two accommodations assigned. That is
        # where it was measured (18 pages, 24 cells, +3/-10 under the family
        # rule, so the fallback nets +7) and where the claim holds that the
        # default rule was already safe on this page. Applied to the 12,356
        # pages that fitted a form outright it is a different and unmeasured
        # change: 2,000 of them sampled lose 10 cells and gain 5.
        rule = replace(DEFAULT_RULE, row_slope=row_slope) if row_slope else DEFAULT_RULE
        rule_id = "ADR0008/default-row-rule"
        policy_family = None
        results, lattice_bound = read_page(rule)
    if rule.direction == "below":
        # Where a value came from travels with it: the reviewer sees a column
        # reading and can check the column.
        results = {
            locus: (
                replace(
                    result,
                    reason=COLUMN_REASON + (f"; {result.reason}" if result.reason else ""),
                )
                if result.status is ResolutionStatus.RESOLVED
                else result
            )
            for locus, result in results.items()
        }
    loci = {locus: restore(result, back) for locus, result in results.items()}
    for locus, result in loci.items():
        status = result.status
        reason = result.reason
        if (
            testing_policy is not None
            and status is ResolutionStatus.REVIEW_REQUIRED
            and (result.reason or "").startswith("anchor found but no box")
            and testing_policy.is_not_tested(policy_family, locus)
        ):
            # HA-009: the form prints this row, the cell is empty, and this
            # laboratory measurably never fills it. That is a finding, and
            # sending it to a reviewer wastes the one resource this project is
            # short of. Only an EMPTY cell is reclassified; a resolved one keeps
            # its value.
            status = ResolutionStatus.NOT_TESTED
            reason = testing_policy.reason(policy_family, locus)
        if comparison and status is ResolutionStatus.RESOLVED:
            # Two subjects on one page: the row rule cannot say whose column a
            # value is in.
            status = ResolutionStatus.REVIEW_REQUIRED
            reason = "this page prints donor and recipient columns for two subjects"
        add(
            locus,
            status.value,
            value=" ".join(result.values) if status is ResolutionStatus.RESOLVED else None,
            raw=" ".join(v.raw for v in result.parsed_values) or None,
            repaired=result.repaired,
            second_allele=(
                result.second_allele.value if status is ResolutionStatus.RESOLVED else None
            ),
            reason=reason,
            rule_id=rule_id + ("+lattice" if locus in lattice_bound else ""),
            anchor_box=_box(result.anchor_box),
            value_boxes=_boxes(result.value_boxes),
        )

    read_genes = resolve_grouped_drbx(latin_level)
    drb1_read = loci.get("DRB1")
    if (
        read_genes["DRB3"].reason == NO_GROUPED_HEADER_REASON
        and drb1_read is not None
        and drb1_read.status is ResolutionStatus.RESOLVED
        and not comparison
    ):
        # No header was read anywhere on this page. The row can still be placed
        # from the page's own geometry — one label pitch below the DRB1 label —
        # and a gene token standing on it read as PRESENT. Never ABSENT: the
        # counting argument that licenses absence needs the printed enumeration,
        # and that is exactly what was not read. The DRB1 status tested here is
        # the FINAL one, after the lattice and the comparison-sheet downgrade,
        # because that is the fact the page ends up carrying.
        token_row = resolve_token_anchored_drbx(
            latin_level, drb1_resolved=True, row_slope=row_slope, lattice=lattice
        )
        if token_row.facts is not None:
            read_genes = token_row.facts
    genes = {gene: restore_drbx(fact, back) for gene, fact in read_genes.items()}
    # The comparison-sheet downgrade is applied to `genes` ITSELF, not to a
    # local copy of the status. The document summary's consistency verdict is
    # built from this dict further down, and while the downgrade lived only in
    # the loop below the summary judged a comparison sheet as if its genes had
    # been resolved — the stored cells said REVIEW_REQUIRED and the summary
    # said CONSISTENT about values nobody had accepted.
    if comparison:
        # The same guard the loci get. Two subjects on one page and the row
        # rule cannot say whose gene the row prints. Today no comparison
        # sheet in the corpus has a readable grouped header, so this changes
        # nothing measurable — it fails closed for the ones that will.
        genes = {
            gene: (
                replace(
                    fact,
                    status=ResolutionStatus.REVIEW_REQUIRED,
                    reason="this page prints donor and recipient columns for two subjects",
                )
                if fact.status is ResolutionStatus.RESOLVED
                else fact
            )
            for gene, fact in genes.items()
        }
    for gene, fact in genes.items():
        add(
            gene,
            fact.status.value,
            value=fact.call.value if fact.status is ResolutionStatus.RESOLVED else None,
            raw=fact.raw_text,
            repaired=fact.repaired,
            reason=fact.reason,
            rule_id=fact.rule_id,
            # Which route read this row, when it was not the plain header
            # route: `token-anchored-drbx`, or `widened-drbx-header:<branch>`.
            # It comes from the RULE, so a re-extraction reproduces it and the
            # review strata keyed on it cannot silently empty.
            source=fact.source,
            anchor_box=_box(fact.header_box),
            # Every box on the row that named this gene, not only the first:
            # a row can print one gene twice, and the second box is what a
            # re-read pass needs to count the second haplotype slot.
            value_boxes=_boxes(list(fact.gene_boxes) or ([fact.gene_box] if fact.gene_box else [])),
        )

    reading = role_reading  # read above: the column rule asks whether two roles are printed
    # The caption is what the POSTER said, and the poster is often a broker.
    # `decide_document_role` lets it corroborate a weak printed field or veto
    # any reading, and never lets it rename the subject.
    decision = decide_document_role(reading, caption_role=caption_role)
    add(
        "ROLE",
        (
            ResolutionStatus.RESOLVED.value
            if decision.is_finding
            else ResolutionStatus.REVIEW_REQUIRED.value
            if decision.needs_review
            else ResolutionStatus.UNKNOWN.value
        ),
        value=decision.role.value if decision.is_finding else None,
        reason=decision.reason or reading.reason,
        rule_id=f"role/{reading.tier.value}",
        source=decision.source,
        anchor_box=_box(reading.anchor_box),
        value_boxes=_boxes([t.box for t in reading.tokens]),
    )

    abo_reading = read_abo(persian, latin, lattice=raw_lattice)
    # F1(b): a band-only reading boxed by one engine is published only when the
    # caption agrees on the letter. Everywhere else the caption is withheld, so
    # this call is the shipped one-argument call it has always been.
    corroboration = (
        {caption_abo} if caption_abo is not None and needs_corroboration(abo_reading) else None
    )
    abo_decision = reconcile_abo(abo_reading, caption_claims=corroboration)
    # The route the value box took into the cell is part of the rule's
    # identity: it is how this group is found in the facts table, sampled into
    # a review pack, and withdrawn if the labels turn against it.
    abo_rule_id = rule_id_for(abo_reading)
    add(
        "ABO",
        abo_decision.status.value,
        value=abo_decision.group,
        raw=abo_reading.raw_value,
        repaired=abo_reading.repaired,
        reason=abo_decision.reason or abo_reading.reason,
        rule_id=abo_rule_id,
        source=abo_decision.source.value,
        anchor_box=_box(abo_reading.anchor_box),
        value_boxes=_boxes(
            list(abo_reading.value_boxes)
            or ([abo_reading.value_box] if abo_reading.value_box else [])
        ),
    )
    add(
        "RH",
        (
            ResolutionStatus.RESOLVED.value
            if abo_decision.status is AboStatus.RESOLVED
            else ResolutionStatus.UNKNOWN.value
        ),
        value=abo_decision.rh.value,
        reason="Rh is never synthesised when the cell does not print it",
        rule_id=abo_rule_id,
        source=abo_decision.source.value,
    )

    drb1 = loci.get("DRB1")
    consistency = ConsistencyOutcome.NOT_CHECKABLE
    consistency_reason = "the DRB1 row or the DRB3/4/5 row was not read"
    if drb1 is not None and drb1.status is ResolutionStatus.RESOLVED:
        # Only cells the page actually STORES as findings. A call the row rule
        # made and the extraction then withdrew to review is not a finding, and
        # the summary must not check the DRB1 row against it.
        present = {
            g
            for g, f in genes.items()
            if f.call is GeneCall.PRESENT and f.status is ResolutionStatus.RESOLVED
        }
        absent = {
            g
            for g, f in genes.items()
            if f.call is GeneCall.ABSENT and f.status is ResolutionStatus.RESOLVED
        }
        checked = check_drb1_drbx([v.first_field for v in drb1.parsed_values], present, absent)
        consistency, consistency_reason = checked.outcome, checked.reason

    summary = {
        "rel_path": document.rel_path,
        "family": family,
        "quality_band": document.quality_band.value,
        "comparison_sheet": int(comparison),
        "consistency": consistency.value,
        "consistency_reason": consistency_reason,
        "n_facts": sum(1 for r in rows if r[3] == ResolutionStatus.RESOLVED.value),
        # The frame the row rules ran in. `tilt_deg` is the straightening angle
        # applied to the stored boxes; 0 with the identity frame.
        "tilt_deg": float(level.theta_deg),
        "frame": "identity" if level.is_identity else "ROTATE",
        # The layout reader's own counts, for every page. `reading_direction`
        # is asked of every document; only a page with no family may act on
        # the answer, and the counts say how close the others came.
        "loci_sharing_a_row": layout.loci_sharing_a_row,
        "loci_sharing_a_column": layout.loci_sharing_a_column,
        "values_along_the_row": layout.values_along_the_row,
        "values_under_the_label": layout.values_under_the_label,
        "dropped_label": assignment.dropped_label if assignment is not None else None,
    }
    return rows, summary


def load_caption_roles(source_db: Path | None) -> dict[str, Role]:
    """Per-document caption claims, written by `scripts/link_documents.py`.

    Only a STATEMENT is carried through. A REFUSED claim — a caption that reads
    as a request for a role rather than an assertion of one — deliberately says
    nothing, because a request inverts the subject.
    """
    if source_db is None or not source_db.exists():
        return {}
    con = sqlite3.connect(source_db)
    try:
        rows = con.execute(
            "SELECT sha256, role FROM document_caption_claim WHERE tier = 'STATEMENT'"
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    finally:
        con.close()
    return {sha256: Role(role) for sha256, role in rows if role in set(Role)}


def load_caption_abo(source_db: Path | None) -> dict[str, tuple[str, Rh]]:
    """The blood group every message a photograph was posted with agrees on.

    The same reading `scripts/caption_pass.py` publishes as a CAPTION_CLAIM, and
    read by the same function so the two can never drift: a message naming two
    groups, or asking FOR one, says nothing, and two messages naming different
    groups leave the document alone. Here it is not published — it is only
    allowed to corroborate a value the label's ruled row admitted on one
    engine's word (`needs_corroboration`).
    """
    if source_db is None or not source_db.exists():
        return {}
    from caption_pass import claim_for, messages_by_document

    out: dict[str, tuple[str, Rh]] = {}
    for sha, texts in messages_by_document(source_db).items():
        group, rh, _ = claim_for(texts)
        if group:
            out[sha] = (group, Rh(rh) if rh in set(Rh) else Rh.UNKNOWN)
    return out


def run(
    src: Path,
    persian_db: Path,
    families_db: Path,
    out: Path,
    limit: int | None,
    batch: int,
    source_db: Path | None = None,
    geometry_db: Path | None = None,
) -> int:
    vocabulary = load_vocabulary()
    testing_policy = load_testing_policy()
    geometry = load_geometry(geometry_db)
    rulings = load_rulings(geometry_db)
    if rulings:
        print(f"ruled grids known for {len(rulings):,} documents", flush=True)
    if geometry:
        rotate = sum(1 for decision, _ in geometry.values() if decision == "ROTATE")
        print(
            f"page geometry known for {len(geometry):,} documents, {rotate:,} of them ROTATE",
            flush=True,
        )
    else:
        # Said out loud: an identity frame everywhere is a valid way to run,
        # but it must never pass for a run that used the geometry. A stale
        # version or a wrong file looks identical from the facts alone.
        print(
            f"no page geometry for {GEOMETRY_VERSION} at {geometry_db}; "
            "every page keeps the identity frame",
            flush=True,
        )
    print(
        "loci this laboratory does not test: "
        + ", ".join(
            f"{fam or '(no family)'}/{loc}" for fam, loc in testing_policy.not_tested_pairs()
        ),
        flush=True,
    )
    caption_roles = load_caption_roles(source_db)
    if caption_roles:
        print(f"caption role claims available: {len(caption_roles):,}", flush=True)
    caption_abo = load_caption_abo(source_db)
    if caption_abo:
        print(
            f"caption blood-group claims available: {len(caption_abo):,} "
            "(used only to corroborate a ruled-row rescue)",
            flush=True,
        )
    con = connect(out)
    done = {
        r[0]
        for r in con.execute(
            "SELECT sha256 FROM document WHERE extraction_version=?", (EXTRACTION_VERSION,)
        )
    }
    print(f"loading Persian geometry from {persian_db.name} ...", flush=True)
    persian = persian_boxes(persian_db)
    prototypes, prefixed = load_families(families_db)
    print(
        f"printed forms known: {len(prototypes)} ({len(prefixed)} print the locus on values)",
        flush=True,
    )
    work = [d for d in read_corpus(src) if d.sha256 not in done]
    if limit:
        work = work[:limit]
    print(f"documents to extract: {len(work):,}  (already done {len(done):,})", flush=True)
    if not work:
        print("nothing to do")
        return 0

    started = time.perf_counter()
    facts: list[tuple] = []
    documents: list[tuple] = []
    tally: Counter[str] = Counter()

    for index, document in enumerate(work, 1):
        now = datetime.now(UTC).isoformat(timespec="seconds")
        frame = frame_for(document, geometry)
        row_slope, column_slope = slopes_for(document, rulings, frame)
        rows, summary = extract(
            document,
            persian.get(document.sha256, []),
            vocabulary,
            now,
            prototypes,
            prefixed,
            caption_roles.get(document.sha256, Role.UNKNOWN),
            testing_policy,
            frame,
            lattice_for(document, rulings, frame),
            row_slope,
            column_slope,
            lattice_for(document, rulings, None),
            caption_abo.get(document.sha256),
        )
        facts.extend(rows)
        documents.append(
            (
                document.sha256,
                EXTRACTION_VERSION,
                summary["rel_path"],
                summary["quality_band"],
                summary["family"],
                summary["comparison_sheet"],
                summary["consistency"],
                summary["consistency_reason"],
                summary["n_facts"],
                now,
                summary["tilt_deg"],
                summary["frame"],
                summary["loci_sharing_a_row"],
                summary["loci_sharing_a_column"],
                summary["values_along_the_row"],
                summary["values_under_the_label"],
                summary["dropped_label"],
            )
        )
        tally["frame_rotate"] += summary["frame"] == "ROTATE"
        for row in rows:
            tally[row[3]] += 1
        tally["comparison_sheets"] += summary["comparison_sheet"]
        tally["family_rule" if summary["family"] else "default_rule"] += 1

        if len(documents) >= batch or index == len(work):
            # Named columns, not positional: `decode_pass.py` adds `stability`
            # to this table, and a positional insert breaks the moment it has.
            # Leaving `stability` out is also the correct behaviour — a
            # re-extracted fact has not been checked for stability, and its
            # NOT_CHECKED default is what keeps it out of Gold until it is.
            con.executemany(
                f"INSERT OR REPLACE INTO fact ({FACT_COLUMNS}) VALUES "
                f"({','.join('?' * len(FACT_COLUMNS.split(',')))})",
                facts,
            )
            con.executemany(
                "INSERT OR REPLACE INTO document (sha256, extraction_version, rel_path, "
                "quality_band, family, comparison_sheet, consistency, consistency_reason, "
                "n_facts, created_utc, tilt_deg, frame, loci_sharing_a_row, "
                "loci_sharing_a_column, values_along_the_row, values_under_the_label, "
                "dropped_label) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                documents,
            )
            con.commit()
            facts.clear()
            documents.clear()
            elapsed = time.perf_counter() - started
            rate = index / elapsed
            print(
                f"  {index:>7,}/{len(work):,}  {rate:6.1f} doc/s  "
                f"eta {(len(work) - index) / rate / 60:5.1f} min",
                flush=True,
            )

    con.close()
    print("\nfacts by status:")
    for status in ("RESOLVED", "REVIEW_REQUIRED", "UNKNOWN", "CONFLICT"):
        if tally[status]:
            print(f"  {status:<18}{tally[status]:>9,}")
    print(f"  comparison sheets {tally['comparison_sheets']:>9,}")
    print(f"  by family rule    {tally['family_rule']:>9,}")
    print(f"  by default rule   {tally['default_rule']:>9,}")
    resolved = out.resolve()
    shown = resolved.relative_to(ROOT) if resolved.is_relative_to(ROOT) else resolved
    print(f"written to {shown}")
    return 0


def status(out: Path) -> int:
    if not out.exists():
        print("no facts database yet")
        return 0
    con = connect(out)
    documents = con.execute(
        "SELECT COUNT(*) FROM document WHERE extraction_version=?", (EXTRACTION_VERSION,)
    ).fetchone()[0]
    print(f"documents : {documents:,}")
    print("\nfacts by field and status:")
    for field, state, count in con.execute(
        "SELECT field, status, COUNT(*) FROM fact WHERE extraction_version=? "
        "GROUP BY field, status ORDER BY field, status",
        (EXTRACTION_VERSION,),
    ):
        print(f"  {field:<8}{state:<18}{count:>8,}")
    con.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, default=ROOT / "data/derived/ocr_pass.sqlite")
    parser.add_argument("--persian", type=Path, default=ROOT / "data/derived/persian_pass.sqlite")
    parser.add_argument(
        "--families", type=Path, default=ROOT / "data/derived/template_families.json"
    )
    parser.add_argument("--out", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--status", action="store_true")
    parser.add_argument(
        "--source",
        type=Path,
        default=ROOT / "data/derived/source.sqlite",
        help="the source store, for caption role evidence; skipped when absent",
    )
    parser.add_argument(
        "--geometry",
        type=Path,
        default=ROOT / "data/derived/geometry.sqlite",
        help="page geometry from scripts/geometry_pass.py; identity frames when absent",
    )
    args = parser.parse_args()
    if args.status:
        return status(args.out)
    if not args.src.exists():
        print(f"missing {args.src}; run scripts/ocr_pass.py first")
        return 2
    return run(
        args.src,
        args.persian,
        args.families,
        args.out,
        args.limit,
        args.batch_size,
        args.source,
        args.geometry,
    )


if __name__ == "__main__":
    raise SystemExit(main())
