"""The synthetic Telegram export fixture, and the code that already reads it.

Milestone 1 of `docs/exec-plans/active/MVP-HIST-001-bootstrap-ingestion.md` is a
fixture corpus covering the message shapes the parser must handle. These tests
guard the corpus itself: a fixture that quietly loses its `joined` message would
let HIST-001 pass while never exercising the hardest case.

Structure is documented in `docs/ingestion/TELEGRAM_HTML_EXPORT_STRUCTURE.md`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from kidneymatch.domain.evidence import MediaQuality
from kidneymatch.ingestion.media import resolve_best_available_media

ROOT = Path(__file__).resolve().parents[2]
EXPORT = ROOT / "tests/fixtures/synthetic/telegram_export"


@pytest.fixture(scope="module")
def html() -> str:
    return (EXPORT / "messages.html").read_text(encoding="utf-8")


def test_the_export_fixture_exists() -> None:
    assert (EXPORT / "messages.html").is_file()
    assert (EXPORT / "messages2.html").is_file()


@pytest.mark.parametrize(
    ("shape", "needle"),
    [
        ("service date divider", '<div class="message service" id="message-1">'),
        ("normal message", '<div class="message default clearfix" id="message101">'),
        ("joined message", '<div class="message default clearfix joined" id="message102">'),
        ("photo with original present", 'href="photos/photo_1@01-01-2020_10-08-10.jpg"'),
        ("photo with original absent", 'href="photos/photo_2@01-01-2020_10-12-00.jpg"'),
        ("same-file reply", 'onclick="return GoToMessage(101)"'),
        ("forwarded block", '<div class="forwarded body">'),
        ("not-exported document", "Not included, change data exporting settings to download."),
        ("pre-2022 timestamp", 'title="02.01.2020 09:00:00"'),
    ],
)
def test_the_corpus_covers_every_required_message_shape(html: str, shape: str, needle: str) -> None:
    assert needle in html, f"fixture no longer covers: {shape}"


def test_a_joined_message_carries_no_sender(html: str) -> None:
    """The property that makes joined messages dangerous to parse.

    If a fixture edit ever gave the joined message a `from_name`, the parser
    could pass its tests while being wrong about the real archive.
    """
    joined = html.split('id="message102"')[1].split("</div>\n\n     </div>")[0]
    # Assert on the ELEMENT, not the word: the message text legitimately
    # mentions "from_name" while describing why its absence matters.
    assert '<div class="from_name">' not in joined
    assert 'class="pull_left userpic_wrap"' not in joined


def test_service_dividers_use_negative_ids(html: str) -> None:
    """Divider ids are not Telegram message ids; a parser must not treat them as such."""
    service_ids = re.findall(r'<div class="message service" id="message(-?\d+)">', html)
    assert service_ids, "no service messages in the fixture"
    assert all(int(value) < 0 for value in service_ids)


def test_normal_message_ids_are_positive(html: str) -> None:
    normal = re.findall(r'<div class="message default[^"]*" id="message(-?\d+)">', html)
    assert normal
    assert all(int(value) > 0 for value in normal)


def test_text_content_is_emitted_at_column_zero(html: str) -> None:
    """The generator does not indent text nodes.

    A parser that locates text by indentation would work on hand-written
    fixtures and fail on real exports.
    """
    assert "\nSynthetic text-only message. No media, no contact details.\n" in html


# --------------------------------------------------------------------------
# The existing media resolver, against realistic input
# --------------------------------------------------------------------------


@pytest.mark.task("MEDIA-001")
def test_the_resolver_prefers_a_present_original(html: str) -> None:
    resolved = resolve_best_available_media(
        EXPORT,
        "photos/photo_1@01-01-2020_10-08-10.jpg",
        "photos/photo_1@01-01-2020_10-08-10_thumb.jpg",
    )
    assert resolved is not None
    assert resolved.quality is MediaQuality.HIGH_RES_AVAILABLE
    assert resolved.path.name == "photo_1@01-01-2020_10-08-10.jpg"


@pytest.mark.task("MEDIA-001")
@pytest.mark.invariant("DEDUPE-001", "missing higher-resolution asset is not treated as an error")
def test_the_resolver_falls_back_to_the_thumbnail_on_the_real_fixture() -> None:
    """message104 references an original that the export never wrote.

    This is the archive's dominant case, and it must yield a usable asset
    marked THUMBNAIL_ONLY rather than an error or a fabricated original.
    """
    resolved = resolve_best_available_media(
        EXPORT,
        "photos/photo_2@01-01-2020_10-12-00.jpg",
        "photos/photo_2@01-01-2020_10-12-00_thumb.jpg",
    )
    assert resolved is not None
    assert resolved.quality is MediaQuality.THUMBNAIL_ONLY
    assert resolved.path.is_file()


def test_the_fixture_contains_no_plausible_personal_data() -> None:
    """Fixtures are the easiest place for real data to leak in unnoticed."""
    corpus = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in EXPORT.rglob("*")
        if p.is_file() and p.suffix in {".html", ".md"}
    )
    assert not re.search(r"(?:\+98|0098|\b0)9\d{9}\b", corpus), "Iranian mobile number in fixture"
    assert not re.search(r"\b\d{10}\b", corpus), "10-digit national-ID-shaped value in fixture"
