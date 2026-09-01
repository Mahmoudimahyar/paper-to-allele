# Cross-agent session protocol

## Start of every fresh Codex/Claude Code session
1. Agent reads root instructions automatically.
2. Read `docs/agent-memory/CURRENT.md` (target <=120 lines).
3. Resolve task from human request or `docs/work/WORK_QUEUE.json`.
4. Run `python scripts/doctor.py --brief`.
5. Run `python scripts/context_pack.py --task TASK-ID`.
6. Read the linked execution plan and only the task-specific context first.
7. Confirm working tree state before editing.

## Work loop
For each tractable increment:
1. State the objective and acceptance command in the execution plan.
2. Add/update failing test(s).
3. Implement the minimal behavior.
4. Run focused verification.
5. Commit or leave a clean, clearly described checkpoint.
6. Update the execution plan progress/decision log.

## High-risk evaluator loop
For OCR acceptance, HLA, matching, authentication/authorization, document access, identity, trust/safety, or compensation isolation:
1. implementation agent completes focused tests;
2. separate reviewer agent/session receives spec + diff + test results, not the original implementation conversation;
3. reviewer searches for counterexamples, missing tests, security/privacy leakage, silent fallback, and contradiction with policy;
4. implementation agent fixes findings and reruns verification.

## End of session
Run `python scripts/handoff.py`. The handoff must record:
- task and plan;
- what changed;
- exact verification commands/results;
- unresolved failures/issues;
- decisions promoted to docs/ADR;
- next 1-3 actions;
- any `HUMAN ACTION REQUIRED` item names (never secret values).

## Memory hygiene
- `CURRENT.md`: only current state and pointers.
- archived handoff: session-specific details.
- `KNOWN_ISSUES.md`: unresolved persistent technical issues.
- ADR/domain doc: durable fact or decision.
- Git history: what changed.
Do not duplicate a durable fact into every memory file.
