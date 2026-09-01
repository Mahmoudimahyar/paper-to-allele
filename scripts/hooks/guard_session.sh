#!/usr/bin/env bash
# PreToolUse, all tools. Operator control channel: kill switch, then steering.
#
# Kill switch and steering live in ONE script deliberately. The reference
# implementation puts them in two hooks in the same matcher group, which emits
# two block decisions for a single tool call with undefined merge semantics, and
# lets the steer hook consume STEER.md even when the kill switch is what the
# agent actually sees.
#
# Blocking uses `exit 2` with a message on stderr rather than JSON on stdout.
# Per the hooks documentation, exit 2 blocks a PreToolUse call unconditionally
# and stderr becomes the blocking message, whereas JSON that fails schema
# validation is a NON-blocking error: the tool call proceeds. A guard must fail
# closed, so we never depend on emitting parseable JSON.
set -u

# shellcheck source=scripts/hooks/_paths.sh
. "$(dirname "${BASH_SOURCE[0]}")/_paths.sh"

ROOT="$(km_to_unix "${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}")"
STOP_FILE="$(km_to_unix "${KM_AGENT_STOP_FILE:-$ROOT/AGENT_STOP}")"
STEER_FILE="$(km_to_unix "${KM_STEER_FILE:-$ROOT/STEER.md}")"

# 1. Kill switch. Presence alone halts every tool call; contents are optional.
if [ -f "$STOP_FILE" ]; then
  {
    echo "HALTED: AGENT_STOP is present ($STOP_FILE)."
    if [ -s "$STOP_FILE" ]; then
      echo "Operator note:"
      cat "$STOP_FILE"
    fi
    echo
    echo "Every tool call is blocked until a human removes this file."
    echo "Do NOT delete it yourself and do not try to work around it."
    echo "Stop what you are doing and report your current status to the user."
  } >&2
  exit 2
fi

# 2. Steering. Delivered exactly once, then the file is truncated.
#    -s (non-empty) not -f: `touch STEER.md` must not deliver an empty message.
if [ -s "$STEER_FILE" ]; then
  note="$(cat "$STEER_FILE")"
  : >"$STEER_FILE"
  {
    echo "OPERATOR STEERING (delivered once; the file has now been cleared):"
    echo
    echo "$note"
    echo
    echo "This tool call was blocked only to surface the message. Incorporate the"
    echo "guidance, then continue. Re-issue the call if it is still the right one."
  } >&2
  exit 2
fi

exit 0
