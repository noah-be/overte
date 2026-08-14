#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

"""Validate that an online entity handed to the renderer is in the test inventory."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


NON_RENDERING_TYPES = {"Unknown", "Empty", "Sound", "Script"}
NON_VISIBLE_GEOMETRY_TYPES = NON_RENDERING_TYPES | {"Zone", "Light", "Material"}


def normalized_id(value: object) -> str:
    return str(value).strip().strip("{}").lower()


def valid_vector(value: object) -> bool:
    return isinstance(value, dict) and all(
        isinstance(value.get(axis), (int, float))
        and not isinstance(value.get(axis), bool)
        and math.isfinite(float(value[axis]))
        for axis in ("x", "y", "z")
    )


def validate(payload: object, render_handoff_id: str) -> dict[str, object]:
    failures: list[str] = []
    if not isinstance(payload, dict):
        return {"schema_version": 1, "passed": False, "failures": ["root must be an object"]}

    entities = payload.get("entities")
    if payload.get("schema_version") != 1:
        failures.append("unsupported schema_version")
    if not isinstance(entities, list) or not entities:
        failures.append("entities must be a non-empty array")
        entities = []
    entity_count = payload.get("entity_count")
    captured_count = payload.get("captured_count")
    if not isinstance(entity_count, int) or isinstance(entity_count, bool) or entity_count < len(entities):
        failures.append("entity_count must cover every captured entity")
    if captured_count != len(entities):
        failures.append("captured_count does not match entities")

    records: dict[str, dict[str, object]] = {}
    computed_visible_renderable = 0
    for index, entity in enumerate(entities):
        if not isinstance(entity, dict):
            failures.append(f"entity {index} is not an object")
            continue
        entity_id = normalized_id(entity.get("id", ""))
        if not entity_id:
            failures.append(f"entity {index} has no id")
        elif entity_id in records:
            failures.append(f"duplicate entity id: {entity_id}")
        else:
            records[entity_id] = entity
        entity_type = entity.get("type")
        if not isinstance(entity_type, str) or not entity_type:
            failures.append(f"entity {index} has no type")
        visible = entity.get("visible")
        if not isinstance(visible, bool):
            failures.append(f"entity {index} visible is not boolean")
        if not valid_vector(entity.get("position")):
            failures.append(f"entity {index} position is invalid")
        if not valid_vector(entity.get("dimensions")):
            failures.append(f"entity {index} dimensions are invalid")
        if (
            visible is True
            and isinstance(entity_type, str)
            and entity_type not in NON_VISIBLE_GEOMETRY_TYPES
        ):
            computed_visible_renderable += 1

    if payload.get("visible_renderable_count") != computed_visible_renderable:
        failures.append("visible_renderable_count does not match inventory")
    if computed_visible_renderable < 1:
        failures.append("inventory has no visible render-affecting entity")

    handoff_id = normalized_id(render_handoff_id)
    handoff = records.get(handoff_id)
    if handoff is None:
        failures.append("render-handoff entity is absent from online inventory")
        handoff_type = None
        handoff_visible = None
    else:
        handoff_type = handoff.get("type")
        handoff_visible = handoff.get("visible")
        if handoff_visible is not True or handoff_type in NON_RENDERING_TYPES:
            failures.append("render-handoff entity is not visible and render-affecting")

    return {
        "schema_version": 1,
        "passed": not failures,
        "failures": failures,
        "entity_count": entity_count,
        "captured_count": len(entities),
        "visible_renderable_count": computed_visible_renderable,
        "render_handoff_id": handoff_id,
        "render_handoff_type": handoff_type,
        "render_handoff_visible": handoff_visible,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inventory", type=Path)
    parser.add_argument("--render-handoff-id", required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()

    try:
        payload = json.loads(args.inventory.read_text(encoding="utf-8"))
        result = validate(payload, args.render_handoff_id)
    except (OSError, json.JSONDecodeError) as error:
        result = {"schema_version": 1, "passed": False, "failures": [str(error)]}
    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
