#!/usr/bin/env python3
"""PreToolUse guard for the default-FAIL acceptance ledger.

`docs/work/acceptance.json` records which acceptance criteria are met. It may
only change through `scripts/acceptance.py`, which requires a real evidence file
produced by an actual command run. Editing it directly would let an agent
declare its own work complete, which is precisely the failure this harness
exists to prevent.

Two deliberate differences from the reference implementation:

1. It also guards Bash. The reference gate matches only Write/Edit and says so
   in its own header: `sed -i`, `jq`, or a `python -c` one-liner rewrite the
   contract file unchecked. Matching Bash and inspecting the command text closes
   that hole.
2. Every failure path exits 2. Exit 1 is a NON-blocking error in Claude Code -
   the tool call proceeds - so an unparseable payload must never fall through to
   a bare non-zero exit.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

LEDGER_NAME = "acceptance.json"
LEDGER_REL = "docs/work/acceptance.json"
SANCTIONED = "acceptance.py"

EDIT_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}


def block(message: str) -> None:
    print(message, file=sys.stderr)
    sys.exit(2)


# Shell constructs that can write a file. Reading the ledger (cat, grep, git
# diff) stays allowed: blocking reads would push the agent to the Read tool for
# no safety gain while making ordinary inspection painful. The ledger's real
# protection is that `mark` demands evidence and `taskctl` re-runs the acceptance
# commands; this hook is defence in depth against casual rewriting.
MUTATORS = (
    ">",
    "sed -i",
    "tee ",
    "mv ",
    "cp ",
    "rm ",
    "truncate",
    "open(",
    "write_text",
    "json.dump",
    "dd ",
)


def mutates(command: str) -> bool:
    return any(token in command for token in MUTATORS)


def targets_ledger(path_text: str) -> bool:
    if not path_text:
        return False
    normalized = path_text.replace("\\", "/")
    return Path(normalized).name == LEDGER_NAME or normalized.endswith(LEDGER_REL)


def main() -> int:
    raw = sys.stdin.read()
    try:
        event = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        # Fail closed: we could not establish that this call is safe.
        block(
            "BLOCKED: the acceptance-ledger guard could not parse its hook payload, "
            "so it cannot confirm this call is safe. This guard fails closed."
        )
        return 2  # unreachable; keeps type checkers happy

    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input") or {}

    if tool in EDIT_TOOLS:
        path_text = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
        if targets_ledger(path_text):
            block(
                f"BLOCKED: {LEDGER_REL} may not be edited directly.\n"
                "It is a default-FAIL contract: a criterion may only be marked met via\n"
                "  python scripts/acceptance.py run <TASK>\n"
                "  python scripts/acceptance.py mark <TASK> <N> --evidence <log>\n"
                "which requires a non-empty evidence file from a real command run.\n"
                "Editing this file by hand would let you certify your own work."
            )

    elif tool == "Bash":
        command = str(tool_input.get("command") or "")
        if LEDGER_NAME in command and SANCTIONED not in command and mutates(command):
            block(
                f"BLOCKED: this command would modify {LEDGER_REL} without going through "
                f"scripts/{SANCTIONED}.\n"
                "Rewriting the acceptance ledger with a redirect, sed, or a Python "
                "one-liner bypasses the evidence requirement.\n"
                "Mark criteria with:\n"
                "  python scripts/acceptance.py mark <TASK> <N> --evidence <log>\n"
                f"Command was: {command}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
