.PHONY: doctor context lint types unit verify
TASK ?= HIST-001

# Mirrors the justfile. Every target runs through the locked environment so that
# local results match CI; --frozen fails on a stale uv.lock rather than resolving.
UV = uv run --frozen

doctor:
	$(UV) python scripts/doctor.py

context:
	$(UV) python scripts/context_pack.py --task $(TASK)

lint:
	$(UV) python scripts/docs_lint.py
	$(UV) python scripts/spec_lint.py
	$(UV) python scripts/architecture_lint.py
	$(UV) ruff check .
	$(UV) ruff format --check .

types:
	$(UV) mypy src

unit:
	$(UV) pytest tests/unit tests/contracts

verify:
	$(UV) python scripts/verify_repo.py
