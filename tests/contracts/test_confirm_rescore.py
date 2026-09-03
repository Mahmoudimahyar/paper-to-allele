"""Re-judging stored confirmer readings when the comparison rule changes."""

from __future__ import annotations

import importlib.util
import inspect
import sqlite3
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.task("BOOT-001")

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/confirm_pass.py"


def load():
    spec = importlib.util.spec_from_file_location("km_confirm_pass", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["km_confirm_pass"] = module
    spec.loader.exec_module(module)
    return module


def test_rescore_moves_a_star_less_reading_to_a_verdict_without_running_ocr(tmp_path: Path) -> None:
    """`A02` for an accepted `A*02` was UNCONFIRMED under the old rule. The
    reading is evidence already gathered; the rule is what changed."""
    module = load()
    db = tmp_path / "facts.sqlite"
    con = sqlite3.connect(db)
    con.executescript(module.SCHEMA)
    con.execute("CREATE TABLE fact (sha256, field, extraction_version, status, value)")
    con.execute("INSERT INTO fact VALUES ('s', 'A', 'facts/v1', 'RESOLVED', 'A*02')")
    con.execute("INSERT INTO fact VALUES ('s', 'B', 'facts/v1', 'RESOLVED', 'B*07')")
    con.execute(
        "INSERT INTO confirmation VALUES ('s', 'A', 'facts/v1', ?, 'UNCONFIRMED', 'A02', 't')",
        (module.CONFIRMER_VERSION,),
    )
    con.execute(
        "INSERT INTO confirmation VALUES ('s', 'B', 'facts/v1', ?, 'UNCONFIRMED', 'B7', 't')",
        (module.CONFIRMER_VERSION,),
    )
    con.commit()
    con.close()

    assert module.rescore(db) == 0
    con = sqlite3.connect(db)
    verdicts = dict(con.execute("SELECT field, verdict FROM confirmation"))
    assert verdicts == {"A": "CONFIRMED", "B": "UNCONFIRMED"}
    readings = dict(con.execute("SELECT field, reading FROM confirmation"))
    assert readings == {"A": "A02", "B": "B7"}, "the evidence itself must not change"


def test_rescore_never_touches_an_image_or_the_binary() -> None:
    module = load()
    source = inspect.getsource(module.rescore)
    for forbidden in ("read_crops", "Image", "export", "binary"):
        assert forbidden not in source
