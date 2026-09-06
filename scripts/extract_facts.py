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

from kidneymatch.documents.abo import (  # noqa: E402
    AboStatus,
    read_abo,
    reconcile_abo,
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
from kidneymatch.ocr.drbx import GeneCall, resolve_grouped_drbx  # noqa: E402
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
from kidneymatch.ocr.rows import row_slope as measure_row_slope  # noqa: E402
from kidneymatch.ocr.rulings import GEOMETRY_VERSION  # noqa: E402
from kidneymatch.ocr.store import read_corpus  # noqa: E402
from kidneymatch.ocr.templates import (  # noqa: E402
    LayoutPrototype,
    assign_prototype,
    constant_label_positions,
    fit_similarity,
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
BELOW_RULE = ValueRule(direction="below", align_overlap=0.3, max_gap=3.0, max_values=2)

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
    for name, ddl in (("tilt_deg", "REAL"), ("frame", "TEXT")):
        if name not in columns:
            con.execute(f"ALTER TABLE document ADD COLUMN {name} {ddl}")
    con.commit()
    return con


def load_geometry(path: Path | None) -> dict[str, tuple[str, float]]:
    """Per-document page geometry from `scripts/geometry_pass.py`: (decision, theta).

    Absent, the identity frame applies everywhere, which is the pipeline of
    today. Only a ROTATE decision — two estimators agreeing — moves anything.
    """
    if path is None or not path.exists():
        return {}
    con = sqlite3.connect(path)
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


def load_rulings(path: Path | None) -> dict[str, tuple[int, int, str, str]]:
    """The stored rulings of every page under this geometry version (see `ocr.lattice`)."""
    return load_stored_rulings(path, GEOMETRY_VERSION)


def lattice_for(
    document, rulings: dict[str, tuple[int, int, str, str]], frame: PageFrame | None
) -> Lattice | None:
    return build_lattice(document.sha256, rulings, frame)


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


def persian_boxes(db: Path) -> dict[str, list[Box]]:
    """Persian-pass geometry, keyed by image, thumbnails excluded."""
    if not db.exists():
        return {}
    con = sqlite3.connect(db)
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
) -> tuple[list[tuple], dict]:
    """Every fact this document yields. Pure: no I/O, so it is testable."""
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
    assignment = assign_prototype(latin_level, prototypes or [])
    family = assignment.prototype_id if assignment else None
    rule = (
        FAMILY_RULE
        if family is not None and family in (prefixed_families or set())
        else DEFAULT_RULE
    )
    rule_id = f"family/{family}" if rule is FAMILY_RULE else "ADR0008/default-row-rule"
    # The rows of this page, along the slope this page prints them at. On a
    # level page, or one whose rulings could not be measured, this is the rule
    # unchanged.
    if row_slope:
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

    results = resolve_document(latin_level, rule, vocabulary=vocabulary)
    lattice_bound: set[str] = set()
    if lattice is not None:
        prototype = next((p for p in prototypes or [] if p.prototype_id == family), None)
        results, lattice_bound = bind_in_lattice(
            latin_level, results, rule, lattice, prototype, vocabulary, level, back
        )
    loci = {locus: restore(result, back) for locus, result in results.items()}
    for locus, result in loci.items():
        status = result.status
        reason = result.reason
        if (
            testing_policy is not None
            and status is ResolutionStatus.REVIEW_REQUIRED
            and (result.reason or "").startswith("anchor found but no box")
            and testing_policy.is_not_tested(family, locus)
        ):
            # HA-009: the form prints this row, the cell is empty, and this
            # laboratory measurably never fills it. That is a finding, and
            # sending it to a reviewer wastes the one resource this project is
            # short of. Only an EMPTY cell is reclassified; a resolved one keeps
            # its value.
            status = ResolutionStatus.NOT_TESTED
            reason = testing_policy.reason(family, locus)
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

    genes = {
        gene: restore_drbx(fact, back) for gene, fact in resolve_grouped_drbx(latin_level).items()
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
            anchor_box=_box(fact.header_box),
            # Every box on the row that named this gene, not only the first:
            # a row can print one gene twice, and the second box is what a
            # re-read pass needs to count the second haplotype slot.
            value_boxes=_boxes(list(fact.gene_boxes) or ([fact.gene_box] if fact.gene_box else [])),
        )

    reading = read_form_role(persian, latin)
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

    abo_reading = read_abo(persian, latin)
    abo_decision = reconcile_abo(abo_reading)
    add(
        "ABO",
        abo_decision.status.value,
        value=abo_decision.group,
        raw=abo_reading.raw_value,
        repaired=abo_reading.repaired,
        reason=abo_decision.reason or abo_reading.reason,
        rule_id="abo/anchored-cell",
        source=abo_decision.source.value,
        anchor_box=_box(abo_reading.anchor_box),
        value_boxes=_boxes([abo_reading.value_box] if abo_reading.value_box else []),
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
        rule_id="abo/anchored-cell",
        source=abo_decision.source.value,
    )

    drb1 = loci.get("DRB1")
    consistency = ConsistencyOutcome.NOT_CHECKABLE
    consistency_reason = "the DRB1 row or the DRB3/4/5 row was not read"
    if drb1 is not None and drb1.status is ResolutionStatus.RESOLVED:
        present = {g for g, f in genes.items() if f.call is GeneCall.PRESENT}
        absent = {g for g, f in genes.items() if f.call is GeneCall.ABSENT}
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
            row_slope_for(document, rulings, frame),
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
                "n_facts, created_utc, tilt_deg, frame) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
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
