#!/usr/bin/env bash
# PostToolUse (Edit|Write) -> lint and format the file that was just touched.
#
# Catches breakage seconds after it is introduced rather than at end of session,
# when the agent has lost the context that produced it.
#
# The tool has ALREADY run by the time PostToolUse fires, so exit 2 here does not
# undo anything; per the hooks documentation it surfaces stderr to Claude. That
# is exactly what we want: a remaining lint error becomes immediate feedback.
set -u

ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

payload="$(cat)"
file="$(printf '%s' "$payload" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"

# Only Python files, and only inside the project.
case "$file" in
*.py) ;;
*) exit 0 ;;
esac
[ -f "$file" ] || exit 0

command -v uv >/dev/null 2>&1 || exit 0

cd "$ROOT" || exit 0
uv run --frozen ruff check --fix "$file" >/dev/null 2>&1
uv run --frozen ruff format "$file" >/dev/null 2>&1

# Re-check: report only what autofix could not resolve.
remaining="$(uv run --frozen ruff check "$file" --output-format concise 2>&1)"
if [ -n "$remaining" ] && ! printf '%s' "$remaining" | grep -q "All checks passed"; then
  {
    echo "ruff still reports problems in $file after autofix:"
    printf '%s\n' "$remaining"
  } >&2
  exit 2
fi

exit 0
