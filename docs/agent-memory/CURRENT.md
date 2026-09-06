# Current project state

**Updated:** 2026-09-05 (fourth session of the day)
**Canonical phase:** MVP-HIST
**Active task:** OCR-GEOM-001 (`docs/exec-plans/active/OCR-GEOM-001-geometry-and-drbx-row.md`); MEDIA-001/DEDUPE-001 stay READY

## Goal now
Validate what is extracted, and fix what the labels show. 220 of the pack's
1,650 cells are labelled (HA-008). Each session traces every non-correct cell
to a root cause and fixes it where the corpus bears it out (ADR 0009 §7). The
fourth found that the instrument itself was part of the problem: the page had
shown no crop for 50 of the 220 answers, and a pack rebuild used to orphan the
labels entirely.

## Locked facts
- **The archive is present**, local-only and gitignored, at
  `data/raw/ChatExport_2026-08-31`: 23,566 unique images, 90% above 900 px.
- **The source layer is parsed (HIST-001, HIST-002):** 180,441 messages,
  **zero unparsed fragments**; 23,565 of 23,566 documents link to their
  postings, 18,799 with caption text.
- **Extraction (ADR 0008, 0009 §7):** `facts.sqlite` refreshed in place with
  `refresh_facts.py` (snapshots beside it), which prints the per-locus
  comparison and names a stop signal — that comparison caught the `LAB`-as-HLA-B
  bug on 9,817 documents before it shipped. Every refresh's stop signal so far
  has been the later passes' writes being reset (all 15 swaps are DRB5 presence
  reverting to the row rule); re-run the passes in the order below.
- **Page geometry (`rulings/v3+lsd+sweep`):** sweep corroborates within 2°,
  calibrated on photographs (3°/0.7). 6,511 ROTATE / 14,139 STRAIGHT / 2,916
  UNCERTAIN; 1,591 levelled (KI-024). A tilt from stored boxes is biased.
- **Recognizers, against the labels** (67 cells, `ENGINE_BENCH_2026-09-05.md`):
  **PP-OCRv6-medium 65 exact**, shipped pipeline 57, v5-server 55, Qwen3-VL 52,
  Tesseract 32, ours 14. No pair agreed on a wrong value, which licenses the
  two-engine gates.
- **The decode and the confirmers.** `confirm_pass.py` has three targets;
  `promote_proposals.py` promotes CONFIRMED proposals — never on a LOW page,
  re-judged with admissibility, withdrawn when an equal-or-better reader
  disagrees. Crops stay axis-aligned; the upright ablation was a wash.
- **The DRB3/4/5 row prints gene names** (22,017 vs 75 bare numbers); grammar v2
  waits on HA-011. `drbx_reread.py` takes the digit only when it IS one.
- **The printed table is read as a grid (`ocr/lattice.py`):** rulings place a
  label the recognizer could not read (**+2,272**) and the second DRB3/4/5 slot,
  which ink certifies ABSENT when it is paper (**4,540 genes**).
  `cell_ink_pass.py` writes no fact: NOT_TESTED is HA-009's, so HA-012 asks.
- **Role resolves on 7,521 documents** (55% of those typed on 3+ loci).
- **Accuracy is unvalidated (KI-012); the binding constraint.**
  The reviewer's 220-cell export scored **84 correct** as the pack showed it and
  **113 correct / 86 correct abstentions / 10 missed / 2 partial / 9
  contradicted** now. All nine contradictions are HA-014, cells marked
  NOT_PRINTED where the page evidence says otherwise; the page had shown no crop
  for 50 of the 220. The blind golden corpus waits on a person.
- **THE REVIEWER'S NOTES ARE THE BEST DIAGNOSTIC WE HAVE. READ THEM** — they are
  in the export under `notes`, not in `pack_score.py`'s report
  (`CV_RESEARCH` s9). Seven were written; three named tilt and one named a
  column-header layout, and each was exactly right.
- **Rows are read along the slope the page prints them at** (`ocr/rows.py`,
  `ValueRule.row_slope`). The slope was already measured on every page the
  reviewer called tilted and thrown away by `MAX_MAD_DEG` (scatter is
  perspective, not a second grid) or `MIN_FRAME_TILT_DEG` (calibrated for
  rotating pixels, not for grouping boxes). Taken from the DOMINANT cluster of
  rulings, floored at 0.008 fall per unit width where the ablation turns
  net-positive. On the labels 64 to 67; corpus-wide **+209 second alleles**.
- **The whole page is read too** (`page_ocr_pass.py`, PP-OCRv5-server det+rec,
  local). Every other second opinion judges OUR crops and so cannot see a cell
  we never boxed. It finds MORE locus labels than our detector (142 of 160
  against 138) and is complementary, right on 7 cells ours misses and wrong on
  11 ours gets, so `page_ocr_bind.py` takes the union: our reading stands, the
  whole page is offered only unresolved cells. 15 s/page, so the pack yes, the
  corpus (100 h) not yet.
- **Two reading refusals get a second opinion (`reread_refused.py`).** An
  inadmissible first field, and a candidate that does not parse. PP-OCRv6 and
  PP-OCRv5-server must state the SAME value; single-engine yield was 97% and
  two-engine 75%. **+2,926 cells**, resumable by its own table.
- **A bare `A`, `B` or `C` can be a locus label** when the page's structure
  says so (+106 per 4,000 documents, none changed); the text matcher still
  refuses them. Ownership needs a quarter-label-height margin (+17). One box
  may print both alleles (`A*24,*02`, 1,819 tokens); `A*24,02` waits on HA-015.
- **A pack rebuild pins the labelled documents (`--keep-labelled`)** or the
  sample reshuffles and orphans them: 11 of 220 survived the first rebuild.
- **Google Vision measured, NOT adopted (`CV_RESEARCH` s8):** ours 62 of 160,
  Vision 28, right where we miss on one cell. **The finding that matters:** the
  23,719-cell "anchor found but no box in its cell" refusal is not a detector
  failure — Vision boxes something in 1.0% of 197 such cells against 89.0% of
  400 we resolved. That bucket is paper and closes through HA-012/HA-009.
- **Two form facts constrain the product:** DPA1/DPB1 printed, never filled
  (HA-009); the letterhead disclaims its blood-group field (KI-014).

## Decided (operator delegated)
HA-003 resolution bands (MID provisional) · HA-005 names as a salted hash ·
HA-006 IMGT 3.62 · HA-009 untested-locus policy (`HUMAN_ACTIONS.md`, Closed).

## Human actions open
**HA-014** re-answer the seven NOT_PRINTED cells (they carry crops now).
**HA-008 label the pack** — 220/1,650 done. **HA-007** the blind golden corpus.
**HA-011** the DRB3/4/5 grammar. Then HA-004 (blocks V1-MATCH), HA-001/2/10.

## Completed foundation
- P0 harness repair, P1 autonomy, P2 test depth (12-step gate, invariant
  traceability, coverage 65% / medical modules 100%, PII scanner, bandit,
  gitleaks, osv-scanner, mutmut).
- Derived local stores, all gitignored: `ocr_pass`, `facts`, `source`,
  `geometry` (sqlite), `data/review/hla_pack/`, `data/review/queue.json`.
  Committed measurements the thresholds rest on live in `config/`.

## Next actions
1. **Human: HA-014** (re-answer the seven), **HA-012** (the NOT_TESTED policy,
   now the largest single lever in the pipeline), then keep labelling (HA-008).
   Score with `pack_score.py` for the pack's view, `facts.sqlite` for the live one.
2. **Pass order after any refresh:** `decode_pass`, the three `confirm_pass`
   targets on tesseract5/ppocrv5/ppocrv6, `promote_proposals`, `drbx_ink_pass`,
   `cell_ink_pass`, `drbx_reread`, `reread_refused`. Rebuild the pack with
   `--keep-labelled <export>` or the labels are orphaned.
3. Agent: the 14 remaining misses are 6 with no anchor (the label is unreadable
   and no rule reaches it), 6 found-and-refused (ownership by reading-axis
   distance, `max_values`, two anchors on one row, a star-less value), 1 empty
   row and 1 unparsable. Then M6 after HA-011, KI-023, KI-027, MEDIA-001,
   DEDUPE-001, ENTITY-001. Human: HA-004 before matching beyond the ABO gate.

## Last verified baseline
`python scripts/verify_repo.py` PASS, 12 steps, 2026-09-05 (fourth session).
Re-run it yourself; this records a past result, not the current environment.
