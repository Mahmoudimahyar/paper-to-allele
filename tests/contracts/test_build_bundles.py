"""Deriving bundles into the store: what re-running is allowed to do.

Runs on a synthetic source database built here; nothing touches the archive.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.task("HIST-002")

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/build_bundles.py"


def load():
    spec = importlib.util.spec_from_file_location("km_build_bundles", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["km_build_bundles"] = module
    spec.loader.exec_module(module)
    return module


def synthetic_source(path: Path) -> None:
    """One joined media run, one lone message, and a reply."""
    from kidneymatch.ingestion.source_store import SCHEMA as SOURCE_SCHEMA

    con = sqlite3.connect(path)
    con.executescript(SOURCE_SCHEMA)
    con.execute(
        "INSERT INTO source_export VALUES ('E','/tmp/x','HTML',1,'t','t','telegram-html/v1')"
    )
    rows = [
        # id, joined, media count, reply target, minute
        (1, 0, 2, None, "01.01.2020 10:00:00"),
        (2, 1, 1, None, "01.01.2020 10:01:00"),
        (3, 0, 0, 1, "01.01.2020 10:30:00"),
    ]
    for message_id, joined, n_media, reply, stamp in rows:
        media = "[]" if not n_media else "[" + ",".join(['{"href":"p.jpg"}'] * n_media) + "]"
        con.execute(
            "INSERT INTO source_message VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "E",
                "messages.html",
                message_id,
                f"message{message_id}",
                f"hash{message_id}",
                "telegram-html/v1",
                stamp,
                "Poster" if message_id != 3 else "Enquirer",
                joined,
                None,
                None,
                reply,
                None,
                joined,
                "",
                media,
                "[]",
                "[]",
                "t",
                "t",
            ),
        )
    con.commit()
    con.close()


def test_a_joined_media_run_becomes_one_bundle_in_the_store(tmp_path: Path) -> None:
    module = load()
    database = tmp_path / "source.sqlite"
    synthetic_source(database)
    assert module.run(database) == 0

    con = sqlite3.connect(database)
    bundles = con.execute(
        "SELECT bundle_id, bundle_type, n_members, n_media FROM message_bundle ORDER BY bundle_id"
    ).fetchall()
    con.close()
    assert bundles == [
        ("messages.html:1", "MEDIA_GROUP", 2, 3),
        ("messages.html:3", "SINGLE", 1, 0),
    ]


def test_rebuilding_replaces_the_derivation_rather_than_appending(tmp_path: Path) -> None:
    """Bundles are derived. A stale row from an older bundler is worse than
    none, and appending would double every count downstream."""
    module = load()
    database = tmp_path / "source.sqlite"
    synthetic_source(database)
    module.run(database)
    module.run(database)

    con = sqlite3.connect(database)
    counts = {
        table: con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]  # noqa: S608
        for table in ("message_bundle", "bundle_message", "bundle_reply_link")
    }
    con.close()
    assert counts == {"message_bundle": 2, "bundle_message": 3, "bundle_reply_link": 1}


def test_a_suggestion_is_never_written_as_a_membership(tmp_path: Path) -> None:
    """The whole point of the weak tier: it goes in its own table, where
    nothing that reads memberships can mistake it for one."""
    module = load()
    database = tmp_path / "source.sqlite"
    synthetic_source(database)
    module.run(database)

    con = sqlite3.connect(database)
    relations = {row[0] for row in con.execute("SELECT DISTINCT relation FROM bundle_message")}
    suggested = {
        row[0] for row in con.execute("SELECT DISTINCT relation FROM bundle_adjacency_suggestion")
    }
    con.close()
    assert "WEAK_CONTEXT" not in relations
    assert relations <= {"PRIMARY", "JOINED"}
    assert suggested <= {"WEAK_CONTEXT"}


def test_the_derivation_never_writes_to_the_source_tables() -> None:
    """Historical raw input is immutable. A derivation that could edit it would
    make the archive unreproducible."""
    body = SCRIPT.read_text(encoding="utf-8")
    for statement in ("UPDATE source_", "DELETE FROM source_", "INSERT INTO source_"):
        assert statement not in body
