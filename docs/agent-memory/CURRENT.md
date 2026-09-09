# Current project state

**Updated:** 2026-09-08 (seventh session)
**Canonical phase:** MVP-HIST
**Active task:** MATCH-001 (built, ACTIVE not COMPLETE, waits on HA-004);
OCR-GEOM-001, MEDIA-001, DEDUPE-001 stay READY

## Goal now
Matching is built and tested; adoption waits on HA-004. Round five (`--n 600`,
on 8767) still measures the ~3,900 unlabelled-source cells; then D2-a exports
tiers A/B/C, review and unknown separately. Check the instrument first.

## Locked facts
- **The archive** (local-only, gitignored, `data/raw/ChatExport_2026-08-31`):
  23,566 images, 90% >900 px; 180,441 messages parsed, ZERO unparsed.
- **Extraction (ADR 0008, 0009 §7):** `refresh_facts.py` prints the per-locus
  comparison against its snapshot — that caught the `LAB`-as-HLA-B bug on 9,817
  documents. ALWAYS compare, and bracket every pass with a status snapshot.
- **Page geometry (`rulings/v3+lsd+sweep`):** 6,511 ROTATE / 14,139 STRAIGHT /
  2,916 UNCERTAIN. A tilt from stored boxes is biased.
- **Recognizers** (`ENGINE_BENCH_2026-09-05.md`): PP-OCRv6 65 of 67 exact. No
  pair agreed on a WRONG value — the two-engine gates rest on that.
- **The confirmers.** `promote_proposals` never promotes on a LOW page. **Every
  binding pass must write `value_boxes`** or the reviewer sees a RESOLVED value
  with no crop (s14, twice).
- **The DRB3/4/5 row prints gene names**; grammar v2 waits on HA-011.
- **LEAD WITH RECALL** (KI-012). Loss by checkpoint: DRB3/4/5 header 41 +
  grammar 22, cell rectangle 35, locus label 22, gate-1 18, recognition 13,
  orientation **0**.
- **THE RESIDUAL IS BINDING, NOT READING** (s25): of 151 labelled failures,
  **113 have the digits readable in a store we hold**. W4, W7, W2(b) declined.
- **A gate should test its hazard, not a proxy** (s25).
- **Levelling is measured** (`checkpoint_guards.py`): 1,513 of 1,591 re-measure under 0.5 deg, 78 do not.
- **~3,900 cells from twelve sources are UNMEASURED** (listed in
  `IMPLEMENTATION_PLAN_2026-09-07.md`), each withdrawable. Round five measures them.
- **Every decision pass is dry-run by default, tagged in `source`, and undoes
  itself** (`--undo`). A pass that fills what another withdrew is a silent
  reversal.
- **`A*24,02` is two alleles (HA-015):** a COMMA splits; other separators still need the second star.
- **A pack rebuild pins labelled documents (`--keep-labelled`)**; the storage
  key is the PACK ID, so two packs on one port cannot collide.
- **The chat is a source of record** (`caption_pass.py`): a request word vetoes
  a group only from the SAME CLAUSE (D1-b). **A locus can come from the printed
  prefix** — three gated routes, in `AGENTS.md` (HA-017).
- **Review a write-rule adversarially BEFORE believing its yield** (s14/16/20):
  all four s20 builds were rejected; D11's re-review found two defects.
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
**HA-004** (blocks V1-MATCH adoption, not its code). **Its two M-tables
disagree: 13 distinct questions, not 11. Conflict table in the HA-004 entry;
never cite an M-number without naming its document.**

## Matching (built 2026-09-08; NOT adopted)
- **Gold** holds no antibody, PRA or crossmatch data and is 97% one-field, so
  V2 is antigen-level and every pair is ANTIBODY_UNKNOWN.
- **Evidence v2** (`HLA_MATCHING_EVIDENCE_V2_2026-09-08.md` + methods; 99
  papers, 1,134 effect sizes, 549 of 567 quotes machine-verified):
  **the penalty is a STEP, not a line.** A point score is log-linear; the
  registry lines are linear in the HAZARD RATIO, intercept >1 (1.04 deceased,
  **1.47 living-unrelated** = ours). 2nd mismatch ~0.3 of the 1st. Antigen
  0-vs-nonzero separates (p=0.0003), non-zero groups do not (p=0.48). DR
  **gates** class I (n=39,205). v1's linear weights were wrong.
- **Built** (`src/kidneymatch/matching/`, `scripts/rank_matches.py`, 774 tests,
  100% of statements and branches): UK levels re-cut so every DR-matched pair
  outranks every DR-mismatched one; 8-field sort key; BOTH directions, one
  mismatch function, recipient always in the recipient argument. **Not
  symmetric** — MM(D→R) − MM(R→D) = |distinct(D)| − |distinct(R)|.
- **Missing is charged at its WORST case** (not zero): the penalty sits at sort
  position 3 and the unknown count at 5, so nothing later offsets it.
- **LABELS** 1,408 cells / 128 docs in `data/review/labels/`, SHA-256 each.
  They live in the BROWSER until exported (KI-031) — export often.
- **THE EXTRACTOR IS ACCURATE AND INCOMPLETE** (`LABEL_MEASUREMENT_2026-09-09`,
  stratified for failure so NOT a corpus accuracy): HLA 83.3% correct, 3
  contradicted; role 84%; **blood group never wrong, missed HALF the time**.
  8,914 docs say "no blood-group label found" and a person reads one off the
  page anyway — the largest measured lever on the matcher.
- **Blood group binds, not HLA.** 45.8% of profiles carry one; 72.6% of pairs
  are `INSUFFICIENT_ABO` — a fact about EXTRACTION, not about the archive. Gold
  records provenance (5,498 caption, 2,676 lab printed, 618 patient reported)
  and **KI-014 is applied at EXTRACTION**, so `LABORATORY_PRINTED` already means
  a non-disclaiming page. **Never re-apply it downstream**: the runner did,
  hiding every clearable pair (fixed fbfedde). Chat exhausted bar 12 docs. An
  UNREADABLE group is MISSING: it lands in `INSUFFICIENT_ABO`, never a ranked
  bucket.

## Completed foundation
P0 harness, P1 autonomy, P2 test depth (12-step gate). Derived stores and
`data/gold/` gitignored; thresholds in `config/`. Round five is BUILT and
CURRENT (`data/review/hla_pack_r5`, port 8767, pack_id 20260902-600-20260909);
its 2026-09-07 build was stale and is kept as `hla_pack_r5_stale_20260907`.

## Next actions
1. **Human:** keep labelling round five, exporting often; then HA-024, HA-022
   and the HA-004 numbering. Score with `label_score.py`.
2. **Pass order after any refresh:** `decode_pass`, three `confirm_pass`
   targets, `promote_proposals`, `drbx_ink_pass`, `cell_ink_pass`,
   `drbx_reread`, `reread_refused`, `page_ocr_bind`, `rerecognise_pass`,
   `prefix_bind`, `caption_pass`, then `gate1_repromote`, `ink_drain`,
   `sheet_abo_review`. Rebuild the pack with `--keep-labelled`.
3. **Agent:** the blood-group LABEL DETECTOR — 8,914 documents, measured, the
   biggest lever. W3(b): CURRENT and the plan disagree, ask first. W6's Bw
   branch in `worktree-wf_e621faf4-df7-1` **must not merge** (a high defect and
   a medium one). Then D2-a export.
4. **Matching:** adoption changes only `status` in the policy config, after the
   HA-004 numbering conflict and its decisions are settled.

## Last verified baseline
`verify_repo.py` PASS — see the latest commit; this records a past result.
