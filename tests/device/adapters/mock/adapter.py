#!/usr/bin/env python3
"""Deterministic virtual adapter used to prove the complete E2E stack device-free."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from contracts import validate_operation_arguments


CAPABILITIES = sorted([
    "accessibility.snapshot", "app.foreground", "app.launch", "app.process", "app.stop",
    "input.fly", "input.jump", "input.look", "input.move", "probe.snapshot", "scene.load",
    "tablet.close", "tablet.open",
])
FIXTURE_MARKERS = [
    "OVERTE_E2E_COLLISION_WALL",
    "OVERTE_E2E_EAST",
    "OVERTE_E2E_FLOOR",
    "OVERTE_E2E_NORTH",
    "OVERTE_E2E_ORIGIN",
]
COLLISION_WALL = {
    "name": "OVERTE_E2E_COLLISION_WALL",
    "center": {"x": 0.0, "y": 2.0, "z": 0.5},
    "dimensions": {"x": 8.0, "y": 4.0, "z": 0.5},
}


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
    return {
        "running": False,
        "foreground": False,
        "sceneUrl": "",
        "sceneReady": False,
        "launchCount": 0,
        "sceneLoadCount": 0,
        "processObservationCount": 0,
        "sampleSequence": 0,
        "position": {"x": 0.0, "y": 1.0, "z": 4.0},
        "velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
        "groundY": 1.0,
        "bodyYawDegrees": 0.0,
        "inAir": False,
        "flying": False,
        "flyingEnabled": True,
        "locomotion": None,
        "locomotionSamples": 0,
        "orientation": {"x": 0.0, "y": 0.0, "z": 0.0},
        "tablet": False,
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


def failures() -> set[str]:
    configured = os.environ.get("OVERTE_MOCK_E2E_FAILURES", "")
    values = {item.strip() for item in configured.split(",") if item.strip()}
    if os.environ.get("OVERTE_MOCK_E2E_BAD_JUMP") == "1":
        values.add("jump-no-height")
    if os.environ.get("OVERTE_MOCK_E2E_BAD_FLY") == "1":
        values.add("fly-no-height")
    return values


def reset_scene(state: dict, url: str) -> None:
    state.update({
        "sceneUrl": url,
        "sceneReady": True,
        "position": {"x": 0.0, "y": -1.0 if "floor-fall-through" in failures() else 1.0,
                     "z": 4.0},
        "velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
        "bodyYawDegrees": 0.0,
        "inAir": False,
        "flying": False,
        "locomotion": None,
        "locomotionSamples": 0,
    })


def apply_move(state: dict, direction: str, duration_seconds: float) -> None:
    if state["tablet"] and "tablet-touch-through" not in failures():
        state["velocity"] = {"x": 0.0, "y": 0.0, "z": 0.0}
        return
    yaw = math.radians(float(state["bodyYawDegrees"]))
    forward = (-math.sin(yaw), -math.cos(yaw))
    right = (math.cos(yaw), -math.sin(yaw))
    axis = forward if direction in {"forward", "backward"} else right
    sign = 1.0 if direction in {"forward", "right"} else -1.0
    if "wrong-move-direction" in failures():
        sign *= -1.0
    distance = float(duration_seconds) * 0.75
    target_x = float(state["position"]["x"]) + axis[0] * sign * distance
    target_z = float(state["position"]["z"]) + axis[1] * sign * distance
    wall_near_z = 0.75
    crosses_wall = (state["position"]["z"] >= wall_near_z > target_z
                    and abs(target_x) <= 4.0)
    if crosses_wall and "collision-pass-through" not in failures():
        target_z = 0.85
    state["position"]["x"] = target_x
    state["position"]["z"] = target_z
    state["velocity"] = ({"x": axis[0] * sign, "y": 0.0, "z": axis[1] * sign}
                         if "stuck-input" in failures() else
                         {"x": 0.0, "y": 0.0, "z": 0.0})


def update_vertical_locomotion(state: dict) -> None:
    if state["locomotion"] == "jump":
        state["locomotionSamples"] += 1
        airborne = (state["locomotionSamples"] <= 2
                    or "jump-no-landing" in failures())
        gain = 0.0 if "jump-no-height" in failures() else 0.8
        state["position"]["y"] = state["groundY"] + (gain if airborne else 0.0)
        state["inAir"] = airborne
        state["flying"] = airborne and "jump-as-flight" in failures()
        state["velocity"] = ({"x": 0.0, "y": 1.0, "z": 0.0} if airborne else
                             {"x": 0.0, "y": 0.0, "z": 0.0})
        if not airborne:
            state["locomotion"] = None
    elif state["locomotion"] == "fly":
        state["locomotionSamples"] += 1
        gain = 0.0 if "fly-no-height" in failures() else 1.5
        state["position"]["y"] = state["groundY"] + gain
        state["inAir"] = state["flying"] = True
        state["velocity"] = {"x": 0.0, "y": 0.0, "z": 0.0}


def probe_snapshot(state: dict) -> dict:
    update_vertical_locomotion(state)
    if "stale-sequence" not in failures() or state["sampleSequence"] == 0:
        state["sampleSequence"] += 1
    markers = (FIXTURE_MARKERS[:-1] if "missing-markers" in failures()
               else FIXTURE_MARKERS)
    above_floor = state["position"]["y"] >= -0.05
    spawn_observed = ((state["position"]["x"] ** 2
                       + (state["position"]["z"] - 4.0) ** 2) <= 1.0)
    # Mirrors the in-client probe: validation latches once the fixture spawn is
    # ready and remains true while later behavior modules move the avatar.
    spawn_validated = (state["sceneReady"] and len(markers) == len(FIXTURE_MARKERS)
                       and "floor-fall-through" not in failures())
    save(state)
    return {
        "schemaVersion": 2,
        "sampleEpochMs": int(time.time() * 1000),
        "sampleSequence": state["sampleSequence"],
        "build": {"platform": "Mock", "version": "device-contract",
                  "date": "1970-01-01"},
        "application": {"running": state["running"], "foreground": state["foreground"]},
        "input": {"dominantHand": "right", "advancedMovementControls": True},
        "scene": {
            "url": state["sceneUrl"],
            "ready": state["sceneReady"],
            "entityCount": len(FIXTURE_MARKERS) if state["sceneReady"] else 0,
            "fixtureMarkerCount": len(markers) if state["sceneReady"] else 0,
            "fixtureMarkers": markers if state["sceneReady"] else [],
            "floorTopY": 0.0 if state["sceneReady"] else None,
            "avatarAboveFloor": above_floor,
            "spawnLocationObserved": spawn_observed,
            "spawnValidated": spawn_validated,
            "collisionWall": COLLISION_WALL if state["sceneReady"] else None,
        },
        "avatar": {
            "position": state["position"],
            "velocity": state["velocity"],
            "bodyYawDegrees": state["bodyYawDegrees"],
            "inAir": state["inAir"],
            "flying": state["flying"],
            "flyingEnabled": state["flyingEnabled"],
        },
        "view": {"orientation": state["orientation"]},
        "tablet": {"open": state["tablet"], "home": state["tablet"],
                   "toolbarMode": False},
    }


def invoke(operation: str, arguments: dict) -> dict:
    validate_operation_arguments(operation, arguments)
    state = load()
    if operation == "app.launch":
        state["running"] = state["foreground"] = True
        state["launchCount"] += 1
        result = {"launched": True}
    elif operation == "app.stop":
        state["running"] = state["foreground"] = False
        result = {"stopped": True}
    elif operation == "app.process":
        state["processObservationCount"] += 1
        identity_suffix = (f"-{state['processObservationCount']}"
                           if "process-change" in failures() else "")
        save(state)
        return {"running": state["running"],
                "identity": (f"mock-e2e-process-{state['launchCount']}{identity_suffix}"
                             if state["running"] else None)}
    elif operation == "app.foreground":
        return {"foreground": state["foreground"]}
    elif operation == "scene.load":
        reset_scene(state, arguments["url"])
        state["sceneLoadCount"] += 1
        result = {"requested": True}
    elif operation == "input.look":
        scale = 2.0 if "small-look" in failures() else 120.0
        state["orientation"]["y"] += float(arguments["horizontal"]) * scale
        state["orientation"]["x"] += float(arguments["vertical"]) * scale
        result = {"performed": True}
    elif operation == "input.move":
        apply_move(state, arguments["direction"], float(arguments["durationSeconds"]))
        result = {"performed": True}
    elif operation == "input.jump":
        state["locomotion"] = "jump"
        state["locomotionSamples"] = 0
        result = {"performed": True}
    elif operation == "input.fly":
        state["locomotion"] = "fly"
        state["locomotionSamples"] = 0
        result = {"performed": True}
    elif operation == "tablet.open":
        if "tablet-transition" not in failures():
            state["tablet"] = True
        result = {"performed": True}
    elif operation == "tablet.close":
        if "tablet-transition" not in failures():
            state["tablet"] = False
        result = {"performed": True}
    elif operation == "probe.snapshot":
        return probe_snapshot(state)
    elif operation == "accessibility.snapshot":
        identifier = "OverteTabletClose" if state["tablet"] else "OverteTabletOpen"
        return {"source": f'<App><Button name="{identifier}" /></App>', "artifact": None}
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
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
