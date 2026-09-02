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
    {{uv}} python scripts/invariant_lint.py
    {{uv}} ruff check .
    {{uv}} ruff format --check .

types:
    {{uv}} mypy src

unit:
    {{uv}} pytest tests/unit tests/contracts

# Security and privacy checks that do not need a network.
security:
    {{uv}} python scripts/scan_pii.py
    {{uv}} bandit -c pyproject.toml -r src -ll -ii

# Dependency vulnerabilities. Reads uv.lock directly, no export step.
audit:
    osv-scanner scan -L uv.lock

# Full gate. Identical to what CI runs.
verify:
    {{uv}} python scripts/verify_repo.py

# Acceptance for one task, writing evidence to .artifacts/<TASK>/.
accept task:
    {{uv}} python scripts/acceptance.py run {{task}}

# Mutation testing. LINUX/WSL ONLY - mutmut calls os.fork(), which does not
# exist on Windows. CI runs this on ubuntu.
verify-mutation min_score="80":
    {{uv}} mutmut run
    {{uv}} mutmut export-cicd-stats
    {{uv}} python scripts/mutation_gate.py --min-score {{min_score}}

handoff agent task summary next="":
    {{uv}} python scripts/handoff.py --agent {{agent}} --task {{task}} --summary {{summary}} --next {{next}}

sync-agent-skills:
    {{uv}} python scripts/sync_agent_skills.py
