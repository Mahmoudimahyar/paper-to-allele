#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "docs/work/WORK_QUEUE.json"


def load() -> dict[str, object]:
    return json.loads(PATH.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sub.add_parser("next")
    setp = sub.add_parser("set")
    setp.add_argument("task")
    setp.add_argument("status")
    args = parser.parse_args()
    data = load()
    tasks: list[dict[str, object]] = data["tasks"]  # type: ignore[assignment]
    if args.cmd == "list":
        for t in tasks:
            print(f"{t['id']:20} {t['status']:22} {t['phase']:14} {t['title']}")
        return 0
    if args.cmd == "next":
        active = [t for t in tasks if t["status"] == "ACTIVE"]
        ready = [t for t in tasks if t["status"] == "READY"]
        for t in active + ready[:1]:
            print(f"{t['id']}\t{t['status']}\t{t['title']}")
        return 0
    allowed = set(data["status_values"])  # type: ignore[arg-type]
    if args.status not in allowed:
        raise SystemExit(f"invalid status {args.status}; choose {sorted(allowed)}")
    target = next((t for t in tasks if t["id"] == args.task), None)
    if target is None:
        raise SystemExit(f"unknown task {args.task}")
    target["status"] = args.status
    if args.status == "ACTIVE":
        for t in tasks:
            if t is not target and t["status"] == "ACTIVE":
                t["status"] = "READY"
        data["active_task"] = args.task
    PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{args.task} -> {args.status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
