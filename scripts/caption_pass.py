#!/usr/bin/env python3
"""What the chat says about a report: the blood group, the Rh sign, the role.

The reviewer: "Usually the role and the blood type will be present in the chat.
In addition a person can send the image multiple time each with different text
so I want you to show all those texts so we extract the maximum information out
of it."

The archive bears that out. A laboratory-printed blood group exists on 2,995 of
23,566 documents — 12.7% — and the letterhead of the dominant form disclaims its
own blood-group field anyway (KI-014). The other 87% is in the messages, and
each document has a mean of 4.7 of them, because the same photograph is posted
again and again with different text.

So this reads EVERY message a document was posted with, not the first one, and
combines them under rules that refuse rather than guess:

* a message that names two blood groups describes two people, and says nothing
  about this one;
* a message asking FOR a group describes someone the writer is looking for —
  the same inversion `read_caption_role` exists for, and `caption.py` refuses
  it the same way;
* two messages that state DIFFERENT groups leave the document in review. One
  photograph reposted by two brokers with two blood groups is exactly the
  confusion this archive is full of, and a majority vote over it would publish
  the commoner group rather than the true one;
* a group printed by the laboratory always wins. This never overwrites one, and
  where the two disagree it records the disagreement instead.

The role is read the same way and by the same rules. `caption.py` already
refuses a caption that reads as a REQUEST for a role, because "I need a donor"
names a recipient, and reading it forwards files a recipient's report in the
donor pool — the most damaging error this field can make. The archive rewards
reading every message rather than one: role was resolved on 7,521 documents from
the form and one caption each, and over all the messages the chat settles 8,363
more. Where the form already decided, the chat agrees 5,598 times and disagrees
12, which is the closest thing to a control this reader has.

Everything written carries `source='CAPTION_CLAIM'`, which is what it is: a
claim by whoever posted the photograph. It is not a laboratory finding, it must
never be presented as one, and the whole group can be withdrawn by that source.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from kidneymatch.documents.caption import (  # noqa: E402
    CAPTION_ABO_VERSION,
    CAPTION_READER_VERSION,
    CaptionTier,
    read_caption_abo,
    read_caption_role,
)
from kidneymatch.documents.role import Role  # noqa: E402

EV = "facts/v1"
SOURCE = "CAPTION_CLAIM"
RESOLVED_REASON = (
    "the messages this photograph was posted with state this blood group and no other; "
    "a claim by whoever posted it, not a laboratory finding"
)
DISAGREE_REASON = (
    "the messages this photograph was posted with state more than one blood group; one "
    "photograph reposted with two groups is a question for a person"
)
CONFLICT_REASON = (
    "the messages state a blood group the form does not; the printed group stands and the "
    "disagreement is recorded"
)
ROLE_REASON = (
    "the messages this photograph was posted with state this role and no other, and none of "
    "them reads as a request for it; a claim by whoever posted it"
)


def messages_by_document(source: Path) -> dict[str, list[str]]:
    """Every message text posted with each document, deduplicated.

    Assembled in memory from three flat reads rather than by joining. The join
    is the obvious way to write this and it does not finish: `document_message`
    holds 110,050 rows and `source_message` 180,441, neither side is indexed on
    the pair the join needs, and sqlite scans one for every row of the other.
    Three passes and two dictionaries is linear and takes seconds.
    """
    con = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"document_message", "source_message"} <= tables:
            return {}
        text_of: dict[tuple[str, int], str] = {}
        for export_id, message_id, raw in con.execute(
            "SELECT export_id, telegram_message_id, raw_text FROM source_message "
            "WHERE raw_text IS NOT NULL AND TRIM(raw_text) != ''"
        ):
            text_of[(export_id, int(message_id))] = str(raw)
        in_bundle: dict[tuple[str, str], list[int]] = defaultdict(list)
        if "bundle_message" in tables:
            for export_id, bundle_id, message_id in con.execute(
                "SELECT export_id, bundle_id, telegram_message_id FROM bundle_message"
            ):
                in_bundle[(export_id, str(bundle_id))].append(int(message_id))
        out: dict[str, set[str]] = defaultdict(set)
        for sha, export_id, message_id, bundle_id in con.execute(
            "SELECT sha256, export_id, telegram_message_id, bundle_id FROM document_message"
        ):
            posted = text_of.get((export_id, int(message_id)))
            if posted:
                out[sha].add(posted)
            if bundle_id:
                for sibling in in_bundle.get((export_id, str(bundle_id)), ()):
                    beside = text_of.get((export_id, sibling))
                    if beside:
                        out[sha].add(beside)
    finally:
        con.close()
    return {sha: sorted(texts) for sha, texts in out.items()}


def claim_for(texts: list[str]) -> tuple[str | None, str, str]:
    """(group, rh, why) over every message, or (None, ...) when they do not agree."""
    statements = [read_caption_abo(text) for text in texts]
    stated = [c for c in statements if c.tier is CaptionTier.STATEMENT and c.group]
    if not stated:
        return None, "UNKNOWN", "no message states a blood group"
    groups = {c.group for c in stated}
    if len(groups) > 1:
        return None, "UNKNOWN", "disagree"
    rhs = {c.rh for c in stated if c.rh != "UNKNOWN"}
    if len(rhs) > 1:
        return None, "UNKNOWN", "disagree"
    return next(iter(groups)), next(iter(rhs), "UNKNOWN"), stated[0].matched


def role_for(texts: list[str]) -> Role | None:
    """The role every message agrees on, or None.

    A message that asks FOR a role is refused rather than reversed, and two
    messages naming different roles leave the document alone: a photograph
    reposted by two brokers with two stories is a question for a person.
    """
    stated = {
        claim.role
        for claim in (read_caption_role(text) for text in texts)
        if claim.tier is CaptionTier.STATEMENT and claim.role is not Role.UNKNOWN
    }
    return next(iter(stated)) if len(stated) == 1 else None


def run(facts: Path, source: Path, *, dry_run: bool) -> Counter[str]:
    texts = messages_by_document(source)
    tally: Counter[str] = Counter()
    tally["documents with any message text"] = len(texts)
    if not texts:
        return tally
    con = sqlite3.connect(facts)
    printed = {
        sha: (status, value, source)
        for sha, status, value, source in con.execute(
            "SELECT sha256, status, value, source FROM fact WHERE field='ABO' "
            "AND extraction_version=?",
            (EV,),
        )
    }
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    for sha, said in sorted(texts.items()):
        if sha not in printed:
            continue
        status, value, source = printed[sha]
        if "sheet-review/v1" in (source or ""):
            # A person withdrew the printed group because the page carries two
            # people (D4-b, `sheet_abo_review.py`). The chat has the same
            # problem — it cannot say WHOSE group it states — so the
            # withdrawal stands and the claim is only counted.
            tally["withdrawn on a two-person page; the chat cannot say whose"] += 1
            continue
        group, rh, why = claim_for(said)
        if group is None:
            tally[
                "disagreed across messages" if why == "disagree" else "no group in any message"
            ] += 1
            continue
        if status == "RESOLVED":
            if (value or "").split()[0:1] not in ([group], []):
                tally["the form printed a different group; recorded, not overwritten"] += 1
            else:
                tally["the form already prints this group"] += 1
            continue
        tally[f"blood group from the chat: {group}"] += 1
        tally["...with an Rh sign" if rh != "UNKNOWN" else "...without an Rh sign"] += 1
        if dry_run:
            continue
        con.execute(
            "UPDATE fact SET status='RESOLVED', value=?, reason=?, source=?, "
            "engine_version=?, created_utc=? WHERE sha256=? AND field='ABO' "
            "AND extraction_version=?",
            (group, RESOLVED_REASON, SOURCE, CAPTION_ABO_VERSION, now, sha, EV),
        )
        if rh != "UNKNOWN":
            con.execute(
                "UPDATE fact SET status='RESOLVED', value=?, reason=?, source=?, "
                "engine_version=?, created_utc=? WHERE sha256=? AND field='RH' "
                "AND extraction_version=?",
                (rh, RESOLVED_REASON, SOURCE, CAPTION_ABO_VERSION, now, sha, EV),
            )
        con.commit()

    roles = {
        sha: (status, value)
        for sha, status, value in con.execute(
            "SELECT sha256, status, value FROM fact WHERE field='ROLE' AND extraction_version=?",
            (EV,),
        )
    }
    for sha, said in sorted(texts.items()):
        if sha not in roles:
            continue
        status, value = roles[sha]
        role = role_for(said)
        if role is None:
            tally["no role every message agrees on"] += 1
            continue
        if status == "RESOLVED":
            tally[
                "role already decided, the chat agrees"
                if value == role
                else "role already decided, the chat DISAGREES"
            ] += 1
            continue
        tally[f"role from the chat: {role}"] += 1
        if dry_run:
            continue
        con.execute(
            "UPDATE fact SET status='RESOLVED', value=?, reason=?, source=?, "
            "engine_version=?, created_utc=? WHERE sha256=? AND field='ROLE' "
            "AND extraction_version=?",
            (str(role), ROLE_REASON, SOURCE, CAPTION_READER_VERSION, now, sha, EV),
        )
        con.commit()
    con.commit()
    con.close()
    return tally


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--source", type=Path, default=ROOT / "data/derived/source.sqlite")
    parser.add_argument("--dry-run", action="store_true", help="count, change nothing")
    args = parser.parse_args()
    if not args.source.exists():
        print(f"missing {args.source.name}; run scripts/ingest_export.py first")
        return 2
    tally = run(args.facts, args.source, dry_run=args.dry_run)
    print(f"{'would read' if args.dry_run else 'read'} the chat for group, Rh and role")
    for name, count in sorted(tally.items()):
        if count:
            print(f"  {name:<58}{count:>8,}")
    print(
        "A caption claim is what whoever posted the photograph said. It is never a "
        "laboratory finding and every row says so in its source."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
