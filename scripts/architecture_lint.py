\
#!/usr/bin/env python3
"""Small structural guardrails that should work for both Codex and Claude Code."""
from __future__ import annotations
from pathlib import Path
import ast
import sys

ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []

# Matching must never import compensation.
matching = ROOT / "src/kidneymatch/matching"
for path in matching.rglob("*.py"):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [x.name for x in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        for name in names:
            if "compensation" in name:
                errors.append(f"{path}: matching module imports compensation: {name}")

# Source tree may not contain hard-coded known secret variable assignments.
secret_names = {"TELEGRAM_BOT_TOKEN", "IDENTITY_PROVIDER_API_KEY", "DJANGO_SECRET_KEY"}
for path in (ROOT / "src").rglob("*.py"):
    text = path.read_text(encoding="utf-8")
    for name in secret_names:
        if f'{name} = "' in text or f"{name} = '" in text:
            errors.append(f"{path}: possible hard-coded secret {name}")

if errors:
    print("architecture_lint: FAIL")
    for error in errors:
        print(" -", error)
    sys.exit(1)
print("architecture_lint: OK")
