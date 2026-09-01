from pathlib import Path

import pytest

# Acceptance for BOOT-001 selects on this marker: pytest --task BOOT-001
pytestmark = pytest.mark.task("BOOT-001")

ROOT = Path(__file__).resolve().parents[2]
THIS_FILE = Path(__file__).resolve()


def test_real_data_directories_are_not_fixture_sources() -> None:
    test_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in (ROOT / "tests").rglob("*.py")
        if path.resolve() != THIS_FILE
    )
    assert "data/raw/telegram-export" not in test_text
