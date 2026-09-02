#!/usr/bin/env python3
"""Layered verification.

Two properties this script must guarantee, because agents treat its exit code as
proof of completion:

1. **No silent skips.** Every step is mandatory. A missing tool is a FAILURE, not
   a skip. A previous version skipped ruff/pytest when they were absent from PATH
   and still printed PASS, which let "verification passed" mean "nothing ran".
2. **Identical to CI.** The step list mirrors `.github/workflows/ci.yml` exactly,
   so a green local run cannot be followed by a red CI run.

Console output stays one line per step; full output of a failing step is written
to `.artifacts/verify/` (see docs/agent-harness/TOKEN_EFFICIENCY.md).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / ".artifacts" / "verify"

# Run through `uv run --frozen` when the locked environment is available so that
# the interpreter and every tool version match CI regardless of which Python
# invoked this script. Falls back to the current interpreter otherwise.
USE_UV = bool(shutil.which("uv")) and (ROOT / "uv.lock").is_file()

# The active phase (MVP-HIST) needs the historical-ingestion parser deps.
# CI, bootstrap and this script must agree; tests/contracts enforces that.
EXTRA = "hist"
PREFIX = ["uv", "run", "--frozen", "--extra", EXTRA] if USE_UV else []


def step(*args: str) -> list[str]:
    """Build one verification command, routed through uv when available."""
    if args[0] == "python":
        return [*PREFIX, "python", *args[1:]] if USE_UV else [sys.executable, *args[1:]]
    return [*PREFIX, *args]


STEPS = [
    step("python", "scripts/sync_agent_skills.py", "--check"),
    step("python", "scripts/docs_lint.py"),
    step("python", "scripts/spec_lint.py"),
    step("python", "scripts/architecture_lint.py"),
    step("python", "scripts/invariant_lint.py"),
    step("python", "scripts/scan_pii.py"),
    step("ruff", "check", "."),
    step("ruff", "format", "--check", "."),
    step("mypy", "src"),
    step("bandit", "-c", "pyproject.toml", "-r", "src", "-ll", "-ii", "-q"),
    step("pytest", "-q", "--cov", "--cov-report=term-missing"),
    # The medical-logic modules are held to 100% separately from the repo-wide
    # ratchet: a global average lets a safety-critical branch go untested while
    # scaffolding coverage carries the number.
    step(
        "coverage",
        "report",
        "--include=*/kidneymatch/hla/*,*/kidneymatch/domain/*,*/kidneymatch/ingestion/media.py",
        "--fail-under=100",
    ),
]


def missing_tool(cmd: list[str]) -> str | None:
    """Return the tool name when it cannot be executed at all."""
    return None if shutil.which(cmd[0]) else cmd[0]


def main() -> int:
    if not USE_UV:
        print(
            "WARNING: running without `uv run --frozen`; tool versions may differ from CI. "
            "Install uv and run `uv sync` for a CI-identical result."
        )
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    for cmd in STEPS:
        label = " ".join(cmd)
        tool = missing_tool(cmd)
        if tool is not None:
            print(f"FAIL: {label}")
            print(f"  '{tool}' is not installed. Run `uv sync`.")
            print("verify_repo: FAIL (a required tool is missing; nothing was skipped)")
            return 127

        proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
        if proc.returncode:
            log = ARTIFACTS / f"{cmd[-1].strip('.-/').replace('/', '_') or 'step'}.log"
            log.write_text(
                f"$ {label}\n\n--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}",
                encoding="utf-8",
            )
            print(f"FAIL: {label}")
            tail = (proc.stdout + proc.stderr).strip().splitlines()[-20:]
            print("\n".join(tail))
            print(f"\nfull output: {log.relative_to(ROOT)}")
            print("verify_repo: FAIL")
            return proc.returncode
        print(f"OK: {label}")

    print(f"verify_repo: PASS ({len(STEPS)} steps, none skipped)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
