---
name: km-plan
description: Create or update an execution plan for non-trivial KidneyMatch work before implementation. Use for tasks spanning multiple files, migrations, high-risk logic, or more than one verification layer.
---

# Plan a task
- Start from `docs/exec-plans/templates/EXEC_PLAN_TEMPLATE.md`.
- Link the feature spec and task ID.
- State objective/non-goals, invariants, milestones, exact acceptance commands, risks, rollback, and human blockers.
- Break work into independently verifiable increments.
- Do not pre-specify implementation details that the repo/framework can decide safely unless the architecture/policy requires them.
- Mark decisions that change architecture/policy for an ADR/document update.
