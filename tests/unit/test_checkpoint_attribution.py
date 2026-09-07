"""The checkpoint a wrong cell is charged to, and the order the checkpoints are tried.

An upstream failure (a sideways page) is charged before any cell-level reason,
a partial value is a rectangle that stopped short, and a reason the rules do
not know is reported as such rather than guessed.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from kidneymatch.review.golden import Outcome

ROOT = Path(__file__).resolve().parents[2]


def load():
    spec = importlib.util.spec_from_file_location(
        "checkpoint_attribution", ROOT / "scripts" / "checkpoint_attribution.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_a_sideways_page_is_charged_before_any_cell_reason() -> None:
    m = load()
    page = {"orientation": "ORIENTATION_SUSPECT"}
    assert (
        m.checkpoint_for(Outcome.MISSED, "UNKNOWN", "no anchor on this document", "A", 2, 0, page)
        == "1 orientation"
    )


def test_an_unlevelled_tilt_is_charged_before_the_cell() -> None:
    m = load()
    page = {"tilt_unlevelled": True}
    assert (
        m.checkpoint_for(
            Outcome.MISSED, "REVIEW_REQUIRED", "anchor found but no box", "B", 2, 0, page
        )
        == "2 tilt"
    )


def test_reasons_map_to_their_checkpoint() -> None:
    m = load()
    cases = {
        "no anchor on this document": "3 layout: label not found",
        "no grouped DRB3/4/5 header on this document": "3 layout: DRB3/4/5 header not read",
        "anchor found but no box at all in its cell": "4 cell: empty (value not detected)",
        "4 candidate values exceeds max_values=2": "4 cell: too wide / wrong owner",
        "candidate is closer to the DQB1 label; another locus owns it": (
            "4 cell: too wide / wrong owner"
        ),
        "values printed under one header of a comparison table": (
            "4 cell: two subjects on the page"
        ),
        "candidate 'x' does not parse as an allele value": "5 recognition",
        "'93' is not an allele family of DRB1 in IMGT 3.62": "5 recognition",
        "withdrawn to review: this value needed a glyph repair": "7 gate withdrew a value",
        "withdrawn to review: a DRB3/4/5 call from a second-opinion source": (
            "6 DRB3/4/5 row grammar"
        ),
        "only one gene token read; the second column is unread": "6 DRB3/4/5 row grammar",
    }
    for reason, expected in cases.items():
        assert (
            m.checkpoint_for(Outcome.MISSED, "REVIEW_REQUIRED", reason, "A", 2, 0, {}) == expected
        ), reason


def test_a_partial_is_a_rectangle_that_stopped_short() -> None:
    m = load()
    assert (
        m.checkpoint_for(Outcome.PARTIAL, "RESOLVED", "", "DRB1", 2, 1, {})
        == "4 cell: too short (one allele of two)"
    )


def test_not_tested_is_policy_and_unknown_reasons_are_not_guessed() -> None:
    m = load()
    assert (
        m.checkpoint_for(Outcome.MISSED, "NOT_TESTED", "anything", "C", 2, 0, {})
        == "8 policy (NOT_TESTED)"
    )
    assert (
        m.checkpoint_for(
            Outcome.MISSED, "REVIEW_REQUIRED", "a reason nobody wrote a rule for", "A", 2, 0, {}
        )
        == "? unclassified"
    )
    # ... except that a DRB3/4/5 gene left UNKNOWN is, by construction, the row.
    assert (
        m.checkpoint_for(Outcome.MISSED, "UNKNOWN", "", "DRB4", 0, 0, {})
        == "6 DRB3/4/5 row grammar"
    )


def test_a_false_acceptance_is_charged_where_the_page_analysis_put_it() -> None:
    m = load()
    page = {"false_acceptance_kind": "4 cell: too wide / wrong owner"}
    assert (
        m.checkpoint_for(Outcome.FALSE_ACCEPTANCE, "RESOLVED", "", "A", 2, 2, page)
        == "4 cell: too wide / wrong owner"
    )
    assert (
        m.checkpoint_for(Outcome.FALSE_ACCEPTANCE, "RESOLVED", "", "A", 2, 2, {}) == "5 recognition"
    )


def test_boxes_are_read_in_every_shape_a_pass_stored() -> None:
    m = load()
    assert m.parse_boxes("[[1, 2, 3, 4], [5, 6, 7, 8]]") == [
        (1.0, 2.0, 3.0, 4.0),
        (5.0, 6.0, 7.0, 8.0),
    ]
    assert m.parse_boxes("[1, 2, 3, 4]") == [(1.0, 2.0, 3.0, 4.0)]
    assert m.parse_boxes('{"x0": 1, "y0": 2, "x1": 3, "y1": 4}') == [(1.0, 2.0, 3.0, 4.0)]
    assert m.parse_boxes("not json") == []
    assert m.parse_boxes(None) == []


def test_only_a_page_that_was_levelled_can_be_charged_to_tilt() -> None:
    """W1 stores a residual for EVERY page: re-measured after levelling on the
    1,591 it levels, and the page's own angle on the 21,975 it does not. Reading
    the second as a levelling failure charged 32 labelled failures to tilt that
    belong to their own checkpoint — 4,920 pages carry 0.5-1.5 deg by design."""
    m = load()
    levelled_and_tilted = {
        "residual_slope_deg": 0.9,
        "residual_source": "remeasured-after-levelling",
        "tilt_unlevelled": True,
    }
    assert (
        m.checkpoint_for(
            Outcome.MISSED, "UNKNOWN", "no anchor on this document", "A", 2, 0, levelled_and_tilted
        )
        == "2 tilt"
    )
    never_levelled = {
        "residual_slope_deg": 0.9,
        "residual_source": "measured-not-levelled",
        "tilt_unlevelled": False,
    }
    assert (
        m.checkpoint_for(
            Outcome.MISSED, "UNKNOWN", "no anchor on this document", "A", 2, 0, never_levelled
        )
        == "3 layout: label not found"
    ), "a page the pipeline never levelled is not a levelling failure"
