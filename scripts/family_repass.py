#!/usr/bin/env python3
"""Re-read the pages whose layout answer changed, without re-extracting the corpus.

Three findings about the 11,210 documents that carry no layout family are
implemented in `ocr/templates.py` and `extract_facts.py`, and all three only
take effect when a document is extracted. A full re-extraction is a multi-hour
run that also resets every later pass, and `docs/agent-memory/CURRENT.md`
records that as the commonest way this pipeline loses cells. So this pass
applies the three findings to the pages they change, and to nothing else:

* **`family-tie`** — the page fits one form inside `MAX_RESIDUAL` and was
  refused only because a second prototype of the SAME form, leaning
  differently, fitted nearly as well (987 pages).
* **`family-loo`** — the page's printed stack fits except at one label, whose
  `HLA-` prefix the recognizer boxed apart (318 pages, of which the far bucket
  is refused by the label-column gate).
* **`below-rule`** — the page's locus labels are column HEADERS and each value
  sits in the cell beneath its own label (305 pages).

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
from kidneymatch.ocr.anchors import (  # noqa: E402
    LocusResolution,
    ResolutionStatus,
    ValueRule,
    resolve_document,
)
from kidneymatch.ocr.geometry import restore  # noqa: E402
from kidneymatch.ocr.layout import reading_direction  # noqa: E402
from kidneymatch.ocr.templates import assign_prototype  # noqa: E402

EV = "facts/v1"
LOCI = ("A", "B", "C", "DRB1", "DQA1", "DQB1", "DPA1", "DPB1")

# One source per proposal, so each group can be counted, reviewed and withdrawn
# on its own evidence. A single "family-repass" would make three separate
# claims indistinguishable.
TIE = "family-tie"
LOO = "family-loo"
BELOW = "below-rule"

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
}


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
    the WRONG PERSON, so it must not fail open.
    """
    return {
        row[0]
        for row in con.execute(
            "SELECT sha256 FROM document WHERE extraction_version=? AND comparison_sheet=1",
            (EV,),
        )
    }


def rule_for_page(
    boxes,
    persian,
    latin,
    prototypes,
    prefixed,
    row_slope: float,
    column_slope: float,
) -> tuple[str, ValueRule, str, object] | None:
    """Which of the three findings applies to this page, and the rule it brings.

    `None` when none of them does — which is the answer for the overwhelming
    majority of pages with no family, and the answer this pass must give
    whenever it is not sure.
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
        if assignment.tied_with:
            rule_id += f"(tie:{','.join(assignment.tied_with)})"
        if assignment.dropped_label:
            rule_id += f"(loo:{assignment.dropped_label})"
        if assignment.dropped_label:
            return LOO, rule, rule_id, assignment
        if assignment.tied_with:
            return TIE, rule, rule_id, assignment
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
        replace(BELOW_RULE, row_slope=row_slope, column_slope=column_slope),
        "ADR0008/below-rule",
        None,
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
    geometry = load_geometry(geometry_db)
    rulings = load_rulings(geometry_db)
    persian = persian_boxes(persian_db, read_only=True)
    sheets = comparison_sheets(con)
    work = candidates(con)
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
        chosen = rule_for_page(
            boxes,
            persian.get(sha, []),
            latin,
            prototypes,
            prefixed,
            row_slope,
            column_slope,
        )
        if chosen is None:
            tally["no finding applies to this page"] += 1
            continue
        source, rule, rule_id, assignment = chosen
        results = read(
            boxes,
            rule,
            lattice_for(document, rulings, frame),
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
    con.close()
    ocr.close()
    return tally


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
    tally = run(
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
    print(
        "Each finding writes its own source (family-tie / family-loo / below-rule) so its "
        "group can be reviewed and withdrawn whole."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
