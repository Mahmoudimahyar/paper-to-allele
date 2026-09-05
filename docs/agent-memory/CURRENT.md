# Current project state

**Updated:** 2026-09-05 (third session of the day)
**Canonical phase:** MVP-HIST
**Active task:** OCR-GEOM-001 (`docs/exec-plans/active/OCR-GEOM-001-geometry-and-drbx-row.md`), M4b/M4c done from the reviewer's second export; MEDIA-001/DEDUPE-001 stay READY

## Goal now
Validate what is extracted, and fix what the labels show. 187 of the pack's
1,650 cells are labelled (HA-008). This session traced every non-correct cell
of the second export to a root cause and fixed each where the corpus bore it
out (ADR 0009 §7): the DQB1 label read `DOBI`, over-full cells on the family
rule, empty cells on the default rule, the grouped header's B-slot misreads,
the S-for-5 repair certifying absence, and the decode's proposals never
becoming facts. The review page now shows the messages posted with each image.

## Locked facts
- **The archive is present**, local-only and gitignored, at
  `data/raw/ChatExport_2026-08-31`: 23,566 unique images, 90% above 900 px.
- **The source layer is parsed (HIST-001, HIST-002).** 180,441 messages and
  3,456 service events — the 183,897 the archive characterization counted —
  with **zero unparsed fragments**, into `source.sqlite`. Re-import is a no-op.
  167,012 bundles, 17,357 reply links, 6,593 adjacency suggestions for a human.
- **Documents are linked to the messages that posted them:** 23,565 of 23,566,
  on 110,050 rows — a mean of 4.7 postings each, the signal ENTITY-001 needs.
  18,799 have caption text in their bundle; the review pack shows it.
- **Extraction (ADR 0008, 0009 §7):** `facts.sqlite` refreshed in place on
  2026-09-05 (`refresh_facts.py`, twice; snapshots beside it): HLA and
  DRB3/4/5 cells **RESOLVED 82,480 → 89,737** (760 promoted proposals, 3,338
  absences certified by paper); 15,614 cells changed or new on the first
  refresh, 998 on the second; among cells resolved both times 890 second alleles gained, 17
  dropped, **0 swapped**. `refresh_facts.py` now prints the per-locus
  comparison itself and names a stop signal.
  Gains: DQB1 +2,411 (the `DOBI` label), A +526, B +407, C +205, DRB1 +557,
  DRB5 +372. Losses by design: DRB4 −955, DRB3 −235 (KI-026, the repaired
  slot). The refresh comparison against the snapshot is part of the procedure
  — it caught a prefix bug that had made the letterhead's `LAB` an HLA-B
  anchor on 9,817 documents before it shipped. The adversarial review (133
  agents, 24 findings, all fixed) then withdrew 154 of the band's cells and 7
  the DRB3/4/5 header owns.
- **Page geometry (`rulings/v3+lsd+sweep`):** the sweep corroborates within 2°,
  the agreement check calibrated on photographs (3°/0.7). Corpus: 6,511 ROTATE
  / 14,139 STRAIGHT / 2,916 UNCERTAIN; 1,591 pages levelled (from 1.5°,
  KI-024). A tilt estimate from the stored boxes is biased (KI-025).
- **Recognizers, against the reviewer's labels** (67 value cells,
  `ENGINE_BENCH_2026-09-05.md`): **PP-OCRv6-medium 65 exact (97%)**, the
  pipeline as it ships 57, PP-OCRv5-server 55, Qwen3-VL-4B 52 at 475 ms/crop,
  the shipped confirmer 50, Tesseract 32, our own recognizer 14. v6's two
  misses are the cells the detector gave one box; no pair ever agreed on a
  wrong value. v6 now reads every resolved cell (96.9% confirmed against v5's
  90.0%, 0.4% silent against 2.6%) and licenses the promotion gate: **961
  promoted** (was 760), 57 withdrawn because v6 contradicts what v5 licensed.
- **The decode and the confirmers.** `confirm_pass.py` gained two targets:
  `--target proposals` judges a reader against the decode's proposal, and
  `promote_proposals.py` promotes the CONFIRMED ones — never on a LOW page,
  re-judged with admissibility, and withdrawn when a reader at least as good
  as the licensing one disagrees (`ENGINE_RANK`). `--target drbx` reads every
  PRESENT gene box: of 1,912 repaired `DRBS` tokens PP-OCRv5 confirms 1,152,
  contradicts 20 (demoted) and renders the same `S` on 740. The upright-crop
  decode ablation on the levelled pages was a wash; crops stay axis-aligned.
- **The DRB3/4/5 row prints gene names** (22,017 vs 75 bare numbers); one
  question per row on the page; grammar v2 waits on HA-011.
- **The printed table is read as a grid (`ocr/lattice.py`).** The stored
  rulings place a label the recognizer could not read (the form's template says
  where; **+2,272 cells**, 0 values swapped) and the second DRB3/4/5 slot. Ink
  measured in that slot certifies ABSENT when it is paper (`drbx_ink_pass.py`:
  **4,540 genes**; 287 rows refused for resting on the S-for-5 repair).
  `cell_ink_pass.py` measures the ~24,000 empty labelled cells and **writes no
  fact** — 14.7k read as paper, but `NOT_TESTED` is HA-009's per-laboratory
  verdict, so HA-012 asks the human. On the labels the ink measure has never
  called a cell paper where a value was read.
- **Role resolves on 7,521 documents** (55% of those typed on 3+ loci), 2,495
  by a caption corroborating a weak printed field (`documents/role.py`).
- **Accuracy is still unvalidated (KI-012); this is the binding constraint.**
  The 187-cell export scored 78 correct / 74 correct abstentions / 29 missed /
  4 contradicted / 2 partial at the start of this session and **87 / 71 / 23
  / 4 / 2** at its end; the four contradictions are one SPLIT-flagged B cell
  and three DRB3/4/5 rows labelled NOT_PRINTED (the page's pre-set) where
  header v2 finds gene names PP-OCRv5 confirms. The blind golden corpus waits
  on a person.
- **Two form facts constrain the product:** DPA1/DPB1 printed, never filled
  (HA-009); the letterhead disclaims its own blood-group field (KI-014).
- **The zero-fact documents are mostly not reports (KI-018):** ~170 of 4,944
  recoverable. Raw inputs are immutable; geometry determines locus, not text.

## Decided (operator delegated)
HA-003 resolution bands (MID provisional) · HA-005 names as a salted hash ·
HA-006 IMGT 3.62 · HA-009 untested-locus policy (`HUMAN_ACTIONS.md`, Closed).

## Human actions open
**HA-008 label the review pack** — 187/1,650 done; the page shows the messages
now (Ctrl+F5); the labels can next settle the repaired DRB3/4/5 slots and the
promoted cells. **HA-007 the blind golden corpus.** **HA-011** codify the
DRB3/4/5 grammar in the spec. Then HA-004 (immunologist; blocks V1-MATCH),
HA-001, HA-002, HA-010 (cloud keys, optional).

## Completed foundation
- P0 harness repair, P1 autonomy, P2 test depth (12-step gate, invariant
  traceability, coverage ratchet 65% / medical modules 100%, PII scanner,
  bandit + gitleaks + osv-scanner, mutmut).
- Derived local stores, all gitignored: `ocr_pass`, `facts`, `source`,
  `geometry` (sqlite), `data/review/hla_pack/`, `data/review/queue.json`.
- Committed measurements the thresholds rest on: `config/hla_first_fields.json`,
  `locus_testing_rates.json`, `locus_genotype_frequencies.json`.

## Next actions
1. **Human: keep labelling (HA-008)**; score each export with
   `scripts/pack_score.py`. The DRB3/4/5 rows marked "repaired" and the cells
   marked "promoted" are the two rules the labels can now confirm or refute.
2. Agent: M6 after HA-011; KI-023's OpenCV override on a machine that can run
   the gate twice; KI-027 (a grid from merged, gap-bridged rulings — 5,581
   empty cells have no ruled row today). Build the NEXT pack (strata `tilted`,
   `promoted`, `ink_certified`) only when the reviewer has finished this one.
   After any refresh: decode, the three confirm targets,
   `promote_proposals.py`, `drbx_ink_pass.py`, `cell_ink_pass.py`.
3. Agent, needs no human: MEDIA-001, DEDUPE-001, then ENTITY-001. Human:
   HA-004 before any matching beyond the ABO gate.

## Last verified baseline
`python scripts/verify_repo.py` → see the handoff of 2026-09-05 (third session).
Re-run it yourself; this file records a past result, not the current environment.
