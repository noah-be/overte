#!/usr/bin/env python3
"""Universal device-harness adapter for physical Overte Android phones."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY_ROOT))
from android.common.device_tests.adb_transport import AdbTransport  # noqa: E402

PACKAGE = "org.overte.phone"
LAUNCHER = "org.overte.phone/.PermissionsActivity"
CAPABILITIES = sorted({
    "app.foreground", "app.launch", "app.process", "app.stop",
    "lifecycle.background", "telemetry.snapshot",
})
ADB = AdbTransport()


def supported_phone(target: str) -> bool:
    identity = " ".join(ADB.prop(target, name) for name in (
        "ro.product.manufacturer", "ro.product.brand", "ro.product.model",
        "ro.product.device")).lower()
    characteristics = ADB.prop(target, "ro.build.characteristics").lower().split(",")
    abis = ADB.prop(target, "ro.product.cpu.abilist").split(",")
    sdk = ADB.prop(target, "ro.build.version.sdk")
    gles = ADB.prop(target, "ro.opengles.version")
    features = ADB.shell(target, "pm", "list", "features", check=False).splitlines()
    return (
        ADB.prop(target, "ro.kernel.qemu") != "1"
        and not ({"watch", "tv", "automotive", "vr"} & set(characteristics))
        and "pico" not in identity and "bytedance" not in identity
        and "arm64-v8a" in abis
        and sdk.isdigit() and int(sdk) >= 26
        and gles.isdigit() and int(gles) >= 196610
        and "feature:android.hardware.touchscreen" in features
    )


def discover() -> list[dict]:
    targets = []
    for target in ADB.authorized_targets():
        if not supported_phone(target):
            continue
        manufacturer = ADB.prop(target, "ro.product.manufacturer") or "Android"
        model = ADB.prop(target, "ro.product.model") or "Phone"
        targets.append({
            "selector": target,
            "displayName": f"{manufacturer} {model}",
            "platform": "android-phone",
            "physical": True,
            "capabilities": CAPABILITIES,
        })
    return targets


def require_target(target: str) -> None:
    if target not in ADB.authorized_targets() or not supported_phone(target):
        raise RuntimeError("target is not an authorized supported physical Android phone")


def require_connected_target(target: str) -> None:
    ADB.require_connected(target)


def describe(target: str) -> dict:
    require_target(target)
    return {
        "abi": ADB.prop(target, "ro.product.cpu.abilist").split(",")[0],
        "androidSdk": int(ADB.prop(target, "ro.build.version.sdk")),
        "manufacturer": ADB.prop(target, "ro.product.manufacturer"),
        "model": ADB.prop(target, "ro.product.model"),
        "osVersion": ADB.prop(target, "ro.build.version.release"),
        "physical": True,
        "platform": "android-phone",
    }


def invoke(target: str, operation: str, arguments: dict) -> dict:
    del arguments
    require_connected_target(target)
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
    if operation == "lifecycle.background":
        ADB.shell(target, "am", "start", "-W", "-a", "android.intent.action.MAIN",
                  "-c", "android.intent.category.HOME")
        return {"backgrounded": True}
    if operation == "telemetry.snapshot":
        return ADB.telemetry_snapshot(target, PACKAGE)
    raise RuntimeError("unsupported adapter operation")


def cleanup(target: str) -> dict:
    require_connected_target(target)
    ADB.shell(target, "am", "force-stop", PACKAGE, check=False)
    return {"cleaned": True}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("discover", "describe", "invoke", "cleanup"))
    parser.add_argument("--target")
    parser.add_argument("--operation")
    parser.add_argument("--arguments", default="{}")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.action == "discover":
        value = discover()
    else:
        if not args.target:
            raise ValueError("--target is required")
        if args.action == "describe":
            value = describe(args.target)
        elif args.action == "cleanup":
            value = cleanup(args.target)
        else:
            if not args.operation:
                raise ValueError("--operation is required")
            arguments = json.loads(args.arguments)
            if not isinstance(arguments, dict):
                raise ValueError("--arguments must be a JSON object")
            value = invoke(args.target, args.operation, arguments)
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired,
            json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
