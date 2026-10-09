"""Validate fresh process-bound native text and presentation observations."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import math
import re
import time
from contracts import validate_text_snapshot


def enabled(target):
    value = target.get("nativeIntegration")
    return (isinstance(value, dict) and value == {"kind": "ios-documents", "version": 2}
            and type(value["version"]) is int)


def envelope(document, process_id, fields, now_ms=None):
    if (not isinstance(document, dict) or set(document) != fields
            or type(document["schemaVersion"]) is not int or document["schemaVersion"] != 1
            or type(document["processId"]) is not int or document["processId"] != process_id):
        raise ValueError("native integration observation has invalid process or schema")
    epoch = document["sampleEpochMs"]
    now_ms = time.time() * 1000 if now_ms is None else now_ms
    if (type(epoch) not in (int, float) or not math.isfinite(epoch)
            or not -1000 <= now_ms - epoch <= 3000):
        raise ValueError("native integration observation is stale")
    return document


def text(document, process_id, command_id, now_ms=None):
    envelope(document, process_id, {"schemaVersion", "processId", "sampleEpochMs", "commandId", "ok", "snapshot"}, now_ms)
    if document["ok"] is not True or document["commandId"] != command_id:
        raise ValueError("native text result did not execute the exact requested command")
    return validate_text_snapshot(document["snapshot"])


def render(document, process_id, now_ms=None):
    envelope(document, process_id, {"schemaVersion", "processId", "sampleEpochMs", "valid", "backend",
        "hardwareAccelerated", "surfaceVisible", "generation", "acceptedPresentCalls", "frameSequence"}, now_ms)
    if (document["valid"] is not True or document["backend"] != "Vulkan/MoltenVK"
            or type(document["hardwareAccelerated"]) is not bool
            or type(document["surfaceVisible"]) is not bool
            or type(document["frameSequence"]) is not int or document["frameSequence"] <= 0
            or any(not isinstance(document[key], str) or not re.fullmatch(r"[1-9][0-9]{0,19}", document[key])
                   or int(document[key]) > 2**64 - 1 for key in ("generation", "acceptedPresentCalls"))):
        raise ValueError("native presentation evidence is absent or malformed")
    return document
