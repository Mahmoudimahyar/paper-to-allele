set shell := ["bash", "-cu"]

doctor:
    python scripts/doctor.py

context task="HIST-001":
    python scripts/context_pack.py --task {{task}}

lint:
    python scripts/docs_lint.py
    python scripts/spec_lint.py
    python scripts/architecture_lint.py
    ruff check .

unit:
    pytest tests/unit tests/contracts

verify:
    python scripts/verify_repo.py

handoff agent task summary next="":
    python scripts/handoff.py --agent {{agent}} --task {{task}} --summary {{summary}} --next {{next}}

sync-agent-skills:
    python scripts/sync_agent_skills.py
