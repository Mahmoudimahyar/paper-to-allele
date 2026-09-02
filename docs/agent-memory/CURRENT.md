# Current project state

**Updated:** 2026-09-02
**Canonical phase:** MVP-HIST
**Active task:** HIST-001
**Active plan:** `docs/exec-plans/active/MVP-HIST-001-bootstrap-ingestion.md`

## Goal now
Build the local, idempotent historical Telegram ingestion foundation. Parse source messages/media metadata first; do **not** begin batch OCR until inventory/dedup and the low-resolution benchmark gates exist.

## Locked facts
- **The real archive is present**, local-only and gitignored, at `data/raw/ChatExport_2026-08-31`: 178,660 files, 7.0 GB, 183,897 messages, 145,697 photos. Measured figures: `docs/ingestion/ARCHIVE_CHARACTERIZATION_2026-08-31.md`.
- **Corrected 2026-09-02 (KI-009):** the archive holds **23,566 unique original
  images, 90% above 900 px and 0.4% at ≤560 px.** The earlier "median 520 px,
  77% ≤640 px" counted 9,581 thumbnail copies (`_thumb (n).jpg`) as originals.
  Quality is still judged on pixel dimensions, never on filename (KI-007,
  HA-003), but low resolution is a small band, not the corpus.
- **Extraction pipeline is built and measured (2026-09-02).** ADR 0008 plus the
  skeptical review's P0, P1, P2 and P7. `scripts/extract_facts.py` runs the whole
  corpus in about a minute into `data/derived/facts.sqlite`: **90,735 resolved
  facts** with provenance, 83,499 review items. Every fact records its anchor
  box, value boxes, raw text, repair flag, rule id and the engine and IMGT
  versions. Detail and evidence: `ADR 0008`, and
  `docs/ingestion/EXTRACTION_REVIEW_2026-09-02.md` sections 3a and 4.
- **Two form facts that constrain the product.** These laboratories print
  DQA1/DPA1/DPB1 rows and leave them blank (KI-013), so the archive supports
  DR/DQB matching and not DP. The dominant letterhead disclaims its own
  blood-group field as patient-reported (KI-014).
- Donor/recipient role is read from the form's own printed field, never from a
  whole-page word search, which would invert it on hundreds of documents.
- **Accuracy is still unvalidated (KI-012), and this is the binding
  constraint.** Every figure above is a yield or an internal-consistency rate;
  no extracted value has been compared to a human reading. **Next: P3 — build
  the labelling tool and label the golden corpus** (199 documents, thumbnail-free,
  about 1,650 cells). It is the only route out of `BLOCKED_BY_BENCHMARK` for
  OCR-001. Then P4 (Tesseract confirmer), P5 (constrained CTC decode), P6
  (PCR-SSP form).
- Forwarded messages are 37% of the corpus and joined (senderless) messages 7%, so "current poster ≠ forwarded author" and sender carry-forward are mainstream paths, not edge cases.
- HTML structure is useful; JSON export is optional improvement, not a blocker.
- Raw historical inputs are immutable/local-only and never committed.
- HLA geometry determines locus; OCR may not assign loci from token text alone.
- Critical low-resolution OCR requires human review before historical Gold publication.
- Matching is not part of the active MVP-HIST task yet.

## Completed foundation
- Product/architecture/OCR/HLA/matching/security technical documents exist.
- Agentic repository scaffold created for Codex + Claude Code.
- Work queue, feature specs, session handoff protocol, credential doctor, context-pack tooling, and verification scripts defined.
- **P0 harness repair done (2026-09-01).** Git initialized; lint/format/type gate green; pinned 3.12 env + `uv.lock`; `verify_repo.py` no longer skips steps and now matches CI exactly. See `docs/agent-harness/HARNESS_READINESS_REVIEW_2026-09-01.md`.

## Harness work still outstanding
**P1 (autonomy) is done** (2026-09-01): hooks, permissions allow/ask/deny, default-FAIL acceptance ledger with a gated `taskctl`, per-task acceptance commands, and the `AGENT_STOP`/`STEER.md` operator channel. See `docs/agent-harness/OPERATOR_CONTROLS.md`.

P1 was then adversarially audited; 8 confirmed defects were fixed, including a
guard that failed **open** on non-object payloads, a comment that disabled the
ledger guard entirely, an unprotected `WORK_QUEUE.json` that made the whole
COMPLETE gate optional, and a hook that edited files outside the repository.
Residual limits and unverified claims: `KNOWN_ISSUES.md` KI-005/KI-006.

**P2 (test depth) is done** (2026-09-01) except for layers blocked on code that
does not exist yet. `verify_repo.py` is now a 12-step gate. What landed:
- invariant->test traceability (`scripts/invariant_lint.py`), enforced at task COMPLETE;
- property-based tests (Hypothesis) on HLA normalization and media resolution;
- coverage gate: repo ratchet 65%, medical modules (hla, domain, ingestion/media) 100%;
- Iranian PII scanner with the national-ID mod-11 checksum, redacted output;
- bandit + gitleaks + osv-scanner + SBOM path; mutmut configured with a threshold gate;
- synthetic Telegram export fixture corpus + `docs/ingestion/TELEGRAM_HTML_EXPORT_STRUCTURE.md`.

Still blocked on code that does not exist: OCR golden/metamorphic tests, the
synthetic Persian lab-form generator, DB constraint tests, Playwright/axe UI
tests. See `docs/operations/TEST_PLAN.md` section 10 for the honest layer list.

## Run in progress (2026-09-02)
`scripts/ocr_pass.py` is extracting text + box geometry from all 33,147 unique
originals. ~4.35 img/s, ETA ~2.1 h, output in gitignored
`data/derived/ocr_pass.sqlite`.

It is **resumable and idempotent** — just re-run the same command; completed
SHA-256s are skipped:

```bash
uv run --frozen --extra hist --extra ocr python scripts/ocr_pass.py --batch-size 250
uv run --frozen --extra hist --extra ocr python scripts/ocr_pass.py --status
```

This pass extracts text and geometry ONLY. It assigns no HLA locus — that needs
the template registry, which needs the golden corpus. Its purpose is to unblock
document classification, template discovery, and stratified sampling of the 200
golden documents from the HLA stratum. See ADR 0006.

## Current blockers
None for HIST-001. Verified from a clean clone: the 12-step gate passes, the
parser dependencies (bs4/lxml) import, the fixture corpus and DOM reference are
present, and `context_pack.py --task HIST-001` surfaces both. The human must provide a local Telegram export path when running against real data, but tests use synthetic fixtures.

## Next actions
1. **Implement HIST-001 test-first.** The fixture corpus, the DOM reference and the acceptance command all exist. Write one failing test per spec invariant (`python scripts/invariant_lint.py` lists the five HIST-001 owns), then the parser.
2. HIST-002 bundle reconstruction, then MEDIA-001 / DEDUPE-001.
3. P2-5 synthetic Persian lab-form generator — schedule early; all OCR work depends on it and it unblocks the 200-document golden-corpus gate.

Acceptance state: run `python scripts/acceptance.py status`. All 9 criteria across the 4 live tasks are unmet by design; `HIST-002`/`DEDUPE-001` have no tests yet, so their acceptance command exits non-zero rather than empty-passing.

## Last verified baseline
`python scripts/verify_repo.py` → **PASS (12 steps, none skipped)**, 2026-09-01,
from a clean `git clone` with nothing pre-built. 96 tests.
Re-run it yourself; this file records a past result, not the current environment.
