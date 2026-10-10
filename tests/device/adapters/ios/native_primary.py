"""Validate a fresh independently picked world target before physical touch."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import math
import time


def enabled(target):
    value = target.get("nativeWorldTap")
    return (isinstance(value, dict) and value == {"kind": "ios-documents", "version": 1}
            and type(value["version"]) is int)


def point(document, command_id, now_ms=None):
    if (not isinstance(document, dict) or set(document) != {"schemaVersion", "sampleEpochMs",
            "sampleSequence", "commandId", "valid", "entityName", "point"}
            or type(document["schemaVersion"]) is not int or document["schemaVersion"] != 1
            or type(document["sampleSequence"]) is not int or document["sampleSequence"] <= 0
            or document["commandId"] != command_id or document["valid"] is not True
            or document["entityName"] != "OVERTE_E2E_INTERACTABLE"):
        raise ValueError("native primary target was not independently observed")
    now_ms = time.time() * 1000 if now_ms is None else now_ms
    epoch = document["sampleEpochMs"]
    value = document["point"]
    if (type(epoch) not in (int, float) or not math.isfinite(epoch)
            or not -1000 <= now_ms - epoch <= 3000
            or not isinstance(value, dict) or set(value) != {"x", "y"}
            or any(type(v) not in (int, float) or not math.isfinite(v) or not 0.05 < v < 0.95
                   for v in value.values())):
        raise ValueError("native primary target point is stale or outside the world viewport")
    return [value["x"], value["y"]]
