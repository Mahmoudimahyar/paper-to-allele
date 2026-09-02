"""The real archive must never reach git, wherever it is dropped.

A Telegram export copied to the repository root is untracked but NOT ignored,
and the `Stop` hook runs `git add -A` at session end. That combination would
commit real donor and recipient medical data, phone numbers and identity
documents. It nearly happened: the archive arrived at the root and was visible
to `git status` until an ignore rule was added.

These tests are cheap and they guard the single most damaging mistake this
project can make.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

# Acceptance for BOOT-001 selects on this marker: pytest --task BOOT-001
pytestmark = pytest.mark.task("BOOT-001")

ROOT = Path(__file__).resolve().parents[2]

# Shapes a real export arrives in. Each must be ignored no matter where it lands.
ARCHIVE_SHAPES = [
    "ChatExport_2026-08-31",
    "ChatExport_2020-01-01",
    "data/raw/ChatExport_2026-08-31",
    "data/raw/anything.html",
    "data/gold/canonical.sqlite3",
    "data/review/queue.json",
    "data/derived/messages.parquet",
]


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def test_the_repository_is_a_git_repo() -> None:
    assert git("rev-parse", "--is-inside-work-tree").returncode == 0


@pytest.mark.parametrize("path", ARCHIVE_SHAPES)
def test_archive_paths_are_ignored(path: str) -> None:
    """`git check-ignore` exits 0 only when the path is genuinely ignored."""
    assert git("check-ignore", path).returncode == 0, (
        f"{path} is NOT gitignored; `git add -A` would commit real data"
    )


def test_no_export_artefact_is_currently_tracked() -> None:
    """Nothing that looks like a real export may be in the index."""
    tracked = git("ls-files").stdout.splitlines()
    offenders = [
        f
        for f in tracked
        if "ChatExport" in f
        or f.startswith(("data/raw/", "data/gold/", "data/review/", "data/derived/"))
        and not f.endswith(".gitkeep")
    ]
    assert offenders == [], f"real-data paths are tracked by git: {offenders[:10]}"


def test_message_pages_are_never_tracked() -> None:
    """A single committed messages*.html is a full disclosure of the archive."""
    tracked = git("ls-files").stdout.splitlines()
    pages = [
        f
        for f in tracked
        if Path(f).name.startswith("messages")
        and f.endswith(".html")
        # the synthetic fixture is fabricated and is allowed
        and not f.startswith("tests/fixtures/synthetic/")
    ]
    assert pages == [], f"message pages tracked by git: {pages}"


def test_the_env_file_is_ignored() -> None:
    """`.env` holds the local archive path and later real credentials."""
    assert git("check-ignore", ".env").returncode == 0
