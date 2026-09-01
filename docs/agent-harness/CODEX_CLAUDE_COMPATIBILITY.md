# Codex + Claude Code compatibility

## Shared contract
`AGENTS.md` is the canonical universal instruction file.

- Codex reads root/nested `AGENTS.md` according to its normal project instruction chain.
- Claude Code reads root `CLAUDE.md`, which imports `@AGENTS.md`; nested `CLAUDE.md` files import their local `AGENTS.md`.

Do not independently maintain equivalent prose in both systems.

## Shared skills
Canonical repeatable workflows are authored under `.agents/skills/` and mirrored byte-for-byte to `.claude/skills/` by:

```bash
python scripts/sync_agent_skills.py
```

CI runs `--check` to prevent drift. The duplication is intentional for ZIP/Windows portability instead of relying on symlinks.

## Memory
Provider-specific memory is not canonical because it is not reliably shared across Codex, Claude Code, machines, and cloud sessions. Canonical memory is:

1. `docs/agent-memory/CURRENT.md`
2. active execution plan
3. archived handoff files
4. Git history
5. durable specs/ADRs/docs

Claude auto-memory may remain enabled as a convenience, but durable discoveries must be promoted into the repo and must never include secrets/real patient data.

## Recommended first prompt
A giant bootstrap prompt is unnecessary. From the repo root, a strong prompt is simply:

> Continue the active repository task. Follow the repo instructions, run the doctor/context-pack workflow, work test-first until the task is verified or genuinely blocked, then leave a durable handoff.

The repository carries the detail instead of repeatedly paying tokens for it.

## Parallel agents
Parallel work is allowed only for independent research/review or disjoint worktrees. The preferred high-risk pattern is sequential **implementer → independent reviewer → implementer fix**, because simultaneous edits create merge/context conflicts.
