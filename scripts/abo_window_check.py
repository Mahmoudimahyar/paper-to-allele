#!/usr/bin/env python3
"""Measure the blood-group cell window against the corpus, and against placebos.

READ-ONLY. Every database is opened `mode=ro` and this script has no write path
at all; `--dry-run` is accepted and is the only behaviour there is.

It answers three questions about `documents/abo.py`'s two rescues (s19 item 1):

**What does the window gain and cost?** The shipped window is rerun with the
rescues switched off — by setting `_MAX_BAND_HEIGHTS` and `_RESCUE_BAND` to 0,
which makes every band implausible and every centre offset out of reach — and
compared page by page against the window as it now stands. Gained, lost and
value-changed are reported per route, because the two routes are not equally
evidenced and only one of them is allowed to lose a document.

**Is the grid in the right frame?** With `--levelled` the lattice is rotated
into the level frame, which is the one integration mistake that silently
changes the answer. The pair is the discriminator: the raw frame is the
acceptance number, the levelled frame is a different number.

**Does the window find values where no value is?** Three placebos, each a way
of asking the same page a question whose answer must be "nothing":

* `--placebo translated` moves every field label 1.0, 1.5, 2.0 and 3.0 label
  heights up and down and reads again. A rule that follows the printed cell
  loses the value; a rule that merely reaches finds one anyway.
* `--placebo decoy` promotes a size-matched NON-label box to be the anchor and
  removes the real label. EVERY size-matched candidate on the page is run, one
  at a time, so the statistic is rescued admissions per candidate — directly
  comparable with rescued admissions per real anchor, which is printed beside
  it. Comparing whole-corpus resolve rates instead would compare two different
  things and did.
* `--placebo direction` reads each cell on the WRONG side of its label. The
  script follows, and a Persian label's value is to its LEFT; read rightwards
  it addresses the next cell, where a rule that locates a printed cell must
  admit nothing.

The gate the fixes ask for, in the words of centre fix 9: translated anchors
and size-matched decoys "must not exceed the shipped counts by more than +2
admissions". That is the REACH — every extra admission, not only the ones whose
value differs — and it is what this gates on; the leak (an extra admission of a
DIFFERENT value than the true read) is gated at the same allowance and reported
beside it, per route, because the two routes do not behave alike. A failing
gate is printed as such and sets a non-zero exit status.

One consequence is structural and is recorded in HA-019 rather than hidden: a
shift SMALLER than `_MAX_BAND_HEIGHTS` (2.0) leaves the label inside its own
printed row, and a rule whose cell IS that row must still find the same cell
there. The +-1.0h reach is therefore not a leak measurement for the band route;
it measures the band cap. The leak column, and every shift at or beyond the
cap, are the parts that carry safety information.

Counts, geometry and refusal classes only. Nothing this prints identifies a
document or repeats what a page says.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from kidneymatch.documents import abo as abo_module  # noqa: E402
from kidneymatch.documents.abo import (  # noqa: E402
    AboRescue,
    AboStatus,
    read_abo,
    reconcile_abo,
)
from kidneymatch.ocr.anchors import Box  # noqa: E402
from kidneymatch.ocr.geometry import PageFrame  # noqa: E402
from kidneymatch.ocr.lattice import Lattice, lattice_for  # noqa: E402
from kidneymatch.ocr.rulings import GEOMETRY_VERSION  # noqa: E402

# Below this the extraction declines to rotate at all (extract_facts.py).
MIN_FRAME_TILT_DEG = 1.5
TRANSLATIONS = (1.0, 1.5, 2.0, 3.0)
DECOY_HEIGHT_TOLERANCE = 0.20
PLACEBO_ALLOWANCE = 2


@dataclass(frozen=True, slots=True)
class Page:
    sha256: str
    persian: list[Box]
    latin: list[Box]
    lattice: Lattice | None


def _boxes(geometry_json: str | None, texts_json: str | None) -> list[Box]:
    geometry = json.loads(geometry_json or "[]")
    texts = json.loads(texts_json or "[]")
    return [Box(b[0], b[1], b[2], b[3], t) for b, t in zip(geometry, texts, strict=False)]


def _readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)


def pages(
    persian_db: Path, ocr_db: Path, geometry_db: Path | None, *, levelled: bool, limit: int
) -> Iterator[Page]:
    """Stream one page at a time: the whole corpus does not fit in memory twice.

    The two OCR passes and the geometry are read in sha order and merged, so
    each page's boxes are parsed, used and dropped.
    """
    persian_con, ocr_con = _readonly(persian_db), _readonly(ocr_db)
    geometry_con = _readonly(geometry_db) if geometry_db and geometry_db.exists() else None
    persian_rows = persian_con.execute(
        "SELECT sha256, boxes_json, texts_json FROM persian_result WHERE n_boxes>0 "
        "ORDER BY sha256, rowid"
    )
    geometry_rows = (
        geometry_con.execute(
            "SELECT sha256, width, height, h_rulings_json, v_rulings_json, decision, theta_deg "
            "FROM page_geometry WHERE geometry_version=? AND h_rulings_json IS NOT NULL "
            "AND width IS NOT NULL ORDER BY sha256",
            (GEOMETRY_VERSION,),
        )
        if geometry_con is not None
        else iter(())
    )
    persian_next = next(persian_rows, None)
    geometry_next = next(geometry_rows, None)
    seen: set[str] = set()
    emitted = 0
    try:
        for sha, rel, b, t in ocr_con.execute(
            "SELECT sha256, rel_path, boxes_json, texts_json FROM ocr_result WHERE n_boxes>0 "
            "ORDER BY sha256, rowid"
        ):
            if "_thumb" in rel or sha in seen:
                continue
            seen.add(sha)
            # The Persian pass may hold several rows for one page; the last one
            # wins, which is what the repass scripts do.
            persian_boxes: list[Box] = []
            while persian_next is not None and persian_next[0] < sha:
                persian_next = next(persian_rows, None)
            while persian_next is not None and persian_next[0] == sha:
                persian_boxes = _boxes(persian_next[1], persian_next[2])
                persian_next = next(persian_rows, None)
            while geometry_next is not None and geometry_next[0] < sha:
                geometry_next = next(geometry_rows, None)
            lattice = None
            if geometry_next is not None and geometry_next[0] == sha:
                _, width, height, h_json, v_json, decision, theta = geometry_next
                frame = (
                    PageFrame(theta_deg=theta, width=int(width), height=int(height))
                    if levelled and decision == "ROTATE" and abs(theta) >= MIN_FRAME_TILT_DEG
                    else None
                )
                lattice = lattice_for(sha, {sha: (int(width), int(height), h_json, v_json)}, frame)
                geometry_next = next(geometry_rows, None)
            yield Page(sha, persian_boxes, _boxes(b, t), lattice)
            emitted += 1
            if limit and emitted >= limit:
                return
    finally:
        persian_con.close()
        ocr_con.close()
        if geometry_con is not None:
            geometry_con.close()


class Window:
    """The window with its rescues switched off, as a context manager.

    Nothing is patched into the product: the two constants that define the
    reaches are set to zero, so no band is ever plausible and no centre offset
    is ever inside the reach. That is the pre-change function exactly.
    """

    def __enter__(self) -> Window:
        self.band = abo_module._MAX_BAND_HEIGHTS
        self.centre = abo_module._RESCUE_BAND
        abo_module._MAX_BAND_HEIGHTS = 0.0
        abo_module._RESCUE_BAND = 0.0
        return self

    def __exit__(self, *_: object) -> None:
        abo_module._MAX_BAND_HEIGHTS = self.band
        abo_module._RESCUE_BAND = self.centre


def _answer(page: Page, *, lattice: Lattice | None) -> tuple:
    """What the reader says, and whether the pipeline would PUBLISH it.

    The last field is the one that decides whether a placebo hit could reach a
    person's record: `reconcile_abo` refuses to publish a ruled-row value boxed
    by one engine, so a placebo admission in that class becomes a review item
    rather than a blood group. No caption is available here, which makes this
    the conservative half of F1 — two engines over the same ink, nothing else.
    """
    reading = read_abo(page.persian, page.latin, lattice=lattice)
    return (
        reading.status,
        reading.group,
        reading.rh,
        reading.rescued,
        reading.reason,
        reconcile_abo(reading).status is AboStatus.RESOLVED,
    )


def _is_anchor(box: Box, latin: list[Box]) -> bool:
    text = (box.text or "").strip()
    return bool(
        abo_module._is_persian_label(box.text)
        or abo_module._LABEL_LATIN.match(text)
        or abo_module._is_group_word_label(box, latin)
    )


def _translated(page: Page, shift: float) -> Page:
    """The FIELD LABEL moved by `shift` of its own height, the page left alone.

    This is the control the rule has to fail: the label now names a place the
    form does not print a blood group, so a window that locates a printed cell
    finds nothing and a window that merely reaches finds whatever is nearby.
    Moving the whole page instead would move the value with the label and
    measure nothing.
    """

    def moved(boxes: list[Box], anchors: list[Box]) -> list[Box]:
        return [
            Box(b.x0, b.y0 + shift * b.height, b.x1, b.y1 + shift * b.height, b.text)
            if _is_anchor(b, anchors)
            else b
            for b in boxes
        ]

    return Page(
        page.sha256, moved(page.persian, page.latin), moved(page.latin, page.latin), page.lattice
    )


class Reversed:
    """Every cell read on the WRONG side of its own label.

    Direction follows the script — a Persian label's value is to its LEFT, an
    English label's to its RIGHT — so reversing it points the window at the
    neighbouring cell while leaving every other gate, and the page, untouched.
    A rule that locates a printed cell must admit nothing here.
    """

    def __enter__(self) -> Reversed:
        self.cell = abo_module._cell

        def flipped(anchor: Box, boxes: list[Box], rightwards: bool, **kw: object) -> object:
            return self.cell(anchor, boxes, not rightwards, **kw)

        abo_module._cell = flipped
        return self

    def __exit__(self, *_: object) -> None:
        abo_module._cell = self.cell


def _anchor_count(page: Page) -> int:
    """How many printed field labels this page offers the rule."""
    return sum(1 for b in page.persian if abo_module._is_persian_label(b.text)) + sum(
        1 for b in page.latin if _is_anchor(b, page.latin)
    )


def _decoys(page: Page) -> Iterator[tuple[list[Box], list[Box]]]:
    """The real labels removed and ONE size-matched ordinary box promoted, in turn.

    Every candidate is yielded rather than a single representative, because the
    statistic that answers "does a printed field label do the work?" is the
    admission rate PER CANDIDATE, and one decoy per page cannot estimate it.
    A candidate is a Persian box within `DECOY_HEIGHT_TOLERANCE` of the label's
    height whose text is not itself a blood-group value.
    """
    labels = [b for b in page.persian if abo_module._is_persian_label(b.text)]
    if not labels:
        return
    height = labels[0].height
    kept = [b for b in page.persian if b not in labels]
    for decoy in kept:
        if abs(decoy.height - height) > DECOY_HEIGHT_TOLERANCE * height:
            continue
        if abo_module._parse((decoy.text or "").strip()) is not None:
            continue
        yield (
            [Box(b.x0, b.y0, b.x1, b.y1, labels[0].text) if b is decoy else b for b in kept],
            page.latin,
        )


def run(args: argparse.Namespace) -> int:
    tally: Counter[str] = Counter()
    routes: Counter[str] = Counter()
    placebo: Counter[str] = Counter()
    examined = 0
    for page in pages(
        args.persian, args.ocr, args.geometry, levelled=args.levelled, limit=args.limit
    ):
        examined += 1
        with Window():
            before = _answer(page, lattice=page.lattice)
        after = _answer(page, lattice=page.lattice)
        if before[:3] == after[:3]:
            if before[4] != after[4]:
                # Split, because they are different claims. Only the first is
                # a REVIEW item a person now reads a specific sentence on; the
                # second is a published reading that now names its route, which
                # is provenance, not an improvement to anyone's review queue.
                tally[
                    "review reason made more specific"
                    if after[0] is not AboStatus.RESOLVED
                    else "a published reading now names its route"
                ] += 1
        elif after[0] is AboStatus.RESOLVED and before[0] is not AboStatus.RESOLVED:
            tally["gained"] += 1
            routes[after[3].value if isinstance(after[3], AboRescue) else "no rescue"] += 1
        elif before[0] is AboStatus.RESOLVED and after[0] is not AboStatus.RESOLVED:
            tally["LOST (a resolved cell now goes to a person)"] += 1
        elif before[0] is AboStatus.RESOLVED and after[0] is AboStatus.RESOLVED:
            tally["!! VALUE CHANGED"] += 1
        else:
            tally["other change"] += 1
        if after[0] is AboStatus.RESOLVED:
            tally["resolved after"] += 1
            if isinstance(after[3], AboRescue):
                tally["...its value box admitted by a rescue"] += 1
        if before[0] is AboStatus.RESOLVED:
            tally["resolved before"] += 1
        tally["printed field labels offered to the rule"] += _anchor_count(page)

        if args.placebo == "translated":
            for shift in TRANSLATIONS:
                for direction in (-1.0, 1.0):
                    moved = _translated(page, direction * shift)
                    with Window():
                        shipped = _answer(moved, lattice=moved.lattice)
                    now = _answer(moved, lattice=moved.lattice)
                    key = f"{'+' if direction > 0 else '-'}{shift:.1f}h"
                    placebo[f"{key} shipped"] += shipped[0] is AboStatus.RESOLVED
                    placebo[f"{key} now"] += now[0] is AboStatus.RESOLVED
                    if now[0] is AboStatus.RESOLVED:
                        if shipped[0] is AboStatus.RESOLVED:
                            placebo[f"{key} differs from the true read"] += now[1] != after[1]
                        elif isinstance(now[3], AboRescue):
                            # Which rescue admitted a value at a label that is
                            # no longer over a field: the leak, by route. An
                            # extra hit that re-finds the SAME value as the
                            # true read measures the window's reach; one that
                            # produces a DIFFERENT value is the leak that
                            # matters, and it is the one gated below.
                            placebo[f"{key} rescued by {now[3].value}"] += 1
                            if now[1] != after[1]:
                                placebo[f"{key} leaked"] += 1
                                placebo[f"{key} leaked via {now[3].value}"] += 1
                                if now[5]:
                                    placebo[f"{key} leaked AND would be published"] += 1
        elif args.placebo == "decoy":
            for persian, latin in _decoys(page):
                fake = Page(page.sha256, persian, latin, page.lattice)
                with Window():
                    shipped = _answer(fake, lattice=fake.lattice)
                now = _answer(fake, lattice=fake.lattice)
                placebo["decoy candidates"] += 1
                placebo["decoy shipped"] += shipped[0] is AboStatus.RESOLVED
                placebo["decoy now"] += now[0] is AboStatus.RESOLVED
                if now[0] is AboStatus.RESOLVED and isinstance(now[3], AboRescue):
                    placebo["decoy admitted by a rescue"] += 1
                    placebo[f"decoy rescued by {now[3].value}"] += 1
                    if shipped[0] is not AboStatus.RESOLVED and now[1] != after[1]:
                        placebo["decoy leaked"] += 1
                        if now[5]:
                            placebo["decoy leaked AND would be published"] += 1
        elif args.placebo == "direction":
            with Reversed():
                with Window():
                    shipped = _answer(page, lattice=page.lattice)
                now = _answer(page, lattice=page.lattice)
            placebo["wrong-direction shipped"] += shipped[0] is AboStatus.RESOLVED
            placebo["wrong-direction now"] += now[0] is AboStatus.RESOLVED
            if now[0] is AboStatus.RESOLVED and isinstance(now[3], AboRescue):
                placebo["wrong-direction admitted by a rescue"] += 1
                placebo[f"wrong-direction rescued by {now[3].value}"] += 1
                if shipped[0] is not AboStatus.RESOLVED and now[1] != after[1]:
                    placebo["wrong-direction leaked"] += 1
                    if now[5]:
                        placebo["wrong-direction leaked AND would be published"] += 1

    frame = "levelled" if args.levelled else "raw"
    print(f"documents examined: {examined:,}   lattice frame: {frame}")
    for name, count in sorted(tally.items(), key=lambda kv: -kv[1]):
        print(f"  {name:<48}{count:>8,}")
    if routes:
        print("  gained, by the route the value box took:")
        for name, count in sorted(routes.items()):
            print(f"    {name:<46}{count:>8,}")
    real_anchors = tally["printed field labels offered to the rule"]
    real_admissions = tally["...its value box admitted by a rescue"]
    if real_anchors:
        print(
            f"  rescued admissions per printed field label: {real_admissions:,}/"
            f"{real_anchors:,} = {100 * real_admissions / real_anchors:.3f}%"
        )
    failed: list[str] = []
    if placebo:
        print(f"placebo: {args.placebo}")
        for name, count in sorted(placebo.items()):
            print(f"  {name:<48}{count:>8,}")
        candidates = placebo["decoy candidates"]
        admitted = placebo["decoy admitted by a rescue"]
        if candidates:
            rate = 100 * admitted / candidates
            print(f"  rescued admissions per decoy: {admitted:,}/{candidates:,} = {rate:.3f}%")
            if real_anchors and rate > 0:
                print(
                    "  specificity, admissions per candidate: "
                    f"{100 * real_admissions / real_anchors:.3f}% at a printed label "
                    f"against {rate:.3f}% at a decoy "
                    f"= {(real_admissions / real_anchors) / (admitted / candidates):.1f}x"
                )
            elif real_anchors:
                print(
                    "  specificity, admissions per candidate: "
                    f"{100 * real_admissions / real_anchors:.3f}% at a printed label "
                    "against 0 at a decoy"
                )
        print(
            "  reach (every extra admission — centre fix 9's gate) and leak (an extra "
            f"admission of a DIFFERENT value); allowance +{PLACEBO_ALLOWANCE}:"
        )
        for key in sorted({n.rsplit(" ", 1)[0] for n in placebo if n.endswith(" now")}):
            delta = placebo[f"{key} now"] - placebo[f"{key} shipped"]
            leaked = placebo[f"{key} leaked"]
            published = placebo[f"{key} leaked AND would be published"]
            marks = []
            if delta > PLACEBO_ALLOWANCE:
                marks.append("REACH OVER THE ALLOWANCE")
                failed.append(f"{key} reach {delta:+,}")
            if leaked > PLACEBO_ALLOWANCE:
                marks.append("LEAK OVER THE ALLOWANCE")
                failed.append(f"{key} leak {leaked:+,}")
            if published:
                marks.append(f"{published} OF THE LEAK WOULD BE PUBLISHED")
                failed.append(f"{key} published leak {published:+,}")
            by_route = " ".join(
                f"{route.value.lower()} {placebo[f'{key} rescued by {route.value}']:+,}"
                for route in AboRescue
                if placebo[f"{key} rescued by {route.value}"]
            )
            print(
                f"    {key:<24}reach {delta:>+7,}   leak {leaked:>+7,}   "
                f"published {published:>+5,}   {'; '.join(marks) or 'ok':<44}{by_route}"
            )
    if failed:
        print("PLACEBO GATE FAILS: " + ", ".join(failed))
        print(
            "  A shift inside the band cap "
            f"({abo_module._MAX_BAND_HEIGHTS:.1f} anchor heights) leaves the label in its own "
            "printed row, where a rule whose cell IS the row must find the same cell; that is "
            "the reach the band route spends there. Every failure is recorded and decided in "
            "HA-019, not waved through here."
        )
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--persian", type=Path, default=ROOT / "data/derived/persian_pass.sqlite")
    parser.add_argument("--ocr", type=Path, default=ROOT / "data/derived/ocr_pass.sqlite")
    parser.add_argument("--geometry", type=Path, default=ROOT / "data/derived/geometry.sqlite")
    parser.add_argument("--limit", type=int, default=0, help="stop after this many documents")
    parser.add_argument(
        "--levelled",
        action="store_true",
        help="rotate the grid into the level frame: the WRONG frame, kept as the discriminator",
    )
    parser.add_argument("--placebo", choices=("translated", "decoy", "direction"), default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="the only mode; this script never writes anything",
    )
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
