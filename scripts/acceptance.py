#!/usr/bin/env python3
"""Default-FAIL acceptance ledger.

P1-3 of the harness readiness review. Before this existed, `taskctl.py set <ID>
COMPLETE` wrote a status with no gate at all: an agent could mark work done
without running anything.

The contract:

* Every acceptance criterion of every live task starts `"passes": false`.
* A criterion may only be marked true with `mark`, which REQUIRES a non-empty
  evidence file produced by an actual command run. You cannot assert a pass from
  reasoning alone.
* `taskctl set <ID> COMPLETE` re-runs the task's acceptance commands rather than
  trusting the ledger, so stale evidence cannot carry a task over the line.

Subcommands
    sync            regenerate the ledger from WORK_QUEUE.json + specs,
                    preserving existing pass state for criteria that still exist
    run <TASK>      run the task's acceptance commands, writing evidence
    status [TASK]   print ledger state
    mark <TASK> <N> mark criterion N true, requires --evidence <path>
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUEUE_PATH = ROOT / "docs/work/WORK_QUEUE.json"
LEDGER_PATH = ROOT / "docs/work/acceptance.json"
ARTIFACTS = ROOT / ".artifacts"
LIVE = {"READY", "ACTIVE"}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


def load_ledger() -> dict:
    if LEDGER_PATH.is_file():
        return _read_json(LEDGER_PATH)
    return {"version": 1, "tasks": {}}


def build_ledger() -> dict:
    """Regenerate from the queue, carrying forward pass state for surviving criteria."""
    previous = load_ledger()
    queue = _read_json(QUEUE_PATH)
    tasks: dict[str, dict] = {}

    for task in queue["tasks"]:
        if task.get("status") not in LIVE:
            continue
        task_id = task["id"]
        prior = {
            entry["criterion"]: entry
            for entry in previous.get("tasks", {}).get(task_id, {}).get("criteria", [])
        }
        criteria = []
        for criterion in task.get("spec_criteria", []):
            kept = prior.get(criterion)
            criteria.append(
                {
                    "criterion": criterion,
                    "passes": bool(kept["passes"]) if kept else False,
                    "evidence": kept.get("evidence") if kept else None,
                }
            )
        tasks[task_id] = {
            "spec": task.get("spec"),
            "commands": list(task.get("acceptance", [])),
            "criteria": criteria,
        }

    return {
        "version": 1,
        "note": (
            "Default-FAIL contract. Every criterion starts false and may only be set "
            "true via `python scripts/acceptance.py mark` with a real evidence file. "
            "taskctl re-runs the commands regardless of what this file claims."
        ),
        "tasks": tasks,
    }


def cmd_sync(_: argparse.Namespace) -> int:
    ledger = build_ledger()
    _write_json(LEDGER_PATH, ledger)
    total = sum(len(t["criteria"]) for t in ledger["tasks"].values())
    print(f"acceptance: synced {len(ledger['tasks'])} live tasks, {total} criteria")
    return 0


def run_commands(task_id: str, commands: list[str]) -> tuple[bool, list[Path]]:
    """Run every acceptance command, writing one evidence file per command."""
    outdir = ARTIFACTS / task_id
    outdir.mkdir(parents=True, exist_ok=True)
    evidence: list[Path] = []
    ok = True

    for index, command in enumerate(commands, 1):
        proc = subprocess.run(shlex.split(command), cwd=ROOT, text=True, capture_output=True)
        log = outdir / f"acceptance-{index}.log"
        log.write_text(
            f"$ {command}\nexit={proc.returncode}\n\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}",
            encoding="utf-8",
            newline="\n",
        )
        evidence.append(log)
        status = "PASS" if proc.returncode == 0 else f"FAIL(exit={proc.returncode})"
        print(f"  [{status}] {command}")
        if proc.returncode:
            ok = False
            for line in (proc.stdout + proc.stderr).strip().splitlines()[-6:]:
                print(f"      {line}")

    return ok, evidence


def cmd_run(args: argparse.Namespace) -> int:
    ledger = load_ledger()
    task = ledger.get("tasks", {}).get(args.task)
    if task is None:
        print(f"acceptance: {args.task} is not a live task in the ledger. Run `sync` first.")
        return 2
    if not task["commands"]:
        print(f"acceptance: {args.task} has no acceptance command; that is a FAILURE.")
        return 2

    print(f"acceptance run: {args.task}")
    ok, evidence = run_commands(args.task, task["commands"])
    print(f"evidence: {', '.join(str(p.relative_to(ROOT)) for p in evidence)}")
    print(f"acceptance: {args.task} commands {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def cmd_status(args: argparse.Namespace) -> int:
    ledger = load_ledger()
    tasks = ledger.get("tasks", {})
    selected = {args.task: tasks[args.task]} if args.task else tasks
    if args.task and args.task not in tasks:
        print(f"acceptance: unknown live task {args.task}")
        return 2

    for task_id, task in selected.items():
        done = sum(1 for c in task["criteria"] if c["passes"])
        print(f"{task_id}: {done}/{len(task['criteria'])} criteria met")
        for index, criterion in enumerate(task["criteria"]):
            mark = "x" if criterion["passes"] else " "
            print(f"  [{mark}] {index}. {criterion['criterion']}")
    return 0


def cmd_mark(args: argparse.Namespace) -> int:
    ledger = load_ledger()
    task = ledger.get("tasks", {}).get(args.task)
    if task is None:
        print(f"acceptance: unknown live task {args.task}")
        return 2
    if not 0 <= args.index < len(task["criteria"]):
        print(f"acceptance: criterion index out of range for {args.task}")
        return 2

    evidence = Path(args.evidence)
    if not evidence.is_absolute():
        evidence = ROOT / evidence
    if not evidence.is_file() or evidence.stat().st_size == 0:
        print(
            f"acceptance: refusing to mark a pass. Evidence file {args.evidence} is "
            f"missing or empty. Run `acceptance.py run {args.task}` first."
        )
        return 2

    # The evidence must belong to THIS task. Otherwise one task's passing log
    # could be replayed to certify a different, unfinished task.
    try:
        relative = evidence.resolve().relative_to((ARTIFACTS / args.task).resolve())
    except ValueError:
        print(
            f"acceptance: refusing to mark a pass. Evidence must live under "
            f".artifacts/{args.task}/ and be produced by "
            f"`acceptance.py run {args.task}`. Got: {args.evidence}"
        )
        return 2
    del relative

    # The evidence must record a PASSING run. `run` writes a log whether the
    # command passed or failed, so without this check the log of a FAILED run
    # is accepted as proof of a pass.
    recorded = evidence.read_text(encoding="utf-8", errors="replace")
    exits = re.findall(r"^exit=(-?\d+)$", recorded, flags=re.MULTILINE)
    if not exits:
        print(
            f"acceptance: refusing to mark a pass. {args.evidence} records no exit "
            f"code, so it is not output from `acceptance.py run`."
        )
        return 2
    if any(code != "0" for code in exits):
        print(
            f"acceptance: refusing to mark a pass. {args.evidence} records a FAILED "
            f"run (exit={', '.join(exits)}). Fix the work, re-run, then mark."
        )
        return 2

    entry = task["criteria"][args.index]
    entry["passes"] = True
    entry["evidence"] = str(evidence.relative_to(ROOT)).replace("\\", "/")
    _write_json(LEDGER_PATH, ledger)
    print(f"acceptance: {args.task}[{args.index}] marked PASS with evidence {entry['evidence']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("sync", help="regenerate the ledger from the work queue")

    run_p = sub.add_parser("run", help="run a task's acceptance commands")
    run_p.add_argument("task")

    status_p = sub.add_parser("status", help="print ledger state")
    status_p.add_argument("task", nargs="?")

    mark_p = sub.add_parser("mark", help="mark one criterion as met")
    mark_p.add_argument("task")
    mark_p.add_argument("index", type=int)
    mark_p.add_argument("--evidence", required=True, help="path to a real command-output file")

    args = parser.parse_args()
    return {
        "sync": cmd_sync,
        "run": cmd_run,
        "status": cmd_status,
        "mark": cmd_mark,
    }[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
