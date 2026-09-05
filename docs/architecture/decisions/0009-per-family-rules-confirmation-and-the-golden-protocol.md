# ADR 0009 — Per-family rules, independent confirmation, and the golden protocol

**Status:** ACCEPTED (2026-09-02)
**Extends:** ADR 0007 (relations, not coordinates), ADR 0008 (extraction gates)
**Answers:** `EXTRACTION_REVIEW_2026-09-02.md` sections P1–P4

## 1. Template discovery was measuring the patient, not the form

Discovery assigned **707 of 23,485** documents to a family while one laboratory
accounts for about two thirds of the corpus. Three causes, all reproduced:

* The signature counted the grouped `DRB3/4/5` row's **values** as form labels.
  12,178 of 12,641 standalone `DRB3` boxes sit on that header's row, where they
  are the patient's presence typing, so one form split into at least seven
  "templates" by genotype and 4,262 documents fell into groups too small to
  cluster.
* It clustered in **absolute page coordinates**. The `HLA-A` label spans y 0.165
  to 0.408 between the 10th and 90th percentiles on hand-held photographs, so
  one form fragments into position blobs.
* Anchor purity then failed on those value-bearing "labels".

**ADR 0007's `DRB4` "in two columns 0.285 apart" was this all along.** `DRB4`
sits at x 0.709 when `DRB3` shares its row and 0.474 when it is alone. That was
never two sub-templates; it was one row with a variable number of values. The
conclusion ADR 0007 drew from it — store relations, not coordinates — remains
right for other reasons, but its evidence was an artefact.

### Decision

A form's signature is the position of the labels the **form** prints in a fixed
place: `A`, `B`, `C`, `DRB1`, `DQA1`, `DQB1`, `DPA1`, `DPB1`. Documents are
compared by fitting an isotropic scale and offset, with the residual expressed
as a fraction of the form's own extent so the threshold means the same thing
however a prototype was built. Three labels are required, because two determine
a fit exactly. Ties are refused.

**Building this reproduced the bug it fixes.** Greedy agglomeration at a tight
threshold split one form into nine prototypes whose mutual residuals were inside
the assignment tolerance; every document then fitted several and 4,096 were
refused as ambiguous. Prototypes that fit each other are one form and are merged.

Coverage: **707 → 12,300 documents (52.4%)** in three printed forms, and 75% of
the documents carrying three or more form labels.

## 2. A per-family rule, gated on a measured property

The default relation caps the value chain at 20 anchor heights. On the dominant
form the second allele column sits 8–25 heights away, so the cap cuts it off:
3,800 of the assigned documents' cells resolved with one allele.

The family rule reads the whole row band with **no distance cap** and requires
each value to print its own locus. The prefix requirement, not the distance, is
what makes that safe — and it is **measured per family rather than assumed**:
99.8–99.9% on all three forms. The first measurement said 65% because it counted
every parseable box on the page, including dates and sample numbers; the
property is about values bound in a cell.

| on the 12,300 assigned documents | default | family rule |
|---|---|---|
| resolved cells | 28,783 | **39,606** |
| two-allele cells | 24,983 | **39,511** |
| single-allele cells | 3,800 | **95** |
| nomenclature-impossible values | 0 | **0** |
| one box bound by two loci | 0 | **0** |
| DRB1↔DRBX disagreement | 7 / 4,975 | 27 / 7,923 |

The disagreement rate rises from 0.14% to 0.34% on a 59% larger checkable base,
and every one of those goes to review rather than into the database.

A document whose form is not recognised keeps the default. Claiming a family
would apply its authored rule to a layout it was never measured on.

## 3. The golden corpus: a protocol, not a spreadsheet

**The unit is the cell.** 199 documents hold 2,189 cells, 948 of them resolved.
Zero failures over 948 bounds false acceptance at **0.32%** by the rule of
three; the document as a unit could only ever bound it at 1.5%.

**The labeller never sees the machine's answer.** It is written to a separate
file the labelling page does not load. A proposal beside a blurry crop is an
anchor, and an anchored labeller measures agreement rather than truth. A
contract test asserts the page cannot reach it.

**Two people label, a third adjudicates.** Double entry by a *different*
operator detects 88.3% of errors against 69.0% for the same operator twice;
letting the two entrants reconcile makes the entries match, sometimes by
introducing new errors. Each annotator's name seeds a different order.

**Only two outcomes are failures**: a cell resolved to a value the human read
differently, or resolved at all where the human could read nothing. Abstaining
where a value exists is a *miss* — an incomplete record is a cost, a wrong one
is a harm. `scripts/golden_score.py` exits non-zero on a single failure, and
also on an empty corpus, so an unlabelled set cannot read as a clean bill of
health.

*Amended 2026-09-05.* A third non-failure outcome, **partial**: the pipeline
resolved ONE allele, declared the second `UNREAD` (KI-015), and that allele is
inside the pair the human read. It is right as far as it goes and honest about
stopping — an incomplete record, scored beside `missed`. Without the
declaration a single value against a printed pair stays a false acceptance.
Partial reads count toward the cells the rule-of-three bound is taken over:
they were resolved and not contradicted, and a pipeline that stopped early on
every pair would be caught by the `partial` column, not hidden by the bound.
Measured on the first 165 anchored labels, 1 of the 2 non-DRB3/4/5
"contradictions" was exactly this. A PRESENT call on a DRB3/4/5 gene is
correct whenever the human saw the gene printed, whether they recorded only
its name or also an allele beside it; the pipeline made no claim about the
allele.

## 4. Confirmation by an independent engine

ADR 0006 requires unanimity across architecturally independent recognizers,
having measured that a 2-of-3 majority across neural engines is *worse* than
unanimity (3.50% against 4.50% false acceptance): engines sharing an
architecture share their mistakes, so a majority of them is one opinion counted
three times.

Tesseract is the independent one available. Cells are re-cropped from the
original at the anchor-defined geometry, not from the primary engine's box.

Two decisions came from measuring:

* **The whitelist must include letters.** Digits alone confirmed 20.8% of cells,
  because the forms that print the locus on every value show `DRB1*11`.
* **The confirmer confirms digits, not the locus.** Requiring its prefix to
  parse withheld 130 of 400 cells where `DRB1*11` had been rendered `RB1*11` and
  the digits were perfectly clear. The locus came from geometry and the primary
  pipeline already refused any value naming a different gene. A prefix read
  clearly and naming another gene still contradicts.

**The vocabulary gate applies to both engines.** Every contradiction the design
pass measured was Tesseract reading a family that does not exist for the locus,
so an impossible reading withholds rather than voting against a possible one.
Three outcomes: `CONFIRMED` (auto-accept candidate), `CONTRADICTED` (review
budget), `UNCONFIRMED` (no second opinion; the value stands on the primary
engine alone).

### Measured over all 46,221 resolved cells

| locus | cells | confirmed | contradicted | no opinion |
|---|---|---|---|---|
| DRB1 | 11,112 | **60.4%** | 15.0% | 24.6% |
| DQB1 | 9,675 | **60.0%** | 16.3% | 23.7% |
| DQA1 | 725 | 52.6% | 17.7% | 29.8% |
| A | 11,628 | 31.4% | 13.5% | 55.1% |
| B | 10,911 | 28.5% | 12.7% | 58.8% |
| C | 3,114 | 27.2% | 12.1% | 60.7% |
| **all** | **46,221** | **43.5%** | **14.2%** | **42.2%** |

A design pass reported 86.3% agreement on a 300-cell DRB1/DQB1 sample. On those
same two loci this measures **60.2%**, so most of the apparent shortfall was the
class I loci being pooled in — but a real gap of about 26 points remains and is
**not explained**. It is reported as measured rather than closed by tuning,
because the confirmer's worth is settled by the golden corpus and not by its own
agreement rate.

The class I pattern is the clearer finding: `A`, `B` and `C` yield *no opinion*
on 55–61% of cells, against 24% for `DRB1`. Tesseract is not contradicting those
readings, it simply cannot read the cells, and that is where any future work on
the confirmer belongs.

`DPA1` and `DPB1` show 56–67% contradiction on 24 and 32 cells respectively —
too few to mean anything, and consistent with those rows being blank on this
corpus (KI-013).

## 5. What none of this establishes

No number here is an accuracy. The pipeline is now self-consistent, gated, and
independently spot-checked, and it still has never been compared to a human
reading (KI-012). Everything above is a yield, an internal-consistency rate, or
an agreement rate between two machines. **HA-007** is the work that changes
that, and until it is done nothing may be published to Gold.

## 6. Amendment 2026-09-02: the anchored review pack, and three measured corrections

Written after the constrained decode (P5) ran over the corpus and the six open
issues were reviewed (`docs/ingestion/OPEN_ISSUES_SOLUTIONS_2026-09-02.md`).

### The decode's corpus-wide verdicts

Over 53,789 cells: UNANIMOUS 79.8%, DIGITS_LOST 10.5%, SPLIT 6.1%, PROPOSAL
3.2%, ILLEGIBLE 0.4%. On resolved facts alone, before the correction below:
43,326 UNANIMOUS, 2,222 SPLIT, 1,670 DIGITS_LOST, 3 ILLEGIBLE.

SPLIT was checked and stands: 93-100% of SPLIT cells per locus are real digit
disagreements between one-pixel offsets, not the prefix rendering differently.
C is the unstable locus (30% SPLIT on FORM#1 against 3-4% for A and B).

**DIGITS_LOST was firing on the locus digit.** Re-examined on 300 demoted cells
(349 boxes): 240 fired only because the greedy path dropped the star, so the
`1` of `DRB1` was compared as a value digit; 108 were the decode adding a digit
the model never read, which is the loss the gate exists for. `digits_preserved`
now strips the leading letters of a star-less reading and forgives exactly one
locus digit; the value digits must still survive in full, in both directions
(tests pin `DQB1103` against `DQB1*03` as lost). The 5,695 DIGITS_LOST cells
were re-decoded under the corrected gate: on resolved facts DIGITS_LOST went
1,670 → 459, UNANIMOUS 43,326 → 44,504, and 33 cells that the digit gate had
masked surfaced as SPLIT. No value changed; 1,178 facts regained their standing.

### The confirmer confirms star-less digits too

Section 4 left the class I gap unexplained. Measured on FORM#1: the class I
value box is 57% the width of a class II box at the same height (`A*02` is four
glyphs, `DRB1*11` seven), Tesseract returns nothing on 19-32% of those crops,
and only 7-14% of its remaining unconfirmed readings contain a star. `_read`
now treats `A02`, `Cw07` and `DRB111` the way `digits_preserved` does. Re-judged
over the 47,621 stored readings with no OCR re-run (`confirm_pass.py
--rescore`): CONFIRMED 20,613 → 22,969, CONTRADICTED 6,795 → 6,633, UNCONFIRMED
20,213 → 18,019. Most of the gap is the empty readings, and that is a recognizer
question, answered in `docs/ingestion/OCR_MODEL_SURVEY_2026-09-02.md`.

### `ABSENT` is a label state

DRB3/4/5 resolve to PRESENT or ABSENT. The golden schema could only say
PRESENT_ONLY, against which any pipeline value scored as correct, so a form
printing "not present" could never contradict a pipeline PRESENT. `ABSENT` is
added and scored: PRESENT_ONLY against a pipeline ABSENT, and ABSENT against a
pipeline PRESENT, are false acceptances.

### The anchored pack is a second instrument, not a replacement

`scripts/review_pack.py` draws documents from fifteen strata (one per failure
signal the pipeline emits, rarest first, plus a clean control) and
`tools/hla_review.html` shows each cell with every engine's reading and the
pipeline's value pre-filled. It is faster than the blind tool and it anchors
the reader, so every cell records APPROVED / EDITED / ADDED and the export is
marked `anchored: true`. The blind corpus (section 3) remains the instrument
for the published bound; the pack is the instrument for *which signal predicts
errors*. Labels are `golden-labels/v1` and are scored by `golden_score.py`
against the pack's `pipeline.json`.

Section 5 stands unchanged: still no accuracy, still nothing to Gold.

## 7. Amendment 2026-09-05: what the second labelled export changed

Written after the reviewer's second anchored export (187 cells, 17 documents)
was traced cell by cell to a root cause and each cause was measured across the
corpus (`docs/exec-plans/active/OCR-GEOM-001-geometry-and-drbx-row.md`, M4b).
Under the refreshed facts the export scored 78 correct, 74 correct abstentions,
29 missed, 4 contradicted, 2 partial. Every change below is a rule the labels
and a corpus measurement both bore out; no change binds a value to a locus its
printed label does not name, the one label repair that can move a damaged
label between loci is accepted on the geometry evidence below and pinned by
the tests, and every promoted or newly-bound cell keeps its provenance.

### The locus label's interior: one repair, measured
`canonical_locus_label` repaired only the final character. The recognizer reads
`DQB1` as `DOBI` (2,150 boxes `HLA-DOBI`, 261 `DOBI`) and `DQA1` as `DOAI`, so
those labels never anchored and the values beneath them, which print the same
prefix, never parsed. The geometry is decisive: 774 refused `DOB…` values sat
under a DQB1 anchor against 1 under DRB1 (76 `DOA…` under DQA1 against 2 under
DPA1), and the 2,410 documents printing a `DOBI`-shaped token carry a DRB1
anchor 87% of the time and a DQB1 anchor 4.6%. The one interior repair is
therefore `O`/`0` → `Q` in the second position; `R` and `P` are never repaired,
and the exhaustive rename sweep in the tests names the crossings this permits
(`DRB1`/`DPB1` → `DQB1`, `DPA1` → `DQA1`, via that glyph only). Trailing
punctuation after a label (`HLA-A*:` 513, `HLA-DQB1":` 307, `HLA-B:` 261) is
stripped; a star is stripped only behind an HLA prefix, because `DRB1*` alone
is as likely a value stub. The prefix itself accepts the recognizer's `ILA`,
`IILA`, `HILA`, and `LA-` before a separator — not a bare `LA`: that variant
made the letterhead's `LAB` an HLA-B anchor on 9,817 documents and was caught
by the refresh comparison, not by a test, which is why the comparison is now
part of the refresh procedure. Corpus: DQB1 resolved 10,207 → 12,618.

### Over-full cells on the family rule
On a form measured to print the locus on every value, a candidate that names
ANOTHER locus inside this row's band is the neighbouring row drifting into it
on a hand-held photograph. It is set aside before the candidate count; a
candidate that names no locus or does not parse is kept, so the existing gates
still refuse the cell. Gate 2 is unchanged for a cell with no more candidates
than the locus can hold. Measured: 1,366 refused cells held exactly two values
naming their own locus beside one or two naming another; 459 resolved.

### The default rule's tolerance band, as a fallback
The nearest allele-shaped box to a label whose cell read empty sits one anchor
height off the label's centre on 1,406 of 5,302 such cells. Applied as a first
criterion, a 1.5-height centre band resolved 949 of them but also added
candidates to 799 cells that already resolved and refused them; applied only
when the overlap test read nothing (or one allele with its partner unread), and
kept only when the wider reading resolves, it adds and never subtracts: +901
cells, 890 second alleles (180 of them a homozygous partner), 0 boxes bound to
two loci, 0 values swapped. This amends ADR 0008's default relation.

### The grouped DRB3/4/5 header, and the slot that rests on a repair
Header v2 accepts the B slot's measured misreads (`DRR`, `DRE`, `DR$`, `DRH`,
`DRD`) and a slash read as `1`, and a missing `4` only behind an HLA prefix with
a slash-misread letter in its place; a 4-less token without those is a pair of
gene names, never a header. 605 header-less documents gain one, 505 with a gene
token then on the band (+1,056 gene calls). On the labelled pack, 7 of 10
ABSENT calls made beside a token whose `S` had been repaired to 5 were wrong, so
such a row now leaves the other genes REVIEW_REQUIRED (KI-026: −1,871 ABSENT
calls corpus-wide). The DRB5 PRESENT call stands, marked repaired, and
`confirm_pass.py --target drbx` reads every PRESENT gene box with PP-OCRv5
(19,372 boxes: 18,481 CONFIRMED / 114 CONTRADICTED / 777 no opinion on the
first run). The reader was then made to abstain on an `S` of its own and to
read a pair printed in one box (`DRB3/4`) as naming both genes: of the 1,912
repaired tokens it now confirms 1,152, contradicts 20 and renders the same
`S` on 740 — the second engine shares the glyph confusion on 39% of them,
which is why an `S` can never confirm the repair. A repaired call the reader
contradicts is demoted to review by the same pass (20 cells; the two labelled
contradictions were among them) and reinstated if a re-judging lifts the
contradiction.

The adversarial review of the diff (133 agents, 24 findings confirmed)
closed three gaps in the band: every gate now runs under the widened
alignment when the band is used, the grouped DRB3/4/5 header owns its row
like any label, and an anchor box out of scale with the page's other labels
gets no band. Re-extracted under those, 154 of the band's cells went back to
review (A 67, B 33, DRB1 29, C 16, DQB1 9), 7 values the header now owns
were withdrawn, and 0 values swapped — the comparison step of
`refresh_facts.py` reported each.

### A PROPOSAL becomes a fact only when a second engine reads the same
Section 6 recorded that the decode's PROPOSAL cells are never promoted on the
decode alone. They now can be, under one condition: `confirm_pass.py --target
proposals` has PP-OCRv5 read the same crop and judges it against the proposal,
and `promote_proposals.py` promotes exactly the CONFIRMED ones (1,889
proposals corpus-wide, 1,715 of them two alleles). The cell's locus came from
geometry and passed every gate before the parse; the value is admissible by
construction; and two independent recognizers read the same digits from the
same crop — the standard every RESOLVED cell meets when its confirmer agrees.
The promoted fact carries `repaired=1`, `source=decode+ppocrv5` and a reason
naming both engines, so the pack shows it and the golden gate can score
promotions apart. On the labelled export the pipeline's four proposals all
equalled the reviewer's reading. Two gates were added after the first run:
never on a LOW-quality page (of the two such promotions the labelled one was
wrong; LOW pages split the decode twice as often), and the confirmer's
reading is re-judged against the proposal at promotion time, with
admissibility re-checked, so a re-decoded cell is never promoted on a stale
agreement. A refusal for value shape is emitted only when every other box
in the cell passed every other gate, which is what makes the promoted boxes
values of this locus. Corpus, 2026-09-05: 2,026 proposals judged, 778
CONFIRMED / 885 CONTRADICTED / 363 no opinion; 775 promoted after the LOW
gate (DRB1 380, DQB1 216, B 108, A 37, DQA1 28, C 8). The 44% contradicted
is the measure of what promoting on the decode alone would have done.

### The empty DRB3/4/5 slot, certified by paper
A one-token grouped row left the other genes UNKNOWN (6,122 cells), because
an unread token and an empty slot look the same to a row rule. They do not
look the same on the page. `ocr/ink.py` places the second slot from the DRB1
row's two resolved value boxes — the form's own columns, never a guess — cuts
it in the level frame and measures its ink with the table rulings removed;
`drbx_ink_pass.py` certifies ABSENT when the slot is paper (thresholds at
least 2.5x under the least-inked of 4,904 columns holding a read token),
sends the other genes to review when it is inked (a token no engine read), and
leaves an unmeasurable slot alone. The certified fact carries the blank region
as its provenance box and `source=ink-certified`. Corpus: 3,338 genes ABSENT,
884 to review; the four labelled rows the reviewer had marked ABSENT all
measured as paper, and no labelled PRESENT cell became ABSENT. Ink never names
a gene.

### The printed table, read as a grid
The geometry pass stores every long ruling of every page to measure the tilt;
nothing had read them as what they are on a form — the lines that box each
value. Measured from the stored rulings alone (`ocr/lattice.py`): on the three
known forms, 4,541 cells had no readable locus label, and for 3,223 of them a
ruled row sat exactly where the form's template puts that label, 2,271 of
those rows holding one or two allele-shaped boxes; 24,187 cells had a readable
label and no box the overlap test could reach, and 20,517 of those rows held no
box at all while 774 held values. So `extract_facts.bind_in_lattice` runs after
the row rules: a label the recognizer could not read is placed by the form's
template — a VIRTUAL anchor box where the template prints it, only on a page
that fits the template (residual ≤ 0.04) and only under the family rule, where
every value prints its locus, so a value from a wrong row names another locus
and refuses itself (gate 2) — and a label with an empty overlap test is retried
in the ruled row around it. Both bind through `anchors.resolve_in_row` under
every existing gate, then `enforce_exclusivity` again; a grid reading replaces
the row rule's only when it resolves. Re-extracted: +2,264 cells (A +610,
B +682, DRB1 +535, DQB1 +298, C +139), 0 values swapped, provenance to the
real value boxes and the (virtual) anchor recorded with `rule_id …+lattice`
and a reason that says which template placed it.

The same grid places the second DRB3/4/5 slot on the rows without a DRB1 pair
(`drbx_ink_pass.py`), and lets `cell_ink_pass.py` measure the empty labelled
cells. That pass **writes no fact**: `NOT_TESTED` is HA-009's per-(family,
locus) verdict about a laboratory, decided by a person from a committed
statistic, and a per-page measurement is evidence for that decision rather
than the decision (HA-012). It fills `cell_ink` — the region, its ink, and
BLANK / INKED / UNMEASURABLE — which is what a person needs to extend HA-009
and what the review queue can order by. Ink never creates a value, and here it
does not retire a review item either.

**What counts as ink, and the control.** A first pass counted every dark pixel
and called 17,221 of 23,719 empty cells INKED — most under 1% ink, in runs
10-30 px wide with no height: JPEG noise, a printed dash, a ruling the tilt
spread over several rows. Ink is now counted only in connected components
shaped like a glyph (at least 4 px or a fifth of the region tall, under 8:1
wide), and a slot is called paper only when the same measure sees the ink the
page is KNOWN to hold — the read gene token, or the locus label itself — at
0.005 or more; below that the page's print is beyond the measure and every
slot on it is UNMEASURABLE. The adversarial review's remaining ink findings
(the absolute contrast floor, a shadow removed as a ruling, a value stacked
under its label) all bear on regions this measure no longer certifies from:
only the DRB3/4/5 slot, whose width the calibration was measured on. Re-measured on 2,806 read-token columns: 2,740 at
0.05 ink or more, one under 0.001, which is what the control exists for.
Corpus: 14,719 cells NOT_TESTED, 3,831 kept in review, 793 unmeasurable;
2,269 DRB3/4/5 rows paper (4,538 genes ABSENT), 262 inked, 127 unmeasurable.
On the reviewer's labels the certified cells are 19 the human marked BLANK,
4 DRB3/4/5 marked ABSENT and 4 NOT_PRINTED — **no cell where a value was
read** — and the 4 held as inked the human called blank, the abstaining
direction. Every pass re-judges its own earlier decisions and withdraws one
it can no longer measure, so the fact follows the evidence in both directions.

### Page geometry v3
The projection sweep corroborates the rulings within 2° (1,231 of 1,595 pages
refused at 1° disagreed by less), and the rulings' own agreement check — added
by the adversarial review on a synthetic case — is calibrated on photographs:
at 1°/80% it refused 6,772 of the 19,695 pages already measured to a MAD under
1.5°; at 3°/70% it refuses 88 of them and 969 genuinely bimodal pages. Corpus:
6,511 ROTATE / 14,139 STRAIGHT / 2,916 UNCERTAIN; 1,591 pages levelled at
extraction. A third estimator from the stored boxes was measured and rejected
(KI-025).

Section 5 stands: still no accuracy claim, still nothing to Gold.
