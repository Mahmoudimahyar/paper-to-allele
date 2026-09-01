---
name: km-verify
description: Verify KidneyMatch work before completion or handoff. Use after implementation, refactors, doc changes, or when claiming a task is done.
---

# Verify
1. `python scripts/verify_repo.py` — 8 mandatory steps, identical to CI. It never skips a step; a missing tool is a failure, not a skip.
2. `python scripts/acceptance.py run <TASK>` — runs the task's acceptance commands and writes evidence to `.artifacts/<TASK>/`.
3. `python scripts/acceptance.py mark <TASK> <N> --evidence <log>` for each criterion actually demonstrated by that evidence.
4. `python scripts/taskctl.py set <TASK> COMPLETE` — refuses unless every criterion is met with existing evidence, and re-runs the commands itself.

Do not edit `docs/work/acceptance.json` by hand; a hook blocks it. Do not use `taskctl --force`: that is a human override, not a way to unblock yourself.

For high-risk changes, run a separate skeptical review that tries counterexamples and permission/security failures.
Report commands and results. "Looks good" is not evidence.
