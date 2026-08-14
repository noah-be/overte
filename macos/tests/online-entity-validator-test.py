#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "macos/tools/validate-online-entities.py"
SPEC = importlib.util.spec_from_file_location("validate_online_entities", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def record(entity_id: str, entity_type: str = "Shape", visible: bool = True) -> dict:
    return {
        "id": entity_id,
        "type": entity_type,
        "visible": visible,
        "position": {"x": 1.0, "y": 2.0, "z": 3.0},
        "dimensions": {"x": 1.0, "y": 1.0, "z": 1.0},
    }


def payload(entities: list[dict]) -> dict:
    visible = sum(
        item["visible"] and item["type"] not in MODULE.NON_VISIBLE_GEOMETRY_TYPES
        for item in entities
    )
    return {
        "schema_version": 1,
        "entity_count": len(entities),
        "captured_count": len(entities),
        "visible_renderable_count": visible,
        "type_counts": {},
        "entities": entities,
    }


handoff = "098c4ff9-4ddd-49a0-94e4-7109a84ba216"
valid = MODULE.validate(payload([record("{" + handoff + "}"), record("other", "Zone")]), handoff)
assert valid["passed"], valid
assert valid["render_handoff_type"] == "Shape"

for environmental_type in ("Zone", "Light", "Material"):
    environmental = MODULE.validate(payload([record(handoff, environmental_type)]), handoff)
    assert not environmental["passed"]
    assert "inventory has no visible render-affecting entity" in environmental["failures"]
    assert "render-handoff entity is not visible and render-affecting" not in environmental["failures"]

zone_handoff = MODULE.validate(
    payload([record(handoff, "Zone"), record("visible-shape")]), handoff
)
assert zone_handoff["passed"], zone_handoff
assert zone_handoff["render_handoff_type"] == "Zone"

missing = MODULE.validate(payload([record("other")]), handoff)
assert not missing["passed"]
assert "render-handoff entity is absent from online inventory" in missing["failures"]

non_rendering = MODULE.validate(payload([record(handoff, "Sound")]), handoff)
assert not non_rendering["passed"]
assert "inventory has no visible render-affecting entity" in non_rendering["failures"]

hidden = MODULE.validate(payload([record(handoff, "Model", False)]), handoff)
assert not hidden["passed"]
assert "render-handoff entity is not visible and render-affecting" in hidden["failures"]

bad_vector_payload = payload([record(handoff)])
bad_vector_payload["entities"][0]["position"]["x"] = float("nan")
bad_vector = MODULE.validate(bad_vector_payload, handoff)
assert not bad_vector["passed"]
assert "entity 0 position is invalid" in bad_vector["failures"]

print("macOS online entity validator contract valid")
