#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "id",
    "version",
    "status",
    "risk",
    "goal",
    "non_goals",
    "actors",
    "preconditions",
    "invariants",
    "acceptance",
}
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
LIVE = {"READY", "ACTIVE"}

# spec path -> {criterion: [task ids that claim it]}
claimed: dict[str, dict[str, list[str]]] = {}

for task in queue["tasks"]:
    spec_path = task.get("spec")
    live = task.get("status") in LIVE
    if live and not spec_path:
        errors.append(f"work queue {task['id']}: READY/ACTIVE task has no feature spec")
        continue
    if spec_path and not (ROOT / spec_path).exists():
        errors.append(f"work queue {task['id']}: missing spec {spec_path}")
        continue
    if not live:
        continue

    # P1-4: prose acceptance cannot end an autonomous loop. A live task must
    # carry at least one command that exits 0 or non-zero.
    if not task.get("acceptance"):
        errors.append(
            f"work queue {task['id']}: READY/ACTIVE task has no acceptance command. "
            f'Add a runnable command, e.g. "uv run --frozen pytest --task {task["id"]} -q".'
        )

    # Each live task must own named spec acceptance criteria, quoted verbatim,
    # so that a spec shared by two tasks has no ambiguous 'done'.
    spec = json.loads((ROOT / spec_path).read_text(encoding="utf-8"))
    spec_acceptance = list(spec.get("acceptance", []))
    owned = task.get("spec_criteria")
    if not owned:
        errors.append(
            f"work queue {task['id']}: READY/ACTIVE task must list spec_criteria "
            f"naming which acceptance bullets of {spec_path} it owns"
        )
        owned = []
    for criterion in owned:
        if criterion not in spec_acceptance:
            errors.append(
                f"work queue {task['id']}: spec_criteria entry is not a verbatim "
                f"acceptance bullet of {spec_path}: {criterion!r}"
            )
        claimed.setdefault(spec_path, {}).setdefault(criterion, []).append(task["id"])

# No acceptance criterion of a live spec may be unowned or double-owned:
# an unowned criterion is a requirement nobody is accountable for.
for spec_path, owners in claimed.items():
    spec = json.loads((ROOT / spec_path).read_text(encoding="utf-8"))
    for criterion in spec.get("acceptance", []):
        holders = owners.get(criterion, [])
        if not holders:
            errors.append(
                f"{spec_path}: acceptance criterion is owned by no live task: {criterion!r}"
            )
        elif len(holders) > 1:
            errors.append(
                f"{spec_path}: acceptance criterion owned by multiple tasks "
                f"{holders}: {criterion!r}"
            )

if errors:
    print("spec_lint: FAIL")
    for error in errors:
        print(" -", error)
    sys.exit(1)
print(f"spec_lint: OK ({len(ids)} feature specs)")
