#!/usr/bin/env python3
"""Scan for Iranian personal data that must never enter the repository.

P2-8 of the harness readiness review. The previous protection was a single test
grepping for one literal path string, which is close to no protection for the
highest-severity risk in this project.

Two detectors, chosen because they have low false-positive rates:

* **National ID (کد ملی)** - 10 digits gated by the official mod-11 checksum.
  A bare `\\d{10}` also matches timestamps, hashes, offsets and lab report
  numbers; the checksum admits only about one in eleven random candidates, which
  is the difference between a scanner people keep and one they mute.
* **Mobile number** - `+98` / `0098` / `09xx` followed by the national
  significant number. All Iranian mobiles begin with 9.

Findings are printed REDACTED. A scanner that echoes the value it found turns
every CI log into a second copy of the leak.

Usage:
    python scripts/scan_pii.py [PATH ...]

With no arguments it scans the directories most likely to accumulate leaked
data: source, tests, docs, config, and generated artifacts.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_TARGETS = ("src", "tests", "docs", "scripts", "config", "specs", "schemas", ".artifacts")

# Lockfiles and vendored metadata carry long digit runs that are not personal
# data; scanning them produces noise that trains people to ignore the tool.
SKIP_NAMES = {"uv.lock", ".gitleaks-baseline.json"}
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache"}
TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".txt",
    ".html",
    ".htm",
    ".csv",
    ".tsv",
    ".log",
    ".cfg",
    ".ini",
    ".sh",
    ".sql",
    ".xml",
}

NATIONAL_ID = re.compile(r"(?<!\d)\d{10}(?!\d)")
MOBILE = re.compile(r"(?<!\d)(?:\+98|0098|98|0)9\d{9}(?!\d)")


def is_valid_national_id(value: str) -> bool:
    """Official mod-11 check for a 10-digit Iranian national ID.

    s = (sum of d[i] * (10 - i) for i in 0..8) mod 11
    valid iff  d[9] == s        when s < 2
               d[9] + s == 11   when s >= 2
    """
    if len(value) != 10 or not value.isdigit():
        return False
    check = int(value[9])
    total = sum(int(value[i]) * (10 - i) for i in range(9)) % 11
    return check == total if total < 2 else check + total == 11


def is_placeholder(value: str) -> bool:
    """Repeated-digit values satisfy the checksum but are never real people.

    `1111111111` genuinely passes the mod-11 check. Reporting it as a leak would
    flag obvious placeholders and erode trust in the scanner.
    """
    return len(set(value)) < 3


def redact(value: str) -> str:
    """Show only enough to locate the value, never enough to identify anyone."""
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"


def iter_files(targets: list[Path]) -> list[Path]:
    files: list[Path] = []
    for target in targets:
        if target.is_file():
            files.append(target)
            continue
        for path in target.rglob("*"):
            if not path.is_file():
                continue
            if SKIP_DIRS & set(path.parts) or path.name in SKIP_NAMES:
                continue
            if path.suffix.lower() in TEXT_SUFFIXES:
                files.append(path)
    return files


def scan(path: Path) -> list[tuple[int, str, str]]:
    """Return (line number, kind, redacted value) for each finding."""
    findings: list[tuple[int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return findings

    for lineno, line in enumerate(text.splitlines(), 1):
        for match in MOBILE.finditer(line):
            findings.append((lineno, "iran-mobile", redact(match.group())))
        for match in NATIONAL_ID.finditer(line):
            value = match.group()
            if is_valid_national_id(value) and not is_placeholder(value):
                findings.append((lineno, "iran-national-id", redact(value)))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan for Iranian PII.")
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args()

    targets = [Path(p) for p in args.paths] or [
        ROOT / name for name in DEFAULT_TARGETS if (ROOT / name).exists()
    ]
    targets = [t for t in targets if t.exists()]

    total = 0
    for path in iter_files(targets):
        for lineno, kind, value in scan(path):
            total += 1
            try:
                shown = path.relative_to(ROOT)
            except ValueError:
                shown = path
            print(f"{shown}:{lineno}: {kind}: {value}")

    if total:
        print(f"\nscan_pii: FAIL ({total} finding(s))")
        print("Values are redacted above on purpose. Remove the data; do not")
        print("commit it and do not paste it into a report or an issue.")
        return 1

    print(f"scan_pii: OK (no Iranian PII found in {len(iter_files(targets))} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
