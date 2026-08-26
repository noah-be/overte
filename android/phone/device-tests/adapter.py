#!/usr/bin/env python3
"""Universal device-harness adapter for physical Overte Android phones."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY_ROOT))
from android.common.device_tests.adb_transport import AdbTransport  # noqa: E402

PACKAGE = "org.overte.phone"
LAUNCHER = "org.overte.phone/.PermissionsActivity"
E2E_LAUNCHER = "org.overte.phone/.E2eLauncherActivity"
BASE_CAPABILITIES = {
    "app.foreground", "app.launch", "app.process",
    "lifecycle.background", "telemetry.snapshot",
}
INPUT_CAPABILITIES = {"input.fly", "input.jump"}
DEBUG_CAPABILITIES = {"probe.snapshot", "scene.load"}
INPUT_OPT_IN = "OVERTE_ANDROID_PHONE_E2E_INPUT"
DEBUG_OPT_IN = "OVERTE_ANDROID_E2E_DEBUG"
ANDROID_DEBUG_PROBE = "files/overte-e2e/overte-probe.json"
EMBEDDED_FIXTURE_URL = "overte-e2e://fixture/scene"
FIXTURE_SPAWN_DEEP_LINK = "hifi:/0,2,4/0,0,0,1"
FIXTURE_MARKER_COUNT = 4
PROBE_MAXIMUM_AGE_SECONDS = 5.0
JUMP_TOUCH_MILLISECONDS = 120
MIN_FLY_DURATION_SECONDS = 0.1
MAX_FLY_DURATION_SECONDS = 10.0

# TouchscreenVirtualPadDevice and VirtualPadManager use these production
# constants to place the jump button. Android's logical display density is the
# closest privacy-safe system measurement available to an out-of-process ADB
# adapter and keeps the calculated point well inside the production hit area.
VIRTUAL_PAD_DPI = 534.0
JUMP_BUTTON_FULL_PIXELS = 164.0
JUMP_BUTTON_TRIMMED_RADIUS_PIXELS = 67.0
JUMP_BUTTON_BOTTOM_MARGIN_PIXELS = 80.0
JUMP_BUTTON_RIGHT_MARGIN_PIXELS = 13.0
ADB = AdbTransport()


def input_opted_in() -> bool:
    return os.environ.get(INPUT_OPT_IN) == "1"


def debug_opted_in() -> bool:
    return os.environ.get(DEBUG_OPT_IN) == "1"


def capabilities() -> list[str]:
    values = set(BASE_CAPABILITIES)
    if input_opted_in():
        values.update(INPUT_CAPABILITIES)
    if debug_opted_in():
        values.update(DEBUG_CAPABILITIES)
    return sorted(values)


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
            "capabilities": capabilities(),
        })
    return targets


def require_target(target: str) -> None:
    if target not in ADB.authorized_targets() or not supported_phone(target):
        raise RuntimeError("target is not an authorized supported physical Android phone")


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


def require_exact_arguments(operation: str, arguments: dict,
                            expected: set[str]) -> None:
    if set(arguments) != expected:
        if expected:
            raise RuntimeError(
                f"{operation} requires only {', '.join(sorted(expected))}")
        raise RuntimeError(f"{operation} does not accept arguments")


def fly_duration(arguments: dict) -> float:
    require_exact_arguments("input.fly", arguments, {"durationSeconds"})
    duration = arguments["durationSeconds"]
    if (isinstance(duration, bool) or not isinstance(duration, (int, float))
            or not math.isfinite(duration)
            or not MIN_FLY_DURATION_SECONDS <= duration <= MAX_FLY_DURATION_SECONDS):
        raise RuntimeError(
            "input.fly durationSeconds must be a finite number from "
            f"{MIN_FLY_DURATION_SECONDS} through {MAX_FLY_DURATION_SECONDS}")
    return float(duration)


def display_size(target: str) -> tuple[int, int]:
    input_state = ADB.shell(target, "dumpsys", "input", check=False)
    viewport_sizes = re.findall(
        r"logicalFrame=\[\s*0\s*,\s*0\s*,\s*(\d+)\s*,\s*(\d+)\s*\]",
        input_state)
    if viewport_sizes:
        width, height = map(int, viewport_sizes[0])
    else:
        raw_size = ADB.shell(target, "wm", "size", check=False)
        sizes = re.findall(
            r"(?:(Physical|Override) size:\s*)?(\d+)x(\d+)", raw_size)
        if not sizes:
            raise RuntimeError("Android display size is unavailable")
        preferred = next((item for item in reversed(sizes) if item[0] == "Override"),
                         sizes[-1])
        width, height = int(preferred[1]), int(preferred[2])
        orientation_match = re.search(
            r"(?:SurfaceOrientation|orientation)\s*[:=]\s*([0-3])",
            input_state)
        if orientation_match and int(orientation_match.group(1)) in {1, 3}:
            width, height = height, width
    if width <= height or width < 2 or height < 2:
        raise RuntimeError("Android Phone input requires the landscape virtual pad")
    return width, height


def display_density(target: str) -> float:
    raw_density = ADB.shell(target, "wm", "density", check=False)
    densities = re.findall(
        r"(?:(Physical|Override) density:\s*)?(\d+(?:[.]\d+)?)", raw_density)
    if not densities:
        raise RuntimeError("Android display density is unavailable")
    preferred = next((item for item in reversed(densities) if item[0] == "Override"),
                     densities[-1])
    density = float(preferred[1])
    if not math.isfinite(density) or not 72.0 <= density <= 1000.0:
        raise RuntimeError("Android display density is outside safe bounds")
    return density


def jump_button_position(target: str) -> tuple[int, int]:
    width, height = display_size(target)
    scale = display_density(target) / VIRTUAL_PAD_DPI
    radius = JUMP_BUTTON_TRIMMED_RADIUS_PIXELS * scale
    x = round(width - (JUMP_BUTTON_RIGHT_MARGIN_PIXELS
                       + JUMP_BUTTON_FULL_PIXELS) * scale)
    y = round(height - (JUMP_BUTTON_BOTTOM_MARGIN_PIXELS * scale) - radius)
    if not 0 < x < width or not 0 < y < height:
        raise RuntimeError("calculated Android Phone jump input is outside the display")
    return x, y


def require_input_session(target: str) -> str:
    if not input_opted_in():
        raise RuntimeError("Android Phone input requires explicit E2E opt-in")
    package_path = ADB.shell(target, "pm", "path", PACKAGE, check=False).strip()
    if not package_path.startswith("package:/"):
        raise RuntimeError("the expected Android Phone package is not installed")
    process = ADB.process_state(target, PACKAGE)
    identity = process.get("identity")
    if (process.get("running") is not True or not isinstance(identity, str)
            or not identity):
        raise RuntimeError("the Android Phone application process is not running")
    if ADB.foreground_package(target) != PACKAGE:
        raise RuntimeError("the Android Phone application is not in the foreground")
    return identity


def session_file(target: str) -> Path:
    root = Path(os.environ.get(
        "OVERTE_ANDROID_PHONE_E2E_STATE_ROOT",
        str(Path(tempfile.gettempdir()) / "overte-android-phone-e2e-state"),
    )).resolve()
    key = hashlib.sha256(f"android-phone\0{target}".encode()).hexdigest()[:24]
    return root / key / "debug-session.json"


def save_debug_session(target: str, identity: str) -> None:
    path = session_file(target)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({
        "package": PACKAGE,
        "processIdentity": identity,
    }, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)


def discard_debug_session(target: str) -> None:
    path = session_file(target)
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def load_debug_session(target: str) -> str:
    try:
        value = json.loads(session_file(target).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("Android Phone debug session is unavailable") from error
    if (not isinstance(value, dict)
            or set(value) != {"package", "processIdentity"}
            or value.get("package") != PACKAGE
            or not isinstance(value.get("processIdentity"), str)
            or not value["processIdentity"]):
        raise RuntimeError("Android Phone debug session is invalid")
    return value["processIdentity"]


def current_process_identity(target: str) -> str:
    process = ADB.process_state(target, PACKAGE)
    identity = process.get("identity")
    if (process.get("running") is not True or not isinstance(identity, str)
            or not identity):
        raise RuntimeError("the Android Phone application process is not running")
    return identity


def require_debug_session(target: str) -> str:
    if not debug_opted_in():
        raise RuntimeError("Android Phone debug operation requires explicit E2E opt-in")
    # Full physical-phone eligibility is established before the debug launcher
    # writes this host-side session binding. Probe polling deliberately uses
    # only the connected target and bound process so a short jump remains
    # observable instead of repeating expensive device-profile discovery.
    ADB.require_connected(target)
    expected = load_debug_session(target)
    if current_process_identity(target) != expected:
        raise RuntimeError("Android Phone debug application process changed")
    return expected


def wait_for_process_identity(target: str, timeout_seconds: float = 30.0) -> str:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            return current_process_identity(target)
        except RuntimeError:
            time.sleep(0.25)
    raise RuntimeError("Android Phone E2E launcher process did not start")


def launch_debug_app(target: str) -> str:
    if not debug_opted_in():
        raise RuntimeError("Android Phone debug launch requires explicit E2E opt-in")
    discard_debug_session(target)
    if ADB.process_state(target, PACKAGE).get("running") is True:
        ADB.shell(target, "am", "force-stop", PACKAGE)
    try:
        ADB.shell(target, "am", "start", "-W", "-n", E2E_LAUNCHER)
        identity = wait_for_process_identity(target)
        save_debug_session(target, identity)
        return identity
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        ADB.shell(target, "am", "force-stop", PACKAGE, check=False)
        discard_debug_session(target)
        raise


def probe_retry_policy() -> tuple[int, float]:
    attempts_raw = os.environ.get("OVERTE_ANDROID_E2E_PROBE_ATTEMPTS", "60")
    interval_raw = os.environ.get(
        "OVERTE_ANDROID_E2E_PROBE_POLL_SECONDS", "0.25")
    if not attempts_raw.isdigit() or not 1 <= int(attempts_raw) <= 120:
        raise RuntimeError(
            "OVERTE_ANDROID_E2E_PROBE_ATTEMPTS must be from 1 through 120")
    try:
        interval = float(interval_raw)
    except ValueError as error:
        raise RuntimeError(
            "OVERTE_ANDROID_E2E_PROBE_POLL_SECONDS must be numeric") from error
    if not math.isfinite(interval) or not 0.01 <= interval <= 1.0:
        raise RuntimeError(
            "OVERTE_ANDROID_E2E_PROBE_POLL_SECONDS must be from 0.01 through 1.0")
    return int(attempts_raw), interval


def fresh_probe_snapshot(raw: str) -> dict | None:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict):
        return None
    sampled = value.get("sampleEpochMs")
    now = int(time.time() * 1000)
    if (not isinstance(sampled, int) or isinstance(sampled, bool)
            or abs(now - sampled) > PROBE_MAXIMUM_AGE_SECONDS * 1000):
        return None
    return value


def read_probe_snapshot(target: str, identity: str,
                        after_sequence: int | None = None) -> dict:
    attempts, interval = probe_retry_policy()
    for attempt in range(attempts):
        raw = ADB.read_debug_app_file(
            target, PACKAGE, ANDROID_DEBUG_PROBE, attempts=1)
        snapshot = fresh_probe_snapshot(raw)
        if snapshot is not None:
            sequence = snapshot.get("sampleSequence")
            sequence_valid = (isinstance(sequence, int)
                              and not isinstance(sequence, bool) and sequence > 0)
            if (after_sequence is None
                    or (sequence_valid and sequence > after_sequence)):
                if current_process_identity(target) != identity:
                    raise RuntimeError("Android Phone debug application process changed")
                return snapshot
        if attempt + 1 < attempts:
            time.sleep(interval)
    if current_process_identity(target) != identity:
        raise RuntimeError("Android Phone debug application process changed")
    raise RuntimeError(
        "Android Phone probe snapshot is unavailable, stale, or did not advance")


def wait_for_fixture_import(target: str, identity: str) -> None:
    attempts, interval = probe_retry_policy()
    previous_epoch = None
    consecutive_samples = 0
    for attempt in range(attempts):
        raw = ADB.read_debug_app_file(
            target, PACKAGE, ANDROID_DEBUG_PROBE, attempts=1)
        snapshot = fresh_probe_snapshot(raw)
        if snapshot is not None:
            epoch = snapshot.get("sampleEpochMs")
            if epoch != previous_epoch:
                previous_epoch = epoch
                scene = snapshot.get("scene")
                marker_count = (scene.get("fixtureMarkerCount")
                                if isinstance(scene, dict) else None)
                consecutive_samples = (consecutive_samples + 1
                                       if marker_count == FIXTURE_MARKER_COUNT else 0)
                if consecutive_samples >= 2:
                    if current_process_identity(target) != identity:
                        raise RuntimeError(
                            "Android Phone debug application process changed")
                    return
        if attempt + 1 < attempts:
            time.sleep(interval)
    if current_process_identity(target) != identity:
        raise RuntimeError("Android Phone debug application process changed")
    raise RuntimeError("Android Phone embedded fixture import did not complete")


def load_embedded_scene(target: str) -> dict:
    identity = launch_debug_app(target)
    try:
        # The debug launcher enters the serverless fixture through the normal
        # --url path. Wait until that asynchronous import has settled before
        # navigating to its viewpoint; applying the launch-time query earlier
        # can be superseded by the serverless scene transition.
        wait_for_fixture_import(target, identity)
        ADB.shell(target, "am", "start", "-W",
                  "-a", "android.intent.action.VIEW",
                  "-d", FIXTURE_SPAWN_DEEP_LINK,
                  "-n", LAUNCHER)
        if current_process_identity(target) != identity:
            raise RuntimeError("Android Phone application process changed during scene load")
        if ADB.foreground_package(target) != PACKAGE:
            raise RuntimeError("Android Phone application left the foreground during scene load")
        return {"requested": True, "verification": "fixture-markers"}
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        ADB.shell(target, "am", "force-stop", PACKAGE, check=False)
        discard_debug_session(target)
        raise


def neutralize_vertical_input(target: str,
                              position: tuple[int, int] | None = None) -> None:
    try:
        x, y = position or jump_button_position(target)
        ADB.shell(target, "input", "touchscreen", "motionevent", "UP",
                  str(x), str(y), check=False)
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        # Cleanup is fail-closed and best effort. A bounded Android
        # `input swipe` also emits its own ACTION_UP when it completes.
        pass


def perform_vertical_touch(target: str, duration_milliseconds: int) -> dict:
    identity = require_input_session(target)
    position = jump_button_position(target)
    x, y = position
    try:
        ADB.shell(target, "input", "touchscreen", "swipe",
                  str(x), str(y), str(x), str(y),
                  str(duration_milliseconds))
    finally:
        neutralize_vertical_input(target, position)
    # The package and foreground checks above bind the touch to the intended
    # session. Re-read only the process identity afterward: repeating package
    # manager and activity dumpsys calls can outlast a bounded jump, preventing
    # the shared probe from observing its airborne phase.
    process = ADB.process_state(target, PACKAGE)
    if process.get("running") is not True or process.get("identity") != identity:
        raise RuntimeError("Android Phone application process changed during input")
    return {"performed": True}


def invoke(target: str, operation: str, arguments: dict) -> dict:
    if operation == "input.jump":
        require_exact_arguments(operation, arguments, set())
        require_target(target)
        return perform_vertical_touch(target, JUMP_TOUCH_MILLISECONDS)
    if operation == "input.fly":
        duration = fly_duration(arguments)
        require_target(target)
        return perform_vertical_touch(target, round(duration * 1000.0))
    if operation == "probe.snapshot":
        require_exact_arguments(
            operation, arguments,
            {"afterSampleSequence"} if "afterSampleSequence" in arguments else set())
        after_sequence = arguments.get("afterSampleSequence")
        if (after_sequence is not None and (
                not isinstance(after_sequence, int) or isinstance(after_sequence, bool)
                or after_sequence < 0)):
            raise RuntimeError(
                "afterSampleSequence must be a non-negative integer")
        identity = require_debug_session(target)
        return read_probe_snapshot(target, identity, after_sequence)
    if operation == "scene.load":
        require_exact_arguments(operation, arguments, {"url"})
        if arguments["url"] != EMBEDDED_FIXTURE_URL:
            raise RuntimeError(
                "Android Phone debug scene.load accepts only the embedded fixture URL")
        if not debug_opted_in():
            raise RuntimeError("scene.load requires an E2E-enabled debug APK")
        require_target(target)
        return load_embedded_scene(target)
    require_target(target)
    if operation == "app.launch":
        require_exact_arguments(operation, arguments, set())
        if debug_opted_in():
            launch_debug_app(target)
        else:
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
    try:
        require_target(target)
        if input_opted_in():
            neutralize_vertical_input(target)
        ADB.shell(target, "am", "force-stop", PACKAGE, check=False)
        return {"cleaned": True}
    finally:
        discard_debug_session(target)


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
