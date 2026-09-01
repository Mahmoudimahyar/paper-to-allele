#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "docs/work/WORK_QUEUE.json"


def load() -> dict[str, object]:
    return json.loads(PATH.read_text(encoding="utf-8"))


def completion_blockers(task_id: str) -> list[str]:
    """Reasons a task may not be marked COMPLETE. Empty list means it may."""
    import acceptance  # local import: taskctl stays usable if the ledger is absent

    ledger = acceptance.load_ledger()
    entry = ledger.get("tasks", {}).get(task_id)
    if entry is None:
        return [
            f"{task_id} has no acceptance ledger entry. Run `python scripts/acceptance.py sync`."
        ]

    blockers: list[str] = []
    if not entry["criteria"]:
        blockers.append("no acceptance criteria are recorded; nothing would be verified")
    for index, criterion in enumerate(entry["criteria"]):
        if not criterion["passes"]:
            blockers.append(f"criterion {index} not met: {criterion['criterion']}")
        elif not criterion.get("evidence"):
            blockers.append(f"criterion {index} claims a pass with no evidence file")
        elif not (ROOT / criterion["evidence"]).is_file():
            blockers.append(
                f"criterion {index} references missing evidence {criterion['evidence']}"
            )

    if not entry["commands"]:
        blockers.append("no acceptance command is defined")
    else:
        print(f"re-running acceptance commands for {task_id} (ledger claims are not trusted):")
        ok, _ = acceptance.run_commands(task_id, entry["commands"])
        if not ok:
            blockers.append("acceptance commands do not pass when re-run right now")

    return blockers


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sub.add_parser("next")
    setp = sub.add_parser("set")
    setp.add_argument("task")
    setp.add_argument("status")
    setp.add_argument(
        "--force",
        action="store_true",
        help="Human override of the COMPLETE gate. Requires --reason and is echoed loudly. "
        "Agents must not use this to unblock themselves.",
    )
    setp.add_argument("--reason", default="", help="Required with --force; recorded in output.")
    args = parser.parse_args()

    if getattr(args, "force", False) and not args.reason:
        raise SystemExit("--force requires --reason explaining why the gate is being bypassed")
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

    # P1-3: COMPLETE is the one transition an agent must not be able to assert.
    # Every criterion must be marked with evidence, AND the acceptance commands
    # are re-run here rather than trusted from the ledger, so a stale pass
    # recorded in an earlier session cannot carry a task over the line.
    if args.status == "COMPLETE" and not args.force:
        blocked = completion_blockers(args.task)
        if blocked:
            print(f"REFUSED: {args.task} cannot be marked COMPLETE.")
            for reason in blocked:
                print(" -", reason)
            print(
                "\nRun `python scripts/acceptance.py run "
                f"{args.task}` and mark each criterion with its evidence file."
            )
            return 2

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
