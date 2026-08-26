#!/usr/bin/env python3
"""Mock-ADB tests for the Android Phone device-harness adapter."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ADAPTER = Path(__file__).resolve().parents[1] / "adapter.py"
GENERIC_ANDROID_ADAPTER = (
    ADAPTER.parents[3] / "tests/device/adapters/android/adapter.py")

MOCK_ADB = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
target = None
if args[:1] == ["-s"]:
    target, args = args[1], args[2:]
state = pathlib.Path(os.environ["MOCK_ADB_STATE"])
log = pathlib.Path(os.environ["MOCK_ADB_LOG"])
if args[:2] == ["devices", "-l"]:
    print("List of devices attached")
    if os.environ.get("MOCK_UNAUTHORIZED") != "1":
        print("private-phone device usb:1-1 model:Mock_Phone")
    raise SystemExit()
if target != "private-phone":
    raise SystemExit(3)
if args == ["get-state"]:
    print("device")
    raise SystemExit()
if args[:1] != ["shell"]:
    raise SystemExit(3)
shell = args[1:]
with log.open("a", encoding="utf-8") as output:
    output.write(json.dumps(shell) + "\n")
props = {
 "ro.product.manufacturer":os.environ.get("MOCK_MANUFACTURER", "Example"),
 "ro.product.brand":os.environ.get("MOCK_BRAND", "Example"),
 "ro.product.model":os.environ.get("MOCK_MODEL", "Phone"),
 "ro.product.device":os.environ.get("MOCK_DEVICE", "phone"),
 "ro.build.characteristics":os.environ.get("MOCK_CHARACTERISTICS", "default"),
 "ro.product.cpu.abilist":"arm64-v8a,armeabi-v7a",
 "ro.build.version.sdk":"36", "ro.build.version.release":"16",
 "ro.opengles.version":"196610", "ro.kernel.qemu":os.environ.get("MOCK_QEMU", "0")}
if shell[:1] == ["getprop"]:
    print(props.get(shell[1], ""))
elif shell == ["pm", "list", "features"]:
    print("feature:android.hardware.touchscreen")
elif shell == ["pm", "path", "org.overte.phone"]:
    if os.environ.get("MOCK_PACKAGE_MISSING") != "1":
        print("package:/data/app/mock/org.overte.phone/base.apk")
elif shell == ["pidof", "-s", "org.overte.phone"]:
    if not state.exists() or state.read_text() != "stopped":
        print("4343" if state.exists() and state.read_text() == "restarted" else "4242")
elif shell == ["cat", "/proc/4242/stat"]:
    print("4242 (overte) S " + "0 " * 18 + "98765 0")
elif shell == ["cat", "/proc/4343/stat"]:
    print("4343 (overte) S " + "0 " * 18 + "12345 0")
elif shell == ["dumpsys", "activity", "activities"]:
    foreground = (not state.exists()
                  or state.read_text() in {"foreground", "restarted"})
    print("mResumedActivity: org.overte.phone/.PhoneInterfaceActivity" if foreground else
          "mResumedActivity: com.android.launcher/.Launcher")
elif shell == ["dumpsys", "input"]:
    if os.environ.get("MOCK_PORTRAIT") == "1":
        print("DisplayViewport{orientation=0, logicalFrame=[0, 0, 1080, 2400]}")
    else:
        print("DisplayViewport{orientation=1, logicalFrame=[0, 0, 2400, 1080]}")
elif shell == ["wm", "density"]:
    print("Physical density: 420")
elif shell == ["wm", "size"]:
    print("Physical size: 1080x2400")
elif shell == ["dumpsys", "meminfo", "org.overte.phone"]:
    print(" TOTAL 123456 234567 0 0")
elif shell == ["dumpsys", "battery"]:
    print("  level: 81\n  temperature: 298")
elif shell == ["dumpsys", "thermalservice"]:
    print("Thermal Status: 2")
elif shell[:4] == ["am", "start", "-W", "-n"]:
    state.write_text("foreground")
elif shell == ["am", "force-stop", "org.overte.phone"]:
    state.write_text("stopped")
elif shell == ["am", "start", "-W", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.HOME"]:
    state.write_text("background")
elif shell[:3] == ["input", "touchscreen", "swipe"]:
    if os.environ.get("MOCK_RESTART_AFTER_INPUT") == "1":
        state.write_text("restarted")
    if os.environ.get("MOCK_INPUT_FAIL") == "1":
        raise SystemExit(9)
elif shell[:4] == ["input", "touchscreen", "motionevent", "UP"]:
    pass
else:
    print("unexpected mock adb command: " + repr(shell), file=sys.stderr)
    raise SystemExit(4)
'''


class AndroidPhoneAdapterTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="phone-adapter-test-")
        self.root = Path(self.temporary.name)
        self.adb = self.root / "adb"
        self.state = self.root / "state"
        self.log = self.root / "adb-log"
        self.adb.write_text(MOCK_ADB, encoding="utf-8")
        self.adb.chmod(0o700)
        self.environment = os.environ.copy()
        self.environment.pop("OVERTE_ANDROID_PHONE_E2E_INPUT", None)
        self.environment.update({"OVERTE_ANDROID_ADB": str(self.adb),
                                 "MOCK_ADB_STATE": str(self.state),
                                 "MOCK_ADB_LOG": str(self.log)})

    def tearDown(self):
        self.temporary.cleanup()

    def call(self, *arguments: str, environment: dict[str, str] | None = None):
        env = self.environment | (environment or {})
        return subprocess.run([sys.executable, str(ADAPTER), *arguments], text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=env, check=False)

    def invoke(self, operation: str, arguments: dict | None = None,
               environment: dict[str, str] | None = None) -> dict:
        result = self.call(
            "invoke", "--target", "private-phone", "--operation", operation,
            "--arguments", json.dumps(arguments or {}), environment=environment)
        self.assertEqual(0, result.returncode, result.stderr)
        return json.loads(result.stdout)

    def invoke_failure(self, operation: str, arguments: object,
                       environment: dict[str, str] | None = None):
        return self.call(
            "invoke", "--target", "private-phone", "--operation", operation,
            "--arguments", json.dumps(arguments), environment=environment)

    def commands(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]

    @staticmethod
    def input_commands(commands: list[list[str]]) -> list[list[str]]:
        return [command for command in commands if command[:2] == ["input", "touchscreen"]]

    def test_discovers_supported_physical_phone_with_sorted_capabilities(self):
        result = self.call("discover")
        self.assertEqual(0, result.returncode, result.stderr)
        targets = json.loads(result.stdout)
        self.assertEqual(1, len(targets))
        self.assertTrue(targets[0]["physical"])
        self.assertEqual(sorted(targets[0]["capabilities"]), targets[0]["capabilities"])

    def test_rejects_emulator(self):
        result = self.call("discover", environment={"MOCK_QEMU": "1"})
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([], json.loads(result.stdout))

    def test_input_capabilities_require_exact_phone_opt_in(self):
        for value, expected in ((None, False), ("true", False), ("0", False),
                                ("1", True)):
            environment = ({"OVERTE_ANDROID_PHONE_E2E_INPUT": value}
                           if value is not None else {})
            result = self.call("discover", environment=environment)
            self.assertEqual(0, result.returncode, result.stderr)
            capabilities = json.loads(result.stdout)[0]["capabilities"]
            self.assertEqual(expected, "input.jump" in capabilities)
            self.assertEqual(expected, "input.fly" in capabilities)

        result = self.invoke_failure("input.jump", {})
        self.assertEqual(2, result.returncode)
        self.assertEqual([], self.input_commands(self.commands()))

    def test_input_capabilities_do_not_activate_on_pico_or_foreign_profiles(self):
        opt_in = {"OVERTE_ANDROID_PHONE_E2E_INPUT": "1"}
        for profile in ({"MOCK_MANUFACTURER": "PICO"},
                        {"MOCK_CHARACTERISTICS": "tv"},
                        {"MOCK_CHARACTERISTICS": "vr"}):
            result = self.call("discover", environment=opt_in | profile)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual([], json.loads(result.stdout))

        for kind, profile in (("phone", {}),
                              ("pico", {"MOCK_MANUFACTURER": "PICO"})):
            result = subprocess.run(
                [sys.executable, str(GENERIC_ANDROID_ADAPTER), "--kind", kind,
                 "discover"], text=True, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self.environment | opt_in | profile, check=False)
            self.assertEqual(0, result.returncode, result.stderr)
            capabilities = json.loads(result.stdout)[0]["capabilities"]
            self.assertNotIn("input.jump", capabilities)
            self.assertNotIn("input.fly", capabilities)

    def test_description_does_not_persist_selector(self):
        result = self.call("describe", "--target", "private-phone")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn("private-phone", result.stdout)
        self.assertEqual("android-phone", json.loads(result.stdout)["platform"])

    def test_launch_lifecycle_process_telemetry_and_cleanup(self):
        self.assertTrue(self.invoke("app.launch")["launched"])
        identity = self.invoke("app.process")["identity"]
        self.assertTrue(identity.startswith("4242:"))
        self.assertTrue(self.invoke("app.foreground")["foreground"])
        self.invoke("lifecycle.background")
        self.assertFalse(self.invoke("app.foreground")["foreground"])
        telemetry = self.invoke("telemetry.snapshot")
        self.assertEqual(123456, telemetry["memoryPssKb"])
        self.assertEqual(2, telemetry["thermalStatus"])
        for _ in range(2):
            result = self.call("cleanup", "--target", "private-phone")
            self.assertEqual(0, result.returncode, result.stderr)

    def test_jump_and_fly_reject_unknown_or_additional_arguments(self):
        opt_in = {"OVERTE_ANDROID_PHONE_E2E_INPUT": "1"}
        for operation, arguments in (
                ("input.jump", []),
                ("input.jump", {"unexpected": True}),
                ("input.fly", {}),
                ("input.fly", {"durationSeconds": 1.0, "unexpected": True})):
            result = self.invoke_failure(operation, arguments, opt_in)
            self.assertEqual(2, result.returncode)
        self.assertEqual([], self.commands())

    def test_fly_rejects_non_numeric_non_finite_and_out_of_range_durations(self):
        opt_in = {"OVERTE_ANDROID_PHONE_E2E_INPUT": "1"}
        for duration in (None, True, "1", float("nan"), float("inf"),
                         -float("inf"), 0.0, 0.099, 10.001):
            result = self.invoke_failure(
                "input.fly", {"durationSeconds": duration}, opt_in)
            self.assertEqual(2, result.returncode, (duration, result.stderr))
        self.assertEqual([], self.commands())

    def test_jump_and_fly_use_bounded_touch_and_neutralize_after_success(self):
        opt_in = {"OVERTE_ANDROID_PHONE_E2E_INPUT": "1"}
        self.assertEqual({"performed": True},
                         self.invoke("input.jump", environment=opt_in))
        jump_input = self.input_commands(self.commands())
        self.assertEqual("swipe", jump_input[-2][2])
        self.assertEqual("120", jump_input[-2][-1])
        self.assertEqual(["input", "touchscreen", "motionevent", "UP"],
                         jump_input[-1][:4])

        self.log.unlink()
        self.assertEqual(
            {"performed": True},
            self.invoke("input.fly", {"durationSeconds": 0.25}, opt_in))
        fly_input = self.input_commands(self.commands())
        self.assertEqual("swipe", fly_input[-2][2])
        self.assertEqual("250", fly_input[-2][-1])
        self.assertEqual(["input", "touchscreen", "motionevent", "UP"],
                         fly_input[-1][:4])

    def test_fly_accepts_both_shared_duration_boundaries(self):
        opt_in = {"OVERTE_ANDROID_PHONE_E2E_INPUT": "1"}
        for duration, milliseconds in ((0.1, "100"), (10.0, "10000")):
            if self.log.exists():
                self.log.unlink()
            self.assertEqual(
                {"performed": True},
                self.invoke("input.fly", {"durationSeconds": duration}, opt_in))
            input_commands = self.input_commands(self.commands())
            self.assertEqual(milliseconds, input_commands[-2][-1])
            self.assertEqual(
                ["input", "touchscreen", "motionevent", "UP"],
                input_commands[-1][:4])

    def test_failed_touch_is_neutralized(self):
        environment = {"OVERTE_ANDROID_PHONE_E2E_INPUT": "1",
                       "MOCK_INPUT_FAIL": "1"}
        result = self.invoke_failure("input.fly", {"durationSeconds": 0.1},
                                     environment)
        self.assertEqual(2, result.returncode)
        input_commands = self.input_commands(self.commands())
        self.assertEqual("swipe", input_commands[-2][2])
        self.assertEqual(["input", "touchscreen", "motionevent", "UP"],
                         input_commands[-1][:4])

    def test_input_requires_expected_foreground_process_and_package(self):
        opt_in = {"OVERTE_ANDROID_PHONE_E2E_INPUT": "1"}
        for state, extra_environment in (
                ("background", {}),
                ("foreground", {"MOCK_PACKAGE_MISSING": "1"})):
            self.state.write_text(state, encoding="utf-8")
            if self.log.exists():
                self.log.unlink()
            result = self.invoke_failure("input.jump", {},
                                         opt_in | extra_environment)
            self.assertEqual(2, result.returncode)
            self.assertEqual([], self.input_commands(self.commands()))

    def test_input_rejects_process_change_after_neutralizing(self):
        environment = {"OVERTE_ANDROID_PHONE_E2E_INPUT": "1",
                       "MOCK_RESTART_AFTER_INPUT": "1"}
        result = self.invoke_failure("input.jump", {}, environment)
        self.assertEqual(2, result.returncode)
        self.assertIn("process changed", result.stderr)
        input_commands = self.input_commands(self.commands())
        self.assertEqual(["input", "touchscreen", "motionevent", "UP"],
                         input_commands[-1][:4])

    def test_cleanup_neutralizes_without_persisting_settings(self):
        environment = {"OVERTE_ANDROID_PHONE_E2E_INPUT": "1"}
        for _ in range(2):
            result = self.call("cleanup", "--target", "private-phone",
                               environment=environment)
            self.assertEqual(0, result.returncode, result.stderr)
        commands = self.commands()
        input_commands = self.input_commands(commands)
        self.assertEqual(2, sum(command[2:4] == ["motionevent", "UP"]
                                for command in input_commands))
        self.assertFalse(any(command[:1] == ["settings"] for command in commands))

    def test_portrait_layout_fails_before_touch(self):
        environment = {"OVERTE_ANDROID_PHONE_E2E_INPUT": "1",
                       "MOCK_PORTRAIT": "1"}
        result = self.invoke_failure("input.jump", {}, environment)
        self.assertEqual(2, result.returncode)
        self.assertEqual([], self.input_commands(self.commands()))


if __name__ == "__main__":
    unittest.main()
