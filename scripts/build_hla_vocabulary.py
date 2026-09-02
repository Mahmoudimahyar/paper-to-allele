#!/usr/bin/env python3
"""Generate the per-locus first-field vocabulary from the IPD-IMGT/HLA allele table.

The resolver needs to know which allele families exist for each locus, because
the recognizer's commonest surviving error is a leading `0` read as `8` or `9`:
`A*83`, `C*84`, `DQB1*83`, `DRB1*93`. The digits are clean, so no glyph repair
can see it — only a vocabulary can (KI-016).

**Why a generated, committed file rather than a lookup at run time.** A
vocabulary that changes under the repository's feet would silently change which
values are accepted between two runs of the same code, and every acceptance
decision recorded against it would become unreproducible. So the table is
generated once, committed with the IMGT version stamped inside it, and read as
data. Regenerating is a deliberate act that shows up in review.

**On the version.** `HLA_VALIDATION_SPEC.md` pins IMGT/HLA 3.65, which the
locked py-ard 1.5.5 cannot load (HA-006 — a human decision). This script does
not choose: it takes `--imgt-version`, records exactly what it used, and refuses
to guess. When HA-006 is settled, rerun it with the agreed version; the
committed file's `imgt_version` field is what every derived fact's provenance
should cite until then.

Usage:
    uv run --frozen --extra hla python scripts/build_hla_vocabulary.py --imgt-version 3620
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sqlite3
import sys
import tempfile
from collections import defaultdict
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "config/hla_first_fields.json"

# The loci this project reads. Serology names (`DR11`, `Cw7`) are deliberately
# absent: they are a different naming system and must never be mixed with
# molecular families (`HLA_VALIDATION_SPEC.md`).
LOCI = ("A", "B", "C", "DRB1", "DRB3", "DRB4", "DRB5", "DQA1", "DQB1", "DPA1", "DPB1")

_ALLELE = re.compile(r"^(?P<locus>[A-Z]+[0-9]*)\*(?P<first>\d{2,4})(?::|$)")


def build(imgt_version: str, out: Path) -> int:
    import pyard

    # Cache outside the repository, under a stable name: this is a
    # multi-megabyte download, nothing derived from it belongs in version
    # control except the small table written below, and py-ard keeps its sqlite
    # connection open, so a self-deleting temporary directory cannot be removed
    # on Windows.
    cache = Path(tempfile.gettempdir()) / "kidneymatch-pyard-cache"
    cache.mkdir(parents=True, exist_ok=True)
    pyard.init(imgt_version=imgt_version, data_dir=str(cache), load_mac=False)
    databases = glob.glob(os.path.join(cache, "*.sqlite3"))
    if not databases:
        print(f"py-ard produced no cache for IMGT {imgt_version}", file=sys.stderr)
        return 2
    con = sqlite3.connect(databases[0])
    rows = [r[0] for r in con.execute("SELECT allele FROM alleles")]
    con.close()

    families: dict[str, set[str]] = defaultdict(set)
    for allele in rows:
        match = _ALLELE.match(allele)
        if not match:
            continue
        locus = match.group("locus")
        if locus in LOCI:
            families[locus].add(match.group("first"))

    missing = [locus for locus in LOCI if not families.get(locus)]
    if missing:
        print(f"no alleles found for {', '.join(missing)}; refusing to write", file=sys.stderr)
        return 2

    payload = {
        "schema": "hla-first-fields/v1",
        "imgt_version": imgt_version,
        "pyard_version": metadata.version("py-ard"),
        "source_alleles": len(rows),
        "note": (
            "First-field allele families per locus, generated from the IPD-IMGT/HLA "
            "allele table. Molecular families only; serology names are a different "
            "system and are never mixed with these."
        ),
        "first_fields": {locus: sorted(families[locus]) for locus in LOCI},
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")

    print(f"IMGT {imgt_version} via py-ard {payload['pyard_version']}: {len(rows):,} alleles")
    for locus in LOCI:
        print(f"  {locus:<6}{len(families[locus]):>4} first fields")
    print(f"written to {out.relative_to(ROOT)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--imgt-version",
        required=True,
        help="IMGT/HLA release to read, e.g. 3620. Recorded in the output; not guessed.",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    return build(args.imgt_version, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
