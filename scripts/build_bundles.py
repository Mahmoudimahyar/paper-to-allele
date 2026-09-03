#!/usr/bin/env python3
"""Derive message bundles from the source store.

`HIST-002`. Reads `source_message` (written by `scripts/ingest_export.py`) and
writes the bundles Telegram's own structure supports, plus the adjacency links
it does not support and a person must judge.

    uv run --frozen --extra hist python scripts/build_bundles.py

Derived and idempotent: the bundle tables are rebuilt for the export being
processed, so re-running after a parser or bundler change replaces the
derivation rather than appending to it. The source records are never touched.

Prints counts only. Bundles are PHI-adjacent and live in gitignored
`data/derived/`.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kidneymatch.ingestion.bundles import (  # noqa: E402
    BUNDLER_VERSION,
    build_bundles,
    suggest_adjacent_links,
)
from kidneymatch.ingestion.telegram_html import TelegramMessageSource  # noqa: E402

SCHEMA = """
CREATE TABLE IF NOT EXISTS message_bundle (
    export_id        TEXT NOT NULL,
    bundle_id        TEXT NOT NULL,
    source_file      TEXT NOT NULL,
    primary_message_id INTEGER NOT NULL,
    bundle_type      TEXT NOT NULL,
    confidence       TEXT NOT NULL,
    review_status    TEXT NOT NULL,
    poster_display_name TEXT,
    forwarded_authors   TEXT NOT NULL,
    n_members        INTEGER NOT NULL,
    n_media          INTEGER NOT NULL,
    started_at_raw   TEXT,
    bundler_version  TEXT NOT NULL,
    PRIMARY KEY (export_id, bundle_id)
);

CREATE TABLE IF NOT EXISTS bundle_message (
    export_id           TEXT NOT NULL,
    bundle_id           TEXT NOT NULL,
    telegram_message_id INTEGER NOT NULL,
    relation            TEXT NOT NULL,
    PRIMARY KEY (export_id, bundle_id, telegram_message_id)
);

CREATE TABLE IF NOT EXISTS bundle_reply_link (
    export_id      TEXT NOT NULL,
    bundle_id      TEXT NOT NULL,
    to_message_id  INTEGER NOT NULL,
    to_file        TEXT,
    resolved       INTEGER NOT NULL,
    PRIMARY KEY (export_id, bundle_id, to_message_id)
);

CREATE TABLE IF NOT EXISTS bundle_adjacency_suggestion (
    export_id      TEXT NOT NULL,
    from_bundle_id TEXT NOT NULL,
    to_bundle_id   TEXT NOT NULL,
    relation       TEXT NOT NULL,
    review_status  TEXT NOT NULL,
    seconds_apart  REAL NOT NULL,
    reason         TEXT NOT NULL,
    PRIMARY KEY (export_id, from_bundle_id, to_bundle_id)
);
"""


def read_messages(con: sqlite3.Connection, export_id: str) -> list[TelegramMessageSource]:
    """Rebuild the source records the bundler needs, in posting order.

    Only the structural fields matter here; the text and media of a message are
    the OCR layer's business, so only the media COUNT is carried across.
    """
    from kidneymatch.ingestion.telegram_html import MediaReference

    rows = con.execute(
        "SELECT source_file, telegram_message_id, dom_id, sent_at_raw, sender_display_name, "
        "sender_is_inherited, forwarded_from_display_name, reply_to_message_id, reply_to_file, "
        "is_joined, json_array_length(media) "
        "FROM source_message WHERE export_id = ? "
        "ORDER BY sent_at_raw IS NULL, sent_at_raw, source_file, telegram_message_id",
        (export_id,),
    ).fetchall()

    from kidneymatch.ingestion.telegram_html import parse_timestamp

    messages: list[TelegramMessageSource] = []
    for row in rows:
        (
            source_file,
            message_id,
            dom_id,
            sent_raw,
            sender,
            inherited,
            forwarded,
            reply_id,
            reply_file,
            joined,
            n_media,
        ) = row
        messages.append(
            TelegramMessageSource(
                telegram_message_id=int(message_id),
                source_file=source_file,
                dom_id=dom_id,
                sent_at=parse_timestamp(sent_raw) if sent_raw else None,
                sent_at_raw=sent_raw,
                sender_display_name=sender,
                sender_is_inherited=bool(inherited),
                forwarded_from_display_name=forwarded,
                forwarded_original_at=None,
                forwarded_original_at_raw=None,
                reply_to_message_id=int(reply_id) if reply_id is not None else None,
                reply_to_file=reply_file,
                is_joined=bool(joined),
                raw_text="",
                media=tuple(
                    MediaReference(href=None, thumbnail_src=None, kind="PHOTO")
                    for _ in range(int(n_media or 0))
                ),
            )
        )
    return messages


def run(database: Path) -> int:
    if not database.exists():
        print(f"missing {database}; run scripts/ingest_export.py first")
        return 2
    con = sqlite3.connect(database)
    con.executescript(SCHEMA)

    exports = [row[0] for row in con.execute("SELECT export_id FROM source_export")]
    if not exports:
        print("no exports in the source store")
        return 2

    for export_id in exports:
        started = time.perf_counter()
        messages = read_messages(con, export_id)
        known = {message.telegram_message_id for message in messages}
        bundles = build_bundles(messages, known_message_ids=known)
        suggestions = suggest_adjacent_links(bundles)

        # Rebuild rather than append: this is a derivation, and a stale bundle
        # from a previous bundler version is worse than none.
        for table in (
            "message_bundle",
            "bundle_message",
            "bundle_reply_link",
            "bundle_adjacency_suggestion",
        ):
            con.execute(f"DELETE FROM {table} WHERE export_id = ?", (export_id,))  # noqa: S608

        con.executemany(
            "INSERT INTO message_bundle VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    export_id,
                    b.bundle_id,
                    b.source_file,
                    b.primary_message_id,
                    b.bundle_type.value,
                    b.confidence.value,
                    b.review_status.value,
                    b.poster_display_name,
                    "|".join(b.forwarded_authors),
                    len(b.members),
                    b.n_media,
                    b.started_at.isoformat() if b.started_at else None,
                    BUNDLER_VERSION,
                )
                for b in bundles
            ],
        )
        con.executemany(
            "INSERT INTO bundle_message VALUES (?,?,?,?)",
            [
                (export_id, b.bundle_id, m.telegram_message_id, m.relation.value)
                for b in bundles
                for m in b.members
            ],
        )
        con.executemany(
            "INSERT OR IGNORE INTO bundle_reply_link VALUES (?,?,?,?,?)",
            [
                (export_id, b.bundle_id, link.to_message_id, link.to_file, int(link.resolved))
                for b in bundles
                for link in b.reply_context
            ],
        )
        con.executemany(
            "INSERT OR IGNORE INTO bundle_adjacency_suggestion VALUES (?,?,?,?,?,?,?)",
            [
                (
                    export_id,
                    s.from_bundle_id,
                    s.to_bundle_id,
                    s.relation.value,
                    s.review_status.value,
                    s.seconds_apart,
                    s.reason,
                )
                for s in suggestions
            ],
        )
        con.commit()

        elapsed = time.perf_counter() - started
        print(f"export {export_id}  ({elapsed:.1f}s)")
        print(f"  messages              {len(messages):>9,}")
        print(f"  bundles               {len(bundles):>9,}")
        for kind in ("SINGLE", "JOINED_RUN", "MEDIA_GROUP"):
            count = sum(1 for b in bundles if b.bundle_type.value == kind)
            print(f"    {kind:<20}{count:>9,}")
        needs_review = sum(1 for b in bundles if b.review_status.value == "REVIEW_SUGGESTED")
        print(f"  bundles needing review{needs_review:>9,}")
        print(f"  reply links           {sum(len(b.reply_context) for b in bundles):>9,}")
        print(f"  adjacency suggestions {len(suggestions):>9,}")

    con.close()
    print(
        "\nA bundle is one posting act, not a person and not a patient. "
        "Adjacency suggestions merge nothing: they are a queue for a human."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "data/derived/source.sqlite")
    args = parser.parse_args()
    return run(args.database)


if __name__ == "__main__":
    raise SystemExit(main())
