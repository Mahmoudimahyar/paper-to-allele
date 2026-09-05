"""The printed table as a grid of cells, from the rulings the geometry pass stored.

`scripts/geometry_pass.py` detects every long horizontal and vertical ruling on
every page (`ocr/rulings.py`, LSD) to measure the tilt, and stores the
segments. This module reads them as what they are on a laboratory form: the
lines that box each value. A row band is the space between two horizontal
rulings that both span a point; the cells of that row are cut by the vertical
rulings crossing it.

Why this exists (measured 2026-09-05 from the stored rulings alone): on the
three known forms, 4,541 cells had no readable locus label; for 3,223 of them
a ruled row sits exactly where the form's template puts the label, and 2,271
of those rows hold one or two allele-shaped boxes the pipeline abstains on
today. 24,187 cells had a readable label and no box in the overlap test's
reach; 20,517 of those rows hold no box at all — a printed locus the lab left
empty, which ink can certify — and 774 hold values the row rules missed. The
grid also places the second DRB3/4/5 slot on 600 rows that have no DRB1 pair
to place it by.

Nothing here reads text. The grid says where a cell is; the anchor gates and
the ink measure say what is in it.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from kidneymatch.ocr.geometry import PageFrame

# A ruling spans a point when the point lies within its extent widened by this
# (normalised page units): the detector trims a few pixels off each end.
SPAN_SLACK = 0.02
# A vertical ruling divides a row only when it crosses this share of the row's
# height. Testing the band's mid line alone with SPAN_SLACK admitted a ruling
# of the block ABOVE that merely ended on the row's top ruling — 0.02 is 26 px
# on a 1300 px page, wider than half a printed row — and the cell it cut was
# then a fraction of the printed one.
VERTICAL_SPAN_SHARE = 0.6
# A token's box may overrun its cell's right ruling by this share of the box's
# width before the next cell is taken to be the one after it.
EDGE_SLACK_SHARE = 0.25
# A row band is plausible when its height is within these multiples of the
# label height: tighter than half a label is a double line, wider than 3.5
# labels is a block, not a row.
MIN_ROW_HEIGHTS = 0.5
MAX_ROW_HEIGHTS = 3.5


@dataclass(frozen=True, slots=True)
class Ruling:
    """One ruling in normalised page coordinates.

    `start`/`end` are its extent along itself and `at_start`/`at_end` its
    position across at each end. A printed ruling on a photographed page is
    straight but rarely level, so its position is read AT the point being
    asked about (`at_x`) rather than collapsed to a mean: on a page tilted a
    degree, a ruling 0.6 of the page wide moves half a row's height from end
    to end, which is enough to put a label in the row above.
    """

    start: float
    end: float
    at_start: float
    at_end: float

    @property
    def at(self) -> float:
        """The position across at the middle of the ruling."""
        return (self.at_start + self.at_end) / 2

    def at_x(self, x: float) -> float:
        """The position across at `x` along the ruling, extended past its ends."""
        span = self.end - self.start
        if span <= 1e-9:
            return self.at
        t = (x - self.start) / span
        return self.at_start + t * (self.at_end - self.at_start)

    def spans(self, x: float, slack: float = SPAN_SLACK) -> bool:
        return self.start - slack <= x <= self.end + slack


@dataclass(frozen=True, slots=True)
class RowBand:
    """The space between two horizontal rulings, both spanning the point asked for."""

    top: float
    bottom: float
    # The extent both rulings share along the row; the cell area runs to `right`.
    left: float = 0.0
    right: float = 1.0

    @property
    def height(self) -> float:
        return self.bottom - self.top

    def contains_y(self, y: float) -> bool:
        return self.top <= y <= self.bottom


@dataclass(frozen=True, slots=True)
class Lattice:
    horizontal: tuple[Ruling, ...]  # extent in x, position in y
    vertical: tuple[Ruling, ...]  # extent in y, position in x

    @classmethod
    def from_segments(
        cls,
        h_segments: list[list[float]] | list[tuple[float, ...]],
        v_segments: list[list[float]] | list[tuple[float, ...]],
        width: int,
        height: int,
        frame: PageFrame | None = None,
    ) -> Lattice:
        """From the stored pixel segments `[x0, y0, x1, y1]`, levelled like the boxes are.

        On a ROTATE page the extraction rectifies the boxes into the level
        frame; the rulings are rotated by the same `PageFrame` so the grid and
        the boxes describe the same page.
        """

        def level(x: float, y: float) -> tuple[float, float]:
            if frame is not None and not frame.is_identity:
                x, y = frame.rotate_pixel(x, y)
            return x / width, y / height

        horizontal: list[Ruling] = []
        for x0, y0, x1, y1 in h_segments:
            (a, b), (c, d) = level(x0, y0), level(x1, y1)
            left, right = ((a, b), (c, d)) if a <= c else ((c, d), (a, b))
            horizontal.append(Ruling(left[0], right[0], left[1], right[1]))
        vertical: list[Ruling] = []
        for x0, y0, x1, y1 in v_segments:
            (a, b), (c, d) = level(x0, y0), level(x1, y1)
            top, bottom = ((a, b), (c, d)) if b <= d else ((c, d), (a, b))
            vertical.append(Ruling(top[1], bottom[1], top[0], bottom[0]))
        return cls(
            tuple(sorted(horizontal, key=lambda r: r.at)),
            tuple(sorted(vertical, key=lambda r: r.at)),
        )

    def row_band(self, x: float, y: float, label_height: float) -> RowBand | None:
        """The row of the printed table containing (x, y), or None.

        Both rulings must span x, and each is read AT x, not at its middle.
        The band must be between half a label and 3.5 labels tall, and no
        other ruling may pass through it anywhere along its width: a ruling
        broken over the label leaves a band spanning two printed rows, and
        3.5 label heights is wide enough to admit that silently. A point on a
        ruling belongs to the row below it.
        """
        spanning = [(r, r.at_x(x)) for r in self.horizontal if r.spans(x)]
        above = [(r, at) for r, at in spanning if at <= y]
        below = [(r, at) for r, at in spanning if at > y]
        if not above or not below:
            return None
        top, top_at = max(above, key=lambda pair: pair[1])
        bottom, bottom_at = min(below, key=lambda pair: pair[1])
        band = RowBand(top_at, bottom_at, max(top.start, bottom.start), min(top.end, bottom.end))
        if not (MIN_ROW_HEIGHTS * label_height <= band.height <= MAX_ROW_HEIGHTS * label_height):
            return None
        if band.right <= band.left:
            return None
        for ruling, _ in ((r, 0) for r in self.horizontal):
            if ruling is top or ruling is bottom:
                continue
            # Anywhere the ruling overlaps the band's width, is it inside it?
            left = max(ruling.start, band.left)
            right = min(ruling.end, band.right)
            if left > right:
                continue
            for probe in (left, (left + right) / 2, right):
                at = ruling.at_x(probe)
                if band.top + 1e-9 < at < band.bottom - 1e-9:
                    return None
        return band

    def verticals_crossing(self, band: RowBand, x_from: float = 0.0) -> list[float]:
        """The x positions of the vertical rulings crossing the band, right of
        `x_from`, ascending.

        A ruling divides this row only when it runs through most of the row's
        height (`VERTICAL_SPAN_SHARE`); one that merely ends on the row's own
        boundary belongs to the block above or below, and cutting a cell with
        it returns a fraction of the printed one.
        """
        needed = VERTICAL_SPAN_SHARE * band.height
        out = []
        for r in self.vertical:
            overlap = min(r.end, band.bottom) - max(r.start, band.top)
            if overlap < needed:
                continue
            at = r.at_x((band.top + band.bottom) / 2)
            if at > x_from:
                out.append(at)
        return sorted(out)

    def cell_right_of(
        self, band: RowBand, x: float, slack: float = 0.0
    ) -> tuple[float, float] | None:
        """The x-extent of the next cell to the right of `x` in this row.

        A box that reaches or overruns its own cell's right ruling would
        otherwise skip the adjacent cell, so `slack` (a share of the box's
        width, chosen by the caller) is allowed back: a ruling within it is
        treated as the boundary the box sits against, not as a cell's start.
        """
        crossing = self.verticals_crossing(band, x - slack)
        if len(crossing) < 2:
            return None
        return crossing[0], crossing[1]


def load_rulings(path: Path | None, version: str) -> dict[str, tuple[int, int, str, str]]:
    """Per-document stored rulings from the geometry pass: (width, height, h_json, v_json).

    Absent — or a geometry file from before the segments were stored — there is
    no lattice anywhere, which is the pipeline of before.
    """
    if path is None or not path.exists():
        return {}
    con = sqlite3.connect(path)
    try:
        return {
            sha: (int(w), int(h), hj, vj)
            for sha, w, h, hj, vj in con.execute(
                "SELECT sha256, width, height, h_rulings_json, v_rulings_json FROM page_geometry "
                "WHERE geometry_version=? AND h_rulings_json IS NOT NULL AND width IS NOT NULL",
                (version,),
            )
        }
    except sqlite3.OperationalError:
        return {}
    finally:
        con.close()


def lattice_for(
    sha256: str, rulings: dict[str, tuple[int, int, str, str]], frame: PageFrame | None
) -> Lattice | None:
    """The page's ruled grid, levelled the way its boxes are, or None."""
    row = rulings.get(sha256)
    if row is None:
        return None
    width, height, h_json, v_json = row
    try:
        h_segments, v_segments = json.loads(h_json or "[]"), json.loads(v_json or "[]")
    except json.JSONDecodeError:
        return None
    if not h_segments:
        return None
    return Lattice.from_segments(h_segments, v_segments, width, height, frame)
