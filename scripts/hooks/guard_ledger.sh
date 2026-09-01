#!/usr/bin/env bash
# PreToolUse (Edit|Write|Bash) -> protect the default-FAIL acceptance ledger.
#
# Thin wrapper whose only job is to find a Python interpreter and FAIL CLOSED if
# there is none. The reference implementation hardcodes `python3`; on Windows
# that frequently does not exist even when `python` does, and its hook then
# silently no-ops, so the gate it advertises is simply absent. A guard that
# disappears when a dependency is missing is worse than no guard, because the
# repository documents a protection that is not there.
set -u

# shellcheck source=scripts/hooks/_paths.sh
. "$(dirname "${BASH_SOURCE[0]}")/_paths.sh"

ROOT="$(km_to_unix "${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}")"

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "BLOCKED: no python3/python on PATH, so the acceptance-ledger guard cannot run." >&2
  echo "This guard fails closed by design. Install Python or fix PATH." >&2
  exit 2
fi

GUARD_UNIX="$ROOT/scripts/hooks/guard_ledger.py"

# Existence is tested with the bash-visible path; the interpreter is handed the
# native one, because on Windows `python` cannot open /c/... paths.
if [ ! -f "$GUARD_UNIX" ]; then
  echo "BLOCKED: acceptance-ledger guard not found at $GUARD_UNIX. Failing closed." >&2
  exit 2
fi

exec "$PY" "$(km_to_native "$GUARD_UNIX")"
