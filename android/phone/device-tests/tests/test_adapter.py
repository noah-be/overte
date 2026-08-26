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
JENKINSFILE = ADAPTER.parent / "Jenkinsfile"
GENERIC_ANDROID_ADAPTER = (
    ADAPTER.parents[3] / "tests/device/adapters/android/adapter.py")

MOCK_ADB = r'''#!/usr/bin/env python3
import json, os, pathlib, sys, time
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
                  or state.read_text() in {"foreground", "restarted", "spawned",
                                           "spawned-disabled", "spawned-restored"})
    print("mResumedActivity: org.overte.phone/.PhoneInterfaceActivity" if foreground else
          "mResumedActivity: com.android.launcher/.Launcher")
elif shell == ["dumpsys", "input"]:
    if os.environ.get("MOCK_PORTRAIT") == "1":
        print("DisplayViewport{orientation=0, logicalFrame=[0, 0, 1080, 2400]}")
    else:
        print("DisplayViewport{orientation=1, logicalFrame=[0, 0, 2400, 1080]}")
elif shell == ["dumpsys", "display"]:
    if os.environ.get("MOCK_DISPLAY_DPI_MISSING") != "1":
        print("DisplayDeviceInfo{density 420, 423.5 x 416.5 dpi}")
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
elif shell == ["run-as", "org.overte.phone", "cat", "files/overte-e2e/overte-probe.json"]:
    if os.environ.get("MOCK_PROBE_MISSING") != "1":
        sampled = 1 if os.environ.get("MOCK_PROBE_STALE") == "1" else int(time.time() * 1000)
        markers = int(os.environ.get("MOCK_FIXTURE_MARKERS", "4"))
        print(json.dumps({
            "schemaVersion": 1,
            "sampleEpochMs": sampled,
            "sampleSequence": int(os.environ.get("MOCK_SAMPLE_SEQUENCE", "4")),
            "scene": {
                "fixtureMarkerCount": markers,
                "ready": (state.exists()
                          and state.read_text().startswith("spawned")
                          and os.environ.get("MOCK_SCENE_NEVER_READY") != "1"),
            },
            "avatar": {
                "inAir": False,
                "flying": False,
                "flyingEnabled": state.exists() and state.read_text() == "spawned",
                "position": {"x": 0, "y": 1, "z": 4},
            },
        }))
        if os.environ.get("MOCK_RESTART_AFTER_PROBE_READ") == "1":
            state.write_text("restarted")
elif shell[:4] == ["am", "start", "-W", "-n"]:
    if shell[4].endswith("E2eFlightControlActivity"):
        mode = shell[-1]
        if mode == "1":
            state.write_text("spawned")
        elif mode == "0":
            state.write_text("spawned-disabled")
        elif mode == "-1":
            state.write_text("spawned-restored")
        else:
            raise SystemExit(5)
    else:
        state.write_text("spawned-disabled"
                         if shell[4].endswith("E2eLauncherActivity")
                         else "foreground")
elif shell == ["am", "force-stop", "org.overte.phone"]:
    state.write_text("stopped")
elif shell == ["am", "start", "-W", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.HOME"]:
    state.write_text("background")
elif shell[:4] == ["input", "touchscreen", "motionevent", "DOWN"]:
    if os.environ.get("MOCK_RESTART_AFTER_INPUT") == "1":
        state.write_text("restarted")
    if os.environ.get("MOCK_INPUT_FAIL") == "1":
        raise SystemExit(9)
elif shell[:4] == ["input", "touchscreen", "motionevent", "UP"]:
    if os.environ.get("MOCK_INPUT_UP_FAIL") == "1":
        raise SystemExit(9)
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
        self.environment.pop("OVERTE_ANDROID_E2E_DEBUG", None)
        self.environment.update({"OVERTE_ANDROID_ADB": str(self.adb),
                                 "MOCK_ADB_STATE": str(self.state),
                                 "MOCK_ADB_LOG": str(self.log),
                                 "OVERTE_ANDROID_PHONE_E2E_STATE_ROOT":
                                     str(self.root / "host-state")})

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
        self.assertNotIn("app.stop", targets[0]["capabilities"])

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

    def test_debug_capabilities_require_exact_phone_opt_in(self):
        for value, expected in ((None, False), ("true", False), ("0", False),
                                ("1", True)):
            environment = ({"OVERTE_ANDROID_E2E_DEBUG": value}
                           if value is not None else {})
            result = self.call("discover", environment=environment)
            self.assertEqual(0, result.returncode, result.stderr)
            capabilities = json.loads(result.stdout)[0]["capabilities"]
            self.assertEqual(expected, "probe.snapshot" in capabilities)
            self.assertEqual(expected, "scene.load" in capabilities)
            self.assertNotIn("input.jump", capabilities)
            self.assertNotIn("input.fly", capabilities)

        pico = self.call(
            "discover", environment={"OVERTE_ANDROID_E2E_DEBUG": "1",
                                     "MOCK_MANUFACTURER": "PICO"})
        self.assertEqual(0, pico.returncode, pico.stderr)
        self.assertEqual([], json.loads(pico.stdout))

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

    def test_debug_scene_uses_only_shared_startup_url(self):
        debug = {"OVERTE_ANDROID_E2E_DEBUG": "1"}
        result = self.invoke(
            "scene.load", {"url": "overte-e2e://fixture/scene"}, debug)
        self.assertEqual(
            {"requested": True, "verification": "fixture-markers"}, result)

        commands = self.commands()
        self.assertIn(
            ["am", "start", "-W", "-n",
             "org.overte.phone/.E2eLauncherActivity"], commands)
        launches = [command for command in commands
                    if command[:3] == ["am", "start", "-W"]]
        self.assertEqual(
            [["am", "start", "-W", "-n",
              "org.overte.phone/.E2eLauncherActivity"],
             ["am", "start", "-W", "-n",
              "org.overte.phone/.E2eFlightControlActivity", "--ei",
              "org.overte.phone.e2e.FLIGHT_MODE", "0"],
             ["am", "start", "-W", "-n",
              "org.overte.phone/.E2eFlightControlActivity", "--ei",
              "org.overte.phone.e2e.FLIGHT_MODE", "1"]], launches)
        self.assertFalse(any(command[:3] == ["am", "start", "-W"]
                             and "android.intent.action.VIEW" in command
                             for command in commands))
        self.assertFalse(any(command[:2] == ["input", "text"]
                             for command in commands))
        probe_reads = [command for command in commands
                       if command[:3] == ["run-as", "org.overte.phone", "cat"]]
        self.assertGreaterEqual(len(probe_reads), 2)
        self.assertFalse(any(command[:1] == ["settings"] for command in commands))

        snapshot = self.invoke("probe.snapshot", environment=debug)
        self.assertEqual(4, snapshot["scene"]["fixtureMarkerCount"])
        self.assertTrue(snapshot["scene"]["ready"])
        self.assertFalse(snapshot["avatar"]["inAir"])
        self.assertFalse(snapshot["avatar"]["flying"])
        self.assertTrue(snapshot["avatar"]["flyingEnabled"])
        session_files = list((self.root / "host-state").glob("*/debug-session.json"))
        self.assertEqual(1, len(session_files))
        self.assertNotIn("private-phone", session_files[0].read_text(encoding="utf-8"))
        cleaned = self.call(
            "cleanup", "--target", "private-phone", environment=debug)
        self.assertEqual(0, cleaned.returncode, cleaned.stderr)
        self.assertEqual(
            [], list((self.root / "host-state").glob("*/debug-session.json")))
        self.assertIn(
            ["am", "start", "-W", "-n",
             "org.overte.phone/.E2eFlightControlActivity", "--ei",
             "org.overte.phone.e2e.FLIGHT_MODE", "-1"],
            self.commands())
        self.assertFalse(any(command[:1] == ["settings"] for command in self.commands()))

    def test_debug_operations_reject_bad_arguments_and_missing_opt_in(self):
        debug = {"OVERTE_ANDROID_E2E_DEBUG": "1"}
        cases = (
            ("scene.load", {}, debug),
            ("scene.load", {"url": "https://example.invalid/scene.json"}, debug),
            ("scene.load", {"url": "overte-e2e://fixture/scene", "extra": 1}, debug),
            ("probe.snapshot", {"unknown": True}, debug),
            ("probe.snapshot", {"afterSampleSequence": True}, debug),
            ("probe.snapshot", {"afterSampleSequence": -1}, debug),
            ("probe.snapshot", {}, {}),
            ("scene.load", {"url": "overte-e2e://fixture/scene"}, {}),
        )
        for operation, arguments, environment in cases:
            result = self.invoke_failure(operation, arguments, environment)
            self.assertEqual(2, result.returncode, (operation, result.stderr))
        self.assertEqual([], self.commands())

    def test_probe_requires_bound_unchanged_process_and_accepts_newer_sequence(self):
        debug = {"OVERTE_ANDROID_E2E_DEBUG": "1"}
        self.invoke("app.launch", environment=debug)
        snapshot = self.invoke(
            "probe.snapshot", {"afterSampleSequence": 3}, debug)
        self.assertEqual(4, snapshot["sampleSequence"])

        if self.log.exists():
            self.log.unlink()
        changed = self.invoke_failure(
            "probe.snapshot", {},
            debug | {"MOCK_RESTART_AFTER_PROBE_READ": "1"})
        self.assertEqual(2, changed.returncode)
        self.assertIn("process changed", changed.stderr)
        self.assertTrue(any(command[:3] == ["run-as", "org.overte.phone", "cat"]
                            for command in self.commands()))

        if self.log.exists():
            self.log.unlink()
        missing_session_root = self.root / "host-state"
        for session in missing_session_root.glob("*/debug-session.json"):
            session.unlink()
        missing = self.invoke_failure("probe.snapshot", {}, debug)
        self.assertEqual(2, missing.returncode)
        self.assertIn("session is unavailable", missing.stderr)
        self.assertFalse(any(command[:1] == ["run-as"] for command in self.commands()))

    def test_failed_scene_import_stops_process_and_discards_session(self):
        environment = {
            "OVERTE_ANDROID_E2E_DEBUG": "1",
            "MOCK_FIXTURE_MARKERS": "0",
            "OVERTE_ANDROID_E2E_PROBE_ATTEMPTS": "3",
            "OVERTE_ANDROID_E2E_PROBE_POLL_SECONDS": "0.01",
        }
        result = self.invoke_failure(
            "scene.load", {"url": "overte-e2e://fixture/scene"}, environment)
        self.assertEqual(2, result.returncode)
        self.assertIn("controlled fixture did not become ready", result.stderr)
        self.assertIn(["am", "force-stop", "org.overte.phone"], self.commands())
        self.assertEqual(
            [], list((self.root / "host-state").glob("*/debug-session.json")))
        self.assertFalse(any(command[:1] == ["settings"] for command in self.commands()))

    def test_scene_never_ready_fails_closed_without_fallback_navigation(self):
        environment = {
            "OVERTE_ANDROID_E2E_DEBUG": "1",
            "MOCK_SCENE_NEVER_READY": "1",
            "OVERTE_ANDROID_E2E_PROBE_ATTEMPTS": "3",
            "OVERTE_ANDROID_E2E_PROBE_POLL_SECONDS": "0.01",
        }
        result = self.invoke_failure(
            "scene.load", {"url": "overte-e2e://fixture/scene"}, environment)
        self.assertEqual(2, result.returncode)
        self.assertIn("controlled fixture did not become ready", result.stderr)
        commands = self.commands()
        launches = [command for command in commands
                    if command[:3] == ["am", "start", "-W"]]
        self.assertEqual(
            [["am", "start", "-W", "-n",
              "org.overte.phone/.E2eLauncherActivity"],
             ["am", "start", "-W", "-n",
              "org.overte.phone/.E2eFlightControlActivity", "--ei",
              "org.overte.phone.e2e.FLIGHT_MODE", "-1"]], launches)
        self.assertFalse(any(command[-1:] == ["1"]
                             and command[:4] == ["am", "start", "-W", "-n"]
                             for command in launches))
        self.assertIn(["am", "force-stop", "org.overte.phone"], commands)
        self.assertEqual(
            [], list((self.root / "host-state").glob("*/debug-session.json")))
        self.assertFalse(any(command[:1] in (["input"], ["settings"])
                             for command in commands))

    def test_scene_rejects_process_replacement_and_discards_session(self):
        environment = {
            "OVERTE_ANDROID_E2E_DEBUG": "1",
            "MOCK_RESTART_AFTER_PROBE_READ": "1",
            "OVERTE_ANDROID_E2E_PROBE_ATTEMPTS": "3",
            "OVERTE_ANDROID_E2E_PROBE_POLL_SECONDS": "0.01",
        }
        result = self.invoke_failure(
            "scene.load", {"url": "overte-e2e://fixture/scene"}, environment)
        self.assertEqual(2, result.returncode)
        self.assertIn("process changed", result.stderr)
        self.assertIn(["am", "force-stop", "org.overte.phone"], self.commands())
        self.assertEqual(
            [], list((self.root / "host-state").glob("*/debug-session.json")))

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
        self.assertEqual(["input", "touchscreen", "motionevent", "DOWN"],
                         jump_input[-2][:4])
        self.assertEqual(["input", "touchscreen", "motionevent", "UP"],
                         jump_input[-1][:4])
        commands = self.commands()
        self.assertEqual(1, commands.count(["pm", "path", "org.overte.phone"]))
        self.assertEqual(1, commands.count(
            ["dumpsys", "activity", "activities"]))

        self.log.unlink()
        self.assertEqual(
            {"performed": True},
            self.invoke("input.fly", {"durationSeconds": 0.25}, opt_in))
        fly_input = self.input_commands(self.commands())
        self.assertEqual(["input", "touchscreen", "motionevent", "DOWN"],
                         fly_input[-2][:4])
        self.assertEqual(["input", "touchscreen", "motionevent", "UP"],
                         fly_input[-1][:4])

    def test_fly_accepts_both_shared_duration_boundaries(self):
        opt_in = {"OVERTE_ANDROID_PHONE_E2E_INPUT": "1"}
        for duration in (0.1, 10.0):
            if self.log.exists():
                self.log.unlink()
            self.assertEqual(
                {"performed": True},
                self.invoke("input.fly", {"durationSeconds": duration}, opt_in))
            input_commands = self.input_commands(self.commands())
            self.assertEqual(
                ["input", "touchscreen", "motionevent", "DOWN"],
                input_commands[-2][:4])
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
        self.assertEqual(["input", "touchscreen", "motionevent", "DOWN"],
                         input_commands[-2][:4])
        self.assertEqual(["input", "touchscreen", "motionevent", "UP"],
                         input_commands[-1][:4])

    def test_failed_touch_and_release_force_stop_the_bound_session(self):
        environment = {"OVERTE_ANDROID_PHONE_E2E_INPUT": "1",
                       "MOCK_INPUT_FAIL": "1", "MOCK_INPUT_UP_FAIL": "1"}
        result = self.invoke_failure("input.fly", {"durationSeconds": 0.1},
                                     environment)
        self.assertEqual(2, result.returncode)
        input_commands = self.input_commands(self.commands())
        self.assertEqual(["input", "touchscreen", "motionevent", "DOWN"],
                         input_commands[-2][:4])
        self.assertEqual(["input", "touchscreen", "motionevent", "UP"],
                         input_commands[-1][:4])
        self.assertIn(["am", "force-stop", "org.overte.phone"], self.commands())

    def test_successful_press_with_failed_release_force_stops_and_fails(self):
        environment = {"OVERTE_ANDROID_PHONE_E2E_INPUT": "1",
                       "MOCK_INPUT_UP_FAIL": "1"}
        result = self.invoke_failure("input.jump", {}, environment)
        self.assertEqual(2, result.returncode)
        self.assertIn("release failed closed", result.stderr)
        self.assertIn(["am", "force-stop", "org.overte.phone"], self.commands())

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

    def test_missing_physical_dpi_fails_before_touch(self):
        environment = {"OVERTE_ANDROID_PHONE_E2E_INPUT": "1",
                       "MOCK_DISPLAY_DPI_MISSING": "1"}
        result = self.invoke_failure("input.jump", {}, environment)
        self.assertEqual(2, result.returncode)
        self.assertIn("physical display DPI is unavailable", result.stderr)
        self.assertEqual([], self.input_commands(self.commands()))

    def test_phone_jenkins_pipeline_is_locked_private_and_phone_only(self):
        source = JENKINSFILE.read_text(encoding="utf-8")
        for required in (
                "agent { label 'overte-device-interactive' }",
                "lock(resource: params.DEVICE_RESOURCE.trim()",
                "withCredentials([string(",
                "OVERTE_CI_ADAPTER_MANIFEST=android/phone/device-tests/adapter.json",
                "String suite = 'vertical-locomotion'",
                "OVERTE_ANDROID_PHONE_E2E_INPUT = '1'",
                "OVERTE_ANDROID_E2E_DEBUG = '1'",
                "OVERTE_ANDROID_ADB",
                "cleanup-target",
                "stage-results",
                "junit(",
                "archiveArtifacts("):
            self.assertIn(required, source)
        self.assertNotIn("android/vr", source)
        self.assertNotIn("android-pico", source)
        self.assertNotIn("appium-ios", source)


if __name__ == "__main__":
    unittest.main()
