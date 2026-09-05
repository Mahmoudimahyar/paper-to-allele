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
  `data/raw/ChatExport_2026-08-31`: 23,566 unique original images, 90% above
  900 px (KI-009 corrected the earlier "median 520 px").
- **The source layer is parsed (HIST-001, HIST-002).** 180,441 messages and
  3,456 service events — exactly the 183,897 the archive characterization
  counted — with **zero unparsed fragments**, into `data/derived/source.sqlite`.
  Re-import is a no-op. 167,012 bundles, 17,357 reply links, 6,593 adjacency
  suggestions for a human. A joined message carries no sender and inherits one;
  measured, inherited senders equal the joined count exactly.
- **Documents are linked to the messages that posted them.** 23,565 of 23,566,
  on 110,050 message rows: the same image posted a mean of 4.7 times, which is
  the reposting signal ENTITY-001 needs. 18,799 documents have caption text
  somewhere in their bundle; the review pack now shows it.
- **Extraction (ADR 0008, 0009 §7):** `facts.sqlite` refreshed in place on
  2026-09-05 (`refresh_facts.py`, twice; snapshots beside it): HLA and
  DRB3/4/5 cells **RESOLVED 82,480 → 86,399** (760 of them promoted
  proposals); 15,614 cells changed or new on the first refresh, 998 on the
  second; among cells resolved both times 890 second alleles gained, 17
  dropped, **0 swapped**. `refresh_facts.py` now prints the per-locus
  comparison itself and names a stop signal.
  Gains: DQB1 +2,411 (the `DOBI` label), A +526, B +407, C +205, DRB1 +557,
  DRB5 +372. Losses by design: DRB4 −955, DRB3 −235 (KI-026, the repaired
  slot). The refresh comparison against the snapshot is part of the procedure
  — it caught a prefix bug that had made the letterhead's `LAB` an HLA-B
  anchor on 9,817 documents before it shipped. The adversarial review (133
  agents, 24 findings, all fixed) then withdrew 154 of the band's cells and 7
  the DRB3/4/5 header owns.
- **Page geometry (`rulings/v3+lsd+sweep`):** the sweep corroborates within 2°
  and the agreement check is calibrated on photographs (3°/0.7). Corpus: 6,511
  ROTATE (27.6%) / 14,139 STRAIGHT / 2,916 UNCERTAIN; 1,591 pages levelled at
  extraction (from 1.5°, KI-024). A tilt estimate from the stored boxes is
  biased 1.44° and was rejected (KI-025).
- **The decode and the confirmers:** the changed cells re-decoded (7,041:
  4,716 UNANIMOUS / 990 PROPOSAL / 612 SPLIT / 585 DIGITS_LOST / 138
  ILLEGIBLE) and re-confirmed by PP-OCRv5 (`--target resolved`). Two new
  targets: `--target proposals` judges PP-OCRv5 against the decode's proposal
  (2,008 judged: 763 CONFIRMED / 882 CONTRADICTED / 363 no opinion — the 44%
  is what promoting on the decode alone would have done) and
  `promote_proposals.py` promotes the CONFIRMED ones, never on a LOW page,
  re-judged with admissibility: **760 promoted** (DRB1 373, DQB1 211, B 106,
  A 36, DQA1 26, C 8), each marked `source=decode+ppocrv5`. `--target drbx`
  reads every PRESENT gene box: of 1,912 repaired `DRBS` tokens PP-OCRv5
  confirms 1,152, contradicts 20 (demoted to review) and renders the same
  `S` on 740. Tesseract has not yet read the changed cells.
- **The DRB3/4/5 row prints gene names**: 22,017 gene tokens vs 75 bare numbers
  corpus-wide. The review page asks one question per row; grammar v2 waits on
  HA-011. Header v2 gains 605 documents.
- **Role resolves on 7,521 documents** (55% of those typed on 3+ loci), 2,495
  of them because a caption corroborated a weak printed field. The Persian
  role words and the anchored ABO cell are what the reviewer asked for; both
  were already the design (`documents/role.py`, `documents/abo.py`).
- **Accuracy is still unvalidated (KI-012); this is the binding constraint.**
  The 187-cell export scored 78 correct / 74 correct abstentions / 29 missed /
  4 contradicted / 2 partial at the start of this session and **83 / 71 / 27
  / 4 / 2** at its end; the four contradictions are one SPLIT-flagged B cell
  and three DRB3/4/5 rows labelled NOT_PRINTED (the page's pre-set) where
  header v2 finds gene names PP-OCRv5 confirms. The blind golden corpus waits
  on a person.
- **Two form facts that constrain the product.** DPA1/DPB1 are printed and
  never filled — `NOT_TESTED` (HA-009, KI-013). The dominant letterhead
  disclaims its own blood-group field (KI-014).
- **The zero-fact documents are mostly not reports (KI-018):** ~170 of 4,944
  recoverable. Raw inputs are immutable and never committed; HLA geometry
  determines locus, never token text alone.

## Decided this session (operator delegated)
HA-003 resolution bands (MID provisional) · HA-005 names as a salted hash ·
HA-006 IMGT pinned to 3.62, the release py-ard 1.5.5 loads · HA-009 the
untested-locus policy. Details in `HUMAN_ACTIONS.md` under Closed.

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
- Derived local stores, all gitignored: `ocr_pass.sqlite`, `facts.sqlite`,
  `source.sqlite`, `geometry.sqlite`, `data/review/hla_pack/`,
  `data/review/queue.json`.
- Committed measurements the thresholds rest on: `config/hla_first_fields.json`,
  `locus_testing_rates.json`, `locus_genotype_frequencies.json`.

## Next actions
1. **Human: keep labelling (HA-008)**; score each export with
   `scripts/pack_score.py`. The DRB3/4/5 rows marked "repaired" and the cells
   marked "promoted" are the two rules the labels can now confirm or refute.
2. Agent: `confirm_pass.py --engine tesseract5` over the changed cells; the
   `--frame` decode ablation on levelled pages (M4); M5 lattice (ink-certified
   empty second column for the 6,100 one-token DRB3/4/5 rows); the
   reinstate-on-confirmer rule for KI-026; M6 after HA-011; KI-023's single
   OpenCV wheel. Build the NEXT pack (with the `tilted` stratum) only when the
   reviewer has finished this one.
3. Agent, needs no human: MEDIA-001 and DEDUPE-001 remain the last MVP-HIST
   tasks; then ENTITY-001. Human: HA-004 before any matching beyond the ABO gate.

## Last verified baseline
`python scripts/verify_repo.py` → see the handoff of 2026-09-05 (third session).
Re-run it yourself; this file records a past result, not the current environment.
