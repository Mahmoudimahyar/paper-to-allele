#!/usr/bin/env python3
"""Join each extracted document to the message that posted it, and read its caption.

The OCR layer knows a document by its file path; the source layer knows the same
path as a media href on a message. That one join is what makes a caption, a
sender and a bundle available to the role decision — the reason role currently
resolves on only 40% of typed documents.

    uv run --frozen --extra hist python scripts/link_documents.py

Writes `document_message` and `document_caption_claim` into the source database.
A caption claim is EVIDENCE: `decide_document_role` weighs it against the
printed form field, which outranks it. Nothing here resolves a role.

Prints counts only. Never prints caption text, sender names or file paths.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kidneymatch.documents.caption import (  # noqa: E402
    CAPTION_READER_VERSION,
    read_caption_role,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS document_message (
    sha256              TEXT NOT NULL,
    export_id           TEXT NOT NULL,
    source_file         TEXT NOT NULL,
    telegram_message_id INTEGER NOT NULL,
    bundle_id           TEXT,
    rel_path            TEXT NOT NULL,
    PRIMARY KEY (sha256, export_id, telegram_message_id)
);

CREATE TABLE IF NOT EXISTS document_caption_claim (
    sha256          TEXT NOT NULL,
    export_id       TEXT NOT NULL,
    role            TEXT NOT NULL,
    tier            TEXT NOT NULL,
    reason          TEXT,
    reader_version  TEXT NOT NULL,
    PRIMARY KEY (sha256, export_id)
);
"""


def run(source_db: Path, facts_db: Path) -> int:
    if not source_db.exists():
        print(f"missing {source_db}; run scripts/ingest_export.py first")
        return 2
    if not facts_db.exists():
        print(f"missing {facts_db}; run scripts/extract_facts.py first")
        return 2

    con = sqlite3.connect(source_db)
    con.executescript(SCHEMA)
    con.execute("ATTACH DATABASE ? AS facts", (str(facts_db),))

    # rel_path -> sha256, from the OCR side.
    documents = {
        rel_path: sha256
        for sha256, rel_path in con.execute("SELECT sha256, rel_path FROM facts.document")
    }
    print(f"documents with facts: {len(documents):,}", flush=True)

    started = time.perf_counter()
    bundle_of = {
        (export_id, message_id): bundle_id
        for export_id, bundle_id, message_id in con.execute(
            "SELECT export_id, bundle_id, telegram_message_id FROM bundle_message"
        )
    }

    links: list[tuple[object, ...]] = []
    caption_rows: list[tuple[object, ...]] = []
    tally: Counter[str] = Counter()
    seen_documents: set[tuple[str, str]] = set()

    for export_id, source_file, message_id, media_json, raw_text in con.execute(
        "SELECT export_id, source_file, telegram_message_id, media, raw_text FROM source_message "
        "WHERE media != '[]'"
    ):
        try:
            media = json.loads(media_json)
        except json.JSONDecodeError:
            continue
        for item in media:
            href = item.get("href")
            if not href:
                continue
            sha256 = documents.get(href)
            if sha256 is None:
                tally["media without an extracted document"] += 1
                continue
            links.append(
                (
                    sha256,
                    export_id,
                    source_file,
                    int(message_id),
                    bundle_of.get((export_id, int(message_id))),
                    href,
                )
            )
            tally["documents linked to a message"] += 1

            key = (sha256, export_id)
            if key in seen_documents:
                continue
            seen_documents.add(key)
            claim = read_caption_role(raw_text or "")
            tally[f"caption {claim.tier.value}"] += 1
            if claim.tier.value != "NONE":
                caption_rows.append(
                    (
                        sha256,
                        export_id,
                        claim.role.value,
                        claim.tier.value,
                        claim.reason or None,
                        CAPTION_READER_VERSION,
                    )
                )

    con.execute("DELETE FROM document_message")
    con.execute("DELETE FROM document_caption_claim")
    con.executemany("INSERT OR REPLACE INTO document_message VALUES (?,?,?,?,?,?)", links)
    con.executemany(
        "INSERT OR REPLACE INTO document_caption_claim VALUES (?,?,?,?,?,?)", caption_rows
    )
    con.commit()

    linked_documents = len({row[0] for row in links})
    print(f"\nlinked in {time.perf_counter() - started:.1f}s")
    print(
        f"  documents linked      {linked_documents:>9,}  "
        f"({linked_documents / max(len(documents), 1):.1%} of extracted documents)"
    )
    print(f"  document-message rows {len(links):>9,}")
    for label, count in tally.most_common():
        print(f"    {label:<34}{count:>9,}")
    print(f"  caption claims stored {len(caption_rows):>9,}")
    con.execute("DETACH DATABASE facts")
    con.close()
    print(
        "\nA caption is what the poster said, and the poster is often a broker. "
        "It corroborates or vetoes the printed field; it never renames the subject."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "data/derived/source.sqlite")
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    args = parser.parse_args()
    return run(args.source, args.facts)


if __name__ == "__main__":
    raise SystemExit(main())
