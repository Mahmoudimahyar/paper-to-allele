"""Reconstructing what was posted as one act, without inventing people.

`HIST-002`. A bundle answers "these messages were posted together", and nothing
else. It is not a person, not a candidate, and not a medical subject: the
exporter groups two unrelated advertisements from the same broker fourteen
minutes apart, and treating that as one submission's evidence would merge two
patients.

So the rule is ordering, not merging: Telegram's own structure decides bundles,
and adjacency may only *suggest* — never join — and always leaves the decision
to a person.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from kidneymatch.ingestion.bundles import (
    BundleType,
    Confidence,
    Relation,
    ReviewStatus,
    build_bundles,
    suggest_adjacent_links,
)

from kidneymatch.ingestion.telegram_html import MediaReference, TelegramMessageSource

pytestmark = pytest.mark.task("HIST-002")

START = datetime(2020, 1, 1, 10, 0, 0)


def message(
    message_id: int,
    *,
    minutes: int = 0,
    sender: str | None = "Poster",
    inherited: bool = False,
    joined: bool = False,
    text: str = "",
    media: int = 0,
    reply_to: int | None = None,
    forwarded: str | None = None,
) -> TelegramMessageSource:
    stamp = START + timedelta(minutes=minutes)
    return TelegramMessageSource(
        telegram_message_id=message_id,
        source_file="messages.html",
        dom_id=f"message{message_id}",
        sent_at=stamp,
        sent_at_raw=stamp.strftime("%d.%m.%Y %H:%M:%S"),
        sender_display_name=sender,
        sender_is_inherited=inherited,
        forwarded_from_display_name=forwarded,
        forwarded_original_at=None,
        forwarded_original_at_raw=None,
        reply_to_message_id=reply_to,
        reply_to_file=None,
        is_joined=joined,
        raw_text=text,
        media=tuple(
            MediaReference(href=f"photos/p{i}.jpg", thumbnail_src=None, kind="PHOTO")
            for i in range(media)
        ),
    )


# --- explicit structure outranks adjacency --------------------------------


@pytest.mark.invariant("HIST-002", "joined/reply/media-group relations outrank adjacency")
def test_a_joined_run_becomes_one_bundle(page_free=None) -> None:
    """Acceptance 0: a multi-image joined submission bundles once.

    The common shape in this archive: a broker posts three photographs of one
    report and a line of text, and Telegram groups them.
    """
    messages = [
        message(1, media=1),
        message(2, minutes=1, joined=True, inherited=True, media=1),
        message(3, minutes=1, joined=True, inherited=True, media=1),
        message(4, minutes=2, joined=True, inherited=True, text="O+ donor, 28"),
    ]
    bundles = build_bundles(messages)
    assert len(bundles) == 1
    bundle = bundles[0]
    assert bundle.primary_message_id == 1
    assert [m.relation for m in bundle.members] == [
        Relation.PRIMARY,
        Relation.JOINED,
        Relation.JOINED,
        Relation.JOINED,
    ]
    assert bundle.n_media == 3
    assert bundle.bundle_type is BundleType.MEDIA_GROUP
    assert bundle.confidence is Confidence.STRUCTURAL
    assert bundle.review_status is ReviewStatus.ACCEPTED


def test_a_lone_message_is_its_own_bundle() -> None:
    bundles = build_bundles([message(1, text="hello")])
    assert len(bundles) == 1
    assert bundles[0].bundle_type is BundleType.SINGLE
    assert [m.relation for m in bundles[0].members] == [Relation.PRIMARY]


def test_a_new_sender_starts_a_new_bundle() -> None:
    """A non-joined message is a new act by definition, even seconds later."""
    bundles = build_bundles(
        [
            message(1, sender="A", text="first"),
            message(2, minutes=1, sender="B", text="second"),
        ]
    )
    assert [b.primary_message_id for b in bundles] == [1, 2]
    assert [b.poster_display_name for b in bundles] == ["A", "B"]


# --- adjacency must never merge silently ----------------------------------


@pytest.mark.invariant("HIST-002", "adjacent unrelated messages must not silently merge")
def test_two_unjoined_messages_from_one_sender_stay_apart(page_free=None) -> None:
    """Acceptance 2, and the invariant behind it.

    Telegram declined to join these — different day, or more than fifteen
    minutes, or a service message between them. The parser must not be braver
    than the exporter about what belongs together.
    """
    messages = [
        message(1, text="donor A, O+"),
        message(2, minutes=40, text="donor B, AB-"),
    ]
    bundles = build_bundles(messages)
    assert len(bundles) == 2, "two advertisements, two bundles"
    assert all(b.review_status is ReviewStatus.ACCEPTED for b in bundles)


def test_adjacency_can_only_suggest_and_the_suggestion_is_not_a_bundle() -> None:
    """Acceptance 2: ambiguous adjacency yields a review suggestion, not a
    merge. The suggestion names two bundles; it never rewrites either."""
    messages = [
        message(1, media=1),
        message(2, minutes=3, text="the report above is for a 31-year-old donor"),
    ]
    bundles = build_bundles(messages)
    suggestions = suggest_adjacent_links(bundles)
    assert len(bundles) == 2
    assert len(suggestions) == 1
    suggestion = suggestions[0]
    assert suggestion.relation is Relation.WEAK_CONTEXT
    assert suggestion.review_status is ReviewStatus.REVIEW_SUGGESTED
    assert (suggestion.from_bundle_id, suggestion.to_bundle_id) == (
        bundles[0].bundle_id,
        bundles[1].bundle_id,
    )
    # And the bundles themselves are untouched by the suggestion.
    assert all(len(b.members) == 1 for b in bundles)


def test_a_distant_neighbour_is_not_even_suggested() -> None:
    """A suggestion queue that contains every pair is a queue nobody reads."""
    messages = [message(1, media=1), message(2, minutes=45, text="unrelated")]
    assert suggest_adjacent_links(build_bundles(messages)) == []


def test_a_different_sender_is_not_suggested_either() -> None:
    messages = [message(1, sender="A", media=1), message(2, minutes=2, sender="B", text="x")]
    assert suggest_adjacent_links(build_bundles(messages)) == []


# --- replies link, they do not merge --------------------------------------


def test_a_reply_links_as_context_without_merging_or_reassigning(page_free=None) -> None:
    """Acceptance 1: reply context links without overwriting the primary
    sender.

    Someone asking "is this donor still available?" is not part of the
    advertisement, and their name must not become the advertiser's.
    """
    messages = [
        message(1, sender="Broker", media=1),
        message(2, minutes=5, sender="Enquirer", text="still available?", reply_to=1),
    ]
    bundles = build_bundles(messages)
    assert len(bundles) == 2
    advert, enquiry = bundles
    assert advert.poster_display_name == "Broker"
    assert enquiry.poster_display_name == "Enquirer"
    assert [link.to_message_id for link in enquiry.reply_context] == [1]
    assert enquiry.reply_context[0].relation is Relation.REPLY_CONTEXT
    assert all(m.relation is Relation.PRIMARY for m in advert.members)


def test_a_reply_to_an_unknown_message_is_kept_as_a_dangling_link() -> None:
    """The target may be in another export file or another chat. Dropping the
    link would lose the only trace that a conversation existed."""
    bundles = build_bundles([message(9, text="answer", reply_to=4)])
    assert bundles[0].reply_context[0].to_message_id == 4
    assert bundles[0].reply_context[0].resolved is False


# --- the four identities stay apart ---------------------------------------


@pytest.mark.invariant(
    "HIST-002",
    "current poster, forwarded actor, advertised contact, medical subject remain separate",
)
def test_a_bundle_never_holds_a_medical_subject(page_free=None) -> None:
    """The poster is who typed it, the forwarded actor is who wrote it first,
    the advertised contact is a phone number in the text, and the subject is
    the patient. A bundle knows the first three and must have nowhere to put
    the fourth: deciding it is `ENTITY-001`'s job, on medical evidence.
    """
    messages = [
        message(1, sender="Broker", forwarded="Original Channel", text="call 0912"),
    ]
    bundle = build_bundles(messages)[0]
    assert bundle.poster_display_name == "Broker"
    assert bundle.forwarded_authors == ("Original Channel",)
    fields = set(type(bundle).__dataclass_fields__)
    for forbidden in ("subject", "candidate", "person", "patient", "donor", "recipient"):
        assert not any(forbidden in name for name in fields), forbidden


def test_a_joined_run_keeps_every_forwarded_author_it_contains() -> None:
    """The exporter only joins messages with identical forwarded state, so a
    run is all-forwarded or none — recorded, not assumed."""
    messages = [
        message(1, forwarded="Channel A"),
        message(2, minutes=1, joined=True, inherited=True, forwarded="Channel A"),
    ]
    bundle = build_bundles(messages)[0]
    assert bundle.forwarded_authors == ("Channel A",)
    assert len(bundle.members) == 2


# --- determinism ----------------------------------------------------------


def test_bundle_ids_are_deterministic() -> None:
    """Two runs over the same export must produce the same bundle ids, or
    nothing downstream can be re-derived."""
    messages = [message(1, media=1), message(2, minutes=1, joined=True, inherited=True, media=1)]
    first = build_bundles(messages)
    second = build_bundles(messages)
    assert [b.bundle_id for b in first] == [b.bundle_id for b in second]
    assert first[0].bundle_id == "messages.html:1"


def test_a_joined_message_with_no_predecessor_is_not_dropped() -> None:
    """A page boundary can put a joined message first. It is still a message,
    and losing it would silently shorten the archive."""
    bundles = build_bundles([message(5, joined=True, inherited=False, sender=None, text="x")])
    assert len(bundles) == 1
    assert bundles[0].primary_message_id == 5
    assert bundles[0].confidence is Confidence.SUGGESTED
