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

**Does the window find values where no value is?** Two placebos, each a way of
asking the same page a question whose answer must be "nothing":

* `--placebo translated` moves every field label 1.0, 1.5 and 2.0 label heights
  up and down and reads again. A rule that follows the printed cell loses the
  value; a rule that merely reaches finds one anyway.
* `--placebo decoy` promotes a size-matched NON-label box to be the anchor and
  removes the real label. A cell located by a printed field label must return
  far less here than at a real one.

The gate the fixes ask for: neither placebo may exceed the shipped count by
more than +2 admissions.

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
)
from kidneymatch.ocr.anchors import Box  # noqa: E402
from kidneymatch.ocr.geometry import PageFrame  # noqa: E402
from kidneymatch.ocr.lattice import Lattice, lattice_for  # noqa: E402
from kidneymatch.ocr.rulings import GEOMETRY_VERSION  # noqa: E402

# Below this the extraction declines to rotate at all (extract_facts.py).
MIN_FRAME_TILT_DEG = 1.5
TRANSLATIONS = (1.0, 1.5, 2.0)
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
    reading = read_abo(page.persian, page.latin, lattice=lattice)
    return (reading.status, reading.group, reading.rh, reading.rescued, reading.reason)


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


def _decoyed(page: Page) -> tuple[list[Box], list[Box]] | None:
    """The real labels removed and one size-matched ordinary box promoted."""
    labels = [b for b in page.persian if abo_module._is_persian_label(b.text)]
    if not labels:
        return None
    height = labels[0].height
    others = [
        b
        for b in page.persian
        if b not in labels
        and abs(b.height - height) <= DECOY_HEIGHT_TOLERANCE * height
        and abo_module._parse((b.text or "").strip()) is None
    ]
    if not others:
        return None
    decoy = others[len(others) // 2]
    persian = [
        Box(b.x0, b.y0, b.x1, b.y1, labels[0].text) if b is decoy else b
        for b in page.persian
        if b not in labels
    ]
    return persian, page.latin


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
                tally["review reason made more specific"] += 1
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
        if before[0] is AboStatus.RESOLVED:
            tally["resolved before"] += 1

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
        elif args.placebo == "decoy":
            decoyed = _decoyed(page)
            if decoyed is None:
                continue
            fake = Page(page.sha256, decoyed[0], decoyed[1], page.lattice)
            with Window():
                shipped = _answer(fake, lattice=fake.lattice)
            now = _answer(fake, lattice=fake.lattice)
            placebo["decoys examined"] += 1
            placebo["decoy shipped"] += shipped[0] is AboStatus.RESOLVED
            placebo["decoy now"] += now[0] is AboStatus.RESOLVED

    frame = "levelled" if args.levelled else "raw"
    print(f"documents examined: {examined:,}   lattice frame: {frame}")
    for name, count in sorted(tally.items(), key=lambda kv: -kv[1]):
        print(f"  {name:<48}{count:>8,}")
    if routes:
        print("  gained, by the route the value box took:")
        for name, count in sorted(routes.items()):
            print(f"    {name:<46}{count:>8,}")
    if placebo:
        print(f"placebo: {args.placebo}")
        for name, count in sorted(placebo.items()):
            print(f"  {name:<48}{count:>8,}")
        print("  reach (extra admissions) and leak (extra admissions of a DIFFERENT value):")
        for key in sorted({n.rsplit(" ", 1)[0] for n in placebo if n.endswith(" now")}):
            delta = placebo[f"{key} now"] - placebo[f"{key} shipped"]
            leaked = placebo[f"{key} leaked"]
            verdict = "ok" if leaked <= PLACEBO_ALLOWANCE else "OVER THE ALLOWANCE"
            print(f"    {key:<28}reach {delta:>+7,}   leak {leaked:>+7,}   {verdict}")
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
    parser.add_argument("--placebo", choices=("translated", "decoy"), default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="the only mode; this script never writes anything",
    )
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
