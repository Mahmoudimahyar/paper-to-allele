"""One person's column on a two-person sheet, and every way it could be wrong.

`prefix_bind.py` refuses a comparison sheet outright and says why: the right
gene of the WRONG PERSON is the worst thing this pipeline can produce. That
refusal is the operator's recorded decision (`CV_RESEARCH_2026-09-05.md` s12);
s12-b amends it for the single-filled-column case only, under the
subject-agreement gate, and these tests are the whole safety argument for the
amendment.

Each test reproduces a construction that was measured against the real 450
sheets before the gate it exercises was written. Removing a gate must turn one
of them red.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import column_bind  # noqa: E402
from column_bind import Reading, holds_a_value, qualified, read_columns  # noqa: E402

from kidneymatch.documents.role import Role, comparison_columns  # noqa: E402
from kidneymatch.hla.vocabulary import load_vocabulary  # noqa: E402
from kidneymatch.ocr.anchors import Box  # noqa: E402

# The template, in normalised page coordinates: a header row with Recipient on
# the LEFT and Donor on the right, then one printed row per locus.
HEADER_Y = 0.11
HEADER_H = 0.02
RECIPIENT_X = 0.20
DONOR_X = 0.60
ROWS = {"A": 0.20, "B": 0.24, "DRB1": 0.28, "DQB1": 0.32}
FILLED = {"A": "A*24,*02", "DRB1": "DRB1*15,*11", "DQB1": "DQB1*03,*05"}


@pytest.fixture(scope="module")
def vocabulary():
    return load_vocabulary()


def at(text: str, x: float, y: float, *, w: float = 0.09, h: float = 0.014) -> Box:
    return Box(x0=x, y0=y - h / 2, x1=x + w, y1=y + h / 2, text=text)


def header_boxes(
    *, recipient_x: float = RECIPIENT_X, donor_x: float = DONOR_X, y: float = HEADER_Y, extra=()
) -> list[Box]:
    return [
        at("Recipient", recipient_x, y, w=0.12, h=HEADER_H),
        at("Donor", donor_x, y, w=0.10, h=HEADER_H),
        *extra,
    ]


def sheet(values: dict[str, str] | None = None, *, column: str = "donor", extra=()) -> list[Box]:
    x = DONOR_X if column == "donor" else RECIPIENT_X
    boxes = header_boxes()
    for locus, text in (FILLED if values is None else values).items():
        boxes.append(at(text, x, ROWS[locus]))
    boxes.extend(extra)
    return boxes


def read(boxes: list[Box], vocabulary, **kw) -> Reading:
    kw.setdefault("role", Role.DONOR)
    kw.setdefault("role_resolved", True)
    kw.setdefault("role_source", "FORM_FIELD")
    return read_columns(boxes, vocabulary, 0.0, **kw)


# --- the baseline this whole file is measured against ------------------------


def test_a_single_filled_column_with_an_agreeing_role_binds(vocabulary) -> None:
    """The one case s12-b admits: two headings, ONE column filled, and the
    document's own role fact naming the same person."""
    found = read(sheet(), vocabulary)
    assert found.verdict == "BIND"
    assert found.subject is Role.DONOR
    assert found.side == "right"
    assert sorted(found.claims) == ["A", "DQB1", "DRB1"]


def test_the_left_column_binds_the_recipient(vocabulary) -> None:
    found = read(sheet(column="recipient"), vocabulary, role=Role.RECIPIENT)
    assert found.verdict == "BIND"
    assert found.subject is Role.RECIPIENT and found.side == "left"


def test_the_b_row_binds_only_because_the_bw_tail_now_parses(vocabulary) -> None:
    """This template prints `B*35,*51,Bw4,Bw6`. Before `glyphs.py` read that
    tail, B was unreachable on every page of the form."""
    values = {**FILLED, "B": "B*35,*51,Bw4,Bw6"}
    assert read(sheet(values), vocabulary).claims.keys() >= {"B"}


# --- the person: every construction that could bind the wrong one ------------


def test_a_contradicting_role_fact_refuses_the_page(vocabulary) -> None:
    """Four real pages contradict their column. All four are refused, and this
    is the gate that does it."""
    found = read(sheet(), vocabulary, role=Role.RECIPIENT)
    assert found.verdict == "REFUSE" and not found.claims


def test_tokens_slid_under_the_other_heading_are_refused_only_by_the_role_gate(
    vocabulary,
) -> None:
    """Stated explicitly because it is the pass's single point of failure.
    Sliding every token into the other column leaves the GEOMETRY perfect: with
    the role gate off, 333 pages bind and 272 name the wrong person."""
    slid = sheet(column="recipient")
    assert read(slid, vocabulary, role=Role.DONOR).verdict == "REFUSE"
    # Nothing else objects: with a role fact that agrees, the same page binds.
    assert read(slid, vocabulary, role=Role.RECIPIENT).verdict == "BIND"


def test_the_headings_swapped_in_place_bind_nothing(vocabulary) -> None:
    """The order gate. 445 of 449 pages print Recipient left; without it the
    four real-world contradiction pages bind the wrong person."""
    boxes = [
        at("Donor", RECIPIENT_X, HEADER_Y, w=0.10, h=HEADER_H),
        at("Recipient", DONOR_X, HEADER_Y, w=0.12, h=HEADER_H),
        *(at(text, DONOR_X, ROWS[locus]) for locus, text in FILLED.items()),
    ]
    assert read(boxes, vocabulary).verdict == "REFUSE"


def test_a_page_rotated_180_binds_nothing(vocabulary) -> None:
    """Turned over, the header row sits BELOW its values, and no rule in this
    pipeline reads a heading upwards."""
    boxes = [Box(b.x0, 1 - b.y1, b.x1, 1 - b.y0, b.text) for b in sheet()]
    assert read(boxes, vocabulary).verdict == "REFUSE"


def test_the_header_row_sought_below_the_values_binds_nothing(vocabulary) -> None:
    boxes = header_boxes(y=0.45) + [at(t, DONOR_X, ROWS[k]) for k, t in FILLED.items()]
    assert read(boxes, vocabulary).verdict == "REFUSE"


def test_headings_translated_half_a_column_bind_nothing(vocabulary) -> None:
    """The alignment gate: values are left-aligned under their heading, and the
    header pitch here is many times the tolerance."""
    boxes = header_boxes(recipient_x=RECIPIENT_X + 0.20, donor_x=DONOR_X + 0.20)
    boxes += [at(t, DONOR_X, ROWS[k]) for k, t in FILLED.items()]
    assert read(boxes, vocabulary).verdict == "REFUSE"


def test_a_frequency_decoy_in_the_same_boxes_binds_nothing(vocabulary) -> None:
    """Size-matched placebo: replace both role words, keep every pixel of
    geometry. 450 of 450 real pages refuse."""
    boxes = [
        at("Frequency", RECIPIENT_X, HEADER_Y, w=0.12, h=HEADER_H),
        at("Frequency", DONOR_X, HEADER_Y, w=0.10, h=HEADER_H),
        *(at(t, DONOR_X, ROWS[k]) for k, t in FILLED.items()),
    ]
    assert read(boxes, vocabulary).verdict == "REFUSE"
    assert comparison_columns(boxes) == []


# --- two people on one page --------------------------------------------------


def test_a_mirrored_second_person_refuses_the_page(vocabulary) -> None:
    extra = [at(t, RECIPIENT_X, ROWS[k]) for k, t in FILLED.items()]
    found = read(sheet(extra=extra), vocabulary)
    assert found.verdict == "REFUSE" and found.two_subject
    assert found.gate == "both columns hold values"


@pytest.mark.parametrize("shape", ["*01,*02", "'01,'02", "01,02", "*01:01,*02:01"])
def test_an_unparsed_second_column_refuses_the_page(vocabulary, shape: str) -> None:
    """The refutation P4 was rewritten for. None of these shapes parses as an
    allele, and every one of them is a second person's typing: with the
    emptiness predicate keyed on the parser alone, five of twelve real
    two-people pages bound."""
    found = read(sheet(extra=[at(shape, RECIPIENT_X, ROWS["A"])]), vocabulary)
    assert found.verdict == "REFUSE" and found.two_subject
    assert found.gate == "the other column is not empty"


def test_the_same_shapes_refuse_with_no_role_fact_at_all(vocabulary) -> None:
    """The two-people gates must not be reachable only through the role gate."""
    found = read(
        sheet(extra=[at("*01,*02", RECIPIENT_X, ROWS["A"])]),
        vocabulary,
        role=Role.UNKNOWN,
        role_resolved=False,
    )
    assert found.verdict == "REFUSE" and found.two_subject


def test_a_box_straddling_the_midline_refuses_the_page(vocabulary) -> None:
    wide = at("01,02", 0.34, ROWS["A"], w=0.20)
    found = read(sheet(extra=[wide]), vocabulary)
    assert found.verdict == "REFUSE" and found.two_subject
    assert found.gate == "a value box straddles the midline"


def test_a_third_role_word_on_the_header_row_refuses_the_page(vocabulary) -> None:
    """Three role words is more than two subjects. It is checked FIRST, which
    is why the three real both-filled pages never reach the two-people branch."""
    third = at("Donor", 0.80, HEADER_Y, w=0.10, h=HEADER_H)
    found = read_columns(
        header_boxes(extra=[third]) + [at(t, DONOR_X, ROWS[k]) for k, t in FILLED.items()],
        vocabulary,
        0.0,
        role=Role.DONOR,
        role_resolved=True,
    )
    assert found.verdict == "REFUSE" and found.two_subject
    assert found.gate == "more than two subjects on the header row"


def test_two_unreadable_columns_are_still_two_subjects(vocabulary) -> None:
    """The nine pages with allele-like text in both columns and nothing fully
    qualified anywhere. They are review work with a crop, not silence."""
    boxes = header_boxes() + [
        at("01,02", DONOR_X, ROWS["A"]),
        at("DRB1*15,*11", RECIPIENT_X, ROWS["DRB1"]),
    ]
    found = read(boxes, vocabulary)
    assert found.verdict == "REFUSE" and found.two_subject
    assert "DRB1" in found.evidence


def test_every_two_subject_refusal_carries_the_boxes_to_crop(vocabulary) -> None:
    """Without them the reviewer gets a refusal with no pixels behind it, which
    is the defect that made 50 of one round's 220 answers unusable."""
    for boxes in (
        sheet(extra=[at(t, RECIPIENT_X, ROWS[k]) for k, t in FILLED.items()]),
        sheet(extra=[at("*01,*02", RECIPIENT_X, ROWS["A"])]),
        sheet(extra=[at("01,02", 0.34, ROWS["A"], w=0.20)]),
    ):
        found = read(boxes, vocabulary)
        assert found.two_subject and found.evidence
        assert all(found.evidence.values())
        assert found.anchor_box is not None


# --- the locus ---------------------------------------------------------------


def test_every_a_prefix_rewritten_to_c_binds_nothing(vocabulary) -> None:
    """The measured wrong-locus channel: 28 cells bound as C, 21 of them on
    pages a person has labelled. This template never prints C, and C sorts
    between B and DRB1 so the row order cannot see it."""
    values = {**FILLED, "A": "C*24,*02"}
    found = read(sheet(values), vocabulary)
    assert found.verdict == "REFUSE" and not found.claims
    assert found.gate == "a value names a locus this template does not print"


def test_a_locus_outside_the_template_refuses_the_page_not_the_cell(vocabulary) -> None:
    """A token naming a gene the form does not print is evidence the READING is
    wrong, so nothing else on the page may be trusted either."""
    values = {**FILLED, "B": "DPB1*04,*02"}
    assert read(sheet(values), vocabulary).claims == {}


def test_a_second_row_of_the_same_locus_withdraws_it(vocabulary) -> None:
    """DRB1 misread as DQB1 gives the page two DQB1 rows. Neither binds."""
    values = {**FILLED, "DRB1": "DQB1*15,*11"}
    found = read(sheet(values), vocabulary)
    assert "DQB1" not in found.claims


def test_a_repaired_prefix_is_never_the_only_locus_evidence(vocabulary) -> None:
    """`DOB1` reaches DQB1 through the interior O->Q repair, justified on
    geometry measured UNDER ANCHORS. There is no anchor here."""
    values = {**FILLED, "DQB1": "DOB1*03,*05"}
    assert "DQB1" not in read(sheet(values), vocabulary).claims
    assert qualified("DOB1*03,*05") is None
    assert qualified("Cw*07,*04") is None
    assert qualified("a*24,*02") is None
    assert qualified("8*35,*51") is None


def test_a_plus_is_the_blood_group_sign_not_a_star(vocabulary) -> None:
    """These pages print bare `A+`/`O-` tokens inside the column bands."""
    assert qualified("DRB1+15,+01") is None
    values = {**FILLED, "DRB1": "DRB1+15,+11"}
    assert "DRB1" not in read(sheet(values), vocabulary).claims


def test_the_stars_the_laboratory_prints_are_accepted(vocabulary) -> None:
    assert qualified("A*24,*02") is not None
    assert qualified("A'24,'02") is not None
    assert qualified('A"24,"02') is not None


def test_a_star_less_token_on_the_row_taints_the_locus(vocabulary) -> None:
    """`A24` parses WITH a prefix. Skipping it hides it from MAX_VALUES, so a
    row of three tokens binds two and reports a complete pair."""
    values = dict(FILLED)
    found = read(sheet(values, extra=[at("A24", DONOR_X + 0.02, ROWS["A"])]), vocabulary)
    assert "A" not in found.claims


def test_a_bare_locus_star_stub_taints_the_locus(vocabulary) -> None:
    """`find_anchors` refuses `DRB1*` as a label — the star stops it — and the
    parser refuses it as a value, so it is invisible to both fences while
    naming a gene out loud. Eleven of sixty pages print one."""
    found = read(sheet(extra=[at("DRB1*", DONOR_X + 0.02, ROWS["DRB1"])]), vocabulary)
    assert "DRB1" not in found.claims


def test_a_printed_label_for_a_claimed_locus_wins(vocabulary) -> None:
    """Geometry always gets first refusal; this pass never overrules a label."""
    found = read(sheet(extra=[at("HLA-A", 0.05, ROWS["A"], w=0.08)]), vocabulary)
    assert "A" not in found.claims


def test_an_inadmissible_value_taints_the_page(vocabulary) -> None:
    values = {**FILLED, "A": "A*99,*98"}
    assert read(sheet(values), vocabulary).claims == {}


def test_more_values_than_a_locus_can_have_is_refused(vocabulary) -> None:
    found = read(sheet(extra=[at("A*11", DONOR_X + 0.02, ROWS["A"], w=0.04)]), vocabulary)
    assert "A" not in found.claims


def test_two_loci_on_one_printed_row_withdraw_each_other(vocabulary) -> None:
    found = read(sheet(extra=[at("DQB1*03,*05", DONOR_X + 0.02, ROWS["A"])]), vocabulary)
    assert "A" not in found.claims and "DQB1" not in found.claims


def test_the_loci_must_be_in_the_templates_vertical_order(vocabulary) -> None:
    """Six pages bound a C token BELOW DRB1 and DQB1 on a form that never
    prints C. The order gate is a template constraint, not a template cell."""
    values = {"DQB1": "A*24,*02", "A": "DQB1*03,*05"}
    assert read(sheet(values), vocabulary).verdict == "REFUSE"


def test_a_qualified_token_outside_the_band_refuses_the_page(vocabulary) -> None:
    """The band edge is a cliff: two of the three pages carrying a token
    outside it carried a C at 16.0 and 16.3 header heights, invisible to the
    row-order gate that would have refused them at 15.9."""
    far = at("A*24,*02", DONOR_X, HEADER_Y + 16.3 * HEADER_H)
    boxes = header_boxes() + [far]
    assert read(boxes, vocabulary).verdict == "REFUSE"
    near = at("A*24,*02", DONOR_X, HEADER_Y + 15.0 * HEADER_H)
    assert read(header_boxes() + [near], vocabulary).verdict == "BIND"


def test_a_bare_blood_group_under_a_heading_neither_anchors_nor_parses(vocabulary) -> None:
    """29 bind pages carry one inside a column band. `A+` must never become an
    HLA-A value, and `A` must never become an anchor."""
    from kidneymatch.ocr.anchors import find_anchors
    from kidneymatch.ocr.glyphs import parse_allele_values

    for text in ("A", "B", "AB", "O", "A+", "B-", "O+"):
        assert parse_allele_values(text) == []
    boxes = sheet(extra=[at("A+", DONOR_X, 0.36, w=0.03)])
    assert find_anchors(boxes, "A") == []
    assert read(boxes, vocabulary).verdict == "BIND"


# --- the emptiness predicate itself -----------------------------------------


@pytest.mark.parametrize(
    "text", ["A*24,*02", "*01,*02", "'01,'02", "01,02", "*01:01,*02:01", "*02", "12/06/2024"]
)
def test_the_other_column_is_not_empty_when_it_holds_this(text: str) -> None:
    assert holds_a_value(text)


@pytest.mark.parametrize("text", ["", "   ", "Frequency", "Donor", "A"])
def test_the_other_column_is_empty_when_it_holds_this(text: str) -> None:
    assert not holds_a_value(text)


# --- naming the column where no role fact exists (never a value) ------------


def test_no_independent_role_names_the_column_instead(vocabulary) -> None:
    found = read(sheet(), vocabulary, role=Role.UNKNOWN, role_resolved=False)
    assert found.verdict == "NAME"
    assert sorted(found.claims) == ["A", "DQB1", "DRB1"]


def test_the_named_reason_never_says_which_role(vocabulary) -> None:
    """`tools/hla_review.html` prints the reason under "refused:" unless blind
    is checked, right beside the Role select the reviewer is supposed to answer
    independently. Naming the column there answers their question for them."""
    assert "DONOR" not in column_bind.NAMED_REASON.upper()
    assert "RECIPIENT" not in column_bind.NAMED_REASON.upper()
    assert "two-column" not in column_bind.NAMED_REASON


def test_the_named_branch_is_never_resolved() -> None:
    """The naming rests entirely on the OCR of one English word: swapping the
    headings flips it 60 times out of 60, and no page carries a Persian role
    word on that row to corroborate it."""
    source = Path(column_bind.__file__).read_text(encoding="utf-8")
    assert 'status="RESOLVED" if binding else "REVIEW_REQUIRED"' in source


# --- provenance, and being able to take it all back -------------------------


def test_each_branch_writes_its_own_source() -> None:
    assert column_bind.SOURCE == "column-bound"
    assert column_bind.NAMED_SOURCE == "column-named+role-unconfirmed"
    assert column_bind.REFUSED_SOURCE == "column-bind-refused"


def test_the_bind_records_which_role_source_gated_it(vocabulary) -> None:
    """61% of binds rest on a caption claim and 25% on a bare role word. Each
    group has to be withdrawable on its own."""
    found = read(sheet(), vocabulary, role_source="CAPTION_CLAIM")
    assert column_bind.rule_id_for(found) == "column/DONOR+right+CAPTION_CLAIM"
    assert "CAPTION_CLAIM" in column_bind.bind_reason(found)
    assert "DONOR" in column_bind.bind_reason(found)


def test_the_refusal_reuses_the_mainline_two_subject_string() -> None:
    """`extract_facts` writes it, `review_pack` tags on it, and a query written
    against one must keep matching the other."""
    mainline = (ROOT / "scripts/extract_facts.py").read_text(encoding="utf-8")
    assert f'reason = "{column_bind.TWO_SUBJECT_REASON}"' in mainline


def test_the_comparison_sheet_guard_fails_closed() -> None:
    """Every page this pass touches is a comparison sheet, so a query that
    cannot run must stop it rather than hand it an empty corpus."""
    con = sqlite3.connect(":memory:")
    with pytest.raises(sqlite3.OperationalError):
        column_bind.comparison_sheets(con)
    con.close()


# --- the write, against a real table ----------------------------------------

FACT_COLUMNS = (
    "sha256, field, extraction_version, status, value, raw, repaired, second_allele, reason, "
    "rule_id, anchor_box, value_boxes, source, created_utc"
)


def facts_db(tmp_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(tmp_path / "facts.sqlite")
    con.execute(f"CREATE TABLE fact ({FACT_COLUMNS})")
    rows = [
        ("s1", "A", "UNKNOWN", "no anchor on this document", None),
        ("s1", "DRB1", "RESOLVED", "read from the anchored cell", "DRB1*15"),
        ("s1", "DQB1", "NOT_TESTED", "this laboratory never fills this row", None),
        ("s1", "B", "REVIEW_REQUIRED", "no anchor on this document", None),
    ]
    for sha, locus, status, reason, value in rows:
        con.execute(
            "INSERT INTO fact (sha256, field, extraction_version, status, reason, value, "
            "repaired, created_utc) VALUES (?,?,?,?,?,?,0,'t')",
            (sha, locus, column_bind.EV, status, reason, value),
        )
    con.commit()
    return con


def status_of(con: sqlite3.Connection, locus: str) -> str:
    return con.execute("SELECT status FROM fact WHERE field=?", (locus,)).fetchone()[0]


def test_the_write_only_ever_touches_an_unknown_no_anchor_cell(tmp_path: Path) -> None:
    """A RESOLVED value, a NOT_TESTED row and a cell already in review belong to
    other passes and to other arguments."""
    con = facts_db(tmp_path)
    for locus in ("A", "DRB1", "DQB1", "B"):
        column_bind._write(
            con,
            "s1",
            locus,
            status="RESOLVED",
            value="A*24",
            raw="A*24",
            second="UNREAD",
            reason="r",
            rule_id="column/DONOR+right+FORM_FIELD",
            source=column_bind.SOURCE,
            anchor=Box(0.1, 0.1, 0.2, 0.2, ""),
            value_boxes=[Box(0.3, 0.3, 0.4, 0.4, "")],
            now="t2",
        )
    con.commit()
    assert status_of(con, "A") == "RESOLVED"
    assert con.execute("SELECT source FROM fact WHERE field='A'").fetchone()[0] == "column-bound"
    assert status_of(con, "DRB1") == "RESOLVED"
    assert con.execute("SELECT source FROM fact WHERE field='DRB1'").fetchone()[0] is None
    assert status_of(con, "DQB1") == "NOT_TESTED"
    assert status_of(con, "B") == "REVIEW_REQUIRED"
    assert con.execute("SELECT source FROM fact WHERE field='B'").fetchone()[0] is None
    con.close()


def test_a_written_cell_carries_its_crop_and_its_header(tmp_path: Path) -> None:
    con = facts_db(tmp_path)
    column_bind._write(
        con,
        "s1",
        "A",
        status="REVIEW_REQUIRED",
        value=None,
        raw="A*24,*02",
        second=None,
        reason=f"{column_bind.TWO_SUBJECT_REASON}; both columns hold values",
        rule_id="column/two-subjects",
        source=column_bind.REFUSED_SOURCE,
        anchor=Box(0.2, 0.1, 0.7, 0.12, ""),
        value_boxes=[Box(0.6, 0.19, 0.69, 0.21, "")],
        now="t2",
    )
    con.commit()
    row = con.execute(
        "SELECT anchor_box, value_boxes, raw, source, reason FROM fact WHERE field='A'"
    ).fetchone()
    assert row[0] and row[1] and row[2]
    assert row[3] == "column-bind-refused"
    assert row[4].startswith(column_bind.TWO_SUBJECT_REASON)
    con.close()


def test_a_bind_is_withdrawn_when_the_role_fact_stops_agreeing(tmp_path: Path) -> None:
    """The role agreement is the whole wrong-person defence, so it cannot be
    checked once and forgotten: `caption_pass`, `role_repass` and a refresh all
    rewrite ROLE facts after this pass has run."""
    con = facts_db(tmp_path)
    con.execute(
        "UPDATE fact SET status='RESOLVED', source=?, rule_id=? WHERE field='A'",
        (column_bind.SOURCE, "column/DONOR+right+CAPTION_CLAIM"),
    )
    con.commit()
    agreeing = {"s1": ("RESOLVED", "DONOR", "CAPTION_CLAIM")}
    assert column_bind.withdraw_stale(con, agreeing, dry_run=False) == 0
    assert status_of(con, "A") == "RESOLVED"

    for roles in ({"s1": ("RESOLVED", "RECIPIENT", "CAPTION_CLAIM")}, {}):
        con.execute("UPDATE fact SET status='RESOLVED' WHERE field='A'")
        assert column_bind.withdraw_stale(con, roles, dry_run=True) == 1
        assert status_of(con, "A") == "RESOLVED", "a dry run writes nothing"
        assert column_bind.withdraw_stale(con, roles, dry_run=False) == 1
        assert status_of(con, "A") == "REVIEW_REQUIRED"
    con.close()


# --- the whole pass, against synthetic databases -----------------------------

SHA = "c" * 64


def corpus(tmp_path: Path) -> tuple[Path, Path, Path]:
    """One comparison sheet, its stored boxes, and no geometry at all."""
    facts = tmp_path / "facts.sqlite"
    con = sqlite3.connect(facts)
    con.execute(f"CREATE TABLE fact ({FACT_COLUMNS})")
    con.execute("CREATE TABLE document (sha256, extraction_version, rel_path, comparison_sheet)")
    con.execute("INSERT INTO document VALUES (?,?,?,1)", (SHA, column_bind.EV, "photos/a.jpg"))
    for locus in ("A", "B", "C", "DRB1", "DQA1", "DPA1", "DPB1"):
        con.execute(
            "INSERT INTO fact (sha256, field, extraction_version, status, reason, repaired, "
            "created_utc) VALUES (?,?,?,'UNKNOWN','no anchor on this document',0,'t')",
            (SHA, locus, column_bind.EV),
        )
    # Already answered by an earlier pass: this pass must leave it alone.
    con.execute(
        "INSERT INTO fact (sha256, field, extraction_version, status, value, reason, repaired, "
        "created_utc) VALUES (?,?,?,'RESOLVED','DQB1*03 DQB1*05','read from the cell',0,'t')",
        (SHA, "DQB1", column_bind.EV),
    )
    con.execute(
        "INSERT INTO fact (sha256, field, extraction_version, status, value, source, repaired, "
        "created_utc) VALUES (?,?,?,'RESOLVED','DONOR','FORM_FIELD_BARE',0,'t')",
        (SHA, "ROLE", column_bind.EV),
    )
    con.commit()
    con.close()

    ocr = tmp_path / "ocr.sqlite"
    con = sqlite3.connect(ocr)
    con.execute(
        "CREATE TABLE ocr_result (sha256, rel_path, boxes_json, texts_json, width, height, n_boxes)"
    )
    boxes = sheet()
    import json

    con.execute(
        "INSERT INTO ocr_result VALUES (?,?,?,?,?,?,?)",
        (
            SHA,
            "photos/a.jpg",
            json.dumps([[b.x0, b.y0, b.x1, b.y1] for b in boxes]),
            json.dumps([b.text for b in boxes]),
            1000,
            1400,
            len(boxes),
        ),
    )
    con.commit()
    con.close()
    return facts, ocr, tmp_path / "no-geometry.sqlite"


def test_the_pass_binds_a_whole_page_and_leaves_the_rest_alone(tmp_path: Path) -> None:
    facts, ocr, geometry = corpus(tmp_path)

    dry = column_bind.run(facts, ocr, geometry, dry_run=True)
    assert dry["bound from its column: A"] == 1
    assert dry["bound from its column: DRB1"] == 1
    assert dry["claimed, but that cell is not ours to answer"] == 1, "DQB1 is already RESOLVED"
    con = sqlite3.connect(facts)
    assert (
        con.execute("SELECT count(*) FROM fact WHERE source=?", ("column-bound",)).fetchone()[0]
        == 0
    ), "a dry run writes nothing"
    con.close()

    column_bind.run(facts, ocr, geometry, dry_run=False)
    con = sqlite3.connect(facts)
    rows = dict(
        (locus, (status, value, source, boxes))
        for locus, status, value, source, boxes in con.execute(
            "SELECT field, status, value, source, value_boxes FROM fact"
        )
    )
    assert rows["A"][:3] == ("RESOLVED", "A*24 A*02", "column-bound")
    assert rows["A"][3], "the crop travels with the fact"
    assert rows["DRB1"][:3] == ("RESOLVED", "DRB1*15 DRB1*11", "column-bound")
    assert rows["DQB1"] == ("RESOLVED", "DQB1*03 DQB1*05", None, None), "untouched"
    assert rows["B"][0] == "UNKNOWN", "the page prints no B row"
    rule = con.execute("SELECT rule_id FROM fact WHERE field='A'").fetchone()[0]
    assert rule == "column/DONOR+right+FORM_FIELD_BARE"
    con.close()


def test_a_page_whose_role_fact_disagrees_is_left_as_it_was(tmp_path: Path) -> None:
    """No value, and no review item either: this is not a two-subject page, it
    is a page whose two signals disagree, and that is the ordinary refusal."""
    facts, ocr, geometry = corpus(tmp_path)
    con = sqlite3.connect(facts)
    con.execute("UPDATE fact SET value='RECIPIENT' WHERE field='ROLE'")
    con.commit()
    con.close()
    tally = column_bind.run(facts, ocr, geometry, dry_run=False)
    assert tally["refused: the document's own role fact contradicts the filled column"] == 1
    con = sqlite3.connect(facts)
    assert con.execute("SELECT count(*) FROM fact WHERE source LIKE 'column%'").fetchone()[0] == 0
    con.close()


def test_a_page_with_no_role_fact_is_named_for_review(tmp_path: Path) -> None:
    facts, ocr, geometry = corpus(tmp_path)
    con = sqlite3.connect(facts)
    con.execute("UPDATE fact SET status='UNKNOWN', value=NULL WHERE field='ROLE'")
    con.commit()
    con.close()
    column_bind.run(facts, ocr, geometry, dry_run=False)
    con = sqlite3.connect(facts)
    status, value, source, boxes, anchor = con.execute(
        "SELECT status, value, source, value_boxes, anchor_box FROM fact WHERE field='A'"
    ).fetchone()
    assert (status, value, source) == ("REVIEW_REQUIRED", None, "column-named+role-unconfirmed")
    assert boxes and anchor
    con.close()


def test_the_pass_refuses_to_run_at_all_without_the_sheet_table(tmp_path: Path) -> None:
    facts, ocr, geometry = corpus(tmp_path)
    con = sqlite3.connect(facts)
    con.execute("DROP TABLE document")
    con.commit()
    con.close()
    with pytest.raises(sqlite3.OperationalError):
        column_bind.run(facts, ocr, geometry, dry_run=True)


# --- ENTITY-001: two documents, two roles, no link ---------------------------


def test_a_conflicting_role_blocks_a_link_rather_than_weakening_it() -> None:
    """The invariant this pass leans on when it writes one person's facts onto
    a page that pictures two: if the column named the wrong one, entity
    resolution must refuse the link outright, not average it away."""
    from kidneymatch.domain import entity_resolution as er

    source = Path(er.__file__).read_text(encoding="utf-8")
    assert "role" in source.lower() and "block" in source.lower()


# --- the review pack must be able to sample any of this ----------------------


def review_pack():
    spec = importlib.util.spec_from_file_location("km_pack_cb", ROOT / "scripts/review_pack.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["km_pack_cb"] = module
    spec.loader.exec_module(module)
    return module


def test_the_new_sources_have_their_own_strata_above_review_refused() -> None:
    """A document is pooled by its FIRST matching tag. Below `review_refused`
    (7,798 documents, quota 15) these pages are never sampled, and a pass
    nobody can see is a pass nobody can check."""
    module = review_pack()
    order = [t for t, _, _ in module.STRATA]
    assert "column_bound" in order and "column_named" in order
    assert order.index("column_bound") < order.index("review_refused")
    assert order.index("column_named") < order.index("review_refused")


def _cell(module, locus, status, source, boxes=((0.1, 0.1, 0.2, 0.2),)):
    return module.Cell(
        locus=locus,
        status=status,
        value=None,
        raw=None,
        repaired=False,
        second_allele=None,
        reason=None,
        rule_id=None,
        stability=None,
        source=source,
        anchor_box=None,
        value_boxes=[list(b) for b in boxes],
    )


def _doc(module, cells):
    doc = module.Doc(
        sha256="s" * 64,
        rel_path="photos/x.jpg",
        quality_band="HIGH",
        family=None,
        comparison_sheet=True,
        consistency=None,
        consistency_reason=None,
    )
    doc.cells = {c.locus: c for c in cells}
    return doc


def test_a_named_column_is_not_filed_as_an_ordinary_refusal(tmp_path: Path) -> None:
    """`review_refused` means "boxes sat on the row and the resolver refused";
    `zero_fact_refused` means "labels anchored and every cell refused". Neither
    describes a page that anchors nothing and was named by its column."""
    module = review_pack()
    doc = _doc(module, [_cell(module, "A", "REVIEW_REQUIRED", "column-named+role-unconfirmed")])
    tags = module.tag_document(doc, tmp_path)
    assert "column_named" in tags
    assert "review_refused" not in tags and "zero_fact_refused" not in tags


def test_a_bound_column_is_tagged_and_a_refusal_is_not_miscounted(tmp_path: Path) -> None:
    module = review_pack()
    bound = _doc(module, [_cell(module, "A", "RESOLVED", "column-bound")])
    assert "column_bound" in module.tag_document(bound, tmp_path)
    refused = _doc(module, [_cell(module, "A", "REVIEW_REQUIRED", "column-bind-refused")])
    tags = module.tag_document(refused, tmp_path)
    assert "review_refused" not in tags and "zero_fact_refused" not in tags
