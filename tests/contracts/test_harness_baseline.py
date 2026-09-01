"""Contract tests for the verification harness itself.

Each test here corresponds to a defect found in the P0 readiness review
(`docs/agent-harness/HARNESS_READINESS_REVIEW_2026-09-01.md`). They exist so the
harness cannot silently regress into a state where an agent believes it has
verified work that was never actually checked.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

LINE_CONTINUATION = "\\\n"


def _python_sources() -> list[Path]:
    return [
        path
        for path in ROOT.rglob("*.py")
        if "__pycache__" not in path.parts and ".venv" not in path.parts
    ]


def test_no_source_file_starts_with_a_line_continuation() -> None:
    """P0-3: the starter shipped 10 files beginning with a stray backslash line.

    It parsed by accident, but broke the shebang and shifted every ruff/mypy line
    number by one, which corrupts the file:line pointers agents rely on.
    """
    offenders = [
        str(path.relative_to(ROOT))
        for path in _python_sources()
        if path.read_text(encoding="utf-8").startswith(LINE_CONTINUATION)
    ]
    assert offenders == [], f"files begin with a stray line-continuation: {offenders}"


def test_lockfile_exists() -> None:
    """P0-5: AGENTS.md forbids adding a dependency without updating the lockfile.

    That rule is unenforceable without a lockfile, and OCR/HLA benchmarks are not
    comparable across sessions unless the dependency set is pinned.
    """
    assert (ROOT / "uv.lock").is_file(), "uv.lock is missing; run `uv sync --extra dev`"


def test_repository_normalizes_line_endings() -> None:
    """CRLF churn breaks sync_agent_skills.py --check, which is a byte-exact filecmp."""
    gitattributes = ROOT / ".gitattributes"
    assert gitattributes.is_file(), ".gitattributes is missing"
    assert "text=auto eol=lf" in gitattributes.read_text(encoding="utf-8")


def test_verification_never_skips_a_step_when_a_tool_is_absent() -> None:
    """P0-2: the original verify_repo.py appended ruff/pytest only when
    `shutil.which` found them, so a machine without those tools printed
    `verify_repo: PASS` having run neither. "Verified" must never mean "skipped".
    """
    source = (ROOT / "scripts/verify_repo.py").read_text(encoding="utf-8")
    assert "return 127" in source, "missing-tool path must fail, not skip"
    assert "none skipped" in source, "PASS message must assert full coverage"


def test_ci_delegates_to_the_same_gate_developers_run() -> None:
    """CI maintaining its own copy of the step list lets local-green mean CI-red."""
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "scripts/verify_repo.py" in ci
    assert "uv sync --frozen" in ci, "CI must not silently re-resolve dependencies"


def test_pre_commit_ruff_matches_the_locked_ruff() -> None:
    """A pre-commit ruff older than the locked ruff reformats differently, so the
    hook and CI fight each other and the working tree never settles.
    """
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    locked = next(p["version"] for p in lock["package"] if p["name"] == "ruff")
    pre_commit = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert f"rev: v{locked}" in pre_commit, (
        f"pre-commit ruff rev does not match locked ruff {locked}"
    )
