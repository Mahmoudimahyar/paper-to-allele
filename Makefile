.PHONY: doctor context verify lint test
TASK ?= HIST-001

doctor:
	python scripts/doctor.py

context:
	python scripts/context_pack.py --task $(TASK)

lint:
	python scripts/docs_lint.py && python scripts/spec_lint.py && python scripts/architecture_lint.py

test:
	pytest

verify:
	python scripts/verify_repo.py
