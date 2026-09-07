#!/usr/bin/env python3
"""Re-read the pages whose layout answer changed, without re-extracting the corpus.

Four findings about the 11,210 documents that carry no layout family are
implemented in `ocr/templates.py` and `extract_facts.py`, and all four only
take effect when a document is extracted. A full re-extraction is a multi-hour
run that also resets every later pass, and `docs/agent-memory/CURRENT.md`
records that as the commonest way this pipeline loses cells. So this pass
applies the four findings to the pages they change, and to nothing else:

* **`family-tie`** — the page fits one form inside `MAX_RESIDUAL` and was
  refused only because a second prototype of the SAME form, leaning
  differently, fitted nearly as well (965 pages here, 550 cells).
* **`family-prefix`** — the recognizer boxed a label's `HLA-` apart from the
  label; joined back into the word the form prints, the page fits at the
  ORDINARY tolerance and is read from the repaired boxes (162 pages, 204
  cells).
* **`family-loo`** — the residue: the stack fits except at one label and no
  fragment on the page explains it, so the fit without that label carries the
  form's rule (209 pages, 258 cells).
* **`below-rule`** — the page's locus labels are column HEADERS and each value
  sits in the cell beneath its own label (290 pages, 364 cells).

Measured against the live stores on 2026-09-07, read-only: 1,376 cells over
1,626 pages, no locus losing a resolved cell.

### What it will not touch

* A cell that is RESOLVED. This pass adds readings; it never revises one.
* A cell any later pass wrote (`source` is not null). Those passes ran on the
  refusal this rule may now remove, and deciding between them is not this
  pass's business — the withdrawal path is, and every fact written here
  carries a `source` of its own so its group can be found and withdrawn whole.
* A page that prints two subjects. The comparison-sheet guard FAILS CLOSED:
  a query that cannot run stops the pass, because an empty set is
  indistinguishable from a corpus with no comparison sheets in it, and there
  are 450.
* A page whose values name no locus under the family rule. That is the
  fallback `extract_facts.extract` implements, and it yields the DEFAULT rule
  the page already ran under, so there is nothing here to add.

### What it leaves behind (KI-028, printed on every run)

* The 1,336 documents it reads under a family rule keep `document.family`
  NULL, so `build_testing_policy.py` counts their 1,012 resolutions in its
  `(no family)` bucket. Safe direction, measured on a fiction.
* 68 DPA1/DPB1 cells go on saying NOT_TESTED where a re-extraction would say
  REVIEW_REQUIRED, because `candidates` may not touch a cell another finding
  made.

Every fact records the boxes it was read from, so the review page can crop
them; a RESOLVED medical value with no crop is the defect that made 50 of one
labelling round's 220 answers unusable.

`--dry-run` is the default. The facts database is opened READ-ONLY unless
`--no-dry-run` is given.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from extract_facts import (  # noqa: E402
    BELOW_RULE,
    COLUMN_REASON,
    FAMILY_RULE,
    NAMES_NO_LOCUS,
    bind_in_lattice,
    frame_for,
    lattice_for,
    load_families,
    load_geometry,
    load_rulings,
    persian_boxes,
    slopes_for,
)
from page_ocr_bind import Document  # noqa: E402
from prefix_bind import page_boxes  # noqa: E402

from kidneymatch.documents.role import read_form_role  # noqa: E402
from kidneymatch.hla.vocabulary import load_vocabulary  # noqa: E402
from kidneymatch.ocr.anchors import Box as OcrBox  # noqa: E402
from kidneymatch.ocr.anchors import (  # noqa: E402
    LocusResolution,
    ResolutionStatus,
    ValueRule,
    resolve_document,
)
from kidneymatch.ocr.geometry import restore  # noqa: E402
from kidneymatch.ocr.layout import reading_direction  # noqa: E402
from kidneymatch.ocr.templates import (  # noqa: E402
    assign_prototype,
    merge_prefix_fragments,
)

EV = "facts/v1"
LOCI = ("A", "B", "C", "DRB1", "DQA1", "DQB1", "DPA1", "DPB1")

# One source per proposal, so each group can be counted, reviewed and withdrawn
# on its own evidence. A single "family-repass" would make three separate
# claims indistinguishable.
TIE = "family-tie"
LOO = "family-loo"
BELOW = "below-rule"
PREFIX = "family-prefix"

REASONS = {
    TIE: (
        "the page fits this form within the template tolerance; a second prototype of the same "
        "form under a different lean fitted as well, which is a lean and not two layouts, so the "
        "form's own cell rule was applied"
    ),
    LOO: (
        "the page's printed label stack fits this form except at one label, whose HLA- prefix the "
        "recognizer boxed apart; the fit without that label is inside half the template tolerance "
        "and the form's own cell rule was applied"
    ),
    BELOW: COLUMN_REASON,
    PREFIX: (
        "the recognizer boxed one or more labels' HLA- prefix apart from the label; joined back "
        "into the word the form prints, the page's stack fits this form at the ordinary template "
        "tolerance, and the form's own cell rule was applied to the repaired boxes"
    ),
}


def resolved_per_locus(con: sqlite3.Connection) -> dict[str, int]:
    """RESOLVED cells per HLA locus, right now. The snapshot half of the
    comparison `refresh_facts.py` makes mandatory.

    `docs/agent-memory/CURRENT.md`: ALWAYS compare per locus, because the
    totals looked plausible on the day the letterhead's `LAB` became an HLA-B
    anchor and only the per-locus fall showed it. A pass that writes cells is
    under the same obligation as a re-extraction, and this pass writes 1,376.
    """
    placeholders = ",".join("?" * len(LOCI))
    return {
        field: count
        for field, count in con.execute(
            f"SELECT field, COUNT(*) FROM fact WHERE extraction_version=? AND status='RESOLVED' "
            f"AND field IN ({placeholders}) GROUP BY field",
            (EV, *LOCI),
        )
    }


def not_tested_cells(con: sqlite3.Connection) -> dict[str, set[str]]:
    """Loci already recorded as NOT_TESTED, per page with no layout family.

    Recorded rather than changed, and counted so the record is checkable.
    `extract_facts.extract` calls a cell NOT_TESTED only when the rule left it
    EMPTY and the family's testing policy says this laboratory never fills it.
    A page that gains a family gains a rule that reads it, so the cell is no
    longer empty under that rule and a re-extraction moves it NOT_TESTED ->
    REVIEW_REQUIRED. This pass cannot: `candidates` selects only UNKNOWN and
    REVIEW_REQUIRED, and widening it would let a repass overwrite a finding it
    did not make. So after this pass the corpus is in a state no single build
    produces, and those cells go on saying "this laboratory does not perform
    this test" about pages the new build reads a family on.
    """
    out: dict[str, set[str]] = defaultdict(set)
    placeholders = ",".join("?" * len(LOCI))
    for sha, field in con.execute(
        "SELECT f.sha256, f.field FROM fact f JOIN document d "
        "  ON d.sha256 = f.sha256 AND d.extraction_version = f.extraction_version "
        f"WHERE f.extraction_version=? AND f.field IN ({placeholders}) "
        "  AND f.status='NOT_TESTED' AND d.family IS NULL",
        (EV, *LOCI),
    ):
        out[sha].add(field)
    return dict(out)


def candidates(con: sqlite3.Connection) -> dict[str, list[str]]:
    """Loci still unread, on documents that carry no layout family.

    A cell any later pass wrote is left alone: those passes answered the
    refusal this rule may now remove, and this pass must not overwrite an
    answer it cannot compare itself against.
    """
    placeholders = ",".join("?" * len(LOCI))
    out: dict[str, list[str]] = defaultdict(list)
    for sha, field in con.execute(
        "SELECT f.sha256, f.field FROM fact f JOIN document d "
        "  ON d.sha256 = f.sha256 AND d.extraction_version = f.extraction_version "
        f"WHERE f.extraction_version=? AND f.field IN ({placeholders}) "
        "  AND f.status IN ('UNKNOWN','REVIEW_REQUIRED') AND (f.source IS NULL OR f.source='') "
        "  AND d.family IS NULL",
        (EV, *LOCI),
    ):
        out[sha].append(field)
    return dict(out)


def comparison_sheets(con: sqlite3.Connection) -> set[str]:
    """Pages holding two people. Raises rather than returning an empty set.

    The only thing standing between this pass and binding the right gene of
    the WRONG PERSON, so it must not fail open — and a query that RUNS and
    matches nothing fails open exactly as loudly as one that cannot run at
    all, which is to say silently. A missing table raises `OperationalError`
    on its own; an extraction that has not yet written `comparison_sheet`, or
    one at a different version, returns the empty set, and 450 two-subject
    sheets would then be read as one person's page each. So emptiness is an
    error here, not an answer.
    """
    found = {
        row[0]
        for row in con.execute(
            "SELECT sha256 FROM document WHERE extraction_version=? AND comparison_sheet=1",
            (EV,),
        )
    }
    if not found:
        raise SystemExit(
            f"no document at extraction_version {EV} is marked comparison_sheet=1. "
            "This corpus has 450 pages that print two people; an empty guard means the "
            "extraction that filled this database did not write the column, not that the "
            "pages are absent. Refusing to read any page rather than read one person's "
            "gene off another person's row."
        )
    return found


def rule_for_page(
    boxes,
    persian,
    latin,
    prototypes,
    prefixed,
    row_slope: float,
    column_slope: float,
    lattice=None,
) -> tuple[str, ValueRule, str, object, list, dict[int, tuple[OcrBox, OcrBox]]] | None:
    """Which of the four findings applies to this page, the rule it brings, the
    boxes to read it from, and what each REPAIRED box was made of.

    `None` when none of them does — which is the answer for the overwhelming
    majority of pages with no family, and the answer this pass must give
    whenever it is not sure.

    The last element is `merge_prefix_fragments`'s own source map, and it is
    returned rather than re-derived because it is keyed by `id()`. A second
    call builds a second set of joined boxes, and the ids it hands back belong
    to objects nobody kept — so they match nothing the page is read from, and
    CPython is free to hand one of those addresses to a live box later. The
    boxes are therefore built ONCE, here, and the map travels with them.
    """
    rule_of = {
        proto.prototype_id: ("family" if proto.prototype_id in prefixed else "default")
        for proto in prototypes
    }
    assignment = assign_prototype(boxes, prototypes, rule_of=rule_of, leave_one_out=True)
    if assignment is not None:
        if assignment.prototype_id not in prefixed:
            return None  # a form with no authored rule reads no differently
        rule = FAMILY_RULE
        if row_slope:
            rule = replace(rule, row_slope=row_slope)
        rule_id = f"family/{assignment.prototype_id}"
        read_from = boxes
        merged_sources: dict[int, tuple[OcrBox, OcrBox]] = {}
        if assignment.merged_prefixes:
            # Read the page from the repaired boxes, as `extract_facts.extract`
            # does: a label whose prefix was boxed apart hands its own value to
            # the next locus down under the ownership gate, so joining the two
            # halves is part of the finding and not only of the fit.
            read_from, _, merged_sources = merge_prefix_fragments(boxes)
            rule_id += f"(prefix:{','.join(assignment.merged_prefixes)})"
        if assignment.tied_with:
            rule_id += f"(tie:{','.join(assignment.tied_with)})"
        if assignment.dropped_label:
            rule_id += f"(loo:{assignment.dropped_label})"
        if assignment.dropped_label:
            return LOO, rule, rule_id, assignment, read_from, merged_sources
        if assignment.tied_with:
            return TIE, rule, rule_id, assignment, read_from, merged_sources
        if assignment.merged_prefixes:
            return PREFIX, rule, rule_id, assignment, read_from, merged_sources
        # It fits outright, with no accommodation — so the page was already
        # being assigned before this change and the stored `family IS NULL`
        # comes from a different families file or an older extraction. That is
        # a re-extraction's business, not a finding of this pass.
        return None

    layout = reading_direction(boxes, row_slope, column_slope)
    if layout.direction != "below":
        return None
    if len({token.role for token in read_form_role(persian, latin).tokens}) > 1:
        # A header row over two subject rows looks exactly like a column form.
        return None
    return (
        BELOW,
        replace(
            BELOW_RULE,
            row_slope=row_slope,
            column_slope=column_slope,
            # The page's own rulings: a ruling between two values stacked under
            # one header is the form saying they are different rows, which is
            # the only thing that separates one person's pair from two people's.
            row_rulings=lattice.horizontal if lattice is not None else (),
        ),
        "ADR0008/below-rule",
        None,
        boxes,
        {},
    )


def read(boxes, rule: ValueRule, lattice, prototypes, assignment, vocabulary, frame, back):
    """The page's loci under this rule, with the lattice where it applies.

    `frame` and `back` are threaded into `bind_in_lattice` for the same reason
    `extract_facts.extract` threads them: a label the template places is drawn
    on the LEVELLED page, and provenance must name the box as STORED or the
    review page crops the wrong part of a rotated photograph.
    """
    results = resolve_document(boxes, rule, vocabulary=vocabulary)
    if any(NAMES_NO_LOCUS in (r.reason or "") for r in results.values()):
        # `extract_facts.extract` sends this page back to the default rule
        # whole, and the default rule is what it already ran under.
        return None
    if lattice is not None and assignment is not None:
        prototype = next((p for p in prototypes if p.prototype_id == assignment.prototype_id), None)
        results, _ = bind_in_lattice(
            boxes, results, rule, lattice, prototype, vocabulary, frame, back
        )
    return results


def run(
    facts: Path,
    ocr_db: Path,
    geometry_db: Path,
    persian_db: Path,
    families_db: Path,
    *,
    dry_run: bool,
    limit: int | None = None,
) -> Counter[str]:
    vocabulary = load_vocabulary()
    prototypes, prefixed = load_families(families_db)
    if not prototypes:
        raise SystemExit(f"no printed forms at {families_db}; nothing to re-assign")
    con = (
        sqlite3.connect(f"file:{facts.as_posix()}?mode=ro", uri=True)
        if dry_run
        else sqlite3.connect(facts)
    )
    ocr = sqlite3.connect(f"file:{ocr_db.as_posix()}?mode=ro", uri=True)
    # The geometry store is only ever read here, and a pass whose contract is
    # that it changes nothing should not hold a writable handle on it.
    geometry = load_geometry(geometry_db, read_only=True)
    rulings = load_rulings(geometry_db, read_only=True)
    persian = persian_boxes(persian_db, read_only=True)
    sheets = comparison_sheets(con)
    work = candidates(con)
    before_per_locus = resolved_per_locus(con)
    untested = not_tested_cells(con)
    tally: Counter[str] = Counter()
    tally["pages with no family and an unread cell"] = len(work)
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())

    for index, (sha, loci) in enumerate(sorted(work.items()), 1):
        if limit is not None and index > limit:
            break
        if sha in sheets:
            tally["comparison sheet; a rule cannot say whose value it is"] += 1
            continue
        latin, width, height = page_boxes(ocr, sha)
        if not latin:
            continue
        document = Document(sha, width, height)
        frame = frame_for(document, geometry)
        row_slope, column_slope = slopes_for(document, rulings, frame)
        level = frame
        boxes, back = (latin, {}) if level is None else level.rectify(latin)
        lattice = lattice_for(document, rulings, frame)
        chosen = rule_for_page(
            boxes,
            persian.get(sha, []),
            latin,
            prototypes,
            prefixed,
            row_slope,
            column_slope,
            lattice,
        )
        if chosen is None:
            tally["no finding applies to this page"] += 1
            continue
        source, rule, rule_id, assignment, read_from, merged_sources = chosen
        if merged_sources:
            # A joined label box is not in the way back; give it one, or a
            # rotated page's crop would name a box in the levelled frame. The
            # map comes from the SAME call that built `read_from`: keyed by
            # `id()`, it is only meaningful for boxes that are still alive, and
            # a second `merge_prefix_fragments` call would key it on objects
            # that are garbage before the loop starts.
            for merged_id, (label_box, fragment) in merged_sources.items():
                first = back.get(id(label_box), label_box)
                second = back.get(id(fragment), fragment)
                back[merged_id] = OcrBox(
                    min(first.x0, second.x0),
                    min(first.y0, second.y0),
                    max(first.x1, second.x1),
                    max(first.y1, second.y1),
                    first.text,
                )
        results = read(
            read_from,
            rule,
            lattice,
            prototypes,
            assignment,
            vocabulary,
            frame,
            back,
        )
        if results is None:
            tally["values name no locus; the page keeps the default rule"] += 1
            continue
        tally[f"pages this finding reads: {source}"] += 1
        for locus in sorted(untested.get(sha, ())):
            # What a re-extraction would do to a cell this pass must leave
            # alone: under the rule that now reads the page, the cell is no
            # longer the empty one the NOT_TESTED finding was made about.
            settled = results.get(locus)
            if settled is not None and not (settled.reason or "").startswith(
                "anchor found but no box"
            ):
                tally[
                    "-- cells a re-extraction moves NOT_TESTED -> REVIEW that this pass cannot"
                ] += 1
        for locus in sorted(loci):
            result: LocusResolution | None = results.get(locus)
            if result is None or result.status is not ResolutionStatus.RESOLVED:
                continue
            result = restore(result, back)
            reason = REASONS[source] + (f"; {result.reason}" if result.reason else "")
            tally[f"{source}: {locus}"] += 1
            tally[f"cells {source} would resolve" if dry_run else f"cells {source} resolved"] += 1
            if dry_run:
                continue
            con.execute(
                "UPDATE fact SET status='RESOLVED', value=?, raw=?, repaired=?, "
                "second_allele=?, reason=?, rule_id=?, anchor_box=?, value_boxes=?, "
                "source=?, created_utc=? "
                "WHERE sha256=? AND field=? AND extraction_version=? "
                "  AND status IN ('UNKNOWN','REVIEW_REQUIRED') AND (source IS NULL OR source='')",
                (
                    " ".join(result.values),
                    " ".join(v.raw for v in result.parsed_values) or None,
                    int(result.repaired),
                    result.second_allele.value,
                    reason,
                    rule_id,
                    json.dumps(
                        [
                            result.anchor_box.x0,
                            result.anchor_box.y0,
                            result.anchor_box.x1,
                            result.anchor_box.y1,
                        ]
                    )
                    if result.anchor_box
                    else None,
                    json.dumps([[b.x0, b.y0, b.x1, b.y1] for b in result.value_boxes]) or None,
                    source,
                    now,
                    sha,
                    locus,
                    EV,
                ),
            )
        if not dry_run:
            con.commit()
    # The per-locus comparison against the snapshot, which `refresh_facts.py`
    # makes a condition of any pass that changes cells. In a dry run the after
    # column is the projection this run just counted; with --no-dry-run it is
    # re-read from the database, so the printed number is the one stored.
    after_per_locus = dict(before_per_locus) if dry_run else resolved_per_locus(con)
    if dry_run:
        for key, count in tally.items():
            source, _, locus = key.partition(": ")
            if source in REASONS and locus in LOCI:
                after_per_locus[locus] = after_per_locus.get(locus, 0) + count
    tally["-- documents this pass leaves with document.family NULL"] = sum(
        count for key, count in tally.items() if key.startswith("pages this finding reads: family-")
    )
    con.close()
    ocr.close()
    return tally, before_per_locus, after_per_locus


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--ocr", type=Path, default=ROOT / "data/derived/ocr_pass.sqlite")
    parser.add_argument("--geometry", type=Path, default=ROOT / "data/derived/geometry.sqlite")
    parser.add_argument("--persian", type=Path, default=ROOT / "data/derived/persian_pass.sqlite")
    parser.add_argument(
        "--families", type=Path, default=ROOT / "data/derived/template_families.json"
    )
    parser.add_argument("--limit", type=int, default=None, help="stop after this many pages")
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="count and change nothing (the default); --no-dry-run writes the facts",
    )
    args = parser.parse_args()
    tally, before_per_locus, after_per_locus = run(
        args.facts,
        args.ocr,
        args.geometry,
        args.persian,
        args.families,
        dry_run=args.dry_run,
        limit=args.limit,
    )
    print("re-read the pages whose layout answer changed")
    for name, count in sorted(tally.items()):
        if count:
            print(f"  {name:<62}{count:>8,}")
    print("\nper locus, RESOLVED before -> after (the comparison refresh_facts.py requires):")
    falling = []
    for locus in LOCI:
        before, after = before_per_locus.get(locus, 0), after_per_locus.get(locus, 0)
        if before or after:
            print(f"  {locus:<6}{before:>9,} -> {after:>9,}   {after - before:+,}")
        if after < before:
            falling.append(locus)
    if falling:
        print(f"  STOP SIGNAL: resolved cells FELL on {', '.join(falling)}")
    else:
        print("  no locus loses a resolved cell; this pass only adds")
    print(
        "\nEach finding writes its own source (family-tie / family-loo / family-prefix / "
        "below-rule) so its group can be reviewed and withdrawn whole."
    )
    print(
        "Two states this pass leaves behind, counted above and not fixed here: the documents "
        "it reads under a family rule keep document.family NULL, so build_testing_policy.py "
        "counts their resolutions in its '(no family)' bucket; and DPA1/DPB1 cells that a "
        "re-extraction would move NOT_TESTED -> REVIEW_REQUIRED stay NOT_TESTED."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
