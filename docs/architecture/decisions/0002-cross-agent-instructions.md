# ADR 0002 — AGENTS.md is canonical; CLAUDE.md imports it

**Status:** Accepted

## Decision
Use short root `AGENTS.md` for shared Codex/Claude instructions. `CLAUDE.md` imports `@AGENTS.md`. Shared repeatable workflows are authored in `.agents/skills` and mirrored into `.claude/skills`.

## Consequences
One source prevents instruction drift; sync is mechanically verified in CI.
