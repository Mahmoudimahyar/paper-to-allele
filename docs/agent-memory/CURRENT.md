# Current project state

**Updated:** 2026-09-01
**Canonical phase:** MVP-HIST
**Active task:** HIST-001
**Active plan:** `docs/exec-plans/active/MVP-HIST-001-bootstrap-ingestion.md`

## Goal now
Build the local, idempotent historical Telegram ingestion foundation. Parse source messages/media metadata first; do **not** begin batch OCR until inventory/dedup and the low-resolution benchmark gates exist.

## Locked facts
- **The real archive is present**, local-only and gitignored, at `data/raw/ChatExport_2026-08-31`: 178,660 files, 7.0 GB, 183,897 messages, 145,697 photos. Measured figures: `docs/ingestion/ARCHIVE_CHARACTERIZATION_2026-08-31.md`.
- Images are low resolution (median longest edge **520 px**, 77% ≤640 px) — but **not** because thumbnails replaced missing originals. Every asset has its original; there are **zero** thumbnail-only assets. Quality must therefore be judged on pixel dimensions, not on a `_thumb` filename. See KI-007 and HA-003; this is a safety gate, not a cosmetic detail.
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
