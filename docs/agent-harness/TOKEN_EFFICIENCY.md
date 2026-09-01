# Token-efficiency policy

1. Root instructions remain short and stable.
2. Load task context just-in-time through `scripts/context_pack.py`.
3. Do not include the long consolidated technical bible in every context.
4. Put repeated procedures in skills, not prompts.
5. Prefer tools/scripts that return concise structured summaries; write verbose diagnostics to `.artifacts/`.
6. Promote durable facts into specs/ADRs/docs instead of repeatedly summarizing them in chat/handoffs.
7. Keep `CURRENT.md` below 120 lines; archive detail in handoffs.
8. Use specialized subagents for read-heavy investigations only when they prevent pollution of the main implementation context; return a short evidence summary.
9. Use a fresh reviewer context for high-risk review rather than asking the implementer to praise/review its own work.
10. Do not pre-load later-phase docs while implementing MVP-HIST.
