#!/usr/bin/env python3
"""Deterministic virtual adapter used to prove the complete E2E stack device-free."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time


CAPABILITIES = sorted([
    "app.foreground", "app.launch", "app.process", "input.look", "input.move",
    "probe.snapshot", "scene.load", "tablet.close", "tablet.open",
])


def cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("discover", "describe", "invoke", "cleanup"))
    parser.add_argument("--target")
    parser.add_argument("--operation")
    parser.add_argument("--arguments", default="{}")
    return parser.parse_args()


def state_path() -> Path:
    value = os.environ.get("OVERTE_MOCK_E2E_STATE")
    if not value:
        raise RuntimeError("OVERTE_MOCK_E2E_STATE is required")
    return Path(value)


def initial_state() -> dict:
    pico = os.environ.get("OVERTE_PICO_OPENXR_INPUT") == "1"
    return {
        "running": False, "foreground": False, "sceneUrl": "", "sceneReady": False,
        "launchCount": 0, "sceneLoadCount": 0,
        "position": {"x": 0.0, "y": 2.0 if pico else 1.0, "z": 4.0},
        "orientation": {"x": 0.0, "y": 0.0, "z": 0.0}, "tablet": False,
        "picoRouteActive": False, "inputSequence": 0,
    }


def load() -> dict:
    path = state_path()
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else initial_state()


def save(value: dict) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def emit(value: object) -> None:
    print(json.dumps(value, separators=(",", ":"), sort_keys=True))


def invoke(operation: str, arguments: dict) -> dict:
    state = load()
    if operation == "app.launch":
        state["running"] = state["foreground"] = True
        state["launchCount"] += 1
        result = {"launched": True}
    elif operation == "app.process":
        return {"running": state["running"],
                "identity": "mock-e2e-process" if state["running"] else None}
    elif operation == "app.foreground":
        return {"foreground": state["foreground"]}
    elif operation == "scene.load":
        state["sceneUrl"] = arguments.get("url", "")
        state["sceneReady"] = True
        state["sceneLoadCount"] += 1
        result = {"requested": True}
    elif operation == "input.look":
        state["inputSequence"] += 1
        state["picoRouteActive"] = False
        state["orientation"]["y"] += 30.0
        result = {"performed": True, "neutralBeforeCommand": False,
                  "sequence": state["inputSequence"]}
    elif operation == "input.move":
        state["inputSequence"] += 1
        state["picoRouteActive"] = True
        state["position"]["z"] -= 1.0
        result = {"performed": True, "neutralBeforeCommand": True,
                  "sequence": state["inputSequence"]}
    elif operation == "tablet.open":
        state["inputSequence"] += 1
        state["tablet"] = True
        result = {"performed": True, "neutralBeforeCommand": True,
                  "sequence": state["inputSequence"]}
    elif operation == "tablet.close":
        state["inputSequence"] += 1
        state["tablet"] = False
        result = {"performed": True, "neutralBeforeCommand": True,
                  "sequence": state["inputSequence"]}
    elif operation == "probe.snapshot":
        snapshot = {
            "schemaVersion": 1,
            "sampleEpochMs": int(time.time() * 1000),
            "build": {"platform": "Mock", "version": "device-contract",
                      "date": "1970-01-01"},
            "application": {"running": state["running"], "foreground": state["foreground"]},
            "scene": {"url": state["sceneUrl"], "ready": state["sceneReady"],
                      "entityCount": 4 if state["sceneReady"] else 0},
            "avatar": {"position": state["position"]},
            "view": {"orientation": state["orientation"]},
            "tablet": {"open": state["tablet"], "home": state["tablet"]},
        }
        if os.environ.get("OVERTE_PICO_OPENXR_INPUT") == "1":
            route_value = 0.8 if state["picoRouteActive"] else 0.0
            snapshot["input"] = {
                "dominantHand": "right", "advancedMovementControls": True,
            }
            snapshot["scene"].update({
                "fixtureMarkerCount": 4 if state["sceneReady"] else 0,
                "floorTopY": 0.0 if state["sceneReady"] else None,
                "spawnValidated": state["sceneReady"],
            })
            snapshot["controller"] = {
                "route": {
                    "openxrAxes": {"lx": 0.0, "ly": route_value,
                                   "rx": 0.0, "ry": 0.0},
                    "standardLy": route_value,
                    "translateZAction": route_value,
                    "rawTranslateZDriveKey": route_value,
                    "translateZDriveKeyDisabled": False,
                },
                "axes": {
                    "lx": 0.0, "ly": route_value, "rx": 0.0, "ry": 0.0,
                    "leftTrigger": 0.0, "rightTrigger": 0.0,
                    "leftGrip": 0.0, "rightGrip": 0.0,
                },
                "buttons": {
                    "menu": False, "leftPrimary": False, "leftSecondary": False,
                    "leftThumbstick": False, "leftTrigger": False,
                    "rightPrimary": False, "rightSecondary": False,
                    "rightThumbstick": False, "rightTrigger": False,
                },
                "poses": {
                    "left": {"valid": False, "translation": None, "rotation": None},
                    "right": {"valid": False, "translation": None, "rotation": None},
                },
            }
        return snapshot
    else:
        raise RuntimeError(f"unsupported operation: {operation}")
    save(state)
    return result


def main() -> int:
    args = cli()
    if args.action == "discover":
        emit([{"selector": "mock-e2e-target", "displayName": "Virtual E2E Contract",
               "platform": "mock", "physical": False, "capabilities": CAPABILITIES}])
    elif args.action == "describe":
        emit({"adapter": "mock-e2e", "model": "Device-free state machine", "os": "mock"})
    elif args.action == "cleanup":
        state = load()
        state["running"] = state["foreground"] = False
        save(state)
        emit({"cleaned": True})
    else:
        values = json.loads(args.arguments)
        if not isinstance(values, dict) or not args.operation:
            raise RuntimeError("invoke requires an operation and object arguments")
        emit(invoke(args.operation, values))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
