"""Behavioural tests for the harness hooks.

Hooks are loaded by Claude Code at session start, so a wiring mistake cannot be
observed from inside the session that introduces it. These tests drive each hook
directly with the documented stdin payload and assert on its exit code, so the
guards are verified rather than assumed.

Exit-code contract these tests encode (from the hooks documentation):
  * exit 2  -> PreToolUse BLOCKS the tool call; stderr becomes the reason.
  * exit 1  -> NON-blocking error: the tool call PROCEEDS. A guard must never
               use it, because failing open is indistinguishable from success.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

# Acceptance for BOOT-001 selects on this marker: pytest --task BOOT-001
pytestmark = pytest.mark.task("BOOT-001")

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / "scripts/hooks"
SETTINGS = ROOT / ".claude/settings.json"

BLOCK = 2
ALLOW = 0

# Resolve bash explicitly rather than letting subprocess search PATH. On Windows
# a bare "bash" can resolve to WSL bash, whose filesystem view is /mnt/c/... ,
# while Claude Code runs hooks under Git Bash, whose view is /c/... . Testing
# against a different interpreter than production would validate nothing.
BASH = shutil.which("bash") or "bash"


def test_bash_is_available_for_hooks() -> None:
    """Every hook is a bash script. Without bash they are silently absent."""
    assert shutil.which("bash"), "bash is required to run the harness hooks"


def run_hook(script: str, payload: object, env_extra: dict[str, str] | None = None) -> int:
    import os

    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(ROOT), **(env_extra or {})}
    text = payload if isinstance(payload, str) else json.dumps(payload)
    # Invoke with cwd=ROOT and a RELATIVE path. MSYS bash on Windows resolves
    # neither `C:\...` nor `C:/...` (it wants /c/...), so an absolute path here
    # exits 127 and looks like a broken hook rather than a broken test.
    proc = subprocess.run(
        [BASH, f"scripts/hooks/{script}"],
        input=text,
        text=True,
        capture_output=True,
        env=env,
        cwd=ROOT,
    )
    return proc.returncode


# --------------------------------------------------------------------------
# guard_ledger: the acceptance ledger may only change via scripts/acceptance.py
# --------------------------------------------------------------------------


def test_direct_edit_of_the_ledger_is_blocked() -> None:
    code = run_hook(
        "guard_ledger.sh",
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": str(ROOT / "docs/work/acceptance.json")},
        },
    )
    assert code == BLOCK


def test_writing_an_unrelated_file_is_allowed() -> None:
    code = run_hook(
        "guard_ledger.sh",
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(ROOT / "src/kidneymatch/ingestion/media.py")},
        },
    )
    assert code == ALLOW


def test_rewriting_the_ledger_through_bash_is_blocked() -> None:
    """The reference implementation guards only Write/Edit, so sed/jq slip past."""
    for command in (
        "sed -i 's/false/true/' docs/work/acceptance.json",
        "jq '.tasks' docs/work/acceptance.json > x && mv x docs/work/acceptance.json",
        "python -c \"import json; json.dump({}, open('docs/work/acceptance.json','w'))\"",
    ):
        code = run_hook(
            "guard_ledger.sh",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": command},
            },
        )
        assert code == BLOCK, f"not blocked: {command}"


def test_the_sanctioned_acceptance_script_is_allowed_through_bash() -> None:
    code = run_hook(
        "guard_ledger.sh",
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": "python scripts/acceptance.py mark HIST-001 0 "
                "--evidence .artifacts/HIST-001/acceptance-1.log"
            },
        },
    )
    assert code == ALLOW


def test_reading_the_ledger_through_bash_is_allowed() -> None:
    """Regression: an early heuristic scanned the whole command for mutator
    tokens, so a multi-line script that merely READ the ledger was blocked
    because an unrelated `rm -rf` appeared elsewhere in it, and because plain
    `open(` was treated as a write. Both are read paths and must pass.
    """
    for command in (
        "cat docs/work/acceptance.json",
        "git diff docs/work/acceptance.json",
        "grep passes docs/work/acceptance.json",
        'rm -rf /tmp/scratch\npython -c "import json; '
        "d=json.load(open('docs/work/acceptance.json', encoding='utf-8')); print(len(d))\"",
    ):
        code = run_hook(
            "guard_ledger.sh",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": command},
            },
        )
        assert code == ALLOW, f"read wrongly blocked: {command}"


def test_write_mode_open_on_the_ledger_is_still_blocked() -> None:
    command = "python -c \"import json; json.dump({}, open('docs/work/acceptance.json', 'w'))\""
    code = run_hook(
        "guard_ledger.sh",
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": command},
        },
    )
    assert code == BLOCK


def test_a_trailing_comment_cannot_exempt_a_mutation() -> None:
    """Audit finding: the exemption was `"acceptance.py" in segment`, tested
    BEFORE the mutation check, so appending `# per acceptance.py` to any command
    disabled the guard entirely. The exemption now requires an invocation of the
    script by path, and comments are stripped before matching.
    """
    for command in (
        "sed -i 's/false/true/' docs/work/acceptance.json  # per acceptance.py",
        "echo '{}' > docs/work/acceptance.json  # regenerate the way acceptance.py would",
        "cp /tmp/forged.json docs/work/acceptance.json",
        "git checkout -- docs/work/acceptance.json",
    ):
        code = run_hook(
            "guard_ledger.sh",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": command},
            },
        )
        assert code == BLOCK, f"bypass not blocked: {command}"


def test_redirect_direction_is_read_not_guessed() -> None:
    """`cat ledger > backup` writes the BACKUP, not the ledger.

    A bare `">" in segment` test blocked these read-only commands.
    """
    for command in (
        "cat docs/work/acceptance.json > .artifacts/backup.json",
        "cp docs/work/acceptance.json /tmp/backup.json",
        "grep -rn acceptance.json scripts/ > /tmp/refs.txt",
    ):
        code = run_hook(
            "guard_ledger.sh",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": command},
            },
        )
        assert code == ALLOW, f"read wrongly blocked: {command}"


def test_unparseable_payload_fails_closed() -> None:
    """An exception must not fall through to exit 1, which would fail OPEN."""
    assert run_hook("guard_ledger.sh", "this is not json") == BLOCK


# --------------------------------------------------------------------------
# guard_session: kill switch and one-shot steering
# --------------------------------------------------------------------------


def test_kill_switch_blocks_every_tool_call(tmp_path: Path) -> None:
    stop = tmp_path / "AGENT_STOP"
    stop.write_text("stop for review", encoding="utf-8")
    code = run_hook(
        "guard_session.sh",
        {"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {}},
        {"KM_AGENT_STOP_FILE": str(stop), "KM_STEER_FILE": str(tmp_path / "none.md")},
    )
    assert code == BLOCK


def test_absent_kill_switch_allows(tmp_path: Path) -> None:
    code = run_hook(
        "guard_session.sh",
        {"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {}},
        {
            "KM_AGENT_STOP_FILE": str(tmp_path / "AGENT_STOP"),
            "KM_STEER_FILE": str(tmp_path / "STEER.md"),
        },
    )
    assert code == ALLOW


def test_steering_is_delivered_once_then_cleared(tmp_path: Path) -> None:
    steer = tmp_path / "STEER.md"
    steer.write_text("switch to HIST-002", encoding="utf-8")
    env = {
        "KM_AGENT_STOP_FILE": str(tmp_path / "AGENT_STOP"),
        "KM_STEER_FILE": str(steer),
    }
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {}}

    assert run_hook("guard_session.sh", payload, env) == BLOCK
    assert steer.read_text(encoding="utf-8") == "", "steer file must be cleared after delivery"
    assert run_hook("guard_session.sh", payload, env) == ALLOW, "must not redeliver"


def test_empty_steer_file_delivers_nothing(tmp_path: Path) -> None:
    steer = tmp_path / "STEER.md"
    steer.write_text("", encoding="utf-8")
    code = run_hook(
        "guard_session.sh",
        {"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {}},
        {"KM_AGENT_STOP_FILE": str(tmp_path / "AGENT_STOP"), "KM_STEER_FILE": str(steer)},
    )
    assert code == ALLOW


# --------------------------------------------------------------------------
# stop_checkpoint / post_edit_check / session_start
# --------------------------------------------------------------------------


def test_stop_hook_never_blocks(tmp_path: Path) -> None:
    """A Stop hook that exits 2 prevents Claude from stopping, and Claude Code
    overrides it after 8 consecutive blocks -- silently turning the gate into a
    no-op. This hook must return 0 on every path, including hostile ones.
    """
    payloads = [
        {"hook_event_name": "Stop", "stop_hook_active": False},
        {"hook_event_name": "Stop", "stop_hook_active": True},
        "not json at all",
    ]
    for payload in payloads:
        # Point it at a directory that is not a git repo: still must not block.
        assert run_hook("stop_checkpoint.sh", payload, {"CLAUDE_PROJECT_DIR": str(tmp_path)}) == 0


def test_post_edit_check_ignores_non_python_files() -> None:
    code = run_hook(
        "post_edit_check.sh",
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(ROOT / "docs/INDEX.md")},
        },
    )
    assert code == ALLOW


def test_session_start_is_bounded_and_succeeds() -> None:
    """Its stdout is injected into every session, so it must stay small."""
    import os

    proc = subprocess.run(
        [BASH, "scripts/hooks/session_start.sh"],
        input="{}",
        text=True,
        capture_output=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(ROOT)},
        cwd=ROOT,
    )
    assert proc.returncode == 0
    lines = proc.stdout.strip().splitlines()
    assert 5 < len(lines) < 40, f"orientation is {len(lines)} lines; keep it small"
    assert "acceptance" in proc.stdout.lower()


def test_session_start_warns_when_the_kill_switch_is_set(tmp_path: Path) -> None:
    import os
    import shutil as sh

    sandbox = tmp_path / "repo"
    sh.copytree(ROOT / "scripts", sandbox / "scripts")
    (sandbox / "AGENT_STOP").write_text("halted", encoding="utf-8")
    proc = subprocess.run(
        [BASH, "scripts/hooks/session_start.sh"],
        input="{}",
        text=True,
        capture_output=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(sandbox)},
        cwd=sandbox,
    )
    assert proc.returncode == 0
    assert "AGENT_STOP" in proc.stdout


# --------------------------------------------------------------------------
# settings.json wiring
# --------------------------------------------------------------------------


def _settings() -> dict:
    return json.loads(SETTINGS.read_text(encoding="utf-8"))


def test_every_configured_hook_script_exists() -> None:
    settings = _settings()
    referenced = [
        handler["command"]
        for groups in settings["hooks"].values()
        for group in groups
        for handler in group["hooks"]
    ]
    assert referenced, "no hooks configured"
    for command in referenced:
        name = command.split("scripts/hooks/")[1].rstrip('"')
        assert (HOOKS / name).is_file(), f"hook script missing: {name}"


def test_stop_hook_has_no_matcher() -> None:
    """Stop does not support matchers; one added there is silently ignored."""
    for group in _settings()["hooks"]["Stop"]:
        assert "matcher" not in group


def test_permission_paths_use_rule_forms_that_are_actually_consulted() -> None:
    """Claude Code consults only Edit(path) and Read(path) for file rules.

    A Write(...)/Glob(...)/MultiEdit(...) path rule is accepted, never applied,
    and warned about at startup -- a permission that silently does nothing.
    """
    permissions = _settings()["permissions"]
    rules = [r for key in ("allow", "ask", "deny") for r in permissions.get(key, [])]
    bad = [r for r in rules if r.startswith(("Write(", "Glob(", "MultiEdit(", "NotebookEdit("))]
    assert bad == [], f"these file rules are never consulted; use Edit()/Read(): {bad}"


def test_bash_rules_are_not_accidentally_overbroad() -> None:
    """`Bash(git status*)` also matches `git statusfoo`; `:*` is the canonical form."""
    rules = [r for r in _settings()["permissions"]["allow"] if r.startswith("Bash(")]
    for rule in rules:
        inner = rule[len("Bash(") : -1]
        if inner.endswith("*") and not inner.endswith((":*", " *", "/*")):
            pytest.fail(f"over-broad bash allow rule {rule!r}; write it as a ':*' suffix")


# --------------------------------------------------------------------------
# Regressions found by the P1 adversarial audit
# --------------------------------------------------------------------------


def test_non_object_json_payloads_fail_closed() -> None:
    """`json.loads` accepts null/42/[]/"x" -- all parse, none are objects.

    Calling .get() on them raised, and an uncaught exception exits 1, which does
    NOT block. Every one of these previously failed OPEN.
    """
    for payload in ("null", "true", "42", "[]", '"x"'):
        assert run_hook("guard_ledger.sh", payload) == BLOCK, f"failed open on {payload}"


def test_post_edit_check_will_not_touch_files_outside_the_repository(tmp_path: Path) -> None:
    """`ruff check --fix` rewrites whatever it is handed.

    Before this guard, an edit to any absolute .py path outside the project had
    its code modified by the hook: an unused import was stripped from a file in
    a temp directory that had nothing to do with this repository.
    """
    victim = tmp_path / "victim.py"
    original = "import os\nx = 1\n"
    victim.write_text(original, encoding="utf-8")

    run_hook(
        "post_edit_check.sh",
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": str(victim)},
        },
    )
    assert victim.read_text(encoding="utf-8") == original, (
        "the hook modified a file outside the project tree"
    )


def test_path_conversion_leaves_posix_paths_alone_off_windows() -> None:
    """`/a/project/x.py` is a legal POSIX path whose first component is one
    letter. The drive-letter rewrite turned it into a bogus `A:` drive path, which
    would break every hook on Linux CI.
    """
    import os

    script = (
        "uname() { echo Linux; }; . scripts/hooks/_paths.sh; "
        'printf "%s|%s" "$(km_to_native /a/project/x.py)" "$(km_to_unix /home/u/f)"'
    )
    proc = subprocess.run(
        [BASH, "-c", script], capture_output=True, text=True, cwd=ROOT, env={**os.environ}
    )
    assert proc.stdout.strip() == "/a/project/x.py|/home/u/f"
