"""Validate evidence from the selected app's actual microphone Settings switch."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
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
            "snapshot", "processBefore", "processAfter", "stoppedByOperatingSystem"}
            or any(type(value[k]) is not int or value[k] <= 0
                   for k in ("processBefore", "processAfter"))
            or str(value["processBefore"]) != identity
            or type(value["stoppedByOperatingSystem"]) is not bool):
        raise ValueError("native permission receipt has invalid process evidence")
    snapshot = validate_operation_result("permission.snapshot", value["snapshot"])
    if type(snapshot["schemaVersion"]) is not int or snapshot["state"] not in {"denied", "granted"}:
        raise ValueError("native permission switch did not expose a definite state")
    return snapshot
