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
import re
import sys
from pathlib import Path

LEDGER_NAME = "acceptance.json"
LEDGER_REL = "docs/work/acceptance.json"
SANCTIONED = "acceptance.py"

EDIT_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}
# PowerShell takes a `command` just like Bash. Omitting it left an open
# bypass of this guard, which was used inadvertently during development.
SHELL_TOOLS = {"Bash", "PowerShell"}


def block(message: str) -> None:
    print(message, file=sys.stderr)
    sys.exit(2)


# Deciding whether a Bash command WRITES the ledger, as opposed to merely
# mentioning it. Two failures found by adversarial audit drove this design:
#
#   * A bare `"acceptance.py" in segment` exemption meant appending
#     `# per acceptance.py` to ANY command disabled the guard completely.
#   * A bare `">" in segment` test blocked `cat ledger > backup`, where the
#     ledger is the SOURCE. Redirect direction must be read, not guessed.

COMMENT = re.compile(r"#[^\n]*")

# The exemption requires an actual invocation of the script by path, which a
# comment cannot satisfy once comments have been stripped.
SANCTIONED_CALL = re.compile(r"\bscripts[/\\]acceptance\.py\b")

# open(...) alone is not a write: reading the ledger uses open() too.
WRITE_OPEN = re.compile(r"""open\s*\([^)]*['"][wax]\+?b?['"]""")

REDIRECT_TARGET = re.compile(r">>?\s*([^\s;|&<>]+)")
INPLACE = re.compile(r"\b(?:sed\s+-i|truncate|tee|dd|patch)\b")
PY_WRITE = re.compile(r"\b(?:json\.dump|write_text|write_bytes|shutil\.copy\w*|os\.replace)\b")
GIT_REWRITE = re.compile(r"\bgit\s+(?:checkout|restore)\b")
COPY_CMD = re.compile(r"^\s*(?:cp|mv|install|rsync)\b(.*)$")

SEGMENT = re.compile(r"[\n;]|&&|\|\||\|")


def _writes_ledger(segment: str) -> bool:
    """True when this segment would modify the ledger, not merely read it."""
    # Redirection writes only the target that follows > or >>.
    for match in REDIRECT_TARGET.finditer(segment):
        if LEDGER_NAME in match.group(1):
            return True

    # In-place editors rewrite whatever file they are handed.
    if INPLACE.search(segment):
        return True

    # cp/mv/install/rsync write their LAST positional argument.
    copy = COPY_CMD.match(segment)
    if copy:
        positional = [a for a in copy.group(1).split() if not a.startswith("-")]
        if positional and LEDGER_NAME in positional[-1]:
            return True

    # git checkout/restore overwrite the working-tree copy.
    if GIT_REWRITE.search(segment):
        return True

    return bool(WRITE_OPEN.search(segment) or PY_WRITE.search(segment))


def mutates_ledger(command: str) -> bool:
    """True only if a segment referencing the ledger would also write to it."""
    for segment in SEGMENT.split(COMMENT.sub("", command)):
        if LEDGER_NAME not in segment:
            continue
        if SANCTIONED_CALL.search(segment):
            continue
        if _writes_ledger(segment):
            return True
    return False


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

    # json.loads("null") / "42" / "[]" all succeed but are not objects; calling
    # .get() on them raises, and an uncaught exception exits 1 -- which does NOT
    # block. Verified: every non-object payload previously failed OPEN.
    if not isinstance(event, dict):
        block(
            "BLOCKED: the acceptance-ledger guard received a non-object hook payload, "
            "so it cannot confirm this call is safe. This guard fails closed."
        )

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

    elif tool in SHELL_TOOLS:
        command = str(tool_input.get("command") or "")
        if mutates_ledger(command):
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
