#!/usr/bin/env python3
"""Deterministic virtual adapter used to prove the complete E2E stack device-free."""

from __future__ import annotations

import argparse
import copy
import io
import json
import math
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from contracts import TABLET_CONTRACT_VERSION, validate_operation_arguments


CAPABILITIES = sorted([
    "accessibility.snapshot", "app.foreground", "app.launch", "app.process", "app.stop",
    "asset.load", "input.fly", "input.jump", "input.look", "input.move",
    "navigation.enter-domain", "probe.snapshot", "scene.load", "sound.play",
    "tablet.activate", "tablet.close", "tablet.open", "tablet.snapshot",
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
        "running": False, "foreground": False, "sceneUrl": "", "sceneReady": False,
        "launchCount": 0, "sceneLoadCount": 0, "domainEnterCount": 0,
        "domainConnected": False, "domainHost": "", "domainId": "",
        "position": {"x": 0.0, "y": 1.0, "z": 4.0},
        "velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
        "bodyYawDegrees": 0.0,
        "groundY": 1.0, "inAir": False, "flying": False, "flyingEnabled": True,
        "locomotion": None, "locomotionSamples": 0,
        "orientation": {"x": 0.0, "y": 0.0, "z": 0.0}, "tablet": False,
        "tabletScreen": "tablet.home",
        "processRevision": 0, "asset": None,
        "sampleSequence": 0, "sampleEpochMs": 0,
        "sound": {
            "commandId": "", "url": "", "commandObserved": False,
            "resourceReady": False, "durationSeconds": 0.0, "format": "unknown",
            "injectorCreated": False, "started": False, "playing": False,
            "finished": False, "finishReason": "none",
            "playbackStartEpochMs": 0, "playbackEndEpochMs": 0,
        },
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
        "domainConnected": False,
        "domainHost": "",
        "domainId": "",
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


def request_sound_command(arguments: dict) -> None:
    payload = json.dumps({
        "schemaVersion": 1, "commandId": arguments.get("commandId"),
        "action": "play", "soundUrl": arguments.get("url"),
    }).encode("utf-8")
    request = Request(str(arguments.get("commandUrl", "")), data=payload,
                      headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=2) as response:
        if response.status != 200:
            raise RuntimeError("fixture rejected mock sound command")


def begin_sound(state: dict, arguments: dict) -> dict:
    command_id = arguments["commandId"]
    url = arguments["url"]
    request_sound_command(arguments)
    sound = {
        "commandId": command_id, "url": url, "commandObserved": True,
        "resourceReady": False, "durationSeconds": 0.0, "format": "wav",
        "injectorCreated": False, "started": False, "playing": False,
        "finished": False, "finishReason": "none",
        "playbackStartEpochMs": 0, "playbackEndEpochMs": 0,
    }
    state["sound"] = sound
    failure = os.environ.get("OVERTE_MOCK_SOUND_FAILURE", "")
    try:
        with urlopen(url, timeout=2) as response:
            encoded = response.read()
    except (HTTPError, URLError, OSError):
        return {"requested": True, "commandId": command_id}
    if failure == "never-resource":
        return {"requested": True, "commandId": command_id}
    try:
        with wave.open(io.BytesIO(encoded), "rb") as source:
            if (source.getsampwidth() != 2 or source.getnchannels() not in {1, 2, 4}
                    or source.getframerate() <= 0 or source.getnframes() <= 0):
                return {"requested": True, "commandId": command_id}
            duration = source.getnframes() / source.getframerate()
    except (EOFError, wave.Error):
        return {"requested": True, "commandId": command_id}
    sound["resourceReady"] = True
    sound["durationSeconds"] = duration
    if failure == "injector-no-start":
        return {"requested": True, "commandId": command_id}
    now = int(time.time() * 1000)
    sound["injectorCreated"] = True
    sound["started"] = True
    sound["playbackStartEpochMs"] = now
    sound["playbackEndEpochMs"] = now + round(duration * 1000)
    if failure == "early-end":
        sound["playbackEndEpochMs"] = now
    return {"requested": True, "commandId": command_id}


def observed_sound(state: dict) -> dict:
    sound = state["sound"]
    if sound["started"] and not sound["finished"]:
        now = int(time.time() * 1000)
        if now >= sound["playbackEndEpochMs"]:
            sound["playing"] = False
            sound["finished"] = True
            sound["finishReason"] = "natural"
        else:
            sound["playing"] = True
    return {key: sound[key] for key in (
        "commandId", "url", "commandObserved", "resourceReady", "durationSeconds",
        "format", "injectorCreated", "started", "playing", "finished", "finishReason",
    )}


def tablet_profile() -> str:
    value = os.environ.get("OVERTE_MOCK_TABLET_UI_PROFILE", "flat")
    if value not in {"flat", "vr"}:
        raise RuntimeError("mock tablet UI profile must be flat or vr")
    return value


def tablet_controls(screen_id: str, profile: str) -> list[str]:
    controls = {
        "tablet.home": ["app.settings", "nav.close"],
        "settings.home": [
            "nav.close", "nav.home", "settings.audio", "settings.general",
            "settings.graphics", "settings.security",
        ],
        "settings.general": ["nav.back", "nav.close", "nav.home"],
        "settings.graphics": ["nav.back", "nav.close", "nav.home"],
        "settings.audio": ["nav.back", "nav.close", "nav.home"],
        "settings.controllers": ["nav.back", "nav.close", "nav.home"],
        "settings.security": ["nav.back", "nav.close", "nav.home"],
    }[screen_id]
    if profile == "vr":
        if screen_id == "settings.home":
            controls.append("settings.controllers")
        elif screen_id == "settings.general":
            controls.append("settings.hmd-preferences")
        elif screen_id == "settings.graphics":
            controls.append("settings.vr-render-resolution")
    return sorted(controls)


def observed_tablet_ui(state: dict) -> dict:
    if os.environ.get("OVERTE_MOCK_TABLET_INFRASTRUCTURE_FAILURE") == "1":
        raise RuntimeError("mock semantic UI transport is unavailable")
    screen_id = state.get("tabletScreen", "tablet.home")
    controls = tablet_controls(screen_id, tablet_profile())
    mutation = os.environ.get("OVERTE_MOCK_TABLET_MUTATION", "")
    changes = {
        "missing-required": ("settings.home", "settings.audio", False),
        "show-hmd": ("settings.general", "settings.hmd-preferences", True),
        "show-controllers": ("settings.home", "settings.controllers", True),
        "show-vr-render-resolution": (
            "settings.graphics", "settings.vr-render-resolution", True),
        "missing-hmd": ("settings.general", "settings.hmd-preferences", False),
        "missing-vr-render-resolution": (
            "settings.graphics", "settings.vr-render-resolution", False),
    }
    if mutation in changes:
        target_screen, control_id, add = changes[mutation]
        if screen_id == target_screen:
            if add and control_id not in controls:
                controls.append(control_id)
            elif not add and control_id in controls:
                controls.remove(control_id)
            controls.sort()
    snapshot = {
        "contractVersion": TABLET_CONTRACT_VERSION,
        "schemaVersion": 1,
        "screenId": screen_id,
        "ready": state["tablet"] and not (
            mutation == "not-ready" and screen_id == "settings.general"),
        "visibleControlIds": controls,
        "selectedControlIds": [],
    }
    if mutation == "malformed":
        snapshot.pop("ready")
    elif mutation == "duplicate-ids":
        snapshot["visibleControlIds"].append(snapshot["visibleControlIds"][0])
    elif mutation == "unsorted-ids":
        snapshot["visibleControlIds"].reverse()
    elif mutation == "unknown-id":
        snapshot["visibleControlIds"].append("settings.unknown")
    elif mutation == "unknown-version":
        snapshot["contractVersion"] = 99
    elif mutation == "unknown-schema-version":
        snapshot["schemaVersion"] = 99
    return snapshot


def activate_tablet_control(state: dict, control_id: str) -> None:
    if not state["tablet"]:
        raise RuntimeError("semantic tablet activation requires an open tablet")
    if os.environ.get("OVERTE_MOCK_TABLET_MUTATION") == "action-no-transition":
        return
    screen_id = state.get("tabletScreen", "tablet.home")
    visible = tablet_controls(screen_id, tablet_profile())
    if control_id not in visible:
        raise RuntimeError("semantic tablet control is not visible")
    if control_id == "app.settings":
        state["tabletScreen"] = (
            "settings.security"
            if os.environ.get("OVERTE_MOCK_TABLET_MUTATION") == "wrong-screen"
            else "settings.home")
    elif control_id in {"settings.audio", "settings.controllers", "settings.general",
                        "settings.graphics", "settings.security"}:
        state["tabletScreen"] = control_id
    elif control_id == "nav.back":
        state["tabletScreen"] = "settings.home"
    elif control_id == "nav.home":
        state["tabletScreen"] = "tablet.home"
    elif control_id == "nav.close":
        state["tablet"] = False
        state["tabletScreen"] = "tablet.home"
    else:
        raise RuntimeError("semantic tablet control is not actionable")
    if os.environ.get("OVERTE_MOCK_TABLET_MUTATION") == "process-restart":
        state["processRevision"] = state.get("processRevision", 0) + 1


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
        identity = "mock-e2e-process"
        if state["launchCount"] > 1:
            identity += f"-{state['launchCount']}"
        if state.get("processRevision", 0):
            identity += f"-{state['processRevision']}"
        if (os.environ.get("OVERTE_MOCK_SOUND_FAILURE") == "process-restart"
                and state.get("sound", {}).get("started")):
            identity = "mock-e2e-process-restarted"
        return {"running": state["running"],
                "identity": identity if state["running"] else None}
    elif operation == "app.foreground":
        return {"foreground": state["foreground"]}
    elif operation == "scene.load":
        reset_scene(state, arguments["url"])
        state["sceneLoadCount"] += 1
        result = {"requested": True}
    elif operation == "navigation.enter-domain":
        requested = arguments.get("url", "")
        parsed = urlsplit(requested)
        try:
            port = parsed.port
        except ValueError as error:
            raise RuntimeError("mock domain navigation has an invalid port") from error
        if parsed.scheme != "hifi" or not parsed.hostname or port is None:
            raise RuntimeError("mock domain navigation requires an explicit hifi URL")
        state["sceneUrl"] = requested
        state["sceneReady"] = False
        state["domainConnected"] = True
        state["domainHost"] = parsed.hostname
        state["domainId"] = os.environ.get(
            "OVERTE_MOCK_E2E_DOMAIN_ID", "11111111-2222-4333-8444-555555555555")
        state["domainEnterCount"] += 1
        result = {"requested": True}
    elif operation == "asset.load":
        asset_id = arguments["assetId"]
        url = arguments["url"]
        entity_name = arguments["entityName"]
        state["asset"] = {
            "assetId": asset_id,
            "resource": {"url": url, "state": "loading"},
            "entity": {
                "id": "{11111111-2222-4333-8444-555555555555}",
                "name": entity_name, "type": "Image", "imageURL": url,
                "naturalDimensions": {"x": 0.1, "y": 0.1, "z": 0.01},
            },
        }
        payload = None
        if os.environ.get("OVERTE_MOCK_ASSET_SKIP_HTTP") != "1":
            with urlopen(url, timeout=5) as response:
                payload = response.read()
            if len(payload) < 24 or payload[:8] != b"\x89PNG\r\n\x1a\n":
                raise RuntimeError("mock asset is not a PNG")
        if os.environ.get("OVERTE_MOCK_ASSET_NEVER_FINISH") != "1":
            if payload is None:
                width, height = 3, 1
            else:
                width = int.from_bytes(payload[16:20], "big")
                height = int.from_bytes(payload[20:24], "big")
            state["asset"]["resource"]["state"] = "finished"
            state["asset"]["entity"]["naturalDimensions"] = {
                "x": 1.0 if width >= height else width / height,
                "y": height / width if width >= height else 1.0,
                "z": 0.01,
            }
        if os.environ.get("OVERTE_MOCK_ASSET_RESTART") == "1":
            state["processRevision"] = state.get("processRevision", 0) + 1
        result = {"requested": True}
    elif operation == "sound.play":
        result = begin_sound(state, arguments)
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
            state["tabletScreen"] = "tablet.home"
        result = {"performed": True}
    elif operation == "tablet.close":
        if "tablet-transition" not in failures():
            state["tablet"] = False
            state["tabletScreen"] = "tablet.home"
        result = {"performed": True}
    elif operation == "tablet.snapshot":
        return observed_tablet_ui(state)
    elif operation == "tablet.activate":
        activate_tablet_control(state, arguments["controlId"])
        result = {"performed": True}
    elif operation == "probe.snapshot":
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
        domain_markers = [
            "OVERTE_E2E_DOMAIN_EAST", "OVERTE_E2E_DOMAIN_FLOOR",
            "OVERTE_E2E_DOMAIN_NORTH", "OVERTE_E2E_DOMAIN_ORIGIN",
        ]
        if os.environ.get("OVERTE_MOCK_E2E_DOMAIN_MARKERS_JSON"):
            domain_markers = json.loads(os.environ["OVERTE_MOCK_E2E_DOMAIN_MARKERS_JSON"])
        if not state["domainConnected"]:
            domain_markers = []
        failure = os.environ.get("OVERTE_MOCK_SOUND_FAILURE", "")
        sound_active = bool(state.get("sound", {}).get("commandObserved"))
        fixture_markers = (FIXTURE_MARKERS[:-1] if "missing-markers" in failures()
                           else FIXTURE_MARKERS)
        stale_common = "stale-sequence" in failures() and state["sampleSequence"] > 0
        if not (failure == "stale-probe" and sound_active) and not stale_common:
            state["sampleSequence"] += 1
        now = int(time.time() * 1000)
        if failure == "inconsistent-probe" and sound_active:
            state["sampleEpochMs"] = max(1, state["sampleEpochMs"] - 1)
        elif not (failure == "stale-probe" and sound_active) and not stale_common:
            state["sampleEpochMs"] = max(now, state["sampleEpochMs"] + 1)
        snapshot = {
            "schemaVersion": 2,
            "sampleEpochMs": state["sampleEpochMs"],
            "sampleSequence": state["sampleSequence"],
            "build": {"platform": "Mock", "version": "device-contract",
                      "date": "1970-01-01"},
            "application": {"running": state["running"], "foreground": state["foreground"]},
            "domain": {
                "connected": state["domainConnected"],
                "hostname": state["domainHost"],
                "id": state["domainId"],
                "protocol": "hifi" if state["domainConnected"] else "file",
                "serverless": not state["domainConnected"],
            },
            "input": {"dominantHand": "right", "advancedMovementControls": True},
            "scene": {"url": state["sceneUrl"], "ready": state["sceneReady"],
                      "entityCount": (4 if state["domainConnected"] else
                                      len(FIXTURE_MARKERS) if state["sceneReady"] else 0),
                      "fixtureMarkerCount": (0 if state["domainConnected"] else
                                             len(fixture_markers) if state["sceneReady"] else 0),
                      "fixtureMarkers": ([] if state["domainConnected"] or not state["sceneReady"]
                                         else fixture_markers),
                      "domainMarkerCount": len(domain_markers),
                      "domainMarkers": domain_markers,
                      "floorTopY": (0.0 if state["sceneReady"]
                                    and not state["domainConnected"] else None),
                      "avatarAboveFloor": state["position"]["y"] >= -0.05,
                      "spawnLocationObserved": (state["position"]["x"] ** 2
                                                + (state["position"]["z"] - 4.0) ** 2 <= 1.0),
                      "spawnValidated": (state["sceneReady"]
                                         and "floor-fall-through" not in failures()
                                         and len(fixture_markers) == len(FIXTURE_MARKERS)),
                      "collisionWall": (COLLISION_WALL if state["sceneReady"]
                                        and not state["domainConnected"] else None)},
            "avatar": {"position": state["position"], "velocity": state["velocity"],
                       "bodyYawDegrees": state["bodyYawDegrees"], "inAir": state["inAir"],
                       "flying": state["flying"], "flyingEnabled": state["flyingEnabled"]},
            "view": {"orientation": state["orientation"]},
            "tablet": {"open": state["tablet"],
                       "home": (state["tablet"]
                                and state.get("tabletScreen") == "tablet.home"),
                       "toolbarMode": False},
            "asset": copy.deepcopy(state.get("asset")),
            "sound": observed_sound(state),
        }
        save(state)
        if snapshot["asset"] is not None:
            if os.environ.get("OVERTE_MOCK_ASSET_WRONG_ID") == "1":
                snapshot["asset"]["assetId"] += "-wrong"
            if os.environ.get("OVERTE_MOCK_ASSET_WRONG_URL") == "1":
                wrong_url = snapshot["asset"]["resource"]["url"] + "-wrong"
                snapshot["asset"]["resource"]["url"] = wrong_url
                snapshot["asset"]["entity"]["imageURL"] = wrong_url
            if os.environ.get("OVERTE_MOCK_ASSET_INCOMPLETE_PROBE") == "1":
                snapshot["asset"].pop("entity", None)
        return snapshot
    elif operation == "accessibility.snapshot":
        identifier = "OverteTabletClose" if state["tablet"] else "OverteTabletOpen"
        return {"source": f'<App><Button name="{identifier}" /></App>', "artifact": None}
    else:
        raise RuntimeError(f"unsupported operation: {operation}")
    save(state)
    return result


def main() -> int:
    args = cli()
    if (os.environ.get("OVERTE_MOCK_ASSERT_POLICY_ISOLATED") == "1"
            and "OVERTE_E2E_TABLET_POLICY" in os.environ):
        raise RuntimeError("adapter received product policy context")
    if args.action == "discover":
        capabilities = [item for item in CAPABILITIES
                        if item != os.environ.get("OVERTE_MOCK_MISSING_CAPABILITY")]
        emit([{"selector": "mock-e2e-target", "displayName": "Virtual E2E Contract",
               "platform": "mock", "physical": False, "capabilities": capabilities}])
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
