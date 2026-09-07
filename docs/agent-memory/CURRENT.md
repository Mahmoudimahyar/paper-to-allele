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
  the reviewer sees a RESOLVED value with no crop (s14, twice).
- **The DRB3/4/5 row prints gene names**; grammar v2 waits on HA-011.
- **The printed table is read as a grid (`ocr/lattice.py`):** rulings place an
  unreadable label (**+2,272**) and the second DRB3/4/5 slot. NOT_TESTED is
  HA-012's.
- **Accuracy (KI-012), 1,342 labels over 4 rounds (s18). LEAD WITH RECALL,
  NOT PRECISION** — the reviewer experiences how often the answer was THERE.
  HLA: recall **85.1%** of cells a person read (692/813), precision 98.0%, 14
  wrong. ROLE recall 84.4%. **ABO recall 47.9%, RH 46.9%** (precision 100%;
  50/51 misses). Round four, the hard one: HLA 81.9%, ABO 36%.
- **The s18 loss list is DONE — all eight (s19-s22).** On the same 1,342
  labels: HLA **666 correct, 5 wrong, precision 99.3%** (was 692/14, 98.0%);
  recall 82.4% (was 85.1%) because items 5+6 deliberately withdrew 2,928 cells
  to review. ROLE 93/2, ABO 48/0, RH 47/0. Coverage ROLE **79.9%**, ABO
  **47.3%**, RH **42.4%**, HLA **67,649** value cells.
- **3,685 cells from nine NEW sources are UNMEASURED** (s22): upright+rotated
  801, column-bound 699, token-anchored-drbx 621, family-tie 550, below-rule
  364, family-loo 258, family-prefix 204, column-named 108, anchor-row 80. Each
  has a source, a stratum and a withdrawal handle; three have `MIN_DRAW`
  floors. **Round five is what measures them.**
- **THE REVIEWER'S NOTES ARE THE BEST DIAGNOSTIC WE HAVE** — under `notes`,
  printed by `label_score.py` (s9).
- **Rows are read along the page's own slope** (`ocr/rows.py`): the dominant
  ruling cluster, floored at 0.008. **+209 second alleles**.
- **The whole page is read too** (`page_ocr_pass.py`) and our boxes again by
  PP-OCRv6 (`rerecognise_pass.py`); strictly additive.
- **REFUSALS AND MISSES ARE DIFFERENT POPULATIONS** (s11, s17): refused cells
  are blank paper; MISSED cells have their digits in the stored OCR 88% of the
  time — read but unbound. Opposite fix.
- **611 pages were photographed SIDEWAYS** (s17, `upright_pass.py`): 0 of them
  anchored any locus. Turned, 425 anchor and **801 cells resolve**. The metric
  is box height>width IN PIXELS — normalised coords make it meaningless.
- **A bare `A`/`B`/`C` can be a locus label** when structure says so (+106 per
  4,000). `A*24,02` is HA-015.
- **A pack rebuild pins labelled documents (`--keep-labelled`)** or the sample
  reshuffles: 11 of 220 survived the first rebuild.
- **The chat is a source of record** (`caption_pass.py`, s13/s16): caption ABO
  validated at 14 correct, 0 wrong; the s15 worry was a question mismatch.
- **One printed value can be detected twice** (`_one_token_read_twice`, s16):
  both engines box the same ink and agree. **+993 documents, 0 lost, 0 value
  changes**; ABO 45.6%, RH 40.7%. Gate 1 (identical values) does all the work.
- **A bare role word IS read** (`FORM_FIELD_BARE`, `role_repass.py`, s15):
  refusing it double-charged evidence already gated above. **ROLE 78.1%**;
  measured 8 right, 1 wrong on the labels.
- **A stratum reporting zero looks like a signal that does not occur** (3x).
  The summary prints what each is CARRIED by; a gate naming a COUNT uses
  `MIN_DRAW`, not a weight share (s21).
- **A value box unlike its page's others is wrong 5x as often** (`boxsize.py`,
  25% vs 5%, n=8): marks for review, gates nothing yet.
- **A locus can come from the allele's printed prefix** (s12): 4,767 cells;
  and from its COLUMN on a two-person sheet (s21, `column_bind.py`, +699).
- **Review a write-rule adversarially BEFORE believing its yield** (s14/16/20):
  one rule's first version had 83% fail the project's own gates, a workflow
  refused 28 of 28 proposals, and all four s20 builds were rejected.
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
