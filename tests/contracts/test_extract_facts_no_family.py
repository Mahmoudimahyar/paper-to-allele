"""The extraction's three answers for a page with no layout family.

Written before the code. 11,210 of 23,566 documents carry no family, and the
review of that population found three separate reasons and one measured fix
each:

* **A tie between prototypes that are one form under lean** — 987 pages fit
  inside `MAX_RESIDUAL` and were refused only because a second prototype fitted
  nearly as well. Assigning the best when the tied prototypes author one rule
  and print one row order gains 651 cells against the default rule.
* **A label whose `HLA-` prefix was boxed apart** — 162 pages, where the
  fragment is on the page and can be put back, after which the stack fits at
  the ordinary tolerance and the page is READ from the repaired boxes.
* **A page whose stack fits except at one label, with no fragment to explain
  it** — the residue, 209 pages. The left-out fit assigns them; the
  virtual-anchor path must NOT run there, because the page's own full fit is
  what failed.
* **A form whose locus labels are column headers** — 290 pages, where every
  value sits in the cell beneath its label. `ocr/layout.py` has been able to
  say so since the reviewer described one, and three add-on passes acted on it
  (`page_ocr_bind.py`, `rerecognise_pass.py`, `upright_bind.py`, which import
  the same rule object); the extraction did not.

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


# --- putting a boxed-apart `HLA-` prefix back ------------------------------


def split_prefix_page(locus: str) -> list[Box]:
    """The stack with one label's `HLA-` boxed apart, and a two-allele A row."""
    boxes = []
    for index, name in enumerate(ROW_ORDER):
        y = 0.20 + index * PITCH
        if name == locus:
            boxes.append(Box(x0=0.15, y0=y, x1=0.19, y1=y + 0.025, text="HLA-"))
            boxes.append(Box(x0=0.194, y0=y, x1=0.25, y1=y + 0.025, text=name))
        else:
            boxes.append(Box(x0=0.15, y0=y, x1=0.25, y1=y + 0.025, text=f"HLA-{name}"))
    return [*boxes, value(0.40, 0.20, "A*01"), value(0.60, 0.20, "A*24")]


def test_a_boxed_apart_prefix_is_put_back_and_the_page_reads_at_full_tolerance() -> None:
    cells, summary = facts(split_prefix_page("DPB1"), prototypes=[prototype("FORM#0", 0.0)])
    assert summary["family"] == "FORM#0"
    assert summary["dropped_label"] is None, "nothing was left out; the word was put back"
    assert cells["A"][3] == "family/FORM#0(prefix:DPB1)", cells["A"]
    assert cells["A"][0] == "RESOLVED"


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


def test_a_prefix_repaired_page_may_place_a_virtual_label() -> None:
    """The deliberate difference from the left-out fit.

    A left-out page places no virtual label because its own full fit is what
    failed. A prefix-repaired page's full fit SUCCEEDS — on the boxes the form
    actually printed — so the template's placement of an unreadable label is
    evidence there in the ordinary way. Measured on the corpus: 73 cells are
    gained down this path on the 162 repaired pages, and 0 on the left-out
    ones.
    """
    page = split_prefix_page("DPB1")
    page = [b for b in page if b.text != "HLA-DRB1"]  # the label glyphs unreadable
    page += [value(0.40, 0.44, "DRB1*04"), value(0.60, 0.44, "DRB1*11")]
    lattice = extract_facts.Lattice.from_segments(
        [[0, 560, 1000, 560], [0, 600, 1000, 600]], [], 1000, 1300
    )
    cells, summary = facts(page, prototypes=[prototype("FORM#0", 0.0)], lattice=lattice)
    assert summary["family"] == "FORM#0"
    assert "(prefix:DPB1)" in (cells["DRB1"][3] or ""), cells["DRB1"]
    assert cells["DRB1"][0] == "RESOLVED"
    assert "placed by the form's template" in (cells["DRB1"][2] or "")


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


# --- the wrong-locus safety case for the two template accommodations -------
#
# The accommodations exist to apply a FORM'S OWN cell rule to a page that
# nearly fits it, and the whole risk is that the rule then reads a value off
# the wrong row. The perturbation that tests it is to move a locus label to
# another row's y and ask what the page publishes: the answer must be a
# refusal, on a form that prints the locus on its values and on one whose
# values have had the prefix stripped. Never a resolution under either.


# One admissible allele family per locus, so the vocabulary gate is not what
# refuses these pages. Fabricated values on synthetic geometry.
FIELDS = {
    "A": ("01", "24"),
    "B": ("07", "35"),
    "C": ("01", "07"),
    "DQB1": ("02", "03"),
    "DRB1": ("04", "11"),
    "DPB1": ("02", "04"),
    "DPA1": ("01", "02"),
    "DQA1": ("01", "05"),
}


def moved_anchor(locus: str, rows: int, prefixed: bool) -> list[Box]:
    """The stack with one label lifted `rows` pitches out of its own row, and
    a two-allele value printed on every row."""
    boxes = []
    for index, name in enumerate(ROW_ORDER):
        y = 0.20 + index * PITCH
        label_y = y + (rows * PITCH if name == locus else 0.0)
        boxes.append(Box(x0=0.15, y0=label_y, x1=0.25, y1=label_y + 0.025, text=f"HLA-{name}"))
        first, second = FIELDS[name]
        head = f"{name}*" if prefixed else ""
        boxes.append(value(0.40, y, f"{head}{first}"))
        boxes.append(value(0.60, y, f"{head}{second}"))
    return boxes


def test_the_control_reads_every_row_when_no_label_is_moved() -> None:
    """The placebo half of the perturbation: with every label in its own row
    the page resolves, so a refusal below is the moved label and not the
    fixture."""
    cells, summary = facts(
        moved_anchor("DQB1", rows=0, prefixed=True), prototypes=[prototype("FORM#0", 0.0)]
    )
    assert summary["family"] == "FORM#0"
    for locus in ("A", "DQB1", "DRB1"):
        assert cells[locus][0] == "RESOLVED", (locus, cells[locus])


def test_a_prefix_stripped_page_publishes_nothing_under_the_family_rule() -> None:
    """The other half of the perturbation, and the reason the moved anchor is
    only dangerous on a form that prints the locus: strip the prefixes and the
    family rule refuses every cell, moved label or not."""
    cells, summary = facts(
        moved_anchor("DQB1", rows=0, prefixed=False), prototypes=[prototype("FORM#0", 0.0)]
    )
    assert summary["family"] == "FORM#0"
    assert not [locus for locus in ROW_ORDER if cells[locus][0] == "RESOLVED"]
    assert extract_facts.NAMES_NO_LOCUS in (cells["A"][2] or "")


@pytest.mark.parametrize("prefixed", [True, False])
@pytest.mark.parametrize("locus", ["DQB1", "B", "DPA1"])
def test_a_moved_anchor_never_resolves(locus: str, prefixed: bool) -> None:
    """Lift one locus label into the next row and ask what the page publishes.

    This is the whole wrong-locus safety case for the two accommodations: they
    exist to apply a FORM'S OWN cell rule to a page that nearly fits it, and
    the risk they carry is that the rule then reads a value off the wrong row.
    The answer must be a refusal for the moved locus and for the locus whose
    row it moved into — on a form that prints the locus on its values, and on
    one whose values have had the prefix stripped. Never a resolution.
    """
    below = ROW_ORDER[ROW_ORDER.index(locus) + 1]
    cells, _ = facts(
        moved_anchor(locus, rows=1, prefixed=prefixed), prototypes=[prototype("FORM#0", 0.0)]
    )
    assert cells[locus][0] != "RESOLVED", cells[locus]
    assert cells[below][0] != "RESOLVED", cells[below]


@pytest.mark.parametrize("prefixed", [True, False])
def test_a_moved_anchor_also_costs_the_page_its_family(prefixed: bool) -> None:
    """Two layers refuse it, and both are worth pinning: the template refuses
    the page (a label a whole pitch out of its row is a different row order,
    and the left-out fit's x-dominance test is what says so), and the binding
    gates refuse the cell even when the page is read under the default rule."""
    cells, summary = facts(
        moved_anchor("DQB1", rows=1, prefixed=prefixed), prototypes=[prototype("FORM#0", 0.0)]
    )
    assert summary["family"] is None
    assert cells["DQB1"][3] == "ADR0008/default-row-rule"
    assert "owns it" in (cells["DQB1"][2] or "")


# --- what the direction that decided 365 cells leaves behind ---------------


def test_the_layout_counts_are_recorded_for_every_page() -> None:
    """`ocr/layout.py` counts four things and the direction it decides settles
    which way a page is read. Without the counts stored there is no per-page
    record of WHY, and no way to see the population that nearly qualified."""
    _, column = facts(column_page())
    assert column["loci_sharing_a_row"] >= 3
    assert column["loci_sharing_a_column"] == 0
    assert column["values_under_the_label"] > column["values_along_the_row"]

    _, stacked = facts([*stack(lean=0.001), value(0.40, 0.20, "A*01")])
    assert stacked["loci_sharing_a_column"] > stacked["loci_sharing_a_row"]
    assert stacked["values_along_the_row"] >= 1


def test_the_dropped_label_is_recorded_on_the_document() -> None:
    """Which label the left-out fit dropped is a column, not something to be
    recovered by string-parsing the rule ids of the cells a page happened to
    gain."""
    page = [
        *stack(dropped="DPB1", dx=0.055),
        value(0.40, 0.20, "A*01"),
        value(0.60, 0.20, "A*02"),
    ]
    _, summary = facts(page, prototypes=[prototype("FORM#0", 0.0)])
    assert summary["dropped_label"] == "DPB1"
    _, plain = facts([*stack(lean=0.001), value(0.40, 0.20, "A*01")])
    assert plain["dropped_label"] is None


def test_the_document_table_carries_every_column_the_summary_writes() -> None:
    """A positional INSERT breaks the moment a column is added to one and not
    the other, and `connect` is what adds them to an existing database."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        con = extract_facts.connect(Path(tmp) / "facts.sqlite")
        columns = {row[1] for row in con.execute("PRAGMA table_info(document)")}
        con.close()
    for name in (
        "loci_sharing_a_row",
        "loci_sharing_a_column",
        "values_along_the_row",
        "values_under_the_label",
        "dropped_label",
    ):
        assert name in columns, name
