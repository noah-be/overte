"""Observe Android runtime grants and effective native microphone AppOps."""
# SPDX-License-Identifier: Apache-2.0
import re


def permission_modes(adb, device, package):
    output = adb.shell(device, "cmd", "appops", "get", package, "RECORD_AUDIO")
    pattern = r"(allow|ignore|deny|default|foreground)\b"
    uid = set(re.findall(r"^\s*Uid mode: RECORD_AUDIO: " + pattern, output, re.MULTILINE))
    modes = set(re.findall(r"^\s*RECORD_AUDIO: " + pattern, output, re.MULTILINE))
    if len(uid) <= 1 and len(modes) <= 1 and (uid or modes):
        return {"uid": next(iter(uid), "default"), "package": next(iter(modes), "default")}
    if "No operations." in output:
        return {"uid": "default", "package": "default"}
    raise RuntimeError("Android microphone AppOps mode is unavailable or ambiguous")


def permission_snapshot(adb, device, package):
    output = adb.shell(device, "dumpsys", "package", package)
    granted = set(re.findall(r"android.permission.RECORD_AUDIO: granted=(true|false)", output))
    if len(granted) != 1:
        raise RuntimeError("Android microphone runtime grant is unavailable or ambiguous")
    modes = permission_modes(adb, device, package)
    mode = modes["uid"] if modes["uid"] != "default" else modes["package"]
    allowed = granted == {"true"} and mode in {"allow", "default", "foreground"}
    return {"schemaVersion": 1, "permissionId": "microphone", "state": "granted" if allowed else "denied"}
