#!/usr/bin/env python3
"""Device-free, fail-closed model of test-only Pico controller injection."""

from __future__ import annotations

from copy import deepcopy
import math
import re
from typing import Any


MAX_COMMANDS = 32
NONCE_PATTERN = re.compile(r"^[0-9a-f]{32,128}$")
IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
ACTION_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
BUTTON_CONTROLS = frozenset({"menu", "primary", "secondary", "thumbstick", "trigger"})
SCALAR_OPERATIONS = frozenset({"controller.grip", "controller.trigger"})
HANDS = frozenset({"left", "right"})
INTER_COMMAND_GAP_MS = 100
NEUTRAL_HOLD_MS = 100


class ControllerContractError(ValueError):
    """A controller command or target binding failed a safety constraint."""


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ControllerContractError(f"{name} must be an object")
    return value


def _exact_keys(value: dict[str, Any], required: set[str], optional: set[str],
                name: str) -> None:
    missing = sorted(required - value.keys())
    unknown = sorted(value.keys() - required - optional)
    if missing:
        raise ControllerContractError(f"{name} is missing: {', '.join(missing)}")
    if unknown:
        raise ControllerContractError(f"{name} has unknown fields: {', '.join(unknown)}")


def _string(value: Any, name: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ControllerContractError(f"{name} has an invalid format")
    return value


def _integer(value: Any, name: str, minimum: int, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ControllerContractError(f"{name} must be an integer >= {minimum}")
    if maximum is not None and value > maximum:
        raise ControllerContractError(f"{name} must be <= {maximum}")
    return value


def _number(value: Any, name: str, minimum: float, maximum: float) -> float:
    if (isinstance(value, bool) or not isinstance(value, (int, float)) or
            not math.isfinite(value) or not minimum <= value <= maximum):
        raise ControllerContractError(
            f"{name} must be finite and between {minimum} and {maximum}")
    return float(value)


def validate_profile(raw: Any) -> dict[str, Any]:
    profile = _object(raw, "profile")
    _exact_keys(profile, {
        "schemaVersion", "profileId", "prototypeOnly", "interactionProfile",
        "poseBaseReferenceSpace", "controls", "viewInjection",
    }, set(), "profile")
    if profile["schemaVersion"] != 1 or profile["prototypeOnly"] is not True:
        raise ControllerContractError("profile must be prototype schema version 1")
    _string(profile["profileId"], "profile.profileId", IDENTIFIER_PATTERN)
    interaction_profile = profile["interactionProfile"]
    if (not isinstance(interaction_profile, str) or
            not interaction_profile.startswith("/interaction_profiles/")):
        raise ControllerContractError("profile interaction profile is invalid")
    if profile["poseBaseReferenceSpace"] != "stage":
        raise ControllerContractError("controller pose injection is restricted to STAGE space")
    view = _object(profile["viewInjection"], "profile.viewInjection")
    _exact_keys(view, {"mode", "maxYawDegrees", "maxPitchDegrees"}, set(),
                "profile.viewInjection")
    if view["mode"] != "view-reference-space-offset":
        raise ControllerContractError("unsupported view injection mode")
    _number(view["maxYawDegrees"], "profile.viewInjection.maxYawDegrees", 1.0, 90.0)
    _number(view["maxPitchDegrees"], "profile.viewInjection.maxPitchDegrees", 1.0, 60.0)

    controls = _object(profile["controls"], "profile.controls")
    _exact_keys(controls, {"buttons", "scalars", "thumbsticks", "poses"}, set(),
                "profile.controls")
    expected_keys = {
        "buttons": {
            "left.menu", "left.primary", "left.secondary", "left.thumbstick",
            "left.trigger", "right.primary", "right.secondary", "right.thumbstick",
            "right.trigger",
        },
        "scalars": {"left.grip", "left.trigger", "right.grip", "right.trigger"},
        "thumbsticks": {"left", "right"},
        "poses": {"left.grip", "right.grip"},
    }
    all_actions: set[str] = set()
    for group, keys in expected_keys.items():
        bindings = _object(controls[group], f"profile.controls.{group}")
        if set(bindings) != keys:
            raise ControllerContractError(
                f"profile.controls.{group} must contain the exact Pico 4 allowlist")
        for action in bindings.values():
            all_actions.add(_string(action, f"profile.controls.{group} action", ACTION_PATTERN))
    if len(all_actions) != sum(len(keys) for keys in expected_keys.values()):
        raise ControllerContractError("controller actions must not be aliased")
    return profile


def validate_envelope(raw: Any, profile_raw: Any) -> dict[str, Any]:
    profile = validate_profile(profile_raw)
    envelope = _object(raw, "envelope")
    _exact_keys(envelope, {"schemaVersion", "sessionNonce", "sequence", "commands"},
                set(), "envelope")
    if envelope["schemaVersion"] != 1:
        raise ControllerContractError("unsupported envelope schemaVersion")
    _string(envelope["sessionNonce"], "envelope.sessionNonce", NONCE_PATTERN)
    _integer(envelope["sequence"], "envelope.sequence", 1)
    commands = envelope["commands"]
    if not isinstance(commands, list) or not 1 <= len(commands) <= MAX_COMMANDS:
        raise ControllerContractError(
            f"envelope.commands must contain 1 through {MAX_COMMANDS} commands")
    identifiers: set[str] = set()
    for index, raw_command in enumerate(commands):
        command = _object(raw_command, f"commands[{index}]")
        _exact_keys(command, {"id", "operation", "arguments"}, set(),
                    f"commands[{index}]")
        identifier = _string(command["id"], f"commands[{index}].id", IDENTIFIER_PATTERN)
        if identifier in identifiers:
            raise ControllerContractError("command ids must be unique")
        identifiers.add(identifier)
        operation = command["operation"]
        arguments = _object(command["arguments"], f"commands[{index}].arguments")
        if operation == "controller.button":
            hand = arguments.get("hand")
            if hand not in HANDS:
                raise ControllerContractError("controller hand must be left or right")
            _exact_keys(arguments, {"hand", "control"}, {"holdMilliseconds"},
                        f"commands[{index}].arguments")
            control = arguments["control"]
            if control not in BUTTON_CONTROLS:
                raise ControllerContractError("unsupported controller button")
            key = f"{hand}.{control}"
            if key not in profile["controls"]["buttons"]:
                raise ControllerContractError(f"button {key} is not available on Pico 4")
            _integer(arguments.get("holdMilliseconds", 120), "button holdMilliseconds", 40, 500)
        elif operation in SCALAR_OPERATIONS:
            hand = arguments.get("hand")
            if hand not in HANDS:
                raise ControllerContractError("controller hand must be left or right")
            _exact_keys(arguments, {"hand", "value"}, {"holdMilliseconds"},
                        f"commands[{index}].arguments")
            _number(arguments["value"], f"{operation} value", 0.05, 1.0)
            _integer(arguments.get("holdMilliseconds", 250),
                     f"{operation} holdMilliseconds", 100, 3000)
        elif operation == "controller.thumbstick":
            hand = arguments.get("hand")
            if hand not in HANDS:
                raise ControllerContractError("controller hand must be left or right")
            _exact_keys(arguments, {"hand", "x", "y"}, {"holdMilliseconds"},
                        f"commands[{index}].arguments")
            x = _number(arguments["x"], "thumbstick x", -1.0, 1.0)
            y = _number(arguments["y"], "thumbstick y", -1.0, 1.0)
            if abs(x) < 0.01 and abs(y) < 0.01:
                raise ControllerContractError("thumbstick command must be non-neutral")
            _integer(arguments.get("holdMilliseconds", 250),
                     "thumbstick holdMilliseconds", 100, 3000)
        elif operation == "controller.pose":
            hand = arguments.get("hand")
            if hand not in HANDS:
                raise ControllerContractError("controller hand must be left or right")
            _exact_keys(arguments, {"hand", "positionMeters", "orientation"},
                        {"holdMilliseconds"}, f"commands[{index}].arguments")
            position = arguments["positionMeters"]
            orientation = arguments["orientation"]
            if not isinstance(position, list) or len(position) != 3:
                raise ControllerContractError("pose positionMeters must have three values")
            if not isinstance(orientation, list) or len(orientation) != 4:
                raise ControllerContractError("pose orientation must have four values")
            for value in position:
                _number(value, "pose position", -3.0, 3.0)
            checked_orientation = [_number(value, "pose orientation", -1.0, 1.0)
                                   for value in orientation]
            # Validate without mutating the caller's envelope. Compilation
            # performs its own type-preserving copy after this gate.
            norm = math.sqrt(sum(value * value for value in checked_orientation))
            if abs(norm - 1.0) > 1e-4:
                raise ControllerContractError("pose orientation must be a normalized quaternion")
            _integer(arguments.get("holdMilliseconds", 500),
                     "pose holdMilliseconds", 100, 3000)
        elif operation == "input.look":
            _exact_keys(arguments, {"horizontal"}, {"vertical", "durationSeconds"},
                        f"commands[{index}].arguments")
            horizontal = _number(arguments["horizontal"], "look horizontal", -0.45, 0.45)
            vertical = _number(arguments.get("vertical", 0.0), "look vertical", -0.45, 0.45)
            if abs(horizontal) < 0.01 and abs(vertical) < 0.01:
                raise ControllerContractError("look command must be non-neutral")
            _number(arguments.get("durationSeconds", 0.35),
                    "look durationSeconds", 0.1, 8.0)
        elif operation == "input.move":
            _exact_keys(arguments, {"direction", "durationSeconds"}, {"strength"},
                        f"commands[{index}].arguments")
            if arguments["direction"] not in {"backward", "forward"}:
                raise ControllerContractError("Pico common movement supports forward/backward only")
            _number(arguments["durationSeconds"], "move durationSeconds", 0.1, 8.0)
            _number(arguments.get("strength", 0.8), "move strength", 0.2, 1.0)
        elif operation in {"tablet.close", "tablet.open"}:
            _exact_keys(arguments, set(), {"holdMilliseconds"},
                        f"commands[{index}].arguments")
            _integer(arguments.get("holdMilliseconds", 120),
                     "tablet holdMilliseconds", 100, 8000)
        else:
            raise ControllerContractError(f"unsupported controller operation: {operation}")
    return envelope


def _neutral(profile: dict[str, Any]) -> dict[str, Any]:
    controls = profile["controls"]
    return {
        "boolean": {action: False for action in controls["buttons"].values()},
        "float": {action: 0.0 for action in controls["scalars"].values()},
        "vector2f": {action: [0.0, 0.0]
                     for action in controls["thumbsticks"].values()},
        "pose": {},
        "viewOffset": {
            "active": False,
            "orientation": [0.0, 0.0, 0.0, 1.0],
            "pitchDegrees": 0.0,
            "yawDegrees": 0.0,
        },
    }


def compile_envelope(envelope_raw: Any, profile_raw: Any) -> dict[str, Any]:
    """Compile physical-control commands to bounded OpenXR query snapshots."""
    profile = validate_profile(profile_raw)
    envelope = validate_envelope(deepcopy(envelope_raw), profile)
    neutral = _neutral(profile)
    events: list[dict[str, Any]] = [{"atMs": 0, "state": deepcopy(neutral)}]
    results: list[dict[str, Any]] = []
    required = {"xrCreateAction", "xrSyncActions"}
    cursor = NEUTRAL_HOLD_MS

    for command in envelope["commands"]:
        operation = command["operation"]
        arguments = command["arguments"]
        state = deepcopy(neutral)
        if operation == "controller.button":
            hand = arguments["hand"]
            duration = int(arguments.get("holdMilliseconds", 120))
            key = f"{hand}.{arguments['control']}"
            action = profile["controls"]["buttons"][key]
            state["boolean"][action] = True
            required.add("xrGetActionStateBoolean")
        elif operation in SCALAR_OPERATIONS:
            hand = arguments["hand"]
            duration = int(arguments.get("holdMilliseconds", 250))
            control = operation.removeprefix("controller.")
            action = profile["controls"]["scalars"][f"{hand}.{control}"]
            state["float"][action] = float(arguments["value"])
            required.add("xrGetActionStateFloat")
        elif operation == "controller.thumbstick":
            hand = arguments["hand"]
            duration = int(arguments.get("holdMilliseconds", 250))
            action = profile["controls"]["thumbsticks"][hand]
            state["vector2f"][action] = [float(arguments["x"]), float(arguments["y"])]
            required.add("xrGetActionStateVector2f")
        elif operation == "controller.pose":
            hand = arguments["hand"]
            duration = int(arguments.get("holdMilliseconds", 500))
            action = profile["controls"]["poses"][f"{hand}.grip"]
            state["pose"][action] = {
                "active": True,
                "baseReferenceSpace": profile["poseBaseReferenceSpace"],
                "locationFlags": [
                    "orientationTracked", "orientationValid",
                    "positionTracked", "positionValid",
                ],
                "orientation": [float(value) for value in arguments["orientation"]],
                "positionMeters": [float(value) for value in arguments["positionMeters"]],
            }
            required.update({
                "xrCreateActionSpace", "xrCreateReferenceSpace",
                "xrGetActionStatePose", "xrLocateSpace",
            })
        elif operation == "input.look":
            duration = round(float(arguments.get("durationSeconds", 0.35)) * 1000)
            action = "view-reference-space-offset"
            yaw = (float(arguments["horizontal"]) / 0.45 *
                   float(profile["viewInjection"]["maxYawDegrees"]))
            pitch = (float(arguments.get("vertical", 0.0)) / 0.45 *
                     float(profile["viewInjection"]["maxPitchDegrees"]))
            yaw_half = math.radians(yaw) / 2.0
            pitch_half = math.radians(pitch) / 2.0
            sy, cy = math.sin(yaw_half), math.cos(yaw_half)
            sp, cp = math.sin(pitch_half), math.cos(pitch_half)
            state["viewOffset"] = {
                "active": True,
                "orientation": [cy * sp, sy * cp, -sy * sp, cy * cp],
                "pitchDegrees": pitch,
                "yawDegrees": yaw,
            }
            required.update({"xrCreateReferenceSpace", "xrLocateSpace", "xrLocateViews"})
        elif operation == "input.move":
            duration = round(float(arguments["durationSeconds"]) * 1000)
            action = profile["controls"]["thumbsticks"]["left"]
            strength = float(arguments.get("strength", 0.8))
            runtime_y = strength if arguments["direction"] == "forward" else -strength
            state["vector2f"][action] = [0.0, runtime_y]
            required.add("xrGetActionStateVector2f")
        else:
            duration = int(arguments.get("holdMilliseconds", 120))
            action = profile["controls"]["buttons"]["left.secondary"]
            state["boolean"][action] = True
            required.add("xrGetActionStateBoolean")
        start = cursor
        release = start + duration
        events.append({"atMs": start, "state": state})
        events.append({"atMs": release, "state": deepcopy(neutral)})
        if operation == "input.look":
            input_domain = "head-pose"
            verification = "probe.view.orientation"
        elif operation == "input.move":
            input_domain = "controller-action"
            verification = "probe.avatar.position"
        elif operation in {"tablet.open", "tablet.close"}:
            input_domain = "controller-action"
            verification = "probe.tablet.open"
        elif operation == "controller.pose":
            input_domain = "controller-pose"
            verification = "probe.controller.poses"
        else:
            input_domain = "controller-action"
            verification = "probe.controllerState"
        results.append({
            "commandId": command["id"],
            "operation": operation,
            "actionName": action,
            "inputDomain": input_domain,
            "activeWindow": {"startMs": start, "endMs": release},
            "verification": verification,
        })
        cursor = release + INTER_COMMAND_GAP_MS

    watchdog = cursor + NEUTRAL_HOLD_MS
    events.append({"atMs": watchdog, "state": deepcopy(neutral)})
    return {
        "schemaVersion": 1,
        "prototypeOnly": True,
        "profileId": profile["profileId"],
        "sessionNonce": envelope["sessionNonce"],
        "sequence": envelope["sequence"],
        "requiredInterception": sorted(required),
        "events": events,
        "results": results,
        "watchdogDeadlineMs": watchdog,
        "terminalState": "neutral-and-disabled",
    }


class PrototypeOpenXrInputConsumer:
    """Model stable head-pose and controller state between sync boundaries."""

    def __init__(self, compiled: dict[str, Any]) -> None:
        if (not isinstance(compiled, dict) or compiled.get("schemaVersion") != 1 or
                compiled.get("prototypeOnly") is not True or
                compiled.get("terminalState") != "neutral-and-disabled"):
            raise ControllerContractError("compiled stream is not a controller prototype")
        self._events = deepcopy(compiled["events"])
        self._deadline = _integer(compiled["watchdogDeadlineMs"],
                                  "watchdogDeadlineMs", 1)
        self._index = 0
        self._last_sync = -1
        self._state = deepcopy(self._events[0]["state"])
        self._previous = deepcopy(self._state)
        self.enabled = True

    def sync_actions(self, offset_ms: int) -> None:
        offset = _integer(offset_ms, "offset_ms", 0)
        if offset < self._last_sync:
            self.enabled = False
            self._neutralize()
            raise ControllerContractError("sync time moved backwards; consumer disabled")
        self._previous = deepcopy(self._state)
        if not self.enabled or offset >= self._deadline:
            self.enabled = False
            self._neutralize()
            self._last_sync = offset
            return
        while (self._index + 1 < len(self._events) and
               self._events[self._index + 1]["atMs"] <= offset):
            self._index += 1
            self._state = deepcopy(self._events[self._index]["state"])
        self._last_sync = offset

    def _neutralize(self) -> None:
        self._state["boolean"] = {name: False for name in self._state["boolean"]}
        self._state["float"] = {name: 0.0 for name in self._state["float"]}
        self._state["vector2f"] = {name: [0.0, 0.0]
                                    for name in self._state["vector2f"]}
        self._state["pose"] = {}
        self._state["viewOffset"] = {
            "active": False,
            "orientation": [0.0, 0.0, 0.0, 1.0],
            "pitchDegrees": 0.0,
            "yawDegrees": 0.0,
        }

    def query(self, action_type: str, action_name: str) -> dict[str, Any] | None:
        if action_type not in {"boolean", "float", "vector2f", "pose"}:
            raise ControllerContractError("unknown action type")
        current = self._state[action_type].get(action_name)
        if current is None:
            return None
        previous = self._previous[action_type].get(action_name)
        return {
            "isActive": self.enabled,
            "currentState": deepcopy(current),
            "changedSinceLastSync": current != previous,
        }


# Compatibility for callers of the initial controller-only prototype name.
# New code should use the semantically complete OpenXR input name above.
PrototypeControllerConsumer = PrototypeOpenXrInputConsumer
