"""The anchored review pack: which documents a person sees, and what leaves it.

Everything runs on a synthetic facts database and synthetic images built here;
nothing touches the corpus.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.task("BOOT-001")

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/review_pack.py"
PAGE = ROOT / "tools/hla_review.html"


def load():
    spec = importlib.util.spec_from_file_location("km_review_pack", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["km_review_pack"] = module  # slots dataclasses resolve names through it
    spec.loader.exec_module(module)
    return module


FACT_COLUMNS = (
    "sha256, field, extraction_version, status, value, raw, repaired, second_allele, reason, "
    "rule_id, anchor_box, value_boxes, source, engine_version, preproc_version, imgt_version, "
    "created_utc, stability"
)


def synthetic_corpus(tmp_path: Path, n_docs: int = 40) -> tuple[Path, Path]:
    """`n_docs` synthetic reports with every failure signal represented."""
    from PIL import Image, ImageDraw

    export = tmp_path / "export"
    (export / "photos").mkdir(parents=True)
    db = tmp_path / "facts.sqlite"
    con = sqlite3.connect(db)
    con.executescript(
        f"""
        CREATE TABLE fact ({FACT_COLUMNS});
        CREATE TABLE document (sha256, extraction_version, rel_path, quality_band, family,
            comparison_sheet, consistency, consistency_reason, n_facts, created_utc);
        CREATE TABLE confirmation (sha256, field, extraction_version, confirmer_version,
            verdict, reading, created_utc);
        CREATE TABLE decode (sha256, field, extraction_version, decoder_version, verdict,
            reading, jitter_readings, grammar_cost, created_utc);
        """
    )
    loci = ("A", "B", "C", "DRB1", "DQA1", "DQB1", "DPA1", "DPB1", "DRB3", "DRB4", "DRB5")
    for i in range(n_docs):
        sha = hashlib.sha256(f"synthetic report {i}".encode()).hexdigest()
        rel = f"photos/report_{i}.jpg"
        image = Image.new("RGB", (800, 600), "white")
        draw = ImageDraw.Draw(image)
        for row, locus in enumerate(loci):
            y = 40 + row * 40
            draw.text((40, y), f"HLA-{locus}", fill="black")
            draw.text((200, y), "11 15" if locus in loci[:8] else "PRESENT", fill="black")
        image.save(export / rel, quality=85)
        # Signals, one per document in rotation, so every stratum has members;
        # 8 and 9 carry no signal at all and are the clean controls.
        signal = i % 10
        band = "LOW" if signal == 1 else ("MID" if signal == 2 else "HIGH")
        consistency = "FORBIDDEN_GENE_PRESENT" if signal == 0 else "CONSISTENT"
        family = None if signal == 3 else "FORM#1"
        con.execute(
            "INSERT INTO document VALUES (?,?,?,?,?,?,?,?,?,?)",
            (sha, "facts/v1", rel, band, family, int(signal == 4), consistency, None, 8, "t"),
        )
        for row, locus in enumerate(loci):
            y0, y1 = (40 + row * 40) / 600, (60 + row * 40) / 600
            anchor = json.dumps([0.05, y0, 0.15, y1])
            boxes = json.dumps([[0.25, y0, 0.30, y1], [0.32, y0, 0.37, y1]])
            status, value = "RESOLVED", (f"{locus}*11 {locus}*15" if row < 8 else "PRESENT")
            if signal == 7 and locus == "A":
                status, value = "REVIEW_REQUIRED", None
            con.execute(
                f"INSERT INTO fact ({FACT_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    sha,
                    locus,
                    "facts/v1",
                    status,
                    value,
                    value,
                    int(signal == 5 and locus == "B"),
                    "UNREAD" if signal == 6 and locus == "C" else "READ",
                    "3 candidate values exceeds max_values=2" if status != "RESOLVED" else None,
                    "family",
                    anchor,
                    boxes,
                    "OCR",
                    "e",
                    "p",
                    "3620",
                    "t",
                    "UNANIMOUS" if status == "RESOLVED" else "NOT_CHECKED",
                ),
            )
            if row < 8:
                # Two independent readers, as the corpus now has.
                for confirmer in ("tesseract5/psm7-alnum", "ppocrv5/en-mobile-rec"):
                    con.execute(
                        "INSERT INTO confirmation VALUES (?,?,?,?,?,?,?)",
                        (sha, locus, "facts/v1", confirmer, "CONFIRMED", "11", "t"),
                    )
                verdict = "UNANIMOUS"
                if signal == 7 and locus == "A":
                    verdict = "PROPOSAL"
                con.execute(
                    "INSERT INTO decode VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        sha,
                        locus,
                        "facts/v1",
                        "ctc-viterbi/v1",
                        verdict,
                        "11",
                        json.dumps({"0:11": 9}),
                        0.0,
                        "t",
                    ),
                )
        for fld, value in (("ROLE", "DONOR"), ("ABO", "O"), ("RH", "POSITIVE")):
            con.execute(
                f"INSERT INTO fact ({FACT_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    sha,
                    fld,
                    "facts/v1",
                    "RESOLVED",
                    value,
                    value,
                    0,
                    None,
                    None,
                    None,
                    None,
                    None,
                    "FORM_FIELD",
                    "e",
                    "p",
                    None,
                    "t",
                    "NOT_CHECKED",
                ),
            )
    con.commit()
    con.close()
    return db, export


def sha_of(i: int) -> str:
    return hashlib.sha256(f"synthetic report {i}".encode()).hexdigest()


SOURCE_MESSAGE_COLUMNS = (
    "export_id, source_file, telegram_message_id, dom_id, content_hash, parser_version, "
    "sent_at_raw, sender_display_name, sender_is_inherited, forwarded_from_display_name, "
    "forwarded_original_at_raw, reply_to_message_id, reply_to_file, is_joined, raw_text, media, "
    "contact_evidence, unparsed, first_seen_utc, last_seen_utc"
)
# Synthetic captions, typed for this test; nothing here is from the corpus.
DONOR_CAPTION = "اهدا کننده کلیه گروه خونی O+"
RECIPIENT_CAPTION = "گیرنده کلیه گروه خونی B مثبت"
# Longer than any cap the pack sets, so the clipping is exercised whatever
# `MAX_MESSAGE_CHARS` is set to; it was raised from 600 to 1,500 when the
# reviewer asked to see every text a photograph was posted with.
LONG_CAPTION = "متن " * 1000


def synthetic_source(tmp_path: Path) -> Path:
    """A source database with the three link tables, for the first four reports.

    report 0: posted three times, out of id order in the link table, one
              forwarded, one over the clip length, one spanning a month
              boundary so a raw-string date sort would misorder it.
    report 1: the photo message is empty; the caption sits on a bundle sibling,
              and a second sibling is empty (must not appear).
    report 2: never posted.
    report 3: posted ten times, all captioned, so the cap has something to cut.
    """
    db = tmp_path / "source.sqlite"
    con = sqlite3.connect(db)
    con.executescript(
        f"""
        CREATE TABLE source_message ({SOURCE_MESSAGE_COLUMNS});
        CREATE TABLE document_message (sha256, export_id, source_file, telegram_message_id,
            bundle_id, rel_path);
        CREATE TABLE bundle_message (export_id, bundle_id, telegram_message_id, relation);
        CREATE TABLE document_caption_claim (sha256, export_id, role, tier, reason,
            reader_version);
        """
    )

    def message(
        message_id: int,
        sent: str | None,
        sender: str | None,
        text: str,
        *,
        forwarded: str | None = None,
        joined: bool = False,
    ) -> None:
        con.execute(
            f"INSERT INTO source_message ({SOURCE_MESSAGE_COLUMNS}) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "exp1",
                "messages.html",
                message_id,
                f"message{message_id}",
                f"h{message_id}",
                "telegram-html/v1",
                sent,
                sender,
                int(sender is None),
                forwarded,
                None,
                None,
                None,
                int(joined),
                text,
                "[]",
                "[]",
                "[]",
                "t",
                "t",
            ),
        )

    def posted(sha: str, message_id: int, bundle_id: str | None = None) -> None:
        con.execute(
            "INSERT INTO document_message VALUES (?,?,?,?,?,?)",
            (sha, "exp1", "messages.html", message_id, bundle_id, "photos/x.jpg"),
        )

    message(90, "28.08.2026 09:00:00 UTC+03:30", "Poster One", LONG_CAPTION)
    message(100, "02.09.2026 10:00:00 UTC+03:30", "Poster One", DONOR_CAPTION)
    message(250, "03.09.2026 08:00:00 UTC+03:30", "Poster Two", "forwarded copy", forwarded="Other")
    for message_id in (250, 90, 100):
        posted(sha_of(0), message_id)
    con.execute(
        "INSERT INTO document_caption_claim VALUES (?,?,?,?,?,?)",
        (sha_of(0), "exp1", "DONOR", "STATEMENT", "first-person statement", "caption-role/v1"),
    )

    message(300, "04.09.2026 12:00:00 UTC+03:30", "Poster One", "")
    message(301, "04.09.2026 12:00:01 UTC+03:30", None, RECIPIENT_CAPTION, joined=True)
    message(302, "04.09.2026 12:00:02 UTC+03:30", None, "", joined=True)
    posted(sha_of(1), 300, "b1")
    for message_id, relation in ((300, "PRIMARY"), (301, "JOINED"), (302, "JOINED")):
        con.execute(
            "INSERT INTO bundle_message VALUES (?,?,?,?)", ("exp1", "b1", message_id, relation)
        )

    for i in range(10):
        message(400 + i, f"05.09.2026 08:00:{i:02d} UTC+03:30", "Poster Two", f"copy {i}")
        posted(sha_of(3), 400 + i)
    con.commit()
    con.close()
    return db


def test_load_messages_orders_clips_and_hashes_the_poster(tmp_path: Path) -> None:
    """A caption often says what the report does not — donor or recipient, and
    the blood group — so the pack carries the posting messages. In time order,
    clipped, and with the poster as a hash: the page needs only "same poster
    or a different one" (HA-005)."""
    module = load()
    source = synthetic_source(tmp_path)
    found = module.load_messages(source, {sha_of(0), sha_of(2)})
    assert set(found) == {sha_of(0), sha_of(2)}
    assert found[sha_of(2)] == []
    msgs = found[sha_of(0)]
    assert [m["message_id"] for m in msgs] == [90, 100, 250], (
        "time order across a month boundary; a raw-string sort puts 02.09 before 28.08"
    )
    assert all(m["on_photo"] for m in msgs)
    assert [m["forwarded"] for m in msgs] == [False, False, True]
    assert msgs[1]["text"] == DONOR_CAPTION
    assert len(msgs[0]["text"]) == module.MAX_MESSAGE_CHARS
    assert msgs[0]["text"].endswith("…")
    expected = hashlib.sha256(b"km-sender|Poster One").hexdigest()[:8]
    assert msgs[0]["sender"] == msgs[1]["sender"] == expected
    assert msgs[2]["sender"] != expected
    assert "Poster" not in json.dumps(found, ensure_ascii=False)
    assert set(msgs[0]) == {
        "message_id",
        "sent_at",
        "text",
        "on_photo",
        "forwarded",
        "joined",
        "sender",
    }


def test_load_messages_reads_the_caption_off_a_bundle_sibling(tmp_path: Path) -> None:
    """18,799 documents have text somewhere in their bundle against 16,858 on
    the posting message itself: the caption often sits one message over."""
    module = load()
    source = synthetic_source(tmp_path)
    msgs = module.load_messages(source, {sha_of(1)})[sha_of(1)]
    assert [(m["message_id"], m["on_photo"]) for m in msgs] == [(300, True), (301, False)]
    assert msgs[0]["text"] == "", "the empty photo message stays so the reader sees 'no caption'"
    assert msgs[1]["text"] == RECIPIENT_CAPTION
    assert msgs[1]["joined"] is True and msgs[1]["sender"] is None


def test_load_messages_caps_the_count_and_reads_the_claim(tmp_path: Path) -> None:
    """The cap exists so one prolific thread cannot bury the pack, and it was
    raised from 8 to 60 when the reviewer asked to see every text: 2,406 of
    23,565 documents carry more than eight postings, and the truncated part is
    exactly where a repost adds the blood group the form never printed. What
    the test holds is that clipping happens in time order, not its size."""
    module = load()
    source = synthetic_source(tmp_path)
    msgs = module.load_messages(source, {sha_of(3)})[sha_of(3)]
    expected = min(module.MAX_MESSAGES, 8)
    assert [m["message_id"] for m in msgs][:expected] == list(range(400, 400 + expected))
    assert len(msgs) <= module.MAX_MESSAGES
    claims = module.load_caption_claims(source, {sha_of(0), sha_of(1)})
    assert claims[sha_of(0)] == {
        "role": "DONOR",
        "tier": "STATEMENT",
        "reason": "first-person statement",
    }
    assert claims[sha_of(1)] is None


def test_augment_messages_adds_the_keys_and_touches_nothing_else(tmp_path: Path) -> None:
    """The pack in progress must not be rebuilt: labels are keyed by cell id
    and the crops are what the reviewer has been looking at. Only pack.json
    and pack.js change, and running it twice changes nothing."""
    module = load()
    db, export = synthetic_corpus(tmp_path, n_docs=4)
    source = synthetic_source(tmp_path)
    pack_dir = tmp_path / "pack"
    module.build_pack(db, export, pack_dir, 4, 1, PAGE)
    before = {
        p.relative_to(pack_dir).as_posix(): p.read_bytes()
        for p in pack_dir.rglob("*")
        if p.is_file() and p.name not in {"pack.json", "pack.js"}
    }
    assert any(name.startswith("crops/") for name in before)
    assert any(name.startswith("images/") for name in before)

    def augment() -> str:
        result = subprocess.run(  # noqa: S603
            [
                sys.executable,
                str(SCRIPT),
                "--augment-messages",
                "--out",
                str(pack_dir),
                "--source",
                str(source),
            ],
            capture_output=True,
            text=True,
            cwd=ROOT,
            encoding="utf-8",
        )
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout

    stdout = augment()
    assert "Poster" not in stdout and DONOR_CAPTION not in stdout, "counts only, never a caption"
    after = {
        p.relative_to(pack_dir).as_posix(): p.read_bytes()
        for p in pack_dir.rglob("*")
        if p.is_file() and p.name not in {"pack.json", "pack.js"}
    }
    assert after == before, "crops, images, pipeline.json and the page are untouched"

    pack = json.loads((pack_dir / "pack.json").read_text(encoding="utf-8"))
    by_sha = {d["sha256"]: d for d in pack["documents"]}
    assert set(by_sha) == {sha_of(i) for i in range(4)}
    for doc in pack["documents"]:
        assert "messages" in doc and "caption_claim" in doc
    assert [m["message_id"] for m in by_sha[sha_of(0)]["messages"]] == [90, 100, 250]
    assert by_sha[sha_of(0)]["caption_claim"]["role"] == "DONOR"
    assert by_sha[sha_of(2)]["messages"] == [] and by_sha[sha_of(2)]["caption_claim"] is None
    js = (pack_dir / "pack.js").read_text(encoding="utf-8")
    assert js.startswith("window.PACK = ") and js.endswith(";\n")
    assert json.loads(js[len("window.PACK = ") : -2]) == pack
    pipeline = json.loads((pack_dir / "pipeline.json").read_text(encoding="utf-8"))
    assert all("messages" not in entry for entry in pipeline["cells"].values())

    first = (pack_dir / "pack.json").read_bytes()
    augment()
    assert (pack_dir / "pack.json").read_bytes() == first, "idempotent"


def test_a_fresh_pack_carries_messages_only_when_the_source_database_exists(
    tmp_path: Path,
) -> None:
    module = load()
    db, export = synthetic_corpus(tmp_path, n_docs=4)
    module.build_pack(
        db, export, tmp_path / "without", 4, 1, PAGE, source_db=tmp_path / "absent.sqlite"
    )
    pack = json.loads((tmp_path / "without/pack.json").read_text(encoding="utf-8"))
    # not loaded is None, never an empty list: the page must not say "no
    # message posted this image" about an archive it never opened
    assert all(
        d["messages"] is None and d["n_messages_total"] is None and d["caption_claim"] is None
        for d in pack["documents"]
    )
    source = synthetic_source(tmp_path)
    module.build_pack(db, export, tmp_path / "with", 4, 1, PAGE, source_db=source)
    pack = json.loads((tmp_path / "with/pack.json").read_text(encoding="utf-8"))
    by_sha = {d["sha256"]: d for d in pack["documents"]}
    assert by_sha[sha_of(1)]["messages"][1]["text"] == RECIPIENT_CAPTION
    assert by_sha[sha_of(0)]["caption_claim"]["tier"] == "STATEMENT"


def test_the_page_shows_the_messages_and_the_caption_claim() -> None:
    """Rendered inside a native <details>, so the keyboard opens it; the text in
    a dir="auto" paragraph, so Persian runs right to left; the poster never a
    name. The open state is remembered for the tab, and only if the browser
    allows it."""
    page = PAGE.read_text(encoding="utf-8")
    assert "function messagesHtml(doc)" in page
    body = page.split("function messagesHtml(doc)")[1].split("\n  }\n")[0]
    assert "<details" in body and "<summary>Messages (" in body
    assert '<p dir="auto">' in body
    assert "esc(m.text)" in body and "esc(m.sender)" in body
    assert "m.name" not in body and "display_name" not in body
    assert "white-space: pre-wrap" in page
    assert "caption: '" in page and "doc.caption_claim.tier" in page
    assert "sessionStorage." in page
    for accessor in page.split("sessionStorage.")[1:]:
        assert "catch" in accessor[:160], (
            "storage access is wrapped; a private window must not throw"
        )


def test_the_messages_panel_is_open_before_anyone_clicks_it() -> None:
    """The reviewer asked to SEE the texts, and the point of carrying the chat
    is that the blood group and the role are usually in it rather than on the
    form. Behind a closed disclosure, on every document, that is information
    nobody reads. Closing one is still remembered for the tab."""
    page = PAGE.read_text(encoding="utf-8")
    body = page.split("function messagesOpen()")[1].split("function rememberMessagesOpen")[0]
    assert "!== '0'" in body, "the default must be open, not closed"
    assert "return true" in body, "a browser refusing storage must still open it"


def test_every_whole_page_field_shows_where_its_value_came_from() -> None:
    """A blood group the laboratory PRINTED and one a person TYPED IN THE CHAT
    are not the same evidence.

    On the round-three pack, 14 of 25 resolved ABO values came from a caption
    and 9 from the printed form. A reviewer weighing "is this right" needs to
    know which, and Role was the only one of the three that said so.
    """
    page = PAGE.read_text(encoding="utf-8")
    assert "function srcHint(field)" in page
    for field in ("doc.abo", "doc.rh"):
        assert f"srcHint({field})" in page, field
    # Role states its source inline rather than through the helper; either way
    # the reader must be able to see it.
    assert "doc.role.source" in page


def test_every_failure_signal_fills_its_own_stratum(tmp_path: Path) -> None:
    """A random sample would be nearly all easy cells; the pack draws from
    each signal the pipeline already emits, rarest first."""
    module = load()
    db, export = synthetic_corpus(tmp_path)
    counts = module.build_pack(db, export, tmp_path / "pack", 24, 1, PAGE)
    for tag in (
        "consistency_flag",
        "low_res",
        "mid_res",
        "default_rule",
        "comparison_sheet",
        "repaired_glyph",
        "unread_second",
        "proposal",
        "clean_control",
    ):
        assert counts[tag] >= 1, tag
    pack = json.loads((tmp_path / "pack/pack.json").read_text(encoding="utf-8"))
    assert pack["schema"] == "hla-review-pack/v1"
    assert pack["n_documents"] == 24


def test_a_document_lands_in_its_rarest_stratum_but_keeps_every_tag(tmp_path: Path) -> None:
    module = load()
    db, export = synthetic_corpus(tmp_path, n_docs=8)
    module.build_pack(db, export, tmp_path / "pack", 8, 1, PAGE)
    pack = json.loads((tmp_path / "pack/pack.json").read_text(encoding="utf-8"))
    flagged = next(d for d in pack["documents"] if d["consistency"] == "FORBIDDEN_GENE_PRESENT")
    assert flagged["primary_tag"] == "consistency_flag"
    assert flagged["tags"][0] == "consistency_flag"


def test_a_rare_stratum_is_not_eaten_by_a_common_one(tmp_path: Path) -> None:
    """A document belongs to its rarest signal, not to whichever signal sits
    higher in STRATA.

    This is the bug that emptied the reviewer's own stratum. `odd_box` holds 22
    documents in the real corpus and `repaired_glyph` holds 11,179, but
    `repaired_glyph` is written first, so every document carrying both was
    pooled as a repaired glyph and `odd_box` drew nothing at all. Rarity is what
    decides: one of 22 witnesses is worth more than one of 11,179.
    """
    module = load()
    db, export = synthetic_corpus(tmp_path)
    con = sqlite3.connect(db)
    # Document 5 already carries `repaired_glyph`, the commoner signal. Give it
    # a value box unlike the others on its page as well.
    sha = hashlib.sha256(b"synthetic report 5").hexdigest()
    stretched = json.dumps([[0.25, 0.10, 0.30, 0.60], [0.32, 0.10, 0.37, 0.60]])
    con.execute("UPDATE fact SET value_boxes=? WHERE sha256=? AND field='DRB1'", (stretched, sha))
    con.commit()
    con.close()
    counts = module.build_pack(db, export, tmp_path / "pack", 24, 1, PAGE)
    assert counts["odd_box"] >= 1
    pack = json.loads((tmp_path / "pack/pack.json").read_text(encoding="utf-8"))
    document = next(d for d in pack["documents"] if d["id"] == sha[:16])
    assert document["primary_tag"] == "odd_box"
    assert "repaired_glyph" in document["tags"]


def test_the_blank_paper_stratum_reads_the_column_the_ink_pass_writes(
    tmp_path: Path,
) -> None:
    """`cell_ink` names the column `decision`.

    The query asked for `verdict`, and a blanket `except OperationalError` —
    written to tolerate a database from before the ink pass — reported the whole
    stratum as empty instead of raising. 14,210 measured-blank cells went
    unreviewable that way, and HA-012, which asks whether a blank cell means the
    laboratory did not test that locus, is the largest open question in the
    project. A missing table is tolerated; a wrong column is not.
    """
    module = load()
    db, export = synthetic_corpus(tmp_path)
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE cell_ink (sha256, field, extraction_version, ink_version, region, "
        "fraction, coverage, longest_run, paper, decision, created_utc)"
    )
    sha = hashlib.sha256(b"synthetic report 3").hexdigest()
    for locus in ("DQA1", "DPA1", "DPB1"):
        con.execute(
            "INSERT INTO cell_ink VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (sha, locus, "facts/v1", "ink/v1", "cell", 0.0, 0.0, 0, 1.0, "BLANK", "t"),
        )
    con.commit()
    con.close()
    counts = module.build_pack(db, export, tmp_path / "pack", 24, 1, PAGE)
    assert counts["blank_paper"] >= 1


def test_the_pack_is_deterministic_for_a_seed(tmp_path: Path) -> None:
    """Two people must be able to label the same documents."""
    module = load()
    db, export = synthetic_corpus(tmp_path)
    module.build_pack(db, export, tmp_path / "a", 20, 7, PAGE)
    module.build_pack(db, export, tmp_path / "b", 20, 7, PAGE)
    ids = lambda p: [d["id"] for d in json.loads((p / "pack.json").read_text("utf-8"))["documents"]]  # noqa: E731
    assert ids(tmp_path / "a") == ids(tmp_path / "b")


def test_cell_ids_and_the_pipeline_file_match_the_golden_conventions(tmp_path: Path) -> None:
    """`golden_score.py` reads labels and the pipeline's answers by cell id
    `<sha256[:16]>:<LOCUS>`; a pack that used any other id could not be scored."""
    module = load()
    db, export = synthetic_corpus(tmp_path, n_docs=8)
    module.build_pack(db, export, tmp_path / "pack", 4, 1, PAGE)
    pipeline = json.loads((tmp_path / "pack/pipeline.json").read_text(encoding="utf-8"))
    pack = json.loads((tmp_path / "pack/pack.json").read_text(encoding="utf-8"))
    for doc in pack["documents"]:
        for cell in doc["cells"]:
            assert cell["cell_id"] == f"{doc['sha256'][:16]}:{cell['locus']}"
            entry = pipeline["cells"][cell["cell_id"]]
            # `second_allele` rides along so a declared partial read scores the
            # same through golden_score.py and pack_score.py (KI-015).
            assert set(entry) == {"status", "locus", "value", "rule", "second_allele"}
            assert entry["status"] == cell["status"]


def test_every_engine_reading_travels_with_the_cell(tmp_path: Path) -> None:
    """The page shows what each engine read; a cell without them is a blind
    label, which is the other tool's job."""
    module = load()
    db, export = synthetic_corpus(tmp_path, n_docs=8)
    suggestions = tmp_path / "sugg"
    suggestions.mkdir()
    (suggestions / "newengine.json").write_text(
        json.dumps(
            {
                "engine": "newengine",
                "cells": {
                    hashlib.sha256(b"synthetic report 0").hexdigest()[:16] + ":A": "A*11 A*15"
                },
            }
        ),
        encoding="utf-8",
    )
    module.build_pack(db, export, tmp_path / "pack", 8, 1, PAGE, suggestions)
    pack = json.loads((tmp_path / "pack/pack.json").read_text(encoding="utf-8"))
    cell = next(c for d in pack["documents"] for c in d["cells"] if c["locus"] == "B")
    assert set(cell["suggestions"]) == {"pipeline", "tesseract5", "ppocrv5", "decode"}, (
        "every confirmer gets its own row; keying them together would show the "
        "reader whichever engine the database returned last"
    )
    assert cell["suggestions"]["decode"]["votes"] == {"0:11": 9}
    assert pack["engines"] == ["newengine"]
    assert (
        pack["suggestions"]["newengine"][
            hashlib.sha256(b"synthetic report 0").hexdigest()[:16] + ":A"
        ]
        == "A*11 A*15"
    )


def test_a_refused_cell_shows_the_row_not_nothing(tmp_path: Path) -> None:
    """The reader has to be able to see what the resolver refused."""
    module = load()
    db, export = synthetic_corpus(tmp_path, n_docs=8)
    module.build_pack(db, export, tmp_path / "pack", 8, 1, PAGE)
    pack = json.loads((tmp_path / "pack/pack.json").read_text(encoding="utf-8"))
    refused = [c for d in pack["documents"] for c in d["cells"] if c["status"] == "REVIEW_REQUIRED"]
    assert refused
    for cell in refused:
        assert cell["crop"] and (tmp_path / "pack" / cell["crop"]).exists()
        assert cell["suggestions"]["pipeline"]["reason"]


def test_the_page_never_reaches_the_network_and_records_anchoring() -> None:
    """The reports are the patients'. Nothing on this page may leave the
    machine, and an export from it says it was made with the suggestions
    visible, so it is never mistaken for a blind golden label.

    The check is on what the page LOADS, not on the characters `http`: the
    storage warning names a localhost address in prose, which fetches nothing.
    """
    page = PAGE.read_text(encoding="utf-8")
    assert "window.PACK" in page
    for reaching_out in ("fetch(", "XMLHttpRequest", "WebSocket", "navigator.sendBeacon"):
        assert reaching_out not in page
    for attribute in ('src="http', "src='http", 'href="http', "href='http", "@import"):
        assert attribute not in page
    assert "anchored: true" in page
    assert "golden-labels/v1" in page
    for decision in ("APPROVED", "EDITED", "ADDED"):
        assert decision in page
    for state in (
        "VALUE",
        "NOT_PRINTED",
        "BLANK",
        "UNREADABLE",
        "PRESENT_ONLY",
        "ABSENT",
        "NOT_A_REPORT",
    ):
        assert f"'{state}'" in page


def test_the_pack_directory_is_never_committable() -> None:
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/review/*" in ignore


def test_an_export_from_the_page_scores_against_the_pack(tmp_path: Path) -> None:
    """The whole point of the pack, end to end.

    `HA-008` tells a person to label and hand the JSON to an agent, who scores
    it with `golden_score.py`. Three files have to agree on one shape for that
    to work — the page's export, the pack's `pipeline.json`, and the scorer —
    and they live apart, so this pins them together: a corrected cell must come
    back as a false acceptance, and the scorer must fail on it.
    """
    module = load()
    db, export = synthetic_corpus(tmp_path, n_docs=20)
    pack_dir = tmp_path / "pack"
    module.build_pack(db, export, pack_dir, 8, 1, PAGE)
    pack = json.loads((pack_dir / "pack.json").read_text(encoding="utf-8"))

    cells: dict[str, object] = {}
    corrected: str | None = None
    for document in pack["documents"]:
        for cell in document["cells"]:
            body = [p.split("*")[-1] for p in (cell["value"] or "").split() if p]
            if cell["status"] != "RESOLVED":
                state, alleles = "NOT_PRINTED", []
            elif cell["kind"] == "DRBX":
                state = "ABSENT" if cell["value"] == "ABSENT" else "PRESENT_ONLY"
                alleles = []
            elif corrected is None:
                corrected, state, alleles = cell["cell_id"], "VALUE", ["11", "16"]
            else:
                state, alleles = "VALUE", body
            cells[cell["cell_id"]] = {
                "locus": cell["locus"],
                "state": state,
                "alleles": alleles,
                "resolution": "FIRST_FIELD" if state == "VALUE" else None,
                "unsure": False,
            }
    assert corrected, "the fixture must contain a resolved cell to disagree with"
    labels = tmp_path / "labels_tester.json"
    labels.write_text(
        json.dumps(
            {"schema": "golden-labels/v1", "annotator": "tester", "anchored": True, "cells": cells}
        ),
        encoding="utf-8",
    )

    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(ROOT / "scripts/golden_score.py"),
            "--labels",
            str(labels),
            str(labels),
            "--hidden",
            str(pack_dir / "pipeline.json"),
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 1, "a false acceptance must fail the gate"
    assert corrected in result.stdout
    assert "FALSE ACCEPTANCE  : 1" in result.stdout


def test_the_pack_can_serve_itself(tmp_path: Path) -> None:
    """A browser may refuse `localStorage` to a page opened off the disk, and
    the labels live there. The page says so if it happens, but the pack also
    ships the one click that makes the question moot."""
    module = load()
    db, export = synthetic_corpus(tmp_path, n_docs=8)
    module.build_pack(db, export, tmp_path / "pack", 4, 1, PAGE)
    windows = (tmp_path / "pack/serve.cmd").read_bytes()
    assert b"http.server" in windows and b"127.0.0.1" in windows
    assert windows.startswith(b"@echo off\r\n"), "cmd.exe wants CRLF, and exactly one"
    assert b"\r\r" not in windows, "the platform translated the line endings twice"
    assert b"127.0.0.1" in (tmp_path / "pack/serve.sh").read_bytes()
    page = PAGE.read_text(encoding="utf-8")
    assert "storageWorks" in page, "and the page must still notice when it cannot save"


def test_the_page_preselects_the_state_the_refusal_reason_implies() -> None:
    """1,650 cells in a 150-document pack, and 850 of them are the pipeline
    saying it read nothing for a reason it already recorded.

    "no anchor on this document" means the form does not print that locus;
    "no box at all in its cell" means it does and the cell is empty. Making the
    reader pick that from a dropdown 850 times would cost the labelling its
    afternoon, and the reason is already in the pack.
    """
    page = PAGE.read_text(encoding="utf-8")
    assert "function defaultStateFor(cell)" in page
    assert "no anchor on this document" in page
    assert "no box at all" in page
    for state in ("NOT_PRINTED", "BLANK"):
        assert state in page.split("function defaultStateFor(cell)")[1].split("}")[0] or True
    body = page.split("function defaultStateFor(cell)")[1][:900]
    assert "'NOT_PRINTED'" in body and "'BLANK'" in body and "'VALUE'" in body


def test_a_chat_exported_twice_does_not_repeat_its_messages(tmp_path: Path) -> None:
    """A re-export is a new export_id holding the same posts. The same caption
    must not appear twice, spend the cap on itself, or inflate the total."""
    module = load()
    source = synthetic_source(tmp_path)
    con = sqlite3.connect(source)
    for message_id, sent, text in (
        (90, "28.08.2026 09:00:00 UTC+03:30", LONG_CAPTION),
        (100, "02.09.2026 10:00:00 UTC+03:30", DONOR_CAPTION),
    ):
        con.execute(
            f"INSERT INTO source_message ({SOURCE_MESSAGE_COLUMNS}) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "exp2",
                "messages.html",
                message_id,
                f"message{message_id}",
                f"h{message_id}",
                "telegram-html/v1",
                sent,
                "Poster One",
                0,
                None,
                None,
                None,
                None,
                0,
                text,
                "[]",
                "[]",
                "[]",
                "t",
                "t",
            ),
        )
        con.execute(
            "INSERT INTO document_message VALUES (?,?,?,?,?,?)",
            (sha_of(0), "exp2", "messages.html", message_id, None, "photos/x.jpg"),
        )
    con.commit()
    con.close()
    totals: dict[str, int] = {}
    found = module.load_messages(source, {sha_of(0), sha_of(3)}, totals)
    assert [m["message_id"] for m in found[sha_of(0)]] == [90, 100, 250]
    assert totals[sha_of(0)] == 3
    # Ten postings under two export ids: the duplicate export must add none of
    # them again, whatever the cap is.
    assert len(found[sha_of(3)]) == min(10, module.MAX_MESSAGES)
    assert totals[sha_of(3)] == 10, "the total counts what the cap cut"
    records = [{"sha256": sha_of(3)}]
    module.attach_messages(records, source)
    assert records[0]["n_messages_total"] == 10
    assert len(records[0]["messages"]) == min(10, module.MAX_MESSAGES)


def test_promoted_and_ink_certified_cells_are_strata_of_their_own(tmp_path: Path) -> None:
    """The two rules the next labels must test: a value two engines agreed on
    where the primary text did not parse, and an absence certified by paper."""
    module = load()
    db, export = synthetic_corpus(tmp_path, n_docs=3)
    con = sqlite3.connect(db)
    shas = [row[0] for row in con.execute("SELECT DISTINCT sha256 FROM fact ORDER BY sha256")]
    con.execute(
        "UPDATE fact SET source='decode+ppocrv5', repaired=1 WHERE sha256=? AND field='DQB1'",
        (shas[0],),
    )
    con.execute(
        "UPDATE fact SET source='ink-certified', value='ABSENT' WHERE sha256=? AND field='DRB5'",
        (shas[1],),
    )
    con.commit()
    docs = module.load_documents(con)
    con.close()
    tags = {sha: module.tag_document(docs[sha], export) for sha in shas}
    assert "promoted" in tags[shas[0]] and "ink_certified" not in tags[shas[0]]
    assert "ink_certified" in tags[shas[1]] and "promoted" not in tags[shas[1]]
    assert "promoted" not in tags[shas[2]] and "ink_certified" not in tags[shas[2]]
    assert {t for t, _, _ in module.STRATA} >= {"promoted", "ink_certified"}


def test_the_page_carries_an_optional_note_on_every_answer() -> None:
    """A note outlives the answer it was written beside, so it is stored in a
    map of its own rather than inside a label: re-confirming a row, marking the
    page "not a report" or answering twice must not lose it, and a cell with no
    answer may still carry one. It rides back in the export."""
    page = PAGE.read_text(encoding="utf-8")
    assert "labels.notes" in page and "notes: labels.notes" in page, "stored and exported"
    assert "labels.notes = labels.notes || {}" in page, "an older saved state gains the map"
    # every answerable row offers one: the HLA cells and the DRB3/4/5 row
    assert page.count("noteButtonHtml(") >= 3, "declared, on a cell row, and on the DRBX row"
    assert page.count("noteFieldHtml(") >= 3
    assert "data-docnote" in page, "and the document has one of its own"
    # a note is never part of the label object, which the scorers read
    label_write = page.split("labels.cells[cell.cell_id] = {")[1].split("};")[0]
    assert "note" not in label_write, "a note must not ride inside a label"
    # Enter inside a note saves it and does not confirm the row underneath
    handler = page.split("panel.addEventListener('keydown'")[1][:900]
    assert "data-notetext" in handler and "stopPropagation" in handler
