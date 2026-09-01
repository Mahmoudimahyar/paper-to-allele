---
name: km-handoff
description: Create durable repository memory before ending a KidneyMatch coding session or switching agents. Use after substantive work even when the task is incomplete.
---

# Handoff
1. Run verification relevant to the current checkpoint.
2. Promote durable decisions/facts into specs, ADRs, code, or domain docs.
3. Update `KNOWN_ISSUES.md` only for persistent unresolved issues.
4. Add human-only blockers to `HUMAN_ACTIONS.md` without secret values.
5. Run `python scripts/handoff.py --agent <codex|claude|human> --task <ID> --summary "..." --next "..."`.
6. Keep `CURRENT.md` concise and update it if phase/task/next actions changed.
