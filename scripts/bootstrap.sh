#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v uv >/dev/null 2>&1; then
  echo "HUMAN ACTION REQUIRED: install uv, then rerun scripts/bootstrap.sh" >&2
  exit 2
fi

PY_MINOR="$(uv run --python 3.12 python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
if [[ "$PY_MINOR" != "3.12" ]]; then
  echo "HUMAN ACTION REQUIRED: make Python 3.12 available to uv." >&2
  exit 2
fi

uv sync --python 3.12 --extra hist --extra hla --extra image --extra ocr
uv run python scripts/sync_agent_skills.py --check
uv run python scripts/docs_lint.py
uv run python scripts/spec_lint.py
uv run python scripts/architecture_lint.py
uv run pytest -q

echo "bootstrap: PASS"
