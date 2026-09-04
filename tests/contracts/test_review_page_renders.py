"""The review page comes up at all.

This is the test that was missing. `tools/hla_review.html` shipped with a
temporal-dead-zone `ReferenceError` on line 2 of its startup path: `load()` was
called before the `let` it reads existed, so the script died before rendering a
single row and the page was blank. Every existing test read the HTML as *text*
— they all passed, and the tool was unusable.

Reading a script cannot tell you whether it runs. So this one runs it, against
a small DOM stub, and asserts that a document actually reached the panel.

Node is the runtime because the page is plain browser JavaScript and the repo
has no browser-automation dependency. Where node is absent the test SKIPS and
says so loudly rather than passing quietly: a skip that reads like a pass is how
the original bug survived.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.task("BOOT-001")

ROOT = Path(__file__).resolve().parents[2]
SMOKE = ROOT / "tests/tools/review_page_smoke.mjs"
PAGE = ROOT / "tools/hla_review.html"

node = shutil.which("node")
needs_node = pytest.mark.skipif(
    node is None,
    reason="node is not installed, so the review page's script cannot be executed here; "
    "the page is then only checked as text, which is what let a blank page ship",
)


def synthetic_pack(tmp_path: Path) -> Path:
    """A small real pack, built by the pack script itself."""
    fixture = importlib.util.spec_from_file_location(
        "km_pack_fixture_render", Path(__file__).with_name("test_review_pack.py")
    )
    module = importlib.util.module_from_spec(fixture)
    assert fixture is not None and fixture.loader is not None
    sys.modules["km_pack_fixture_render"] = module
    fixture.loader.exec_module(module)

    spec = importlib.util.spec_from_file_location("km_pack_render", ROOT / "scripts/review_pack.py")
    pack = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["km_pack_render"] = pack
    spec.loader.exec_module(pack)

    db, export = module.synthetic_corpus(tmp_path, n_docs=10)
    out = tmp_path / "pack"
    pack.build_pack(db, export, out, 6, 1, PAGE)
    return out


def smoke(page: Path, pack_js: Path) -> dict:
    result = subprocess.run(  # noqa: S603
        [str(node), str(SMOKE), str(page), str(pack_js)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    line = (result.stdout or "").strip().splitlines()
    assert line, f"the smoke runner printed nothing; stderr:\n{result.stderr}"
    return json.loads(line[-1])


@needs_node
def test_the_page_starts_and_renders_a_document(tmp_path: Path) -> None:
    """The whole point: it must not throw, and it must put a document on screen."""
    out = synthetic_pack(tmp_path)
    report = smoke(out / "index.html", out / "pack.js")
    assert report["error"] is None, report["error"]
    assert report["started"] is True
    assert report["renderedHtmlLength"] > 500, "the panel is empty"
    assert "cells" in report["wroteProgress"], report["wroteProgress"]
    assert "documents done" in report["wroteProgress"], report["wroteProgress"]
    assert report["ok"] is True


@needs_node
def test_the_smoke_test_actually_catches_a_dead_script(tmp_path: Path) -> None:
    """A regression test that cannot fail is decoration.

    This reintroduces the exact defect that shipped — a `load()` above the
    `let storageWorks` it reads — and requires the runner to report it.
    """
    out = synthetic_pack(tmp_path)
    source = PAGE.read_text(encoding="utf-8")
    anchor = "  // Whether this browser will actually keep anything."
    assert anchor in source, "the startup section moved; update this test with it"
    broken = tmp_path / "broken.html"
    broken.write_text(source.replace(anchor, "  let early = load();\n\n" + anchor, 1), "utf-8")

    report = smoke(broken, out / "pack.js")
    assert report["ok"] is False
    assert "storageWorks" in (report["error"] or ""), report["error"]


@needs_node
def test_a_pack_with_no_documents_does_not_crash_the_page(tmp_path: Path) -> None:
    """An empty pack is an operator error, not a stack trace. The page has to
    say something rather than throwing on `PACK.documents[0]`."""
    out = synthetic_pack(tmp_path)
    empty = json.loads((out / "pack.json").read_text(encoding="utf-8"))
    empty["documents"] = []
    empty["n_cells"] = 0
    empty["n_documents"] = 0
    pack_js = tmp_path / "empty.js"
    pack_js.write_text("window.PACK = " + json.dumps(empty) + ";\n", encoding="utf-8")

    report = smoke(out / "index.html", pack_js)
    assert report["error"] is None, f"an empty pack should not throw: {report['error']}"
