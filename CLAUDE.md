@AGENTS.md

## Claude Code-specific notes
- Treat repo-tracked `docs/agent-memory/` as canonical cross-agent memory. Claude auto-memory may record local convenience notes, but must not override repo facts or contain secrets/PII.
- Use path-scoped `.claude/rules/` and project skills instead of expanding this file.
- For complex tasks, prefer explore/plan/implement/verify; use a fresh skeptical review subagent/session when the task is high risk.
- Before reporting success, show verification evidence rather than self-assessing quality.
