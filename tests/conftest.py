"""Pytest configuration for task-scoped acceptance runs.

Every READY/ACTIVE task in `docs/work/WORK_QUEUE.json` must carry an acceptance
command that returns 0 or non-zero (P1-4 of the harness readiness review). Prose
acceptance cannot end an autonomous loop.

Rather than hardcoding test file paths into the work queue -- which would break
the moment an implementer chooses a different layout -- acceptance selects tests
by marker:

    @pytest.mark.task("HIST-002")
    def test_joined_submission_bundles_once(): ...

    $ uv run --frozen pytest --task HIST-002 -q

A task with no tagged tests exits NON-ZERO. That is deliberate: "this task has
no tests" must never be indistinguishable from "this task passes".
"""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--task",
        action="store",
        default=None,
        metavar="TASK_ID",
        help="Run only tests marked @pytest.mark.task('<TASK_ID>'). "
        "Exits non-zero if no test carries that marker.",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "task(task_id): the WORK_QUEUE.json task whose acceptance this test proves.",
    )
    config.addinivalue_line(
        "markers",
        "invariant(spec_id, text): the feature-spec invariant this test enforces.",
    )


def _task_ids(item: pytest.Item) -> set[str]:
    return {str(arg) for marker in item.iter_markers(name="task") for arg in marker.args}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    task_id = config.getoption("--task")
    if not task_id:
        return

    selected = [item for item in items if task_id in _task_ids(item)]
    deselected = [item for item in items if item not in selected]

    if not selected:
        # pytest's own "no tests ran" exit code is 5, but an explicit UsageError
        # makes the reason legible to an agent reading only the last line.
        raise pytest.UsageError(
            f"No test is marked @pytest.mark.task({task_id!r}). "
            f"Acceptance for {task_id} cannot pass until at least one test claims it. "
            f"This is a FAILURE, not an empty pass."
        )

    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected
