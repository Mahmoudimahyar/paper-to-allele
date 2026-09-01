#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []
index = json.loads((ROOT / "docs/index.json").read_text(encoding="utf-8"))
for topic, paths in index["topics"].items():
    for path in paths:
        if not (ROOT / path).exists():
            errors.append(f"docs/index.json topic {topic}: missing {path}")

current = (ROOT / "docs/agent-memory/CURRENT.md").read_text(encoding="utf-8")
if len(current.splitlines()) > 120:
    errors.append("CURRENT.md exceeds 120-line cross-agent memory budget")

agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
if len(agents.splitlines()) > 110:
    errors.append("AGENTS.md exceeds 110-line startup budget")

if errors:
    print("docs_lint: FAIL")
    for error in errors:
        print(" -", error)
    sys.exit(1)
print("docs_lint: OK")
