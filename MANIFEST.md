# Starter repository manifest

## Agent entry points
- `AGENTS.md` — canonical cross-agent rules.
- `CLAUDE.md` — imports `AGENTS.md` plus Claude-specific notes.
- `.agents/skills/` — Codex shared workflows.
- `.claude/skills/` — mirrored Claude Code workflows.
- `.claude/rules/` — path-scoped Claude rules; nested `AGENTS.md`/`CLAUDE.md` give equivalent domain guidance.

## Cross-session memory
- `docs/agent-memory/CURRENT.md`
- `docs/agent-memory/KNOWN_ISSUES.md`
- `docs/agent-memory/HUMAN_ACTIONS.md`
- `docs/agent-memory/handoffs/`
- `docs/exec-plans/`
- Git history once initialized.

## Machine-readable controls
- `docs/work/WORK_QUEUE.json` — zero-to-100 task map.
- `config/credentials.json` — credential/human-action contract without values.
- `config/ocr_policy_v1.json`
- `config/matching_policy_ir_v1.json`
- `schemas/` and `specs/features/`.

## Universal commands
```bash
python scripts/doctor.py
python scripts/context_pack.py --task HIST-001
python scripts/taskctl.py next
python scripts/verify_repo.py
python scripts/handoff.py --agent codex --task HIST-001 --summary "..." --next "..."
```

## Current phase
`MVP-HIST`. No cloud credential is required. The active task is `HIST-001`. OCR is intentionally not the first implementation task; parse/inventory/dedupe/relevance come before OCR.
