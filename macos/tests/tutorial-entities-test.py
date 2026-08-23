#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "macos/tools/validate-tutorial-entities.py"
SPEC = importlib.util.spec_from_file_location("validate_tutorial_entities", VALIDATOR)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def record(identifier: str, name: str, entity_type: str, loaded: bool = False) -> dict:
    return {
        "id": identifier,
        "name": name,
        "type": entity_type,
        "visible": True,
        "loaded": loaded,
        "position": {"x": 1, "y": 2, "z": 3},
        "dimensions": {"x": 1, "y": 1, "z": 1},
    }


def valid_payload() -> dict:
    entities = [
        record(f"model-{index}", name, "Model", True)
        for index, name in enumerate(sorted(MODULE.EXPECTED_MODELS))
    ]
    entities.extend(
        [
            record("zone-0", "MainDomeZone", "Zone"),
            record("text-0", "IN-WORLD PORTAL", "Text"),
            record("text-1", "QUICK SETUP", "Text"),
            record("text-2", "Avatar_Viewer_Sign", "Text"),
        ]
    )
    additions = {
        "Box": 2,
        "Light": 10,
        "Material": 1,
        "ParticleEffect": 3,
        "Shape": 2,
        "Text": 2,
    }
    for entity_type, count in additions.items():
        for index in range(count):
            entities.append(
                record(
                    f"additional-{entity_type.lower()}-{index}",
                    f"additional {entity_type} {index}",
                    entity_type,
                )
            )
    assert len(entities) == 40
    type_counts: dict[str, int] = {}
    for entity in entities:
        type_counts[entity["type"]] = type_counts.get(entity["type"], 0) + 1
    return {
        "schema_version": 1,
        "entity_count": 40,
        "expected_entity_count": 40,
        "expected_model_count": len(MODULE.EXPECTED_MODELS),
        "found_expected_model_count": len(MODULE.EXPECTED_MODELS),
        "loaded_expected_model_count": len(MODULE.EXPECTED_MODELS),
        "expected_landmark_count": len(MODULE.EXPECTED_LANDMARKS),
        "found_expected_landmark_count": len(MODULE.EXPECTED_LANDMARKS),
        "visible_model_count": len(MODULE.EXPECTED_MODELS),
        "loaded_visible_model_count": len(MODULE.EXPECTED_MODELS),
        "type_counts": type_counts,
        "expected_models": {
            name: {"found": True, "loaded": True}
            for name in MODULE.EXPECTED_MODELS
        },
        "expected_landmarks": {name: True for name in MODULE.EXPECTED_LANDMARKS},
        "entities": entities,
        "resource_queues": {name: 0 for name in MODULE.QUEUE_NAMES},
        "present_count": 42,
    }


payload = valid_payload()
result = MODULE.validate(payload)
assert result["passed"], result

missing_model = copy.deepcopy(payload)
missing_model["expected_models"]["Temple"]["loaded"] = False
result = MODULE.validate(missing_model)
assert not result["passed"]
assert "tutorial model is not loaded: Temple" in result["failures"]

busy_queue = copy.deepcopy(payload)
busy_queue["resource_queues"]["processing"] = 1
result = MODULE.validate(busy_queue)
assert not result["passed"]
assert "resource queue processing is not empty" in result["failures"]

duplicate_id = copy.deepcopy(payload)
duplicate_id["entities"][1]["id"] = duplicate_id["entities"][0]["id"]
result = MODULE.validate(duplicate_id)
assert not result["passed"]
assert any(failure.startswith("duplicate entity id:") for failure in result["failures"])

print("macOS bundled tutorial entity validator contract valid")
