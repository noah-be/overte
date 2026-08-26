#!/usr/bin/env python3
"""Universal ADB adapter for physical Overte Phone and Pico targets."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time


REPOSITORY = Path(__file__).resolve().parents[4]
DEVICE_ROOT = Path(__file__).resolve().parents[2]
for path in (str(REPOSITORY), str(DEVICE_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from android.common.device_tests.adb_transport import AdbTransport  # noqa: E402
from adapters.common import (EMBEDDED_FIXTURE_URL, emit, fail,  # noqa: E402
                             parse_operation_arguments,
                             require_fresh_snapshot)
from openxr_input.adapter_session import (  # noqa: E402
    PicoOpenXrAdapterSession, pico_openxr_opted_in,
    validate_pico_openxr_configuration,
)
from openxr_input.android_transport import AndroidOpenXrTransport  # noqa: E402


PROFILES = {
    "phone": {
        "adapter": "android-phone-adb",
        "package": "org.overte.phone",
        "activity": "org.overte.phone/.PermissionsActivity",
        "display": "Overte Android Phone",
    },
    "pico": {
        "adapter": "android-pico-adb",
        "package": "org.overte.pico",
        "activity": "org.overte.pico/.PermissionsActivity",
        "display": "Overte Pico",
    },
}

ANDROID_DEBUG_PROBE = "files/overte-e2e/overte-probe.json"


def cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=tuple(PROFILES), required=True)
    parser.add_argument("action", choices=("discover", "describe", "invoke", "cleanup"))
    parser.add_argument("--target")
    parser.add_argument("--operation")
    parser.add_argument("--arguments", default="{}")
    return parser.parse_args()


class AndroidAdapter:
    def __init__(self, kind: str) -> None:
        self.kind = kind
        self.profile = PROFILES[kind]
        self.pico_configuration: tuple[int, Path] | None = None
        if self.kind == "pico" and pico_openxr_opted_in():
            self.pico_configuration = validate_pico_openxr_configuration()
        self.adb = AdbTransport(
            server_port=(self.pico_configuration[0]
                         if self.pico_configuration is not None else None))

    def is_pico(self, target: str) -> bool:
        identity = " ".join(self.adb.prop(target, item) for item in (
            "ro.product.manufacturer", "ro.product.brand", "ro.product.model", "ro.product.device"
        )).lower()
        return "pico" in identity or "bytedance" in identity

    def eligible(self, target: str) -> bool:
        pico = self.is_pico(target)
        if self.kind == "pico":
            abis = self.adb.prop(target, "ro.product.cpu.abilist").split(",")
            sdk = self.adb.prop(target, "ro.build.version.sdk")
            gles = self.adb.prop(target, "ro.opengles.version")
            return (pico and "arm64-v8a" in abis and sdk.isdigit() and int(sdk) >= 26
                    and gles.isdigit() and int(gles) >= 196610)
        if pico:
            return False
        characteristics = self.adb.prop(target, "ro.build.characteristics").lower().split(",")
        abis = self.adb.prop(target, "ro.product.cpu.abilist").split(",")
        sdk = self.adb.prop(target, "ro.build.version.sdk")
        gles = self.adb.prop(target, "ro.opengles.version")
        features = self.adb.shell(target, "pm", "list", "features", check=False).splitlines()
        return (not {"watch", "tv", "automotive", "vr"}.intersection(characteristics)
                and "arm64-v8a" in abis and sdk.isdigit() and int(sdk) >= 26
                and gles.isdigit() and int(gles) >= 196610
                and "feature:android.hardware.touchscreen" in features)

    def capabilities(self) -> list[str]:
        values = ["app.foreground", "app.launch", "app.process",
                  "lifecycle.background", "telemetry.snapshot"]
        if os.environ.get("OVERTE_ANDROID_E2E_DEBUG") == "1":
            values += ["probe.snapshot", "scene.load"]
        if self.kind == "pico" and os.environ.get("OVERTE_PICO_OPENXR_INPUT") == "1":
            # An explicit opt-in with incomplete isolation is a configuration
            # error, not a silent capability downgrade.
            validate_pico_openxr_configuration()
            values += ["input.look", "input.move", "tablet.close", "tablet.open"]
        return sorted(values)

    def pico_input_session(self, target: str) -> PicoOpenXrAdapterSession:
        if self.kind != "pico" or not pico_openxr_opted_in():
            fail("Pico OpenXR input requires an E2E Debug APK and explicit opt-in")
        if self.pico_configuration is None:
            fail("Pico OpenXR input isolation is not configured")
        port, state_directory = self.pico_configuration
        transport = AndroidOpenXrTransport(
            self.adb.executable, target, server_port=port)
        return PicoOpenXrAdapterSession(transport, target, state_directory)

    def wait_for_process_identity(self, target: str, timeout_seconds: float = 30.0) -> str:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            state = self.adb.process_state(target, self.profile["package"])
            identity = state.get("identity")
            if state.get("running") is True and isinstance(identity, str) and identity:
                return identity
            time.sleep(0.25)
        fail("Android E2E launcher process did not start")

    def launch_debug_app(self, target: str) -> str | None:
        package = self.profile["package"]
        running = self.adb.process_state(target, package)["running"] is True
        isolated_pico = self.kind == "pico" and pico_openxr_opted_in()
        if isolated_pico:
            if running:
                fail("Pico E2E launcher must be stopped before its single launch")
            session = self.pico_input_session(target)
            session.cleanup(False)
            session.discard_local_state()
        elif running:
            self.adb.shell(target, "am", "force-stop", package)
        self.adb.shell(target, "am", "start", "-W", "-n",
                       f"{package}/.E2eLauncherActivity")
        if not isolated_pico:
            return None
        identity = self.wait_for_process_identity(target)
        self.pico_input_session(target).begin(identity)
        return identity

    def require_pico_session_identity(self, target: str) -> str:
        state = self.adb.process_state(target, self.profile["package"])
        identity = state.get("identity")
        if state.get("running") is not True or not isinstance(identity, str) or not identity:
            fail("Pico E2E launcher process is not running")
        self.pico_input_session(target).require_process_identity(identity)
        return identity

    @staticmethod
    def probe_retry_policy() -> tuple[int, float]:
        attempts_raw = os.environ.get("OVERTE_ANDROID_E2E_PROBE_ATTEMPTS", "60")
        interval_raw = os.environ.get("OVERTE_ANDROID_E2E_PROBE_POLL_SECONDS", "0.25")
        if not attempts_raw.isdigit() or not 1 <= int(attempts_raw) <= 120:
            fail("OVERTE_ANDROID_E2E_PROBE_ATTEMPTS must be from 1 through 120")
        try:
            interval = float(interval_raw)
        except ValueError:
            fail("OVERTE_ANDROID_E2E_PROBE_POLL_SECONDS must be numeric")
        if not 0.01 <= interval <= 1.0:
            fail("OVERTE_ANDROID_E2E_PROBE_POLL_SECONDS must be from 0.01 through 1.0")
        return int(attempts_raw), interval

    def read_probe_snapshot(self, target: str, package: str,
                            after_sequence: int | None) -> dict:
        attempts, interval = self.probe_retry_policy()
        for attempt in range(attempts):
            raw = self.adb.read_debug_app_file(
                target, package, ANDROID_DEBUG_PROBE, attempts=1)
            try:
                snapshot = require_fresh_snapshot(json.loads(raw))
            except (json.JSONDecodeError, RuntimeError):
                snapshot = None
            if snapshot is not None:
                sequence = snapshot.get("sampleSequence")
                sequence_valid = (isinstance(sequence, int)
                                  and not isinstance(sequence, bool) and sequence > 0)
                if ((self.kind != "pico" or sequence_valid)
                        and (after_sequence is None
                             or (sequence_valid and sequence > after_sequence))):
                    return snapshot
            if attempt + 1 < attempts:
                time.sleep(interval)
        fail("Android probe snapshot is unavailable, stale, or did not advance")

    def discover(self) -> list[dict]:
        targets = []
        for selector in self.adb.authorized_targets():
            if not self.eligible(selector):
                continue
            model = self.adb.prop(selector, "ro.product.model") or self.profile["display"]
            targets.append({
                "selector": selector,
                "displayName": model,
                "platform": "android",
                "physical": self.adb.prop(selector, "ro.kernel.qemu") != "1",
                "capabilities": self.capabilities(),
            })
        return targets

    def require(self, target: str) -> None:
        self.adb.require_connected(target)
        if not self.eligible(target):
            fail("target does not satisfy this Android adapter profile")

    def describe(self, target: str) -> dict:
        self.require(target)
        return {
            "adapter": self.profile["adapter"],
            "kind": self.kind,
            "os": "Android",
            "osVersion": self.adb.prop(target, "ro.build.version.release") or None,
            "sdk": self.adb.prop(target, "ro.build.version.sdk") or None,
        }

    def invoke(self, target: str, operation: str, values: dict) -> dict:
        self.require(target)
        package = self.profile["package"]
        if operation == "app.install":
            apk = values.get("path")
            if not isinstance(apk, str) or not Path(apk).is_file():
                fail("app.install requires an existing APK path")
            arguments = ["install", "-r", "-g"]
            self.adb.execute([*arguments, str(Path(apk).resolve())], target=target, timeout=180)
            return {"installed": True}
        if operation == "app.launch":
            if os.environ.get("OVERTE_ANDROID_E2E_DEBUG") == "1":
                self.launch_debug_app(target)
            else:
                self.adb.shell(target, "am", "start", "-W", "-n", self.profile["activity"])
            return {"launched": True}
        if operation == "app.process":
            state = self.adb.process_state(target, package)
            if self.kind == "pico" and pico_openxr_opted_in():
                identity = state.get("identity")
                if (state.get("running") is not True or not isinstance(identity, str)
                        or not identity):
                    fail("Pico E2E launcher process is not running")
                self.pico_input_session(target).require_process_identity(identity)
            return state
        if operation == "app.foreground":
            if self.kind == "pico" and pico_openxr_opted_in():
                self.require_pico_session_identity(target)
            return {"foreground": self.adb.foreground_package(target) == package}
        if operation == "lifecycle.background":
            self.adb.shell(target, "input", "keyevent", "KEYCODE_HOME")
            return {"backgrounded": True}
        if operation == "telemetry.snapshot":
            return self.adb.telemetry_snapshot(target, package)
        if operation == "scene.load":
            url = values.get("url")
            if url != EMBEDDED_FIXTURE_URL:
                fail("Android debug scene.load accepts only the embedded fixture URL")
            if os.environ.get("OVERTE_ANDROID_E2E_DEBUG") != "1":
                fail("scene.load requires an E2E-enabled debug APK")
            if self.kind == "pico" and pico_openxr_opted_in():
                self.require_pico_session_identity(target)
            else:
                self.launch_debug_app(target)
            return {"requested": True, "verification": "fixture-markers"}
        if operation == "probe.snapshot":
            if os.environ.get("OVERTE_ANDROID_E2E_DEBUG") != "1":
                fail("probe.snapshot requires an E2E-enabled debug APK")
            if self.kind == "pico" and pico_openxr_opted_in():
                self.require_pico_session_identity(target)
            unexpected = set(values) - {"afterSampleSequence"}
            if unexpected:
                fail("probe.snapshot arguments are unsupported")
            after_sequence = values.get("afterSampleSequence")
            if (after_sequence is not None and (
                    not isinstance(after_sequence, int) or isinstance(after_sequence, bool)
                    or after_sequence < 0)):
                fail("afterSampleSequence must be a non-negative integer")
            return self.read_probe_snapshot(target, package, after_sequence)
        if operation in {"input.look", "input.move", "tablet.open", "tablet.close"}:
            identity = self.require_pico_session_identity(target)
            return self.pico_input_session(target).stage(identity, operation, values)
        fail(f"unsupported operation: {operation}")

    def cleanup(self, target: str) -> dict:
        self.adb.require_connected(target)
        package = self.profile["package"]
        running = self.adb.process_state(target, package)["running"] is True
        cleanup_error = None
        session = None
        if self.kind == "pico" and pico_openxr_opted_in():
            session = self.pico_input_session(target)
            try:
                session.cleanup(running)
            except RuntimeError as error:
                cleanup_error = error
        if running:
            self.adb.shell(target, "am", "force-stop", package, check=False)
        if session is not None:
            session.discard_local_state()
        if cleanup_error is not None:
            raise cleanup_error
        return {"cleaned": True}


def main() -> int:
    args = cli()
    adapter = AndroidAdapter(args.kind)
    if args.action == "discover":
        emit(adapter.discover())
        return 0
    if not args.target:
        fail(f"{args.action} requires --target")
    if args.action == "describe":
        emit(adapter.describe(args.target))
    elif args.action == "cleanup":
        emit(adapter.cleanup(args.target))
    else:
        if not args.operation:
            fail("invoke requires --operation")
        emit(adapter.invoke(args.target, args.operation,
                            parse_operation_arguments(args.arguments)))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
