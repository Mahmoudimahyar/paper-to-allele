# ADR 0001 — Agent-first repository is the system of record

**Status:** Accepted

## Decision
Keep product policy, architecture, execution plans, tests, work queue, and cross-session memory versioned in-repo. Root agent instructions are a map, not a manual.

## Consequences
Agents can resume from a fresh session using Git-tracked artifacts; documentation drift is linted. Chat history is not a required dependency.
