"""The extraction's three answers for a page with no layout family.

Written before the code. 11,210 of 23,566 documents carry no family, and the
review of that population found three separate reasons and one measured fix
each:

* **A tie between prototypes that are one form under lean** — 987 pages fit
  inside `MAX_RESIDUAL` and were refused only because a second prototype fitted
  nearly as well. Assigning the best when the tied prototypes author one rule
  and print one row order gains 649 cells against the default rule.
* **A page whose stack fits except at one label** — 318 pages, where the
  recognizer boxed one label's `HLA-` prefix apart. The left-out fit assigns
  them; the virtual-anchor path must NOT run there, because the page's own
  full fit is what failed.
* **A form whose locus labels are column headers** — 305 pages, where every
  value sits in the cell beneath its label. `ocr/layout.py` has been able to
  say so since the reviewer described one, and until now only
  `page_ocr_bind.py` acted on it.

And one fallback the tie measurement asked for: on 18 pages the family rule
refuses a value for naming no locus where the default rule reads the page
fine, so the page goes back to the default rule whole.

Synthetic geometry, fabricated allele values, no patient data.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.task("OCR-001")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from kidneymatch.hla.vocabulary import load_vocabulary  # noqa: E402
from kidneymatch.ocr.anchors import Box  # noqa: E402
from kidneymatch.ocr.store import OcrDocument  # noqa: E402


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"km_{name}", ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[f"km_{name}"] = module
    spec.loader.exec_module(module)
    return module


extract_facts = load("extract_facts")
LayoutPrototype = __import__(
    "kidneymatch.ocr.templates", fromlist=["LayoutPrototype"]
).LayoutPrototype

# The dominant form: eight labels stacked in one column at a fixed pitch.
ROW_ORDER = ("A", "B", "C", "DQB1", "DRB1", "DPB1", "DPA1", "DQA1")
PITCH = 0.06


def stack(lean: float = 0.0, dropped: str | None = None, dx: float = 0.0) -> list[Box]:
    boxes = []
    for index, locus in enumerate(ROW_ORDER):
        x = 0.15 + lean * index + (dx if locus == dropped else 0.0)
        y = 0.20 + index * PITCH
        boxes.append(Box(x0=x, y0=y, x1=x + 0.10, y1=y + 0.025, text=f"HLA-{locus}"))
    return boxes


def prototype(name: str, lean: float) -> LayoutPrototype:
    return LayoutPrototype.from_positions(
        name,
        {
            locus: (0.20 + lean * index, 0.2125 + index * PITCH)
            for index, locus in enumerate(ROW_ORDER)
        },
    )


TWINS = [prototype("FORM#0", 0.0), prototype("FORM#1", 0.002)]
PREFIXED = {"FORM#0", "FORM#1"}
RULE_OF = {"FORM#0": "family", "FORM#1": "family"}


def value(x0: float, y: float, text: str) -> Box:
    return Box(x0=x0, y0=y, x1=x0 + 0.10, y1=y + 0.025, text=text)


def document(boxes: list[Box], sha: str = "a" * 64) -> OcrDocument:
    return OcrDocument(
        sha256=sha,
        rel_path="photos/synthetic.jpg",
        boxes=boxes,
        confidences=[0.9] * len(boxes),
        width=1000,
        height=1300,
        engine_version="test-engine",
        preproc_version="test-preproc",
        error=None,
    )


def facts(
    boxes: list[Box],
    persian: list[Box] | None = None,
    prototypes: list[LayoutPrototype] | None = None,
    **kwargs,
) -> tuple[dict[str, tuple], dict]:
    rows, summary = extract_facts.extract(
        document(boxes),
        persian or [],
        load_vocabulary(),
        "2026-09-06T00:00:00+00:00",
        TWINS if prototypes is None else prototypes,
        PREFIXED,
        **kwargs,
    )
    # field -> (status, value, reason, rule_id)
    return {row[1]: (row[3], row[4], row[8], row[9]) for row in rows}, summary


# --- the tie ---------------------------------------------------------------


def test_a_page_between_two_leans_of_one_form_is_assigned_to_it() -> None:
    page = [
        *stack(lean=0.001),
        value(0.40, 0.20, "A*01"),
        value(0.60, 0.20, "A*02"),
    ]
    cells, summary = facts(page)
    assert summary["family"] in ("FORM#0", "FORM#1")
    assert cells["A"][0] == "RESOLVED"
    assert cells["A"][1] == "A*01 A*02"
    assert cells["A"][3].startswith("family/")
    assert "(tie:" in cells["A"][3], "the tie must be visible in provenance"


def test_a_tie_page_whose_values_name_no_locus_goes_back_to_the_default_rule() -> None:
    """Measured on 18 pages: the family rule refuses every bare value, the
    default rule reads them, and the page was already being read that way
    before the tie clause assigned it a family."""
    page = [
        *stack(lean=0.001),
        value(0.40, 0.20, "01"),
        value(0.60, 0.20, "02"),
    ]
    cells, summary = facts(page)
    assert summary["family"] in ("FORM#0", "FORM#1"), "the page is still that form"
    assert cells["A"][3] == "ADR0008/default-row-rule"
    assert cells["A"][0] == "RESOLVED"
    assert cells["A"][1] == "01 02"


# --- the left-out fit ------------------------------------------------------


def test_a_stack_that_fits_except_at_one_label_is_read_under_the_family_rule() -> None:
    page = [
        *stack(dropped="DPB1", dx=0.055),
        value(0.40, 0.20, "A*01"),
        value(0.60, 0.20, "A*02"),
    ]
    cells, summary = facts(page, prototypes=[prototype("FORM#0", 0.0)])
    assert summary["family"] == "FORM#0"
    assert cells["A"][3] == "family/FORM#0(loo:DPB1)", cells["A"]
    assert cells["A"][0] == "RESOLVED"


def test_a_left_out_page_never_places_a_virtual_label() -> None:
    """The page's own full fit is what failed, so the template's placement of
    an unreadable label is not evidence on this page. `bind_in_lattice` keeps
    its own full-fit check and places nothing."""
    page = [
        *stack(dropped="DPB1", dx=0.055),
        value(0.40, 0.20, "A*01"),
        value(0.60, 0.20, "A*02"),
    ]
    page = [b for b in page if b.text != "HLA-DRB1"]  # the label glyphs unreadable
    lattice = extract_facts.Lattice.from_segments(
        [[0, 572, 1000, 572], [0, 650, 1000, 650]], [], 1000, 1300
    )
    cells, summary = facts(page, prototypes=[prototype("FORM#0", 0.0)], lattice=lattice)
    assert summary["family"] == "FORM#0"
    assert cells["DRB1"][0] == "UNKNOWN"
    assert "+lattice" not in (cells["DRB1"][3] or "")


# --- the column form -------------------------------------------------------

HEADERS = ("A", "B", "C")


def column_page(texts: tuple[str, str, str] = ("A*01,*02", "B*07,*08", "C*01,*02")) -> list[Box]:
    """Three locus labels side by side on one printed line, values beneath."""
    boxes = []
    for index, locus in enumerate(HEADERS):
        x = 0.15 + index * 0.25
        boxes.append(Box(x0=x, y0=0.20, x1=x + 0.12, y1=0.225, text=f"HLA-{locus}"))
        boxes.append(Box(x0=x, y0=0.28, x1=x + 0.12, y1=0.305, text=texts[index]))
    return boxes


def test_a_form_whose_labels_are_column_headers_is_read_downwards() -> None:
    cells, _ = facts(column_page())
    for locus, expected in (("A", "A*01 A*02"), ("B", "B*07 B*08"), ("C", "C*01 C*02")):
        status, read, reason, rule_id = cells[locus]
        assert status == "RESOLVED", (locus, reason)
        assert read == expected
        assert rule_id == "ADR0008/below-rule"
        assert reason.startswith(extract_facts.COLUMN_REASON)


def test_a_column_page_carrying_both_role_words_keeps_the_row_rule() -> None:
    """A header row over two subject rows is exactly what a column layout
    looks like. Measured cost of refusing them: 13 cells on 10 pages."""
    persian = [
        Box(0.05, 0.05, 0.20, 0.075, "اهدا کننده"),
        Box(0.05, 0.10, 0.20, 0.125, "گیرنده"),
    ]
    cells, _ = facts(column_page(), persian=persian)
    assert cells["A"][3] == "ADR0008/default-row-rule"
    assert cells["A"][0] != "RESOLVED"


def test_a_page_with_a_family_never_takes_the_column_rule() -> None:
    """The column rule is for pages no form was recognised on."""
    page = [
        *stack(lean=0.001),
        value(0.40, 0.20, "A*01"),
        value(0.60, 0.20, "A*02"),
    ]
    cells, summary = facts(page)
    assert summary["family"] is not None
    assert "below" not in (cells["A"][3] or "")
