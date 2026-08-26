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
    if operation == "input.jump":
        if value:
            raise ValueError("input.jump does not accept arguments")
    elif operation == "input.fly":
        if set(value) != {"durationSeconds"}:
            raise ValueError("input.fly requires only durationSeconds")
        duration = value["durationSeconds"]
        if (not isinstance(duration, (int, float)) or isinstance(duration, bool)
                or not math.isfinite(float(duration))
                or not 0.1 <= float(duration) <= MAX_FLY_DURATION_SECONDS):
            raise ValueError(
                f"input.fly durationSeconds must be from 0.1 through "
                f"{MAX_FLY_DURATION_SECONDS}")
    return value


def validate_performed_result(operation: str, value: object) -> dict:
    if not isinstance(value, dict) or value.get("performed") is not True:
        raise ValueError(f"{operation} result must confirm performed: true")
    return value


def validate_probe_snapshot(value: object) -> dict:
    if not isinstance(value, dict) or value.get("schemaVersion") != 1:
        raise ValueError("probe snapshot must use schema version 1")
    if (not isinstance(value.get("sampleEpochMs"), int)
            or isinstance(value["sampleEpochMs"], bool) or value["sampleEpochMs"] <= 0):
        raise ValueError("probe snapshot requires a positive sampleEpochMs")
    required_objects = ("build", "application", "scene", "avatar", "view", "tablet")
    for field in required_objects:
        if not isinstance(value.get(field), dict):
            raise ValueError(f"probe snapshot requires object field {field}")
    build = value["build"]
    if not all(isinstance(build.get(field), str) and build[field]
               for field in ("platform", "version", "date")):
        raise ValueError("probe build requires non-empty platform, version and date")
    application = value["application"]
    if not isinstance(application.get("running"), bool):
        raise ValueError("probe application.running must be boolean")
    input_state = value.get("input")
    if input_state is not None:
        if (not isinstance(input_state, dict)
                or input_state.get("dominantHand") not in {"left", "right"}
                or not isinstance(input_state.get("advancedMovementControls"), bool)):
            raise ValueError("probe input requires dominantHand and advancedMovementControls")
    scene = value["scene"]
    entity_count = scene.get("entityCount")
    if (not isinstance(scene.get("ready"), bool) or not isinstance(entity_count, int)
            or isinstance(entity_count, bool) or entity_count < 0):
        raise ValueError("probe scene requires ready and entityCount")
    for owner, field in ((value["avatar"], "position"), (value["view"], "orientation")):
        vector = owner.get(field)
        if not isinstance(vector, dict) or not all(
                isinstance(vector.get(axis), (int, float)) and not isinstance(vector.get(axis), bool)
                and math.isfinite(float(vector[axis]))
                for axis in ("x", "y", "z")):
            raise ValueError(f"probe {field} requires numeric x/y/z")
    avatar = value["avatar"]
    for field in ("inAir", "flying", "flyingEnabled"):
        if not isinstance(avatar.get(field), bool):
            raise ValueError(f"probe avatar.{field} must be boolean")
    if avatar["flying"] and not avatar["inAir"]:
        raise ValueError("probe avatar cannot be flying while not inAir")
    if not isinstance(value["tablet"].get("open"), bool):
        raise ValueError("probe tablet.open must be boolean")
    return value
