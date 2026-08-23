#!/usr/bin/env python3
"""Universal device-harness adapter for physical Overte Android phones."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys


PACKAGE = "org.overte.phone"
LAUNCHER = "org.overte.phone/.PermissionsActivity"
CAPABILITIES = sorted({
    "app.foreground", "app.launch", "app.process", "app.stop",
    "lifecycle.background", "telemetry.snapshot",
})


def adb_path() -> str:
    candidates = [
        os.environ.get("OVERTE_ANDROID_ADB", ""),
        str(Path(os.environ.get("ANDROID_SDK_ROOT", "")) / "platform-tools/adb"),
        str(Path(os.environ.get("ANDROID_HOME", "")) / "platform-tools/adb"),
        str(Path.home() / "Android/Sdk/platform-tools/adb"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise RuntimeError("ADB executable was not found")


def execute(arguments: list[str], *, target: str | None = None,
            timeout: int = 20, check: bool = True) -> str:
    command = [adb_path()]
    if target:
        command += ["-s", target]
    result = subprocess.run([*command, *arguments], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=timeout, check=False)
    if check and result.returncode != 0:
        raise RuntimeError("ADB operation failed")
    return result.stdout.replace("\r", "")


def shell(target: str, *arguments: str, check: bool = True) -> str:
    return execute(["shell", *arguments], target=target, check=check)


def prop(target: str, name: str) -> str:
    return shell(target, "getprop", name, check=False).strip()


def supported_phone(target: str) -> bool:
    identity = " ".join(prop(target, name) for name in (
        "ro.product.manufacturer", "ro.product.brand", "ro.product.model",
        "ro.product.device")).lower()
    characteristics = prop(target, "ro.build.characteristics").lower().split(",")
    abis = prop(target, "ro.product.cpu.abilist").split(",")
    sdk = prop(target, "ro.build.version.sdk")
    gles = prop(target, "ro.opengles.version")
    features = shell(target, "pm", "list", "features", check=False).splitlines()
    return (
        prop(target, "ro.kernel.qemu") != "1"
        and not ({"watch", "tv", "automotive", "vr"} & set(characteristics))
        and "pico" not in identity and "bytedance" not in identity
        and "arm64-v8a" in abis
        and sdk.isdigit() and int(sdk) >= 26
        and gles.isdigit() and int(gles) >= 196610
        and "feature:android.hardware.touchscreen" in features
    )


def authorized_targets() -> list[str]:
    lines = execute(["devices", "-l"], check=True).splitlines()
    return [parts[0] for line in lines if len(parts := line.split()) >= 2 and parts[1] == "device"]


def discover() -> list[dict]:
    targets = []
    for target in authorized_targets():
        if not supported_phone(target):
            continue
        manufacturer = prop(target, "ro.product.manufacturer") or "Android"
        model = prop(target, "ro.product.model") or "Phone"
        targets.append({
            "selector": target,
            "displayName": f"{manufacturer} {model}",
            "platform": "android-phone",
            "physical": True,
            "capabilities": CAPABILITIES,
        })
    return targets


def require_target(target: str) -> None:
    if target not in authorized_targets() or not supported_phone(target):
        raise RuntimeError("target is not an authorized supported physical Android phone")


def require_connected_target(target: str) -> None:
    if execute(["get-state"], target=target, check=False).strip() != "device":
        raise RuntimeError("target is not connected and authorized")


def describe(target: str) -> dict:
    require_target(target)
    return {
        "abi": prop(target, "ro.product.cpu.abilist").split(",")[0],
        "androidSdk": int(prop(target, "ro.build.version.sdk")),
        "manufacturer": prop(target, "ro.product.manufacturer"),
        "model": prop(target, "ro.product.model"),
        "osVersion": prop(target, "ro.build.version.release"),
        "physical": True,
        "platform": "android-phone",
    }


def process_state(target: str) -> dict:
    pid = shell(target, "pidof", "-s", PACKAGE, check=False).strip()
    if not pid.isdigit():
        return {"running": False, "identity": None}
    stat = shell(target, "cat", f"/proc/{pid}/stat", check=False).strip().split()
    start_ticks = stat[21] if len(stat) > 21 and stat[21].isdigit() else "unknown"
    return {"running": True, "identity": f"{pid}:{start_ticks}"}


def foreground_state(target: str) -> dict:
    activities = shell(target, "dumpsys", "activity", "activities", check=False)
    resumed_pattern = re.compile(
        r"^\s*(?:mResumedActivity|topResumedActivity|ResumedActivity|Resumed):")
    resumed = next((line for line in activities.splitlines()
                    if resumed_pattern.search(line)), "")
    return {"foreground": PACKAGE in resumed}


def integer_match(pattern: str, text: str) -> int | None:
    match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
    return int(match.group(1)) if match else None


def telemetry(target: str) -> dict:
    memory = shell(target, "dumpsys", "meminfo", PACKAGE, check=False)
    total = re.search(r"^\s*TOTAL\s+(\d+)\s+(\d+)", memory, re.MULTILINE)
    battery = shell(target, "dumpsys", "battery", check=False)
    thermal = shell(target, "dumpsys", "thermalservice", check=False)
    value: dict[str, object] = {
        "batteryLevel": integer_match(r"^\s*level:\s*(\d+)", battery),
        "batteryTemperatureDeciC": integer_match(r"^\s*temperature:\s*(\d+)", battery),
        "memoryPssKb": int(total.group(1)) if total else None,
        "memoryRssKb": int(total.group(2)) if total else None,
        "thermalStatus": integer_match(r"(?:Thermal Status:|mStatus=)\s*(\d+)", thermal),
    }
    return value


def invoke(target: str, operation: str, arguments: dict) -> dict:
    del arguments
    require_connected_target(target)
    if operation == "app.launch":
        shell(target, "am", "start", "-W", "-n", LAUNCHER)
        return {"launched": True}
    if operation == "app.stop":
        shell(target, "am", "force-stop", PACKAGE)
        return {"stopped": True}
    if operation == "app.process":
        return process_state(target)
    if operation == "app.foreground":
        return foreground_state(target)
    if operation == "lifecycle.background":
        shell(target, "am", "start", "-W", "-a", "android.intent.action.MAIN",
              "-c", "android.intent.category.HOME")
        return {"backgrounded": True}
    if operation == "telemetry.snapshot":
        return telemetry(target)
    raise RuntimeError("unsupported adapter operation")


def cleanup(target: str) -> dict:
    require_connected_target(target)
    shell(target, "am", "force-stop", PACKAGE, check=False)
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
