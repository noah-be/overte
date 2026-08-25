#!/usr/bin/env python3
"""Contract tests for the shared ADB transport."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from android.common.device_tests.adb_transport import AdbTransport


MOCK = r'''#!/usr/bin/env python3
import sys
a=sys.argv[1:]
if len(a) >= 2 and a[0] == "-P":
    if a[1] != "5041": raise SystemExit(4)
    a=a[2:]
if a == ["devices", "-l"]: print("List of devices attached\nsecret device model:Mock")
elif a == ["-s", "secret", "get-state"]: print("device")
elif a[-4:] == ["shell", "pidof", "-s", "org.overte.test"]: print("42")
elif a[-3:] == ["shell", "cat", "/proc/42/stat"]: print("42 (app) S " + "0 "*18 + "123 0")
elif a[-4:] == ["shell", "dumpsys", "activity", "activities"]: print("  ResumedActivity: x u0 org.overte.test/.Main t1")
else: raise SystemExit(3)
'''


class AdbTransportTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="adb-transport-test-")
        self.adb = Path(self.temporary.name) / "adb"
        self.adb.write_text(MOCK, encoding="utf-8")
        self.adb.chmod(0o700)
        self.transport = AdbTransport(str(self.adb))

    def tearDown(self):
        self.temporary.cleanup()

    def test_discovers_authorized_transport(self):
        self.assertEqual(["secret"], self.transport.authorized_targets())
        self.transport.require_connected("secret")

    def test_process_identity_includes_start_time(self):
        state = self.transport.process_state("secret", "org.overte.test")
        self.assertTrue(state["running"])
        self.assertTrue(state["identity"].startswith("42:"))

    def test_parses_android_17_foreground_format(self):
        self.assertEqual("org.overte.test", self.transport.foreground_package("secret"))

    def test_explicit_server_port_is_applied_to_discovery_and_selected_calls(self):
        transport = AdbTransport(str(self.adb), server_port=5041)
        self.assertEqual(["secret"], transport.authorized_targets())
        transport.require_connected("secret")
        self.assertTrue(transport.process_state("secret", "org.overte.test")["running"])

    def test_invalid_explicit_server_ports_fail_closed(self):
        for value in (True, 0, 65536, "5041"):
            with self.subTest(value=value), self.assertRaisesRegex(
                    RuntimeError, "server port is invalid"):
                AdbTransport(str(self.adb), server_port=value)


if __name__ == "__main__":
    unittest.main()
