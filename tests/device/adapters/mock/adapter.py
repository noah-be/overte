#!/usr/bin/env python3
"""Deterministic virtual adapter used to prove the complete E2E stack device-free."""

from __future__ import annotations

import argparse
import copy
import io
import json
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from contracts import validate_operation_arguments


CAPABILITIES = sorted([
    "accessibility.snapshot", "app.foreground", "app.launch", "app.process",
    "asset.load", "input.fly", "input.jump", "input.look", "input.move",
    "navigation.enter-domain", "probe.snapshot", "scene.load", "sound.play",
    "tablet.close", "tablet.open",
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
        "launchCount": 0, "sceneLoadCount": 0, "domainEnterCount": 0,
        "domainConnected": False, "domainHost": "", "domainId": "",
        "position": {"x": 0.0, "y": 2.0 if pico else 1.0, "z": 4.0},
        "groundY": 2.0 if pico else 1.0,
        "inAir": False, "flying": False, "flyingEnabled": True,
        "locomotion": None, "locomotionSamples": 0,
        "orientation": {"x": 0.0, "y": 0.0, "z": 0.0}, "tablet": False,
        "picoRouteActive": False, "inputSequence": 0,
        "processRevision": 0, "asset": None,
        "sampleSequence": 0, "sampleEpochMs": 0,
        "soundObservationCount": 0,
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


def invoke(operation: str, arguments: dict) -> dict:
    validate_operation_arguments(operation, arguments)
    state = load()
    if operation == "app.launch":
        state["running"] = state["foreground"] = True
        state["launchCount"] += 1
        result = {"launched": True}
    elif operation == "app.process":
        identity = "mock-e2e-process"
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
        state["sceneUrl"] = arguments.get("url", "")
        state["sceneReady"] = True
        state["domainConnected"] = False
        state["domainHost"] = state["domainId"] = ""
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
        state["inputSequence"] += 1
        state["picoRouteActive"] = False
        state["orientation"]["y"] += 30.0
        result = {"performed": True, "neutralBeforeCommand": False,
                  "sequence": state["inputSequence"]}
        if os.environ.get("OVERTE_PICO_OPENXR_INPUT") == "1":
            result.update({"viewApplied": True, "viewYawDegrees": 25.0,
                           "viewPitchDegrees": 0.0})
    elif operation == "input.move":
        state["inputSequence"] += 1
        state["picoRouteActive"] = True
        state["position"]["z"] -= 1.0
        result = {"performed": True, "neutralBeforeCommand": True,
                  "sequence": state["inputSequence"]}
        if os.environ.get("OVERTE_PICO_OPENXR_INPUT") == "1":
            result.update({"openXrVectorApplied": True,
                           "openXrLeftThumbstickY": 0.4})
    elif operation == "input.jump":
        state["locomotion"] = "jump"
        state["locomotionSamples"] = 0
        result = {"performed": True}
    elif operation == "input.fly":
        state["locomotion"] = "fly"
        state["locomotionSamples"] = 0
        result = {"performed": True}
    elif operation == "tablet.open":
        state["inputSequence"] += 1
        state["tablet"] = True
        result = {"performed": True, "neutralBeforeCommand": True,
                  "sequence": state["inputSequence"]}
        if os.environ.get("OVERTE_PICO_OPENXR_INPUT") == "1":
            result.update({"openXrBooleanApplied": True,
                           "openXrLeftSecondaryApplied": True})
    elif operation == "tablet.close":
        state["inputSequence"] += 1
        state["tablet"] = False
        result = {"performed": True, "neutralBeforeCommand": True,
                  "sequence": state["inputSequence"]}
        if os.environ.get("OVERTE_PICO_OPENXR_INPUT") == "1":
            result.update({"openXrBooleanApplied": True,
                           "openXrLeftSecondaryApplied": True})
    elif operation == "probe.snapshot":
        after = arguments.get("afterSampleSequence")
        if (after is not None and (not isinstance(after, int) or isinstance(after, bool)
                                   or after < 0)):
            raise RuntimeError("afterSampleSequence must be a non-negative integer")
        if state["locomotion"] == "jump":
            state["locomotionSamples"] += 1
            airborne = state["locomotionSamples"] <= 2
            gain = 0.0 if os.environ.get("OVERTE_MOCK_E2E_BAD_JUMP") == "1" else 0.8
            state["position"]["y"] = state["groundY"] + (gain if airborne else 0.0)
            state["inAir"], state["flying"] = airborne, False
            if not airborne:
                state["locomotion"] = None
        elif state["locomotion"] == "fly":
            state["locomotionSamples"] += 1
            gain = 0.0 if os.environ.get("OVERTE_MOCK_E2E_BAD_FLY") == "1" else 1.5
            state["position"]["y"] = state["groundY"] + gain
            state["inAir"] = state["flying"] = True
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
        if sound_active:
            state["soundObservationCount"] = state.get("soundObservationCount", 0) + 1
            if (failure == "end-after-two-active-samples"
                    and state["soundObservationCount"] > 2):
                state["sound"]["playbackEndEpochMs"] = 0
        if not (failure == "stale-probe" and sound_active):
            state["sampleSequence"] += 1
        now = int(time.time() * 1000)
        if failure == "inconsistent-probe" and sound_active:
            state["sampleEpochMs"] = max(1, state["sampleEpochMs"] - 1)
        elif not (failure == "stale-probe" and sound_active):
            state["sampleEpochMs"] = max(now, state["sampleEpochMs"] + 1)
        snapshot = {
            "schemaVersion": 1,
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
            "scene": {"url": state["sceneUrl"], "ready": state["sceneReady"],
                      "entityCount": 4 if state["sceneReady"] or state["domainConnected"] else 0,
                      "domainMarkerCount": len(domain_markers),
                      "domainMarkers": domain_markers},
            "avatar": {"position": state["position"], "inAir": state["inAir"],
                       "flying": state["flying"], "flyingEnabled": state["flyingEnabled"]},
            "view": {"orientation": state["orientation"]},
            "tablet": {"open": state["tablet"], "home": state["tablet"]},
            "asset": copy.deepcopy(state.get("asset")),
            "sound": observed_sound(state),
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
                    # The avatar drive-key API exposes TranslateZ with the
                    # opposite sign from the OpenXR/controller action axes.
                    "rawTranslateZDriveKey": -route_value,
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
