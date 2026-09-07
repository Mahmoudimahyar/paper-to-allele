#!/usr/bin/env python3
"""Measure, per page, that checkpoints 1 and 2 actually held. Records only.

`checkpoint_attribution.py` charges 0 labelled failures to orientation and to
tilt. That is a statement about 1,342 labelled cells, and it is only as good as
the records behind it: the orientation verdict lives in another store and the
tilt is recorded as the angle the pipeline INTENDED to remove, not as the angle
that was left. A levelling bug — a sign error, a biased theta (KI-024), a frame
built from the wrong page size — would leave a tilted page tilted and this
project would learn about it in a labelling round, months later.

So this pass writes two columns on `document` and nothing else:

* `orientation` — the upright pass's verdict for the page, or `NOT_A_CANDIDATE`
  where the page never entered that pass (its boxes were already portrait, which
  is that pass's own test for upright);
* `residual_slope_deg` — how far from level the page's printed rulings still
  are, AFTER the frame the pipeline uses. For a page the pipeline levels this is
  **re-measured from the rotated image**, not derived from the angle that was
  removed: an independent number is the only kind that can catch a levelling
  bug. For a page the pipeline does not level it is the measured page angle
  itself, because that is exactly what the row reader carries.

`residual_source` records which of the two it is, so nobody has to guess.

The guard: **a levelled page must come back under 0.5°.** The pass prints how
many did not, and every page it re-measured. It writes no fact and changes no
status.

Re-measuring means one image load and one LSD detection per levelled page
(1,591 of 23,566 today), so the run is bounded by the pages the pipeline
actually transformed. `--limit` and re-runs are safe: a page already measured
under this version is skipped unless `--remeasure` is passed.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from extract_facts import MIN_FRAME_TILT_DEG  # noqa: E402

EV = "facts/v1"
GEOMETRY_VERSION = "rulings/v3+lsd+sweep"
GUARD_VERSION = "checkpoint-guards/v1"
# A levelled page must come back under this. The row reader follows the page's
# own slope from here (`ocr/rows.py`), and half a degree over a page width is
# well inside one printed row's height.
LEVEL_TOLERANCE_DEG = 0.5

NOT_A_CANDIDATE = "NOT_A_CANDIDATE"
REMEASURED = "remeasured-after-levelling"
AS_MEASURED = "measured-not-levelled"
NO_MEASUREMENT = "no-ruling-measurement"


def add_columns(con: sqlite3.Connection) -> None:
    """The two columns, added once. Named, so an older row simply reads NULL."""
    existing = {row[1] for row in con.execute("PRAGMA table_info(document)")}
    for name, kind in (
        ("orientation", "TEXT"),
        ("residual_slope_deg", "REAL"),
        ("residual_source", "TEXT"),
    ):
        if name not in existing:
            con.execute(f"ALTER TABLE document ADD COLUMN {name} {kind}")
    con.commit()


def orientation_verdicts(upright: Path | None) -> dict[str, str]:
    if upright is None or not upright.exists():
        return {}
    con = sqlite3.connect(f"file:{upright.as_posix()}?mode=ro", uri=True)
    try:
        return {
            str(sha): str(verdict)
            for sha, verdict in con.execute("SELECT sha256, verdict FROM upright_result")
        }
    finally:
        con.close()


def page_angles(geometry: Path | None) -> dict[str, tuple[str, float | None]]:
    if geometry is None or not geometry.exists():
        return {}
    con = sqlite3.connect(f"file:{geometry.as_posix()}?mode=ro", uri=True)
    try:
        return {
            str(sha): (str(decision), None if theta is None else float(theta))
            for sha, decision, theta in con.execute(
                "SELECT sha256, decision, theta_deg FROM page_geometry WHERE geometry_version=?",
                (GEOMETRY_VERSION,),
            )
        }
    finally:
        con.close()


def remeasure(export: Path, rel_path: str, theta_deg: float) -> float | None:
    """The page's ruling angle AFTER the pipeline's own rotation, or None.

    The image is rotated by exactly the angle `PageFrame` applies (both are
    OpenCV's convention, `rulings.rotate_image` and `PageFrame.rotate_pixel`),
    and the rulings are detected again on the result. Nothing here reads the
    angle that was removed, which is the point.

    The expanded canvas is deliberate, against the obvious worry. Rotating with
    `expand=True` leaves the page's own rectangular boundary standing at the
    angle that was just removed, and if LSD locked onto those four edges the
    residual would read back as the tilt and every levelled page would look
    unlevelled. Measured on the first 20 levelled pages, it does not: expanded
    residuals are +0.01 to +0.71 deg against tilts of 1.5-4.6, i.e. near zero
    and nowhere near theta, and 19 of the 20 are under tolerance. Cropping to
    the central 80% to dodge the boundary is WORSE (3 of 20 over tolerance):
    it throws away the long rulings the estimate rests on. The page's printed
    grid outvotes its border, so the whole frame is what gets measured.
    """
    import numpy as np
    from PIL import Image as PilImage

    from kidneymatch.ocr.rulings import detect_rulings, rotate_image

    try:
        with PilImage.open(export / rel_path) as handle:
            image = np.asarray(handle.convert("L"))
    except (OSError, ValueError):
        return None
    levelled = rotate_image(image, theta_deg)
    estimate = detect_rulings(levelled)
    return None if estimate.theta_deg is None else float(estimate.theta_deg)


def run(
    facts: Path,
    export: Path,
    geometry: Path | None,
    upright: Path | None,
    *,
    dry_run: bool,
    limit: int | None,
    remeasure_all: bool,
) -> Counter[str]:
    con = sqlite3.connect(facts)
    if not dry_run:
        add_columns(con)
    have_columns = {row[1] for row in con.execute("PRAGMA table_info(document)")}
    verdicts = orientation_verdicts(upright)
    angles = page_angles(geometry)

    # `residual_source` says whether a page was already re-measured. On the
    # first run the column does not exist yet under --dry-run, and NULL then
    # means "not yet", which is exactly right.
    rows = con.execute(
        "SELECT sha256, rel_path, frame"
        + (", residual_source" if "residual_source" in have_columns else ", NULL")
        + " FROM document WHERE extraction_version=? ORDER BY sha256",
        (EV,),
    ).fetchall()

    tally: Counter[str] = Counter()
    tally["documents"] = len(rows)
    written = 0
    for sha, rel_path, frame, done in rows:
        decision, theta = angles.get(sha, ("NONE", None))
        verdict = verdicts.get(sha, NOT_A_CANDIDATE)
        tally[f"orientation: {verdict}"] += 1

        levelled = frame == "ROTATE" and theta is not None and abs(theta) >= MIN_FRAME_TILT_DEG
        if levelled:
            if done == REMEASURED and not remeasure_all:
                tally["already re-measured"] += 1
                continue
            if limit is not None and tally["re-measured"] >= limit:
                tally["levelled, not yet re-measured"] += 1
                continue
            residual = remeasure(export, rel_path, float(theta))
            source = REMEASURED if residual is not None else NO_MEASUREMENT
            tally["re-measured"] += 1
            if residual is None:
                tally["levelled, rulings not found after levelling"] += 1
            elif abs(residual) >= LEVEL_TOLERANCE_DEG:
                tally[f"LEVELLED PAGE STILL TILTED >= {LEVEL_TOLERANCE_DEG} deg"] += 1
            else:
                tally["levelled and level"] += 1
        else:
            residual = None if theta is None else abs(float(theta))
            source = AS_MEASURED if residual is not None else NO_MEASUREMENT
            if residual is None:
                tally["no ruling angle measured"] += 1
            elif residual >= MIN_FRAME_TILT_DEG:
                # A page the pipeline chose not to level that is tilted anyway:
                # UNCERTAIN geometry, or a ROTATE the frame gate declined.
                tally[f"not levelled, tilt >= {MIN_FRAME_TILT_DEG} deg ({decision})"] += 1
            elif residual >= LEVEL_TOLERANCE_DEG:
                tally[f"not levelled, tilt {LEVEL_TOLERANCE_DEG}-{MIN_FRAME_TILT_DEG} deg"] += 1
            else:
                tally["not levelled, already level"] += 1

        if dry_run:
            continue
        con.execute(
            "UPDATE document SET orientation=?, residual_slope_deg=?, residual_source=? "
            "WHERE sha256=? AND extraction_version=?",
            (verdict, residual, source, sha, EV),
        )
        written += 1
        if written % 200 == 0:
            con.commit()
    if not dry_run:
        con.commit()
    tally["rows written"] = written
    return tally


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--export", type=Path, default=ROOT / "data/raw/ChatExport_2026-08-31")
    parser.add_argument("--geometry", type=Path, default=ROOT / "data/derived/geometry.sqlite")
    parser.add_argument("--upright", type=Path, default=ROOT / "data/derived/upright_pass.sqlite")
    parser.add_argument("--dry-run", action="store_true", help="count, change nothing")
    parser.add_argument("--limit", type=int, default=None, help="cap the re-measurements this run")
    parser.add_argument(
        "--remeasure", action="store_true", help="re-measure pages already measured"
    )
    args = parser.parse_args()
    tally = run(
        args.facts,
        args.export,
        args.geometry,
        args.upright,
        dry_run=args.dry_run,
        limit=args.limit,
        remeasure_all=args.remeasure,
    )
    for key, count in tally.most_common():
        print(f"{count:>7,}  {key}")
    print(
        "The residual of a levelled page is re-measured from the rotated image; "
        "of an unlevelled page it is the angle the row reader carries."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
