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

MOCK_ADB = r'''#!/usr/bin/env python3
import os, pathlib, sys
args = sys.argv[1:]
target = None
if args[:1] == ["-s"]:
    target, args = args[1], args[2:]
state = pathlib.Path(os.environ["MOCK_ADB_STATE"])
if args[:2] == ["devices", "-l"]:
    print("List of devices attached")
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
props = {
 "ro.product.manufacturer":"Example", "ro.product.brand":"Example",
 "ro.product.model":"Phone", "ro.product.device":"phone",
 "ro.build.characteristics":"default", "ro.product.cpu.abilist":"arm64-v8a,armeabi-v7a",
 "ro.build.version.sdk":"36", "ro.build.version.release":"16",
 "ro.opengles.version":"196610", "ro.kernel.qemu":os.environ.get("MOCK_QEMU", "0")}
if shell[:1] == ["getprop"]:
    print(props.get(shell[1], ""))
elif shell == ["pm", "list", "features"]:
    print("feature:android.hardware.touchscreen")
elif shell == ["pidof", "-s", "org.overte.phone"]:
    if not state.exists() or state.read_text() != "stopped": print("4242")
elif shell == ["cat", "/proc/4242/stat"]:
    print("4242 (overte) S " + "0 " * 18 + "98765 0")
elif shell == ["dumpsys", "activity", "activities"]:
    foreground = not state.exists() or state.read_text() == "foreground"
    print("mResumedActivity: org.overte.phone/.PhoneInterfaceActivity" if foreground else
          "mResumedActivity: com.android.launcher/.Launcher")
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
        self.adb.write_text(MOCK_ADB, encoding="utf-8")
        self.adb.chmod(0o700)
        self.environment = os.environ.copy()
        self.environment.update({"OVERTE_ANDROID_ADB": str(self.adb),
                                 "MOCK_ADB_STATE": str(self.state)})

    def tearDown(self):
        self.temporary.cleanup()

    def call(self, *arguments: str, environment: dict[str, str] | None = None):
        env = self.environment | (environment or {})
        return subprocess.run([sys.executable, str(ADAPTER), *arguments], text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=env, check=False)

    def invoke(self, operation: str) -> dict:
        result = self.call("invoke", "--target", "private-phone", "--operation", operation)
        self.assertEqual(0, result.returncode, result.stderr)
        return json.loads(result.stdout)

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


if __name__ == "__main__":
    unittest.main()
