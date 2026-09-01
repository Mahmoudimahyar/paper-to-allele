---
name: km-verify
description: Verify KidneyMatch work before completion or handoff. Use after implementation, refactors, doc changes, or when claiming a task is done.
---

# Verify
Run focused acceptance commands from the feature spec/plan, then `python scripts/verify_repo.py`.
For high-risk changes, perform a separate skeptical review that tries counterexamples and permission/security failures.
Report commands and results. Do not use “looks good” as evidence.
