#!/usr/bin/env python3
"""Contract tests for the shared ADB transport."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from android.common.device_tests.adb_transport import AdbTransport


MOCK = r'''#!/usr/bin/env python3
import os,shlex,sys
a=sys.argv[1:]
if len(a) >= 2 and a[0] == "-P":
    if a[1] != "5041": raise SystemExit(4)
    a=a[2:]
if a == ["devices", "-l"]: print("List of devices attached\nsecret device model:Mock")
elif a == ["-s", "secret", "get-state"]: print("device")
elif a[-4:] == ["shell", "pidof", "-s", "org.overte.test"]: print("42")
elif a[-3:] == ["shell", "cat", "/proc/42/stat"]: print("42 (app) S " + "0 "*18 + "123 0")
elif a[-4:] == ["shell", "dumpsys", "activity", "activities"]: print("  ResumedActivity: x u0 org.overte.test/.Main t1")
elif len(a) >= 4 and a[-2] == "shell" and a[-1].startswith("run-as "):
    remote=shlex.split(a[-1])
    expected=["run-as","org.overte.test","sh","-c",
      'umask 077; temporary="$1.tmp"; cat > "$temporary" && chmod 600 "$temporary" && mv "$temporary" "$1"',
      "overte-e2e-write","files/overte-e2e/control.json"]
    if remote != expected: raise SystemExit(5)
    payload=sys.stdin.read()
    open(os.environ["MOCK_CONTROL_STATE"],"w").write(payload)
elif a[-5:] == ["shell","run-as","org.overte.test","cat","files/overte-e2e/control.json"]:
    print(open(os.environ["MOCK_CONTROL_STATE"]).read(),end="")
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

    def test_connection_retry_is_bounded_and_recovers(self):
        with mock.patch.object(
                self.transport, "execute",
                side_effect=["offline\n", "device\n"]) as execute, mock.patch(
                    "android.common.device_tests.adb_transport.time.sleep") as sleep:
            self.transport.require_connected(
                "secret", attempts=2, interval_seconds=0.25)
        self.assertEqual(2, execute.call_count)
        sleep.assert_called_once_with(0.25)

    def test_network_connection_retry_reconnects_only_the_exact_target(self):
        target = "127.0.0.1:5555"
        with mock.patch.object(
                self.transport, "execute",
                side_effect=["offline\n", "connected\n", "device\n"]) as execute, mock.patch(
                    "android.common.device_tests.adb_transport.time.sleep") as sleep:
            self.transport.require_connected(
                target, attempts=2, interval_seconds=0.25)
        self.assertEqual([
            mock.call(["get-state"], target=target, check=False),
            mock.call(["connect", target], timeout=5, check=False),
            mock.call(["get-state"], target=target, check=False),
        ], execute.call_args_list)
        sleep.assert_called_once_with(0.25)

    def test_invalid_connection_retry_policy_is_rejected(self):
        for attempts, interval in ((0, 0.25), (True, 0.25), (121, 0.25),
                                   (1, -0.1), (1, True), (1, 1.1)):
            with self.subTest(attempts=attempts, interval=interval), self.assertRaisesRegex(
                    RuntimeError, "retry policy is invalid"):
                self.transport.require_connected(
                    "secret", attempts=attempts, interval_seconds=interval)

    def test_invalid_explicit_server_ports_fail_closed(self):
        for value in (True, 0, 65536, "5041"):
            with self.subTest(value=value), self.assertRaisesRegex(
                    RuntimeError, "server port is invalid"):
                AdbTransport(str(self.adb), server_port=value)

    def test_debug_file_write_preserves_remote_shell_argument_boundaries(self):
        state = Path(self.temporary.name) / "control.json"
        previous = os.environ.get("MOCK_CONTROL_STATE")
        os.environ["MOCK_CONTROL_STATE"] = str(state)
        self.addCleanup(
            lambda: (os.environ.pop("MOCK_CONTROL_STATE", None)
                     if previous is None
                     else os.environ.__setitem__("MOCK_CONTROL_STATE", previous)))
        payload = '{"schemaVersion":1}\n'
        self.transport.write_debug_app_file(
            "secret", "org.overte.test", "files/overte-e2e/control.json", payload)
        self.assertEqual(payload, state.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
