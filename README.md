# KidneyMatch Iran — Agentic Starter Repository

This repository is the executable starting point for the Iran-only kidney donor/recipient matching project.

**Current active phase:** `MVP-HIST` — reconstruct the historical Telegram archive locally, deduplicate it, extract evidence conservatively from low-resolution images, human-review critical HLA values, and publish a provenance-rich Gold database.

## Start here — human or coding agent

1. If this ZIP was not cloned from Git, optionally run `bash scripts/init_repo.sh` after configuring Git identity.
2. Read `AGENTS.md` (Codex) or `CLAUDE.md` (Claude Code; it imports `AGENTS.md`).
3. Run `python scripts/doctor.py`. For a clean Python 3.12 environment, `bash scripts/bootstrap.sh` is available.
4. Run `python scripts/context_pack.py --task HIST-001`.
5. Read the active execution plan printed by the context pack.
6. Implement test-first; do not invent missing behavior.
7. Run `python scripts/verify_repo.py` before declaring completion.
8. Run `python scripts/handoff.py ...` before ending a session.

## Why the repository is structured this way

The repo is optimized for **progressive disclosure**: root instructions are intentionally short; deeper context lives in indexed, versioned docs, feature specs, execution plans, and agent skills. Durable project memory lives in Git-tracked files so Codex, Claude Code, and humans share the same source of truth.

## Clinical safety boundary

This project initially reconstructs historical evidence and later provides compatibility **pre-screening**. It is not a substitute for a transplant center, donor-specific antibody interpretation, virtual/physical crossmatch, or donor medical clearance. Missing clinical data is `UNKNOWN`, never assumed compatible.

## Current media constraint

The historical export contains many low-resolution Telegram images and thumbnails, and in some cases no better image exists. The pipeline must use the **best physically available asset**, record its quality, apply geometry-aware extraction, strict HLA vocabulary validation, multi-engine consensus where useful, and abstain when uncertainty remains. It must never fabricate a higher-resolution source.

## Key directories

- `docs/INDEX.md` — documentation map.
- `docs/agent-memory/CURRENT.md` — cross-agent current state.
- `docs/exec-plans/active/` — active long-running plans.
- `docs/work/WORK_QUEUE.json` — machine-readable work queue.
- `specs/features/` — executable feature contracts.
- `.agents/skills/` — Codex project skills.
- `.claude/skills/` — generated Claude Code mirrors of the shared skills.
- `src/kidneymatch/` — application/domain code.
- `tests/` — layered verification.
- `data/` — local data contract only; real historical data is gitignored.

## Non-negotiable privacy rule

Never commit real donor/recipient identities, phone numbers, national IDs, medical images, Telegram exports, OCR crops, logs containing protected information, or Playwright traces containing real data.
