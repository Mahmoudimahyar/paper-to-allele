#!/usr/bin/env python3
"""Import a Telegram HTML export into the source store, idempotently.

`HIST-001`. Re-running this over the same export writes nothing: identity is
`(export id, file, telegram message id)`, the export id follows the bytes of the
message pages rather than the path, and a row is rewritten only when its content
hash changed.

    uv run --frozen --extra hist python scripts/ingest_export.py \\
        --export data/raw/ChatExport_2026-08-31

Prints counts only. The messages are the patients' and the brokers' own words:
nothing here echoes message text, sender names or contact details, and the
database it writes is PHI and lives in gitignored `data/derived/`.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kidneymatch.ingestion.source_store import ingest  # noqa: E402
from kidneymatch.ingestion.telegram_html import PARSER_VERSION, export_files  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", type=Path, default=ROOT / "data/raw/ChatExport_2026-08-31")
    parser.add_argument("--database", type=Path, default=ROOT / "data/derived/source.sqlite")
    args = parser.parse_args()

    if not args.export.is_dir():
        print(f"missing export directory {args.export}")
        return 2
    pages = export_files(args.export)
    if not pages:
        print(f"no messages*.html under {args.export}")
        return 2

    print(f"parser {PARSER_VERSION}; {len(pages)} page(s) to read", flush=True)
    started = time.perf_counter()
    report = ingest(args.export, args.database)
    elapsed = time.perf_counter() - started

    print(f"export        {report.export_id}")
    print(f"files         {report.files:>9,}")
    print(f"messages      {report.messages:>9,}")
    print(f"  inserted    {report.inserted:>9,}")
    print(f"  updated     {report.updated:>9,}")
    print(f"  unchanged   {report.unchanged:>9,}")
    print(f"service events{report.service_events:>9,}")
    print(f"unparsed      {report.unparsed:>9,}")
    print(f"elapsed       {elapsed:>9.1f}s  -> {args.database}")
    if report.idempotent:
        print("\nNothing changed: this export was already imported.")
    if report.unparsed:
        print(
            f"\n{report.unparsed} source fragment(s) the parser did not recognise were "
            "stored in `source_unparsed` rather than dropped. Read them there."
        )
    print("\nThis is the evidence layer. No bundle, no candidate, no medical reading.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
