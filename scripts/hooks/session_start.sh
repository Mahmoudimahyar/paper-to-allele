#!/usr/bin/env bash
# SessionStart -> print orientation.
#
# On exit 0, SessionStart stdout is added to context as something Claude can see,
# so this replaces the first few steps of the session protocol with zero
# reasoning tokens and zero tool calls.
#
# Keep the output SHORT. It is prepended to every session and competes with the
# task for context (docs/agent-harness/TOKEN_EFFICIENCY.md).
set -u

ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$ROOT" || exit 0

if [ -f "$ROOT/AGENT_STOP" ]; then
  echo "!! AGENT_STOP is present. Every tool call is blocked until a human removes it."
  echo "   Report this to the user instead of attempting work."
  exit 0
fi

if command -v python3 >/dev/null 2>&1; then PY=python3
elif command -v python >/dev/null 2>&1; then PY=python
else
  echo "No python on PATH; run scripts/doctor.py once Python is available."
  exit 0
fi

echo "KidneyMatch session orientation"
echo "-- active/next task --"
"$PY" scripts/taskctl.py next 2>/dev/null || echo "(taskctl unavailable)"
echo "-- acceptance ledger (default-FAIL; criteria start unmet) --"
"$PY" scripts/acceptance.py status 2>/dev/null | head -20 || echo "(ledger unavailable)"
echo "-- environment --"
"$PY" scripts/doctor.py --brief 2>/dev/null || echo "(doctor unavailable)"
echo "-- reminders --"
echo "Gate: python scripts/verify_repo.py . Acceptance: scripts/acceptance.py run <TASK>."
echo "COMPLETE is gated on evidence; the ledger cannot be edited by hand."

exit 0
