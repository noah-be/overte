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
    insets = [native.get("safeInset" + edge) for edge in ("Left", "Top", "Right", "Bottom")]
    if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in insets):
        raise ValueError("native safe-content insets are invalid")
    left, top, right, bottom = insets
    width, height = sizes[0] - left - right, sizes[1] - top - bottom
    if width < 1 or height < 1:
        raise ValueError("native safe-content area is empty")
    # Qt reports its safe-content viewport, UIKit the complete window. Use
    # observed native insets, including the home-indicator area, for projection.
    # Reject rotation races instead of guessing an orientation or fixed offset.
    if abs(width / height - sizes[2] / sizes[3]) > 0.005:
        raise ValueError("native UIKit and Qt viewport orientations disagree")
    return {"x": left, "y": top, "width": width, "height": height}
