\
#!/usr/bin/env python3
"""Token-efficient environment/credential doctor. Never prints secret values."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
CREDENTIALS = json.loads((ROOT / "config/credentials.json").read_text(encoding="utf-8"))

PHASE_ORDER = ["MVP-HIST", "V1-MATCH", "V2-SYNC", "V3-BOT-INTAKE", "V4-BOT-MATCH", "V5-WEB"]
CURRENT_PHASE = "MVP-HIST"


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
    py_ok = sys.version_info[:2] == (3, 12)
    commands = [command_info(x) for x in ("git", "uv", "docker", "tesseract")]
    env_items = [check_env_item(x) for x in current_phase_items()]
    return {
        "project": "kidneymatch-iran",
        "phase": CURRENT_PHASE,
        "python": {"version": platform.python_version(), "expected": "3.12.x", "ok": py_ok},
        "commands": commands,
        "environment": env_items,
    }


def human_actions(data: dict[str, object]) -> list[str]:
    actions: list[str] = []
    if not data["python"]["ok"]:  # type: ignore[index]
        actions.append("Install/use Python 3.12 for the project environment.")
    commands = {x["name"]: x for x in data["commands"]}  # type: ignore[index]
    if not commands["git"]["present"]:
        actions.append("Install Git.")
    if not commands["uv"]["present"]:
        actions.append("Install uv (recommended) or use an equivalent isolated Python workflow.")
    for item in data["environment"]:  # type: ignore[index]
        if item["env"] == "KM_TELEGRAM_EXPORT_DIR" and not item["present"]:
            # Not a hard failure for synthetic tests.
            actions.append("For a real-data smoke test, set KM_TELEGRAM_EXPORT_DIR in local .env; synthetic tests can proceed without it.")
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
        print("HUMAN ACTION REQUIRED:" if "real-data" not in action.lower() else "HUMAN ACTION LATER:", action)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
