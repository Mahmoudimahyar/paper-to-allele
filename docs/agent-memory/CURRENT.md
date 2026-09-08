# Current project state

**Updated:** 2026-09-07 (sixth session)
**Canonical phase:** MVP-HIST
**Active task:** OCR-GEOM-001 (`docs/exec-plans/active/OCR-GEOM-001-geometry-and-drbx-row.md`); MEDIA-001/DEDUPE-001 stay READY

## Goal now
Gold DB built and deduplicated; matching evidence review done, waits on HA-004.
Round five (`--n 600`, on 8767) still measures the ~3,900 unlabelled-source
cells; then D2-a exports tiers A/B/C, review and unknown separately. Check the
instrument before the pipeline.

## Locked facts
- **The archive** (local-only, gitignored, `data/raw/ChatExport_2026-08-31`):
  23,566 images, 90% >900 px; 180,441 messages parsed, ZERO unparsed.
- **Extraction (ADR 0008, 0009 §7):** `refresh_facts.py` prints the per-locus
  comparison against its snapshot — that caught the `LAB`-as-HLA-B bug on 9,817
  documents. ALWAYS compare, and bracket every pass with a status snapshot.
- **Page geometry (`rulings/v3+lsd+sweep`):** 6,511 ROTATE / 14,139 STRAIGHT /
  2,916 UNCERTAIN; 1,591 levelled (KI-024). A tilt from stored boxes is biased.
- **Recognizers** (`ENGINE_BENCH_2026-09-05.md`): PP-OCRv6 65 of 67 exact,
  shipped 57, ours 14. No pair agreed on a WRONG value — the two-engine gates
  rest on that, and D6-a re-promoted 123 gate-1 withdrawals on it.
- **The confirmers.** Three `confirm_pass` targets; `promote_proposals` never
  promotes on a LOW page. **Every binding pass must write `value_boxes`** or
  the reviewer sees a RESOLVED value with no crop (s14, twice).
- **The DRB3/4/5 row prints gene names**; grammar v2 waits on HA-011.
- **Accuracy (KI-012), 1,342 labels, five rounds (s25). LEAD WITH RECALL.**
  HLA **691 correct, 2 wrong, 130 missed, 19 partial**; ROLE 94/1, ABO 48/0,
  RH 47/0. HLA **68,916** value cells, DRB3/4/5 **37,661**; review queue
  **34,278**. Loss by checkpoint: DRB3/4/5 header 41 + grammar 22, cell
  rectangle 35, locus label 22, gate-1 18, recognition 13, orientation **0**.
- **THE RESIDUAL IS BINDING, NOT READING** (s25). Of 151 remaining labelled
  failures, **113 have the digits readable in a store we hold**, 7 have nothing.
  W4, W7, W2(b) assumed a reading problem, were measured and declined
  (`IMPLEMENTATION_PLAN_2026-09-07.md`).
- **A gate should test its hazard, not a proxy** (s25): G2b replaces
  DRB1-RESOLVED where DRB1 is unresolved; gate-2 re-promotion tests the CELL's
  token, not its page's. Both measured, both shipped.
- **Levelling is measured, not assumed** (`checkpoint_guards.py`): a levelled
  page's residual is re-measured from the rotated image. **1,513 of 1,591 come
  back under 0.5 deg; 78 do not**; 4,920 pages carry 0.5-1.5 deg, never levelled.
- **~3,900 cells from twelve sources are UNMEASURED** (s22, s25): upright 801,
  column-bound 699, token-anchored-drbx 621, family-tie 550, below-rule 364,
  family-loo 258, family-prefix 204, column-named 108, anchor-row 80,
  `token_anchored_drbx_unresolved` 116, `second_allele_reread` 4, gate-2
  re-promotions. Each is withdrawable. **Round five measures them.**
- **Every decision pass is dry-run by default, tagged in `source`, and undoes
  itself in one statement** (`--undo`). A pass that fills what another withdrew
  is a silent reversal: `caption_pass` did it to 6 sheet rows and now honours a
  `sheet-review/v1` row (s23).
- **THE REVIEWER'S NOTES ARE THE BEST DIAGNOSTIC** — `notes`, via
  `label_score.py` (s9).
- **`A*24,02` is two alleles (HA-015, D9):** a COMMA between two numbers splits;
  a period, semicolon or slash still needs the second star (a period is what a
  colon becomes under damage). +1,144 cells through `prefix_bind`.
- **A pack rebuild pins labelled documents (`--keep-labelled`)**;
  `--disagreements-only EXPORT…` packs only the disputed documents, pre-filled.
- **The chat is a source of record** (`caption_pass.py`, s13/s16/s23): a request
  word vetoes a group only from inside the SAME CLAUSE (D1-b). **A locus can
  come from the allele's printed prefix** (s12) — three gated, withdrawable
  routes, named in `AGENTS.md` (HA-017, D12-a).
- **A stratum reporting zero looks like a signal that does not occur** (3x); a
  gate naming a COUNT uses `MIN_DRAW`, not a weight share (s21). **Review a
  write-rule adversarially BEFORE believing its yield** (s14/16/20, s25): all
  four s20 builds were rejected; D11's re-review found two defects.
- **The gate installs what the code imports** (HA-021, D13-a): `EXTRAS = (hist,
  hla, image, ocr)`. `python` on PATH is NOT the interpreter — use `.venv`.
- **Two form facts:** DPA1/DPB1 printed but never filled (HA-009); the
  letterhead disclaims its blood-group field (KI-014).

## Decided (operator delegated)
HA-003 · HA-005 · HA-006 · HA-009 · HA-015 · HA-017 · HA-021, and the
2026-09-07 set D1-b, D2-a, D3-a, D4-b, D5-a, D6-a, D7-a, D8-a, D9, D12-a,
D13-a, D14-a, D15 (`CV_RESEARCH` s23); D10-a (HA-011 (a) codified) and D11
(Bw4/Bw6 extracted, enforced nowhere). **Open: HA-024**, HA-022.

## Human actions open
**HA-008 round five** (600 unseen pages, on 8767). **HA-024**, **HA-022**,
**HA-014**. **HA-007** the blind golden corpus. **HA-011** (b)–(d). Then
**HA-004** (blocks V1-MATCH); its decision packet is the v2 review's §10 (M1–M8).

## Matching (Gold DB built 2026-09-07; evidence review v2 done 2026-09-08)
- **Gold:** 19,200 profiles, 14,864 with HLA (DONOR 8,226 / RECIPIENT 4,612 /
  UNKNOWN 2,026); 9,817 carry A+B+DRB1; ABO on 8,792; **no antibody, PRA or
  crossmatch data**; 97% one-field, so V2 is antigen-level (no eplet/PIRCHE).
- **Evidence v2** (`HLA_MATCHING_EVIDENCE_V2_2026-09-08.md` + methods + appendix;
  100 papers, 1,151 effect sizes, 550/573 quotes machine-verified): **the penalty
  is a STEP, not a line.** A point score is log-linear; the registry lines are
  linear in the HAZARD RATIO with intercept >1 (1.04 deceased, **1.47
  living-unrelated** = our population). 2nd mismatch costs ~0.3 of the 1st (DR
  median 0.29, 8 series). Antigen 0-vs-nonzero separates (p=0.0003), non-zero
  groups do not (p=0.48). DR **gates** class I (Doxiadis n=39,205). Proposal:
  first/second charges DR 6/2, DQ 4/1, B 2/1, A 1/0, C 1/0, others x0.5 when DR
  mismatched. **Not adopted** — HA-004, M1-M8. v1 superseded: its linear weights
  and its "43% of DQ pairs" figure were both wrong.

## Completed foundation
P0 harness, P1 autonomy, P2 test depth (12-step gate). Derived stores and
`data/gold/` gitignored; threshold measurements in `config/`.

## Next actions
1. **Human:** round five; HA-024 and HA-022. Score with `label_score.py`, the
   page-field scorer, and `checkpoint_attribution.py`.
2. **Pass order after any refresh:** `decode_pass`, three `confirm_pass`
   targets, `promote_proposals`, `drbx_ink_pass`, `cell_ink_pass`,
   `drbx_reread`, `reread_refused`, `page_ocr_bind`, `rerecognise_pass`,
   `prefix_bind`, `caption_pass`, then `gate1_repromote`, `ink_drain`,
   `sheet_abo_review`. Rebuild the pack with `--keep-labelled`.
3. **Agent:** the plan's remaining live items only — W3(b) (`exceeds
   max_values`, surgery on `anchors.resolve_in_row`, needs adversarial review)
   and W6's Bw branch in `worktree-wf_e621faf4-df7-1`, which **must not merge**:
   a high defect (`bw_backfill --undo` stops matching once another pass
   re-stamps `created_utc`) and a medium one (a tailed token records its epitope
   through a refused box). Then D2-a export.
4. **Matching, after HA-004 answers M1–M8:** policy V2 doc + versioned JSON from
   the evidence review, then the MATCH-001 core test-first.

## Last verified baseline
`verify_repo.py` PASS — see the latest commit; this records a past result.
