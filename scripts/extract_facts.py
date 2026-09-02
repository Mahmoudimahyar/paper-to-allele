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
    decide_document_role,
    is_comparison_sheet,
    read_form_role,
)
from kidneymatch.hla.drbx_consistency import ConsistencyOutcome, check_drb1_drbx  # noqa: E402
from kidneymatch.hla.vocabulary import load_vocabulary  # noqa: E402
from kidneymatch.ocr.anchors import (  # noqa: E402
    Box,
    ResolutionStatus,
    ValueRule,
    resolve_document,
)
from kidneymatch.ocr.drbx import GeneCall, resolve_grouped_drbx  # noqa: E402
from kidneymatch.ocr.store import read_corpus  # noqa: E402

EXTRACTION_VERSION = "facts/v1"

# The default relation (ADR 0008). Per-family rules are authored in the registry
# and will override this; the numbers here must be validated against the golden
# corpus rather than tuned by yield.
DEFAULT_RULE = ValueRule(direction="right", align_overlap=0.2, max_gap=20.0, max_values=2)

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
    return con


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


def extract(document, persian: list[Box], vocabulary, now: str) -> tuple[list[tuple], dict]:
    """Every fact this document yields. Pure: no I/O, so it is testable."""
    latin = document.boxes
    rows: list[tuple] = []
    comparison = is_comparison_sheet(latin)

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

    loci = resolve_document(latin, DEFAULT_RULE, vocabulary=vocabulary)
    for locus, result in loci.items():
        status = result.status
        reason = result.reason
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
            rule_id="ADR0008/default-row-rule",
            anchor_box=_box(result.anchor_box),
            value_boxes=_boxes(result.value_boxes),
        )

    genes = resolve_grouped_drbx(latin)
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
            value_boxes=_boxes([fact.gene_box] if fact.gene_box else []),
        )

    reading = read_form_role(persian, latin)
    decision = decide_document_role(reading)
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
        "quality_band": document.quality_band.value,
        "comparison_sheet": int(comparison),
        "consistency": consistency.value,
        "consistency_reason": consistency_reason,
        "n_facts": sum(1 for r in rows if r[3] == ResolutionStatus.RESOLVED.value),
    }
    return rows, summary


def run(src: Path, persian_db: Path, out: Path, limit: int | None, batch: int) -> int:
    vocabulary = load_vocabulary()
    con = connect(out)
    done = {
        r[0]
        for r in con.execute(
            "SELECT sha256 FROM document WHERE extraction_version=?", (EXTRACTION_VERSION,)
        )
    }
    print(f"loading Persian geometry from {persian_db.name} ...", flush=True)
    persian = persian_boxes(persian_db)
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
        rows, summary = extract(document, persian.get(document.sha256, []), vocabulary, now)
        facts.extend(rows)
        documents.append(
            (
                document.sha256,
                EXTRACTION_VERSION,
                summary["rel_path"],
                summary["quality_band"],
                summary["comparison_sheet"],
                summary["consistency"],
                summary["consistency_reason"],
                summary["n_facts"],
                now,
            )
        )
        for row in rows:
            tally[row[3]] += 1
        tally["comparison_sheets"] += summary["comparison_sheet"]

        if len(documents) >= batch or index == len(work):
            con.executemany(
                "INSERT OR REPLACE INTO fact VALUES (" + ",".join("?" * 17) + ")", facts
            )
            con.executemany("INSERT OR REPLACE INTO document VALUES (?,?,?,?,?,?,?,?,?)", documents)
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
    print(f"written to {out.relative_to(ROOT)}")
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
    parser.add_argument("--out", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if args.status:
        return status(args.out)
    if not args.src.exists():
        print(f"missing {args.src}; run scripts/ocr_pass.py first")
        return 2
    return run(args.src, args.persian, args.out, args.limit, args.batch_size)


if __name__ == "__main__":
    raise SystemExit(main())
