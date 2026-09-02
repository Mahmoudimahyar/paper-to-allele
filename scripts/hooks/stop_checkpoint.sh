#!/usr/bin/env bash
# Stop -> commit a work-in-progress checkpoint.
#
# Without this, a context reset or crash mid-task loses everything since the last
# manual commit. Git history is one third of this repository's declared
# cross-agent memory system (see AGENTS.md), so checkpoints are memory, not just
# safety.
#
# This hook MUST NOT block. A Stop hook that exits 2 prevents Claude from
# stopping, and Claude Code hard-overrides after 8 consecutive blocks, which
# silently converts the gate into a no-op. Every path here exits 0.
#
# `git add -A` rather than `git commit -am`: the reference implementation commits
# tracked files only, so a brand-new test or source file is silently NOT saved by
# the very backstop meant to save it.
set -u

# shellcheck source=scripts/hooks/_paths.sh
. "$(dirname "${BASH_SOURCE[0]}")/_paths.sh"

ROOT="$(km_to_unix "${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}")"
if ! cd "$ROOT" 2>/dev/null; then
  # Report rather than exiting silently: a checkpoint that never happens is a
  # silent loss of the git history this repo treats as cross-agent memory.
  echo "stop_checkpoint: cannot cd to '$ROOT'; NOTHING was checkpointed." >&2
  exit 0
fi

command -v git >/dev/null 2>&1 || exit 0
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

# Never interfere with an in-progress merge, rebase, bisect or cherry-pick.
gitdir="$(git rev-parse --git-dir 2>/dev/null)" || exit 0
for state in MERGE_HEAD REBASE_HEAD CHERRY_PICK_HEAD BISECT_LOG rebase-merge rebase-apply; do
  if [ -e "$gitdir/$state" ]; then
    echo "stop_checkpoint: skipped, repository is mid-$state" >&2
    exit 0
  fi
done

# A commit on a detached HEAD is unreferenced and git will eventually collect
# it, so the "checkpoint" would silently preserve nothing.
if ! branch="$(git symbolic-ref --quiet --short HEAD 2>/dev/null)"; then
  echo "stop_checkpoint: HEAD is detached; NOTHING was checkpointed." >&2
  echo "Create a branch (git switch -c <name>) to enable checkpoints." >&2
  exit 0
fi

git diff --quiet && git diff --cached --quiet && [ -z "$(git status --porcelain)" ] && exit 0

git add -A >/dev/null 2>&1 || exit 0

stamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || echo unknown)"

# Unlike the reference hook, failures are reported rather than swallowed. A
# missing git identity or a rejecting pre-commit hook would otherwise make this
# backstop preserve nothing while appearing to work.
if ! out="$(git commit -q -m "chore(wip): checkpoint on ${branch} at ${stamp}" 2>&1)"; then
  {
    echo "stop_checkpoint: COMMIT FAILED - your work is NOT checkpointed."
    printf '%s\n' "$out"
  } >&2
  # Leaving everything staged after a failed commit silently changes the
  # working state the next session inherits. Put the index back.
  git reset --quiet >/dev/null 2>&1 || true
fi

exit 0
