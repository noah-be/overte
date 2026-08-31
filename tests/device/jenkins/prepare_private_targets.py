#!/usr/bin/env python3
"""Create disabled, private target templates for one local device-lab host."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys


HERE = Path(__file__).resolve().parent
DEVICE_ROOT = HERE.parent


def fail(message: str) -> "NoReturn":
    raise RuntimeError(message)


def private_write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    if os.name != "nt":
        temporary.chmod(stat.S_IRUSR | stat.S_IWUSR)
    temporary.replace(path)


def private_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    if os.name != "nt":
        temporary.chmod(stat.S_IRUSR | stat.S_IWUSR)
    temporary.replace(path)


def environment_assignment(name: str, value: str) -> str:
    if not name or any(character in value for character in ("\0", "\n", "\r")):
        fail("agent environment contains an unsafe value")
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'{name}="{escaped}"'


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schemaVersion") != 1 or not isinstance(value.get("targets"), list):
        fail(f"invalid target template: {path}")
    return value


def prepare(arguments: argparse.Namespace) -> int:
    root = Path(arguments.config_root).expanduser().resolve()
    state_path = root / "local-lab.json"
    if not state_path.is_file():
        fail("install the local device lab before preparing target files")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state.get("schemaVersion") != 1:
        fail("unsupported local device-lab state")
    targets = root / "targets"
    targets.mkdir(parents=True, exist_ok=True, mode=0o700)

    appium_path = targets / "appium.json"
    if arguments.environment_only:
        if not appium_path.is_file():
            fail("environment-only requires existing private target files")
    else:
        appium = load_json(DEVICE_ROOT / "adapters/appium/targets.example.json")
        for target in appium["targets"]:
            target["enabled"] = False
        private_write(appium_path, appium)

    environment = {
        "schemaVersion": 1,
        "variables": {
            "OVERTE_APPIUM_TARGETS": str(appium_path),
            "APPIUM_HOME": state["appiumHome"],
            "OVERTE_CONAN_CACHE_ROOT": str(root / "conan-cache"),
            "OVERTE_ANDROID_BUILD_ROOT": str(root / "android-build-workspaces"),
        },
        "activationRequired": True,
        "note": "All targets are disabled until private selectors and hardware gates are completed.",
    }
    private_write(root / "target-environment.json", environment)
    private_text(root / "agent.env", "\n".join(
        environment_assignment(name, str(value))
        for name, value in sorted(environment["variables"].items())
    ) + "\n")
    if arguments.environment_only:
        print(f"Updated the private Jenkins agent environment for {targets}")
    else:
        print(f"Prepared disabled private target files in {targets}")
    return 0


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--config-root", required=True)
    value.add_argument("--environment-only", action="store_true")
    return value


def main() -> int:
    try:
        return prepare(parser().parse_args())
    except (RuntimeError, OSError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
