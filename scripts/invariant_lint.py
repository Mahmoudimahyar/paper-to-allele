#!/usr/bin/env python3
"""Traceability from feature-spec invariants to the tests that enforce them.

P2-1 of the harness readiness review. Every spec carries an `invariants` array
and, before this, nothing connected those sentences to any test. "Everything is
tested" was an assertion rather than something the repository could check.

Convention:

    @pytest.mark.invariant("HIST-001", "re-ingestion is idempotent")
    def test_same_export_twice_creates_no_duplicates(): ...

The invariant text must match the spec VERBATIM. That is deliberate: a
paraphrase drifts from the spec silently, and a typo would otherwise create a
test that claims coverage it does not provide.

This lint FAILS on a broken reference (unknown spec, or text that is not one of
that spec's invariants) because those are always mistakes. It REPORTS, without
failing, on invariants that no test covers yet: an unimplemented task legitimately
has uncovered invariants. Coverage is enforced where it matters instead - by
`taskctl.py`, which refuses to mark a task COMPLETE while any invariant it owns
is unproven.

Markers are read statically, so the arguments must be literal strings.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "specs/features"
TESTS = ROOT / "tests"
QUEUE = ROOT / "docs/work/WORK_QUEUE.json"
LIVE = {"READY", "ACTIVE"}


def live_spec_invariants() -> dict[str, list[str]]:
    """Invariants of every spec referenced by a live task."""
    queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    wanted = {
        task["spec"] for task in queue["tasks"] if task.get("status") in LIVE and task.get("spec")
    }
    out: dict[str, list[str]] = {}
    for relative in sorted(wanted):
        spec = json.loads((ROOT / relative).read_text(encoding="utf-8"))
        out[spec["id"]] = list(spec.get("invariants", []))
    return out


def _literal_args(call: ast.Call) -> list[str] | None:
    values = []
    for arg in call.args:
        if not isinstance(arg, ast.Constant) or not isinstance(arg.value, str):
            return None
        values.append(arg.value)
    return values


def _invariant_calls(tree: ast.AST) -> list[tuple[list[str] | None, int]]:
    """Every `pytest.mark.invariant(...)` call in the module, with line numbers."""
    found: list[tuple[list[str] | None, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "invariant":
            # Match pytest.mark.invariant / mark.invariant
            owner = func.value
            if (
                isinstance(owner, ast.Attribute)
                and owner.attr == "mark"
                or isinstance(owner, ast.Name)
                and owner.id == "mark"
            ):
                found.append((_literal_args(node), node.lineno))
    return found


def collect_claims() -> tuple[dict[tuple[str, str], list[str]], list[str]]:
    """Map (spec id, invariant text) -> locations, plus any malformed markers."""
    claims: dict[tuple[str, str], list[str]] = {}
    problems: list[str] = []

    for path in sorted(TESTS.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            problems.append(f"{path.relative_to(ROOT)}: cannot parse: {exc}")
            continue
        for args, lineno in _invariant_calls(tree):
            location = f"{path.relative_to(ROOT)}:{lineno}"
            if args is None or len(args) != 2:
                problems.append(
                    f"{location}: invariant marker needs exactly two literal string "
                    f"arguments: @pytest.mark.invariant('<SPEC-ID>', '<verbatim text>')"
                )
                continue
            claims.setdefault((args[0], args[1]), []).append(location)

    return claims, problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    specs = live_spec_invariants()
    claims, errors = collect_claims()

    # A marker must point at a real invariant of a real spec.
    for (spec_id, text), locations in sorted(claims.items()):
        if spec_id not in specs:
            errors.append(
                f"{locations[0]}: invariant marker names unknown or non-live spec "
                f"{spec_id!r}. Live specs: {sorted(specs)}"
            )
        elif text not in specs[spec_id]:
            errors.append(
                f"{locations[0]}: text is not a verbatim invariant of {spec_id}: {text!r}"
            )

    covered = {key for key in claims if key[0] in specs and key[1] in specs[key[0]]}
    uncovered = [
        (spec_id, text)
        for spec_id, invariants in specs.items()
        for text in invariants
        if (spec_id, text) not in covered
    ]

    if args.json:
        print(
            json.dumps(
                {
                    "specs": {k: len(v) for k, v in specs.items()},
                    "covered": [list(k) for k in sorted(covered)],
                    "uncovered": [list(x) for x in uncovered],
                    "errors": errors,
                },
                indent=2,
            )
        )
        return 1 if errors else 0

    if errors:
        print("invariant_lint: FAIL")
        for error in errors:
            print(" -", error)
        return 1

    total = sum(len(v) for v in specs.values())
    print(f"invariant_lint: OK ({len(covered)}/{total} live spec invariants have a covering test)")
    for spec_id, text in uncovered:
        print(f"  UNPROVEN {spec_id}: {text}")
    if uncovered:
        print("  (not a failure: these block their task's COMPLETE, not the build)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
