"""Store parsed Telegram messages so that re-importing changes nothing.

`HIST-001` acceptance: *the same export imported twice produces no duplicate
source records*. That is a property of the write, not of the parse, so it lives
here.

The identity of a source record is `(export id, file, telegram message id)`.
The export id is derived from the content of the `messages*.html` pages, so a
re-run over the same export writes nothing and a genuinely different export is
a different export rather than a silent overwrite.

`content_hash` decides whether a row changed. When it has not, `first_seen_utc`
is left alone: an import that re-reads unchanged history must not look like new
evidence. When it has — the operator re-exported the chat and Telegram now says
something different, or the parser was fixed — the row is updated and
`last_seen_utc` and `parser_version` move, so the two cases stay distinguishable
afterwards.

Raw text is written once and never rewritten in place by anything but a real
content change, which is what "raw source text is immutable" means for a store
that has to tolerate re-import.

Output is PHI: it belongs in gitignored `data/derived/`.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from kidneymatch.ingestion.telegram_html import (
    PARSER_VERSION,
    ParsedExport,
    TelegramMessageSource,
    export_files,
    parse_export,
)

SCHEMA_VERSION = "source/v1"

SCHEMA = """
CREATE TABLE IF NOT EXISTS source_export (
    export_id        TEXT PRIMARY KEY,
    source_path      TEXT NOT NULL,
    format           TEXT NOT NULL,
    n_files          INTEGER NOT NULL,
    first_imported_utc TEXT NOT NULL,
    last_imported_utc  TEXT NOT NULL,
    importer_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_message (
    export_id            TEXT NOT NULL,
    source_file          TEXT NOT NULL,
    telegram_message_id  INTEGER NOT NULL,
    dom_id               TEXT NOT NULL,
    content_hash         TEXT NOT NULL,
    parser_version       TEXT NOT NULL,
    sent_at_raw          TEXT,
    sender_display_name  TEXT,
    sender_is_inherited  INTEGER NOT NULL,
    forwarded_from_display_name TEXT,
    forwarded_original_at_raw   TEXT,
    reply_to_message_id  INTEGER,
    reply_to_file        TEXT,
    is_joined            INTEGER NOT NULL,
    raw_text             TEXT NOT NULL,
    media                TEXT NOT NULL,
    contact_evidence     TEXT NOT NULL,
    unparsed             TEXT NOT NULL,
    first_seen_utc       TEXT NOT NULL,
    last_seen_utc        TEXT NOT NULL,
    PRIMARY KEY (export_id, source_file, telegram_message_id)
);

CREATE TABLE IF NOT EXISTS source_service_event (
    export_id           TEXT NOT NULL,
    source_file         TEXT NOT NULL,
    dom_id              TEXT NOT NULL,
    telegram_message_id INTEGER,
    text                TEXT NOT NULL,
    PRIMARY KEY (export_id, source_file, dom_id)
);

CREATE TABLE IF NOT EXISTS source_unparsed (
    export_id   TEXT NOT NULL,
    fragment    TEXT NOT NULL,
    PRIMARY KEY (export_id, fragment)
);
"""


@dataclass(frozen=True, slots=True)
class IngestReport:
    """What one import actually changed."""

    export_id: str
    files: int
    messages: int
    inserted: int
    unchanged: int
    updated: int
    service_events: int
    unparsed: int

    @property
    def idempotent(self) -> bool:
        """True when this import wrote no new evidence."""
        return self.inserted == 0 and self.updated == 0


def export_id_for(directory: Path) -> str:
    """A stable id for the content of an export's message pages.

    Derived from the bytes rather than the path or the modification time: the
    same archive copied elsewhere is the same export, and touching a file is
    not a new one.
    """
    digest = hashlib.blake2b(digest_size=16)
    for path in export_files(directory):
        digest.update(path.name.encode("utf-8"))
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


def _row(export_id: str, message: TelegramMessageSource, now: str) -> tuple[object, ...]:
    return (
        export_id,
        message.source_file,
        message.telegram_message_id,
        message.dom_id,
        message.content_hash,
        PARSER_VERSION,
        message.sent_at_raw,
        message.sender_display_name,
        int(message.sender_is_inherited),
        message.forwarded_from_display_name,
        message.forwarded_original_at_raw,
        message.reply_to_message_id,
        message.reply_to_file,
        int(message.is_joined),
        message.raw_text,
        json.dumps([asdict(m) for m in message.media], ensure_ascii=False),
        json.dumps([asdict(c) for c in message.contact_evidence], ensure_ascii=False),
        json.dumps(list(message.unparsed), ensure_ascii=False),
        now,
        now,
    )


def write(
    con: sqlite3.Connection, export_id: str, parsed: ParsedExport, path: Path
) -> IngestReport:
    """Write a parsed export, leaving unchanged rows untouched."""
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    known = {
        (source_file, message_id): content_hash
        for source_file, message_id, content_hash in con.execute(
            "SELECT source_file, telegram_message_id, content_hash FROM source_message "
            "WHERE export_id = ?",
            (export_id,),
        )
    }

    inserted = unchanged = updated = 0
    for message in parsed.messages:
        key = (message.source_file, message.telegram_message_id)
        existing = known.get(key)
        if existing == message.content_hash:
            # Same evidence, read again. Only the sighting moves.
            con.execute(
                "UPDATE source_message SET last_seen_utc = ? WHERE export_id = ? "
                "AND source_file = ? AND telegram_message_id = ?",
                (now, export_id, *key),
            )
            unchanged += 1
            continue
        placeholders = ",".join("?" * 20)
        con.execute(
            f"INSERT OR REPLACE INTO source_message VALUES ({placeholders})",
            _row(export_id, message, now),
        )
        if existing is None:
            inserted += 1
        else:
            updated += 1

    con.executemany(
        "INSERT OR REPLACE INTO source_service_event VALUES (?,?,?,?,?)",
        [
            (export_id, event.source_file, event.dom_id, event.telegram_message_id, event.text)
            for event in parsed.service_events
        ],
    )
    con.executemany(
        "INSERT OR IGNORE INTO source_unparsed VALUES (?,?)",
        [(export_id, fragment) for fragment in parsed.unparsed],
    )
    con.execute(
        "INSERT INTO source_export VALUES (?,?,?,?,?,?,?) "
        "ON CONFLICT(export_id) DO UPDATE SET last_imported_utc = excluded.last_imported_utc, "
        "importer_version = excluded.importer_version",
        (
            export_id,
            str(path),
            "HTML",
            len(parsed.files),
            now,
            now,
            PARSER_VERSION,
        ),
    )
    con.commit()
    return IngestReport(
        export_id=export_id,
        files=len(parsed.files),
        messages=len(parsed.messages),
        inserted=inserted,
        unchanged=unchanged,
        updated=updated,
        service_events=len(parsed.service_events),
        unparsed=len(parsed.unparsed),
    )


def ingest(directory: Path, database: Path) -> IngestReport:
    """Parse an export and write it. Running this twice changes nothing."""
    parsed = parse_export(directory)
    export_id = export_id_for(directory)
    con = connect(database)
    try:
        return write(con, export_id, parsed, directory)
    finally:
        con.close()
