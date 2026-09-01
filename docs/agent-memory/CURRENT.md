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
P1 (autonomy) and P2 (test depth) from the readiness review are **not** done. Most load-bearing gaps before a long unattended run:
- no hooks, no `permissions.allow` — the agent will stop on prompts;
- `taskctl.py set ... COMPLETE` has no evidence gate;
- 1 of 42 tasks has a machine-checkable acceptance command;
- `tests/{e2e,integration,ocr,property}/` are still empty.

## Current blockers
None for HIST-001. The human must provide a local Telegram export path when running against real data, but tests use synthetic fixtures.

## Next actions
1. P1 harness batch: hooks, permissions allowlist, default-FAIL acceptance ledger, kill-switch, acceptance commands on every READY task.
2. P2-1/P2-2: invariant→test markers with a coverage lint, then property tests on `normalize_reported_hla` and `resolve_best_available_media`.
3. Implement/finish HIST-001 parser against synthetic HTML fixtures and characterize real export structure locally.

## Last verified baseline
`python scripts/verify_repo.py` → **PASS (8 steps, none skipped)**, 2026-09-01, commit `green baseline`.
16 tests pass. Re-run it yourself; this file records a past result, not the current environment.
