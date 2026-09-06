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

