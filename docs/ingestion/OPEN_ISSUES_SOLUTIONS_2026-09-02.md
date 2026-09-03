# Open issues after P0–P7: diagnosis and solutions (2026-09-02)

Companion to `EXTRACTION_REVIEW_2026-09-02.md` (what was fixed) and
`OCR_MODEL_SURVEY_2026-09-03.md` (which other engines were tried). This document
takes the six issues from the status report one at a time: what is actually
wrong, what was measured today, what is now built, and what remains and for
whom. Every number here is a yield or an aggregate over the local corpus; none
is an accuracy, because no extracted value has been compared to a human reading
yet (KI-012). That is issue 1.

Corpus reference: 23,566 unique originals; 14,625 documents with at least one
resolved locus; 10,246 with three or more; 90,735 resolved facts.

---

## Issue 1 — Nothing is validated

**Diagnosis.** Every gate, verdict and yield was designed from measurements of
the OCR output itself. The blind golden tool (`tools/golden_label.html`, 199
documents, 2,189 cells) has been ready since ADR 0009 and nobody has labelled
with it. Blind labelling is the right instrument for the *accuracy claim* but a
slow one for *finding errors*: the labeller types every cell from scratch.

**Solution: an anchored review pack, chosen by failure signal.** Built today.

* `scripts/review_pack.py` selects documents from fifteen strata, one per
  signal the pipeline already emits, rarest first, plus a clean-control
  stratum, and packs them with per-cell crops and every engine's reading into
  `data/review/hla_pack/` (gitignored; the pack is the patients' reports).
* `tools/hla_review.html` is the page (copied into the pack as `index.html`,
  opens from disk, no server). For each document it shows the photo with the
  selected cell highlighted, and per locus: the crop, the pipeline's value and
  raw text, Tesseract's reading and verdict, the constrained decode's reading
  and its jitter votes, any extra engine's reading, and an input pre-filled
  with the pipeline's value. Enter approves; typing edits. Document-level
  role, ABO, Rh, "not a report" and "unsure" are captured too.
* Output is `golden-labels/v1` with `decision: APPROVED | EDITED | ADDED`
  per cell and `anchored: true` on the file, and the pack writes
  `pipeline.json` in `golden_score.py`'s hidden format, so the labels are
  scored with the existing tool:

      python scripts/golden_score.py --labels a.json b.json --hidden data/review/hla_pack/pipeline.json

  One person's anchored labels can be scored by passing the same file twice;
  the report then reads as "what one anchored reader disagreed with".

The 150-document pack built today:

| stratum | docs | what it tests |
|---|---:|---|
| consistency_flag | 8 | DRB1 and the DRB3/4/5 row contradict each other |
| low_res | 4 | LOW band (85 exist in the corpus) |
| digits_lost | 12 | the decode dropped a digit the recognizer saw |
| proposal | 8 | resolver refused for shape; decode reads cleanly |
| review_refused | 13 | boxes on the row, cell refused |
| unread_second | 8 | second allele unread |
| decode_split | 16 | reading changes under one-pixel jitter |
| confirmer_contradicted | 16 | Tesseract read different digits |
| repaired_glyph | 12 | accepted value went through glyph repair |
| comparison_sheet | 4 | donor and recipient on one sheet |
| mid_res | 8 | MID band; informs HA-003 |
| default_rule | 8 | no layout family, generic rule |
| zero_fact_no_anchor | 9 | no label anchored anywhere (see issue 6c) |
| zero_fact_refused | 8 | labels anchored, every cell refused |
| clean_control | 16 | every signal agrees |

Seeded (`--seed 20260902`), so two people get the same documents; `--n`
scales the quotas.

**The trade-off, stated.** An anchored reader approves what is shown more
often than a blind reader would type it; that is why the decision is recorded
per cell and the file is marked anchored. The blind corpus remains the
instrument for the published false-acceptance bound. The anchored pack is the
instrument for *which signal predicts errors*, which is what orders the review
queue (issue 5). Expect about one minute per document: roughly 2.5 hours for
150.

**Who:** a human labels. Then an agent runs the score and, per stratum, reports
the edited-over-approved rate. The clean-control rate is the one that decides
whether anything can be published.

---

## Issue 2 — The database is per image, not per person

**Diagnosis.** 14,625 documents carry ~4,334 distinct HLA fingerprints; the
most repeated fingerprint appears on 67 documents. Brokers repost, patients
re-send, and the same report is photographed twice. Matching over documents
would match a person against themselves and count them many times.

**Solution: `ENTITY-001`, evidence-tiered clustering, HLA never merges alone.**

**Measured 2026-09-02, and it corrected the first draft of this rule.** 10,032
documents resolve three or more of A/B/C/DRB1/DQB1, in 4,246 distinct
fingerprints. Two questions had to be separated: are the repeats real, and is a
fingerprint discriminating enough to merge on?

*The repeats are real.* Within each locus set, identical pairs run 177 to 1,982
times above what independent chance predicts, and the largest groups are
internally consistent: the 67-document group is 58 RECIPIENT and 9 unread, the
62-document group 35 DONOR and 27 unread, the 45-document group carries one
blood group on all 45. People repost.

*The fingerprint is still not discriminating enough to merge on alone.* Per
locus, the chance two unrelated documents carry the same genotype:

| locus | documents | distinct genotypes | two random documents match |
|---|---:|---:|---|
| DQB1 | 9,675 | 30 | 1 in 10 |
| C | 3,114 | 97 | 1 in 40 |
| DRB1 | 11,112 | 113 | 1 in 44 |
| A | 11,628 | 149 | 1 in 55 |
| B | 10,911 | 344 | 1 in 90 |

These are first-field genotypes from Iranian donors and recipients, not alleles:
DQB1 with thirty observed genotypes carries almost no identifying power. 10,032
documents make 50.3 million pairs, so **any per-pair match probability above
2 × 10⁻⁸ yields an expected false merge**, and the draft rule "identical on ≥3
loci" reaches only 1 in 22,000 to 1 in 218,000 for the triples that actually
occur — on the order of 200 to 2,300 coincidental pairs corpus-wide. Merging on
that would fabricate people.

Rules, to be written into the spec and tested first:

1. Identical file hash, or identical perceptual hash above the DEDUPE-001
   threshold: same *document*, one record, many postings. No HLA needed.
2. **A fingerprint link is scored, not counted.** Compute the match probability
   as the product of the per-locus figures above over the loci both documents
   resolve. `P ≤ 10⁻⁷` (A+B+C+DRB1 is 1 in 8.8 million; A+B+DRB1+DQB1 is 1 in
   2.1 million) proposes a `TIER_2` review candidate. `10⁻⁷ < P ≤ 10⁻⁵` proposes
   one only with corroboration. Above 10⁻⁵ it proposes nothing.
3. **Nothing auto-links on HLA at any probability.** A cluster is auto-linked
   only when a non-HLA identifier agrees as well: the same sender hash, or the
   name hash once HA-005 is decided. HLA then confirms; it never proposes alone.
   This is the doctrine's rule, and the arithmetic above is why it is right.
4. Any conflict (two blood groups, two roles that are not a comparison sheet,
   a DRB1/DRBX inconsistency between members) blocks the cluster and lands it
   in the queue.
5. The per-locus frequency table is derived from this corpus and must be
   regenerated, versioned and committed whenever extraction changes, because
   every threshold above is stated in terms of it.

Storage: a `person_cluster` table (cluster id, tier, evidence list with
provenance to each document and the computed probability) and a
`merge_decision` table (human decisions, append-only, reversible). Matching
(`MATCH-001`) reads clusters, never documents, and treats a cluster with an
open conflict as UNKNOWN.

**Consequence for the product.** Sender identity, which lives in the Telegram
export and not in the report, is the load-bearing signal for deduplication. That
makes `HIST-001`/`HIST-002` a prerequisite for entity resolution as well as for
role (issue 3), and it is already the active task.

**Who:** human decides HA-005; agent writes the spec, tests, tables.

---

## Issue 3 — Role is missing on 60% of typed documents

**Diagnosis.** The printed role field resolves on 5,054 documents (2,885 donor,
2,169 recipient); it is REVIEW_REQUIRED on 5,370 and absent on 13,142. The
form field is the only source wired into `extract_facts.py`, and the two other
sources are not yet available in the repository pipeline: message captions and
the surrounding conversation are not parsed, because `HIST-001` (the Telegram
HTML parser) is the ACTIVE task in the work queue and is at 0/3 criteria.

**Solution: finish HIST-001 → HIST-002, then a caption claim extractor.**

`decide_document_role(form, caption_role=..., has_recipient_only_test=...,
sender_prior=...)` already exists and already encodes the precedence (printed
field wins, caption may veto to REVIEW, never overrides). What is missing is
the *producer* of `caption_role`:

* `kidneymatch.documents.caption` (new): reads the message caption and the
  same sender's text messages inside the bundle, Persian tiers as for the
  form field (donor words, recipient words, "candidate for transplant" =
  recipient, "patient" = recipient), English fallback, refuses when both
  words appear. Output `CaptionClaim(role, tier, source_message_id)` with
  provenance.
* `has_recipient_only_test`: a PRA or crossmatch result on the same document
  or in the same bundle is recipient-only evidence; the archive
  characterization lists the marker strings.
* Sender prior: a sender whose *printed* roles are ≥95% one role over ≥20
  documents gives a tier-C prior for their unread documents. A prior is a hint
  for the reviewer and never a resolved role.

Expected effect cannot be stated honestly until captions are parsed; the
earlier archive characterization found role words in a large share of
captions, which is why the veto path exists. Measure, then report.

**Who:** agent. HIST-001 is already the active task, so this is the queue
working as intended; the role extractor is the first consumer.

---

## Issue 4 — Decisions only a human can make

| item | what blocks | recommendation (not a decision) |
|---|---|---|
| HA-006 IMGT version | nomenclature gate is pinned at 3620 while the spec says 3.65 | (a) amend the spec to 3620 now; schedule the py-ard 2.x upgrade as its own task with the lockfile and OSS register. The gate's job is first-field admissibility, which has not changed between those releases for any locus these forms print. |
| HA-003 resolution bands | which band forces human review | LOW (≤560 px, 85 docs) always reviewed. For MID (561–900 px, 2,276 docs) the pack's `mid_res` stratum measures the error rate directly; decide after the labels rather than before. |
| HA-005 patient names | entity resolution design | salted hash. It keeps the linking value and removes the exposure; a reviewer who needs the name has the photo. |
| HA-004 Iranian practice | matching spec freeze | out of the agent's competence. Note for the immunologist: these laboratories do not type DQA1, DPA1 or DPB1 (KI-013), so DR/DQB-prioritised counting is the only option the data supports. |

None of these blocks the labelling in issue 1.

---

## Issue 5 — No review-queue workflow for ~94k items

**Diagnosis.** 83,499 cells are REVIEW_REQUIRED, but they are not 83,499
decisions. Measured today over the class I/II cells:

* "anchor found but no box at all in its cell": DQA1 10,766, C 9,906, DRB1
  1,002, B 985, A 944, DQB1 539. By KI-013 these are overwhelmingly loci the
  laboratory does not type: the label is printed and the cell is empty.
* "N candidate values exceeds max_values=2": ~2,000 (SSP-style layouts and
  comparison sheets with two columns).
* "2 anchors found; cannot decide which row": 416 on DQB1 alone.
* Decode `SPLIT`: 1,602 cells so far; `DIGITS_LOST`: 1,191 (see issue 6 for
  why most of those will clear).

**Solution: a policy change for the empty cells, then value-ordered queue.**

1. **Empty-cell policy (versioned change, needs a spec line, not a human per
   cell).** For a layout family where a locus label is printed and the cell is
   empty on ≥95% of documents (measured per family in KI-013), an anchored
   label with no box in its cell resolves to `NOT_TESTED` for that family,
   with the measured rate recorded as provenance. This removes on the order of
   20,000 items with one auditable rule. It is a spec change, so it goes into
   `OCR-001` and the extraction tests before the code.
2. **Order the rest by what a decision buys**, not by reason:
   1. cells whose resolution completes a document that already has a role and
      four or more other loci (a matchable record is the unit of value);
   2. `SPLIT` cells with exactly two candidate readings: a one-click choice,
      and the page already shows both;
   3. "N candidates" and "2 anchors" refusals with boxes on the row: a
      reader sees the row and types;
   4. `CONTRADICTED` cells: pipeline and Tesseract disagree, one of them is
      right;
   5. everything else, newest first.
3. **Reuse the pack page as the queue page.** `review_pack.py` already builds
   the unit of work (document + crops + readings + pre-filled answers); a
   `--only <stratum>` selector and a `--exclude-labelled <labels.json>` filter
   turn it into a queue generator. Labels stay `golden-labels/v1`, so every
   queue batch is also benchmark data.

**Who:** agent (spec line for step 1 needs a human "yes" because it changes
what UNKNOWN means for those cells; steps 2–3 are tooling).

---

## Issue 6 — Confirmer gap, unstable decodes, zero-fact documents

### 6a. Why class I cells are "unconfirmed"

Measured on FORM#1, resolved cells:

| locus | cells | Tesseract UNCONFIRMED | of which empty reading | mean value-box width (page fraction) |
|---|---:|---:|---:|---:|
| A | 8,809 | 52.5% | 23.0% | 0.042 |
| B | 8,456 | 56.1% | 19.4% | 0.040 |
| C | 2,156 | 59.1% | 31.5% | 0.041 |
| DRB1 | 7,684 | 18.6% | 11.9% | 0.072 |
| DQB1 | 6,744 | 18.5% | 10.9% | 0.074 |

CONTRADICTED rates are the same for both classes (14–15%). The gap is entirely
UNCONFIRMED, and class I value boxes are 57% the width of class II boxes at the
same height: `A*02` is four glyphs, `DRB1*11` is seven. Tesseract at psm 7 on a
crop that narrow returns nothing (a fifth to a third of the time) or a string
without the star (only 7–14% of the unconfirmed readings contain one), and
`confirm._read` then refuses to parse it.

**Fixed the same day**, and it moved 4,113 verdicts: the confirmer now reads a
star-less `A02` or `Cw07` the way `digits_preserved` does. Confirmed went
20,613 → 22,969 and unconfirmed 20,213 → 18,019 over the stored readings, with
no OCR re-run (`scripts/confirm_pass.py --rescore`).

**The remaining 18,019 need a different engine, and one was measured.**
PP-OCRv5 en-mobile-rec agrees with the trusted set 97.0% and the hard cells
91.0%, against Tesseract's 90.0% and 51.5%, at 13 ms per crop on the CPU. See
`OCR_MODEL_SURVEY_2026-09-03.md` §8, including the dependency decision that
adopting it requires.

### 6b. The decode's DIGITS_LOST verdict fires on the locus digit

Re-examined 300 demoted cells (349 boxes): **240 fired because the greedy path
dropped the star**, so the `1` of `DRB1` was compared as a value digit; 108 were
the decode adding a digit the model did not read, which is a real loss and must
stay flagged; 1 other. Fixed today in `kidneymatch.ocr.ctc.digits_preserved`
(letters stripped, one locus digit forgiven, value digits must survive in
full), with tests pinning both directions. The 5,695 DIGITS_LOST cells were
re-decoded the same day: on resolved facts DIGITS_LOST 1,670 → 459, UNANIMOUS
43,326 → 44,504, and 33 masked SPLIT cells surfaced. No value changed.

`SPLIT` was checked the same way and is sound: 93–100% of SPLIT cells per locus
are real digit disagreements between offsets, not prefix rendering. C is the
unstable locus (30% SPLIT on FORM#1 versus 3–4% for A and B): the narrowest
crops with the `Cw` prefix.

### 6c. The 7,516 zero-fact documents, and the correction that shrank them

A first pass split them by what their OCR boxes contained and concluded that
4,944 documents were readable forms whose class I labels lacked the `HLA-`
prefix. **Measuring it properly reversed that**, and the reversal is the most
useful thing in this document.

| signal | the 16,050 that produced facts | the 4,944 that anchored nothing |
|---|---:|---:|
| carries a canonical locus label | 98.9% | 9.0% |
| carries ≥1 allele with a star or colon | 98.6% | 27.8% |
| carries ≥4 such alleles | 95.0% | 9.3% |
| carries ≥8 such alleles | 63.6% | 6.1% |

The bare `A` boxes that suggested the first reading are *less* frequent in the
failing group (1.8% of documents carry three or more) than in the working one
(3.2%). They are noise in both. And the failing documents are not forms holding
unread values: **72% contain no allele-shaped value at all** and 8.5% contain
almost no text. They are photographs, screenshots and other non-reports, which
is what a public Telegram channel is mostly made of.

The genuinely recoverable subset is **170 documents** carrying both a canonical
label and four or more starred alleles. Their labels are DRB3, DRB4 and DRB5
(127, 41 and 71 documents) with almost no A, B, C, DRB1 or DQB1: the grouped
DRBX row was read and the main rows were not. A template pass over those is
worth a day, and it is P6's real size.

The other zero-fact population, the 2,572 documents that anchored labels and
had every cell refused, is a different and better prospect: those are
multi-column layouts hitting "N candidates exceeds max_values=2" and "2 anchors
found". The review pack draws from both so a person can confirm this reading.

**What this changes about the plan.** The corpus is not hiding thousands of
readable reports. What exists is roughly what has been extracted, so the work
that raises the value of this database is validating the 16,050 documents that
did produce facts, not recovering the rest. That is issue 1, and it is waiting
on a person.

## What was built or changed today

* `scripts/review_pack.py`, `tools/hla_review.html`, `tests/contracts/test_review_pack.py`
  (synthetic corpus; nothing reads the archive in tests).
* `kidneymatch.review.golden.LabelState.ABSENT` and its scoring, so a
  presence-typed gene can be labelled absent and contradict a pipeline PRESENT.
* `kidneymatch.ocr.ctc.digits_preserved`: the locus-digit fix (6b).
* The measurements above, all aggregate, from `facts.sqlite`.

## Order of work from here

1. Human: label the pack (issue 1). Everything else is ordered by what it says.
2. Agent: confirmer star-less parse (6a); re-run the decode pass (6b); score
   the labels per stratum.
3. Human: HA-006, HA-003, HA-005 (issue 4), and a "yes" for the empty-cell
   policy (issue 5, step 1).
4. Agent: HIST-001 → HIST-002 → caption claims (issue 3); ENTITY-001 spec
   and tables (issue 2); template discovery over the no-anchor population
   (6c).
