# Open issues after P0–P7: diagnosis and solutions (2026-09-02)

Companion to `EXTRACTION_REVIEW_2026-09-02.md` (what was fixed) and
`OCR_MODEL_SURVEY_2026-09-02.md` (which other engines were tried). This document
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

Signals available today, cheapest first: the document hash (exact duplicate),
the sender hash and posting time (HIST-002 bundles), the printed role and ABO,
the HLA fingerprint, and (pending HA-005) a salted hash of the printed name.

Rules, to be written into the spec and tested first:

1. Identical file hash, or identical perceptual hash above the DEDUPE-001
   threshold: same *document*, one record, many postings.
2. Same sender hash, identical fingerprint on ≥3 resolved loci, ABO equal or
   unknown, roles not contradictory: `TIER_1` cluster, auto-linked, marked
   "pending human confirmation", usable for matching as one person.
3. Different senders, identical fingerprint on ≥4 loci: `TIER_2` candidate,
   review only. A fingerprint on <4 loci never proposes a link.
4. Any conflict (two ABO groups, two roles that are not a comparison sheet,
   DRB1/DRBX inconsistency between members) blocks the cluster and lands it
   in the queue.
5. Name hash, once HA-005 is decided, is an *additional* signal for tier 1 and
   never a sufficient one: two people can share a name, and the name field is
   the most misread field on the form.

Storage: a `person_cluster` table (cluster id, tier, evidence list with
provenance to each document) and a `merge_decision` table (human decisions,
append-only, reversible). Matching (`MATCH-001`) reads clusters, never
documents, and treats a cluster with an open conflict as UNKNOWN.

**One check before designing further:** the 67-document fingerprint. If it is
one person, reposting dominates and tier 1 will collapse most of the
duplication. If it is many people, the fingerprint is an OCR or template
artefact (a value printed on the form itself), and rule 2 is unsafe as written.
The pack will show this if any of those documents were drawn; otherwise a
targeted look is a ten-minute task for the labeller.

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

**Fix (small, testable):** let the confirmer compare digits when its reading
is a locus letter followed by digits with the star missing, exactly as
`digits_preserved` now does for the decode. Expected to move a large share of
class I UNCONFIRMED to CONFIRMED or CONTRADICTED, either of which is
information; UNCONFIRMED is not. A second, independent confirmer from the OCR
survey is the other route (see that document).

### 6b. The decode's DIGITS_LOST verdict fires on the locus digit

Re-examined 300 demoted cells (349 boxes): **240 fired because the greedy path
dropped the star**, so the `1` of `DRB1` was compared as a value digit; 108 were
the decode adding a digit the model did not read, which is a real loss and must
stay flagged; 1 other. Fixed today in `kidneymatch.ocr.ctc.digits_preserved`
(letters stripped, one locus digit forgiven, value digits must survive in
full), with tests pinning both directions. Re-running `scripts/decode_pass.py`
after the pass in flight completes will restore roughly two thirds of the 1,191
demoted facts to UNANIMOUS without changing a single value.

`SPLIT` was checked the same way and is sound: 93–100% of SPLIT cells per locus
are real digit disagreements between offsets, not prefix rendering. C is the
unstable locus (30% SPLIT on FORM#1 versus 3–4% for A and B): the narrowest
crops with the `Cw` prefix.

### 6c. The 7,516 zero-fact documents are two populations

| population | docs | what the OCR boxes contain |
|---|---:|---|
| no locus label anchored anywhere | 4,944 | 79% of zero-fact docs have label-shaped AND allele-shaped boxes; the labels just do not anchor |
| labels anchored, every cell refused | 2,572 | "N candidates exceeds 2" and "2 anchors" dominate: multi-column layouts |
| genuinely not a report (fewer than 8 boxes, or no text) | 209 | photos of people, chat screenshots |

The label shapes that fail to anchor, by documents containing them: bare `A`
(3,058 docs), bare `C` (740), bare `B` (507), `DQ` (302), `DR` (212), `CW` (55),
`DRB` followed by digits (47). These are forms that print class I loci without
the `HLA-` prefix and class II loci as serologic families. The resolver
requires the prefix for class I on purpose (a bare `A` is also a blood group
and a grade), and the doctrine says OCR text alone may not assign a locus. The
way through is the one the doctrine names: **template geometry**. Cluster the
4,944 no-anchor documents by layout, have a human read five exemplars per
cluster (this is P6, the PCR-SSP form, and it is larger than the 2,631 first
estimated), and write a family rule where a bare `A` anchors only when the
template places it in the class I label column.

The pack now draws twenty documents from these two populations so the labeller
sees what they are.

---

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
