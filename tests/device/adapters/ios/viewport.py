"""Validate independently sampled UIKit geometry before physical HID input."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import math
import time


def viewport(document, now_ms=None):
    if (not isinstance(document, dict) or set(document) != {
            "schemaVersion", "sampleEpochMs", "sampleSequence", "nativeUi", "window"}
            or document["schemaVersion"] != 1
            or type(document["sampleSequence"]) is not int or document["sampleSequence"] < 1):
        raise ValueError("native viewport observation has invalid fields")
    observed = document["sampleEpochMs"]
    now_ms = time.time() * 1000 if now_ms is None else now_ms
    if (type(observed) not in (int, float) or not math.isfinite(observed)
            or not -1000 <= now_ms - observed <= 3000):
        raise ValueError("native viewport observation is stale")
    native, window = document["nativeUi"], document["window"]
    if not isinstance(native, dict) or native.get("valid") is not True or not isinstance(window, dict):
        raise ValueError("native UIKit surface is unavailable")
    sizes = [native.get("surfaceWidth"), native.get("surfaceHeight"),
             window.get("width"), window.get("height")]
    if any(type(v) not in (int, float) or not math.isfinite(v) or not 1 <= v <= 10000 for v in sizes):
        raise ValueError("native viewport dimensions are invalid")
    # Both views describe the same active application surface. Reject rotation
    # races and hidden/resized windows rather than injecting at guessed points.
    if abs(sizes[0] / sizes[1] - sizes[2] / sizes[3]) > 0.02:
        raise ValueError("native UIKit and Qt viewport orientations disagree")
    return {"x": 0, "y": 0, "width": sizes[0], "height": sizes[1]}
