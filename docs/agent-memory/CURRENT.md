# Current project state

**Updated:** 2026-09-07 (sixth session)
**Canonical phase:** MVP-HIST
**Active task:** OCR-GEOM-001 (`docs/exec-plans/active/OCR-GEOM-001-geometry-and-drbx-row.md`); MEDIA-001/DEDUPE-001 stay READY

## Goal now
Finalize the database. **1,342 cells labelled over four rounds** (HA-008); the
operator answered fifteen decisions on 2026-09-07 and every one is applied
(`CV_RESEARCH` s23). Two things stand between here and a tiered export: the
**disagreement pack** (56 documents where a person and the pipeline differ,
served on 8766, D15) and **round five** (`--n 600`, D8) which measures the
3,685 cells from nine sources no person has checked. Then D2-a: export tiers
A/B/C, review and unknown separately. Check the instrument before the pipeline.

## Locked facts
- **The archive** (local-only, gitignored, `data/raw/ChatExport_2026-08-31`):
  23,566 images, 90% >900 px; 180,441 messages parsed, ZERO unparsed.
- **Extraction (ADR 0008, 0009 §7):** `refresh_facts.py` prints the per-locus
  comparison against its snapshot — that caught the `LAB`-as-HLA-B bug on 9,817
  documents. ALWAYS compare, and bracket every pass with a status snapshot.
- **Page geometry (`rulings/v3+lsd+sweep`):** 6,511 ROTATE / 14,139 STRAIGHT /
  2,916 UNCERTAIN; 1,591 levelled (KI-024). A tilt from stored boxes is biased.
- **Recognizers** (`ENGINE_BENCH_2026-09-05.md`): PP-OCRv6 65 of 67 exact,
  shipped 57, ours 14. No pair agreed on a WRONG value: the two-engine gates
  rest on that, and D6-a re-promoted 123 gate-1 withdrawals on exactly it.
- **The confirmers.** Three `confirm_pass` targets; `promote_proposals` never
  promotes on a LOW page. **Every binding pass must write `value_boxes`** or
  the reviewer sees a RESOLVED value with no crop (s14, twice).
- **The DRB3/4/5 row prints gene names**; grammar v2 waits on HA-011.
- **The printed table is read as a grid (`ocr/lattice.py`):** rulings place an
  unreadable label (**+2,272**) and the second DRB3/4/5 slot.
- **Accuracy (KI-012), 1,342 labels, after s23. LEAD WITH RECALL, NOT
  PRECISION.** HLA **670 correct, 5 wrong, 114 missed, 19 partial**; ROLE 93/2,
  ABO 48/0, RH 47/0. Coverage ROLE **79.9%**, ABO **47.1%**, RH **42.2%**, HLA
  **68,916** value cells. Review queue **35,391 cells / 14,631 documents** (was
  45,846 / 18,132): D3-a drained 14,060 blank printed cells to NOT_TESTED.
- **3,685 cells from nine NEW sources are UNMEASURED** (s22): upright+rotated
  801, column-bound 699, token-anchored-drbx 621, family-tie 550, below-rule
  364, family-loo 258, family-prefix 204, column-named 108, anchor-row 80. Each
  has a source, a stratum and a withdrawal handle. **Round five measures them.**
- **Every decision pass is dry-run by default, tagged in `source`, and undoes
  itself in one statement** (`gate1_repromote`, `ink_drain`,
  `sheet_abo_review`, all `--undo`). A pass that fills what another pass
  withdrew is a silent reversal: `caption_pass` did it to 6 sheet rows within
  the hour, and now honours a `sheet-review/v1` row (s23).
- **THE REVIEWER'S NOTES ARE THE BEST DIAGNOSTIC WE HAVE** — under `notes`,
  printed by `label_score.py` (s9).
- **Rows are read along the page's own slope** (`ocr/rows.py`): the dominant
  ruling cluster, floored at 0.008. **+209 second alleles**.
- **REFUSALS AND MISSES ARE DIFFERENT POPULATIONS** (s11, s17): refused cells
  are blank paper; MISSED cells have their digits in the stored OCR 88% of the
  time — read but unbound. Opposite fix.
- **611 pages were photographed SIDEWAYS** (s17, `upright_pass.py`): turned,
  425 anchor and **801 cells resolve**. Box height>width IN PIXELS, never in
  normalised coordinates.
- **`A*24,02` is two alleles (HA-015, D9):** a COMMA between two numbers splits;
  a period, semicolon or slash still needs the second star, because a period is
  what a colon becomes under damage. +1,144 cells through `prefix_bind`.
- **A pack rebuild pins labelled documents (`--keep-labelled`)** or the sample
  reshuffles; `--disagreements-only EXPORT…` builds a pack of ONLY the
  documents where the pipeline now disputes an earlier answer, pre-filled.
- **The chat is a source of record** (`caption_pass.py`, s13/s16/s23): a request
  word vetoes a group only from inside the SAME CLAUSE (D1-b).
- **A locus can come from the allele's printed prefix** (s12) — three gated,
  withdrawable routes, now named in `AGENTS.md` (HA-017, D12-a).
- **A stratum reporting zero looks like a signal that does not occur** (3x).
  A gate naming a COUNT uses `MIN_DRAW`, not a weight share (s21).
- **Review a write-rule adversarially BEFORE believing its yield** (s14/16/20):
  all four s20 builds were rejected; D9's first `_PAIR` let a `Bw4` tail pose
  as a second allele and an existing test caught it.
- **The gate installs what the code imports** (HA-021, D13-a): `EXTRAS =
  (hist, hla, image, ocr)` in `verify_repo`, CI and bootstrap; the contract
  pins all four. `python` on PATH is NOT the project interpreter — use `.venv`.
- **Two form facts:** DPA1/DPB1 printed but never filled (HA-009); the
  letterhead disclaims its blood-group field (KI-014).

## Decided (operator delegated)
HA-003 · HA-005 · HA-006 · HA-009 · HA-015 · HA-017 · HA-021, and the
2026-09-07 set D1-b, D2-a, D3-a, D4-b, D5-a, D6-a, D7-a, D8-a, D9, D12-a,
D13-a, D14-a, D15 (`CV_RESEARCH` s23). **Open: D10, D11** (explained, awaiting
an answer) and **HA-024** (caption groups on two-person pages).

## Human actions open
**D15 the disagreement pack** on 8766: 138 disputed cells and 2 ROLE fields,
everything else pre-filled — change an answer only if the crop says so.
**HA-024**, **HA-014**, **HA-008** round five (600). **HA-007** the blind golden
corpus. **HA-011** the DRB3/4/5 grammar. Then HA-004 (blocks V1-MATCH).

## Completed foundation
P0 harness, P1 autonomy, P2 test depth (12-step gate, coverage 65% / medical
100%, PII scanner, bandit, gitleaks, osv-scanner, mutmut). Derived stores are
gitignored (`ocr_pass`, `facts`, `source`, `geometry`, `data/review/`); the
measurements the thresholds rest on are committed in `config/`.

## Next actions
1. **Human:** re-check the disagreement pack (D15); answer D10/D11 and HA-024;
   then round five. Score with `label_score.py` and the page-field scorer.
2. **Pass order after any refresh:** `decode_pass`, the three `confirm_pass`
   targets, `promote_proposals`, `drbx_ink_pass`, `cell_ink_pass`,
   `drbx_reread`, `reread_refused`, `page_ocr_bind`, `rerecognise_pass`,
   `prefix_bind`, `caption_pass`, then the decision passes `gate1_repromote`,
   `ink_drain`, `sheet_abo_review`. Rebuild the pack with `--keep-labelled`.
3. **Agent:** D2-a tiered export; D8-a round-five pack at `--n 600`; the CV
   plan (`CV_PLAN_2026-09-07.md`) against recall, the unmeasured mass and the
   review queue. Then M6 after HA-011, KI-023, KI-027, MEDIA-001, DEDUPE-001.

## Last verified baseline
`python scripts/verify_repo.py` — see the sixth-session commit message for the
result; this file records a past result, not the current environment.
