# Current project state

**Updated:** 2026-09-07 (sixth session)
**Canonical phase:** MVP-HIST
**Active task:** OCR-GEOM-001 (`docs/exec-plans/active/OCR-GEOM-001-geometry-and-drbx-row.md`); MEDIA-001/DEDUPE-001 stay READY

## Goal now
Finalize the database. **1,342 cells labelled over five rounds** (HA-008); the
operator answered every decision on 2026-09-07 and re-checked the disputed
pack (s23, s24). The loss is now charged to checkpoints and the work is ordered
by it (`IMPLEMENTATION_PLAN_2026-09-07.md`): the DRB3/4/5 row first. Round five
(`--n 600`, on 8767) measures the 3,685 cells from nine sources no person has
checked; then D2-a exports tiers A/B/C, review and unknown separately. Check
the instrument before the pipeline.

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
- **Accuracy (KI-012), 1,342 labels over five rounds, after the checkpoint
  plan (s25). LEAD WITH RECALL.** HLA **691 correct, 2 wrong, 130 missed, 19
  partial**; ROLE 94/1, ABO 48/0, RH 47/0. HLA **68,916** value cells, DRB3/4/5
  **37,661**; review queue **34,278**. Loss by checkpoint
  (`checkpoint_attribution.py`): DRB3/4/5 header 41 + row grammar 22, cell
  rectangle 35, locus label 22, gate-1 withdrawals 18, recognition 13,
  orientation/tilt **0**.
- **THE RESIDUAL IS BINDING, NOT READING** (s25). Of the 151 remaining labelled
  failures, **113 have the value's digits readable in a store we already hold**
  and only 7 have nothing readable. Rules that assumed a reading problem (W4,
  W7, W2(b)) were measured and declined; see
  `IMPLEMENTATION_PLAN_2026-09-07.md` for each item's evidence.
- **A gate should test its hazard, not a proxy for it** (s25): G2b replaces
  DRB1-RESOLVED where DRB1 is unresolved; the gate-2 re-promotion tests the
  CELL's token, not its page's. Both measured, both shipped.
- **Levelling is measured, not assumed** (`checkpoint_guards.py`): the residual
  of a levelled page is re-measured from the rotated image. **1,513 of 1,591
  come back under 0.5 deg; 78 do not**, and 4,920 pages carry 0.5-1.5 deg that
  is never levelled.
- **~3,900 cells from twelve sources are UNMEASURED** (s22, s25): the nine of
  s22 (upright 801, column-bound 699, token-anchored-drbx 621, family-tie 550,
  below-rule 364, family-loo 258, family-prefix 204, column-named 108,
  anchor-row 80) plus `token_anchored_drbx_unresolved` 116,
  `second_allele_reread` 4 and the gate-2 re-promotions. Each has a source, a
  stratum and a withdrawal handle. **Round five measures them.**
- **Every decision pass is dry-run by default, tagged in `source`, and undoes
  itself in one statement** (`gate1_repromote`, `ink_drain`,
  `sheet_abo_review`, all `--undo`). A pass that fills what another pass
  withdrew is a silent reversal: `caption_pass` did it to 6 sheet rows within
  the hour, and now honours a `sheet-review/v1` row (s23).
- **THE REVIEWER'S NOTES ARE THE BEST DIAGNOSTIC WE HAVE** — under `notes`,
  printed by `label_score.py` (s9).
- **`A*24,02` is two alleles (HA-015, D9):** a COMMA between two numbers splits;
  a period, semicolon or slash still needs the second star, because a period is
  what a colon becomes under damage. +1,144 cells through `prefix_bind`.
- **A pack rebuild pins labelled documents (`--keep-labelled`)**;
  `--disagreements-only EXPORT…` packs only the disputed documents, pre-filled.
- **The chat is a source of record** (`caption_pass.py`, s13/s16/s23): a request
  word vetoes a group only from inside the SAME CLAUSE (D1-b).
- **A locus can come from the allele's printed prefix** (s12) — three gated,
  withdrawable routes, now named in `AGENTS.md` (HA-017, D12-a).
- **A stratum reporting zero looks like a signal that does not occur** (3x).
  A gate naming a COUNT uses `MIN_DRAW`, not a weight share (s21).
- **Review a write-rule adversarially BEFORE believing its yield** (s14/16/20,
  s25): all four s20 builds were rejected; D11's own re-review found two
  defects; and a test caught D9's `_PAIR` letting a `Bw4` tail pose as an allele.
- **The gate installs what the code imports** (HA-021, D13-a): `EXTRAS =
  (hist, hla, image, ocr)` in `verify_repo`, CI and bootstrap; the contract
  pins all four. `python` on PATH is NOT the project interpreter — use `.venv`.
- **Two form facts:** DPA1/DPB1 printed but never filled (HA-009); the
  letterhead disclaims its blood-group field (KI-014).

## Decided (operator delegated)
HA-003 · HA-005 · HA-006 · HA-009 · HA-015 · HA-017 · HA-021, and the
2026-09-07 set D1-b, D2-a, D3-a, D4-b, D5-a, D6-a, D7-a, D8-a, D9, D12-a,
D13-a, D14-a, D15 (`CV_RESEARCH` s23); D10-a (HA-011 (a) codified in the
specs) and D11 (Bw4/Bw6 extracted, enforced nowhere — landing from its
workflow). **Open: HA-024** (caption groups on two-person pages), HA-022.

## Human actions open
**HA-008 round five** (600 unseen pages, on 8767). **HA-024**, **HA-022**,
**HA-014**. **HA-007** the blind golden corpus. **HA-011** (b)–(d). Then
HA-004 (blocks V1-MATCH).

## Completed foundation
P0 harness, P1 autonomy, P2 test depth (12-step gate, coverage 65% / medical
100%, PII scanner, bandit, gitleaks, osv-scanner, mutmut). Derived stores are
gitignored (`ocr_pass`, `facts`, `source`, `geometry`, `data/review/`); the
measurements the thresholds rest on are committed in `config/`.

## Next actions
1. **Human:** round five; HA-024 and HA-022. Score with `label_score.py`, the
   page-field scorer, and `checkpoint_attribution.py`.
2. **Pass order after any refresh:** `decode_pass`, the three `confirm_pass`
   targets, `promote_proposals`, `drbx_ink_pass`, `cell_ink_pass`,
   `drbx_reread`, `reread_refused`, `page_ocr_bind`, `rerecognise_pass`,
   `prefix_bind`, `caption_pass`, then the decision passes `gate1_repromote`,
   `ink_drain`, `sheet_abo_review`. Rebuild the pack with `--keep-labelled`.
3. **Agent:** the plan's remaining live items only — W3(b) (the
   `exceeds max_values` choice, surgery on `anchors.resolve_in_row`, needs an
   adversarial review) and W6's Bw branch, which is built in
   `worktree-wf_e621faf4-df7-1` but **must not merge**: its re-review found a
   high defect (`bw_backfill --undo` stops matching once another pass re-stamps
   `created_utc`) and a medium one (a tailed token records its epitope through
   a refused box). Then D2-a export.

## Last verified baseline
`python scripts/verify_repo.py` — see the sixth-session commit message for the
result; this file records a past result, not the current environment.
