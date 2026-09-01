from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class MediaReference:
    href: str | None
    thumbnail_src: str | None


@dataclass(frozen=True, slots=True)
class TelegramMessageSource:
    message_id: int
    sent_at: datetime | None
    sender_display_name: str | None
    sender_stable_id: str | None
    forwarded_from_display_name: str | None
    forwarded_from_stable_id: str | None
    forwarded_original_at: datetime | None
    reply_to_message_id: int | None
    is_joined: bool
    raw_text: str
    media: tuple[MediaReference, ...] = field(default_factory=tuple)
