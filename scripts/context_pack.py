#!/usr/bin/env python3
"""Return the smallest high-signal repo context for one task."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUEUE = json.loads((ROOT / "docs/work/WORK_QUEUE.json").read_text(encoding="utf-8"))

ALWAYS = [
    "docs/agent-memory/CURRENT.md",
    "docs/product/PRODUCT_CONSTITUTION.md",
]


def task_by_id(task_id: str) -> dict[str, object]:
    for task in QUEUE["tasks"]:
        if task["id"] == task_id:
            return task
    raise SystemExit(f"Unknown task: {task_id}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    task = task_by_id(args.task)
    paths: list[str] = []
    for path in (
        ALWAYS
        + [str(task.get("spec", "")), str(task.get("plan", ""))]
        + list(task.get("context", []))
    ):
        if path and path not in paths:
            paths.append(path)
    missing = [p for p in paths if not (ROOT / p).exists()]
    payload = {
        "task": task["id"],
        "title": task["title"],
        "status": task["status"],
        "read_in_order": paths,
        "missing": missing,
        "acceptance": task.get("acceptance", []),
        "instruction": (
            "Read these files first. Retrieve more context only when the task requires it; "
            "do not preload the consolidated technical bible."
        ),
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Context pack for {task['id']} — {task['title']}")
        for idx, path in enumerate(paths, 1):
            print(f"{idx}. {path}")
        if task.get("acceptance"):
            print("Acceptance:")
            for cmd in task["acceptance"]:
                print(f"  - {cmd}")
        if missing:
            print("ERROR: missing indexed files:", ", ".join(missing))
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
