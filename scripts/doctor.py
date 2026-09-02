#!/usr/bin/env python3
"""Token-efficient environment/credential doctor. Never prints secret values."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CREDENTIALS = json.loads((ROOT / "config/credentials.json").read_text(encoding="utf-8"))

PHASE_ORDER = ["MVP-HIST", "V1-MATCH", "V2-SYNC", "V3-BOT-INTAKE", "V4-BOT-MATCH", "V5-WEB"]
CURRENT_PHASE = "MVP-HIST"


def project_python() -> dict[str, object]:
    """Report the interpreter the project actually builds/tests with.

    Verification runs through `uv run --frozen`, i.e. the pinned `.venv`, so the
    interpreter that happens to launch this script is irrelevant. Checking
    `sys.version_info` here made the doctor emit HUMAN ACTION REQUIRED on every
    run whenever a newer system Python was first on PATH, which trains agents to
    ignore the one channel reserved for genuine blockers.
    """
    venv = ROOT / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
    if venv.is_file():
        proc = subprocess.run(
            [str(venv), "-c", "import sys; print('%d.%d.%d' % sys.version_info[:3])"],
            text=True,
            capture_output=True,
        )
        version = proc.stdout.strip()
        if version:
            return {
                "version": version,
                "expected": "3.12.x",
                "ok": version.startswith("3.12."),
                "source": "project .venv",
            }
    return {
        "version": platform.python_version(),
        "expected": "3.12.x",
        "ok": sys.version_info[:2] == (3, 12),
        "source": "current interpreter (no project .venv found)",
    }


def command_info(name: str) -> dict[str, object]:
    path = shutil.which(name)
    return {"name": name, "present": bool(path), "path": path}


def current_phase_items() -> list[dict[str, object]]:
    current_index = PHASE_ORDER.index(CURRENT_PHASE)
    items = []
    for item in CREDENTIALS["items"]:
        phase = item["phase"]
        if phase in PHASE_ORDER and PHASE_ORDER.index(phase) <= current_index:
            items.append(item)
    return items


def check_env_item(item: dict[str, object]) -> dict[str, object]:
    name = str(item["env"])
    value = os.getenv(name, "")
    result: dict[str, object] = {
        "id": item["id"],
        "env": name,
        "required": item["required"],
        "secret": item["secret"],
        "present": bool(value),
        "status": "OK" if value else "MISSING_OR_NOT_NEEDED_YET",
    }
    if value and item.get("validation") == "path_exists":
        exists = Path(value).expanduser().exists()
        result["valid"] = exists
        result["status"] = "OK" if exists else "INVALID_PATH"
    return result


def report() -> dict[str, object]:
    commands = [command_info(x) for x in ("git", "uv", "docker", "tesseract")]
    env_items = [check_env_item(x) for x in current_phase_items()]
    return {
        "project": "kidneymatch-iran",
        "phase": CURRENT_PHASE,
        "python": project_python(),
        "commands": commands,
        "environment": env_items,
    }


def human_actions(data: dict[str, object]) -> list[str]:
    actions: list[str] = []
    if not data["python"]["ok"]:  # type: ignore[index]
        actions.append("Create the pinned project environment: `uv sync --python 3.12`.")
    commands = {x["name"]: x for x in data["commands"]}  # type: ignore[index]
    if not commands["git"]["present"]:
        actions.append("Install Git.")
    if not commands["uv"]["present"]:
        actions.append("Install uv (recommended) or use an equivalent isolated Python workflow.")
    for item in data["environment"]:  # type: ignore[index]
        if item["env"] == "KM_TELEGRAM_EXPORT_DIR" and not item["present"]:
            # Not a hard failure for synthetic tests.
            actions.append(
                "For a real-data smoke test, set KM_TELEGRAM_EXPORT_DIR in local .env; "
                "synthetic tests can proceed without it."
            )
        if item.get("status") == "INVALID_PATH":
            actions.append(f"Fix local path in {item['env']}; the current value does not exist.")
    return actions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--brief", action="store_true")
    args = parser.parse_args()
    data = report()
    actions = human_actions(data)
    if args.json:
        print(json.dumps({**data, "human_actions": actions}, indent=2))
        return 0
    print(f"KidneyMatch doctor | phase={CURRENT_PHASE} | python={data['python']['version']}")  # type: ignore[index]
    present = [x["name"] for x in data["commands"] if x["present"]]  # type: ignore[index]
    missing = [x["name"] for x in data["commands"] if not x["present"]]  # type: ignore[index]
    print("tools present:", ", ".join(present) or "none")
    if missing and not args.brief:
        print("tools absent/optional depending on task:", ", ".join(missing))
    for action in actions:
        print(
            "HUMAN ACTION REQUIRED:"
            if "real-data" not in action.lower()
            else "HUMAN ACTION LATER:",
            action,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
