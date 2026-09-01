# Contributing

## Change workflow
1. Pick one task from `docs/work/WORK_QUEUE.json`.
2. Create/update an execution plan for non-trivial work.
3. Add or update a failing test first.
4. Implement the minimal change.
5. Run focused tests, then `python scripts/verify_repo.py`.
6. Run an independent review for high-risk changes.
7. Update traceability/memory and commit in reviewable units.

## Commit guidance
Prefer small semantic commits such as `feat(ingestion): ...`, `test(ocr): ...`, `docs(agent): ...`, `fix(hla): ...`. Never commit secrets or real medical data.

## Branch/worktree guidance
One agent = one task = one branch/worktree when parallel work is used. Merge only after verification; do not share an uncommitted working tree across agents.
