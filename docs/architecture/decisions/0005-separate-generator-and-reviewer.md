# ADR 0005 — Separate implementation and skeptical review for high-risk code

**Status:** Accepted

## Decision
After implementation of matching/HLA/OCR acceptance/auth/document-access/trust-safety code, use a separate agent/session as skeptical reviewer with spec + diff + tests.

## Consequences
Self-evaluation bias is reduced; review findings become tests/fixes before completion.
