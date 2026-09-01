# ADR 0003 — Repo memory over provider-specific memory

**Status:** Accepted

## Decision
`docs/agent-memory/` + Git history + execution plans are canonical memory. Claude auto-memory is optional secondary memory.

## Rationale
Codex and Claude Code must see the same state across sessions and machines.
