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
