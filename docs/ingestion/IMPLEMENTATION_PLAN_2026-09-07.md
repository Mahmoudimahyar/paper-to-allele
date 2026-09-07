# Implementation plan — the checkpoints, what each one loses, and what to build (2026-09-07)

The operator's model of the pipeline is a chain of checkpoints; an extraction
error is a failure at the first one that did not hold. `scripts/checkpoint_attribution.py`
charges every non-correct labelled cell to a checkpoint from the fact's own
refusal reason and the page's orientation and geometry records. This plan is
that measurement turned into an ordered list of work, each item with the loss
it addresses, the change, and the gate it must pass on the same labels before
its facts count. It supersedes the ordering in `CV_PLAN_2026-09-07.md`; the
techniques there are the same, the order is now the measured one.

## The checkpoints, as they stand

The operator's four, with the ones the measurement adds:

| # | checkpoint | what must hold | labelled loss (of 169) |
|---|---|---|---|
| 0 | image quality | the asset is the best available; LOW/THUMBNAIL recorded, never guessed | 7% of failures on LOW pages, 7% of all cells — not over-represented |
| 1 | orientation | the page is upright | **0** — 611 sideways pages already turned (`upright_pass`) |
| 2 | tilt | the rulings are level | **0** — every page ≥1.5° is levelled; tilted pages are 19% of failures vs 15% of cells |
| 3a | layout: locus label | the printed label was found | **22** (13%) |
| 3b | layout: DRB3/4/5 header | the grouped header was read, or the row placed | **41** (24%) |
| 4 | cell rectangle | right row, right width: not empty, not one allele of two, not a neighbour's | **35** (21%): too short 19, too wide/wrong owner 12, empty 3, two subjects 1 |
| 5 | recognition | the characters in the right rectangle read right | **13** (8%; the only 2 wrong values are here) |
| 6 | DRB3/4/5 row grammar | the gene tokens on the row read as genes | **40** (24%) |
| 7 | precision gates | a right value is not withdrawn | **18** (11%) |
| 8 | policy | NOT_TESTED only where nothing is printed | 0 |
| 9 | whole-page fields | ABO / Rh / ROLE | ABO 48 missed of 96, RH 49, ROLE 16 (0/0/1 wrong) |

Two page-level signals the measurement adds: a **comparison sheet** carries
10% of failures and 2% of cells (5×), and a value rectangle **narrower than its
siblings** fails 50% of the time against an 11% baseline — the operator's
rectangle-size check, measured, is a real signal.

Baseline on 1,342 labels after the operator's re-check of the disputed pack:
**673 correct, 148 missed, 19 partial, 2 wrong** (of the 138 disputed cells, 6
were label errors and 132 stand as pipeline errors); ROLE 94/1, ABO 48/0, RH
47/0. Every gate below is measured against these labels and against round five.

## Outcome, 2026-09-07 — what each item did when it was built

Four items shipped, five were built or specified far enough to be MEASURED and
then declined on the evidence. A declined item is not a gap in the work: each
one below would have made the database less true, and the measurement that says
so is the deliverable. Every shipped pass is dry-run by default, carries its own
`source`/`rule_id`, has a review stratum and an exact `--undo`, and was applied
under a per-field status snapshot.

**On the 1,342 labels: 673 -> 691 correct, 148 -> 130 missed, 19 partial, 2
wrong (unchanged).** Corpus: DRB3/4/5 resolved +1,241, HLA value cells 68,916,
review queue 35,391 -> 34,278 cells.

| item | outcome | measured |
|---|---|---|
| **W1** checkpoint guards | **shipped** `scripts/checkpoint_guards.py` | `document` gains `orientation`, `residual_slope_deg`, `residual_source`. The residual of a levelled page is **re-measured from the rotated image**, not derived from the angle removed. 1,591 levelled pages: **1,513 come back under 0.5 deg, 78 do not** (61 at 0.5-1.0, 16 at 1.0-2.0, 1 at 2.6). A further 4,920 pages carry 0.5-1.5 deg that is never levelled. Checkpoints 1 and 2 still attribute 0 labelled failures |
| **W2(a)** row on an unresolved-DRB1 page | **shipped** — `resolve_token_anchored_drbx(allow_unresolved_drb1=True)` + new gate **G2b** | G2's DRB1-RESOLVED half is a proxy for one named hazard (DRB1's values walking into the grouped row); G2b tests for the hazard itself — no allele value may stand on the placed row. Of the 116 pages the lift admits, 95 carry no allele value there, 14 a bare one, 7 a DRB1-prefixed one. Applied only where DRB1 is unresolved: 56 of the 488 pages the route accepts today would fail it. **+116 cells on 92 pages**, own rule id, own stratum, 0 labelled cells (see W4) |
| **W2(b)** gene-token classifier | **not built** | Superseded by the measurement under W4: the residual DRB3/4/5 loss is not a reading problem. On 63 of the failing cells a gene-or-header token IS readable; what fails is placing the row |
| **W2(c)** gate-2 re-promotion | **shipped** `scripts/drbx_gate2_repromote.py` | Gate 2 is charged per PAGE, the damage is per CELL. Of the 21 labelled withdrawals, **18 were right and 3 wrong, and all 3 wrong rest on a repaired token** (`DRBS`, `DR83`). Page-level cleanliness would drop 18 to 12 and requiring DRB1 to agree 18 to 16, excluding no error either way. **+1,113 cells on 556 pages; +18 labelled correct, 0 new contradictions** |
| **W3(a)** second allele from the row | **shipped, tiny** `scripts/second_allele_reread.py` | The ink route does not reach this loss. On the 19 labelled partials the remainder of the ruled row holds ink on **2**; on 7 it measures BLANK, on 5 the rulings place no row and on 5 no value box is stored. The mechanics are sound — this crop and measure reproduce `cell_ink_pass`'s stored decision on **136 of 136** measurable cells — which is what makes the negative trustworthy. The pass therefore never writes a BLANK "one allele printed" finding, which would have been false on 7 of 9 measurable labelled cells. It writes only where ink is present and two engines agree: **4 cells corpus-wide**, unmeasured, own stratum. W3(a)'s target of 19 -> <=8 is **not reachable this way** |
| **W3(b)** too-wide / wrong owner | **specified, deliberately not built** | 8 of the 12 are `N candidate values exceeds max_values=2` — not a wide box to split but a choice of WHICH candidates the locus owns, and the plan's remedies do not apply. The fallback band cannot be the cause: it already refuses to widen past `max_values`. The refusal counts parsed ALLELES, and corpus-wide it holds **6,940 cells** whose candidate counts run 3 (1,945), 4 (1,526), 5 (1,054), 6 (738), 7 (524), 8-9 (263) — a whole printed row reached by the chain, not two pairs. Choosing 2 of 7 is the two-subject hazard the guard exists for; on all 8 labelled cells the person read exactly 2 alleles, but nothing in the geometry says WHICH 2. Position does not separate them (the test that appeared to was vacuous at n=2). Changing `anchors.resolve_in_row` on no separating signal, with 6,940 cells of blast radius, is how a pipeline starts publishing one person's genotype from two people's values |
| **W4** locus label | **declined on evidence** | Both named means fail. Family templates reach **6 of 22** labelled cells: 16 have no family at all, and corpus-wide 9,229 of 11,847 pages with a no-anchor cell have none — a family is assigned FROM the labels, so the pages that lose their labels lose their family too. Whole-page OCR is already done on 11 of the 22 and found the locus label **0 times of 11** (it did find the value's digits on 7). Generalising the DRB3/4/5 row anchor from DRB1 to another label was tested and refused: only **3 of 4,000** pages let the row-order model be validated at all, and on those 3 it mispredicts DRB1's own row by 1.38 label heights — more than enough to assign every gene on a page to the wrong row |
| **W5** gate-1 re-promotion | **declined on evidence** | Restoring all 18 labelled gate-1 withdrawals gives **5 correct and 13 contradictions**. No available evidence separates them: the best bucket (two engine families confirming, none contradicting) is **1 correct to 3 wrong**, and the constrained decoder cannot be the fourth witness because SPLIT is the verdict that triggered the gate. The plan's gate (>=9 back with 0 contradictions) is unreachable; gate 1 is doing its job |
| **W6** recognition | **in flight, not merged** | The Bw4/Bw6 half (D11) was built and adversarially reviewed in a worktree (`worktree-wf_e621faf4-df7-1`, 52 agents). Its re-review found a **high** defect (`bw_backfill --undo` stops matching once any of nine other passes re-stamps `created_utc`, leaving an untrackable write) and a **medium** one (a tailed token records its epitope even when the height or ownership gate refuses the box). Both carry reproducible counterexamples. **Not merged** |
| **W7** whole-page fields | **declined as specified** | ROLE: on **14 of the 16** misses the Persian pass ran and found neither `اهدا` nor `گیرنده`, so there is no anchor word for a tick detector to sit beside. ABO: of 48 misses, 27 are "no blood-group field label on this document" and 29 have neither the group word nor the donor word in the Persian OCR; ~15 do have the group word and are the genuine recognition candidates. Gates of 48 -> <=24 and 16 -> <=8 are not reachable by the named mechanisms |
| **W8** two-subject pages | **blocked** | HA-022, unchanged |
| **W9** measure, then export | **ready** | Round five is built and served (600 unseen pages, port 8767). Three new unmeasured groups now need it: `token_anchored_drbx_unresolved` (116 cells), `second_allele_reread` (4), and the re-promoted gate-2 group |

## What the measurement says to do next

The residual is **not** an OCR reading problem, which is what several of the
items above assumed. Of the 151 remaining labelled failures, **113 have the
value's digits readable in a store we already hold**, and on 63 of the DRB3/4/5
failures a gene-or-header token is readable too. Only 7 have nothing readable
at all. The loss is in BINDING: knowing which row and which column a readable
token belongs to, on pages whose locus labels our recognizer does not read.

That points at one thing rather than nine: a way to place rows and columns on a
page whose labels are unreadable, validated against pages where they ARE
readable so the row order can be checked rather than assumed. The one attempt
at it here (the DRB3/4/5 anchor generalisation) failed its own validation, and
the reason is worth keeping: the pages that need it are the pages that cannot
validate it. A learned table-structure model (`CV_PLAN_2026-09-07.md` phase 2)
is trained and validated on the pages that DO read, and is the only route in
either plan that gets around that.

## The original work list, as written

## The work, in order

Each item ships the way every pass now ships: dry-run by default, its own
`source` tag and review stratum, a status snapshot around the corpus write, a
label re-score, `checkpoint_attribution.py` re-run, and an adversarial review
before its yield is believed.

### W1 — checkpoint guards (½ day)
Orientation and tilt lose nothing today; make sure they go on losing nothing.
Record per page, in `document`: the orientation verdict and the **residual
ruling slope after levelling** (re-measured from the levelled image; must be
< 0.5°). The attribution prints both, so a regression at either checkpoint is
visible the day it happens rather than found in a labelling round.
*Gate:* checkpoints 1 and 2 stay at 0 on the labelled set.

### W2 — the DRB3/4/5 row (2–3 days; 81 cells, 48% of the loss)
(a) **Header not read (41).** Accept the damaged spellings of the grouped
header the widened pattern already recognises, and place the row from the
page's own label pitch even where DRB1 is not RESOLVED — today that is a gate of
the token-anchored route — provided the row band's ink is consistent with a
printed row.
(b) **Row grammar (40).** A three-class gene-token classifier (DRB3 / DRB4 /
DRB5 / none) on row-slot crops, trained on the 19,372 `@drbx` confirmations
already stored. It replaces the `S`-for-`5` repair and reads the slots whose ink
no engine boxed ("second slot holds ink that no engine read").
(c) **Second-opinion withdrawals (21 of the 40).** Re-promote a withdrawn call
when the classifier agrees with it — the D6-a pattern.
*Gate:* DRB3/4/5 misses 81 → ≤ 30; 0 new DRB3/4/5 contradictions; the
DRB1↔DRB3/4/5 consistency check reports 0 FORBIDDEN. HA-011 (a) is decided.

### W3 — the cell rectangle (2 days; 35 cells, 21%)
(a) **Too short (19; corpus: 4,788 RESOLVED cells carry `second_allele=UNREAD`).**
After the first allele binds, measure the ink in the remainder of the row band
past the value box (`ocr/ink.py`). If INKED, re-recognise the **row band**, not
the box, with the second engine and bind the second allele on two-engine
agreement. The narrow-rectangle flag is the trigger and, now, a review-ordering
signal.
(b) **Too wide / wrong owner (12).** The sibling check as a gate: a value box
wider than 2.2× the page median, or spanning two label rows, is split at the
column ruling or the nearest label row before binding, and refused if still
ambiguous.
(c) **Empty (3)** goes to W4; **two subjects (1)** to W8.
*Gate:* partials 19 → ≤ 8; too-wide 12 → ≤ 5; 0 new contradictions.

### W4 — the locus label (1 day + machine days; 22 cells, 13%; 11,847 pages corpus-wide)
Whole-page PP-OCRv6 over the corpus in resumable batches of ~500 (the box
powers off under sustained load), then `page_ocr_bind`. Then family templates:
for a page whose family is known, the label positions of that family's tier-A
pages predict where each label stands, and a damaged label token at the
predicted spot is accepted as the anchor.
*Gate:* label-not-found 22 → ≤ 8; contradictions ≤ 2; every bound fact carries
`value_boxes`.

### W5 — gate withdrawals (½ day; 18 cells, 11%)
The constrained decoder (`decode_pass`) as a fourth witness on gate-1 rows:
re-promote when it and one engine agree with the withdrawn value.
*Gate:* ≥ 9 of the 18 back with 0 contradictions.

### W6 — recognition (2 days; 13 cells, 8%)
Grammar-constrained ensemble decoding across the three engines' logits with
the per-locus IMGT alphabet (`CV_PLAN` phase 4); the printed Bw4/Bw6 tails
(D11, in flight) unblock 202 B cells corpus-wide on their own.
*Gate:* recognition 13 → ≤ 6; the 2 wrong values → 0.

### W7 — whole-page fields (1½ days)
ABO: a small classifier on the located field crop (A/B/AB/O × +/−), silver
labels from the 11,000 resolved printed groups, validated on the 96 gold; the 8
pages never read whole-page get W4 first. ROLE: the tick beside
`اهدا کننده` / `گیرنده` by the same ink measure that was right 74 of 76 times.
*Gate:* ABO misses 48 → ≤ 24 with 0 wrong; ROLE misses 16 → ≤ 8. Human:
HA-019's 20 readings arrive with round five; HA-024 decides the caption
groups on two-person pages.

### W8 — two-subject pages (human first)
5× over-represented among failures. HA-022 asks whether `fact` gains a subject;
until it is answered, W3(b)'s ownership gate keeps a value from being bound to
the wrong person, and `column_bind` binds only where one column is filled.

### W9 — measure, then export
Round five (600 unseen pages, on 8767) measures the nine sources no person has
checked. `checkpoint_attribution.py` runs after every item above. Then D2-a:
export tiers A/B/C, review and unknown separately.

## What each checkpoint needs from the operator

| checkpoint | decision |
|---|---|
| W2 | none — HA-011 (a) decided; (b) stays REVIEW for matching |
| W7 | HA-024 (caption groups on two-person pages); HA-019's 20 readings via round five |
| W8 | HA-022 (a second subject in the data model) |
| W9 | label round five; then the D2-a export shape is already decided |
