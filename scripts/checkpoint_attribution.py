#!/usr/bin/env python3
"""Which checkpoint failed, for every labelled cell the pipeline got wrong.

The operator's model of the pipeline (2026-09-07) is a chain of checkpoints, and
an extraction error is a failure at the FIRST one that did not hold:

1. **orientation** — the page is upright;
2. **tilt** — the rulings are level;
3. **layout** — the locus label was found (and, for DRB3/4/5, the row header);
4. **cell** — the value rectangle is right: not empty, not too short (one
   allele of two), not too wide (a neighbour's values, two subjects);
5. **recognition** — the characters in the right rectangle were read right;
6. **row grammar** — the DRB3/4/5 row's gene tokens were read;
7. **gate** — a value that was read right was withdrawn by a precision gate;
8. **policy** — NOT_TESTED where the reviewer read a value.

Each non-correct labelled cell (missed / partial / contradicted, by the golden
rule in `review/golden.classify`) is placed at one checkpoint from the fact's
own refusal reason and the page's orientation/geometry records, and the
rectangle is compared with the page's other value rectangles — a box unlike
its siblings is the operator's own suggestion for catching a wrong crop.

Prints COUNTS ONLY: a checkpoint x outcome matrix, the per-locus split of the
largest checkpoints, and page-context rates for failures against all labelled
cells (so an upstream cause that is merely common on every page is not
mistaken for one that is common on failing pages).
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from label_score import EV, load_labels, short_to_sha  # noqa: E402

from kidneymatch.review.golden import CellLabel, Outcome, classify  # noqa: E402

DRBX = ("DRB3", "DRB4", "DRB5")
HLA = ("A", "B", "C", "DRB1", "DQA1", "DQB1", "DPA1", "DPB1")
GEOMETRY_VERSION = "rulings/v3+lsd+sweep"
TILT_DEG = 1.5

CHECKPOINTS = (
    "1 orientation",
    "2 tilt",
    "3 layout: label not found",
    "3 layout: DRB3/4/5 header not read",
    "4 cell: empty (value not detected)",
    "4 cell: too short (one allele of two)",
    "4 cell: too wide / wrong owner",
    "4 cell: two subjects on the page",
    "5 recognition",
    "6 DRB3/4/5 row grammar",
    "7 gate withdrew a value",
    "8 policy (NOT_TESTED)",
    "? unclassified",
)

# Refusal-reason patterns, in the order the checkpoints are tried. A reason
# names the FIRST thing the resolver could not do, which is what we want.
REASON_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("3 layout: label not found", re.compile(r"^no anchor on this document")),
    ("3 layout: DRB3/4/5 header not read", re.compile(r"^no grouped DRB3/4/5 header")),
    ("4 cell: empty (value not detected)", re.compile(r"^anchor found but no box")),
    ("4 cell: empty (value not detected)", re.compile(r"cell rectangle held n")),
    (
        "4 cell: too wide / wrong owner",
        re.compile(
            r"exceeds max_values|another locus owns it|anchors found; cannot decide"
            r"|straddles|stacked under this header"
        ),
    ),
    (
        "4 cell: two subjects on the page",
        re.compile(r"comparison table|two subjects|donor and recipient columns"),
    ),
    (
        "5 recognition",
        re.compile(
            r"does not parse as an allele|is not an allele family|is a locus label, not a value"
            r"|names its locus without a star|names no locus"
        ),
    ),
    (
        "7 gate withdrew a value",
        re.compile(r"^withdrawn to review: this value needed a glyph repair"),
    ),
    (
        "6 DRB3/4/5 row grammar",
        re.compile(
            r"^withdrawn to review: a DRB3/4/5 call|only one gene token read"
            r"|header present but no gene token|rests on an S read as"
            r"|second slot of this row holds ink|gene token"
        ),
    ),
)


def parse_boxes(text: str | None) -> list[tuple[float, float, float, float]]:
    """`[[x0,y0,x1,y1], ...]`, or a single box, or dicts — whatever a pass stored."""
    if not text:
        return []
    try:
        raw = json.loads(text)
    except ValueError:
        return []
    if isinstance(raw, dict):
        raw = [raw]
    if raw and isinstance(raw[0], (int, float)):
        raw = [raw]
    out = []
    for b in raw:
        if isinstance(b, dict):
            keys = ("x0", "y0", "x1", "y1") if "x0" in b else ("left", "top", "right", "bottom")
            try:
                out.append(tuple(float(b[k]) for k in keys))  # type: ignore[misc]
            except (KeyError, TypeError, ValueError):
                continue
        elif isinstance(b, (list, tuple)) and len(b) >= 4:
            try:
                out.append(tuple(float(v) for v in b[:4]))  # type: ignore[misc]
            except (TypeError, ValueError):
                continue
    return out  # type: ignore[return-value]


def checkpoint_for(
    outcome: Outcome,
    status: str,
    reason: str,
    locus: str,
    label_alleles: int,
    value_count: int,
    page: dict,
) -> str:
    """The first checkpoint that failed for one non-correct cell."""
    reason = reason or ""
    # Upstream first: a page the pipeline read sideways or could not level
    # fails every cell on it, whatever the cell's own reason says.
    if page.get("orientation") == "ORIENTATION_SUSPECT":
        return "1 orientation"
    if page.get("tilt_unlevelled"):
        return "2 tilt"
    if status == "NOT_TESTED":
        return "8 policy (NOT_TESTED)"
    if outcome is Outcome.PARTIAL:
        # A value was read and one allele is missing: the rectangle stopped
        # short, or the second box was never detected.
        return "4 cell: too short (one allele of two)"
    if outcome is Outcome.FALSE_ACCEPTANCE:
        return page.get("false_acceptance_kind") or "5 recognition"
    for name, pattern in REASON_RULES:
        if pattern.search(reason):
            return name
    if status == "RESOLVED" and label_alleles == 2 and value_count == 1:
        return "4 cell: too short (one allele of two)"
    if locus in DRBX and status in ("UNKNOWN", "REVIEW_REQUIRED"):
        return "6 DRB3/4/5 row grammar"
    return "? unclassified"


def page_context(
    con: sqlite3.Connection,
    geo: sqlite3.Connection | None,
    upright: sqlite3.Connection | None,
    shas: set[str],
) -> dict[str, dict]:
    ctx: dict[str, dict] = defaultdict(dict)
    for sha, frame, tilt, band, sheet in con.execute(
        f"SELECT sha256, frame, tilt_deg, quality_band, comparison_sheet FROM document "
        f"WHERE extraction_version=? AND sha256 IN ({','.join('?' * len(shas))})",
        (EV, *shas),
    ):
        ctx[sha].update(frame=frame, tilt_deg=tilt, quality_band=band, comparison_sheet=bool(sheet))
    if geo is not None:
        for sha, decision, theta in geo.execute(
            f"SELECT sha256, decision, theta_deg FROM page_geometry WHERE geometry_version=? "
            f"AND sha256 IN ({','.join('?' * len(shas))})",
            (GEOMETRY_VERSION, *shas),
        ):
            ctx[sha].update(geometry=decision, theta=theta)
    if upright is not None:
        for sha, verdict, rotation in upright.execute(
            "SELECT sha256, verdict, rotation FROM upright_result "
            f"WHERE sha256 IN ({','.join('?' * len(shas))})",
            tuple(shas),
        ):
            ctx[sha].update(orientation=verdict, rotation=rotation)
    for sha in shas:
        c = ctx[sha]
        theta = c.get("theta")
        c["tilted"] = theta is not None and abs(theta) >= TILT_DEG
        c["tilt_unlevelled"] = bool(c["tilted"]) and c.get("frame") != "ROTATE"
    return ctx


def rectangle_flags(con: sqlite3.Connection, sha: str) -> dict[str, str]:
    """Per locus on one page: is its value rectangle unlike its siblings'?

    The operator's suggestion: if HLA-A and HLA-B captured both alleles, the
    other loci should have rectangles of about the same size; a big spread says
    something is wrong. Height and width are compared with the page median
    over the RESOLVED loci, using the `boxsize.py` ratios.
    """
    dims: dict[str, tuple[float, float]] = {}
    for locus, boxes_text in con.execute(
        "SELECT field, value_boxes FROM fact WHERE sha256=? AND extraction_version=? AND field IN "
        f"({','.join('?' * len(HLA))}) AND value_boxes IS NOT NULL",
        (sha, EV, *HLA),
    ):
        boxes = parse_boxes(boxes_text)
        if not boxes:
            continue
        x0 = min(b[0] for b in boxes)
        x1 = max(b[2] for b in boxes)
        heights = [b[3] - b[1] for b in boxes]
        dims[locus] = (x1 - x0, median(heights))
    if len(dims) < 3:
        return {}
    med_w = median(w for w, _ in dims.values())
    med_h = median(h for _, h in dims.values())
    flags = {}
    for locus, (w, h) in dims.items():
        if med_h and (h / med_h > 1.6 or h / med_h < 0.6):
            flags[locus] = "height unlike siblings"
        elif med_w and w / med_w < 0.45:
            flags[locus] = "narrow: likely one allele's width"
        elif med_w and w / med_w > 2.2:
            flags[locus] = "wide: likely more than this locus"
        else:
            flags[locus] = "like siblings"
    return flags


def run(exports: list[Path], facts: Path, geometry: Path | None, upright: Path | None) -> int:
    labels, _, _ = load_labels(exports)
    con = sqlite3.connect(f"file:{facts.as_posix()}?mode=ro", uri=True)
    geo = (
        sqlite3.connect(f"file:{geometry.as_posix()}?mode=ro", uri=True)
        if geometry and geometry.exists()
        else None
    )
    upr = (
        sqlite3.connect(f"file:{upright.as_posix()}?mode=ro", uri=True)
        if upright and upright.exists()
        else None
    )
    lookup = short_to_sha(con)

    rows = []
    for cell_id, lab in labels.items():
        head, _, locus = cell_id.rpartition(":")
        sha = lookup.get(head)
        if sha is None or not isinstance(lab, CellLabel):
            continue
        fact = con.execute(
            "SELECT status, value, second_allele, reason FROM fact "
            "WHERE sha256=? AND field=? AND extraction_version=?",
            (sha, locus, EV),
        ).fetchone()
        if fact is None:
            continue
        status, value, second, reason = fact
        label = lab
        values = tuple(part.split("*")[-1] for part in (value or "").split() if part)
        outcome = classify(label, (status, locus, values, second))
        rows.append(
            (
                sha,
                locus,
                label,
                status,
                value,
                reason or "",
                outcome,
                len(label.alleles),
                len(values),
            )
        )

    shas = {r[0] for r in rows}
    ctx = page_context(con, geo, upr, shas)
    rect_cache: dict[str, dict[str, str]] = {}

    # A false acceptance is a wrong owner if the wrong value equals another
    # locus's labelled alleles on the same page; otherwise it is recognition.
    labelled_by_page: dict[str, dict[str, set[str]]] = defaultdict(dict)
    for sha, locus, label, *_ in rows:
        labelled_by_page[sha][locus] = set(label.alleles)

    matrix: Counter = Counter()
    per_locus: dict[str, Counter] = defaultdict(Counter)
    context_fail: Counter = Counter()
    context_all: Counter = Counter()
    rect_fail: Counter = Counter()
    rect_all: Counter = Counter()
    n_fail = 0
    for sha, locus, _label, status, value, reason, outcome, n_lab, n_val in rows:
        page = dict(ctx.get(sha, {}))
        for key in (
            "orientation",
            "tilted",
            "tilt_unlevelled",
            "geometry",
            "comparison_sheet",
            "quality_band",
        ):
            context_all[(key, str(page.get(key)))] += 1
        if locus in HLA:
            flags = rect_cache.setdefault(sha, rectangle_flags(con, sha))
            rect_all[flags.get(locus, "no rectangle")] += 1
        if outcome not in (Outcome.MISSED, Outcome.PARTIAL, Outcome.FALSE_ACCEPTANCE):
            continue
        n_fail += 1
        if outcome is Outcome.FALSE_ACCEPTANCE:
            values = {part.split("*")[-1] for part in (value or "").split()}
            others = {
                a for other, alle in labelled_by_page[sha].items() if other != locus for a in alle
            }
            page["false_acceptance_kind"] = (
                "4 cell: too wide / wrong owner" if values and values <= others else "5 recognition"
            )
        cp = checkpoint_for(outcome, status, reason, locus, n_lab, n_val, page)
        matrix[(cp, outcome.value)] += 1
        per_locus[cp][locus] += 1
        for key in (
            "orientation",
            "tilted",
            "tilt_unlevelled",
            "geometry",
            "comparison_sheet",
            "quality_band",
        ):
            context_fail[(key, str(page.get(key)))] += 1
        if locus in HLA:
            rect_fail[rect_cache[sha].get(locus, "no rectangle")] += 1

    n_all = len(rows)
    print(
        f"{n_all:,} labelled cells scored; {n_fail:,} not correct "
        "(missed / partial / contradicted)\n"
    )
    print(f"{'checkpoint':<42}{'missed':>8}{'partial':>9}{'wrong':>7}{'total':>7}")
    for cp in CHECKPOINTS:
        m, p, w = matrix[(cp, "missed")], matrix[(cp, "partial")], matrix[(cp, "false_acceptance")]
        if m + p + w:
            print(f"{cp:<42}{m:>8}{p:>9}{w:>7}{m + p + w:>7}")
    print("\nper locus, for the checkpoints that carry most of the loss:")
    for cp, counter in sorted(per_locus.items(), key=lambda kv: -sum(kv[1].values()))[:6]:
        print(f"  {cp}: " + ", ".join(f"{loc} {n}" for loc, n in counter.most_common()))
    print("\npage context — share among failing cells vs among all labelled cells:")
    for key in ("orientation", "tilted", "geometry", "comparison_sheet", "quality_band"):
        vals = sorted({v for k, v in context_all if k == key})
        parts = []
        for v in vals:
            f = context_fail[(key, v)]
            a = context_all[(key, v)]
            parts.append(
                f"{v}: {100 * f / max(n_fail, 1):.0f}% of failures"
                f" / {100 * a / max(n_all, 1):.0f}% of all"
            )
        print(f"  {key}: " + " | ".join(parts))
    print("\nvalue rectangle vs the page's other loci (HLA cells only):")
    for flag in (
        "like siblings",
        "narrow: likely one allele's width",
        "wide: likely more than this locus",
        "height unlike siblings",
        "no rectangle",
    ):
        f, a = rect_fail[flag], rect_all[flag]
        if a:
            print(f"  {flag:<36} {f:>4} of {a:>5} cells fail  ({100 * f / a:.0f}%)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "exports", type=Path, nargs="+", help="golden-labels/v1 exports, later rounds win"
    )
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--geometry", type=Path, default=ROOT / "data/derived/geometry.sqlite")
    parser.add_argument("--upright", type=Path, default=ROOT / "data/derived/upright_pass.sqlite")
    args = parser.parse_args()
    return run(args.exports, args.facts, args.geometry, args.upright)


if __name__ == "__main__":
    sys.exit(main())
