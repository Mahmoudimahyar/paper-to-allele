# Handoff — P2-HARNESS

- **UTC:** 2026-09-02T00:11:24.405783+00:00
- **Agent:** claude
- **Commit/checkpoint:** db93a82
- **Verification command:** `python scripts/verify_repo.py`

## Completed
Repository is ready to begin HIST-001 implementation. verify_repo.py is a 12-step gate (skill sync, docs/spec/architecture/invariant lints, PII scan, ruff check+format, mypy, bandit, pytest+coverage, medical-module coverage at 100%) verified green from a fresh clone with 94 tests. P0 fixed the shipped starter (git init, 26 lint errors, stray backslashes, 3.12 pin, lockfile) and rebuilt verify_repo so it can no longer print PASS having skipped steps. P1 added enforcement: five hooks, permissions allow/ask/deny, a default-FAIL acceptance ledger whose criteria require evidence from a passing run of that task, a taskctl COMPLETE gate that re-runs the commands rather than trusting the ledger, and the AGENT_STOP/STEER.md operator channel; an adversarial audit then found and I fixed 8 real defects including a guard failing OPEN, a comment that disabled the ledger guard, an unprotected WORK_QUEUE.json that made the gate optional, and a hook editing files outside the repo. P2 added invariant->test traceability enforced at COMPLETE, 15 Hypothesis property tests (verified by injecting a silent low-resolution HLA promotion and watching them catch it), coverage ratchet plus 100% on medical modules, an Iranian PII scanner using the official mod-11 national-ID checksum with redacted output, bandit/gitleaks/osv-scanner/mutmut with a threshold gate, and a synthetic Telegram export fixture corpus with a DOM reference derived from the tdesktop generator source.

## Next
Implement HIST-001 test-first. Run scripts/invariant_lint.py for the five invariants HIST-001 owns, write one failing test per invariant against tests/fixtures/synthetic/telegram_export/, then the parser. Acceptance: uv run --frozen pytest --task HIST-001 -q. taskctl will refuse COMPLETE until every invariant has a covering test and the acceptance command passes on re-run. After MVP-HIST parsing, the longest pole is the synthetic Persian lab-form generator (P2-5), which unblocks the 200-document OCR golden-corpus gate.

## Known failures/blockers
None declared by handoff script. Add specific failures here if any verification did not pass.

## Human actions
See `docs/agent-memory/HUMAN_ACTIONS.md`. Never put secret values here.
