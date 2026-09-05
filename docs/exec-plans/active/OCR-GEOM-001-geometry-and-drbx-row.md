# OCR-GEOM-001 — Page geometry, ruled cells, and the DRB3/4/5 row as one question

**Status:** ACTIVE
**Feature spec:** `specs/features/OCR-001-hla-extraction.json` (invariants: geometry defines locus; unknown is valid output; every accepted field has source crop/bbox)
**Owner/session:** claude, 2026-09-05, from the reviewer's feedback on the first 165 anchored labels

## Objective

Recover the cells the pipeline abstains on because the page is tilted or the
detector merged a label with its value, stop asking the reviewer three questions
about one printed DRB3/4/5 row, and make every change measurable against the
labels the reviewer is producing. Order follows measured gain per unit of risk
(research synthesis in `docs/ingestion/CV_RESEARCH_2026-09-05.md`).

What the 165 labels said (`scripts/pack_score.py`, counts only):

- 17 of the 19 "contradictions" were the labelling page, not the pipeline: every
  DRB3/4/5 "value" the reviewer typed was 03, 04 or 05 — the digit of a printed
  gene NAME — because the page asked for two alleles per gene. The row prints
  names (14 of 14 raw tokens gene-shaped, 0 digit-shaped).
- Of the two real B contradictions, one is a declared partial read (one allele
  read, second UNREAD, the allele is in the printed pair) and one is a wrong
  single allele the decode already marks SPLIT and PP-OCRv5 CONTRADICTED.
- 21 misses: 9 are a label glued to a digit in one detector box (`CN`, `AN`,
  `DQBN`…), 5 are "no anchor" on HIGH-quality pages, 3 "too many candidates",
  3 grouped-header misses, 1 empty cell.

## Non-goals

- Learned dewarpers, table transformers, or any model over all 23,500 images.
- Inferring a DRB3/4/5 gene or allele from DRB1 (policy: never).
- Any cloud OCR/VLM; any change that raises wrong-locus false acceptance.

## Required context

`src/kidneymatch/ocr/{anchors,drbx,templates,ctc,confirm}.py`, `scripts/{ocr_pass,extract_facts,decode_pass,confirm_pass,review_pack,pack_score}.py`,
`docs/ingestion/OCR_SPEC.md` §2 §6 §7, `docs/clinical/HLA_VALIDATION_SPEC.md` §7, ADR 0006–0009,
`docs/operations/WORKSTATION_STABILITY.md` (keep every pass light and resumable).

## Risks / invariants

- Geometry defines locus; token text never assigns one (OCR_SPEC §2). The
  rectified frame changes *where* boxes are, never *what* binds to what.
- A wrong page angle silently mis-rows everything: rotate only when two
  independent estimators agree, otherwise the identity frame and `UNCERTAIN`.
- The primary recogniser loses 56 points on a 0.4 % crop pad: every crop change
  is ablated against the labels before it ships.
- Provenance boxes stay in the ORIGINAL image frame; the transform is stored.
- No allele value, caption or crop of a real report is printed or committed.

## Milestones

- [x] M0 `pack_score.py`: score an anchored export per locus and stratum; DRB3/4/5 shape diagnostics; declared partial reads are `partial`, not false acceptances (`golden.py`, `golden_score.py`, `golden_tasks.py`).
- [x] M1 Review page: the DRB3/4/5 row is one question (tick the printed genes; allele only if printed); per-gene labels derived; legacy per-gene numbers shown as "re-confirm".
- [x] M2 `ocr/rulings.py` + `scripts/geometry_pass.py`: page angle from printed rulings (LSD) cross-checked by a projection sweep; STRAIGHT / ROTATE / UNCERTAIN; perspective flag; `data/derived/geometry.sqlite`, resumable. Calibrated on the pack (v2): 53 ROTATE / 71 STRAIGHT / 26 UNCERTAIN; ~60 ms per image.
- [x] M2b The star the recognizer did not read: `A02` for `A*02` parses with its prefix (marked repaired), `8*44` repairs the B/8 prefix confusion, `Cw` names C. Corpus: +2,368 cells REVIEW→RESOLVED, 46 the other way (all the KI-015 second-allele guard), 0 changed values; 5 of the 21 misses on the labelled documents now RESOLVED and equal to the human, 0 contradictions.
- [x] M3 `ocr/geometry.py`: rectify stored boxes into the page frame (rotate the geometry, not the pixels); `extract_facts.py --geometry` applies it from 1.5 deg of ROTATE. Measured on the pack's tilted pages: under 1.5 deg the frame gained and lost 9 cells each (estimator error ≈ tilt), from 2 deg it gained 5 and lost 0 — hence the gate. Provenance stays in the stored frame; `document.tilt_deg`/`frame` recorded.
- [x] M4 `ocr/crops.py`: one place cuts every crop; `RAW`, `CONFIRMER_PADDED` and `TESSERACT` reproduce today's crops byte for byte (pinned against the old arithmetic inline); upright crops through the page rotation and a glyph-height profile exist and map back to source pixels. `decode_pass.py` delegates to it (default unchanged; `--frame` cuts upright crops on levelled pages under a `+frame` decoder version). **Done 2026-09-05:** the ablation (`decode_pass.py --frame --only-levelled`, 3,727 cells on the 1,591 levelled pages) is a wash — UNANIMOUS 81.4% axis-aligned against 82.3% upright, 95 cells one way and 87 the other, 4.6% of resolved readings differ — so the default crops stay axis-aligned and the frame keeps doing its work at row assignment. `confirm_pass.py` keeps its own cropping (PIL Lanczos for Tesseract) for the same reason: nothing measured says to change it.
- [x] M5 (2026-09-05, as `ocr/ink.py` + `scripts/drbx_ink_pass.py` rather than a rulings lattice): the grouped row's second slot is placed by the DRB1 row's two value boxes and its ink measured with the rulings removed. Calibrated on 4,904 columns holding a read token (none under 0.005 ink, 8 under 0.2 coverage): BLANK at <0.002 ink, <0.05 coverage, run <6. Corpus: 2,410 one-token rows placed, 1,669 BLANK → 3,338 genes ABSENT with the paper region as provenance, 442 INKED → 884 cells to review (a token no engine read), 15 unmeasurable, 284 not placed; 2,178 one-token cells stay UNKNOWN for want of DRB1 geometry. On the labels: the 4 rows the reviewer marked ABSENT all measured as paper; no PRESENT cell became ABSENT. A rulings lattice is no longer needed for this; the ruling-based cell grid stays a non-goal until a labelled miss asks for it.
- [ ] M6 DRB3/4/5 grammar v2 (`GROUPED_DRBX/v2`): typed slots, allele proposals, bare number → REVIEW with candidate genes; spec/ADR changes first (HLA_VALIDATION_SPEC §7, OCR_SPEC, OCR-001 1.1.0, ADR 0010).
- [x] M4b The second labelled export (187 cells, 2026-09-05): every non-correct cell traced to a root cause and the causes fixed where the corpus bore them out — the DQB1 label read `DOBI` (canonicaliser v2: Q-as-O, trailing punctuation, `ILA`/`IILA` prefixes; +2,411 DQB1 resolved), the family rule's over-full cells (prefix-consistent filtering; +459), the default rule's empty cells (a 1.5-height tolerance band as a fallback; +901 cells and 890 second alleles, 0 boxes bound twice), the grouped header's B-slot misreads (header v2; +1,056 DRB3/4/5 calls), the S-for-5 repair certifying absence (KI-026), and the decode's PROPOSAL never becoming a fact (`confirm_pass.py --target proposals` + `promote_proposals.py`). Geometry v3: sweep bound 2°, agreement check calibrated (3°/0.7); 6,511 ROTATE / 2,916 UNCERTAIN.
- [x] M4c The review pack shows the messages posted with each image (`review_pack.py --augment-messages`; `tools/hla_review.html` Messages block; caption claim beside Role), in place on the pack in progress.
- [x] M7 Docs and memory: ADR 0009 §7, KI-025/KI-026, CURRENT.md, handoff (2026-09-05, third session); adversarial review pass of the diff (24 findings, all fixed).

## Acceptance commands
```bash
uv run --frozen --extra hist python -m pytest tests/unit/test_rulings.py tests/unit/test_page_geometry.py tests/unit/test_crops.py tests/unit/test_grouped_drbx.py tests/unit/test_golden_labelling.py -q
uv run --frozen python scripts/pack_score.py --export <the reviewer's golden-labels/v1 export>
python scripts/verify_repo.py
```

## Progress log
- 2026-09-05: 165-label export scored; DRB3/4/5 diagnosis; one-row question shipped to the live pack (`--page-only`); partial-read scoring; research workflow (6 lenses, 6 skeptics, 3 code maps) synthesised.
- 2026-09-05: `rulings.py` (24 tests) and `geometry_pass.py` (4 contract tests); pass over the 150-document pack; decision rule calibrated on real photographs (scatter bound 0.5→1.5 deg refused 79/150 pages; verticals demoted to a flag). Of the 21 misses only 1 sits on a ROTATE page — the misses are glued label+digit tokens, so the star-less parser shipped first and recovered 5 of them; tilt handling continues for the corpus (35% of pack pages rotate ≥0.5 deg).
- 2026-09-05 (later): page frame wired (`--geometry`, from 1.5 deg); `ocr/crops.py` with the decode pass on it; `tilted` stratum for the next pack; corpus geometry pass complete (5,486 ROTATE / 14,209 STRAIGHT / 3,871 UNCERTAIN). Adversarial review (3 lenses, 19 refuters) confirmed 18 findings; the behavioural ones fixed and pinned: star-less digits must be literal digits (`ALL` was A*11), star-less values resolve only under the family rule (557 held for review elsewhere), a printed allele beside a present DRB3/4/5 gene is not a contradiction, one `classify()` for both scorers, bimodal rulings and sideways pages refused, calibrated constants pinned, `run()` tested. Main `facts.sqlite` refreshed in place via `refresh_facts.py`: 95,991 resolved (was 93,202), 1,205 levelled pages, 3,959 cells changed or new and sent back through the decode/confirm passes.

- 2026-09-05 (third session): the 187-cell export — 29 missed / 4 contradicted / 2 partial under the refreshed facts. Root causes measured corpus-wide and fixed (M4b); the `LA` prefix bug caught by the refresh comparison (9,817 B cells "2 anchors found") before it shipped; facts refreshed again: HLA/DRB3/4/5 resolved 82,480 → 85,821, 15,614 cells changed or new, 0 values swapped.
- 2026-09-05 (third session, later): PP-OCRv5 over 2,026 proposals (778 CONFIRMED / 885 CONTRADICTED) and 19,372 gene boxes; 775 cells promoted; adversarial review (7 lenses, 133 agents) confirmed 24 findings, all fixed: every gate under the widened alignment, the grouped header as an owner, no band from a tall anchor, geometric gates before any parse, a quote-star stub never anchors, `confirm_gene` abstains on an `S` and reads pairs, promotion re-judged with admissibility and never on LOW pages, pack messages deduplicated across exports with "8 of N" and "not loaded" distinct from "none", the refresh comparison as a step of `refresh_facts.py`, the agreement window pinned on a two-grid image.
- 2026-09-05 (fourth pass): Tesseract over the 5,859 changed cells (1,881 / 949 / 3,029); the upright-crop ablation is a wash (M4 closed); the KI-026 reinstatement rule refuted by the labels (3 of 4); `ocr/ink.py` and `drbx_ink_pass.py` (M5) with 12 synthetic tests; the next pack gains `promoted` and `ink_certified` strata; `refresh_facts.py` names the passes to re-run. Export 2: 87 / 71 / 23 / 4 / 2.

## Decision log
- Rulings angle via `cv2.createLineSegmentDetector`, not morphological kernels: the kernels return 0 segments at 7.3°; LSD measured 9.4 ms/img, <0.01° on synthetic.
- Rotate the geometry (stored boxes) before the pixels: zero pixel cost for row assignment; pixels are rotated only for crops on ROTATE pages.
- Never rotate on one estimator: LSD and the projection sweep must agree within 1°.
- A declared partial read (`second_allele=UNREAD`, one allele inside the printed pair) scores as `partial`; without the declaration a single value against a pair stays a false acceptance.
- The DRB3/4/5 row is one review question; storage stays per gene (HLA_VALIDATION_SPEC §7).
- A slot that rests on the S-for-5 repair certifies no absence: the other genes are REVIEW_REQUIRED, never ABSENT (7 of 10 labelled ABSENT calls beside a repaired token were wrong).
- The default rule's tolerance band is a FALLBACK (consulted only when the overlap test read nothing, or one allele with its partner unread), never a widening: as a first criterion it also refused 799 cells that resolved.
- A decode PROPOSAL becomes a fact only when PP-OCRv5 reads the same digits from the same crop; the promoted fact says so in `source` and `reason`.
- No third tilt estimator from the stored boxes (KI-025: biased 1.44° median, 106 pages to gain).
- Ink says paper or not-paper, never which gene: a BLANK slot certifies ABSENT, an INKED slot no engine read goes to a person; the slot is placed by the form's own DRB1 row, never guessed.
- Upright crops stay an option, not the default: the ablation moved unanimity by under a point either way.

## Verification evidence
- `pack_score.py` on the 165-cell export → 50 correct / 75 correct abstentions / 21 missed / 1 partial / 18 contradicted, 17 of them DRB3/4/5 protocol artefacts.
- Browser: 22/22 assertions on the one-row DRB3/4/5 question (fabricated demo pack); real pack renders one row, 9/9 crops.

## Rollback
- Page: `git checkout tools/hla_review.html` then `review_pack.py --page-only`.
- Facts: v1 rows are never rewritten; v2 rows are keyed by `EXTRACTION_VERSION`; `--frame identity`.
- Crops: profile `raw`.

## Handoff / next actions
1. Done 2026-09-05: corpus geometry complete, `facts.sqlite` refreshed in place (`refresh_facts.py`), 3,959 changed cells sent through `decode_pass.py` and both confirmers — finished: 3,212 decoded (2,045 UNANIMOUS / 610 SPLIT / 465 DIGITS_LOST / 75 PROPOSAL / 17 ILLEGIBLE), 3,052 confirmed against PP-OCRv5 (2,490 CONFIRMED / 373 CONTRADICTED / 189 no opinion) and Tesseract (410 / 454 / 2,188). The recovered cells are harder than the corpus average (64% unanimous against 94%), and about a third of them route to review; no resolved HLA cell is left NOT_CHECKED.
2. Reviewer re-confirms the DRB3/4/5 rows on the 15 labelled documents with the new question, then keeps labelling; score every export with `pack_score.py`.
3. M4 remainder: switch `confirm_pass.py` to `ocr.crops` and run the ablation (raw vs upright vs glyph-height) on the labelled cells; M5 lattice; M6 after HA-011.
4. The NEXT review pack (never rebuild the one in progress) gains a `tilted` stratum keyed on `document.tilt_deg` and a `frame_used` tag, so the frame's effect is labelled directly.
5. Hygiene: one OpenCV wheel in the lockfile (KI-023).
