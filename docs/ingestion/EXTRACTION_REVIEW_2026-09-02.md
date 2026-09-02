# Skeptical review of the extraction implementations — 2026-09-02

**Scope:** the five commits `d5d2d8d..02b9e82` (ADR 0008): corpus definition and
reader, glyph repair, gated locus resolver, grouped DRB3/4/5 row, role and ABO
readers, DRB1↔DRBX consistency check, regenerated families and golden sample.

**Method.** Six independent adversarial reviewers, one lens each, every claim
reproduced on the corpus (23,485 analysable true originals) or with a synthetic
input. Every finding then went to three independent refuters and counts only if
at least two could not refute it. The most dangerous claims were reproduced a
third time by hand before acceptance. Four further agents researched the next
accuracy gains, each required to measure rather than estimate. In total 136
agents, 1,226 tool calls, every corpus figure reproduced from the shipped code.

## 1. Verdict

**The design holds where it was measured, and the reviewers could not break the
core gates.** Across 7,247 documents with two different-locus labels on one line,
no resolved value lies beyond a same-line other-locus label. Every
self-identifying cross-locus value is refused. No final-character repair maps one
locus to another. All 239 resolved two-field values are real IMGT alleles. The
`S`→`5` repair is confirmed by an independent row wherever one exists.

**But 42 findings were raised and 39 survived verification, 16 of them able to
emit a wrong clinical fact.** One dwarfs the rest and was invisible to every
yield metric:

> **A single resolved allele is not homozygosity, and 29–36% of resolved
> A/B/DRB1 cells are single-allele.** The default `max_gap=20` label heights
> cuts the second-allele column in half: in two-allele cells the gap to the
> second allele is median 15.3, p90 18.4 and max *exactly* 20.0 — the cap. In
> 6,597 single-allele cells a further value-shaped box sits on the same row just
> beyond the chain (median 22.1 heights), self-prefixed with the same locus in
> 98–99% of cases, and equal to the first allele in only 13%. It is the
> heterozygous second allele. Nothing in `LocusResolution` distinguishes "one
> allele printed" from "one allele read", so every one of those cells would
> enter the database as homozygous typing and miscount every mismatch.

The remaining wrong-fact classes are rare and cheap to close: a missing
nomenclature gate (480 values), a tall value box bound to two loci (3 boxes; the
tie-break cannot see stacked labels), a Persian recipient regex that matches an
ordinary verb (2,062 documents), a printed choice label read as a value, and a
disclaimer detector that misses the wrapped footnote.

Nothing extracted so far may be published. That was already the position
(KI-012); this review adds that several of the published *counts* need
restating, and says precisely what to fix first.

## 2. Confirmed findings

Severity after verification: **W** can emit a wrong fact · **S** silently drops
correct data · **N** floods review · **Q** code, tests, drift.

### 2.1 Wrong-fact class

| # | finding | corpus count | fix |
|---|---|---|---|
| W1 | **Second allele truncated at `max_gap`; single value read as complete.** No state distinguishes one-printed from one-read. | 6,597 cells (4,316 documents); 12,440 single-value resolutions at gap 20 vs 5,406 at gap 40 | A single-value resolution never implies homozygosity: emit the second allele as `UNREAD`. Any aligned value-shaped box beyond the chain → `REVIEW_REQUIRED` ("second allele beyond gap"). Validate the gap distribution on the golden set; never retune by yield. |
| W2 | **No first-field admissibility gate.** The recognizer reads a leading `0` as `8`/`9` (`A*83`, `C*84`, `DQB1*83/93`, `DRB1*93/97/84/81`); the digits are clean, so repair cannot see it. Also three-digit fields on non-DP loci and all-letter tokens (`SS`→`55`) that are impossible 20× more often. | 480 resolved values (0.64%); 166 all-letter, 15 impossible | Fifth gate: per-locus first-field vocabulary from the py-ard allele table (A 21, B 36, C 14, DRB1 13, DQB1 5, DQA1 6, DPA1 4). Outside it → `REVIEW`. Never repair `8`/`9`→`0`. Refuse a value body with no digit at all. |
| W3 | **One value box bound to two loci.** Alignment normalises overlap by the *shorter* box, so a tall detector blob is "aligned" with every row it crosses; gate 3 tie-breaks on `x1`, which stacked labels share; a strict `<` lets an exact tie bind twice. | 3 boxes; 91 bound boxes taller than 2 label heights; 16 exact ties | Tie or near-tie → `REVIEW`; candidate taller than 2.5× the anchor → `REVIEW`; per-document exclusivity pass: a box bound by two loci invalidates both. |
| W4 | **Gate 3 cannot discriminate stacked labels.** Values are boxed 0.5–0.75 heights *above* their label; on tight-spacing forms the value overlaps the row above more than its own row and the row-above locus takes it. Confirmed on the A/B pair, whose families are disjoint. | 710 tight-spacing documents; 2 A cells holding a B-only family (≥2.5% for that pair alone); 41 values within 1 height of a second aligned label | Break ties on vertical proximity of centres, not horizontal distance; W2 catches the disjoint pairs; the per-family row band (P1 below) removes the mechanism on Yekta. |
| W5 | **`_RECIPIENT` matches the past participle `کرده` ("done") and the OCR form `گرده`.** Both interior groups were optional. | 2,062 documents; 61 promoted to a Tier-B *finding*; 740 genuine donor forms pushed to review as "both role words" | Require the `ن`; anchor to a token boundary; keep the measured variants explicitly. |
| W6 | **A single box holding both role words (a printed choice label) is read as DONOR** because donor is tested first. | 7 boxes, 6 documents, 4 resolve DONOR | A box matching both regexes is a label: refuse it as a token. |
| W7 | **Comparison sheets.** Documents printing `Donor | Recipient` as column headers on one row band resolve locus cells — the only path found by which two people's alleles could enter one typing. | 503 documents; 10 resolve 16 two-valued cells | Force every locus resolution on such a page to `REVIEW`; exclude the family from role Tier C. |
| W8 | **Grouped row uses a centre-distance band, not overlap.** A third gene token sharing the physical line falls outside it, so the row emits `ABSENT` where it must `REVIEW`. The ADR's "zero documents print more than two tokens" was an artefact of the band. | 7 documents | Overlap alignment, as in `anchors.py`; keep the >2 rule. |
| W9 | **Disclaimer detector needs both words in one box.** The wrapped footnote defeats it; values on disclaimed forms are labelled `LABORATORY_PRINTED` and their caption agreement counts as independent. | ≥27.5% of Yekta pages with the disclaimer missed; 120 resolved readings mislabelled | Detect across the footnote's row band; treat any Yekta-marked page as disclaimed unless proven otherwise. |
| W10 | **A standalone `DRB3`/`DRB4`/`DRB5` label still runs the generic rightward rule** and binds neighbouring numbers. | 4 documents, 5 values, 5 impossible | The generic resolver refuses DRB3/4/5; only `drbx.py` reads them. |
| W11 | **Expression-suffix alternative swallows a third digit glyph.** `SOSS`→`505S`, `ILA`→`11A`, `10S`→`10`+S. Nomenclature never attaches a suffix to a first-field-only name. | 3,062 boxes; 33 in anchored cells; 1 resolved | A suffix is legal only after two fields. |
| W12 | **Undamaged allele token on the presence row is invisible** to the gene count; beside two gene tokens the third gene is called `ABSENT`. | 0 on the corpus; 11 documents get a false "no gene token read" | An allele token names its gene: count it PRESENT, carry the allele as a separate proposal. |

### 2.2 Silent loss

| # | finding | count |
|---|---|---|
| S1 | Grouped-row centre band loses a gene token on tightly printed forms. | 1,036 documents |
| S2 | Compact two-gene tokens (`DRB3/4`, `DRB4/5`) on the row are ignored. | 333 documents |
| S3 | An empty grouped row is `UNKNOWN` in `drbx.py` but the same situation is `REVIEW_REQUIRED` in `anchors.py`. | 1,305 documents |
| S4 | `LOCUS*` label boxes (star inside the label) anchor nothing and are not label-shaped. | 785 `DRB1*` tokens on zero-fact documents |
| S5 | A value box that horizontally touches its label is excluded, so the cell resolves with one allele. | confirmed |
| S6 | `کاندید پیوند` (transplant candidate) is treated only as a form label, never as recipient evidence. | 476 documents |
| S7 | English `Donor`/`Recipient` with the label directly *above* is dropped. | confirmed |
| S8 | A printed ABO label swallowed into a long line box, or present only in the footnote, is reported "no label". | confirmed |
| S9 | `scripts/persian_pass.py` and `golden_sample.allele_fingerprints` bypass the corpus reader. | 1,164 thumbnails were OCR'd |

### 2.3 Review noise

| # | finding | count | fix |
|---|---|---|---|
| N1 | **One-value DRB1 rows are doubled into a homozygous pair** before the consistency check, manufacturing `FORBIDDEN_GENE_PRESENT`. The ADR's 99.62% is the two-value subset only. | 1,315 of 2,304 one-value rows (57%); a one-value-aware check flags 23 of 7,630 (0.30%) | With one allele read, only a gene forbidden by *that* allele, or an expected gene called absent, is checkable. |
| N2 | A caption stating the group without Rh is treated as a different blood group and questions the subject's identity. | confirmed | Compare letter and Rh separately; `UNKNOWN` never conflicts. |
| N3 | Footnote word `groups` ("alleles or groups of alleles … PCR-SSP") anchors an ABO cell. | 604 anchors / 576 documents; 2 resolve | Drop bare `group(s)` from the Latin label list. |
| N4 | The value grammar accepts English words, `hh:mm` times and 3-digit codes; only geometry keeps them out of cells. | 26,174 digit-free accepted tokens corpus-wide, none resolved | W2's no-digit rule. |

### 2.4 Code, tests, drift

- `scripts/resolve_loci.py` passes `same_row_tol` into `align_overlap`, defaults to
  `below`/2.5, uses the legacy regex path and reads thumbnails: resolves ~0.
- Two tautological assertions (`status is not RESOLVED or locus == 'DRB1'`; the
  "no repair turns one locus into another" test iterates substitutions that
  cannot fail). **Eleven scratch mutations survive the suite**, including the
  ownership-alignment fix and every tolerance constant.
- The `anchor_pattern` override bypasses canonicalisation and the grouped-header
  refusal; gate 3 cannot see anchors found through it.
- `T`, `t`, `!` were added to the digit-repair table without corpus evidence
  (their value-box population is English text). `expected_drbx_genes` accepts the
  serological broad families 02/05/06.
- Dead code in `looks_like_locus_label`; two unreachable guards in
  `parse_allele_value`. Docstrings and ADR 0008 Decision 5 quote counts that no
  longer reproduce.
- **Nothing assembles the pipeline.** `role.py`, `abo.py`, `drbx.py` and
  `drbx_consistency.py` are imported by no script; every corpus number so far
  came from inline session scripts. There is no caption extractor in `src`, so
  `decide_document_role` and `reconcile_abo` are only as safe as what a caller
  passes them.

### 2.5 Refuted (3)

- *Bare Persian blood-word anchor plus reversed grammar publishes a locus
  fragment as a blood group.* The code path exists and the synthetic input
  resolves, but three refuters found zero corpus harm through it. Kept as a
  hardening item, not a defect.
- *The `repaired` flag is silent on a swallowed suffix.* The flag's contract
  holds; the suffix itself is W11.
- *OCR-001 invariants lack marker traceability.* Designed behaviour for a
  `BLOCKED` task; the proposed fix would break the CI gate.

## 3. What the reviewers could not break

- Gate 1 on the chain across 7,247 two-label lines: zero walk-throughs; damaged
  labels in the chain trip cardinality or shape.
- Gate 2: every cross-locus self-identifying value refused; interior-damaged
  prefixes cannot bind.
- Label repair: exhaustive probe of damaged spellings; no cross-locus mapping.
  `T`-final DRB1 anchors bind families a DRB3/4/5 row cannot print.
- `S`→`5` where a second row can check it: DRB1 `IS`→15 confirmed by DRB5
  PRESENT in every checkable case; DQB1 `0S`→05 matches a DQB1*05 haplotype in 8
  of 9.
- All 239 resolved two-field values are IMGT 3620 alleles.
- The `repaired` flag is set on every glyph route.
- Post-hoc repair vs a grammar-constrained re-decode of the crops: **0 of 785**
  vocabulary-valid repaired DRB1 values changed (rule of three: <0.38%).

## 4. How to make it better — the plan, ranked by harm per hour

Effort in agent-days (A) and human hours (H). Every magnitude below was measured
by the research agents on the real corpus; none is an estimate unless marked.

### P0 — Close the wrong-fact classes (≈2 A, 0 H). Before anything else.

1. **Second allele and single-value semantics (W1).** `UNREAD` second allele;
   "value beyond gap" → `REVIEW`. Changes what the golden set will score, so it
   goes first.
2. **Fifth gate: first-field vocabulary (W2).** DRB1/DQB1/DQA1/DPA1/DRB3-5 sets
   are fixed knowledge; class I from the py-ard table (HA-006). Measured on the
   Yekta family: 431 impossible values → 0, 412 cells to review.
3. **Ownership (W3, W4):** tie → `REVIEW`; height cap; exclusivity post-pass;
   vertical tie-break.
4. **One-value-aware consistency (N1):** 1,315 flags → 23.
5. **Comparison-sheet harm gate (W7):** costs 10 documents.
6. **Role (W5, W6, S6):** nun required; both-words box refused; `کاندید پیوند` as
   Tier-B recipient evidence.
7. **Grouped row (W8, W12, S1–S3):** overlap band; count allele tokens;
   two-gene tokens; one empty-row policy.
8. **ABO (W9, N2, N3):** disclaimer across the row band; Rh `UNKNOWN` never
   conflicts; drop bare `group(s)`.
9. **Grammar (W10, W11):** generic resolver refuses DRB3/4/5; suffix only after
   two fields.
10. Fix `resolve_loci.py`, the two tautological tests, and add mutation-killing
    tests for the eleven survivors.

### P1 — Per-family rule for Yekta (1.5–2 A). ADR 0007 registry entry.

`direction="right"` everywhere (`below` is dead on this corpus: ≤168 resolutions
per locus at any setting, 88% of them the next row's label). Row band = anchor
centre ± 0.5 row pitch (the pitch is a template constant, 0.1248 of the A→DQA1
span); no distance cap inside the band; max 2 values; **require the value's own
locus prefix** (99.9% of Yekta values print it; the prefix gate alone caught 554
next-row leaks); vocabulary gate on. Measured on 13,323 Yekta documents against
the default rule:

| | default | Yekta rule |
|---|---|---|
| two-allele cells | 27,545 | **43,350** |
| single-value cells | 10,516 | **329** |
| impossible first fields | 359 | **0** |
| same box bound twice | 3 | **0** |
| DRB1↔DRBX disagreement | 0.28% | 0.34%, all to review |

For unassigned documents keep `right/0.2/20` with P0's gates. **Do not loosen
`max_gap` globally**: gate-2 leaks on Yekta rise 36 → 145, and they would be
silent on prefix-free forms.

### P2 — Rewrite template discovery (1 A), then redraw the golden sample (0.25 A).

Root causes, all reproduced: the signature counts standalone `DRB3/4/5` labels
that are actually the grouped row's *values* (12,178 of 12,641 DRB3 boxes),
so one Yekta form splits into ≥7 presence groups by genotype; absolute page
coordinates on hand-held photos (the A label spans y 0.165–0.408) let HDBSCAN
fragment one template into position blobs and discard 4,195 of 7,299
fully-labelled Yekta documents as noise; anchor purity then fails on the
value-bearing "labels". The "`DRB4` in two columns 0.285 apart" of ADR 0007 is
this: DRB4 sits at x 0.709 when DRB3 is also on the row and 0.474 when alone.

Prototype fix: signature over template-constant labels only, a
similarity-normalised frame (DRB1 at origin, A→DQA1 span = 1), HDBSCAN on
fully-labelled documents, then a least-squares similarity fit for any document
with ≥3 constant labels. **Coverage 707 → 14,876 documents (63.3%)**, zero
ambiguous assignments, residual p99 0.037 span. 154 of the 199 golden documents
are Yekta and no other laboratory is represented; 25 "non-report" golden
documents are assignable Yekta reports. Redraw per family plus an OTHER stratum.

### P3 — Label the golden corpus (1 A tooling; ~4 H per annotator).

Under the current anchors the 199 documents hold **1,657 cells**: 1,216 locus
cells plus 441 DRB3/4/5 gene cells; 522 locus cells and 380 gene calls are
resolved today. Rule of three on the 902 resolved facts bounds wrong-locus /
wrong-value acceptance at ≤0.33%. A single-file local labelling page was
prototyped (blind to the OCR proposal, per-locus pick-lists, cell → row → page
crops, annotator-seeded shuffle, states `VALUE / NOT_PRINTED / BLANK /
UNREADABLE / PRESENT_ONLY / NOT_A_REPORT`). Remaining: `golden_tasks.py`,
`golden_adjudicate.py` (two label files → third-person adjudication) and
`golden_score.py`, whose non-zero exit on any wrong-locus acceptance is the
acceptance evidence `scripts/acceptance.py` already consumes. Label the 902
resolved cells first. Note 39 golden documents have an exact perceptual-hash
copy elsewhere in the corpus — a free cross-check.

### P4 — Tesseract as the independent confirmer (0.5–1 A). ADR 0006 unanimity.

Tesseract 5.4.0 is installed (not on `PATH`). On 300 resolved DRB1/DQB1 value
crops, `--psm 7` with a digit whitelist agrees with the repaired OnnxTR value on
**86.3%**; 11.3% are Tesseract abstentions on narrow two-allele crops
(recoverable by cropping from the anchor-defined cell), **1.7% are
contradictions, and every one of those Tesseract readings is outside the DQB1
vocabulary while every OnnxTR reading is inside**. Auto-accept only
unanimity-in-vocabulary; the ~14% remainder is the human review budget.
Padding, other page-segmentation modes and Otsu all made it worse.

### P5 — Grammar-constrained CTC decode as a complement (1–2 A).

Not greedy masking: it dropped the `*` on 12 of 120 prefixed values and turned
23 of 50 *label* crops into allele-shaped strings with normal confidence. A
grammar-constrained Viterbi decode over the recognizer's logits, run only on
anchored cells after gates 1 and 3, recovers 164 of 200 currently unparseable
DRB1 candidates (62 under a strict policy; ~540 corpus-wide, ~3% more DRB1
facts) and gives an abstention signal the pipeline lacks: **4.6% of currently
resolved cells decode to two or more different alleles under ±1 px crop
jitter** and are accepted silently today. The grammar cost separates labels
from values (0 of 50 labels admitted at cost < 8). It changed 0 of 785
vocabulary-valid repaired values, so it complements the repair rather than
replacing it. Re-decode only anchored cells (113,707 boxes), never the full
pass.

### P6 — The PCR-SSP narrative form (2–3 A + a human reading ~5 forms).

2,631 documents (95.9% zero-fact) are a prose form ("PCR-SSP", "primers",
"peripheral"). Self-prefixed merged values are bindable on 1,818 of them
(3,608 cells) but 134 carry both role words, 50 carry antibody words, the
out-of-vocabulary rate is 2.1% vs 0.9%, and no DRB3/4/5 row exists to check
them. **Emit as PROPOSAL tier only, and only after a human confirms on ~5 forms
that the listed alleles are the subject's typing and not the primer panel.**
Stripping trailing punctuation from labels (`HLA-A*:` 489 tokens) anchors 2,272
more of these documents for classification but yields only 72 facts.

### P7 — Assemble the pipeline (0.5 A).

`scripts/extract_facts.py`: resumable, batch-committed like the OCR pass, writing
`data/derived/facts.sqlite` with one row per (sha256, field, value, status,
reason, anchor box, value box, raw, repaired, rule id, engine versions). A
caption extractor in `src` (CLAIM-001). Route `persian_pass.py` and
`golden_sample.py` through the corpus reader.

### Leave unresolved, with reason

181 no-text or sparse images (not documents); 939 chemistry, urine and virology
reports; 1,027 other photographs; 53 phone-number advertisements; 49 antibody
tests. The zero-fact set shrinks by only ~144 documents under the alignment
relaxation because 7,400 of it is the PCR-SSP family, comparison sheets and
non-reports.

### Do not do

Loosen `max_gap` globally. Repair `8`/`9`→`0`. Treat a one-value resolution as
homozygous. Merge records by perceptual hash beyond an exact match: at
distance ≤8 phash groups 37.9% of documents with 8.9% disagreeing and a median
allele-token Jaccard of 0.17 — it is layout-dominated and merges different
patients on the same printed form. The "71.7% near-duplicate" token-fingerprint
figure is not reproduced at pixel level: 20.6% exact, and the 0.43% cross-copy
disagreement is an instability floor under recompression, not an error
estimate.

## 5. What remains unmeasurable without labels

Digit misreads that land on a *valid* family of the same locus — `DRB1*13` read
as `*15`, `B*35` as `*55` (about 3 of 11 leading-`S` B cells by the header's own
confusion rates), `A*24` as `*02`, a trailing `0` as `8`/`9` (about 0.4%, moving
`B*40` to `B*48`) — pass every gate and every cross-check. Only the golden
corpus can size them (KI-012). The P0 changes alter what the golden set will be
scoring, which is why they come first.

## 6. Provenance

All counts 2026-09-02 on this machine from `data/derived/ocr_pass.sqlite`,
`persian_pass.sqlite`, the export HTML and, for the CTC and Tesseract
prototypes, crops re-cut from the originals at the stored boxes. Counts only; no
text, value or identifier tied to a document was printed. Reviewer and research
outputs, refuter votes and prototype scripts are in the session artefacts.
