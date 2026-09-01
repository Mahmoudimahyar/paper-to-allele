# Repository memory system

This directory is the canonical memory shared by Codex, Claude Code, and humans.

- `CURRENT.md`: short state index loaded first.
- `KNOWN_ISSUES.md`: persistent unresolved issues only.
- `HUMAN_ACTIONS.md`: requests that require a person; never contains secret values.
- `handoffs/`: archived session handoffs.

Claude auto-memory is optional secondary memory and must not override this directory. If auto-memory learns something durable, promote it into code/docs/ADR and remove stale duplication.
