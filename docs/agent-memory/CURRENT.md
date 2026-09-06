# Current project state

**Updated:** 2026-09-06 (fifth session)
**Canonical phase:** MVP-HIST
**Active task:** OCR-GEOM-001 (`docs/exec-plans/active/OCR-GEOM-001-geometry-and-drbx-row.md`); MEDIA-001/DEDUPE-001 stay READY

## Goal now
Validate what is extracted, and fix what the labels show. **561 cells labelled**
over two rounds (HA-008); round three is packed and waiting. Trace every
non-correct cell to a root cause and fix it where the corpus bears it out (ADR
0009 §7). Two sessions running, the INSTRUMENT was part of the problem: no crop
shown for 50 of 220 answers, then two strata reporting zero when neither was
empty (`CV_RESEARCH` s13). Check the instrument before the pipeline.

## Locked facts
- **The archive** (local-only, gitignored, `data/raw/ChatExport_2026-08-31`):
  23,566 images, 90% >900 px; 180,441 messages parsed, ZERO unparsed.
- **Extraction (ADR 0008, 0009 §7):** `refresh_facts.py` prints the per-locus
  comparison against its snapshot — that caught the `LAB`-as-HLA-B bug on 9,817
  documents. ALWAYS compare; every stop signal so far is later passes being
  reset, so re-run them.
- **Page geometry (`rulings/v3+lsd+sweep`):** 6,511 ROTATE / 14,139 STRAIGHT /
  2,916 UNCERTAIN; 1,591 levelled (KI-024). A tilt from stored boxes is biased.
- **Recognizers** (`ENGINE_BENCH_2026-09-05.md`): PP-OCRv6 65 of 67 exact,
  shipped 57, ours 14. No pair agreed on a WRONG value: the two-engine gates
  rest on that.
- **The confirmers.** Three `confirm_pass` targets; `promote_proposals` never
  promotes on a LOW page. **Every binding pass must write `value_boxes`** or
  the reviewer sees a RESOLVED value with no crop (s14; happened twice).
- **The DRB3/4/5 row prints gene names**; grammar v2 waits on HA-011.
  `drbx_reread.py` takes the digit only when it IS one, and sees both boxes.
- **The printed table is read as a grid (`ocr/lattice.py`):** rulings place an
  unreadable label (**+2,272**) and the second DRB3/4/5 slot, ink-certified
  ABSENT when paper (**4,540 genes**). NOT_TESTED is HA-012's to answer.
- **Accuracy is unvalidated (KI-012); the binding constraint.** 561 labels:
  **310 correct, 205 abstained, 35 missed, 2 partial, 9 contradicted** — 87.1%
  of the 356 cells a person actually read. Round one alone went 84 -> 121.
  Contradictions are HA-014. `scripts/label_score.py` scores any number of
  exports against LIVE facts, no pack needed. Golden corpus waits on a person.
- **THE REVIEWER'S NOTES ARE THE BEST DIAGNOSTIC WE HAVE. READ THEM** — under
  `notes`, printed by `label_score.py` (s9). 14 annotated pages hold 26 of the
  35 misses.
- **Rows are read along the page's own slope** (`ocr/rows.py`): the DOMINANT
  ruling cluster, floored at 0.008. It was already measured on every tilted
  page and thrown away by thresholds meant for rotating pixels. **+209**.
- **The whole page is read too** (`page_ocr_pass.py`) and our boxes again by
  PP-OCRv6 (`rerecognise_pass.py`); strictly additive. On the worst annotated
  pages the whole-page engine finds FEWER boxes than ours (s14).
- **DO NOT chase the OCR further without reading `CV_RESEARCH` s11.** Six
  measurements: detection is not the constraint, recognition is 3.3% of the
  loss, and **84.3% of refused cells never got a box from any engine** — blank
  paper. The rest is HA-012/014/011.
- **`reread_refused.py`: both engines must state the SAME value. +2,926 cells.**
- **A bare `A`/`B`/`C` can be a locus label** when structure says so (+106 per
  4,000). One box may print both alleles; `A*24,02` is HA-015.
- **A pack rebuild pins labelled documents (`--keep-labelled`)** or the sample
  reshuffles: 11 of 220 survived the first rebuild.
- **Google Vision measured, NOT adopted (s8):** ours 62 of 160, Vision 28; it
  boxes something in 1.0% of "no box in its cell" refusals — they are paper.
- **The chat is a source of record.** `caption_pass.py` reads ABO/Rh/Role from
  EVERY message posted with a document: ABO **42.6%**, RH **37.6%** (s13). But
  the labels CANNOT judge those: every disagreement is against NOT_PRINTED —
  the reviewer answers "what does this page print", the pass answers "what is
  this person's group" (s15). Unvalidated, not disproven.
- **A bare role word IS read** (`FORM_FIELD_BARE`, `role_repass.py`, s15).
  Refusing it double-charged evidence already gated above; on 50 labelled roles
  a bare word is right 13 times, wrong once. **ROLE 67.4% -> 78.1%.**
- **A stratum reporting zero looks exactly like a signal that does not occur.**
  Two did and neither was empty: a wrong column name swallowed by a blanket
  `except`, and a rare stratum pooled away by a common one. Pools are now by
  MEASURED rarity; read corpus-wide counts when adding a stratum.
- **A value box unlike its page's others is wrong 5x as often** (25% vs 5%,
  `ocr/boxsize.py`); n=8, so it MARKS for review and gates nothing yet.
- **A locus can come from the allele's own printed prefix** (`prefix_bind.py`,
  s12) where the page labels no row: **4,767 cells**, tried last, comparison
  sheets refused. HA-017 holds the AGENTS.md wording.
- **`anchor_row_bind.py` (s14): 80 cells, ACCURACY UNMEASURED.** Its first
  version bound 458 and an adversarial review confirmed 11 defects: no gap cap,
  no direction, and it resolved values inside another locus's cell — the case
  `resolve_locus` reserves for a human. Those writes were REVERTED; 83% failed
  this project's own rules. **Review a write-rule adversarially BEFORE
  believing its yield.**
- **Two form facts:** DPA1/DPB1 printed but never filled (HA-009); the
  letterhead disclaims its blood-group field (KI-014).

## Decided (operator delegated)
HA-003 resolution bands (MID provisional) · HA-005 names as a salted hash ·
HA-006 IMGT 3.62 · HA-009 untested-locus policy (`HUMAN_ACTIONS.md`, Closed).

## Human actions open
**HA-014** re-answer the seven NOT_PRINTED cells (they carry crops now).
**HA-008 label the pack** — 561 cells over two rounds; round three (60
documents) is packed and served on 8768. **HA-007** the blind golden corpus.
**HA-011** the DRB3/4/5 grammar. Then HA-004 (blocks V1-MATCH), HA-001/2/10.

## Completed foundation
P0 harness, P1 autonomy, P2 test depth (12-step gate, coverage 65% / medical
100%, PII scanner, bandit, gitleaks, osv-scanner, mutmut). Derived stores are
gitignored (`ocr_pass`, `facts`, `source`, `geometry`, `data/review/`); the
measurements the thresholds rest on are committed in `config/`.

## Next actions
1. **Human: HA-014** (re-answer the seven), **HA-012** (the NOT_TESTED policy,
   now the largest single lever in the pipeline), then keep labelling (HA-008).
   Score with `pack_score.py` for the pack's view, `facts.sqlite` for the live one.
2. **Pass order after any refresh:** `decode_pass`, the three `confirm_pass`
   targets on tesseract5/ppocrv5/ppocrv6, `promote_proposals`, `drbx_ink_pass`,
   `cell_ink_pass`, `drbx_reread`, `reread_refused`, `page_ocr_bind`,
   `rerecognise_pass`, `prefix_bind`, `caption_pass`. Rebuild the pack with
   `--keep-labelled <export>` or the labels are orphaned; `--skip-labelled`
   instead when the point is to show a reviewer what they have NOT yet seen.
3. **Agent: work the annotated documents** (`CV_RESEARCH` s14). The 14 pages
   with a reviewer note hold **26 of the 35 misses and 5 of the 9
   contradictions**. Measured: the two "bare A" pages fail because NO engine
   emits an `A`/`B`/`C` box, not because a rule refuses. Then M6 after HA-011,
   KI-023, KI-027, MEDIA-001, DEDUPE-001, ENTITY-001. Human: HA-004.

## Last verified baseline
`python scripts/verify_repo.py` PASS, 12 steps, 2026-09-05 (fourth session).
Re-run it yourself; this records a past result, not the current environment.
