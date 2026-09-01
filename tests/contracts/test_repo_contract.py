from pathlib import Path

import pytest

# Acceptance for BOOT-001 selects on this marker: pytest --task BOOT-001
pytestmark = pytest.mark.task("BOOT-001")

ROOT = Path(__file__).resolve().parents[2]


def test_cross_agent_instruction_files_exist() -> None:
    assert (ROOT / "AGENTS.md").is_file()
    assert (ROOT / "CLAUDE.md").read_text(encoding="utf-8").startswith("@AGENTS.md")


def test_canonical_memory_files_exist() -> None:
    for name in ("CURRENT.md", "KNOWN_ISSUES.md", "HUMAN_ACTIONS.md"):
        assert (ROOT / "docs/agent-memory" / name).is_file()


def test_matching_source_does_not_reference_compensation() -> None:
    source = "\n".join(
        p.read_text(encoding="utf-8") for p in (ROOT / "src/kidneymatch/matching").glob("*.py")
    )
    assert "kidneymatch.compensation" not in source
