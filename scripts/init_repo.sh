#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -d .git ]]; then
  echo "git repository already initialized"
  exit 0
fi

git init -b main
if ! git config user.email >/dev/null || ! git config user.name >/dev/null; then
  echo "HUMAN ACTION REQUIRED: configure git user.name and user.email, then rerun scripts/init_repo.sh" >&2
  exit 2
fi

git add -A
git commit -m "chore: initialize KidneyMatch agentic starter"
echo "git baseline created"
