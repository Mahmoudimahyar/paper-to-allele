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
- [~] M4 `ocr/crops.py`: one place cuts every crop; `RAW`, `CONFIRMER_PADDED` and `TESSERACT` reproduce today's crops byte for byte (pinned against the old arithmetic inline); upright crops through the page rotation and a glyph-height profile exist and map back to source pixels. `decode_pass.py` delegates to it (default unchanged; `--frame` cuts upright crops on levelled pages under a `+frame` decoder version). **Pending:** `confirm_pass.py` (its Tesseract upscale is PIL Lanczos; switching interpolation is itself a change to ablate) and the ablation on the labelled cells.
- [ ] M5 `ocr/rulings.py` lattice: cells from the rulings; empty cells certified by ink; DRB3/4/5 slot identity by column; used only when the lattice agrees with the label stack.
- [ ] M6 DRB3/4/5 grammar v2 (`GROUPED_DRBX/v2`): typed slots, allele proposals, bare number → REVIEW with candidate genes; spec/ADR changes first (HLA_VALIDATION_SPEC §7, OCR_SPEC, OCR-001 1.1.0, ADR 0010).
- [ ] M7 Docs and memory: research record, KNOWN_ISSUES, CURRENT.md, handoff; adversarial review pass of the diff.

## Acceptance commands
```bash
uv run --frozen --extra hist python -m pytest tests/unit/test_rulings.py tests/unit/test_page_geometry.py tests/unit/test_crops.py tests/unit/test_grouped_drbx.py tests/unit/test_golden_labelling.py -q
uv run --frozen python scripts/pack_score.py --export <the reviewer's golden-labels/v1 export>
python scripts/verify_repo.py
```

## Progress log
- 2026-09-05: 165-label export scored; DRB3/4/5 diagnosis; one-row question shipped to the live pack (`--page-only`); partial-read scoring; research workflow (6 lenses, 6 skeptics, 3 code maps) synthesised.
- 2026-09-05: `rulings.py` (24 tests) and `geometry_pass.py` (4 contract tests); pass over the 150-document pack; decision rule calibrated on real photographs (scatter bound 0.5→1.5 deg refused 79/150 pages; verticals demoted to a flag). Of the 21 misses only 1 sits on a ROTATE page — the misses are glued label+digit tokens, so the star-less parser shipped first and recovered 5 of them; tilt handling continues for the corpus (35% of pack pages rotate ≥0.5 deg).

## Decision log
- Rulings angle via `cv2.createLineSegmentDetector`, not morphological kernels: the kernels return 0 segments at 7.3°; LSD measured 9.4 ms/img, <0.01° on synthetic.
- Rotate the geometry (stored boxes) before the pixels: zero pixel cost for row assignment; pixels are rotated only for crops on ROTATE pages.
- Never rotate on one estimator: LSD and the projection sweep must agree within 1°.
- A declared partial read (`second_allele=UNREAD`, one allele inside the printed pair) scores as `partial`; without the declaration a single value against a pair stays a false acceptance.
- The DRB3/4/5 row is one review question; storage stays per gene (HLA_VALIDATION_SPEC §7).

## Verification evidence
- `pack_score.py` on the 165-cell export → 50 correct / 75 correct abstentions / 21 missed / 1 partial / 18 contradicted, 17 of them DRB3/4/5 protocol artefacts.
- Browser: 22/22 assertions on the one-row DRB3/4/5 question (fabricated demo pack); real pack renders one row, 9/9 crops.

## Rollback
- Page: `git checkout tools/hla_review.html` then `review_pack.py --page-only`.
- Facts: v1 rows are never rewritten; v2 rows are keyed by `EXTRACTION_VERSION`; `--frame identity`.
- Crops: profile `raw`.

## Handoff / next actions
1. When `geometry_pass.py --status` covers the corpus: re-extract `facts.sqlite` in place with `--geometry`, then `decode_pass.py` and `confirm_pass.py` for the new cells (both resumable; the delta is ~2,400 cells).
2. Reviewer re-confirms the DRB3/4/5 rows on the 15 labelled documents with the new question, then keeps labelling; score every export with `pack_score.py`.
3. M4 remainder: switch `confirm_pass.py` to `ocr.crops` and run the ablation (raw vs upright vs glyph-height) on the labelled cells; M5 lattice; M6 after HA-011.
4. The NEXT review pack (never rebuild the one in progress) gains a `tilted` stratum keyed on `document.tilt_deg` and a `frame_used` tag, so the frame's effect is labelled directly.
5. Hygiene: one OpenCV wheel in the lockfile (KI-023).
