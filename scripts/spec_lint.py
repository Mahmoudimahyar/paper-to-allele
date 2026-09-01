\
#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {"id", "version", "status", "risk", "goal", "non_goals", "actors", "preconditions", "invariants", "acceptance"}
ALLOWED = {"DRAFT", "READY", "ACTIVE", "BLOCKED", "BACKLOG"}

errors: list[str] = []
ids: set[str] = set()
for path in sorted((ROOT / "specs/features").glob("*.json")):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"{path}: invalid JSON: {exc}")
        continue
    missing = REQUIRED - set(data)
    if missing:
        errors.append(f"{path}: missing required keys {sorted(missing)}")
    if data.get("status") not in ALLOWED:
        errors.append(f"{path}: invalid status {data.get('status')!r}")
    if data.get("id") in ids:
        errors.append(f"{path}: duplicate spec id {data.get('id')}")
    ids.add(data.get("id"))
    if data.get("status") in {"READY", "ACTIVE"}:
        serialized = json.dumps(data, ensure_ascii=False).upper()
        if "TBD" in serialized or "TODO" in serialized:
            errors.append(f"{path}: READY/ACTIVE spec contains TBD/TODO")
        if not data.get("invariants") or not data.get("acceptance"):
            errors.append(f"{path}: READY/ACTIVE spec requires invariants and acceptance")

queue = json.loads((ROOT / "docs/work/WORK_QUEUE.json").read_text(encoding="utf-8"))
for task in queue["tasks"]:
    spec_path = task.get("spec")
    if task.get("status") in {"READY", "ACTIVE"} and not spec_path:
        errors.append(f"work queue {task['id']}: READY/ACTIVE task has no feature spec")
        continue
    if spec_path and not (ROOT / spec_path).exists():
        errors.append(f"work queue {task['id']}: missing spec {spec_path}")

if errors:
    print("spec_lint: FAIL")
    for error in errors:
        print(" -", error)
    sys.exit(1)
print(f"spec_lint: OK ({len(ids)} feature specs)")
