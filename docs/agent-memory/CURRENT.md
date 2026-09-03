# Current project state

**Updated:** 2026-09-02
**Canonical phase:** MVP-HIST
**Active task:** HIST-001
**Active plan:** `docs/exec-plans/active/MVP-HIST-001-bootstrap-ingestion.md`

## Goal now
Build the local, idempotent historical Telegram ingestion foundation. Parse
source messages/media metadata first; do **not** begin batch OCR until
inventory/dedup and the low-resolution benchmark gates exist.

## Locked facts
- **The real archive is present**, local-only and gitignored, at
  `data/raw/ChatExport_2026-08-31`: 178,660 files, 7.0 GB, 183,897 messages,
  145,697 photos (`docs/ingestion/ARCHIVE_CHARACTERIZATION_2026-08-31.md`).
  **Corrected 2026-09-02 (KI-009):** 23,566 unique original images, 90% above
  900 px, 0.4% at ≤560 px; the earlier "median 520 px" counted thumbnail copies.
- **Extraction pipeline is built and measured (ADR 0008, ADR 0009).**
  `scripts/extract_facts.py` runs the corpus in about a minute into
  `data/derived/facts.sqlite`: 90,735 resolved facts with provenance (anchor
  box, value boxes, raw text, repair flag, rule id, engine and IMGT versions),
  83,499 review items. Evidence: `docs/ingestion/EXTRACTION_REVIEW_2026-09-02.md`.
- **Two form facts that constrain the product.** These laboratories leave the
  DQA1/DPA1/DPB1 rows blank (KI-013): DR/DQB matching only, no DP. The dominant
  letterhead disclaims its own blood-group field as patient-reported (KI-014).
- Donor/recipient role is read from the form's own printed field; captions and
  senders are not parsed yet because HIST-001 is not done (solutions doc, issue 3).
- **Accuracy is still unvalidated (KI-012); this is the binding constraint.**
  Every figure is a yield or an agreement rate. Two instruments now exist and
  both wait on a human: the blind golden corpus (2,189 cells,
  `tools/golden_label.html`, HA-007) and the anchored review pack (150
  documents from fifteen failure strata, `scripts/review_pack.py` +
  `tools/hla_review.html`, HA-008). `scripts/golden_score.py` scores either.
- **Independent confirmation (P4) and the constrained decode (P5) ran over the
  corpus.** Tesseract re-judged 2026-09-02 with star-less parsing: 22,969
  confirmed / 6,633 contradicted / 18,019 no opinion over 47,621 cells. The
  decode, after correcting a DIGITS_LOST gate that fired on the locus digit:
  44,504 UNANIMOUS / 2,255 SPLIT / 459 DIGITS_LOST resolved facts; SPLIT
  verdicts are real digit disagreements. ADR 0009 section 6 has the numbers.
- **The zero-fact documents are mostly not reports (KI-018, corrected).** Of
  the 4,944 that anchor nothing, 72% hold no allele-shaped value either and
  only 9% carry a locus label, against 99% of the documents that did produce
  facts. Just 170 are genuinely recoverable. The corpus is not hiding thousands
  of readable forms, so the work that pays is validating what is extracted.
- **OCR engine survey (2026-09-03).** 22 configurations on 600 real crops:
  PP-OCRv5 en-mobile-rec leads the practical field (0.970 trusted / 0.910 hard
  agreement, 13 ms/crop, CPU) against Tesseract's 0.900 / 0.515. The pipeline's
  own recognizer loses 56 points when the crop is padded by a few pixels, so it
  depends on the detector's box being exact. Cloud models were never shown real
  data (PHI) and no keys exist (HA-010).
  `docs/ingestion/OCR_MODEL_SURVEY_2026-09-03.md`.
- **The workstation powers off unexpectedly, and it is not this workload.** 35
  unclean shutdowns on record since 2026-06-11, most before this project, with
  no bug-check, dump or hardware-error entry. The GPU model runs were stopped
  anyway. `docs/operations/WORKSTATION_STABILITY.md`.
- Forwarded messages are 37% of the corpus and joined (senderless) messages 7%:
  "current poster ≠ forwarded author" is a mainstream path.
- Raw historical inputs are immutable/local-only and never committed.
- HLA geometry determines locus; OCR may not assign loci from token text alone.
- Critical low-resolution OCR requires human review before Gold publication.
- Matching is not part of the active MVP-HIST task yet.

## Completed foundation
- Product/architecture/OCR/HLA/matching/security documents; agentic scaffold;
  work queue, feature specs, handoff protocol, credential doctor, context packs.
- **P0 harness repair (2026-09-01):** git, lint/format/type gate, pinned 3.12 +
  `uv.lock`, `verify_repo.py` matches CI. `docs/agent-harness/HARNESS_READINESS_REVIEW_2026-09-01.md`.
- **P1 autonomy (2026-09-01):** hooks, permissions, default-FAIL acceptance
  ledger with gated `taskctl`, `AGENT_STOP`/`STEER.md`. Adversarially audited;
  8 defects fixed; residual limits in KI-005/KI-006.
- **P2 test depth (2026-09-01):** 12-step gate; invariant→test traceability;
  Hypothesis tests; coverage ratchet 65% / medical modules 100%; PII scanner
  with the national-ID checksum; bandit + gitleaks + osv-scanner + SBOM; mutmut;
  synthetic Telegram fixture corpus. Blocked layers: `docs/operations/TEST_PLAN.md` §10.
- **Derived local stores (gitignored):** `data/derived/ocr_pass.sqlite` (text +
  boxes for every original, resumable via `scripts/ocr_pass.py`),
  `facts.sqlite` (facts, confirmation, decode tables), `data/review/golden/`,
  `data/review/hla_pack/`.

## Human actions open
HA-008 label the review pack (≈2.5 h) · HA-007 blind golden corpus · HA-009
empty-cell policy · HA-006 IMGT pin · HA-003 resolution bands · HA-005 name
hashing · HA-004 Iranian practice · HA-010 cloud keys (optional). Recommendations
per item: `docs/ingestion/OPEN_ISSUES_SOLUTIONS_2026-09-02.md` issue 4.

## Current blockers
None for HIST-001: the 12-step gate passes, parser dependencies import, the
fixture corpus and DOM reference are present. Real-data runs need the local
export path; tests use synthetic fixtures.

## Next actions
1. **Human: label the pack (HA-008).** Then an agent scores it per stratum; the
   clean-control rate decides whether anything can be published.
2. **HIST-001 test-first**, then HIST-002; the caption role extractor is their
   first consumer (solutions doc, issue 3).
3. Agent work that needs no human: ENTITY-001 spec and tables (issue 2);
   re-run `scripts/decode_pass.py` after any gate change. A second confirmer
   (PP-OCRv5) is measured and recommended but needs the dependency decision.
4. Human "yes" items: HA-009 (queue policy), HA-006, HA-003, HA-005.

Acceptance state: `python scripts/acceptance.py status`. All criteria across
the live tasks are unmet by design.

## Last verified baseline
`python scripts/verify_repo.py` → **PASS (12 steps, none skipped)**, 2026-09-02.
Re-run it yourself; this file records a past result, not the current environment.
