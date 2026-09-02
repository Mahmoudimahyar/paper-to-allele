"""The Iranian PII scanner must actually detect, and must never echo.

Test values are CONSTRUCTED at runtime from the checksum rather than written as
literals. A hard-coded valid national ID in this file would be a PII-shaped
string committed to the repository - exactly what the scanner exists to prevent,
and it would make the scanner fail on its own test suite.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

# Acceptance for BOOT-001 selects on this marker: pytest --task BOOT-001
pytestmark = pytest.mark.task("BOOT-001")

ROOT = Path(__file__).resolve().parents[2]
SCANNER = ROOT / "scripts/scan_pii.py"


def load_scanner():
    spec = importlib.util.spec_from_file_location("km_scan_pii", SCANNER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_mobile(kind: str = "local") -> str:
    """Assemble a mobile number at runtime.

    Written in pieces so no mobile-shaped literal is ever committed: the
    scanner flags this file otherwise, and it is right to.
    """
    nsn = "9" + "12" + "1234567"
    return {"local": "0" + nsn, "plus": "+" + "98" + nsn, "intl": "00" + "98" + nsn}[kind]


def make_national_id(prefix: str) -> str:
    """Build a checksum-valid 10-digit ID from a 9-digit prefix."""
    assert len(prefix) == 9
    total = sum(int(prefix[i]) * (10 - i) for i in range(9)) % 11
    check = total if total < 2 else 11 - total
    return f"{prefix}{check}"


def test_the_generator_agrees_with_the_validator() -> None:
    scanner = load_scanner()
    for prefix in ("123456789", "049937089", "008457594", "987654321"):
        assert scanner.is_valid_national_id(make_national_id(prefix))


def test_a_valid_national_id_is_detected(tmp_path: Path) -> None:
    scanner = load_scanner()
    target = tmp_path / "leak.md"
    target.write_text(f"patient code {make_national_id('123456789')}\n", encoding="utf-8")

    findings = scanner.scan(target)
    assert [kind for _, kind, _ in findings] == ["iran-national-id"]


def test_a_digit_string_that_fails_the_checksum_is_ignored(tmp_path: Path) -> None:
    """The checksum is what makes this scanner survivable.

    A bare 10-digit regex also matches timestamps, offsets and report numbers,
    and a scanner that cries wolf gets muted within a week.
    """
    scanner = load_scanner()
    valid = make_national_id("123456789")
    invalid = valid[:9] + str((int(valid[9]) + 1) % 10)
    target = tmp_path / "noise.md"
    target.write_text(f"report number {invalid}\n", encoding="utf-8")
    assert scanner.scan(target) == []


def test_repeated_digit_placeholders_are_not_reported(tmp_path: Path) -> None:
    """1111111111 genuinely satisfies the checksum but is never a person."""
    scanner = load_scanner()
    assert scanner.is_valid_national_id("1111111111") is True
    target = tmp_path / "placeholder.md"
    target.write_text("example id 1111111111\n", encoding="utf-8")
    assert scanner.scan(target) == []


@pytest.mark.parametrize("kind", ["local", "plus", "intl"])
def test_iranian_mobile_numbers_are_detected(tmp_path: Path, kind: str) -> None:
    scanner = load_scanner()
    target = tmp_path / "contact.md"
    target.write_text(f"call {make_mobile(kind)}\n", encoding="utf-8")
    assert [k for _, k, _ in scanner.scan(target)] == ["iran-mobile"]


def test_a_landline_shaped_number_is_not_reported_as_mobile(tmp_path: Path) -> None:
    scanner = load_scanner()
    target = tmp_path / "landline.md"
    landline = "0" + "21" + "12345678"
    target.write_text(f"office {landline}\n", encoding="utf-8")
    assert [kind for _, kind, _ in scanner.scan(target) if kind == "iran-mobile"] == []


def test_findings_are_redacted_and_never_echo_the_value(tmp_path: Path) -> None:
    """A scanner that prints what it found makes the CI log a second leak."""
    national_id = make_national_id("123456789")
    mobile = make_mobile()
    target = tmp_path / "leak.md"
    target.write_text(f"id {national_id}\nphone {mobile}\n", encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(SCANNER), str(target)], capture_output=True, text=True
    )
    assert proc.returncode == 1, "the scanner must exit non-zero on a finding"
    assert national_id not in proc.stdout
    assert mobile not in proc.stdout
    assert "iran-national-id" in proc.stdout
    assert "iran-mobile" in proc.stdout
    assert "*" in proc.stdout


def test_the_repository_itself_is_clean() -> None:
    proc = subprocess.run([sys.executable, str(SCANNER)], capture_output=True, text=True, cwd=ROOT)
    assert proc.returncode == 0, f"PII found in the repository:\n{proc.stdout}"
