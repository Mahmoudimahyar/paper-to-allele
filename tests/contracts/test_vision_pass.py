"""The pass that sends a real report page off the machine.

Every test here guards something the project doctrine says outright: a
credential must never be echoed, a derived medical fact must keep its
provenance, and the sample must be what a person named rather than whatever the
code could reach. The network is never touched; these exercise the parsing, the
key handling and the scope guard.

Coordinates matter more than they look. The whole purpose of the pass is to put
Vision's boxes in the same normalised frame as `ocr_pass.sqlite` so that
`ocr/anchors.py` can be asked the identical question of both. A box that is
silently wrong there produces a comparison that looks like a measurement and is
not one.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from vision_pass import (  # noqa: E402
    ALLOWED_OUTPUT_ROOT,
    KEY_VARIABLE,
    MissingKey,
    Rejected,
    Unreachable,
    _quad,
    documents_from_export,
    documents_from_pack,
    parse_response,
    read_key,
    run,
)

# A fabricated key. No run of ten digits: `scripts/scan_pii.py` reads one as an
# Iranian national ID, and that check is worth more than a realistic-looking
# constant (`scripts/confirm_pass.py` records the same trade-off).
SECRET = "AIza-THIS-IS-NOT-A-REAL-KEY-fabricated-for-tests"


def vertices(*points: tuple[int, int]) -> list[dict[str, int]]:
    return [{"x": x, "y": y} for x, y in points]


def test_a_polygon_becomes_a_normalised_box() -> None:
    box = _quad(vertices((10, 20), (110, 20), (110, 60), (10, 60)), 1000, 200)
    assert box == [0.01, 0.1, 0.11, 0.3]


def test_vision_omits_a_zero_coordinate_and_the_box_still_starts_at_zero() -> None:
    """Vision leaves `x` out when it is 0; a missing key is 0, not a skip."""
    box = _quad([{"y": 20}, {"x": 100, "y": 20}, {"x": 100, "y": 60}, {"y": 60}], 1000, 200)
    assert box is not None
    assert box[0] == 0.0


def test_a_rotated_quadrilateral_becomes_its_enclosing_rectangle() -> None:
    """The rest of the pipeline speaks axis-aligned boxes and nothing else."""
    box = _quad(vertices((10, 20), (110, 30), (108, 70), (8, 60)), 200, 100)
    assert box == [0.04, 0.2, 0.55, 0.7]


def test_a_degenerate_or_impossible_box_is_dropped_rather_than_stored() -> None:
    assert _quad(vertices((10, 20), (10, 20), (10, 20), (10, 20)), 100, 100) is None
    assert _quad([], 100, 100) is None
    assert _quad(vertices((10, 20), (110, 60)), 0, 100) is None


def test_the_whole_page_entry_is_not_a_word() -> None:
    """`textAnnotations[0]` is the entire page; taking it would add a box that
    covers the sheet and is aligned with every row on it."""
    payload = {
        "textAnnotations": [
            {
                "description": "everything",
                "boundingPoly": {"vertices": vertices((0, 0), (100, 0), (100, 100), (0, 100))},
            },
            {
                "description": "HLA-A",
                "boundingPoly": {"vertices": vertices((10, 10), (50, 10), (50, 20), (10, 20))},
            },
        ]
    }
    parsed = parse_response(payload, 100, 100)
    assert parsed["texts"] == ["HLA-A"]
    assert len(parsed["boxes"]) == 1


def test_a_page_with_no_text_parses_to_nothing_rather_than_failing() -> None:
    parsed = parse_response({}, 100, 100)
    assert parsed["boxes"] == []
    assert parsed["texts"] == []
    assert not parsed["full_text"]


def test_the_full_text_falls_back_to_the_page_entry() -> None:
    payload = {"textAnnotations": [{"description": "page text", "boundingPoly": {"vertices": []}}]}
    assert parse_response(payload, 100, 100)["full_text"] == "page text"


def test_boxes_and_texts_stay_in_step_when_one_polygon_is_unusable() -> None:
    """A dropped box must drop its word too, or every later box names the
    wrong token and the comparison is silently meaningless."""
    payload = {
        "textAnnotations": [
            {"description": "page", "boundingPoly": {"vertices": []}},
            {"description": "bad", "boundingPoly": {"vertices": vertices((5, 5), (5, 5))}},
            {
                "description": "HLA-B",
                "boundingPoly": {"vertices": vertices((10, 10), (50, 10), (50, 20), (10, 20))},
            },
        ]
    }
    parsed = parse_response(payload, 100, 100)
    assert parsed["texts"] == ["HLA-B"]
    assert len(parsed["boxes"]) == len(parsed["texts"])


def test_the_environment_beats_the_dotenv_file(tmp_path: Path, monkeypatch) -> None:
    env = tmp_path / ".env"
    env.write_text(f"{KEY_VARIABLE}=from-the-file\n", encoding="utf-8")
    monkeypatch.setenv(KEY_VARIABLE, SECRET)
    assert read_key(env) == SECRET


def test_a_key_is_read_from_the_dotenv_file_with_its_quotes_stripped(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv(KEY_VARIABLE, raising=False)
    env = tmp_path / ".env"
    env.write_text(f'OTHER=x\n{KEY_VARIABLE}="{SECRET}"  \n', encoding="utf-8")
    assert read_key(env) == SECRET


def test_a_missing_key_names_the_variable_and_never_a_value(tmp_path: Path, monkeypatch) -> None:
    """The message a person sees when nothing was sent."""
    monkeypatch.delenv(KEY_VARIABLE, raising=False)
    env = tmp_path / ".env"
    env.write_text("SOMETHING_ELSE=value\n", encoding="utf-8")
    with pytest.raises(MissingKey) as raised:
        read_key(env)
    said = str(raised.value)
    assert KEY_VARIABLE in said
    assert "value" not in said.split(KEY_VARIABLE)[-1].replace("Nothing was sent.", "")
    assert "Nothing was sent" in said


def facts_with(tmp_path: Path, digests: list[str]) -> Path:
    path = tmp_path / "facts.sqlite"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE document (sha256 TEXT, rel_path TEXT, extraction_version TEXT)")
    con.executemany(
        "INSERT INTO document VALUES (?,?,'facts/v1')",
        [(d, f"photos/{d[:4]}.jpg") for d in digests],
    )
    con.commit()
    con.close()
    return path


def test_only_the_documents_a_person_labelled_are_selected(tmp_path: Path) -> None:
    wanted, other = "a" * 64, "b" * 64
    facts = facts_with(tmp_path, [wanted, other])
    export = tmp_path / "labels.json"
    export.write_text(
        '{"schema": "golden-labels/v1", "cells": {"' + wanted[:16] + ':A": {}}}',
        encoding="utf-8",
    )
    found, failed = documents_from_export([export], facts)
    assert [sha for sha, _ in found] == [wanted]
    assert failed == []


def test_an_empty_export_selects_nothing_and_reports_no_failure(tmp_path: Path) -> None:
    """The guard that stops a typo becoming a run over the whole corpus."""
    facts = facts_with(tmp_path, ["a" * 64, "b" * 64])
    empty = tmp_path / "empty.json"
    empty.write_text('{"cells": {}}', encoding="utf-8")
    assert documents_from_export([empty], facts) == ([], [])


def test_an_unreadable_export_is_reported_rather_than_skipped(tmp_path: Path) -> None:
    """Silently shrinking the sample would look like a completed run."""
    facts = facts_with(tmp_path, ["a" * 64])
    absent = tmp_path / "absent.json"
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    listed = tmp_path / "list.json"
    listed.write_text("[1, 2, 3]", encoding="utf-8")
    for path in (absent, broken, listed):
        found, failed = documents_from_export([path], facts)
        assert found == []
        assert failed == [path]


def test_an_unreadable_pack_is_reported_rather_than_crashing(tmp_path: Path) -> None:
    facts = facts_with(tmp_path, ["a" * 64])
    assert documents_from_pack(tmp_path / "absent.json", facts) == ([], [tmp_path / "absent.json"])
    odd = tmp_path / "pack.json"
    odd.write_text('{"documents": "not a list"}', encoding="utf-8")
    assert documents_from_pack(odd, facts) == ([], [odd])


def test_a_key_with_a_trailing_comment_is_read_without_it(tmp_path: Path, monkeypatch) -> None:
    """`KEY=value # rotated 2026-09-01` is a line people write."""
    monkeypatch.delenv(KEY_VARIABLE, raising=False)
    env = tmp_path / ".env"
    env.write_text(f"{KEY_VARIABLE}={SECRET} # rotated\n", encoding="utf-8")
    assert read_key(env) == SECRET


def test_an_export_prefix_and_a_byte_order_mark_do_not_hide_the_key(
    tmp_path: Path, monkeypatch
) -> None:
    """A BOM on the first line otherwise hides a key that is really there."""
    monkeypatch.delenv(KEY_VARIABLE, raising=False)
    env = tmp_path / ".env"
    body = f"export {KEY_VARIABLE}={SECRET}\n"
    env.write_bytes(b"\xef\xbb\xbf" + body.encode())
    assert read_key(env) == SECRET


def test_a_key_holding_whitespace_is_refused_and_never_printed(tmp_path: Path, monkeypatch) -> None:
    """A mangled secret in a URL used to be printed verbatim by a traceback."""
    monkeypatch.delenv(KEY_VARIABLE, raising=False)
    env = tmp_path / ".env"
    env.write_text(f'{KEY_VARIABLE}="{SECRET} trailing words"\n', encoding="utf-8")
    with pytest.raises(MissingKey) as raised:
        read_key(env)
    assert SECRET not in str(raised.value)
    assert "Nothing was sent" in str(raised.value)


def test_the_key_is_sent_as_a_header_and_never_in_the_url() -> None:
    """The whole class of secret-in-a-traceback leaks lives in the query string."""
    source = (ROOT / "scripts" / "vision_pass.py").read_text(encoding="utf-8")
    assert "X-Goog-Api-Key" in source
    assert "?key=" not in source


def test_limit_zero_sends_nothing(tmp_path: Path) -> None:
    """`--limit 0` asked for nothing; truthiness used to send the whole sample."""
    out = tmp_path / "vision.sqlite"
    tally = run([("a" * 64, "photos/a.jpg")], tmp_path, out, "unused-key", limit=0)
    assert tally["pages read"] == 0
    assert tally["held back by --limit"] == 1


def test_the_output_must_live_in_the_ignored_tree() -> None:
    """The stop hook commits with `git add -A`; this store is report text."""
    assert ALLOWED_OUTPUT_ROOT.name == "derived"
    source = (ROOT / "scripts" / "vision_pass.py").read_text(encoding="utf-8")
    assert "is_relative_to(ALLOWED_OUTPUT_ROOT.resolve())" in source


def test_a_refusal_and_a_silence_are_different_kinds_of_failure() -> None:
    """One means stop; the other means try the next page."""
    assert issubclass(Rejected, RuntimeError)
    assert issubclass(Unreachable, RuntimeError)
    assert not issubclass(Rejected, Unreachable)
