"""Group messages into the acts that produced them, and nothing further.

`HIST-002`. A `MessageBundle` says "these messages were posted together". It is
deliberately not a person, a candidate or a medical subject — the exporter joins
two unrelated advertisements posted by the same broker fourteen minutes apart,
so treating a bundle as one patient's evidence would merge two patients.

## The ordering the spec requires

Telegram's own structure decides membership; adjacency may only *suggest*:

1. **JOINED** — the exporter grouped these itself, and its rule is strict (same
   author, same bot, same calendar date, identical forwarded state, within 900
   seconds, no service message between). This is the strongest evidence the
   format offers, and it is still only evidence of one posting act.
2. **REPLY_CONTEXT** — a reply points at another message. It links the two and
   merges nothing: the person asking "is this donor still available?" is not
   the advertiser, and letting a reply into the bundle would overwrite the
   primary sender with the enquirer's name.
3. **WEAK_CONTEXT** — adjacency alone. Never merged, never written into a
   bundle: it is emitted as a suggestion for a person to judge.

## What a bundle deliberately cannot hold

The current poster, the forwarded author, the advertised contact and the medical
subject are four different things. This module knows the first three, because
the export states them. It has no field for the fourth, and a test asserts that
it has none: deciding whose report a photograph shows is `ENTITY-001`'s work, on
medical evidence, with a person in the loop.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from kidneymatch.ingestion.telegram_html import TelegramMessageSource

BUNDLER_VERSION = "bundles/v1"

# The exporter's own joining window, `kJoinWithinSeconds`. Adjacency is only
# ever suggested inside the same span: past it, Telegram itself would not have
# grouped the messages, and neither should a suggestion.
JOIN_WITHIN_SECONDS = 900


class Relation(StrEnum):
    """How a message came to be in, or beside, a bundle."""

    PRIMARY = "PRIMARY"
    JOINED = "JOINED"
    REPLY_CONTEXT = "REPLY_CONTEXT"
    MEDIA_SIBLING = "MEDIA_SIBLING"
    WEAK_CONTEXT = "WEAK_CONTEXT"


class BundleType(StrEnum):
    SINGLE = "SINGLE"
    JOINED_RUN = "JOINED_RUN"
    MEDIA_GROUP = "MEDIA_GROUP"


class Confidence(StrEnum):
    """Where the membership came from.

    `STRUCTURAL` means Telegram grouped it. `SUGGESTED` means something less
    than that, and nothing downstream may treat the two alike.
    """

    STRUCTURAL = "STRUCTURAL"
    SUGGESTED = "SUGGESTED"


class ReviewStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    REVIEW_SUGGESTED = "REVIEW_SUGGESTED"


@dataclass(frozen=True, slots=True)
class BundleMessage:
    telegram_message_id: int
    relation: Relation


@dataclass(frozen=True, slots=True)
class ReplyLink:
    """A reply's target. `resolved` is False when the target is not in view —
    another export file, or another chat — and the link is kept anyway."""

    to_message_id: int
    to_file: str | None
    relation: Relation
    resolved: bool


@dataclass(frozen=True, slots=True)
class MessageBundle:
    bundle_id: str
    source_file: str
    primary_message_id: int
    bundle_type: BundleType
    confidence: Confidence
    review_status: ReviewStatus
    poster_display_name: str | None
    forwarded_authors: tuple[str, ...]
    members: tuple[BundleMessage, ...]
    reply_context: tuple[ReplyLink, ...]
    n_media: int
    started_at: datetime | None


@dataclass(frozen=True, slots=True)
class AdjacencySuggestion:
    """A proposal for a person. It changes nothing on its own."""

    from_bundle_id: str
    to_bundle_id: str
    relation: Relation
    review_status: ReviewStatus
    seconds_apart: float
    reason: str


def _bundle_id(source_file: str, primary_message_id: int) -> str:
    """Deterministic, so that re-deriving bundles gives the same identifiers."""
    return f"{source_file}:{primary_message_id}"


def build_bundles(
    messages: Sequence[TelegramMessageSource],
    known_message_ids: Iterable[int] | None = None,
) -> list[MessageBundle]:
    """Group a chronological run of messages by Telegram's own structure.

    `known_message_ids` decides whether a reply target is resolvable; by default
    only the messages passed in are in view.
    """
    known = (
        set(known_message_ids)
        if known_message_ids is not None
        else {message.telegram_message_id for message in messages}
    )
    bundles: list[MessageBundle] = []
    run: list[TelegramMessageSource] = []

    def flush() -> None:
        if run:
            bundles.append(_bundle_from(run, known))
            run.clear()

    for message in messages:
        # A joined message continues the run above it — but only when there IS
        # one. At a page boundary the run's head is in the previous file, and
        # the message still has to become a bundle rather than disappear.
        if message.is_joined and run:
            run.append(message)
            continue
        flush()
        run.append(message)
    flush()
    return bundles


def _bundle_from(run: list[TelegramMessageSource], known: set[int]) -> MessageBundle:
    head = run[0]
    members = tuple(
        BundleMessage(
            telegram_message_id=message.telegram_message_id,
            relation=Relation.PRIMARY if index == 0 else Relation.JOINED,
        )
        for index, message in enumerate(run)
    )
    n_media = sum(len(message.media) for message in run)
    if len(run) == 1:
        bundle_type = BundleType.SINGLE
    elif n_media >= 2:
        bundle_type = BundleType.MEDIA_GROUP
    else:
        bundle_type = BundleType.JOINED_RUN

    # A joined message that opens a run lost its head to a page boundary, so
    # its membership is inferred rather than stated.
    orphaned = head.is_joined
    confidence = Confidence.SUGGESTED if orphaned else Confidence.STRUCTURAL
    review = ReviewStatus.REVIEW_SUGGESTED if orphaned else ReviewStatus.ACCEPTED

    reply_context = tuple(
        ReplyLink(
            to_message_id=message.reply_to_message_id,
            to_file=message.reply_to_file,
            relation=Relation.REPLY_CONTEXT,
            # A target in another file or chat is still a real link.
            resolved=message.reply_to_file is None and message.reply_to_message_id in known,
        )
        for message in run
        if message.reply_to_message_id is not None
    )
    forwarded = tuple(
        dict.fromkeys(
            message.forwarded_from_display_name
            for message in run
            if message.forwarded_from_display_name
        )
    )
    return MessageBundle(
        bundle_id=_bundle_id(head.source_file, head.telegram_message_id),
        source_file=head.source_file,
        primary_message_id=head.telegram_message_id,
        bundle_type=bundle_type,
        confidence=confidence,
        review_status=review,
        poster_display_name=head.sender_display_name,
        forwarded_authors=forwarded,
        members=members,
        reply_context=reply_context,
        n_media=n_media,
        started_at=head.sent_at,
    )


def suggest_adjacent_links(
    bundles: Sequence[MessageBundle],
    window_seconds: int = JOIN_WITHIN_SECONDS,
) -> list[AdjacencySuggestion]:
    """Propose, never merge.

    The archive's common shape is a photograph of a report followed by a
    separate line of text about it, which Telegram declined to join. That is
    worth a person's attention and is not worth guessing: a wrong merge here
    attaches one patient's description to another patient's laboratory report.

    Only same-poster neighbours inside the exporter's own joining window are
    proposed. Beyond it, Telegram itself saw no relation, and a suggestion
    queue that holds every pair is a queue nobody reads.
    """
    suggestions: list[AdjacencySuggestion] = []
    for earlier, later in zip(bundles, bundles[1:], strict=False):
        if earlier.poster_display_name != later.poster_display_name:
            continue
        if earlier.poster_display_name is None:
            continue
        if earlier.started_at is None or later.started_at is None:
            continue
        gap = (later.started_at - earlier.started_at).total_seconds()
        if not 0 <= gap <= window_seconds:
            continue
        suggestions.append(
            AdjacencySuggestion(
                from_bundle_id=earlier.bundle_id,
                to_bundle_id=later.bundle_id,
                relation=Relation.WEAK_CONTEXT,
                review_status=ReviewStatus.REVIEW_SUGGESTED,
                seconds_apart=gap,
                reason=(
                    "same poster within the exporter's joining window, but Telegram "
                    "did not join them"
                ),
            )
        )
    return suggestions
