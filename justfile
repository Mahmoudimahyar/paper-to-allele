set shell := ["bash", "-cu"]

# Every recipe runs through the locked environment so local results match CI.
# `--frozen` fails loudly on a stale uv.lock instead of silently re-resolving.
uv := "uv run --frozen"

doctor:
    {{uv}} python scripts/doctor.py

context task="HIST-001":
    {{uv}} python scripts/context_pack.py --task {{task}}

lint:
    {{uv}} python scripts/docs_lint.py
    {{uv}} python scripts/spec_lint.py
    {{uv}} python scripts/architecture_lint.py
    {{uv}} ruff check .
    {{uv}} ruff format --check .

types:
    {{uv}} mypy src

unit:
    {{uv}} pytest tests/unit tests/contracts

# Full gate. Identical to what CI runs.
verify:
    {{uv}} python scripts/verify_repo.py

handoff agent task summary next="":
    {{uv}} python scripts/handoff.py --agent {{agent}} --task {{task}} --summary {{summary}} --next {{next}}

sync-agent-skills:
    {{uv}} python scripts/sync_agent_skills.py
