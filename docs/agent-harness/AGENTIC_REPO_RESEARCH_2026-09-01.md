# Agentic repository design research — 2026-09-01

## Decisions adopted

1. **Short root instructions; repo docs as system of record.** OpenAI's 2026 Harness Engineering report describes a short `AGENTS.md` acting as a map, with structured docs and first-class execution plans rather than a giant instruction manual.
2. **Progressive disclosure.** Codex loads repo skills from `.agents/skills` progressively; Claude Code project skills live in `.claude/skills`. The repo mirrors the same shared workflows into both locations.
3. **One canonical instruction source.** Claude's official docs recommend a `CLAUDE.md` that imports `@AGENTS.md` when a repo supports other coding agents. This prevents instruction drift.
4. **Path-scoped rules for expensive context.** Claude recommends keeping `CLAUDE.md` concise (target under 200 lines) and using `.claude/rules/`/skills so specialized instructions load only when relevant.
5. **Structured handoffs for long-running work.** Anthropic's long-running-agent work found that fresh sessions need durable progress artifacts plus Git history; later harness work emphasizes structured artifacts and an independent evaluator/reviewer.
6. **Small high-signal context.** Anthropic's context-engineering guidance recommends the smallest useful set of tokens and just-in-time retrieval rather than loading an entire knowledge base by default.
7. **Mechanical enforcement over prompt-only rules.** Critical architecture/security rules are linted/tested in scripts and CI. Instructions guide behavior; CI establishes invariants.
8. **Evidence-based completion.** Agents must provide passing commands/tests, not self-assess that code is correct.
9. **Independent skeptical review for high-risk domains.** Matching, HLA, OCR acceptance, identity, auth, and medical-document access get a separate review pass.
10. **Simple harness first.** We do not build a custom autonomous orchestration framework in the starter. Codex/Claude Code operate directly against versioned tasks/plans; multi-agent/subagent work is used only where separation of context or independent evaluation provides value.

## Token-efficiency design

- `AGENTS.md` contains universal invariants and a map, not full domain docs.
- `docs/index.json` maps tasks/topics to only the files needed.
- `scripts/context_pack.py` emits a minimal task context pack.
- `.agents/skills` and `.claude/skills` package repeatable workflows and load on demand.
- Verbose command outputs/reports go to `.artifacts/`; console summaries stay concise.
- Cross-agent memory uses a small `CURRENT.md` plus archived handoffs; detailed facts are promoted to durable docs/ADRs instead of accumulating in memory.

## Primary research sources

- OpenAI, “Harness engineering: leveraging Codex in an agent-first world,” 2026-02-11: https://openai.com/index/harness-engineering/
- OpenAI Codex docs, “Custom instructions with AGENTS.md”: https://developers.openai.com/codex/guides/agents-md
- OpenAI/ChatGPT Learn, Codex skills/customization docs: https://learn.chatgpt.com/docs/customization/overview
- Anthropic, “Effective context engineering for AI agents,” 2025-09-29: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Anthropic, “Effective harnesses for long-running agents,” 2025-11-26: https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- Anthropic, “Harness design for long-running application development,” 2026-03-24: https://www.anthropic.com/engineering/harness-design-long-running-apps
- Claude Code docs, project memory and `CLAUDE.md`: https://code.claude.com/docs/en/memory
- Claude Code docs, skills: https://code.claude.com/docs/en/skills
- OWASP ASVS 5.0: https://owasp.org/www-project-application-security-verification-standard/
