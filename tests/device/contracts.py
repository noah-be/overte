#!/usr/bin/env python3
"""Versioned contracts shared by the device runner and adapter verifier."""

from __future__ import annotations

import json
import math
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent
IDENTIFIER = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$")
MAX_FLY_DURATION_SECONDS = 10.0
MAX_INPUT_DURATION_SECONDS = 10.0
MAX_LOOK_COMPONENT = 1.0
MOVEMENT_DIRECTIONS = {"backward", "forward", "left", "right"}


def load_capability_registry(path: Path | None = None) -> dict[str, dict]:
    source = path or ROOT / "capabilities.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    capabilities = payload.get("capabilities")
    if payload.get("schemaVersion") != 1 or not isinstance(capabilities, dict):
        raise ValueError("unsupported capability registry schema")
    if not capabilities or list(capabilities) != sorted(capabilities):
        raise ValueError("capability registry must be non-empty and sorted")
    for name, definition in capabilities.items():
        if not IDENTIFIER.fullmatch(name) or not isinstance(definition, dict):
            raise ValueError(f"invalid capability registry entry: {name}")
        operation = definition.get("operation")
        if operation is not None and operation != name:
            raise ValueError(f"capability operation must match its name: {name}")
        if not isinstance(definition.get("result"), str) or not definition["result"]:
            raise ValueError(f"capability requires result documentation: {name}")
    return capabilities


def validate_identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} must use lowercase dotted identifier syntax")
    return value


def validate_capabilities(values: object, registry: dict[str, dict] | None = None) -> list[str]:
    known = registry or load_capability_registry()
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise ValueError("capabilities must be a string list")
    if values != sorted(set(values)):
        raise ValueError("capabilities must be unique and use deterministic sorted order")
    unknown = sorted(set(values) - set(known))
    if unknown:
        raise ValueError("unknown capabilities: " + ", ".join(unknown))
    return values


def validate_operation_arguments(operation: str, value: object) -> dict:
    """Validate arguments whose portable shape is part of the shared contract."""
    if not isinstance(value, dict):
        raise ValueError("operation arguments must be an object")
    if operation in {
            "app.foreground", "app.launch", "app.process", "app.stop",
            "input.jump", "tablet.close", "tablet.open"}:
        if value:
            raise ValueError(f"{operation} does not accept arguments")
    elif operation == "input.fly":
        if set(value) != {"durationSeconds"}:
            raise ValueError("input.fly requires only durationSeconds")
        _bounded_number(value["durationSeconds"], "input.fly durationSeconds",
                        0.1, MAX_FLY_DURATION_SECONDS)
    elif operation == "input.look":
        if set(value) != {"horizontal", "vertical"}:
            raise ValueError("input.look requires only horizontal and vertical")
        horizontal = _bounded_number(
            value["horizontal"], "input.look horizontal",
            -MAX_LOOK_COMPONENT, MAX_LOOK_COMPONENT)
        vertical = _bounded_number(
            value["vertical"], "input.look vertical",
            -MAX_LOOK_COMPONENT, MAX_LOOK_COMPONENT)
        if horizontal == 0.0 and vertical == 0.0:
            raise ValueError("input.look requires a non-zero component")
    elif operation == "input.move":
        if set(value) != {"direction", "durationSeconds"}:
            raise ValueError("input.move requires only direction and durationSeconds")
        if value["direction"] not in MOVEMENT_DIRECTIONS:
            raise ValueError("input.move direction is unsupported")
        _bounded_number(value["durationSeconds"], "input.move durationSeconds",
                        0.1, MAX_INPUT_DURATION_SECONDS)
    elif operation == "probe.snapshot":
        if not set(value) <= {"afterSampleSequence"}:
            raise ValueError("probe.snapshot accepts only afterSampleSequence")
        if "afterSampleSequence" in value:
            sequence = value["afterSampleSequence"]
            if (not isinstance(sequence, int) or isinstance(sequence, bool)
                    or sequence <= 0):
                raise ValueError("probe.snapshot afterSampleSequence must be a positive integer")
    elif operation == "scene.load":
        if set(value) != {"url"}:
            raise ValueError("scene.load requires only url")
        if not isinstance(value["url"], str) or "://" not in value["url"]:
            raise ValueError("scene.load url must be an absolute URL")
    return value


def _bounded_number(value: object, label: str, minimum: float, maximum: float) -> float:
    if (not isinstance(value, (int, float)) or isinstance(value, bool)
            or not math.isfinite(float(value))
            or not minimum <= float(value) <= maximum):
        raise ValueError(f"{label} must be from {minimum} through {maximum}")
    return float(value)


def validate_performed_result(operation: str, value: object) -> dict:
    if not isinstance(value, dict) or value.get("performed") is not True:
        raise ValueError(f"{operation} result must confirm performed: true")
    return value


def validate_operation_result(operation: str, value: object) -> dict:
    """Validate the portable result evidence returned by an adapter operation."""
    if not isinstance(value, dict):
        raise ValueError(f"{operation} result must be an object")
    if operation in {"input.fly", "input.jump", "input.look", "input.move",
                     "tablet.close", "tablet.open"}:
        return validate_performed_result(operation, value)
    confirmation = {
        "app.launch": "launched",
        "app.stop": "stopped",
        "scene.load": "requested",
    }.get(operation)
    if confirmation is not None and value.get(confirmation) is not True:
        raise ValueError(f"{operation} result must confirm {confirmation}: true")
    if operation == "app.foreground" and not isinstance(value.get("foreground"), bool):
        raise ValueError("app.foreground result requires foreground: boolean")
    if operation == "app.process":
        running = value.get("running")
        identity = value.get("identity")
        if not isinstance(running, bool):
            raise ValueError("app.process result requires running: boolean")
        if running and (not isinstance(identity, str) or not identity):
            raise ValueError("running app.process result requires a non-empty identity")
        if not running and identity is not None:
            raise ValueError("stopped app.process result requires identity: null")
    return value


def validate_probe_snapshot(value: object) -> dict:
    if not isinstance(value, dict) or value.get("schemaVersion") != 2:
        raise ValueError("probe snapshot must use schema version 2")
    _require_exact_fields(value, {
        "application", "avatar", "build", "input", "sampleEpochMs",
        "sampleSequence", "scene", "schemaVersion", "tablet", "view",
    }, "probe snapshot")
    if (not isinstance(value.get("sampleEpochMs"), int)
            or isinstance(value["sampleEpochMs"], bool) or value["sampleEpochMs"] <= 0):
        raise ValueError("probe snapshot requires a positive sampleEpochMs")
    if (not isinstance(value.get("sampleSequence"), int)
            or isinstance(value["sampleSequence"], bool) or value["sampleSequence"] <= 0):
        raise ValueError("probe snapshot requires a positive sampleSequence")
    required_objects = ("build", "application", "input", "scene", "avatar", "view", "tablet")
    for field in required_objects:
        if not isinstance(value.get(field), dict):
            raise ValueError(f"probe snapshot requires object field {field}")
    build = value["build"]
    _require_exact_fields(build, {"date", "platform", "version"}, "probe build")
    if not all(isinstance(build.get(field), str) and build[field]
               for field in ("platform", "version", "date")):
        raise ValueError("probe build requires non-empty platform, version and date")
    application = value["application"]
    _require_exact_fields(application, {"foreground", "running"}, "probe application")
    if (not isinstance(application.get("running"), bool)
            or not isinstance(application.get("foreground"), bool)):
        raise ValueError("probe application requires running and foreground booleans")
    input_state = value["input"]
    _require_exact_fields(
        input_state, {"advancedMovementControls", "dominantHand"}, "probe input")
    if (input_state.get("dominantHand") not in {"left", "right", "unknown"}
            or not isinstance(input_state.get("advancedMovementControls"), bool)):
        raise ValueError("probe input requires dominantHand and advancedMovementControls")
    scene = value["scene"]
    _require_exact_fields(scene, {
        "avatarAboveFloor", "collisionWall", "entityCount", "fixtureMarkerCount",
        "fixtureMarkers", "floorTopY", "ready", "spawnLocationObserved",
        "spawnValidated", "url",
    }, "probe scene")
    entity_count = scene.get("entityCount")
    if (not isinstance(scene.get("ready"), bool) or not isinstance(entity_count, int)
            or isinstance(entity_count, bool) or entity_count < 0):
        raise ValueError("probe scene requires ready and entityCount")
    if not isinstance(scene.get("url"), str):
        raise ValueError("probe scene.url must be a string")
    marker_count = scene.get("fixtureMarkerCount")
    markers = scene.get("fixtureMarkers")
    if (not isinstance(marker_count, int) or isinstance(marker_count, bool)
            or marker_count < 0 or not isinstance(markers, list)
            or not all(isinstance(marker, str) and marker for marker in markers)
            or len(markers) != marker_count or len(set(markers)) != len(markers)):
        raise ValueError("probe scene fixture markers are invalid")
    floor_top = scene.get("floorTopY")
    if floor_top is not None:
        _finite_number(floor_top, "probe scene.floorTopY")
    for field in ("avatarAboveFloor", "spawnLocationObserved", "spawnValidated"):
        if not isinstance(scene.get(field), bool):
            raise ValueError(f"probe scene.{field} must be boolean")
    wall = scene.get("collisionWall")
    if wall is not None:
        if not isinstance(wall, dict) or set(wall) != {"center", "dimensions", "name"}:
            raise ValueError("probe scene.collisionWall has an invalid shape")
        if wall.get("name") != "OVERTE_E2E_COLLISION_WALL":
            raise ValueError("probe scene.collisionWall has an invalid name")
        _validate_vector(wall.get("center"), "probe collision wall center")
        dimensions = _validate_vector(
            wall.get("dimensions"), "probe collision wall dimensions")
        if any(float(dimensions[axis]) <= 0.0 for axis in ("x", "y", "z")):
            raise ValueError("probe collision wall dimensions must be positive")
    avatar = value["avatar"]
    _require_exact_fields(avatar, {
        "bodyYawDegrees", "flying", "flyingEnabled", "inAir", "position", "velocity",
    }, "probe avatar")
    _validate_vector(avatar.get("position"), "probe avatar.position")
    _validate_vector(avatar.get("velocity"), "probe avatar.velocity")
    _finite_number(avatar.get("bodyYawDegrees"), "probe avatar.bodyYawDegrees")
    for field in ("inAir", "flying", "flyingEnabled"):
        if not isinstance(avatar.get(field), bool):
            raise ValueError(f"probe avatar.{field} must be boolean")
    if avatar["flying"] and not avatar["inAir"]:
        raise ValueError("probe avatar cannot be flying while not inAir")
    _require_exact_fields(value["view"], {"orientation"}, "probe view")
    _validate_vector(value["view"].get("orientation"), "probe view.orientation")
    _require_exact_fields(
        value["tablet"], {"home", "open", "toolbarMode"}, "probe tablet")
    for field in ("open", "home", "toolbarMode"):
        if not isinstance(value["tablet"].get(field), bool):
            raise ValueError(f"probe tablet.{field} must be boolean")
    return value


def _finite_number(value: object, label: str) -> float:
    if (not isinstance(value, (int, float)) or isinstance(value, bool)
            or not math.isfinite(float(value))):
        raise ValueError(f"{label} must be finite numeric")
    return float(value)


def _require_exact_fields(value: dict, expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} contains unsupported or missing fields")


def _validate_vector(value: object, label: str) -> dict:
    if not isinstance(value, dict) or set(value) != {"x", "y", "z"}:
        raise ValueError(f"{label} requires exactly numeric x/y/z")
    for axis in ("x", "y", "z"):
        _finite_number(value[axis], f"{label}.{axis}")
    return value
