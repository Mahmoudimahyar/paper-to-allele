\
#!/usr/bin/env python3
"""Layered verification with concise output; full subprocess output is emitted only on failure."""
from __future__ import annotations
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

steps = [
    [sys.executable, "scripts/sync_agent_skills.py", "--check"],
    [sys.executable, "scripts/docs_lint.py"],
    [sys.executable, "scripts/spec_lint.py"],
    [sys.executable, "scripts/architecture_lint.py"],
]
if shutil.which("ruff"):
    steps.append(["ruff", "check", "."])
if shutil.which("pytest"):
    steps.append(["pytest", "-q"])

for cmd in steps:
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    label = " ".join(cmd)
    if proc.returncode:
        print(f"FAIL: {label}")
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    print(f"OK: {label}")
print("verify_repo: PASS")
