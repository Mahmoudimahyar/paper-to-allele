# Current project state

**Updated:** 2026-09-01
**Canonical phase:** MVP-HIST
**Active task:** HIST-001
**Active plan:** `docs/exec-plans/active/MVP-HIST-001-bootstrap-ingestion.md`

## Goal now
Build the local, idempotent historical Telegram ingestion foundation. Parse source messages/media metadata first; do **not** begin batch OCR until inventory/dedup and the low-resolution benchmark gates exist.

## Locked facts
- Current archive contains many low-resolution images; some have no better source. Use best physically available media and preserve `THUMBNAIL_ONLY` provenance.
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

**P2 (test depth) is NOT done.** `TEST_PLAN.md` lists ten test layers; four exist. Remaining, in priority order:
- P2-1 invariant→test markers plus a lint that fails when a live spec invariant has no covering test (the `invariant` marker is already registered in `tests/conftest.py`, unused);
- P2-2 property tests (`hypothesis` installed, `tests/property/` still empty);
- P2-3 mutation testing (no tool chosen);
- P2-4 metamorphic OCR tests; P2-5 synthetic Persian lab-form corpus generator (longest pole);
- P2-6 Playwright + axe on the review UI; P2-7 coverage/determinism/security scanning; P2-8 real PII scanner.

## Current blockers
None for HIST-001. The human must provide a local Telegram export path when running against real data, but tests use synthetic fixtures.

## Next actions
1. P2-1/P2-2: invariant→test markers with a coverage lint, then property tests on `normalize_reported_hla` and `resolve_best_available_media`.
2. P2-5: synthetic Persian lab-form generator — schedule early, all OCR work depends on it.
3. Implement/finish HIST-001 parser against synthetic HTML fixtures and characterize real export structure locally.

Acceptance state: run `python scripts/acceptance.py status`. All 9 criteria across the 4 live tasks are unmet by design; `HIST-002`/`DEDUPE-001` have no tests yet, so their acceptance command exits non-zero rather than empty-passing.

## Last verified baseline
`python scripts/verify_repo.py` → **PASS (8 steps, none skipped)**, 2026-09-01, commit `green baseline`.
16 tests pass. Re-run it yourself; this file records a past result, not the current environment.
