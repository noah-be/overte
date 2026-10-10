"""Validate evidence from the selected app's actual microphone Settings switch."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import math
import time
from contracts import validate_operation_result


def enabled(target):
    value = target.get("nativePermission")
    if value is None:
        return False
    if value != {"kind": "ios-settings-ui", "permissionId": "microphone"}:
        raise ValueError("native permission requires the explicit microphone Settings binding")
    return True


def observation(value, identity):
    if (not isinstance(value, dict) or set(value) != {
            "snapshot", "processBefore", "processAfter", "stoppedByOperatingSystem", "recoveryLaunchEpochMs"}
            or any(type(value[k]) is not int or value[k] <= 0
                   for k in ("processBefore", "processAfter"))
            or str(value["processBefore"]) != identity
            or type(value["stoppedByOperatingSystem"]) is not bool
            or type(value["recoveryLaunchEpochMs"]) is not int
            or not -1000 <= time.time() * 1000 - value["recoveryLaunchEpochMs"] <= 120000):
        raise ValueError("native permission receipt has invalid process evidence")
    snapshot = validate_operation_result("permission.snapshot", value["snapshot"])
    if type(snapshot["schemaVersion"]) is not int or snapshot["state"] not in {"denied", "granted"}:
        raise ValueError("native permission switch did not expose a definite state")
    return snapshot


def audio_snapshot(value):
    """Observe the foreground client's native audio permission after recovery."""
    if (not isinstance(value, dict) or value.get("ok") is not True
            or value.get("iosForeground") is not True
            or type(value.get("iosPermission")) is not int
            or value["iosPermission"] not in (1, 2)):
        raise ValueError("native audio did not expose a definite foreground microphone permission")
    epoch = value.get("sampleEpochMs")
    if (type(epoch) not in (int, float) or not math.isfinite(epoch)
            or not -1000 <= time.time() * 1000 - epoch <= 5000):
        raise ValueError("native microphone permission sample is stale")
    return validate_operation_result("permission.snapshot", {
        "schemaVersion": 1, "permissionId": "microphone",
        "state": "granted" if value["iosPermission"] == 1 else "denied"})
