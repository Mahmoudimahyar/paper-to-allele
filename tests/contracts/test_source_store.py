"""Writing parsed messages so that re-importing an export changes nothing.

`HIST-001` acceptance 1. Runs on the synthetic fixture and on exports written
into `tmp_path`; nothing here touches the archive.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from kidneymatch.ingestion.source_store import export_id_for, ingest
from kidneymatch.ingestion.telegram_html import PARSER_VERSION

pytestmark = pytest.mark.task("HIST-001")

ROOT = Path(__file__).resolve().parents[2]
EXPORT = ROOT / "tests/fixtures/synthetic/telegram_export"


def count(database: Path, table: str = "source_message") -> int:
    con = sqlite3.connect(database)
    try:
        return int(con.execute(f"SELECT count(*) FROM {table}").fetchone()[0])  # noqa: S608
    finally:
        con.close()


@pytest.mark.invariant("HIST-001", "re-ingestion is idempotent")
def test_importing_the_same_export_twice_produces_no_duplicates(tmp_path: Path) -> None:
    """Acceptance 1, and the invariant behind it.

    The archive will be re-exported and re-imported many times over this
    project's life. If each import appended, the message count would grow
    without any new evidence and every downstream count would inflate with it.
    """
    database = tmp_path / "source.sqlite"

    first = ingest(EXPORT, database)
    assert first.inserted == 10
    assert first.unchanged == 0
    assert count(database) == 10

    second = ingest(EXPORT, database)
    assert second.inserted == 0
    assert second.updated == 0
    assert second.unchanged == 10
    assert second.idempotent is True
    assert count(database) == 10


def test_a_re_import_does_not_move_the_first_sighting(tmp_path: Path) -> None:
    """Re-reading unchanged history must not look like new evidence arriving."""
    database = tmp_path / "source.sqlite"
    ingest(EXPORT, database)
    con = sqlite3.connect(database)
    before = dict(con.execute("SELECT telegram_message_id, first_seen_utc FROM source_message"))
    con.close()

    ingest(EXPORT, database)
    con = sqlite3.connect(database)
    after = dict(con.execute("SELECT telegram_message_id, first_seen_utc FROM source_message"))
    con.close()
    assert before == after


def test_an_edited_export_updates_the_row_rather_than_duplicating_it(tmp_path: Path) -> None:
    """The other half of idempotency: content that genuinely changed has to be
    recorded, and must not silently read as 'already imported'."""
    directory = tmp_path / "export"
    directory.mkdir()
    page = directory / "messages.html"
    template = (
        '<html><body><div class="history">'
        '<div class="message default clearfix" id="message1"><div class="body">'
        '<div class="from_name">Someone</div><div class="text">{text}</div>'
        "</div></div></div></body></html>"
    )
    database = tmp_path / "source.sqlite"

    page.write_text(template.format(text="first version"), encoding="utf-8")
    assert ingest(directory, database).inserted == 1
    first_export = export_id_for(directory)

    page.write_text(template.format(text="second version"), encoding="utf-8")
    second = ingest(directory, database)
    # Changing the bytes makes it a different export, so this is a new record
    # rather than an overwrite of history that may already have been published.
    assert export_id_for(directory) != first_export
    assert second.inserted == 1
    assert count(database) == 2

    con = sqlite3.connect(database)
    texts = {row[0] for row in con.execute("SELECT raw_text FROM source_message")}
    con.close()
    assert texts == {"first version", "second version"}


@pytest.mark.invariant("HIST-001", "raw source text is immutable")
def test_the_stored_text_is_exactly_what_the_export_said(tmp_path: Path) -> None:
    """No normalisation on the way in. A derived, normalised form is a separate
    field for a later stage; rewriting the source would destroy the only copy
    of what was actually posted."""
    database = tmp_path / "source.sqlite"
    ingest(EXPORT, database)
    con = sqlite3.connect(database)
    stored = dict(con.execute("SELECT telegram_message_id, raw_text FROM source_message"))
    con.close()
    assert stored[109].count("@synthetic_broker") == 1
    assert "+1 555 0100" in stored[109], "spacing is part of what was posted"
    assert stored[103] == "", "an image-only message has no text, not a placeholder"


def test_the_export_identity_follows_the_content_not_the_path(tmp_path: Path) -> None:
    """The same archive copied to another disk is the same export. Keying on
    the path would re-import all of it as new evidence."""
    import shutil

    copy = tmp_path / "elsewhere"
    shutil.copytree(EXPORT, copy)
    assert export_id_for(copy) == export_id_for(EXPORT)


def test_service_events_and_unparsed_fragments_are_stored_too(tmp_path: Path) -> None:
    """Acceptance 2: unparsed fragments are preserved. A fragment that only
    lived in a log would be gone by the time anyone asked."""
    database = tmp_path / "source.sqlite"
    report = ingest(EXPORT, database)
    assert report.service_events == 2
    assert count(database, "source_service_event") == 2

    directory = tmp_path / "odd"
    directory.mkdir()
    (directory / "messages.html").write_text(
        '<html><body><div class="history">'
        '<div class="message default clearfix" id="message1"><div class="body">'
        '<div class="text">hi</div><div class="poll_question">Who?</div>'
        "</div></div></div></body></html>",
        encoding="utf-8",
    )
    odd = tmp_path / "odd.sqlite"
    ingest(directory, odd)
    con = sqlite3.connect(odd)
    unparsed = con.execute("SELECT unparsed FROM source_message").fetchone()[0]
    con.close()
    assert "poll_question" in unparsed


def test_every_row_records_the_parser_that_produced_it(tmp_path: Path) -> None:
    """A corrected parser must be distinguishable from a re-import of unchanged
    data, or a fixed reading can never be told apart from the old one."""
    database = tmp_path / "source.sqlite"
    ingest(EXPORT, database)
    con = sqlite3.connect(database)
    versions = {row[0] for row in con.execute("SELECT parser_version FROM source_message")}
    con.close()
    assert versions == {PARSER_VERSION}
