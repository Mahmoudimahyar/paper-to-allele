# Computer-vision research for the four reviewer failure modes (2026-09-05)

What the reviewer reported after the first 165 anchored labels, what a
six-lens research sweep with an adversarial skeptic per lens found, and what
was measured on this corpus before anything shipped. Every number below is a
count or a rate; no value, caption or crop of a real report appears here.

## 1. The four failure modes, and what the labels actually showed

`scripts/pack_score.py` over the reviewer's export (165 cells, 15 documents):
50 correct, 75 correct abstentions, 21 missed, 19 "contradicted".

| reported | measured |
|---|---|
| DRB3/4/5: "the system assigns the same number to DRB3, DRB4 and DRB5" and "writes DRB4 instead of 04" | The **labelling page** asked three per-gene "type two alleles" questions about one printed row. All 17 DRB3/4/5 "values" typed were 03/04/05 — the digit of a printed gene NAME; the pipeline's raw tokens on those rows were gene-shaped 14/14 and digit-shaped 0/14. 17 of the 19 contradictions were this protocol artefact. |
| Tilted photographs | Real corpus-wide (35% of the pack's pages rotate ≥0.5°, 9% ≥2°), but of the 21 misses only **1** sits on a page the rulings call tilted. |
| "OCR doesn't grasp the structure" | 9 of the 21 misses were the value's `*` not read at all (`A##`, `C##`, `DQB1##`); 3 more were a damaged prefix; 5 were an unrecognised label; 3 a header miss; 1 an empty cell. Corpus-wide, **3,153 cells** were refused only for the missing star — 45% of every shape refusal. |
| "boxes around each value form a table" | True: 13,793 documents carry a grouped DRB3/4/5 header on a ruled table; the rulings are the most precise thing on the page to measure tilt from, and they can certify an EMPTY cell. |

## 2. What the research settled (winner / why the skeptic left it / killed)

| failure mode | winner | evidence that survived | killed or deferred |
|---|---|---|---|
| tilt | rulings angle via `cv2.LineSegmentDetector` (9.4 ms/img, <0.01° on synthetic), corroborated by a Leptonica-style projection sweep; **rotate the geometry (stored boxes), not the pixels**; pixels only per crop on ROTATE pages | morphological long-kernel line extraction returns **0 segments at 7.3°** — a tilted ruling is not a horizontal run of pixels; the project's own detector keeps 80/80 boxes at 7.3° and 14°, so fixing row membership fixes the reported class | `straighten_pages=True` (double detection, integer angle), orientation classifiers (0.67 confidence on a clean page), DocAligner, UVDoc/DocScanner/DocTr (licence, ~1 s, no error certificate), sbrunner/deskew (scikit-image), jdeskew only as an experiment for unruled pages |
| rulings unused | an own OpenCV lattice from the LSD segments (rows, columns, cells, ink ratio) — the only option that certifies emptiness and gives every learned model its gate | zero dependency; camelot's lattice recipe and img2table's algorithm notes as references | img2table (prunes empty rows; contrib cv2), PaddleX RT-DETR (Paddle runtime measured 6 s/img here), LORE, TableFormer, TATR |
| DRB3/4/5 | one review question per printed row with per-gene answers derived; storage stays per gene (HLA_VALIDATION_SPEC §7); a bare number never binds a gene; DRB1 only ever generates a *review hint* | consistent with the constitution and OCR_SPEC §2; the "same number to three genes" defect was the page's question, not the pipeline | inferring a DRBX gene or first field from DRB1; template priors (circular); scoring the row as three fields |
| low-resolution crops | crop discipline (rotated ROI, glyph height 24–32 px, engine-specific pad/stretch, **ablated** before shipping), grammar-constrained decoding with an in-grammar/unconstrained margin on every CTC engine, a confirmer A/B (PP-OCRv6 small, RepSVTR ONNX, en_PP-OCRv4 mobile), Qwen3-VL-4B locally as a tie-breaker on the disputed set only (982 ms/crop, 0.997/0.910 measured 2026-09-03) | the primary recogniser loses 56 points on a 0.4% crop pad, so any crop change must be ablated; the margin exists because a tight grammar turns a misread into a plausible wrong answer | PARSeq as third voter (+0.9 pt), calibration/LTT (≈16 errors in 1,650 cells fit nothing), text super-resolution (hallucination), TrOCR, Florence-2, Granite-Docling, Moondream, HunyuanOCR (licence bars medical use), PaddleOCR-VL |

Cost envelope measured on this workstation (single process): JPEG decode + LSD
≈ 30 ms/img; projection sweep ≈ 30 ms; both ≈ 60–90 ms/img (12 img/s);
full-page `warpAffine` 48 ms; PP-OCRv5 en-mobile 13 ms/crop; Tesseract
8.3 ms/crop; `extract_facts` ≈ 1 min for the corpus. Anything ≥ 0.2 s/img is
gated to a subset; anything ≥ 0.5 s/crop to the disputed set, duty-cycled per
`docs/operations/WORKSTATION_STABILITY.md`.

## 3. What shipped, in the order the measurements justified

1. **The DRB3/4/5 row is one question** (`tools/hla_review.html`): tick the
   genes printed on the row; an allele only if one is printed beside a name;
   03/04/05 beside a gene is refused as the gene's own digit. Per-gene labels
   are derived; labels made under the old question render as "re-confirm".
2. **Declared partial reads score as `partial`** (`review/golden.py`): a single
   allele with `second_allele=UNREAD` inside the printed pair is an incomplete
   record, not a false acceptance. Without the declaration the KI-015 rule
   stands.
3. **The star the recognizer never read** (`ocr/glyphs.py`): `A02` parses with
   its prefix (marked repaired), `8*44` repairs the B/8 prefix confusion,
   `Cw` names C. Corpus: **+2,368** cells REVIEW→RESOLVED, 46 the other way
   (every one the KI-015 guard), 0 changed values; 5 of the reviewer's 21
   misses recovered, 0 contradictions.
4. **Page geometry from the rulings** (`ocr/rulings.py`, `scripts/geometry_pass.py`):
   STRAIGHT / ROTATE / UNCERTAIN per document, never rotating on one
   estimator. Calibrated on real photographs: a half-degree scatter bound
   refused 79 of 150 pages; at 1.5° with the sweep as guard, 53 ROTATE / 71
   STRAIGHT / 26 UNCERTAIN. Converging verticals (median 2.6° across a
   hand-held page) are a perspective flag, not a veto.
5. **The page frame** (`ocr/geometry.py`, `extract_facts.py --geometry`):
   stored boxes are levelled before the row rules run, provenance restored.
   Applied from 1.5° of tilt: under that the frame gained and lost 9 cells
   each on the pack; from 2° it gained 5 and lost 0.

## 4. The DRB3/4/5 row's measured grammar (E11)

Over the 13,793 documents with exactly one grouped header, the tokens on the
header's row band:

| shape | tokens |
|---|---:|
| gene name (`DRB3` / `DRB4` / `DRB5`) | 22,017 |
| gene pair in one box (`DRB3/4`) | 330 |
| bare first field (`01`, `02`, …) | 75 (on 48 documents) |
| single gene digit (`3`, `4`, `5`) | 45 |
| prefixed allele (`DRB4*01…`) | 16 |
| serotype (`DR51/52/53`) | 0 |
| other (letters / digits / punctuation) | 1,295 |

Rows: 9,664 print two tokens, 3,232 one, 562 none. Presence typing by name is
97% of what the row prints, which is why the review question is "which genes
are printed" and why a typed-slot grammar (bare number → review with candidate
genes; prefixed allele → presence plus a proposal) is a small follow-up rather
than the next step. It still needs the spec changes listed in HUMAN_ACTIONS
(HA-011) before it is built: the licence to read a gene name from token text
inside the grouped row lives in ADR 0008 and must be codified in OCR_SPEC §2.

## 5. Open experiments

| # | question | what settles it |
|---|---|---|
| E3 | ruled-table share and ruling detectability on phone photos | the corpus geometry pass's STRAIGHT/ROTATE/UNCERTAIN shares and `n_h/n_v` |
| E4 | perspective prevalence | `perspective_flag` counts (pack: 71/150 under the calibrated thresholds) |
| E6 | pad vs stretch vs rotate per engine | the crop ablation on the labelled cells |
| E8 | best light confirmer on HLA cells | A/B on the 600-crop survey set + golden |
| E9 | does polygon detection recover missed boxes? | `ocr_pass --mode polygons` on the gated residual |
| E13 | golden-set size for a pooled 99% claim | ≥1,650 gold-readable cells over ≥100 documents (expect 180–220) |

## 6. Do not do

Learned dewarpers or table transformers over the corpus; `straighten_pages`;
morphological long-kernel line extraction before deskew; any single angle
estimator applying a rotation without agreement; PaddleX RT-DETR / SLANeXt /
LORE / img2table; PARSeq, TrOCR, Florence-2, Granite-Docling, Moondream or
PaddleOCR-VL as confirmers; HunyuanOCR (licence prohibits medical use); text
super-resolution; calibration or LTT before the golden set holds ≥50 wrong
reads; word-lexicon-only CTC constraints (they complete low-resolution reads);
inferring a DRBX gene or first field from DRB1; emitting ABSENT from an empty
cell; scoring the DRB3/4/5 row as three fields; new dependencies without a
register row and `uv lock`.

## 7. What may leave the machine (amended 2026-09-05 by the project owner)

s6 read "any cloud OCR/VLM or sending an image off the machine" until the
operator lifted it. **Whole report pages may now be sent to the Google Cloud
Vision API**, using the key in the ignored `.env`, for the purpose of measuring
a second detector against the reviewer's labels.

The operator was given the narrow option — value crops only, a padded rectangle
around one allele, carrying no name, no laboratory, no date and no identifier —
and chose whole pages, because the evidence is only useful there: the largest
refusal bucket in the pipeline is **23,719 cells whose locus label was found and
whose value box was never detected**, and a crop cannot say whether a better
detector would have boxed it. A whole page carries the patient's name and the
laboratory's letterhead, and this decision accepts that.

What the amendment does NOT permit, and what still needs a further decision:

* no other cloud OCR or VLM service;
* no cloud call from any pass that writes a fact. A cloud reading is evidence
  about our detector, not a laboratory value, and the rule that OCR produces
  proposals rather than verification is untouched;
* no key in a document, a commit, a log line, a prompt or a memory file. It
  lives in `.env` and is read from the environment;
* nothing is sent that a person did not put in the sample: the pass takes an
  explicit document list and refuses to walk the corpus.

## 8. What Google Vision actually bought (measured 2026-09-05)

150 whole pages of the review pack were read with Cloud Vision
`DOCUMENT_TEXT_DETECTION` under the s7 permission, and `vision_compare.py` put
its boxes and ours through the SAME binding rule, scored by `review/golden.py`
against the reviewer's labels. DRB3/4/5 are excluded: the grouped row is read
by `ocr/drbx.py`, not by the rule under test.

**Tokenisation is not a detail; it was the whole first result.** Vision returns
WORDS, and it puts a word boundary at punctuation: `A*24` comes back as `A`,
`*`, `24`, and `HLA-A` as `HLA`, `-`, `A`. `canonical_locus_label` refuses a
bare `A` on purpose and `parse_allele_value` cannot read a bare `24`, so the
raw words scored **1 correct cell of 160**. Rejoining by measuring gaps is a
guess and reached 10: a threshold tight enough to keep two value columns apart
keeps `A` and `24` apart too. Vision already reports where its spaces are
(`detectedBreak`), and using that reached 28.

| boxes from | correct | partial | missed | contradicted | label anchored |
|---|---|---|---|---|---|
| our own detector | **62** | 2 | 19 | 3 | 138 of 160 |
| Vision, words as returned | 1 | 0 | 84 | 0 | 93 |
| Vision, gaps measured | 10 | 1 | 74 | 0 | 104 |
| Vision, its own break marks | 28 | 5 | 51 | 2 | 135 |

**Vision finds the printed label about as well as we do (135 against 138) and
converts far fewer of them into a value.** Cell by cell it is correct where we
are correct 27 times, and correct where we miss **once**. That one cell is the
entire recall it adds, against 33 it loses. Some of the gap is ours by
construction — the glyph repairs are calibrated on our recognizer's measured
confusions and do nothing for Vision's — but the conclusion for this form
family does not turn on the margin.

**The result worth having is about the largest refusal in the pipeline.**
23,719 cells are refused with "anchor found but no box at all in its cell":
we located the printed label and never detected a value beside it. That reads
like a detector failure and it is not. On 197 of those cells, drawn from pages
Vision has read, **Vision boxes something in the cell 1.0% of the time**. The
control says the test is sound: on 400 cells our pipeline resolved, Vision
boxes something 89.0% of the time.

So that bucket is paper. It agrees with `cell_ink_pass.py`, which measured
14,162 of 24,270 empty labelled cells as ink-free, and it means the bucket is
closed by **HA-012 and HA-009's per-laboratory NOT_TESTED policy**, not by a
better detector. Chasing detection there is work with nothing at the end of it.

**Decision: do not adopt Vision in the pipeline.** It is worse through our
rules, it adds a cloud dependency and a per-page cost, and it sends a patient's
whole report off the machine. `vision_pass.py` and `vision_compare.py` stay as
measuring instruments, run deliberately, writing no fact.

## 9. The reviewer's notes, and what they turned out to be

The review page carries an optional note per answer. Seven were written, and
they are the most useful diagnostic the project has received. Three of them
name one cause:

* "This image is tilted and the system failed to recognize that and all the
  boxes are situated incorrectly. The system must identify the lines and the
  slope of the lines and immediately identify that an image is tilted and draw
  its boxes for each loci with that slope."
* "This image is tilted and that caused the system to not recognize the correct
  alleles values for each HLA"
* "the pipeline failed to generate correct alleles for each loci, specifically
  it only recognized one of the two alleles"

The slope had been measured on every one of those pages and thrown away:

| note | rulings measured | what the pipeline did |
|---|---|---|
| tilted (LOW) | -3.05 deg | ROTATE applied, cells still wrong |
| tilted (HIGH) | -3.19 deg | UNCERTAIN: scatter 2.02 over `MAX_MAD_DEG` 1.5 |
| one of two alleles | -1.31 deg | ROTATE, then declined by `MIN_FRAME_TILT_DEG` |
| different structure | -1.70 deg | ROTATE applied |

`ocr/rows.py` and `ValueRule.row_slope` are the answer (see the commit and
`tests/unit/test_row_slope.py`): the row test now compares a box where its
printed row would have put it on a level page. 64 correct to 67 on the labels,
nothing lost, and both halves of the "one of two alleles" page recovered.

**"What if we give them the entire image?"** The reviewer's other note is that
every second opinion so far has been an opinion about OUR boxes: the confirmers
re-read the crop our detector drew, which can say nothing about a cell the
detector never boxed. `page_ocr_pass.py` runs PP-OCRv5-server detection AND
recognition over whole pages, locally, and `vision_compare.py`'s harness scores
it through the identical binding rule:

| boxes from | correct | missed | locus label found |
|---|---|---|---|
| our detector, flat rows | 64 | 17 | 138 |
| our detector, rows along the slope | 67 | 16 | 138 |
| Google Vision, whole page | 31 | 53 | 135 |
| PaddleOCR, whole page | 63 | 20 | **142** |

The whole-page read finds MORE printed locus labels than our own detector, and
the two disagree in both directions: it is right on 7 cells ours misses, ours
is right on 11 it misses, and at least one of them is right on 74 of 160. So
neither replaces the other and `page_ocr_bind.py` takes the union — our own
reading always stands, and the whole page is asked only about cells the
pipeline left unresolved, under every gate the resolver applies.

## 10. Reading the structure, in the order the reviewer set out

The last note was "this lab report has totally different structure. Instead of
writing the loci and then the alleles in front of it, it writes each allele in
the cell under the loci", and the method came with it:

> "first we need to know how much is the tilt of the image, in another word we
> need to know the slope. Then we need to find the loci names. Then we should
> detect the orientations of these loci names. Are they on the same row meaning
> if we draw a horizontal line with the same slope as other horizontal lines in
> the image, it can reach another loci name or we need to make the vertical
> line to achieve that? how about alleles, if we draw a horizontal line from
> the loci can we reach the respective alleles?"

`ocr/layout.py` is that, in that order. It needs one thing the geometry did not
have: rows and columns do NOT share a slope once boxes are normalised. A page
turned by theta prints rows at `tan(theta) * width / height` and columns at
`-tan(theta) * height / width`, which on a portrait page differ five-fold, so
`ocr/rows.py` now returns both and `ValueRule` carries both.

On the seven noted pages the reading is unanimous and correct:

| page | loci sharing a line | loci sharing a column | direction |
|---|---|---|---|
| the six ordinary forms | 0–3 | 6–36 | right |
| "totally different structure" | 3 | 0 | **below** |

That page then resolves. `BELOW_RULE` reads down the column, sheared by the
column lean; the printed cell ends where the next header begins, which is what
`_candidates` and `_value_beyond_the_chain` now honour, because rows on a
header form are evenly spaced and no distance cap separates a value from the
label of the row beneath it. HLA-A and HLA-B bind with both alleles each, from
the paired token the value grammar learned in s9. HLA-C abstains: its cell
holds three asterisks and nothing else, which is the right answer.

The direction is only ever read from the page, and `right` is what a page keeps
whenever the evidence does not clearly say otherwise — 149 of the 150 pack
pages. A form read the wrong way round binds one locus's value to another,
which is the failure this project exists to prevent.

## 11. Where the OCR still loses cells, and why most of it is not OCR

Six independent measurements over the local stores, each proposal then handed
to a separate skeptic told to break it. 29 proposals, 22 verified, and the
skeptics corrected the claimed sizes by between two and twenty times. Three
survived, all worth zero cells. The value of the exercise is the negative
result, so it is recorded rather than the proposals.

**Detection is not the constraint, and our detector is not the weak one.** Over
the 150 pack pages ours draws 12,646 boxes against PaddleOCR v5-server's 7,670
(medians 83 against 54). Of 56 (page, locus) anchors PaddleOCR or Vision find
and we do not, 54 already have one of our own boxes on the label; all 53 cells
their boxes resolve that ours do not are already RESOLVED in shipped facts. A
comparison run on boxes alone overstates the opportunity about fivefold, which
is a correction to how s8 and s9 framed it: the whole-page pass is worth having
for the layouts it reads, not for its detector.

**Recognition is 3.3% of the loss.** A better engine's reading is already
stored for 2,036 cells whose outcome it would change, which is real and is what
`rerecognise_pass.py` collects. It is also the ceiling, because **84.3% of
refused HLA cells — 115,153 of 136,596 — never got a box from any engine at
all.** Nothing that reads better can reach them.

**The two biggest refusals hold no box, so no re-read can ever touch them.**
Of 188,528 value-locus cells, 60,913 are RESOLVED and 86,688 refused. 61,999 of
those are "no anchor on this document" and 23,986 are "anchor found but no box
at all in its cell". **77% of the second bucket is measured blank paper**, whose
only remaining question is HA-012 and HA-009's per-laboratory NOT_TESTED policy.
That agrees with what Google Vision said in s8 from the other direction.

**Resolution is not the binding constraint.** The resolved-cell rate on
form-family pages is flat between 0.47 and 0.62 from under 500 px to over
1,300 px on the longest edge. Thumbnails are worth zero cells end to end. Page
upscaling has no size gradient to exploit. `quality_band` does not separate
outcomes and should not be used to route work. The one size signal that does
convert into lost cells is neither the page nor the glyph but the CROP: a value
box taller than about 1.6 times its own anchor row is lost 40-96% of the time —
a box the detector stretched across rows, not a small one.

**The grouped DRB3/4/5 row holds 60 of the 220 labelled cells**, not 40, and
scores 40 correct, 12 correct abstentions, 2 missed and 6 contradicted. Every
one of those 6 is a NOT_PRINTED label, so the row contributes six of the nine
contradictions and only two of the misses. Corpus-wide it leaves 30,459 cells
UNKNOWN, and the skeptics killed every proposal to widen the header grammar:
merging adjacent same-line boxes before matching gains 75 cells and de-resolves
more, and accepting a truncated header is refused by design.

**Two proposals did survive, and neither is an engine.** Both are cells the
pipeline threw away rather than misread, and both were reproduced independently
before being built:

* **the template places a label where the page prints no ruling.** 2,439 cells
  had a template fit inside `MAX_TEMPLATE_RESIDUAL` and were refused only for
  the absence of a printed line. The band now comes from the label's own height
  (`TEMPLATE_BAND_HEIGHTS`), which is safe on measurement rather than hope: the
  row pitch of these templates is a median 3.35-3.38 label heights, so a band
  of plus or minus 1.5 spans nine tenths of a row and two never touch, and the
  path runs only under the family rule where a value from a wrong row names
  another locus and gate 2 refuses it. What is refused outright is a placement
  the page's own grid contradicts — a ruling around the VALUE that excludes the
  label, 31 of 491 against 4 of the 1,698 the ruled path already binds.
  **+458 cells.**
* **a row that prints one gene twice discarded the second box.** `drbx.py` kept
  one box per gene, so on 4,115 rows the second was lost, and on 224 of them it
  carried the only S-for-5 repair — the token the re-read pass exists to settle.
  Every box is kept now, and two boxes count as two haplotype slots only when
  they stand apart along the row, because one printed token boxed twice would
  manufacture an absence. Rows reading one gene in two slots went from 12 to
  218.

**Everything else is still HA-012** (the NOT_TESTED policy, which decides the
largest bucket in the pipeline), **HA-014** (the nine contradictions) and
**HA-011**. The reviewer's next round of labels is worth more than any
recognizer.

## 12. A locus from the allele's own prefix (amended 2026-09-06 by the operator)

The reviewer, labelling round two, against a page whose loci all went unread:

> "This is a unique report, it doesn't specify the loci, but we still can find
> the info from the alleles name. For exmaple A*11 belong to HLA-A"

That qualifies a rule the project states outright — `AGENTS.md`: "Geometry/
template cell defines HLA locus; OCR text alone may not assign locus", and
`.claude/rules/ocr.md` says it again. The rule is not wrong and is not being
removed. It exists because a nearby WORD must never decide a gene: matching
`DRB1` inside a value inflated apparent DRB1 presence 5.18x and put the
locus wherever a patient's allele happened to sit (KI-010, ADR 0007).

What the operator has decided is that a **fully-qualified allele is not a
nearby word**. `A*11` states its own gene in the notation the laboratory
printed, and on a form that labels no rows it is the only thing that does.

`scripts/prefix_bind.py` implements it as the LAST thing tried and the weakest
evidence accepted:

* the locus must have no anchor anywhere on the page — geometry always gets
  first refusal, and this never overrules a printed label;
* the token must carry its own star (`B35` may be serology, `35` names nothing);
* the value must be admissible for the locus it claims, and one inadmissible
  claim taints the whole page;
* every box taken for one locus must sit on one printed row, followed at the
  page's own slope, because two rows are two people as easily as two alleles;
* **a comparison sheet is refused outright** — two patients on one page means a
  prefix cannot say whose value it is, which is the wrong-locus failure in its
  most dangerous form: the right gene of the wrong person. 3,535 cells refused
  on this ground alone;
* a box claimed by two loci withdraws both.

Measured: **4,767 cells** corpus-wide, and on the 561 human labels 308 correct
becomes 310 with **no new contradiction**. Every fact carries
`source='prefix-bound'` and a reason naming the prefix as the evidence, so the
whole group can be found and withdrawn if the decision is reversed.

HA-017 records that the sentence in `AGENTS.md` now has a documented exception
and should be reworded by a person rather than by an agent.

## 12-b. A comparison sheet with ONE filled column (amended 2026-09-06)

s12 above says "**a comparison sheet is refused outright**". This amends that,
narrowly, and the amendment is recorded here because s12 is the operator's own
decision and an agent may not quietly reverse one.

**The operator's instruction, this session:** all eight segments of the s18
loss are to be resolved. Comparison sheets are segment 2, and the refusal above
is what makes them a segment: 450 pages, 0 cells, on one laboratory template.

**What the pages actually are.** Family `None` on all 450. An identity block,
then a header row `Recipient | Frequency | Donor | Frequency` — Recipient LEFT
on 445 of 449 pages — then allele rows printed one locus per box with NO row
labels at all (0 locus anchors on 427 of 450). On **419 of 450, only ONE column
holds fully-qualified alleles**. Such a page prints two headings and describes
ONE person. The heading above the filled column is the only thing on the page
that says which.

**The amendment, and the condition on it.** A comparison sheet may be bound
when, and only when, the **subject-agreement gate** holds:

> exactly one column holds fully-qualified values, the other column holds
> nothing a person could have typed, and the document's own independent ROLE
> fact is RESOLVED and names the same subject as the heading above the filled
> column.

The locus still comes from the value's printed prefix, exactly as s12 allows,
and still only where the page anchors no label for it. What is NEW is that
geometry now decides the PERSON as well: which column, plus the row-order and
alignment constraints of the template. `scripts/column_bind.py` implements it
with `source='column-bound'`, so the whole group is withdrawable — and each
fact records in `rule_id` which ROLE source gated it, because that gate is 54%
caption claims (150 of 276 binds) and 30% bare role words (84), against 15% on
a strong printed field (42), so the weakest tier can be withdrawn on its own.

**Everything the amendment does NOT permit.** A page with values under both
headings, a third role word on the header row, a box reaching both columns, or
a second column holding anything typed at all, is refused to `REVIEW_REQUIRED`
with the tokens and the filled heading boxed (`source='column-bind-refused'`):
40 pages, which the reviewer previously saw as three.

**Those 40 are two groups, and they are not the same claim.** 15 pages / 26
cells are refused because the PAGE prints two subjects, and only those carry
"this page prints donor and recipient columns for two subjects"
(`rule_id='column/two-subjects'`). The other 25 pages / 53 cells are refused
because the column that should be empty is not blank, and what is in it is a
date, a frequency or an 11-digit identifier rather than anything shaped like a
typing: they carry a reason that says exactly that, under
`rule_id='column/other-column-unread'`, and `review_pack` samples them as their
own stratum. The emptiness predicate is deliberately wider than the parser — it
has to be, or five of twelve real two-people pages bind — so it also catches
the form's own printing, and writing a two-subject claim over a reference
number would put a false statement about a patient's record into the medical
review queue.

A page whose geometry is clean but whose ROLE fact is missing is NEVER resolved
— it is named for review only (`source='column-named+role-unconfirmed'`, 50
pages / 108 cells), and the reason deliberately does not say which role,
because the review page prints the reason beside the Role question the reviewer
is meant to answer independently. That reason also states how many printed rows
on the page got no crop at all because the second allele is printed without its
own star (89 rows on 77 pages corpus-wide); `parse_allele_values` will not
guess between a pair and one two-field value, so those rows are not proposals.

**Why the gate is the condition and not a detail.** Sliding every token under
the OTHER heading, with the gate off, binds 333 pages and names the wrong
person on 272 of them. With it on, on the shipped code: 276 of 276 bound pages
refuse the slide, and 276 of 276 refuse a MIRROR of their own filled column
into the vacant one. It is the whole wrong-person defence, and the residual it
does not cover is stated in the pass's docstring — pixels cannot certify a
column blank, so a second column no engine boxed at all is gated by the ROLE
fact alone.

**Worth, measured from the shipped code by `--dry-run` against the live stores
with every connection forced read-only:** 276 pages / 699 cells (A 219,
DRB1 216, DQB1 146, B 118); 50 pages / 108 cells named; 40 pages / 79 cells
into review; 84 refused outright; 276 + 50 + 40 + 84 = 450. Applied to a copy
of `facts.sqlite`: 699 rows written, all RESOLVED, every one of them UNKNOWN
"no anchor on this document" beforehand, and 0 already-RESOLVED cells changed
anywhere. On the four label exports (1,287 cells scored, 774 judged): 616 to
618 correct, 121 to 119 missed, 18 to 18 contradicted, nothing lost.

**The B row, stated exactly.** B binds at all only because `glyphs.py` now
reads the `Bw4,Bw6` epitope tail this template prints after the B pair. That
parser change alone newly reads **279 tokens on 279 pages** (270 `B*`, 3 `8*`,
6 other spellings; 180 of them comparison sheets, 99 not) and changes **ZERO
mainline cells on every locus** — there is no B anchor on any of those pages,
so the ordinary resolver never sees them. Its own yield is **+97 B cells
through `scripts/prefix_bind.py`** (`--dry-run`, read-only, against the live
stores), all on non-sheet pages, all two-valued, and 0 on comparison sheets —
the 3,535 sheet cells stay behind the guard. No human label covers any of the
97. The "+1 correct" belongs to `column_bind`, not to the parser.

**That acceptance evidence has now been produced.** A full corpus extraction
with the parser was compared by `refresh_facts.compare` against a full corpus
extraction with the pre-branch `glyphs.py`, both written to scratch databases
from the same read-only sources:

    A     13,306 -> 13,306      DQB1  13,024 -> 13,024
    B     13,136 -> 13,136      DRB1  12,912 -> 12,912
    C      3,998 ->  3,998      DRB3  11,323 -> 11,323
    DPA1      29 ->     29      DRB4   9,550 ->  9,550
    DPB1      32 ->     32      DRB5  10,815 -> 10,815
    DQA1     839 ->    839
    0 second alleles gained, 0 dropped, 0 SWAPPED, no status transition at all

0 RESOLVED deltas on every one of the eleven loci, which is what was owed.

`prefix_bind.py` was hardened before that landed: its comparison-sheet guard
returned an empty set on a query error — indistinguishable from a corpus with
no sheets in it, and 180 two-role pages' B rows now sit behind it — and its
star-less same-locus token was skipped past rather than tainting the page,
which hid it from `MAX_VALUES`. Both are `tests/contracts/test_prefix_binding.py`.

**Counting is the default.** `python scripts/column_bind.py` with no argument
does not write: this pass reverses a recorded operator decision on 450 pages of
real patient facts, so the write is `--write`, asked for by name. That differs
from `prefix_bind.py` and `anchor_row_bind.py` deliberately.

**Pass order.** `column_bind.py` runs AFTER `prefix_bind` and
`anchor_row_bind`, and after any pass that writes ROLE (`caption_pass`,
`role_repass`): it re-checks every `column-bound` fact against the current ROLE
fact at the head of each run and withdraws the ones that no longer agree, so
re-running it in order is the repair when a later pass changes a role.

HA-017 now carries the second exception as well as the first.

## s13 — the whole-page fields, and two strata that were silently empty

The reviewer, on where the rest of the answer lives:

> "I also want you to add the group text that the user sent along this picture.
> Because we have the entire chat history and we can easily see what they have
> sent with the image of their report. ... Usually the role and the blood type
> will be present in the chat. In addition a person can send the image multiple
> time each with different text so I want you to show all those texts"

That is right, and it is the largest gain this project has had from a source
that is not the photograph. `scripts/caption_pass.py` reads ABO, Rh and Role
from every message a document was ever posted with, not only the first.
Measured on the live database, 23,566 documents:

| field | resolved before | resolved now  | from a caption |
|-------|-----------------|---------------|----------------|
| ABO   | 2,993 (12.7%)   | 10,049 (42.6%)| 7,054          |
| RH    | 2,993 (12.7%)   |  8,850 (37.6%)| 5,855          |
| ROLE  | 7,517 (31.9%)   | 15,884 (67.4%)| 10,858         |

Role's caption count exceeds its gain because a caption often CONFIRMS what the
form already printed; those carry `source='FORM_FIELD+CAPTION'`.

The pack's message caps were raised from 8 postings to 60 and from 600
characters to 1,500 to match: 2,406 documents carry more than eight postings,
and the truncated tail is exactly where a repost adds the blood group the form
never printed. On the round-three pack, 24 of 60 documents were posted more than
once and one thread holds 75 postings.

A caption is a person's claim, not a laboratory result, and the page now says so
on all three fields rather than on Role alone. In that pack 14 of 25 resolved
ABO values came from a caption against 9 from the printed form, and a reviewer
weighing "is this right" cannot do it without knowing which.

### Two strata reported empty when they were not

Building the round-three pack, `odd_box` — the reviewer's own box-size signal —
and `blank_paper` both drew **zero** documents. Neither was empty.

**`blank_paper` asked for the wrong column.** `cell_ink` names it `decision`;
the query asked for `verdict`, and a blanket `except sqlite3.OperationalError`
— written to tolerate a facts database from before the ink pass existed —
reported the whole stratum as absent instead of raising. 14,210 measured-blank
cells across 63 qualifying pages were unreachable that way, and HA-012, which
asks whether a blank printed cell means the laboratory did not test that locus,
is the largest open question in the project. The table's presence is now checked
explicitly, so a wrong column is heard instead of swallowed.

**`odd_box` was eaten by a commoner stratum.** A document was pooled under
`doc.tags[0]`, and `tag_document` returns tags in the order `STRATA` is
*written* — an order that had drifted from how rare the strata actually are.
`odd_box` holds 22 documents corpus-wide and sat below `repaired_glyph`, which
holds 11,179, so every odd box was pooled as a repaired glyph. Documents are now
assigned to their rarest stratum **as measured on the corpus being packed**,
with the written order breaking ties only, so a pack stays reproducible for a
seed.

Corpus-wide, the strata are spread over four orders of magnitude — `whole_page`
17 documents, `repaired_glyph` 11,179 — which is why written order could not
stand in for rarity and why it must not be trusted to again.

Neither defect failed loudly, and that is the part worth keeping: a stratum
reporting zero looks exactly like a signal that does not occur, and the pack is
the instrument the whole project steers by. Corpus-wide counts per stratum are
cheap; read them whenever a stratum is added.

The same seed, before and after:

    before: 26 strata drawn, 3 empty, largest stratum 7 of 60 documents
    after:  26 strata drawn, 0 empty, largest stratum 5 of 60 documents

## s14 — the reviewer's notes are where the loss is, and one pass built from them

Scored against live facts, the 561 labels give 310 correct, 205 abstained, 35
missed, 2 partial, 9 contradicted — 87.1% of the 356 cells a person actually
read. The reviewer wrote a note on **14 pages**. Those 14 hold **26 of the 35
misses and 5 of the 9 contradictions**. Fourteen pages out of 561 labelled
cells hold three quarters of the loss, and the reviewer named the cause on each
one. Nothing else in this project has that hit rate.

What the notes name, and what was found on inspecting each page:

| the note | what is actually wrong |
|---|---|
| "instead of HLA-A we just have A" (twice) | no engine produces an `A`/`B`/`C` box at all — not the bare-label rule refusing |
| "doesn't specify the loci ... A*11 belongs to HLA-A" | `prefix_bind` refuses: A/B/C DO have anchors here, so the gate stands down |
| "no tables and only ABC loci" | no anchors from any engine |
| "just says A*01, *33" | HA-015, the star-less continuation |
| "each allele in the cell under the loci" | column layout |
| tilted (three notes) | four of the nine contradictions sit on one tilted page |

The two "bare A" pages were the surprise. `_bare_class_i_column` was built for
exactly them, and it is not the thing refusing: on one, our detector drew 86
boxes on a full report and produced **zero** `A`, `B` or `C` tokens, garbling
the table region while reading the letterhead cleanly. The whole-page engine
does no better — across the seven worst annotated pages it finds FEWER boxes
than ours (43 against 86, 39 against 144) and recovers two anchors in total.
That is s11's finding reached from a third direction: these pages are not lost
to a binding rule, they are lost before any rule runs.

### `anchor_row_bind.py`, and what it is worth

One note did point at something fixable. "anchor found but no box at all in its
cell under this rule" is the second largest refusal in the corpus — 23,986
cells over 14,701 pages. On some of those the label WAS read, so the row is
known, and the value is sitting on that row; what failed was the cell rectangle,
not the reading.

The pass binds only when two independent signals agree: the **row** from the
printed anchor (geometry, as the project requires) and the **locus** from the
value's own printed prefix (nomenclature, the s12 decision).

### The first version was wrong, and an adversarial review is what caught it

The first version bound **458 cells**, and the argument above was the whole
safety case for it. A skeptical multi-agent review (31 agents, every claimed
defect independently refuted before being kept) confirmed **eleven** defects.
Two of them destroyed the argument:

**"On the anchor's row" was a stripe across the whole page.** There was no
distance cap and no direction. Measured on that version's own binds: the gap
from the label reached 69 anchor heights, **87% of bound boxes sat past the
`max_gap=20` that `DEFAULT_RULE` enforces on the very same pages**, and twelve
boxes were to the LEFT of their own label, which no rule in this pipeline
reads. `_candidates` states the reason the cap exists: a gap wide enough to
reach a second allele from the anchor is wide enough to reach the next column,
"which is exactly how a value gets bound to the wrong locus."

**It published the case the project reserves for a human.** Two loci on one
printed band is a normal layout. With `HLA-A`'s cell blank and `A*24` sitting
inside `HLA-B`'s printed cell, `resolve_locus` refuses that box — "value names
A but the anchor is B; geometry and text disagree" — because when geometry and
text disagree, neither wins. The first version resolved it. A matching prefix
does not establish which cell a box came from, and the claim that "geometry
supplies the row" was never checked against ownership.

Also confirmed: a star-less token (`A24` parses WITH a prefix) was skipped
rather than tainting the row, hiding it from `MAX_VALUES` so a row of three
tokens could bind two; the comparison-sheet guard — the only thing between the
pass and the right gene of the WRONG PERSON — returned an empty set on a query
error, failing open; the two-loci exclusivity check was provably unreachable
dead code that looked like a safety gate; and the OCR connection was never
closed.

The 458 writes were **reverted from the database**, not amended in place.

### What survives

With the gates the mainline actually enforces — right of the label, within
`MAX_GAP` measured from the previous cell in the chain, not owned by a nearer
label, star-less tokens tainting the row, the sheet guard failing closed —
the pass binds **80 cells**: A 19, B 21, C 8, DRB1 24, DQB1 8.

**83% of what the first version wrote does not survive this project's own
rules.** That is the measurement worth keeping, and it is an argument for
reviewing a rule adversarially before its output is believed, not after.

**Accuracy is still unmeasured.** The 561 labels score identically before and
after: 310 correct, 9 contradicted. None of the 80 cells is labelled. A stratum
(`anchor_row`) now draws from it so the next round can settle it.

### A provenance defect in both passes

The same review found that neither pass wrote `value_boxes`, `anchor_box` or
`raw`. All **4,767** prefix-bound facts therefore had no boxes at all, so
`review_pack.cell_crop_box` returned `None` and the review page showed a
RESOLVED medical value **with no pixels behind it** — the identical defect that
made 50 of round one's 220 answers unusable. Both passes now record the boxes
they read from; the 4,767 were reset and rebound to backfill them.

`prefix_bind.py` had also shipped with no tests, which for an OCR acceptance
rule is against this repository's own test-first requirement.
`tests/contracts/test_prefix_binding.py` now covers both — 23 cases, each
naming a way a pass could assert something untrue, seven of them reproducing a
probe from the review.

## s15 — the role words the form prints, and a question the review page asked badly

The operator:

> "whenever you see something like اهدا کننده this means donner and whenever
> you see گیرنده or any other variations you should extract that the role is
> reciever. So do not miss these obvious evidence."

They were being missed, and measurement says where. Of 7,682 documents with no
role, **5,096** have Persian OCR with boxes, and of those:

| | documents |
|---|---|
| exactly ONE role word printed, role still unresolved | **2,400** |
| no role word in the Persian OCR | 2,594 |
| both role words printed (ambiguous by design) | 102 |

The 2,400 were all Tier C — a role word with no `نسبت:` field label beside it
and no other form word on its row. Only **4** of those pages print a `نسبت`
label anywhere, so this is not an anchor window set too tight; the forms really
do print the word bare.

### Why the refusal was wrong

`decide_document_role` refused Tier C alone, on a real measurement: the weakest
tier contradicts recipient-only serology 20% of the time against 0% for the
anchored tiers. That number stands. But the contradiction it names has **its own
gate two branches earlier** in the same function, and so does a caption naming
the other role, and so does a page printing both words. By the time control
reached the Tier-C branch, every failure the 20% described had already been
excluded. Refusing there charged the same evidence a second time.

Against the reviewer's **50 labelled roles**, a bare word agrees with the human
**13 times and disagrees once**.

So a bare word now resolves, under its own source `FORM_FIELD_BARE`, with every
contradiction gate unchanged ahead of it. `scripts/role_repass.py` applies the
decision to the extracted corpus rather than a full refresh.

**ROLE: 67.4% → 78.1%** of 23,566 documents (15,884 → 18,404). By source:
CAPTION_CLAIM 8,458, FORM_FIELD 5,029, FORM_FIELD+CAPTION 2,527,
FORM_FIELD_BARE 2,390. A `bare_role` stratum draws from the last group so the
next round settles its rate.

### The caption spellings

Separately, 1,416 unresolved documents carry a role word in their chat text.
Classified: 588 name BOTH roles, 549 ask for a role rather than state one (both
correctly refused), and **179** name one role in a spelling the reader did not
know — the ezafe `ی` in `اهدای کننده`, the hamza in `اهداء کننده`, and `دهنده`
standing alone rather than only before `کلیه`. Those are now read.

`اهدا کلیه` — "kidney donation" — is deliberately NOT read as a role. It names
an activity, not a person, and rides in the group's own boilerplate; 93
documents carry it.

### A question the review page was asking badly

Scoring the whole-page fields against the 50 human answers turned up something
that is not a pipeline error at all:

| field | source | correct | disagreeing |
|---|---|---|---|
| ABO | LABORATORY_PRINTED | 6 | 0 |
| ABO | CAPTION_CLAIM | 4 | 13 |
| RH | CAPTION_CLAIM | 4 | 10 |
| ROLE | CAPTION_CLAIM | 16 | 6 |

**Every single one of those disagreements is against a human answer of
`NOT_PRINTED`, `UNREADABLE` or `UNKNOWN`.** Not one is a different blood group
or the opposite role. The reviewer was answering "what does this page print?" —
correctly — and the pipeline was answering "what is this person's group?" from
the chat. Two different questions, and the page did not say which it was
asking.

That is an instrument defect, and it means the caption-derived ABO and Rh from
s13 are **unvalidated, not disproven**: the labels cannot speak to them. The
page now says so on any caption-sourced value. Whether a chat-stated group
should be recorded as a fact about the person, separately from what the form
prints, is a question for the operator and not for a pass.

The one genuine role contradiction in the whole set is a single
`FORM_FIELD_BARE` DONOR the reviewer read as RECIPIENT.

## s16 — 957 labels: where the accuracy actually is, and one value the pipeline was throwing away

Three rounds of review now give **957 HLA cell labels** and **86 whole-page
answers**. Scored against live facts:

| HLA cells | |
|---|---|
| correct | 511 |
| correctly abstained | 365 |
| missed | 59 |
| partial | 11 |
| contradicted | 11 |

**86.3% correct on the 592 cells a person actually read.**

| whole-page field | correct | wrong | missed | precision |
|---|---|---|---|---|
| ROLE | 67 | 1 | 9 | 98.5% |
| ABO | 34 | 0 | 29 | 100% |
| RH | 34 | 0 | 29 | 100% |

The single role error is a `FORM_FIELD_BARE` donor the reviewer read as
recipient — the s15 rule running 8 correct to 1 wrong.

**s15's worry about caption blood groups is resolved, and it was unfounded.**
With the third round's labels, caption-derived ABO is **14 correct and 0
contradictions**. The earlier "13 wrong" were every one against `NOT_PRINTED`:
the question mismatch, exactly as diagnosed. Those values are validated now,
not merely unrefuted.

### Precision is not the problem; recall is

Nothing in the whole-page fields is wrong. ABO and Rh simply abstain on more
than half the documents a person can read, and — measured — **the Rh misses are
exactly the same documents as the ABO misses**, so ABO recall is one lever that
moves both fields.

### One printed value, detected twice

`read_abo` refused any cell holding more than one parsing box. 1,113 documents
reach that branch, and **996 of them are ONE printed token that both engines
boxed**: the Latin pass (onnxtr) and the Persian pass (easyocr) each drew a
rectangle around the same ink, and the two readings agree. Refusing them cost
993 documents a blood group and 760 an Rh for no safety whatsoever.

`_one_token_read_twice` collapses that case behind three gates. Measured on the
1,113, gate 1 does all the work and the others are insurance:

| gate | rejects |
|---|---|
| the parsed values must be identical | 117 |
| the boxes must overlap (IoU ≥ 0.5) — same ink, not two agreeing values | 1 |
| the boxes must come from two different engines | 0 |

Same-ink cross-engine disagreement runs at 10.5% (9.1% sign-only, 1.4% letter),
and gate 1 catches all of it — including every sign disagreement, which is the
dangerous one: an `A-` read as `A+` puts a Rh-negative recipient in a positive
pool.

**A/B over all 23,566 documents, gate on against gate off: 993 gained, 0 lost,
0 values changed on a document already resolved.** Conditional on the gates:

| independent check | result |
|---|---|
| 282 chat claims | 0 letter contradictions, 0 sign |
| the reviewer's own answers | 6 of 6 |
| PP-OCRv5, whole page | 14 of 14 agree |
| PP-OCRv6, on our boxes | 14 of 14 agree |
| **control — what already ships** | **10 letter errors in 1,003 (1.0%)** |

So the collapsed readings are measurably no worse than readings the pipeline
already trusts. The 95% upper bound is 1.06%, not zero, which is why the 117
genuinely different cells still go to a person and why every fact records BOTH
boxes it agreed on.

Applied: **ABO 42.6% → 45.6%, RH 37.6% → 40.7%.** On the reviewer's answers,
ABO and Rh each go from 29 correct to **34 correct, still 0 wrong**.

### What an adversarial workflow refused to let through

Five investigators produced 28 proposals; independent verifiers, each told to
refute by default and to measure rather than read, **rejected all 28**. That is
the point of the exercise, and three of the rejections are worth keeping:

* **anchoring the blood group on a bare `Blood` box** would gain 5 values and
  create 2,425 new review items — 485 review items per value. 69.5% of those
  boxes are the specimen line ("Whole Blood", "Peripheral Blood"); the cell it
  opens is the SPECIMEN cell. Measured dead in all three reading directions.
* **repairing a value's prefix toward the anchored locus** claimed +275 cells;
  re-measured, **+16**, because 288 of the 304 are already resolved by passes
  that read pixels rather than guessing glyphs.
* **the sideways-page flag** claimed 611 documents / 4,888 cells; the flag
  itself yields **0 new values**, since all 4,888 are already UNKNOWN. The
  diagnosis survived, though, and independently: flagged pages have median
  vertical-ruling share 0.784 against the corpus's 0.240, and median box aspect
  2.25 against 0.39 — a 90° rotation predicts exactly that swap. **611
  documents in this archive are photographed sideways**, and re-reading them
  upright is real work with a real yield, which is not the same as the flag.

The 993 that survived did so because its mechanism was attacked with
constructed counterexamples and placebo controls and did not break; its
rejection was for two misstated yield figures and a provenance defect, all
three of which are fixed here.

## s17 — 611 pages were photographed sideways

The misses and the refusals are not the same population, and s11 answered only
one of them. Root-causing all 59 missed cells against the 957 labels:

| class | cells | share |
|---|---|---|
| the locus label was never anchored | 29 | 49.2% |
| a box parsed, and a gate refused it | 13 | 22.0% |
| no box in the cell at all | 11 | 18.6% |
| a box was there and did not parse | 6 | 10.2% |

**43 of the 59 missed cells have a human value to find, and 38 of those (88.4%)
have its digits somewhere in the stored OCR — 29 (67.4%) as a box that parses
as an allele with the right first field. Only 5 are absent from both engines.**

s11 measured that 84.3% of all REFUSED cells are blank paper, and that is still
true. But the missed population is the opposite: **the refusals are blank
paper; the misses are read-but-unbound.** Different problem, opposite fix, and
chasing recognition would have addressed neither.

### The largest single population: pages that are not upright

A metric already sitting in `ocr_pass.sqlite` finds them for nothing — the
fraction of detected boxes whose PIXEL height exceeds their pixel width. That
qualifier is the whole measurement: the stored geometry is normalised to 0-1,
so comparing normalised height with normalised width compares a fraction of the
page's height with a fraction of its width and means nothing.

`tallfrac >= 0.6` over the 23,357 documents with at least 8 boxes selects
**611**, and the distribution is bimodal rather than a judgement call: 592 are
above 0.8, and moving the threshold to 0.5 or 0.7 gives 621 or 599.

The separation is total. **0 of the 611 carry a single named locus anchor**,
against 83.9% of the corpus, and all 4,888 of their locus cells are UNKNOWN
with reason "no anchor on this document". Nothing on these pages was trusted,
so nothing could be disturbed.

Three independent measurements confirm they are ROTATED rather than merely
unreadable — only the first of those is fixable:

| | flagged | corpus |
|---|---|---|
| vertical-ruling share (median) | 0.784 | 0.240 |
| vertical-dominant, of ruled pages | 87.7% | 6.4% |
| box aspect, pixel height/width (median) | 2.25 | 0.39 |

A quarter turn predicts exactly that transposition (1/0.39 = 2.56).

### What it was worth

`upright_pass.py` reads each of the 611 at all four rotations and keeps one
**only when it beats every other outright on named locus anchors**. A tie, or
zero anchors everywhere, writes nothing: binding a locus from a wrongly turned
page reads every value against the wrong row, which is the worst failure this
change could produce.

    611 read     425 found an upright rotation (70%)
                 186 yield no anchor at any rotation and stay unreadable
    rotations    284 at 270 degrees, 141 at 90, and NONE at 180

The absent 180° is the sanity check: an upside-down page still prints wide
boxes, so it is never flagged, and none was.

`upright_bind.py` then binds with the generic rule and **no stored geometry at
all** — the frame, the template family and the row slope were every one
measured on the sideways image, and rectifying an upright reading with a
sideways frame places every cell wrong.

**801 cells resolved** (DQB1 191, A 175, DRB1 170, B 165, C 75, DQA1 23, DPA1
and DPB1 1 each) on pages that had zero. The 957 labels are unchanged — 511
correct, 11 contradicted — because none of the 801 is labelled, which is
exactly why an `upright` stratum now draws from them.

Note what the honest number is NOT. The reason strings on those pages cover
4,888 cells, and quoting that as the yield would overstate it 6x: most cells on
these forms hold nothing to recover. On the one flagged page a human has
labelled, the reviewer found a value in 2 of 11 cells.

### The precision question this leaves for a person

All 11 contradictions on the 957 labels concentrate hard. Splitting the 261
labelled DRB3/4/5 cells by whether the grouped header is cleanly spelled or
only reachable through the damage-tolerant regex:

| stratum | cells | correct | contradicted |
|---|---|---|---|
| clean header + add-on source | 37 | 37 | 0 |
| **damaged header + add-on source** | **20** | 15 | **5 (25%)** |
| damaged header + core rule | 40 | 30 | 1 (2.5%) |
| clean header + core rule | 119 | 112 | 0 |

**Every add-on contradiction lives in one stratum**, at 25% against a 1.4%
baseline for the core row rule. Corpus-wide the two add-on sources
(`drbx-reread+ppocrv6`, `ink-certified`) hold 8,799 cells on 3,737 documents;
gating them on a cleanly spelled header keeps 7,338 and sends **1,461 to
review** — extrapolating the stratum's own rate, roughly 365 wrong values
withdrawn at the cost of roughly 1,096 correct ones deferred to a person.

That removes 45% of every contradiction the pipeline has, at three correct
readings per wrong one. `PRODUCT_CONSTITUTION` says ambiguous critical OCR goes
to review rather than being best-guessed, and 25% is ambiguous by any reading —
but a 3:1 trade is a judgement about how this archive will be used, not a
measurement. It is recorded here for the operator and NOT applied.

## s18 — 1,342 labels: the honest accuracy, and the loss segmented

The reviewer, after round four: "You've claimed that you have more than 90%
accuracy. However these new annotations didn't reflect that."

They were right about the emphasis. The number led with was PRECISION — of what
the pipeline asserted, how much was right — and that holds on every round. The
number a reviewer experiences is how often the pipeline HAD the answer, and on
blood group it does not have it more often than it does. Both are reported here
and the second is put first.

Four rounds, **1,342 HLA cell labels** and **120 whole-page answers**, scored
against live facts. Round four was drawn deliberately from the strata the
pipeline is least sure of.

### HLA cells

| | all four rounds | round four alone |
|---|---|---|
| correct | 692 | 181 |
| correctly abstained | 529 | 164 |
| missed | 88 | 29 |
| partial | 19 | 8 |
| **wrong** | **14** | **3** |
| **recall on cells a person read** | **85.1%** | **81.9%** |
| **precision of what was asserted** | **98.0%** | **98.4%** |

Per round: 90.3% / 85.1% / 85.2% / 81.9% recall, with 9 / 0 / 2 / 3 wrong. Recall
falls as the rounds get harder; precision RISES. The pipeline abstains more on
hard pages, and it is right when it speaks.

### Whole-page fields

| field | correct | wrong | **missed** | precision | **recall** |
|---|---|---|---|---|---|
| ROLE | 92 | 2 | 17 | 97.9% | 84.4% |
| ABO | 46 | 0 | **50** | 100% | **47.9%** |
| RH | 45 | 0 | **51** | 100% | **46.9%** |

On round four alone ABO recall is **36%** (12 of 33) and Rh **33%**. That is
the number the reviewer felt, and it is the right number to feel.

### The loss, segmented

**Where the 88 HLA misses are.** Three strata run at exactly zero: comparison
sheets (13 read, 0 correct), pages that anchored no label (18, 0) and pages
that anchored labels and refused every cell (7, 0). Pages with **no template
family run at 64.1%** (32 misses on 103 read) against 87.6% for FORM#0.

By stored reason: no anchor 28, no grouped DRB3/4/5 header 12, too many
candidates 8, second gene column unread 8, candidate does not parse 7, header
with no gene token 6, no box in the cell 4, S-read-as-5 3, inadmissible family
3, owned by another locus 3, beyond the chain 2, three anchors 1.

The 28 "no anchor" misses, by page: **10 on comparison sheets** (0 anchors, 2-4
allele tokens each — the page prints alleles and no labels), **10 on pages with
no template family**, 5 on FORM#0 pages that DID anchor 4-6 labels (so the
anchor exists and the cell rule fails), 2 on a sideways page that turned
upright but still bound nothing, and 3 on a page with no allele tokens at all.

**The 19 partials are all declared.** Every one carries `second_allele=UNREAD`:
11 from the two-engine re-read, 5 from prefix binding, 3 from anchor-row. The
pipeline said it read one allele. It did not silently drop the second.

**The 14 wrong values, and the one segment that holds them.** 6 are DRB3/4/5
presence calls (4 from the two add-on sources, s17's stratum). The other 8 are
allele values, and **7 of the 8 went through glyph repair**. Splitting every
resolved value cell by repair and stability:

| segment | labelled | wrong | error | corpus cells |
|---|---|---|---|---|
| clean / UNANIMOUS | 260 | 1 | **0.4%** | 44,066 |
| repaired / UNANIMOUS | 79 | 2 | 2.5% | 9,655 |
| repaired / NOT_CHECKED | 44 | 0 | 0.0% | 8,771 |
| clean / SPLIT | 21 | 0 | 0.0% | 2,034 |
| **repaired / SPLIT** | **19** | **4** | **21.1%** | **1,467** |
| repaired / DIGITS_LOST | 19 | 1 | 5.3% | 671 |

A value that needed a glyph repair AND whose reading changes under one-pixel
jitter is wrong one time in five. It holds 4 of the 8 allele contradictions on
1,467 corpus cells, against a trustworthy core of 44,066 cells at 0.4%. The
gate is obvious and it is not applied here, because 15 correct readings would
go to review for every 4 wrong ones withdrawn — the same 3:1 trade as s17, and
the same decision for the operator.

**Where the 50 ABO misses are.** By stored reason: no label 29, label found but
cell unreadable 18, sign without letter 2, doubled 1. By what the page holds:

| the page | misses |
|---|---|
| a strict label IS present; the cell rule fails | **21** |
| the label is there in a spelling the reader misses | 9 |
| no label anywhere, but a group-shaped token exists | 7 |
| no Persian OCR ran on this page, no Latin label | 6 |
| no label in either script, no group token | 6 |
| the page is sideways | 1 |

And inside the 21 where the label was found: 7 pages carry NO group-shaped
token at all (the reviewer read a value the recognizer never produced), 4 carry
only a bare letter with no Rh sign, **3 have the value on the wrong side of
the label**, 4 have it beyond `_MAX_GAP` (12h, 22h, 23h), 2 have it inside the
gap with zero vertical overlap, 1 was refused as doubled. The nearest token
sits at median 5 anchor heights but with median vertical overlap 0.00 — the
value is beside the label and the window does not reach it.

**The 17 ROLE misses are not a reader defect.** 6 pages have no Persian OCR at
all. Of the 11 that do, none prints a role word the reader failed on; 5 have
chat that only REQUESTS a role (correctly refused), 6 have chat that says
nothing. The recall ceiling here is the Persian pass backlog, not the patterns.

### The prioritised list

Ranked by measured cells, with what each needs:

1. **ABO cell window — 21 labelled misses, ~2,736 corpus.** Direction (3),
   distance (4) and vertical overlap (2) are geometry the HLA rules already
   handle with a page slope and a chain walk; `_cell` has neither. The 7 with
   no token and the 4 bare letters are not window problems.
2. **Comparison sheets — 13 HLA misses at 0%, 450 corpus documents, 4,946
   unresolved cells.** The pages print alleles under column headers with no
   row labels. Needs column-aware subject assignment; refused outright today.
3. **No template family — 32 HLA misses at 64%.** 20 of 122 labelled documents
   and a third of the loss. Needs new families or a better generic rule.
4. **Persian OCR backlog — 1,566 documents never read in Persian.** 6 of 17
   role misses and 6 of 50 ABO misses have no Persian OCR at all.
5. **`repaired / SPLIT` — 4 of 8 allele contradictions, 1,467 corpus cells at
   21%.** Operator decision: 3:1 correct-to-wrong deferred to review.
6. **DRBX add-on on a damaged header — 4 of 6 presence contradictions, 1,461
   corpus cells at 25%.** Same shape, same decision (s17).
7. **ABO label spellings — 9 misses.** s16's Tier-1 pair route, verified with
   placebo controls, +194 documents.
8. **DRB3/4/5 no grouped header — 12 misses.** HA-011.

## s19 — working the s18 list in order: items 4 through 7

The operator: "please go through your list in order and resolve them one by one
and don't stop until you have solve all of them." Items 1-3 need a designed
rule and are with an adversarial workflow; item 8 likewise. This records the
four that are done.

### Items 5 and 6 — the two precision gates, applied

s18 left both as a 3:1 trade for the operator. The instruction to resolve all
eight is that decision, and both strata are "ambiguous critical OCR", which the
constitution sends to review rather than best-guessing.

`scripts/precision_gates.py`:

| gate | stratum | labelled error | corpus cells withdrawn |
|---|---|---|---|
| 1 | value repaired AND stability SPLIT | 21.1% (4 of 19) | 1,467 |
| 2 | DRB3/4/5 from an add-on source, no cleanly spelled header | 25% (5 of 20) | 1,461 |

Nothing is deleted: the value moves to `raw`, the reason names the gate, the
source carries `precision-gate/v1` so the group can be found and restored, and
the reviewer sees the reading as a proposal with its crop. Running it twice
touches nothing the second time.

On the 1,342 labels, exactly as predicted:

| | before | after |
|---|---|---|
| correct | 692 | 661 |
| **contradicted** | **14** | **5** |
| recall on cells read | 85.1% | 81.8% |
| **precision of what is asserted** | 98.0% | **99.2%** |

Nine wrong values withdrawn for thirty-one correct ones deferred to a person.

### Item 7 — the blood-group label in the recognizer's spellings

s16's Tier-1 pair route, which had survived placebo controls: a damaged group
word IMMEDIATELY followed by a damaged blood word inside one box. Adjacency is
the whole gate — `کرده` ("done") matches the wide group pattern and sits in
prose on 364 pages, and alone it anchors nothing.

A/B over all 23,566 documents, pair route on against off: **+291 resolved, 322
surfaced to review (label found, cell unread), 1 lost** — the verifier's own
predicted cost, where a new anchor makes one cell doubled. Applied by
`scripts/abo_label_repass.py` to the extracted corpus: +221 (the caption pass
had already claimed the rest from chat) and +154 to review with the anchor
recorded so the reviewer's crop lands on the field.

ABO 45.6% → **46.5%**, RH 40.7% → **41.7%**. On the labels ABO 46 → 47
correct, still 0 wrong.

### Item 4 — the Persian OCR backlog: DONE

The pass's own filter (`--min-loci 2`) reported 1,566 documents; the true
backlog was **4,529** of 23,566 with no Persian OCR at all, holding 6 of the 17
role misses and 6 of the 50 ABO misses. `easyocr` is in no lockfile extra — the
20,201 existing rows predate the repo's environment — so it was installed into
the one environment on this machine with torch (`anaconda3/envs/AGILE`, CPU)
and the pass run there in resumable batches at ~5s/page.

**Every report document in the archive now has Persian OCR: 20,201 → 21,948
rows, 0 errors, and `targets()` returns 0.** The 2,782 documents still without
it carry no locus label in the Latin pass at all — advertisements and
screenshots, which is exactly what the filter is for.

Harvested by re-running the three readers over the new pages:

| pass | gained |
|---|---|
| `role_repass.py` | 247 DONOR + 117 RECIPIENT bare, 35 + 27 anchored |
| `abo_label_repass.py` | 138 resolved, 215 surfaced to review |
| `caption_pass.py` | the chat re-weighed against the new form readings |

**ROLE 78.1% → 79.9%** (18,404 → 18,830), ABO 46.5% → **47.1%**, RH 41.7% →
**42.2%**. On the labels ROLE gains one correct (92 → 93) with contradictions
unchanged at 2; ABO and RH hold at 47 and 46 correct, 0 wrong.

### Item 8, sized while the design is verified

The 12 labelled misses for "no grouped DRB3/4/5 header" sit on 4 pages; on
every one the header is unreadable to both patterns, but each page prints 1-3
DRB3/4/5 GENE TOKENS on the row and the human confirms the row exists.
Corpus-wide, of 9,207 no-header documents, **4,615 print the gene tokens**
(2,734 one, 1,499 two, 371 three) and 2,156 of them resolved DRB1 on the same
page. Anchoring the row from its own gene tokens is the ADR 0008 Decision 4
licence with the header absent, which HA-011 says needs no spec change for
presence — and it reads a gene from token text, so it goes through the
adversarial workflow before a line of it ships.

## s20 — items 1, 2, 3 and 8: four builds, four rejections, and what they caught

The four remaining items were designed by one workflow, adversarially verified
by a second, implemented in isolated worktrees by a third and reviewed there by
a fourth. **Every one of the four builds was rejected**, each on measurements
the reviewer reproduced against the live stores. That is the process paying for
itself, and the defects are worth recording whether or not the branches land.

### The one that matters most: two people published as one genotype

Item 3 wires `BELOW_RULE` into extraction so a form printing its alleles UNDER
column headers can be read. The reviewer built the counterexample the design
missed: a header row `HLA-A | HLA-B | HLA-C` over a donor row and a recipient
row, one prefixed allele each. The branch resolves **A, B and C each with two
values — one from each person** — and publishes them as a single genotype.

Nothing in the shipped gates sees it. The cardinality gate counts two boxes and
two alleles, which is exactly `max_values`. `refuse_bare` passes because both
values print their own locus. The ownership gate passes because both boxes are
in the header's own column. `is_comparison_sheet` was measured at **0 of 305**
on these very pages, and the Persian role words fire on 10 of 305 while 76
pages carry ROLE UNKNOWN.

The verifier had required a gate for exactly this — refuse a two-box BELOW cell
when a page ruling crosses between the two value boxes, measured cost 0 of 199
— and it was not implemented. This is the wrong-person failure this project
names as its worst, reached by a rule that was verified in design and then lost
its guard in the build.

### The other three

**Item 1 (the ABO cell window).** The corroboration half of the safety case is
dead code: `reconcile_abo` accepts caption claims and no production caller
passes any, so the pinned "30 published / 13 to review" ships as 17 / 28, and
14 documents whose chat states the same letter are downgraded anyway. Worse,
the partial-contradiction gate exists on one route and not the other: 3 pages
publish a rescued value over a contradicting sign printed in the label's own
cell, and 2 of those would publish a POSITIVE Rh over a printed `-` the moment
the caption branch is wired in.

**Item 2 (comparison sheets).** The dry run does not reproduce its own pin: 241
pages bound against ~305. The cause is a straddle gate whose midline falls
inside a `Frequency` column, so wide OCR boxes holding an 11-digit identifier or
a percentage read as "a value straddles the midline". It refuses 85 pages
(pinned: 5), 64 of which bind cleanly without those boxes — and it writes
`this page prints donor and recipient columns for two subjects` into the review
queue for all of them. **224 of the 252 review cells assert two people on the
evidence of an ID number.** A false provenance statement in a medical queue is
worse than the missing yield.

**Item 8 (the DRB3/4/5 row).** The widened-header route writes 194 RESOLVED
cells — 75 of them ABSENT, a clinical negative — through the same code path as
strict headers, so `source` is NULL and `rule_id` is the ordinary one. Nothing
in the store distinguishes a widened-header page from a strict one: the review
pack cannot sample them and the group cannot be withdrawn. 16 of those pages
rest on a `3`-for-`5` glyph substitution with no measurement behind it, where
the sibling `S`-for-`5` rule has one. Separately, the token route's own stratum
tags on a `source` string that only the one-off pass sets, so it empties
silently at the next re-extraction — the third time this session a stratum has
been built that reports zero without being empty.

### What this says about the method

Every one of these was caught by measurement, not by reading: the reviewer ran
the pass against the live stores, built the counterexample, and compared the
shipped numbers with the docstrings. Three of the four rejections are about
something written into the repo or the queue that the code does not do —
a yield, a provenance, a guarantee. The fourth is a wrong-value path.

None of the four is merged. A fix round is applying the reviews' required fixes
in the same worktrees, to be re-reviewed against the same measurements.

## s21 — items 1, 2 and 8 merged and applied; what the fix round changed

The four rejected builds (s20) went back to their worktrees with the reviews as
the specification. Three came back approved and are merged; item 3 was rejected
a second time, on a defect its own fix round introduced.

### What the fix round actually closed

Each of these was a path that could publish something untrue, and none was
visible without running the code:

* **item 1** — the partial-contradiction gate ran on one rescue route and not
  the other, so 3 pages published over a contradicting sign printed in the
  label's own cell; 2 of them would have published a POSITIVE Rh over a printed
  `-` the moment the caption branch became reachable. The caption branch was
  itself dead code: `reconcile_abo` accepted claims and no caller passed any.
* **item 2** — the straddle test crossed a midline that, on a
  `Recipient | Frequency | Donor | Frequency` template, falls INSIDE the
  Frequency column. Wide boxes holding an 11-digit identifier read as "a value
  straddles the midline": 85 pages refused where the design priced 5, and
  **224 of 252 review cells asserted two people on the evidence of an ID
  number**. The test is now geometric — a box must reach into both columns'
  own spans.
* **item 8** — a widened header whose printed final `5` was read as a `3` was
  certifying **ABSENT**, a clinical negative resting on a glyph substitution
  with no measurement behind it where the sibling `S`-for-`5` rule has three
  independent legs. Those absences now go to review.

### Applied to the corpus

| pass | written |
|---|---|
| `abo_label_repass` (band + centre rescue) | 44 newly resolved, 12 caption rows upgraded to a form reading, 13 uncorroborated candidates to review |
| `column_bind` | 699 cells bound on 276 comparison sheets, 108 named for review on 50, 79 refused with crops |
| `drbx_token_repass` | 621 PRESENT on 479 pages |

Measured against the 1,342 labels: **662 → 664 correct, 122 → 120 missed,
contradictions unchanged at 5.** Corpus: HLA value cells 65,574 → 66,273, ABO
47.1% → **47.3%**, RH 42.2% → **42.4%**, and ABO gains a labelled correct (47 →
48) with Rh (46 → 47), still 0 wrong on either.

The labelled movement is small because these rules were aimed at populations
the four review rounds had barely sampled — 276 comparison sheets scored 0
correct on every labelled cell before, and 479 no-header DRB3/4/5 pages had
none. Their accuracy is unmeasured, which is why each ships with its own
`source`, its own review stratum, and a withdrawal handle.

### A quota that was a share, and had to become a count

Merging exposed something neither review could see alone. `abo_centre_rescue`
was weighted so a default pack drew 21 documents, meeting HA-019's gate of 20
readings before promotion. Item 2's two strata landed beside it, the total
weight grew, and the same weight drew **19**. Raising it to 112 bought one
merge; item 8's two strata took it back to 19 on the very next one.

A weight is a share of a total that other work keeps changing. A promotion gate
is an absolute count. `MIN_DRAW` now states the count and is drawn before the
weighted share, so a stratum landing beside it cannot quietly repeal the gate,
and the test asserts the guarantee rather than re-deriving arithmetic that kept
going stale. It was item 1's own test that caught it, twice — which is the
argument for writing the arithmetic down.

### Item 3, rejected again

Its fix round introduced a wrong-crop path. `family_repass` re-derived its
provenance map from a **second, independent** `merge_prefix_fragments()` call,
so the map's keys were `id()` values of objects that were garbage before the
next line ran. The lookup never matched, 43 resolved cells got an anchor box in
the levelled frame while their value boxes were in the raw one — the anchor
crop and the value crops of one fact in different frames — and, worse, a dead
`id()` is recyclable: a freshly constructed `Box` can take one of those
addresses, and the restore would hand a live box the wrong provenance, silently
and differently on each run.

It also still justified `refuse_bare` with "765 of 765 values print their
locus" from the pre-fix build, where the shipped extraction reads 290 pages and
727 of 727. That is the same class of defect the first review rejected it for.

## s22 — all eight items closed

The s18 list is done. Item 3 was rejected twice and landed on the third pass;
the other seven are in.

| # | item | outcome |
|---|---|---|
| 1 | ABO cell window | merged — the cell is the label's ROW, not its line |
| 2 | comparison sheets | merged — one person's column, under a subject-agreement gate |
| 3 | no-family pages | merged after 2 rejections — tie, leave-one-out, prefix repair, column direction |
| 4 | Persian OCR backlog | done — every report document read, 21,948 rows |
| 5 | repaired+SPLIT | withdrawn to review, 1,467 cells |
| 6 | damaged-header DRBX | withdrawn to review, 1,461 cells |
| 7 | ABO label spellings | merged — the pair route, +221 |
| 8 | DRB3/4/5, no readable header | merged — token route + gated widening |

### Accuracy, measured on the same 1,342 labels throughout

|  | start of the list | now |
|---|---|---|
| HLA correct | 692 | **666** |
| HLA **wrong** | 14 | **5** |
| HLA precision | 98.0% | **99.3%** |
| HLA recall (of cells a person read) | 85.1% | 82.4% |
| ROLE correct / wrong | 92 / 2 | **93 / 2** |
| ABO correct / wrong | 46 / 0 | **48 / 0** |
| RH correct / wrong | 45 / 0 | **47 / 0** |

Recall fell and precision rose because items 5 and 6 were precision trades,
taken deliberately: 2,928 cells withdrawn to review at roughly three correct
readings deferred per wrong one withdrawn. **Nine of the fourteen wrong HLA
values are gone.** Combined across all four fields the pipeline now asserts
854 values and 7 of them disagree with a human — 99.2%.

Corpus coverage: ROLE **79.9%** (from 78.1% at the start of the list), ABO
**47.3%** (45.6%), RH **42.4%** (40.7%), HLA value cells **67,649** (65,574 at
the start of the day, before the sideways pages).

### What the nine new sources are worth, and what they are not

    upright+rotated                801   sideways pages, turned
    column-bound                   699   one person's column on a two-person sheet
    token-anchored-drbx            621   the DRB3/4/5 row with no readable header
    family-tie                     550   prototypes that author the same rule
    below-rule                     364   values printed UNDER their labels
    family-loo                     258   a stack that fits except at one label
    family-prefix                  204   an HLA- prefix boxed apart from its locus
    column-named+role-unconfirmed  108   named for review, no value written
    anchor-row-prefix               80   the label read, the cell rectangle wrong

**3,685 cells, and almost none of them measured.** These rules were aimed at
populations four review rounds had barely sampled: 276 comparison sheets scored
0 correct on every labelled cell before this, 479 no-header DRB3/4/5 pages had
no labels at all, and the left-out fit and the column direction hold zero
labelled pages between them. Each ships with its own `source`, its own review
stratum and a withdrawal handle, and three of them carry a `MIN_DRAW` floor so
the pack cannot quietly stop sampling them.

The honest position is that precision is now 99.3% on what a person has
checked, and 3,685 cells sit outside anything a person has checked. That is
what round five is for.

### What the process cost and returned

Eight items produced, across four workflows: 28 design proposals of which the
verifiers refused 28; four implementations of which the reviewers refused four;
one of those refused twice more. Every rejection was a measurement, not an
opinion — a dry run against the live stores, a constructed counterexample, a
docstring compared against what the shipped gates produce.

Three findings are worth carrying forward more than the cells they earned:

* **two people published as one genotype**, caught by building the page rather
  than reading the rule — a header row over a donor row and a recipient row,
  where every gate passed and the cardinality was exactly right;
* **a provenance map keyed on `id()` of objects already garbage** — 43 cells
  with the anchor crop and the value crops in different frames, and a recycled
  address able to hand a live box someone else's provenance, differently on
  each run;
* **a promotion gate written as a weight share**, which two unrelated merges
  silently took below the number it names.

None of the three is visible by reading the diff. All three were found by
running the code against the corpus and comparing what it did with what it
said.

## s23 — the operator's decisions, applied (2026-09-07)

Fifteen questions went to the operator with options and a recommendation each.
What follows is the answer, the code that carries it, and what it measurably did.
Every new pass is dry-run by default, writes its own `source` tag, was run under a
per-field status snapshot, and undoes itself in one statement (`--undo`).

| decision | carried by | measured |
|---|---|---|
| **D1-b** a request word in the chat vetoes a blood group only from inside the same clause | `documents/caption.py` `_request_beside`: the clause is what the writer bounded with punctuation or a line break; "my group is O+, looking for a donor" states O+ | +19 ABO, +17 Rh from the chat; 2 unit tests |
| **D3-a** an empty printed cell is NOT_TESTED, not a review item | `scripts/ink_drain.py`: REVIEW_REQUIRED ∧ `anchor found but no box` ∧ `cell-ink/v1` BLANK | **14,060 cells** (C 7,007, DQA1 6,881, B 65, A 60, DRB1 31, DQB1 16); not one labelled value among them |
| **D4-b** a printed blood group on a two-person page cannot be attributed | `scripts/sheet_abo_review.py`: LABORATORY_PRINTED ABO/Rh RESOLVED on a comparison sheet → REVIEW_REQUIRED, value kept as the proposal | 66 ABO + 66 Rh on 66 pages |
| **D6-a** a gate-1 withdrawal that two independent engines agree on comes back | `scripts/gate1_repromote.py`: ≥2 engine FAMILIES CONFIRMED with one identical reading, no CONTRADICTED, no other engine reading otherwise | **123 of 1,467** (101 by two families, 22 by three); +1 labelled correct |
| **D9** `A*24,02` is A*24 and A*02 | `ocr/glyphs.py` `_PAIR`: a bare second half is accepted after a COMMA only; period, semicolon and slash still need the second star | `prefix_bind` **+1,144 cells** (A 307, B 343, C 205, DQB1 148, DRB1 139, DQA1 2); anchor-row route +0; +3 labelled correct |
| **D12-a** the constitution names its exceptions | `AGENTS.md`, `.claude/rules/ocr.md`: `prefix-bound`, `anchor-row-prefix`, `column-bound` | HA-017 DECIDED |
| **D13-a** the gate installs what the code imports | `EXTRAS = (hist, hla, image, ocr)` in `verify_repo.py`, CI (sync and mutmut), bootstrap; `test_harness_baseline` pins all four | HA-021 DECIDED |
| **D15** a pack of only the disputed cells, the rest pre-filled | `review_pack.py --disagreements-only EXPORT…` (`prior_labels`, `disagreement` on `golden.classify`); the page seeds the earlier answers into the named drawer and badges DISAGREES with "you said / pipeline now" | **56 documents, 616 cells pre-answered, 138 disputed** (DQB1 25, DRB4 20, B 19, DRB1 19, A 18, DRB5 14, DRB3 13, C 9, DQA1 1) + 2 ROLE fields; on 8766 |

The HA-018/HA-019 numbers that two parallel merges had each given to two entries
are HA-022 (two-person page) and HA-023 (Bw4/Bw6 gate) now; the blood-group
window entry keeps HA-019 because eleven files cite it.

### Net, on the same 1,342 labels

HLA **666 → 670 correct**, 118 → 114 missed, 19 partial, **5 contradicted
(unchanged)**. ROLE 93/2, ABO 48/0, RH 47/0. Corpus: HLA value cells 67,649 →
**68,916**; ABO 47.3 → 47.1% and RH 42.4 → 42.2% (the 66 sheet withdrawals net
of the chat gains); review queue **45,846 → 35,391 cells, 18,132 → 14,631
documents**; NOT_TESTED 38,987.

### Four things the session found on the way

* **A pass that fills what another pass withdrew is a silent reversal.** The
  caption pass fills any ABO row that is not RESOLVED — and a printed group the
  sheet review had just withdrawn is exactly that. Six of the 66 were overwritten
  within the hour. `caption_pass` now leaves a `sheet-review/v1` row alone (17
  of the 66 carry a chat group and stay in review); the six are restored. The
  same pass writes Rh alongside ABO without looking at the Rh row's own status:
  noted, not changed.
* **153 ABO and 136 Rh caption claims on comparison sheets stand RESOLVED.** The
  chat cannot say whose group it states any more than the print can. D4-b was
  scoped to the printed 66; this is HA-024, the operator's call.
* **D9's first `_PAIR` let a `Bw4` tail pose as a bare second allele:**
  `8*35,*51,Bw4` matched with `Bw4` as the second half and fell through to
  nothing. The bare branch is digits-only now and the tail path gets first
  refusal. An existing test caught it — the argument, again, for pinning
  behaviour the next rule will brush against.
* **172 → 123.** The gate-1 candidate count quoted when the decision was framed
  used a looser "none disagreeing"; the shipped rule counts an UNCONFIRMED
  engine with a different reading as a dissent. The smaller number is the one
  the code can defend.

Still open from the decision list: **D10, D11** (explained; awaiting an
answer), **D2-a** the tiered export, **D8-a** round five at `--n 600`, and the
CV plan (`CV_PLAN_2026-09-07.md`).

## s24 — the disputed pack re-checked; the loss charged to checkpoints (2026-09-07)

The operator re-read the 56-page disagreement pack (D15). Of the 138 disputed
cells, **6 were label errors and 132 stand as pipeline errors** (114
re-confirmed by hand, 18 left as seeded); one ROLE answer changed. Separately,
35 cells the pipeline and the reviewer had AGREED on were changed — all DRB3/4/5
rows once labelled NOT_PRINTED and now read as present/absent — which is why the
miss count rose: those rows were always unread, and are now counted.

On 1,342 labels over five rounds: **673 correct, 148 missed, 19 partial, 2
wrong** (was 670 / 114 / 19 / 5); ROLE 94/1, ABO 48/0, RH 47/0.

### The checkpoints

The operator's model: orientation → tilt → cell rectangle → recognition, an
error charged to the first checkpoint that did not hold.
`scripts/checkpoint_attribution.py` charges each non-correct labelled cell from
the fact's refusal reason and the page's `upright_pass` / `page_geometry`
records, and compares the value rectangle with the page's other loci.

| checkpoint | cells | of 169 |
|---|---|---|
| 1 orientation | 0 | — |
| 2 tilt | 0 | — |
| 3 layout: locus label not found | 22 | 13% |
| 3 layout: DRB3/4/5 header not read | 41 | 24% |
| 4 cell: too short (one allele of two) | 19 | 11% |
| 4 cell: too wide / wrong owner | 12 | 7% |
| 4 cell: empty / two subjects | 4 | 2% |
| 5 recognition | 13 (incl. both wrong values) | 8% |
| 6 DRB3/4/5 row grammar | 40 | 24% |
| 7 a precision gate withdrew a right value | 18 | 11% |

Orientation and tilt attribute nothing: the 611 sideways pages were turned
(s17) and every page ≥ 1.5° is levelled; tilted pages are 19% of failures
against 15% of all labelled cells. **The DRB3/4/5 row is 48% of the loss.**
Comparison sheets carry 10% of failures on 2% of cells (5×). The operator's
rectangle-size check measures as a signal: a value rectangle narrower than its
page's siblings fails **6 of 12** times (50%) against 11% for a rectangle like
its siblings; a wider-than-siblings rectangle (3 cells) did not fail, and a
height unlike siblings (28) failed once.

The ordered plan that follows from this is `IMPLEMENTATION_PLAN_2026-09-07.md`.



## s25 — the checkpoint plan built: four shipped, five declined on evidence (2026-09-07)

`IMPLEMENTATION_PLAN_2026-09-07.md` ordered the work by the checkpoint each
failure belongs to. Building it produced four passes and five measurements that
say a rule should NOT be written. The full table is in that document; this
records what the corpus and the labels did, and the three findings worth
carrying forward.

**Labels (1,342): 673 -> 691 correct, 148 -> 130 missed, 19 partial, 2 wrong.**
Corpus: DRB3/4/5 resolved +1,241 (+1,113 from W2(c), +116 from W2(a), +12 from
pages the token route newly reached), review queue 35,391 -> 34,278.

### The gate is charged where the damage is not (W2(c))

Precision gate 2 withdraws every DRB3/4/5 second-opinion call on a page whose
header only the damage-tolerant pattern reads. Per PAGE. But of the 21 such
cells a person has read, 18 were right, and **all three wrong ones rest on a
repaired gene token** — `DRBS` for DRB5, `DR83` for DRB3. The page's damage is
not the discriminator; the cell's own token is. Re-promoting on that test, with
the DRB1 consistency check allowed to object but not required to agree,
recovers 18 of 21 with 0 wrong and 1,113 cells corpus-wide. Requiring the whole
page to be clean would have recovered 12, and requiring DRB1 to agree 16 —
both strictly worse, and neither excludes an error the token test misses.

### A gate that names a hazard should test the hazard (W2(a))

`resolve_token_anchored_drbx`'s G2 requires the page's DRB1 **value** RESOLVED,
and its own docstring says why: every page with a DRB1 value box inside the
grouped row's window is a page whose DRB1 the resolver refused. That is a proxy.
Testing the hazard directly — no allele value may stand on the placed row — the
116 pages the lifted gate admits split 95 clean, 14 with a bare value, 7 with a
DRB1-prefixed one. The new gate is applied only where DRB1 is unresolved,
because 56 of the 488 pages the route accepts today would fail it and those
rest on exactly the corroboration being replaced.

### Three rules the measurement stopped

* **W5.** Restoring the 18 labelled gate-1 withdrawals yields **5 correct and
  13 contradictions**, and no available evidence separates them: two engine
  families agreeing with nothing contradicting is 1 right to 3 wrong. The
  constrained decoder cannot arbitrate because `SPLIT` is what triggered the
  gate. Gate 1 is doing its job.
* **W3(a).** The ink in the rest of the ruled row was to find the missing second
  allele. On the 19 labelled partials it holds ink on 2 and measures BLANK on 7.
  The pass therefore does NOT record a blank remainder as "one allele printed" —
  that finding would have been false on 7 of the 9 measurable labelled cells,
  corpus-wide about 1,270 cells. The crop and the measure reproduce
  `cell_ink_pass`'s stored decision on 136 of 136 measurable cells, which is
  what makes the negative a result rather than a bug.
* **W4.** Family templates reach 6 of 22 (16 of the pages have no family;
  corpus-wide 9,229 of 11,847, because the family is assigned from the labels
  the page failed to read). Whole-page OCR already covers 11 of the 22 and finds
  the locus label **0 times**. Generalising the DRB3/4/5 anchor to another label
  was refused by its own validation: only 3 of 4,000 pages can check the row
  order, and those 3 mispredict DRB1's row by 1.38 label heights.

### The residual is binding, not reading

Of the 151 remaining labelled failures, **113 have the value's digits readable
in a store already held**, 63 of the DRB3/4/5 failures have a readable gene or
header token, and only 7 have nothing readable at all. Several plan items
assumed the opposite. What is missing is the ability to say which row and which
column a readable token belongs to on a page whose labels are unreadable — and
the pages that need that capability are precisely the pages that cannot
validate it, which is the argument for a table-structure model trained on the
pages that do read (`CV_PLAN_2026-09-07.md` phase 2).
