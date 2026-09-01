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

## Current blockers
None for HIST-001. The human must provide a local Telegram export path when running against real data, but tests use synthetic fixtures.

## Next actions
1. Implement/finish HIST-001 parser against synthetic HTML fixtures and characterize real export structure locally.
2. Implement HIST-002 bundle reconstruction.
3. Implement DEDUPE-001 best-available media inventory + exact dedupe.

## Last verified baseline
Run `python scripts/verify_repo.py` after extraction from the ZIP. This file is not proof of a passing environment.
