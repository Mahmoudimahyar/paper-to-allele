"""The DRB3/4/5 row on a page whose grouped header was never read.

Written before the implementation, from the measured proposal and the verifier's
required fixes (workflow `design-drbx-gene-token-row`, 2026-09-06).

`resolve_grouped_drbx` needs the printed enumeration `{DRB3, DRB4, DRB5}` to
license reading a gene name from the row. On 9,207 documents the recognizer
produced no box that pattern reaches, and those documents hold all three genes
UNKNOWN. The shipped gates accept 479 of them, writing 621 PRESENT cells
(measured 2026-09-07 against the live stores; the 578/579 this docstring used to
quote came from a permissive reading of G3/G4/G9 and no build ever shipped it).
On 476 of those 479 accepted rows a box DOES stand in the label column of the
placed row — 394 carrying the header's `DR` stem in a spelling no header pattern
reads, and 6 more spelling an enumeration the damage-tolerant pattern does read
but standing where the geometry gate will not call it a header. The row is
therefore placed by geometry exactly as the header route places it; what is
missing is the reading of the header, not the header.

The route emits **PRESENT only**. Nothing here ever says a gene is absent: the
counting argument that licenses ABSENT rests on the enumeration having been
read, and it has not been.

Every test below is a way this rule could assert something untrue. The five
placebos are the ones the verifier constructed and measured on the corpus.
"""

from __future__ import annotations

import pytest

from kidneymatch.ocr.anchors import Box, ResolutionStatus
from kidneymatch.ocr.drbx import (
    GENES,
    TOKEN_ANCHORED_RULE_ID,
    GeneCall,
    resolve_token_anchored_drbx,
)

# One label height, and the column the form stacks its labels in.
H = 0.012
LABEL_X0, LABEL_X1 = 0.10, 0.19
# The dominant no-header form prints DQB1 one row ABOVE DRB1; the pitch between
# them is the row pitch, and the grouped row is one pitch BELOW DRB1.
PITCH = 0.040  # 3.33 label heights, the measured median (3.68h)
DQB1_Y, DRB1_Y = 0.400, 0.440
ROW_Y = DRB1_Y + PITCH
# G6: a value column starts at least 4 label heights right of the label's edge.
# True tokens sit 6.09h out at the first percentile.
VALUE_X = 0.40
SECOND_X = 0.70


def label(text: str, centre_y: float, x0: float = LABEL_X0, x1: float = LABEL_X1) -> Box:
    return Box(x0=x0, y0=centre_y - H / 2, x1=x1, y1=centre_y + H / 2, text=text)


def token(text: str, x0: float = VALUE_X, centre_y: float = ROW_Y, width: float = 0.06) -> Box:
    return Box(x0=x0, y0=centre_y - H / 2, x1=x0 + width, y1=centre_y + H / 2, text=text)


def page(*extra: Box, drb1: str = "DRB1", dqb1_y: float = DQB1_Y) -> list[Box]:
    """A no-header page: the label column, its pitch, and whatever is added."""
    return [label("DQB1", dqb1_y), label(drb1, DRB1_Y), *extra]


def read(boxes: list[Box], **kwargs):
    kwargs.setdefault("drb1_resolved", True)
    return resolve_token_anchored_drbx(boxes, **kwargs)


def present(boxes: list[Box], **kwargs) -> set[str]:
    row = read(boxes, **kwargs)
    if row.facts is None:
        return set()
    return {gene for gene, fact in row.facts.items() if fact.call is GeneCall.PRESENT}


# --- the row is placed, and only the row -----------------------------------


def test_two_gene_tokens_one_pitch_below_DRB1_are_read_as_present() -> None:
    row = read(page(token("DRB3"), token("DRB4", x0=SECOND_X)))
    assert row.facts is not None, row.reason
    assert row.facts["DRB3"].call is GeneCall.PRESENT
    assert row.facts["DRB4"].call is GeneCall.PRESENT
    assert row.facts["DRB3"].status is ResolutionStatus.RESOLVED
    assert row.facts["DRB3"].rule_id == TOKEN_ANCHORED_RULE_ID


def test_two_tokens_leave_the_third_gene_UNKNOWN_and_never_ABSENT() -> None:
    """The counting rule that licenses ABSENT needs the enumeration printed.

    On this route it was not read, so two tokens account for nothing: the third
    gene is the absence of a finding, which is UNKNOWN.
    """
    row = read(page(token("DRB3"), token("DRB4", x0=SECOND_X)))
    assert row.facts is not None
    assert row.facts["DRB5"].call is GeneCall.UNKNOWN
    assert row.facts["DRB5"].status is ResolutionStatus.UNKNOWN
    assert all(fact.call is not GeneCall.ABSENT for fact in row.facts.values())


def test_one_token_names_its_gene_and_says_nothing_about_the_others() -> None:
    row = read(page(token("DRB5")))
    assert row.facts is not None
    assert row.facts["DRB5"].call is GeneCall.PRESENT
    for gene in ("DRB3", "DRB4"):
        assert row.facts[gene].call is GeneCall.UNKNOWN
        assert row.facts[gene].status is ResolutionStatus.UNKNOWN


def test_a_pair_printed_in_one_box_names_both_genes() -> None:
    assert present(page(token("DRB3/5"))) == {"DRB3", "DRB5"}


# --- provenance -------------------------------------------------------------


def test_a_present_gene_carries_the_DRB1_label_and_its_own_box() -> None:
    gene_box = token("DRB4")
    row = read(page(gene_box))
    assert row.facts is not None
    fact = row.facts["DRB4"]
    assert fact.header_box is not None
    assert (fact.header_box.x0, fact.header_box.x1) == (LABEL_X0, LABEL_X1)
    assert fact.gene_box is gene_box
    assert fact.gene_boxes == (gene_box,)
    assert fact.raw_text == "DRB4"
    assert fact.repaired is False


def test_the_unknown_genes_carry_no_anchor_box_so_no_crop_is_cut_for_them() -> None:
    """`review_pack.cell_crop_box` crops "the row right of the anchor" when a
    cell has an anchor and no value box. With the DRB1 label there, a reviewer
    labelling DRB5 would be shown the DRB1 row — label noise on exactly the
    cells the golden set needs (verifier fix 4)."""
    row = read(page(token("DRB3")))
    assert row.facts is not None
    assert row.facts["DRB3"].header_box is not None
    for gene in ("DRB4", "DRB5"):
        assert row.facts[gene].header_box is None
        assert row.facts[gene].gene_boxes == ()


def test_a_gene_printed_twice_keeps_both_boxes() -> None:
    row = read(page(token("DRB3"), token("DRB3", x0=SECOND_X)))
    assert row.facts is not None
    assert len(row.facts["DRB3"].gene_boxes) == 2


# --- the placebos: the row must move when the ink moves ---------------------


@pytest.mark.parametrize("steps", [-2, -1, 1, 2])
def test_translating_the_tokens_by_whole_row_pitches_accepts_nothing(steps: int) -> None:
    """Measured: 0 of 568 accepted pages survive this on the corpus."""
    moved = ROW_Y + steps * PITCH
    assert (
        present(page(token("DRB3", centre_y=moved), token("DRB4", x0=SECOND_X, centre_y=moved)))
        == set()
    )


def test_remapping_the_gene_digits_moves_the_emitted_set_with_them() -> None:
    """The rule reads the token, as ADR 0008 Decision 4 licenses it to. This
    placebo must FOLLOW, and a placebo that did not would mean the genes were
    coming from somewhere other than the printed name."""
    assert present(page(token("DRB3"), token("DRB4", x0=SECOND_X))) == {"DRB3", "DRB4"}
    assert present(page(token("DRB4"), token("DRB5", x0=SECOND_X))) == {"DRB4", "DRB5"}
    assert present(page(token("DRB5"), token("DRB3", x0=SECOND_X))) == {"DRB5", "DRB3"}


def test_a_lone_gene_token_on_the_DRB1_row_itself_is_refused() -> None:
    assert read(page(token("DRB3", centre_y=DRB1_Y))).facts is None


def test_an_HLA_DRB3_fragment_in_the_label_column_refuses_the_page() -> None:
    """G9 beats G6. A box on the row that `canonical_locus_label` NAMES is a
    form that types these genes as standalone rows, and this rule has no
    licence there — not a header fragment to be skipped past (verifier fix 2)."""
    assert read(page(label("HLA-DRB3", ROW_Y), token("DRB4"))).facts is None
    assert read(page(label("DRB3", ROW_Y), token("DRB4"))).facts is None


def test_a_comparison_sheet_is_refused_whatever_its_row_says() -> None:
    sheet = page(
        token("DRB3"),
        Box(x0=0.30, y0=0.10, x1=0.38, y1=0.10 + H, text="Donor"),
        Box(x0=0.55, y0=0.10, x1=0.66, y1=0.10 + H, text="Recipient"),
    )
    assert read(sheet).facts is None


# --- G6: the header fragment that would have written a wrong DRB5 -----------


def test_a_gene_token_in_the_label_column_is_never_present() -> None:
    """The split header: `HLA-DRB3,` | `DRB4,` | `DRB5`, the last fragment
    starting 3.1 label heights right of the DRB1 label. At the proposal's 1.0h
    gate that wrote DRB5 PRESENT on 316 pages, 145 of them rows that printed no
    gene at all. At 4.0h: none (verifier fix 1)."""
    close = LABEL_X1 + 3.0 * H
    assert present(page(token("DRB5,", x0=close, width=0.04))) == set()


def test_a_fragment_the_label_matcher_does_not_name_is_skipped_not_refused() -> None:
    """`DRB3,` is not a locus label; it is excluded from the count while a real
    token in the value column is still read."""
    close = LABEL_X1 + 2.0 * H
    assert present(page(token("DRB3,", x0=close, width=0.04), token("DRB4"))) == {"DRB4"}


def test_the_column_gate_is_measured_in_DRB1_label_heights() -> None:
    from kidneymatch.ocr.drbx import TOKEN_COLUMN_GAP_HEIGHTS

    assert TOKEN_COLUMN_GAP_HEIGHTS == 4.0
    just_inside = LABEL_X1 + 3.9 * H
    just_outside = LABEL_X1 + 4.1 * H
    assert present(page(token("DRB4", x0=just_inside, width=0.04))) == set()
    assert present(page(token("DRB4", x0=just_outside, width=0.04))) == {"DRB4"}


# --- G4: the pitch, and the forms whose row order is not this one -----------


def test_a_DQB1_label_one_pitch_BELOW_DRB1_refuses_the_page() -> None:
    """Another form's row order. The proposal fell back to half the DRB1->DPB1
    gap here, which admitted 26 pages of a layout nobody measured (fix 3)."""
    boxes = [label("DQB1", DRB1_Y + PITCH), label("DRB1", DRB1_Y), token("DRB3")]
    assert read(boxes).facts is None


def test_an_insane_DQB1_pitch_does_not_fall_back_to_DPB1() -> None:
    boxes = [
        label("DQB1", DRB1_Y - 0.9 * H),  # under 1.5 label heights: not a row apart
        label("DPB1", DRB1_Y - 2 * PITCH),
        label("DRB1", DRB1_Y),
        token("DRB3"),
    ]
    assert read(boxes).facts is None


def test_DPB1_supplies_the_pitch_only_when_no_DQB1_label_is_read() -> None:
    boxes = [
        label("DPB1", DRB1_Y - 2 * PITCH),  # two rows above: half the gap is one
        label("DRB1", DRB1_Y),
        token("DRB3"),
    ]
    assert present(boxes) == {"DRB3"}


@pytest.mark.parametrize("ratio", [0.5, 0.55, 1.35, 1.5])
def test_a_token_outside_the_row_window_refuses_the_page(ratio: float) -> None:
    """G7: a gene token that is not on the placed row is another form's row,
    and the page is refused rather than the token ignored."""
    assert read(page(token("DRB3", centre_y=DRB1_Y + ratio * PITCH))).facts is None


def test_one_token_on_the_row_and_one_off_it_refuses_the_page() -> None:
    off = DRB1_Y + 0.5 * PITCH
    assert read(page(token("DRB3"), token("DRB4", x0=SECOND_X, centre_y=off))).facts is None


# --- G2, G3, G1: what must be true of the page before the row is placed -----


def test_a_page_whose_DRB1_was_not_resolved_is_refused() -> None:
    """The DRB1-REVIEW stratum is held back: 116 pages have a DRB1 VALUE box
    inside this window, and every one of them is a DRB1 the resolver refused."""
    assert read(page(token("DRB3")), drb1_resolved=False).facts is None


def test_two_DRB1_labels_leave_the_row_undecided() -> None:
    boxes = [*page(token("DRB3")), label("DRB1", 0.70)]
    assert read(boxes).facts is None


def test_no_DRB1_label_places_no_row() -> None:
    boxes = [label("DQB1", DQB1_Y), token("DRB3")]
    assert read(boxes).facts is None


def test_a_column_header_form_is_refused() -> None:
    """G3: another locus label on DRB1's own printed line means the labels are
    column headings, and "one pitch below DRB1" is not a row of that table."""
    boxes = [*page(token("DRB3")), label("DQA1", DRB1_Y, x0=0.30, x1=0.39)]
    assert read(boxes).facts is None


def test_a_page_with_a_grouped_header_is_left_to_the_header_route() -> None:
    """G1: the header route gets first refusal, always."""
    boxes = [*page(token("DRB3")), label("HLA-DRB3/4/5", ROW_Y)]
    assert read(boxes).facts is None


# --- G10, G11: what a token may say ----------------------------------------


@pytest.mark.parametrize("text", ["DRBS", "DRBS/S", "DRB3/S"])
def test_an_S_anywhere_refuses_the_page(text: str) -> None:
    """No S-for-5 repair on this route. The header's own digits are what made
    that repair measurable, and they were not read here."""
    assert read(page(token(text))).facts is None


def test_three_symbols_on_one_row_refuse_the_page() -> None:
    third = SECOND_X + 0.15
    boxes = page(token("DRB3"), token("DRB4", x0=SECOND_X), token("DRB5", x0=third))
    assert read(boxes).facts is None


@pytest.mark.parametrize("text", ["DRR3", "DRE3", "DR3", "DR83"])
def test_only_the_strict_DR_B8_stem_names_a_gene(text: str) -> None:
    """The damage-tolerant stem belongs to the header, which is a printed
    enumeration; a VALUE that needed that much repair names nothing. `DR83` is
    the one accepted alternative spelling of the stem."""
    row = read(page(token(text)))
    named = (
        set()
        if row.facts is None
        else {gene for gene, fact in row.facts.items() if fact.call is GeneCall.PRESENT}
    )
    assert named == ({"DRB3"} if text == "DR83" else set())


def test_an_allele_of_one_of_these_genes_names_it() -> None:
    assert present(page(token("DRB4*01:01"))) == {"DRB4"}


# --- G8: the accepted tokens are one printed line ---------------------------


def test_two_tokens_that_do_not_share_a_line_refuse_the_page() -> None:
    boxes = page(token("DRB3"), token("DRB4", x0=SECOND_X, centre_y=ROW_Y + 0.9 * H))
    assert read(boxes).facts is None


def test_the_row_is_followed_along_the_pages_own_slope() -> None:
    """A tilted page prints its row falling; the token half a page right sits
    below its label by the fall, not off the row (`ocr/rows.py`)."""
    slope = 0.03
    drifted = ROW_Y + slope * (SECOND_X + 0.03 - (LABEL_X0 + LABEL_X1) / 2)
    boxes = page(token("DRB4", x0=SECOND_X, centre_y=drifted))
    assert present(boxes) == set()
    assert present(boxes, row_slope=slope) == {"DRB4"}


# --- the outcome carries a reason a tally can group by ----------------------


def test_every_refusal_states_why() -> None:
    row = read(page(token("DRB3", centre_y=DRB1_Y)))
    assert row.facts is None
    assert row.reason


def test_the_genes_are_all_three_and_in_order() -> None:
    row = read(page(token("DRB3")))
    assert row.facts is not None
    assert tuple(row.facts) == GENES


# --- G5: what the printed rulings say about the two rows --------------------

PX = 1000  # the synthetic page, in pixels, for `Lattice.from_segments`


def ruled(*ys: float):
    """A lattice whose horizontal rulings run across the page at these y."""
    from kidneymatch.ocr.lattice import Lattice

    return Lattice.from_segments(
        [[0.05 * PX, y * PX, 0.95 * PX, y * PX] for y in ys],
        [[0.05 * PX, 0.30 * PX, 0.05 * PX, 0.90 * PX]],
        PX,
        PX,
    )


# The DRB1 label's row and the grouped row below it, sharing one ruling.
ADJACENT = (0.395, 0.425, 0.455, 0.485)


def test_the_lattice_does_not_veto_a_row_that_shares_a_ruling_with_DRB1() -> None:
    assert present(page(token("DRB3")), lattice=ruled(*ADJACENT)) == {"DRB3"}


def test_a_token_inside_the_DRB1_labels_own_ruled_band_is_refused() -> None:
    """The pitch can be right and the row still wrong: a short pitch puts the
    window over the DRB1 row itself, and the page's own rulings say so."""
    pitch = 1.6 * H
    boxes = [
        label("DQB1", DRB1_Y - pitch),
        label("DRB1", DRB1_Y),
        token("DRB3", centre_y=DRB1_Y + 0.7 * pitch),
    ]
    assert present(boxes) == {"DRB3"}  # geometry alone accepts it
    assert read(boxes, lattice=ruled(*ADJACENT)).facts is None


def test_a_ruled_band_between_the_two_rows_refuses_the_page() -> None:
    """Two label pitches of ruled table between the DRB1 row and the token's
    row means the token is not on the row below the label, whatever the
    arithmetic says."""
    pitch = 0.060
    boxes = [
        label("DQB1", DRB1_Y - pitch),
        label("DRB1", DRB1_Y),
        token("DRB3", centre_y=DRB1_Y + pitch),
    ]
    assert present(boxes) == {"DRB3"}
    assert read(boxes, lattice=ruled(0.425, 0.455, 0.487, 0.515)).facts is None


def test_with_no_pitch_at_all_only_a_shared_ruling_places_the_row() -> None:
    """11 pages print neither a DQB1 nor a DPB1 label the matcher reads. There
    the rulings alone place the row, and they must be adjacent."""
    lonely = [label("DRB1", DRB1_Y), token("DRB3")]
    assert read(lonely).facts is None  # no pitch, no lattice: nothing to place
    assert present(lonely, lattice=ruled(*ADJACENT)) == {"DRB3"}
    apart = ruled(0.395, 0.425, 0.455, 0.470, 0.500)
    assert read(lonely, lattice=apart).facts is None


# --- the frame the row rules ran in -----------------------------------------


def test_a_ROTATE_frame_restores_provenance_to_the_boxes_as_stored() -> None:
    """84 accepted pages are ROTATE frames. The rule runs on the levelled page
    and the fact must name the boxes the reviewer's crop is cut from."""
    from kidneymatch.ocr.geometry import PageFrame, restore_drbx, unrectify_box

    frame = PageFrame(theta_deg=2.5, width=PX, height=PX)
    # The page as the camera stored it: the level form, turned.
    stored = [unrectify_box(frame, box) for box in page(token("DRB3"), token("DRB4", x0=SECOND_X))]
    levelled, back = frame.rectify(stored)
    row = read(levelled)
    assert row.facts is not None
    restored = {gene: restore_drbx(fact, back) for gene, fact in row.facts.items()}
    assert restored["DRB3"].gene_box is stored[2]
    assert restored["DRB3"].gene_boxes == (stored[2],)
    assert restored["DRB3"].header_box is stored[1]  # the DRB1 label as stored
    assert restored["DRB5"].header_box is None


# --- the group's provenance comes from the RULE, not from a one-off pass -----


def test_the_present_facts_carry_the_pass_source_from_the_rule_itself() -> None:
    """`scripts/drbx_token_repass.py` writes `source='token-anchored-drbx'`, and
    `review_pack.py` used to build this route's stratum from that string alone.
    A full re-extraction writes the same facts through `extract_facts.py`, which
    never set the source — so the cells kept their `rule_id`, lost the `source`,
    and the stratum silently drew zero. That is the failure `review_pack.py`'s
    own header warns about, and the store holds a dozen `facts.before-*` backups
    to show how often a re-extraction happens.

    The rule now emits it, so both paths agree. Only the PRESENT facts carry it,
    exactly as the pass writes it: the UNKNOWN genes are cells this route
    declined to claim, and marking them would claim them."""
    from kidneymatch.ocr.drbx import TOKEN_ANCHORED_SOURCE

    row = read(page(token("DRB3")))
    assert row.facts is not None
    assert row.facts["DRB3"].source == TOKEN_ANCHORED_SOURCE
    assert row.facts["DRB3"].rule_id == TOKEN_ANCHORED_RULE_ID
    assert row.facts["DRB4"].source is None
    assert row.facts["DRB5"].source is None
    assert {f.rule_id for f in row.facts.values()} == {TOKEN_ANCHORED_RULE_ID}
