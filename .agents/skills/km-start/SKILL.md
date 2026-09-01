---
name: km-start
description: Orient at the beginning of a KidneyMatch session or task. Use before editing when you need current state, task scope, prerequisites, and minimal context.
---

# Start a KidneyMatch task
1. Read `docs/agent-memory/CURRENT.md`.
2. Resolve the requested task from `docs/work/WORK_QUEUE.json`.
3. Run `python scripts/doctor.py --brief`.
4. Run `python scripts/context_pack.py --task <TASK-ID>`.
5. Run `python scripts/acceptance.py status <TASK-ID>` to see which criteria are still unmet (all start unmet by design).
6. Read only the returned files first.
7. Inspect Git status before editing.
8. If the task is complex, ensure its execution plan exists and is current.
Do not load the consolidated technical bible unless the task-specific docs are insufficient.
