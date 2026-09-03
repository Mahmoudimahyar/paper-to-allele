"""Parsing Telegram's HTML export into immutable source records.

Written against `docs/ingestion/TELEGRAM_HTML_EXPORT_STRUCTURE.md`, which was
derived from the exporter's own source. Every case here is a shape the real
archive contains, and several of them are traps that a reasonable-looking parser
gets wrong: a joined message has no sender at all, a date divider's id is not a
message id, and a forwarded message names two different people.

The fixture is entirely synthetic. Nothing in this file touches the archive.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from kidneymatch.ingestion.telegram_html import (
    PARSER_VERSION,
    ContactEvidence,
    parse_export,
    parse_file,
)

pytestmark = pytest.mark.task("HIST-001")

ROOT = Path(__file__).resolve().parents[2]
EXPORT = ROOT / "tests/fixtures/synthetic/telegram_export"
TEHRAN = timezone(timedelta(hours=3, minutes=30))


@pytest.fixture(scope="module")
def page():
    return parse_file(EXPORT / "messages.html")


@pytest.fixture(scope="module")
def export():
    return parse_export(EXPORT)


def by_id(parsed):
    return {m.telegram_message_id: m for m in parsed.messages}


# --- the shapes the acceptance criterion names ---------------------------


def test_every_required_message_shape_parses(page) -> None:
    """Acceptance 0: normal, joined, forwarded, reply, image-only, text-only
    and service fixtures parse."""
    messages = by_id(page)
    assert set(messages) == {101, 102, 103, 104, 105, 106, 107, 108, 109}
    assert [event.text for event in page.service_events] == ["1 January 2020", "2 January 2020"]


def test_a_text_only_message_keeps_its_text_and_claims_no_media(page) -> None:
    message = by_id(page)[101]
    assert message.raw_text.startswith("Synthetic text-only message")
    assert message.media == ()
    assert message.sender_display_name == "Synthetic Poster One"


def test_an_image_only_message_has_media_and_no_text(page) -> None:
    message = by_id(page)[103]
    assert message.raw_text == ""
    assert len(message.media) == 1
    assert message.media[0].href == "photos/photo_1@01-01-2020_10-08-10.jpg"
    assert message.media[0].thumbnail_src == "photos/photo_1@01-01-2020_10-08-10_thumb.jpg"


# --- the joined trap ------------------------------------------------------


def test_a_joined_message_inherits_the_previous_sender(page) -> None:
    """The single most important fact about this format.

    A joined message omits the `from_name` block entirely. Reading that as
    "unknown sender" would orphan a large part of the archive, so the sender is
    carried forward — and the record still says it was inherited, because that
    is a display grouping and not evidence about the subject.
    """
    joined = by_id(page)[102]
    assert joined.is_joined is True
    assert joined.sender_display_name == "Synthetic Poster One"
    assert joined.sender_is_inherited is True
    assert by_id(page)[101].sender_is_inherited is False


def test_a_service_message_breaks_the_sender_chain() -> None:
    """The exporter never joins across a service message, so neither may the
    carry-forward: a sender must not leak past a date divider into a message
    that genuinely has none."""
    html = """<div class="history">
     <div class="message default clearfix" id="message1"><div class="body">
      <div class="from_name">Someone</div><div class="text">first</div></div></div>
     <div class="message service" id="message-1">
      <div class="body details">2 January 2020</div></div>
     <div class="message default clearfix joined" id="message2"><div class="body">
      <div class="text">orphan</div></div></div>
    </div>"""
    parsed = parse_file(_write(html))
    assert by_id(parsed)[2].sender_display_name is None


def _write(html: str, name: str = "messages.html") -> Path:
    import tempfile

    directory = Path(tempfile.mkdtemp(prefix="km-telegram-"))
    path = directory / name
    path.write_text(f"<html><body>{html}</body></html>", encoding="utf-8")
    return path


# --- invariant: message ID is not user ID ---------------------------------


@pytest.mark.invariant("HIST-001", "message ID is not user ID")
def test_a_message_id_is_never_used_as_an_actor_identity(page) -> None:
    """`message1301549` is a message id. Nothing in this export identifies a
    user, and inventing an actor id from the message id would silently make
    every message its own author."""
    messages = by_id(page)
    assert messages[101].sender_display_name == messages[107].sender_display_name
    assert messages[101].telegram_message_id != messages[107].telegram_message_id
    for message in messages.values():
        for value in (message.sender_display_name, message.forwarded_from_display_name):
            assert value is None or str(message.telegram_message_id) not in value


def test_a_date_divider_is_not_a_message(page) -> None:
    """Dividers carry negative, monotonically decreasing ids that are not
    Telegram ids at all. A parser that trusts `id` invents messages."""
    assert all(message.telegram_message_id > 0 for message in page.messages)
    assert [event.dom_id for event in page.service_events] == ["message-1", "message-2"]
    assert all(event.telegram_message_id is None for event in page.service_events)


# --- invariant: current and forwarded actor remain distinct ---------------


@pytest.mark.invariant("HIST-001", "current and forwarded actor remain distinct")
def test_a_forwarded_message_names_two_different_people(page) -> None:
    """And the current poster is READ, not inherited.

    Measured over the real archive: `forwarded body` is nested inside the
    message's own `body`, which carries the current poster's `from_name`. A
    parser that treats the forwarded block as the whole body loses that name on
    every forwarded message and silently attributes the post to whoever spoke
    last — 37% of this archive, attributed to the wrong person.
    """
    forwarded = by_id(page)[106]
    assert forwarded.forwarded_from_display_name == "Synthetic Original Author"
    assert forwarded.sender_display_name == "Synthetic Poster Three"
    assert forwarded.sender_is_inherited is False
    assert forwarded.sender_display_name != forwarded.forwarded_from_display_name
    assert forwarded.forwarded_original_at == datetime(2019, 12, 15, 8, 30, 0, tzinfo=TEHRAN)
    assert forwarded.sent_at == datetime(2020, 1, 1, 10, 25, 0, tzinfo=TEHRAN)


def test_a_forwarded_message_keeps_its_own_text_and_media(page) -> None:
    """The content lives in the forwarded block; only the author does not."""
    forwarded = by_id(page)[106]
    assert forwarded.raw_text.startswith("Forwarded content.")


def test_a_message_that_is_not_forwarded_claims_no_original_author(page) -> None:
    assert by_id(page)[101].forwarded_from_display_name is None
    assert by_id(page)[101].forwarded_original_at is None


# --- timestamps -----------------------------------------------------------


def test_a_modern_timestamp_keeps_its_offset(page) -> None:
    assert by_id(page)[101].sent_at == datetime(2020, 1, 1, 10, 0, 0, tzinfo=TEHRAN)


def test_a_pre_2022_timestamp_has_no_zone_and_does_not_get_one_invented(page) -> None:
    """The offset suffix arrived in tdesktop 2022 and this archive predates it.
    Assuming a zone would shift every early message by hours."""
    message = by_id(page)[108]
    assert message.sent_at == datetime(2020, 1, 2, 9, 0, 0)
    assert message.sent_at.tzinfo is None
    assert message.sent_at_raw == "02.01.2020 09:00:00"


# --- replies --------------------------------------------------------------


def test_a_same_file_reply_links_by_id(page) -> None:
    assert by_id(page)[105].reply_to_message_id == 101
    assert by_id(page)[105].reply_to_file is None


def test_a_cross_file_reply_carries_its_file_and_has_no_onclick(export) -> None:
    """The cross-file shape has no `onclick`, so a parser that only reads
    `GoToMessage(...)` loses every reply that crosses a page boundary."""
    message = by_id(export)[201]
    assert message.reply_to_message_id == 101
    assert message.reply_to_file == "messages.html"


# --- media ----------------------------------------------------------------


def test_a_document_that_was_not_exported_records_why(page) -> None:
    """The generic block is a `div`, not an `a`, and carries no href. Treating
    its absence as "no media" would lose the fact that a document existed."""
    media = by_id(page)[107].media
    assert len(media) == 1
    assert media[0].href is None
    assert media[0].title == "synthetic_report.pdf"
    assert media[0].absence_reason == "Not included, change data exporting settings to download."


def test_a_photo_whose_original_is_absent_still_names_the_original(page) -> None:
    """The export writes the href whether or not the file was downloaded, so
    the parser reports the reference and the filesystem answers separately."""
    media = by_id(page)[104].media
    assert media[0].href == "photos/photo_2@01-01-2020_10-12-00.jpg"
    assert not (EXPORT / media[0].href).exists()
    assert (EXPORT / media[0].thumbnail_src).exists()


# --- invariant: phone/username links are unverified contact evidence ------


@pytest.mark.invariant("HIST-001", "phone/username links are unverified contact evidence")
def test_contact_links_are_recorded_as_unverified_evidence(page) -> None:
    """A t.me link in a broker's advertisement is a claim about a channel, not
    proof of who owns it. The record must not be able to express verification.
    """
    evidence = by_id(page)[109].contact_evidence
    assert ContactEvidence(kind="USERNAME", value="synthetic_broker") in evidence
    assert ContactEvidence(kind="PHONE", value="+15550100") in evidence
    assert all(item.verified is False for item in evidence)
    with pytest.raises(AttributeError):
        evidence[0].verified = True  # type: ignore[misc]  # frozen


def test_a_message_without_links_claims_no_contact(page) -> None:
    assert by_id(page)[101].contact_evidence == ()


# --- invariant: raw source text is immutable ------------------------------


@pytest.mark.invariant("HIST-001", "raw source text is immutable")
def test_raw_text_is_preserved_exactly_and_cannot_be_mutated(page) -> None:
    message = by_id(page)[109]
    assert "@synthetic_broker" in message.raw_text
    assert "+1 555 0100" in message.raw_text, "the text keeps the human spacing"
    with pytest.raises(AttributeError):
        message.raw_text = "edited"  # type: ignore[misc]


def test_the_record_carries_a_locator_back_to_its_fragment(page) -> None:
    """Provenance: every derived fact must be traceable to the source fragment
    it came from."""
    message = by_id(page)[101]
    assert message.source_file == "messages.html"
    assert message.dom_id == "message101"


# --- acceptance 2: unparsed fragments are preserved or classified ---------


def test_an_unrecognised_block_is_kept_rather_than_dropped() -> None:
    """A future Telegram version will add a block this parser does not know.
    Silently dropping it would lose evidence with no trace; the record has to
    say that something was there and what it looked like."""
    html = """<div class="history">
     <div class="message default clearfix" id="message1"><div class="body">
      <div class="from_name">Someone</div>
      <div class="text">hello</div>
      <div class="poll_question some_future_block">Who is the donor?</div>
     </div></div></div>"""
    message = by_id(parse_file(_write(html)))[1]
    assert message.raw_text == "hello"
    assert len(message.unparsed) == 1
    assert "poll_question" in message.unparsed[0]
    assert "Who is the donor?" in message.unparsed[0]


def test_a_known_but_ignored_block_is_not_reported_as_unparsed(page) -> None:
    """The userpic and the date are read or deliberately skipped; reporting
    them as unknown would bury a real unknown in noise."""
    assert all(message.unparsed == () for message in page.messages)


# --- invariant: re-ingestion is idempotent --------------------------------


@pytest.mark.invariant("HIST-001", "re-ingestion is idempotent")
def test_parsing_the_same_export_twice_yields_identical_records(export) -> None:
    """Acceptance 1: the same export imported twice produces no duplicates.

    The parser is pure, so the guarantee it can offer is a stable identity per
    message; whatever stores these keys on it.
    """
    again = parse_export(EXPORT)
    assert [m.content_hash for m in export.messages] == [m.content_hash for m in again.messages]
    keys = [(m.source_file, m.telegram_message_id) for m in export.messages]
    assert len(keys) == len(set(keys))


def test_the_content_hash_changes_when_the_content_does() -> None:
    """An idempotency key that ignored the text would let an edited export
    overwrite nothing and be reported as already imported."""
    first = by_id(
        parse_file(
            _write(
                '<div class="history"><div class="message default clearfix" id="message1">'
                '<div class="body"><div class="text">one</div></div></div></div>'
            )
        )
    )[1]
    second = by_id(
        parse_file(
            _write(
                '<div class="history"><div class="message default clearfix" id="message1">'
                '<div class="body"><div class="text">two</div></div></div></div>'
            )
        )
    )[1]
    assert first.content_hash != second.content_hash


def test_the_parser_records_its_own_version(export) -> None:
    """Re-parsing after a parser fix must be distinguishable from a re-import
    of unchanged data, or a corrected reading can never be published."""
    assert export.parser_version == PARSER_VERSION
    assert PARSER_VERSION.startswith("telegram-html/")


# --- the whole export -----------------------------------------------------


def test_pages_are_read_in_order_and_pagination_is_not_a_message(export) -> None:
    assert [m.telegram_message_id for m in export.messages] == [
        101,
        102,
        103,
        104,
        105,
        106,
        107,
        108,
        109,
        201,
    ]
    assert export.files == ("messages.html", "messages2.html")
