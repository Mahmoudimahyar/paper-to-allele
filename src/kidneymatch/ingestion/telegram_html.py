"""Read Telegram's HTML export into immutable source records.

`HIST-001`. The structure this reads is documented in
`docs/ingestion/TELEGRAM_HTML_EXPORT_STRUCTURE.md`, taken from the exporter's
own source rather than guessed from one archive.

## What this module refuses to do

It reads. It does not interpret. No medical value, no candidate identity, no
bundle: those are `HIST-002` and later, and mixing them in here would make the
source layer unreproducible.

Three properties of the format make a naive parser silently wrong, and each has
a test:

* **A joined message has no sender at all.** The exporter omits the whole
  `from_name` block when it groups a message with the one above. Reading that
  as "unknown" would orphan a large share of the archive, so the sender is
  carried forward — and the record says `sender_is_inherited`, because joining
  is a display decision (same author, same day, within 15 minutes) and not
  evidence that two messages are about the same person.
* **A date divider's id is not a message id.** Dividers get negative,
  monotonically decreasing ids. A parser that trusts `id` invents messages.
* **A forwarded message names two people.** The enclosing message carries the
  current poster; the forwarded block carries the original author. The product
  constitution keeps them apart, so this keeps them in separate fields.

## Identity

The HTML export contains **no stable user id** (KI-002) — the `userpic1..N`
class is a colour index, not an identity. So this module reports display names
and nothing more; resolving those into actors is a later, evidence-weighted
decision.

Links found in the text are recorded as `ContactEvidence` with `verified=False`
and no way to set it otherwise: a `t.me` address in a broker's advertisement is
a claim about a channel, never proof of who owns it.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bs4.element import Tag

PARSER_VERSION = "telegram-html/v1"

# `message<ID>`; a leading minus marks a date divider, not a Telegram id.
_DOM_ID = re.compile(r"^message(-?\d+)$")

# "03.12.2025 19:07:28 UTC+02:00", and the pre-2022 form without the suffix.
_TIMESTAMP = re.compile(
    r"^(?P<day>\d{2})\.(?P<month>\d{2})\.(?P<year>\d{4})\s+"
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})"
    r"(?:\s+UTC(?P<sign>[+-])(?P<offhour>\d{2}):(?P<offminute>\d{2}))?$"
)

_GO_TO_MESSAGE = re.compile(r"GoToMessage\((\d+)\)")
_REPLY_HREF = re.compile(r"^(?P<file>[^#]*)#go_to_message(?P<id>\d+)$")

# The three sentences the exporter writes when a file was not downloaded.
ABSENCE_REASONS = frozenset(
    {
        "Unavailable, please try again later.",
        "Exceeds maximum size, change data exporting settings to download.",
        "Not included, change data exporting settings to download.",
    }
)

# Blocks that are read elsewhere or carry nothing about the subject. Anything
# outside this set and outside the handled cases is reported as unparsed rather
# than dropped, so a future Telegram version cannot lose evidence silently.
_IGNORED_CLASSES = frozenset({"pull_left", "userpic_wrap", "date", "details", "pull_right"})

_MEDIA_FOLDERS = {
    "photos": "PHOTO",
    "video_files": "VIDEO",
    "animations": "ANIMATION",
    "stickers": "STICKER",
    "voice_messages": "VOICE",
    "round_video_messages": "ROUND_VIDEO",
    "files": "FILE",
}


@dataclass(frozen=True, slots=True)
class ContactEvidence:
    """A link someone published. Never verified, and it cannot be marked so."""

    kind: str  # USERNAME | PHONE | LINK
    value: str
    verified: bool = False


@dataclass(frozen=True, slots=True)
class MediaReference:
    """What the export says about one attachment.

    `href` is written whether or not the file was downloaded, so the reference
    and the file's presence on disk are separate questions; `media.py` answers
    the second.
    """

    href: str | None
    thumbnail_src: str | None
    kind: str
    title: str | None = None
    absence_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ServiceEvent:
    """A date divider, or a real service action.

    `telegram_message_id` is None for a divider, whose negative DOM id is a
    render artefact rather than an identifier.
    """

    source_file: str
    dom_id: str
    telegram_message_id: int | None
    text: str


@dataclass(frozen=True, slots=True)
class TelegramMessageSource:
    """One message, exactly as the export states it."""

    telegram_message_id: int
    source_file: str
    dom_id: str
    sent_at: datetime | None
    sent_at_raw: str | None
    sender_display_name: str | None
    sender_is_inherited: bool
    forwarded_from_display_name: str | None
    forwarded_original_at: datetime | None
    forwarded_original_at_raw: str | None
    reply_to_message_id: int | None
    reply_to_file: str | None
    is_joined: bool
    raw_text: str
    media: tuple[MediaReference, ...] = ()
    contact_evidence: tuple[ContactEvidence, ...] = ()
    unparsed: tuple[str, ...] = ()

    @property
    def content_hash(self) -> str:
        """A stable identity for this message's content.

        Re-importing an unchanged export must not duplicate anything, and an
        export whose content changed must not be mistaken for one already
        imported, so the hash covers what was said and not when it was read.
        """
        parts = [
            PARSER_VERSION,
            self.source_file,
            str(self.telegram_message_id),
            self.sent_at_raw or "",
            self.sender_display_name or "",
            self.forwarded_from_display_name or "",
            self.forwarded_original_at_raw or "",
            str(self.reply_to_message_id or ""),
            self.raw_text,
            "|".join(f"{m.href or ''}>{m.thumbnail_src or ''}" for m in self.media),
        ]
        return hashlib.blake2b("\x1f".join(parts).encode("utf-8"), digest_size=16).hexdigest()


@dataclass(frozen=True, slots=True)
class ParsedExport:
    """Everything one or more export files stated."""

    files: tuple[str, ...]
    messages: tuple[TelegramMessageSource, ...] = ()
    service_events: tuple[ServiceEvent, ...] = ()
    unparsed: tuple[str, ...] = field(default_factory=tuple)
    parser_version: str = PARSER_VERSION


def _classes(node: Tag) -> list[str]:
    value = node.get("class")
    if value is None:
        return []
    return list(value) if isinstance(value, list) else str(value).split()


def _text_of(node: Tag) -> str:
    """The element's text with the exporter's own line breaks preserved.

    Block tags emit a newline and indentation but text is written at column 0,
    so stripping each line is safe and stripping the whole string is not.
    """
    return node.get_text().strip("\n").strip()


def parse_timestamp(raw: str) -> datetime | None:
    """`title="03.12.2025 19:07:28 UTC+02:00"`, and the pre-2022 form.

    The offset suffix arrived in tdesktop 2022 and this archive predates it, so
    a timestamp without one stays naive: inventing a zone would move every early
    message by hours and there is nothing in the file to justify a guess.
    """
    match = _TIMESTAMP.match(raw.strip())
    if match is None:
        return None
    parts = match.groupdict()
    tzinfo = None
    if parts["sign"] is not None:
        offset = timedelta(hours=int(parts["offhour"]), minutes=int(parts["offminute"]))
        tzinfo = timezone(-offset if parts["sign"] == "-" else offset)
    return datetime(
        int(parts["year"]),
        int(parts["month"]),
        int(parts["day"]),
        int(parts["hour"]),
        int(parts["minute"]),
        int(parts["second"]),
        tzinfo=tzinfo,
    )


def _contact_evidence(node: Tag) -> tuple[ContactEvidence, ...]:
    """Links, as claims. A published address is not an identity."""
    found: list[ContactEvidence] = []
    for anchor in node.find_all("a", href=True):
        href = str(anchor["href"]).strip()
        if href.startswith("tel:"):
            found.append(ContactEvidence(kind="PHONE", value=href[4:].replace(" ", "")))
        elif "t.me/" in href:
            username = href.split("t.me/", 1)[1].strip("/")
            if username:
                found.append(ContactEvidence(kind="USERNAME", value=username))
        elif href.startswith(("http://", "https://")):
            found.append(ContactEvidence(kind="LINK", value=href))
    seen: dict[tuple[str, str], ContactEvidence] = {}
    for item in found:
        seen.setdefault((item.kind, item.value), item)
    return tuple(seen.values())


def _media_kind(href: str | None, classes: list[str]) -> str:
    if href:
        folder = href.split("/", 1)[0]
        if folder in _MEDIA_FOLDERS:
            return _MEDIA_FOLDERS[folder]
    for name in classes:
        if name.startswith("media_") and name != "media_wrap":
            return name.removeprefix("media_").upper()
    return "UNKNOWN"


def _read_media(wrap: Tag) -> list[MediaReference]:
    """Both shapes: the sized `a.photo_wrap`, and the generic block for a file
    that was not exported (a `div`, with the reason in `div.description`)."""
    media: list[MediaReference] = []
    for anchor in wrap.find_all("a", href=True):
        image = anchor.find("img")
        href = str(anchor["href"])
        media.append(
            MediaReference(
                href=href,
                thumbnail_src=str(image["src"])
                if image is not None and image.has_attr("src")
                else None,
                kind=_media_kind(href, _classes(anchor)),
            )
        )
    if media:
        return media

    for block in wrap.find_all("div", class_="media"):
        title = block.find("div", class_="title")
        description = block.find("div", class_="description")
        reason = _text_of(description) if description is not None else None
        media.append(
            MediaReference(
                href=None,
                thumbnail_src=None,
                kind=_media_kind(None, _classes(block)),
                title=_text_of(title) if title is not None else None,
                absence_reason=reason if reason in ABSENCE_REASONS else None,
            )
        )
    if not media:
        # A media_wrap the parser does not recognise. Say so rather than
        # reporting the message as having no attachment.
        media.append(MediaReference(href=None, thumbnail_src=None, kind="UNKNOWN"))
    return media


def _read_reply(block: Tag) -> tuple[int | None, str | None]:
    """Same-file replies carry `onclick`; cross-file ones carry a filename and
    no handler; cross-chat ones carry no link at all."""
    anchor = block.find("a", href=True)
    if anchor is None:
        return None, None
    onclick = str(anchor.get("onclick") or "")
    match = _REPLY_HREF.match(str(anchor["href"]))
    if match is not None:
        return int(match.group("id")), match.group("file") or None
    found = _GO_TO_MESSAGE.search(onclick)
    return (int(found.group(1)), None) if found else (None, None)


def _read_forwarded(body: Tag) -> tuple[str | None, datetime | None, str | None]:
    name_block = body.find("div", class_="from_name")
    if name_block is None:
        return None, None, None
    date_span = name_block.find("span", class_="date")
    raw = (
        str(date_span.get("title"))
        if date_span is not None and date_span.has_attr("title")
        else None
    )
    if date_span is not None:
        date_span.extract()
    return _text_of(name_block) or None, (parse_timestamp(raw) if raw else None), raw


def parse_file(path: Path) -> ParsedExport:
    """Read one `messages*.html`. Pure: the same bytes give the same records."""
    from bs4 import BeautifulSoup

    source_file = path.name
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")

    messages: list[TelegramMessageSource] = []
    services: list[ServiceEvent] = []
    unparsed: list[str] = []
    carried_sender: str | None = None

    for node in soup.find_all("div", class_="message"):
        classes = _classes(node)
        dom_id = str(node.get("id") or "")
        match = _DOM_ID.match(dom_id)
        numeric = int(match.group(1)) if match else None

        if "service" in classes:
            body = node.find("div", class_="body")
            services.append(
                ServiceEvent(
                    source_file=source_file,
                    dom_id=dom_id,
                    # A negative id is a divider's render artefact, not an id.
                    telegram_message_id=numeric if numeric is not None and numeric > 0 else None,
                    text=_text_of(body) if body is not None else "",
                )
            )
            # The exporter never joins across a service message, so the sender
            # chain stops here too.
            carried_sender = None
            continue

        if numeric is None or numeric <= 0:
            unparsed.append(f"{source_file}: message element with unusable id {dom_id!r}")
            continue

        message, carried_sender = _read_message(node, source_file, dom_id, numeric, carried_sender)
        messages.append(message)

    return ParsedExport(
        files=(source_file,),
        messages=tuple(messages),
        service_events=tuple(services),
        unparsed=tuple(unparsed),
    )


def _read_message(
    node: Tag, source_file: str, dom_id: str, numeric: int, carried_sender: str | None
) -> tuple[TelegramMessageSource, str | None]:
    classes = _classes(node)
    is_joined = "joined" in classes

    # `class_="forwarded"` also matches `pull_left forwarded userpic_wrap`, the
    # avatar column. The block that carries the original author is the one
    # holding BOTH classes.
    forwarded_body = next(
        (
            candidate
            for candidate in node.find_all("div")
            if {"forwarded", "body"} <= set(_classes(candidate))
        ),
        None,
    )
    body = forwarded_body if forwarded_body is not None else node.find("div", class_="body")

    sent_raw: str | None = None
    sender: str | None = None
    reply_id: int | None = None
    reply_file: str | None = None
    text_parts: list[str] = []
    media: list[MediaReference] = []
    contacts: list[ContactEvidence] = []
    unparsed: list[str] = []

    forwarded_name, forwarded_at, forwarded_raw = (None, None, None)
    if forwarded_body is not None:
        forwarded_name, forwarded_at, forwarded_raw = _read_forwarded(forwarded_body)

    # The date lives on the enclosing message even when the body is forwarded.
    date_block = node.find("div", class_="date")
    if date_block is not None and date_block.has_attr("title"):
        sent_raw = str(date_block["title"])

    if body is not None:
        for child in body.find_all("div", recursive=False):
            child_classes = _classes(child)
            if "from_name" in child_classes:
                if forwarded_body is None:
                    sender = _text_of(child) or None
            elif "text" in child_classes:
                text_parts.append(_text_of(child))
                contacts.extend(_contact_evidence(child))
            elif "media_wrap" in child_classes:
                media.extend(_read_media(child))
                contacts.extend(_contact_evidence(child))
            elif "reply_to" in child_classes:
                reply_id, reply_file = _read_reply(child)
            elif "signature" in child_classes or _IGNORED_CLASSES & set(child_classes):
                continue
            else:
                unparsed.append(
                    f"{source_file}#{dom_id}: unrecognised block "
                    f"{' '.join(child_classes) or '(no class)'}: {_text_of(child)[:200]}"
                )

    sender_is_inherited = False
    if sender is None and forwarded_body is None:
        # A joined message omits from_name entirely; carry the sender forward.
        sender = carried_sender
        sender_is_inherited = sender is not None
    if forwarded_body is not None and sender is None:
        sender = carried_sender
        sender_is_inherited = sender is not None

    message = TelegramMessageSource(
        telegram_message_id=numeric,
        source_file=source_file,
        dom_id=dom_id,
        sent_at=parse_timestamp(sent_raw) if sent_raw else None,
        sent_at_raw=sent_raw,
        sender_display_name=sender,
        sender_is_inherited=sender_is_inherited,
        forwarded_from_display_name=forwarded_name,
        forwarded_original_at=forwarded_at,
        forwarded_original_at_raw=forwarded_raw,
        reply_to_message_id=reply_id,
        reply_to_file=reply_file,
        is_joined=is_joined,
        raw_text="\n".join(part for part in text_parts if part),
        media=tuple(media),
        contact_evidence=tuple(contacts),
        unparsed=tuple(unparsed),
    )
    return message, sender


def export_files(directory: Path) -> list[Path]:
    """`messages.html`, then `messages2.html`, `messages3.html`, … in order.

    The first page has no number, and lexicographic order would put
    `messages10.html` before `messages2.html`.
    """

    def page_number(path: Path) -> int:
        digits = path.stem.removeprefix("messages")
        return int(digits) if digits.isdigit() else 1

    found = [p for p in directory.glob("messages*.html") if page_number(p) or True]
    return sorted(found, key=page_number)


def parse_export(directory: Path) -> ParsedExport:
    """Read every page of an export, in order."""
    files: list[str] = []
    messages: list[TelegramMessageSource] = []
    services: list[ServiceEvent] = []
    unparsed: list[str] = []
    for path in export_files(directory):
        page = parse_file(path)
        files.append(path.name)
        messages.extend(page.messages)
        services.extend(page.service_events)
        unparsed.extend(page.unparsed)
    return ParsedExport(
        files=tuple(files),
        messages=tuple(messages),
        service_events=tuple(services),
        unparsed=tuple(unparsed),
    )
