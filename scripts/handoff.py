#!/usr/bin/env python3
"""Create a durable cross-agent handoff without storing secrets."""

from __future__ import annotations

import argparse
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

parser = argparse.ArgumentParser()
parser.add_argument("--agent", required=True, choices=["codex", "claude", "human", "other"])
parser.add_argument("--task", required=True)
parser.add_argument("--summary", required=True)
parser.add_argument("--next", default="")
parser.add_argument("--verification", default="python scripts/verify_repo.py")
args = parser.parse_args()

now = datetime.now(UTC)
ts = now.strftime("%Y%m%dT%H%M%SZ")
try:
    commit = (
        subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True, capture_output=True
        ).stdout.strip()
        or "NO_GIT_COMMIT"
    )
except Exception:
    commit = "NO_GIT_COMMIT"

content = f"""# Handoff — {args.task}

- **UTC:** {now.isoformat()}
- **Agent:** {args.agent}
- **Commit/checkpoint:** {commit}
- **Verification command:** `{args.verification}`

## Completed
{args.summary}

## Next
{args.next or "See active execution plan."}

## Known failures/blockers
None declared by handoff script. Add specific failures here if any verification did not pass.

## Human actions
See `docs/agent-memory/HUMAN_ACTIONS.md`. Never put secret values here.
"""
path = ROOT / "docs/agent-memory/handoffs" / f"{ts}-{args.agent}-{args.task}.md"
path.write_text(content, encoding="utf-8")
print(path.relative_to(ROOT))
