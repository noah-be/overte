#!/usr/bin/env python3
"""Universal device-harness adapter for physical Pico headsets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from android.common.device_tests.adb_transport import AdbTransport  # noqa: E402

PACKAGE = "org.overte.pico"
LAUNCHER = "org.overte.pico/.PermissionsActivity"
CAPABILITIES = sorted({"app.foreground", "app.launch", "app.process", "app.stop",
                       "telemetry.snapshot", "world.status", "xr.focus"})
ADB = AdbTransport()


def is_pico(target: str) -> bool:
    identity = " ".join(ADB.prop(target, key) for key in (
        "ro.product.manufacturer", "ro.product.brand", "ro.product.model",
        "ro.product.device")).lower()
    return (ADB.prop(target, "ro.kernel.qemu") != "1"
            and ("pico" in identity or "bytedance" in identity)
            and "arm64-v8a" in ADB.prop(target, "ro.product.cpu.abilist").split(","))


def require_pico(target: str) -> None:
    if target not in ADB.authorized_targets() or not is_pico(target):
        raise RuntimeError("target is not an authorized physical Pico headset")


def discover() -> list[dict]:
    result = []
    for target in ADB.authorized_targets():
        if is_pico(target):
            result.append({"selector": target,
                           "displayName": ADB.prop(target, "ro.product.model") or "Pico",
                           "platform": "android-vr-pico", "physical": True,
                           "capabilities": CAPABILITIES})
    return result


def describe(target: str) -> dict:
    require_pico(target)
    return {"abi": ADB.prop(target, "ro.product.cpu.abilist").split(",")[0],
            "androidSdk": int(ADB.prop(target, "ro.build.version.sdk")),
            "manufacturer": ADB.prop(target, "ro.product.manufacturer"),
            "model": ADB.prop(target, "ro.product.model"), "physical": True,
            "platform": "android-vr-pico"}


def xr_focus(target: str) -> dict:
    boundary = ADB.prop(target, "sys.pxr.boundary.ready")
    seethrough = ADB.prop(target, "sys.guardian.vst.status")
    return {"focused": ADB.foreground_package(target) == PACKAGE,
            "boundaryReady": boundary == "1",
            "seethroughActive": seethrough != "0"}


def world_status(target: str) -> dict:
    raw = ADB.shell(target, "run-as", PACKAGE, "cat", "cache/world-status", check=False).strip()
    fields = raw.split("|")
    valid = (len(raw) <= 4096 and len(fields) >= 4 and len(fields[0]) <= 12
             and fields[0].isascii() and fields[0].isdigit() and fields[1] in {"0", "1"})
    fresh = bool(valid and 0 <= int(time.time()) - int(fields[0]) <= 5)
    return {"available": valid, "fresh": fresh,
            "connected": fresh and fields[1] == "1",
            "place": None}


def invoke(target: str, operation: str) -> dict:
    if operation not in CAPABILITIES:
        raise RuntimeError("unsupported adapter operation")
    require_pico(target)
    ADB.require_connected(target)
    if operation == "app.launch":
        ADB.shell(target, "am", "start", "-W", "-n", LAUNCHER)
        return {"launched": True}
    if operation == "app.stop":
        ADB.shell(target, "am", "force-stop", PACKAGE)
        return {"stopped": True}
    if operation == "app.process":
        return ADB.process_state(target, PACKAGE)
    if operation == "app.foreground":
        return {"foreground": ADB.foreground_package(target) == PACKAGE}
    if operation == "telemetry.snapshot":
        return ADB.telemetry_snapshot(target, PACKAGE)
    if operation == "xr.focus":
        return xr_focus(target)
    if operation == "world.status":
        return world_status(target)
    raise RuntimeError("unsupported adapter operation")


def cleanup(target: str) -> dict:
    require_pico(target)
    ADB.require_connected(target)
    ADB.shell(target, "am", "force-stop", PACKAGE, check=False)
    return {"cleaned": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("discover", "describe", "invoke", "cleanup"))
    parser.add_argument("--target")
    parser.add_argument("--operation")
    parser.add_argument("--arguments", default="{}")
    args = parser.parse_args()
    if args.action == "discover": value = discover()
    elif not args.target: raise ValueError("--target is required")
    elif args.action == "describe": value = describe(args.target)
    elif args.action == "cleanup": value = cleanup(args.target)
    elif not args.operation: raise ValueError("--operation is required")
    else:
        if not isinstance(json.loads(args.arguments), dict):
            raise ValueError("--arguments must be a JSON object")
        value = invoke(args.target, args.operation)
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try: raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired,
            json.JSONDecodeError) as error:
        print("error: Pico adapter operation failed", file=sys.stderr)
        raise SystemExit(2)
