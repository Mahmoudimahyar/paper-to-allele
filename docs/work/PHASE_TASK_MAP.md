# Zero-to-100 phase/task map

The machine-readable source is `WORK_QUEUE.json`. The queue intentionally contains later-phase tasks that are **BACKLOG**, not READY. A coding agent may inspect them to understand the whole project but must not implement a BACKLOG task until a task-specific feature spec and execution plan are promoted to READY.

This prevents a long-running agent from inventing late-stage requirements while still giving every fresh session a complete map from historical ingestion through the public website.

Use:
```bash
python scripts/taskctl.py next
python scripts/taskctl.py list
```

Status semantics:
- `COMPLETE`: verified historical work.
- `ACTIVE`: the single current editing objective.
- `READY`: fully specified and eligible after dependencies.
- `BACKLOG`: known future work; must be specified before coding.
- `BLOCKED*`: known work with an explicit prerequisite.
