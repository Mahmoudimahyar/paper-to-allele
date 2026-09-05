# Current project state

**Updated:** 2026-09-05
**Canonical phase:** MVP-HIST
**Active task:** OCR-GEOM-001 (`docs/exec-plans/active/OCR-GEOM-001-geometry-and-drbx-row.md`), from the reviewer's first 165 labels; MEDIA-001/DEDUPE-001 stay READY

## Goal now
Validate what is extracted, and fix what the first labels showed. 165 of the
pack's 1,650 cells are labelled (HA-008): 17 of 19 "contradictions" were the
page's own DRB3/4/5 question (KI-021, fixed), the misses were mostly a `*`
the recognizer never read (KI-022, fixed: +2,368 cells corpus-wide), and tilt
is real (35% of pack pages) but explained one miss. Research record:
`docs/ingestion/CV_RESEARCH_2026-09-05.md`.

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
  the reposting signal ENTITY-001 needs.
- **Extraction (ADR 0008, 0009):** 93,202 resolved facts with provenance,
  63,233 review items, 24,663 `NOT_TESTED` in `facts.sqlite` (v1). Re-extracted
  into `facts_v2.sqlite` with the star-less parser and the page frame:
  **95,581 resolved / 60,855 review**, 0 changed values, 46 cells moved to
  review by the KI-015 guard. The main database is re-extracted in place once
  the corpus geometry pass finishes; decode/confirm passes then cover the delta.
- **Page geometry (OCR-GEOM-001):** `geometry_pass.py` measures tilt from the
  printed rulings (LSD + projection sweep, never one estimator). Pack: 53
  ROTATE / 71 STRAIGHT / 26 UNCERTAIN at ~60 ms/img. The extraction levels the
  stored boxes from 1.5° of tilt (below that the frame is a wash, KI-024).
- **The DRB3/4/5 row prints gene names**: 22,017 gene tokens vs 75 bare numbers
  corpus-wide. The review page asks one question per row; grammar v2 waits on
  HA-011.
- **Role resolves on 7,521 documents** (55% of those typed on 3+ loci, up from
  40%), 2,495 of them because a caption corroborated a weak printed field. A
  caption that reads as a *request* for a role is refused: «اهدا کننده نیاز
  دارم» is a recipient asking for a donor.
- **Two independent confirmers read every resolved cell.** Tesseract: 22,778
  confirmed / 6,577 contradicted / 17,866 no opinion. PP-OCRv5
  (`--extra confirm`): **43,124 / 3,063 / 1,034**, answering on 17,206 of the
  cells Tesseract could not read. Its crop must be per value box; on a crop
  spanning both alleles it agreed only 49.3% of the time.
- **The constrained decode:** 44,504 UNANIMOUS / 2,255 SPLIT / 459 DIGITS_LOST.
- **Accuracy is still unvalidated (KI-012); this is the binding constraint.**
  Everything above is a yield or an agreement rate. The anchored review pack
  (150 documents, 15 strata, five readings per cell) and the blind golden
  corpus both wait on a person.
- **Two form facts that constrain the product.** DPA1/DPB1 are printed and
  never filled — now `NOT_TESTED`, not review work (HA-009, KI-013). The
  dominant letterhead disclaims its own blood-group field (KI-014), so a
  patient-reported group may exclude a pair and never clear one.
- **The zero-fact documents are mostly not reports (KI-018).** Only ~170 of the
  4,944 are recoverable.
- Raw historical inputs are immutable and never committed. HLA geometry
  determines locus; OCR may not assign a locus from token text alone.

## Decided this session (operator delegated)
HA-003 resolution bands (MID provisional) · HA-005 names as a salted hash ·
HA-006 IMGT pinned to 3.62, the release py-ard 1.5.5 loads · HA-009 the
untested-locus policy. Details in `HUMAN_ACTIONS.md` under Closed.

## Human actions open
**HA-008 label the review pack** — 165/1,650 done; the 15 documents' DRB3/4/5
rows must be re-confirmed under the one-row question (KI-021). **HA-007 the
blind golden corpus.** **HA-011** codify the DRB3/4/5 grammar in the spec
(blocks grammar v2 only). Then HA-004 (immunologist; blocks V1-MATCH), HA-001,
HA-002, HA-010 (cloud keys, optional).

## Completed foundation
- P0 harness repair, P1 autonomy, P2 test depth (12-step gate, invariant
  traceability, coverage ratchet 65% / medical modules 100%, PII scanner,
  bandit + gitleaks + osv-scanner, mutmut).
- Derived local stores, all gitignored: `ocr_pass.sqlite`, `facts.sqlite`,
  `source.sqlite`, `data/review/hla_pack/`, `data/review/queue.json`.
- Committed measurements the thresholds rest on: `config/hla_first_fields.json`,
  `config/locus_testing_rates.json`, `config/locus_genotype_frequencies.json`.

## Next actions
1. **Human: re-confirm the DRB3/4/5 rows, keep labelling (HA-008).** Score each
   export with `scripts/pack_score.py`; the clean-control rate decides whether
   anything may be published.
2. Agent: when `geometry_pass.py --status` covers the corpus, re-extract
   `facts.sqlite` in place with `--geometry`, then run `decode_pass.py` and
   `confirm_pass.py` for the new cells. Then OCR-GEOM-001 M4 (crop discipline,
   ablated on the labelled cells) and M5 (ruled-cell lattice); M6 after HA-011.
3. Agent, needs no human: MEDIA-001 and DEDUPE-001 remain the last MVP-HIST
   tasks; then ENTITY-001. Human: HA-004 before any matching beyond the ABO gate.

Acceptance state: `python scripts/acceptance.py status`.

## Last verified baseline
`python scripts/verify_repo.py` → **PASS (12 steps, none skipped)**, 2026-09-05.
Re-run it yourself; this file records a past result, not the current environment.
