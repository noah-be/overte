#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

"""Validate the entity and asset evidence captured for the bundled tutorial."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


EXPECTED_MODELS = {
    "Seagull",
    "LOGO",
    "Bowl",
    "Dome Glass",
    "trees",
    "Dome",
    "Temple",
    "Planters",
    "STAND-ANGLE_CONTROLS",
    "STAND-ANGLE_TABLET-TOOLBAR",
    "STAND-ANGLE_APPLICATIONS",
    "STAND-ANGLE_AVATAR",
    "STAND-ANGLE_CONFIG-WIZARD",
    "AVATAR_VIEWER_PLATFORM",
    "QUICK TEST AREA",
    "TELEPORTER",
}
EXPECTED_LANDMARKS = {
    "MainDomeZone",
    "IN-WORLD PORTAL",
    "QUICK SETUP",
    "Avatar_Viewer_Sign",
}
EXPECTED_TYPE_MINIMUMS = {
    "Box": 2,
    "Light": 10,
    "Material": 1,
    "Model": 16,
    "ParticleEffect": 3,
    "Shape": 2,
    "Text": 5,
    "Zone": 1,
}
QUEUE_NAMES = (
    "downloads",
    "downloads_pending",
    "processing",
    "processing_pending",
    "texture_pending_mb",
)


def valid_vector(value: object) -> bool:
    return isinstance(value, dict) and all(
        isinstance(value.get(axis), (int, float))
        and not isinstance(value.get(axis), bool)
        and math.isfinite(float(value[axis]))
        for axis in ("x", "y", "z")
    )


def validate(payload: object) -> dict[str, object]:
    failures: list[str] = []
    if not isinstance(payload, dict):
        return {
            "schema_version": 1,
            "passed": False,
            "failures": ["root must be an object"],
        }

    if payload.get("schema_version") != 1:
        failures.append("unsupported schema_version")
    if payload.get("expected_entity_count") != 40:
        failures.append("expected_entity_count must preserve the 40-entity tutorial contract")
    entity_count = payload.get("entity_count")
    if (
        not isinstance(entity_count, int)
        or isinstance(entity_count, bool)
        or entity_count < 40
    ):
        failures.append("tutorial inventory contains fewer than 40 entities")

    entities = payload.get("entities")
    if not isinstance(entities, list):
        failures.append("entities must be an array")
        entities = []
    if isinstance(entity_count, int) and entity_count != len(entities):
        failures.append("entity_count does not match the captured inventory")

    identifiers: set[str] = set()
    computed_types: dict[str, int] = {}
    computed_visible_models = 0
    computed_loaded_visible_models = 0
    for index, entity in enumerate(entities):
        if not isinstance(entity, dict):
            failures.append(f"entity {index} is not an object")
            continue
        identifier = str(entity.get("id", "")).strip().strip("{}").lower()
        if not identifier:
            failures.append(f"entity {index} has no id")
        elif identifier in identifiers:
            failures.append(f"duplicate entity id: {identifier}")
        identifiers.add(identifier)
        entity_type = entity.get("type")
        if not isinstance(entity_type, str) or not entity_type:
            failures.append(f"entity {index} has no type")
            continue
        computed_types[entity_type] = computed_types.get(entity_type, 0) + 1
        visible = entity.get("visible")
        loaded = entity.get("loaded")
        if not isinstance(visible, bool):
            failures.append(f"entity {index} visible is not boolean")
        if not isinstance(loaded, bool):
            failures.append(f"entity {index} loaded is not boolean")
        if not valid_vector(entity.get("position")):
            failures.append(f"entity {index} position is invalid")
        if not valid_vector(entity.get("dimensions")):
            failures.append(f"entity {index} dimensions are invalid")
        if entity_type == "Model" and visible is True:
            computed_visible_models += 1
            if loaded is True:
                computed_loaded_visible_models += 1

    type_counts = payload.get("type_counts")
    if type_counts != computed_types:
        failures.append("type_counts does not match the captured inventory")
    for entity_type, minimum in EXPECTED_TYPE_MINIMUMS.items():
        if computed_types.get(entity_type, 0) < minimum:
            failures.append(
                f"tutorial has fewer than {minimum} {entity_type} entities"
            )

    if payload.get("expected_model_count") != len(EXPECTED_MODELS):
        failures.append("expected_model_count does not match the tutorial contract")
    expected_models = payload.get("expected_models")
    if not isinstance(expected_models, dict) or set(expected_models) != EXPECTED_MODELS:
        failures.append("expected_models has an unexpected name set")
        expected_models = {}
    for name in sorted(EXPECTED_MODELS):
        state = expected_models.get(name)
        if not isinstance(state, dict) or state.get("found") is not True:
            failures.append(f"tutorial model is missing: {name}")
        elif state.get("loaded") is not True:
            failures.append(f"tutorial model is not loaded: {name}")
    if payload.get("found_expected_model_count") != len(EXPECTED_MODELS):
        failures.append("not every expected tutorial model was found")
    if payload.get("loaded_expected_model_count") != len(EXPECTED_MODELS):
        failures.append("not every expected tutorial model was loaded")

    if payload.get("expected_landmark_count") != len(EXPECTED_LANDMARKS):
        failures.append("expected_landmark_count does not match the tutorial contract")
    expected_landmarks = payload.get("expected_landmarks")
    if (
        not isinstance(expected_landmarks, dict)
        or set(expected_landmarks) != EXPECTED_LANDMARKS
    ):
        failures.append("expected_landmarks has an unexpected name set")
        expected_landmarks = {}
    for name in sorted(EXPECTED_LANDMARKS):
        if expected_landmarks.get(name) is not True:
            failures.append(f"tutorial landmark is missing: {name}")
    if payload.get("found_expected_landmark_count") != len(EXPECTED_LANDMARKS):
        failures.append("not every expected tutorial landmark was found")

    if payload.get("visible_model_count") != computed_visible_models:
        failures.append("visible_model_count does not match the captured inventory")
    if payload.get("loaded_visible_model_count") != computed_loaded_visible_models:
        failures.append("loaded_visible_model_count does not match the captured inventory")
    if computed_visible_models < len(EXPECTED_MODELS):
        failures.append("tutorial has fewer visible models than expected")
    if computed_loaded_visible_models < len(EXPECTED_MODELS):
        failures.append("tutorial has fewer loaded visible models than expected")

    resource_queues = payload.get("resource_queues")
    if not isinstance(resource_queues, dict):
        failures.append("resource_queues must be an object")
        resource_queues = {}
    for name in QUEUE_NAMES:
        value = resource_queues.get(name)
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            or value != 0
        ):
            failures.append(f"resource queue {name} is not empty")

    present_count = payload.get("present_count")
    if (
        not isinstance(present_count, int)
        or isinstance(present_count, bool)
        or present_count <= 0
    ):
        failures.append("present_count must be a positive integer")

    return {
        "schema_version": 1,
        "passed": not failures,
        "failures": failures,
        "entity_count": entity_count,
        "expected_model_count": len(EXPECTED_MODELS),
        "loaded_expected_model_count": payload.get("loaded_expected_model_count"),
        "expected_landmark_count": len(EXPECTED_LANDMARKS),
        "found_expected_landmark_count": payload.get("found_expected_landmark_count"),
        "visible_model_count": computed_visible_models,
        "loaded_visible_model_count": computed_loaded_visible_models,
        "type_counts": computed_types,
        "resource_queues": resource_queues,
        "present_count": present_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inventory", type=Path)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = json.loads(args.inventory.read_text(encoding="utf-8"))
        result = validate(payload)
    except (OSError, json.JSONDecodeError) as error:
        result = {
            "schema_version": 1,
            "passed": False,
            "failures": [str(error)],
        }
    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
