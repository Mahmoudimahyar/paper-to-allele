"""Tests for the default-FAIL acceptance ledger's evidence rules.

Found by adversarial audit of the P1 harness: `mark` originally accepted any
non-empty file as proof, so the log of a FAILED run - or another task's passing
log - could certify a criterion.

These run against a temp ledger, never the repository's own.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import pytest

# Acceptance for BOOT-001 selects on this marker: pytest --task BOOT-001
pytestmark = pytest.mark.task("BOOT-001")

ROOT = Path(__file__).resolve().parents[2]


def load_module():
    spec = importlib.util.spec_from_file_location("km_acceptance", ROOT / "scripts/acceptance.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def sandbox(tmp_path: Path):
    """An acceptance module rooted in a throwaway directory."""
    module = load_module()
    module.ROOT = tmp_path
    module.LEDGER_PATH = tmp_path / "acceptance.json"
    module.ARTIFACTS = tmp_path / ".artifacts"
    ledger = {
        "version": 1,
        "tasks": {
            "T-1": {
                "spec": "specs/features/x.json",
                "commands": ["true"],
                "criteria": [{"criterion": "does the thing", "passes": False, "evidence": None}],
            }
        },
    }
    module.LEDGER_PATH.write_text(json.dumps(ledger), encoding="utf-8")
    return module


def write_log(module, task: str, exit_code: int) -> Path:
    d = module.ARTIFACTS / task
    d.mkdir(parents=True, exist_ok=True)
    log = d / "acceptance-1.log"
    log.write_text(f"$ true\nexit={exit_code}\n\n--- stdout ---\nok\n", encoding="utf-8")
    return log


def mark(module, task: str, index: int, evidence: Path) -> int:
    return module.cmd_mark(argparse.Namespace(task=task, index=index, evidence=str(evidence)))


def passes(module) -> bool:
    data = json.loads(module.LEDGER_PATH.read_text(encoding="utf-8"))
    return data["tasks"]["T-1"]["criteria"][0]["passes"]


def test_evidence_from_a_failed_run_is_refused(sandbox) -> None:
    log = write_log(sandbox, "T-1", exit_code=4)
    assert mark(sandbox, "T-1", 0, log) == 2
    assert passes(sandbox) is False


def test_evidence_from_another_task_is_refused(sandbox) -> None:
    other = write_log(sandbox, "T-2", exit_code=0)
    assert mark(sandbox, "T-1", 0, other) == 2
    assert passes(sandbox) is False


def test_a_file_with_no_recorded_exit_code_is_refused(sandbox) -> None:
    d = sandbox.ARTIFACTS / "T-1"
    d.mkdir(parents=True, exist_ok=True)
    bogus = d / "acceptance-1.log"
    bogus.write_text("looks like evidence but records nothing", encoding="utf-8")
    assert mark(sandbox, "T-1", 0, bogus) == 2
    assert passes(sandbox) is False


def test_an_empty_file_is_refused(sandbox) -> None:
    d = sandbox.ARTIFACTS / "T-1"
    d.mkdir(parents=True, exist_ok=True)
    empty = d / "acceptance-1.log"
    empty.write_text("", encoding="utf-8")
    assert mark(sandbox, "T-1", 0, empty) == 2
    assert passes(sandbox) is False


def test_evidence_from_a_passing_run_is_accepted(sandbox) -> None:
    """The gate must be able to OPEN; one that never opens is equally broken."""
    log = write_log(sandbox, "T-1", exit_code=0)
    assert mark(sandbox, "T-1", 0, log) == 0
    assert passes(sandbox) is True


def test_force_records_the_override_in_the_queue(tmp_path: Path) -> None:
    """A bypass that leaves no trace is indistinguishable from a passing gate.

    Audit finding: --force required a reason but only printed it, so the
    override vanished with the session.
    """
    import subprocess
    import sys

    queue = {
        "version": 2,
        "active_task": "T-1",
        "status_values": ["COMPLETE", "ACTIVE", "READY", "BACKLOG", "BLOCKED"],
        "tasks": [{"id": "T-1", "status": "READY", "title": "t", "phase": "P"}],
    }
    work = tmp_path / "docs" / "work"
    work.mkdir(parents=True)
    (work / "WORK_QUEUE.json").write_text(json.dumps(queue), encoding="utf-8")

    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for name in ("taskctl.py", "acceptance.py"):
        (scripts / name).write_bytes((ROOT / "scripts" / name).read_bytes())

    proc = subprocess.run(
        [
            sys.executable,
            str(scripts / "taskctl.py"),
            "set",
            "T-1",
            "COMPLETE",
            "--force",
            "--reason",
            "human override for a cancelled task",
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    written = json.loads((work / "WORK_QUEUE.json").read_text(encoding="utf-8"))
    task = written["tasks"][0]
    assert task["status"] == "COMPLETE"
    assert task["forced_complete"]["reason"] == "human override for a cancelled task"
    assert "WARNING" in proc.stdout


def test_force_without_a_reason_is_refused(tmp_path: Path) -> None:
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/taskctl.py"), "set", "T-1", "COMPLETE", "--force"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.returncode != 0
    assert "requires --reason" in (proc.stdout + proc.stderr)
