#!/usr/bin/env python3
"""Fail-closed compiler and consumer model for Overte OpenXR E2E input.

This module deliberately has no device transport and cannot activate an OpenXR
layer.  It validates target-neutral commands, compiles them to the state
transitions a future test-only API layer must implement, and models OpenXR's
sync/query behavior for device-free contract tests.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import re
from typing import Any


BUILD_MARKER = "OVERTE_E2E_OPENXR_INPUT_V1"
CHANNEL = "app-private-file"
MAX_COMMANDS = 16
MAX_GRANT_LIFETIME_MS = 5 * 60 * 1000
MAX_CLOCK_SKEW_MS = 5 * 1000
NEUTRAL_HOLD_MS = 100
OBSERVATION_HOLD_MS = 1200
INTER_COMMAND_GAP_MS = 100
NONCE_PATTERN = re.compile(r"^[0-9a-f]{32,128}$")
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
ACTION_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class ContractError(ValueError):
    """An input contract was invalid or failed a safety gate."""


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{name} must be an object")
    return value


def _exact_keys(value: dict[str, Any], required: set[str], optional: set[str],
                name: str) -> None:
    missing = sorted(required - value.keys())
    unknown = sorted(value.keys() - required - optional)
    if missing:
        raise ContractError(f"{name} is missing: {', '.join(missing)}")
    if unknown:
        raise ContractError(f"{name} has unknown fields: {', '.join(unknown)}")


def _integer(value: Any, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ContractError(f"{name} must be an integer >= {minimum}")
    return value


def _number(value: Any, name: str, minimum: float, maximum: float) -> float:
    if (isinstance(value, bool) or not isinstance(value, (int, float)) or
            not math.isfinite(value) or not minimum <= value <= maximum):
        raise ContractError(f"{name} must be finite and between {minimum} and {maximum}")
    return float(value)


def _string(value: Any, name: str, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{name} must be a non-empty string")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise ContractError(f"{name} has an invalid format")
    return value


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def profile_fingerprint(profile: dict[str, Any]) -> str:
    """Return the hash that binds a runtime grant to an exact target profile."""
    validate_profile(profile)
    return hashlib.sha256(_canonical_json(profile)).hexdigest()


def validate_profile(raw: Any) -> dict[str, Any]:
    profile = _object(raw, "profile")
    _exact_keys(profile, {
        "schemaVersion", "profileId", "prototypeOnly", "consumer",
        "interactionProfile", "viewInjection", "actions",
    }, set(), "profile")
    if profile["schemaVersion"] != 1:
        raise ContractError("unsupported profile schemaVersion")
    _string(profile["profileId"], "profile.profileId", IDENTIFIER_PATTERN)
    if profile["prototypeOnly"] is not True:
        raise ContractError("profile.prototypeOnly must be true")
    consumer = _string(profile["consumer"], "profile.consumer")
    if not consumer.startswith("XR_APILAYER_"):
        raise ContractError("profile.consumer must be an OpenXR API layer name")
    interaction = _string(profile["interactionProfile"],
                          "profile.interactionProfile")
    if not interaction.startswith("/interaction_profiles/"):
        raise ContractError("profile.interactionProfile must be an OpenXR path")

    view = _object(profile["viewInjection"], "profile.viewInjection")
    _exact_keys(view, {"mode", "maxYawDegrees", "maxPitchDegrees", "intercepts"},
                set(), "profile.viewInjection")
    if view["mode"] != "reference-space-offset":
        raise ContractError("unsupported view injection mode")
    _number(view["maxYawDegrees"], "profile.viewInjection.maxYawDegrees", 1.0, 90.0)
    _number(view["maxPitchDegrees"], "profile.viewInjection.maxPitchDegrees", 1.0, 60.0)
    intercepts = view["intercepts"]
    if (not isinstance(intercepts, list) or intercepts != sorted(set(intercepts)) or
            set(intercepts) != {"xrLocateSpace", "xrLocateViews"}):
        raise ContractError("view injection must intercept sorted xrLocateSpace and xrLocateViews")

    actions = _object(profile["actions"], "profile.actions")
    _exact_keys(actions, {"locomotion", "tabletToggle"}, set(), "profile.actions")
    locomotion = _object(actions["locomotion"], "profile.actions.locomotion")
    _exact_keys(locomotion, {
        "name", "type", "forwardRuntimeY", "supportedDirections",
        "applicationPreconditions",
    }, set(),
                "profile.actions.locomotion")
    _string(locomotion["name"], "profile.actions.locomotion.name", ACTION_NAME_PATTERN)
    if locomotion["type"] != "vector2f":
        raise ContractError("locomotion action must use vector2f")
    forward = _number(locomotion["forwardRuntimeY"],
                      "profile.actions.locomotion.forwardRuntimeY", -1.0, 1.0)
    if abs(forward) != 1.0:
        raise ContractError("forwardRuntimeY must be -1 or 1")
    directions = locomotion["supportedDirections"]
    if (not isinstance(directions, list) or directions != sorted(set(directions)) or
            not directions or not set(directions) <= {"backward", "forward", "left", "right"}):
        raise ContractError("locomotion supportedDirections are invalid or unsorted")
    preconditions = _object(locomotion["applicationPreconditions"],
                            "profile.actions.locomotion.applicationPreconditions")
    _exact_keys(preconditions, {"dominantHand"}, {"advancedMovement"},
                "profile.actions.locomotion.applicationPreconditions")
    if preconditions["dominantHand"] not in {"left", "right"}:
        raise ContractError("locomotion dominantHand must be left or right")
    if ("advancedMovement" in preconditions and
            not isinstance(preconditions["advancedMovement"], bool)):
        raise ContractError("locomotion advancedMovement must be boolean")

    tablet = _object(actions["tabletToggle"], "profile.actions.tabletToggle")
    _exact_keys(tablet, {"name", "type", "pulseMilliseconds"}, set(),
                "profile.actions.tabletToggle")
    _string(tablet["name"], "profile.actions.tabletToggle.name", ACTION_NAME_PATTERN)
    if tablet["type"] != "boolean":
        raise ContractError("tablet toggle action must use boolean")
    pulse = _integer(tablet["pulseMilliseconds"],
                     "profile.actions.tabletToggle.pulseMilliseconds", 40)
    if pulse > 500:
        raise ContractError("tablet toggle pulse must be <= 500 ms")
    return profile


def validate_envelope(raw: Any) -> dict[str, Any]:
    envelope = _object(raw, "envelope")
    _exact_keys(envelope, {
        "schemaVersion", "sessionNonce", "sequence", "issuedEpochMs", "commands",
    }, set(), "envelope")
    if envelope["schemaVersion"] != 1:
        raise ContractError("unsupported envelope schemaVersion")
    _string(envelope["sessionNonce"], "envelope.sessionNonce", NONCE_PATTERN)
    _integer(envelope["sequence"], "envelope.sequence", 1)
    _integer(envelope["issuedEpochMs"], "envelope.issuedEpochMs", 1)
    commands = envelope["commands"]
    if not isinstance(commands, list) or not 1 <= len(commands) <= MAX_COMMANDS:
        raise ContractError(f"envelope.commands must contain 1 through {MAX_COMMANDS} commands")
    identifiers: set[str] = set()
    for index, raw_command in enumerate(commands):
        command = _object(raw_command, f"commands[{index}]")
        _exact_keys(command, {"id", "operation", "arguments"}, set(),
                    f"commands[{index}]")
        identifier = _string(command["id"], f"commands[{index}].id", IDENTIFIER_PATTERN)
        if identifier in identifiers:
            raise ContractError("command ids must be unique")
        identifiers.add(identifier)
        operation = command["operation"]
        arguments = _object(command["arguments"], f"commands[{index}].arguments")
        if operation == "input.look":
            _exact_keys(arguments, {"horizontal"}, {"vertical", "durationSeconds"},
                        f"commands[{index}].arguments")
            _number(arguments["horizontal"], "look.horizontal", -0.45, 0.45)
            _number(arguments.get("vertical", 0.0), "look.vertical", -0.45, 0.45)
            _number(arguments.get("durationSeconds", 0.35),
                    "look.durationSeconds", 0.1, 2.0)
            if abs(arguments["horizontal"]) < 0.01 and abs(arguments.get("vertical", 0.0)) < 0.01:
                raise ContractError("look must request a visible non-zero rotation")
        elif operation == "input.move":
            _exact_keys(arguments, {"direction", "durationSeconds"}, {"strength"},
                        f"commands[{index}].arguments")
            if arguments["direction"] not in {"backward", "forward", "left", "right"}:
                raise ContractError("move.direction is unsupported")
            _number(arguments["durationSeconds"], "move.durationSeconds", 0.1, 3.0)
            _number(arguments.get("strength", 0.8), "move.strength", 0.2, 1.0)
        elif operation in {"tablet.close", "tablet.open"}:
            _exact_keys(arguments, set(), set(), f"commands[{index}].arguments")
        else:
            raise ContractError(f"unsupported semantic operation: {operation}")
    return envelope


def validate_grant(raw: Any, envelope: dict[str, Any], profile: dict[str, Any],
                   now_ms: int) -> dict[str, Any]:
    grant = _object(raw, "grant")
    _exact_keys(grant, {
        "schemaVersion", "buildMarker", "testBuild", "runtimeOptIn", "channel",
        "consumer", "bindingProfileSha256", "sessionNonce", "sequence",
        "expiresEpochMs",
    }, set(), "grant")
    if grant["schemaVersion"] != 1:
        raise ContractError("unsupported grant schemaVersion")
    if grant["buildMarker"] != BUILD_MARKER or grant["testBuild"] is not True:
        raise ContractError("grant requires the exact E2E test-build marker")
    if grant["runtimeOptIn"] is not True:
        raise ContractError("grant requires explicit runtime opt-in")
    if grant["channel"] != CHANNEL:
        raise ContractError("grant channel must be app-private-file")
    if grant["consumer"] != profile["consumer"]:
        raise ContractError("grant consumer does not match the profile")
    profile_hash = _string(grant["bindingProfileSha256"],
                           "grant.bindingProfileSha256", HASH_PATTERN)
    if profile_hash != profile_fingerprint(profile):
        raise ContractError("grant binding profile hash does not match")
    nonce = _string(grant["sessionNonce"], "grant.sessionNonce", NONCE_PATTERN)
    if nonce != envelope["sessionNonce"]:
        raise ContractError("grant and envelope session nonces differ")
    sequence = _integer(grant["sequence"], "grant.sequence", 1)
    if sequence != envelope["sequence"]:
        raise ContractError("grant does not authorize this exact sequence")
    expires = _integer(grant["expiresEpochMs"], "grant.expiresEpochMs", 1)
    issued = envelope["issuedEpochMs"]
    if issued > now_ms + MAX_CLOCK_SKEW_MS:
        raise ContractError("envelope issue time is in the future")
    if now_ms - issued > MAX_GRANT_LIFETIME_MS:
        raise ContractError("envelope is stale")
    if expires <= now_ms:
        raise ContractError("grant is expired")
    if expires - now_ms > MAX_GRANT_LIFETIME_MS:
        raise ContractError("grant lifetime exceeds the safety limit")
    return grant


def _quaternion(yaw_degrees: float, pitch_degrees: float) -> list[float]:
    """Return an OpenXR-order [x, y, z, w] yaw-then-pitch quaternion."""
    yaw = math.radians(yaw_degrees) / 2.0
    pitch = math.radians(pitch_degrees) / 2.0
    sy, cy = math.sin(yaw), math.cos(yaw)
    sp, cp = math.sin(pitch), math.cos(pitch)
    # q_yaw * q_pitch
    return [cy * sp, sy * cp, -sy * sp, cy * cp]


def _neutral_state(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "viewOffset": {
            "yawDegrees": 0.0,
            "pitchDegrees": 0.0,
            "orientation": [0.0, 0.0, 0.0, 1.0],
        },
        "vector2f": {profile["actions"]["locomotion"]["name"]: [0.0, 0.0]},
        "boolean": {profile["actions"]["tabletToggle"]["name"]: False},
    }


def compile_envelope(envelope_raw: Any, grant_raw: Any, profile_raw: Any,
                     now_ms: int) -> dict[str, Any]:
    """Compile semantic commands to deterministic API-layer state transitions."""
    profile = validate_profile(profile_raw)
    envelope = validate_envelope(envelope_raw)
    grant = validate_grant(grant_raw, envelope, profile, now_ms)
    neutral = _neutral_state(profile)
    events: list[dict[str, Any]] = [{"atMs": 0, "state": deepcopy(neutral)}]
    results: list[dict[str, Any]] = []
    cursor = NEUTRAL_HOLD_MS
    locomotion = profile["actions"]["locomotion"]
    tablet = profile["actions"]["tabletToggle"]
    max_yaw = float(profile["viewInjection"]["maxYawDegrees"])
    max_pitch = float(profile["viewInjection"]["maxPitchDegrees"])

    for command in envelope["commands"]:
        operation = command["operation"]
        arguments = command["arguments"]
        if operation == "input.look":
            duration = round(float(arguments.get("durationSeconds", 0.35)) * 1000)
            yaw = float(arguments["horizontal"]) / 0.45 * max_yaw
            pitch = float(arguments.get("vertical", 0.0)) / 0.45 * max_pitch
            start = cursor
            peak = start + duration
            state = deepcopy(neutral)
            state["viewOffset"] = {
                "yawDegrees": yaw,
                "pitchDegrees": pitch,
                "orientation": _quaternion(yaw, pitch),
            }
            events.append({
                "atMs": start,
                "transition": {"durationMs": duration, "curve": "linear"},
                "state": state,
            })
            release = peak + OBSERVATION_HOLD_MS
            events.append({"atMs": release, "state": deepcopy(neutral)})
            results.append({
                "commandId": command["id"],
                "operation": operation,
                "acknowledgeAtMs": peak,
                "observationWindow": {"startMs": peak, "endMs": release},
                "verification": "probe.view.orientation",
            })
            cursor = release + INTER_COMMAND_GAP_MS
        elif operation == "input.move":
            duration = round(float(arguments["durationSeconds"]) * 1000)
            strength = float(arguments.get("strength", 0.8))
            forward_y = float(locomotion["forwardRuntimeY"])
            direction = arguments["direction"]
            if direction not in locomotion["supportedDirections"]:
                raise ContractError(
                    f"profile {profile['profileId']} does not support move direction {direction}")
            axes = {
                "forward": [0.0, forward_y * strength],
                "backward": [0.0, -forward_y * strength],
                "left": [-strength, 0.0],
                "right": [strength, 0.0],
            }[direction]
            start = cursor
            release = start + duration
            state = deepcopy(neutral)
            state["vector2f"][locomotion["name"]] = axes
            events.append({"atMs": start, "state": state})
            events.append({"atMs": release, "state": deepcopy(neutral)})
            results.append({
                "commandId": command["id"],
                "operation": operation,
                "acknowledgeAtMs": release,
                "observationWindow": {
                    "startMs": release,
                    "endMs": release + OBSERVATION_HOLD_MS,
                },
                "verification": "probe.avatar.position",
                "precondition": {
                    f"application.{key}": value
                    for key, value in locomotion["applicationPreconditions"].items()
                },
            })
            cursor = release + OBSERVATION_HOLD_MS + INTER_COMMAND_GAP_MS
        else:
            start = cursor
            release = start + int(tablet["pulseMilliseconds"])
            state = deepcopy(neutral)
            state["boolean"][tablet["name"]] = True
            events.append({"atMs": start, "state": state})
            events.append({"atMs": release, "state": deepcopy(neutral)})
            expected_before = operation == "tablet.close"
            results.append({
                "commandId": command["id"],
                "operation": operation,
                "acknowledgeAtMs": release,
                "observationWindow": {
                    "startMs": release,
                    "endMs": release + OBSERVATION_HOLD_MS,
                },
                "precondition": {"probe.tablet.open": expected_before},
                "verification": "probe.tablet.open",
            })
            cursor = release + OBSERVATION_HOLD_MS + INTER_COMMAND_GAP_MS

    watchdog = max(cursor, events[-1]["atMs"] + NEUTRAL_HOLD_MS)
    if events[-1]["state"] != neutral:
        events.append({"atMs": watchdog, "state": deepcopy(neutral)})
    elif events[-1]["atMs"] < watchdog:
        events.append({"atMs": watchdog, "state": deepcopy(neutral)})
    return {
        "schemaVersion": 1,
        "prototypeOnly": True,
        "consumer": profile["consumer"],
        "profileId": profile["profileId"],
        "bindingProfileSha256": grant["bindingProfileSha256"],
        "sessionNonce": envelope["sessionNonce"],
        "sequence": envelope["sequence"],
        "requiredInterception": [
            "xrCreateAction", "xrCreateReferenceSpace", "xrGetActionStateBoolean",
            "xrGetActionStateVector2f", "xrLocateSpace", "xrLocateViews", "xrSyncActions",
        ],
        "events": events,
        "results": results,
        "watchdogDeadlineMs": watchdog,
        "terminalState": "neutral-and-disabled",
    }


class PrototypeConsumer:
    """Small state machine modeling the future API layer's sync boundaries."""

    def __init__(self, compiled: dict[str, Any], *, last_sequence: int = 0,
                 expected_session_nonce: str | None = None) -> None:
        if (not isinstance(compiled, dict) or compiled.get("schemaVersion") != 1 or
                compiled.get("prototypeOnly") is not True or
                compiled.get("terminalState") != "neutral-and-disabled"):
            raise ContractError("compiled stream is not a supported prototype")
        sequence = _integer(compiled.get("sequence"), "compiled.sequence", 1)
        previous_sequence = _integer(last_sequence, "last_sequence", 0)
        if sequence <= previous_sequence:
            raise ContractError("compiled stream sequence is stale or replayed")
        nonce = _string(compiled.get("sessionNonce"), "compiled.sessionNonce",
                        NONCE_PATTERN)
        if expected_session_nonce is not None and nonce != expected_session_nonce:
            raise ContractError("compiled stream belongs to a different session")
        events = compiled.get("events")
        if not isinstance(events, list) or not events:
            raise ContractError("compiled stream requires events")
        times = [event.get("atMs") for event in events]
        if any(isinstance(value, bool) or not isinstance(value, int) for value in times):
            raise ContractError("event times must be integers")
        if times != sorted(times):
            raise ContractError("events must use monotonic time")
        self._events = deepcopy(events)
        self.accepted_sequence = sequence
        self._deadline = _integer(compiled.get("watchdogDeadlineMs"),
                                  "watchdogDeadlineMs", 0)
        self._last_sync = -1
        self._event_index = 0
        self._state = deepcopy(events[0]["state"])
        self._previous_state = deepcopy(self._state)
        self.enabled = True

    def sync_actions(self, offset_ms: int) -> None:
        """Publish one immutable snapshot, as xrSyncActions requires."""
        offset = _integer(offset_ms, "offset_ms", 0)
        if offset < self._last_sync:
            self.enabled = False
            self._neutralize()
            raise ContractError("sync time moved backwards; consumer disabled")
        self._previous_state = deepcopy(self._state)
        if not self.enabled or offset >= self._deadline:
            self.enabled = False
            self._neutralize()
            self._last_sync = offset
            return
        while (self._event_index + 1 < len(self._events) and
               self._events[self._event_index + 1]["atMs"] <= offset):
            self._event_index += 1
            self._state = deepcopy(self._events[self._event_index]["state"])
        self._last_sync = offset

    def _neutralize(self) -> None:
        self._state["viewOffset"] = {
            "yawDegrees": 0.0,
            "pitchDegrees": 0.0,
            "orientation": [0.0, 0.0, 0.0, 1.0],
        }
        self._state["vector2f"] = {key: [0.0, 0.0]
                                    for key in self._state.get("vector2f", {})}
        self._state["boolean"] = {key: False
                                  for key in self._state.get("boolean", {})}

    def vector2f(self, action_name: str) -> dict[str, Any] | None:
        """Return an injected vector action, or None to delegate to the runtime."""
        current = self._state.get("vector2f", {}).get(action_name)
        if current is None:
            return None
        previous = self._previous_state.get("vector2f", {}).get(action_name)
        return {"isActive": self.enabled, "currentState": deepcopy(current),
                "changedSinceLastSync": current != previous}

    def boolean(self, action_name: str) -> dict[str, Any] | None:
        """Return an injected boolean action, or None to delegate to the runtime."""
        current = self._state.get("boolean", {}).get(action_name)
        if current is None:
            return None
        previous = self._previous_state.get("boolean", {}).get(action_name)
        return {"isActive": self.enabled, "currentState": current,
                "changedSinceLastSync": current != previous}

    def view_offset(self) -> dict[str, Any]:
        return deepcopy(self._state["viewOffset"])
