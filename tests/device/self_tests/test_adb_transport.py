#!/usr/bin/env python3
"""Contract tests for the shared ADB transport."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
import tempfile
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adb_transport import AdbTransport


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
    def test_property_snapshot_uses_one_selected_call_and_preserves_empty_values(self):
        raw = "[ro.product.model]: [A8110]\r\n[ro.product.cpu.abilist]: [arm64-v8a]\n[empty]: []\n"
        with mock.patch.object(self.transport, 'shell', return_value=raw.replace('\r', '')) as shell:
            self.assertEqual(self.transport.properties('owned-test-alias'),
                             {'ro.product.model': 'A8110', 'ro.product.cpu.abilist': 'arm64-v8a', 'empty': ''})
            shell.assert_called_once_with('owned-test-alias', 'getprop')

    def telemetry(self, memory, status, rollup='', *, changed=False):
        values = {'meminfo':memory,'status':status,'smaps_rollup':rollup,
                  'battery':'level: 72\ntemperature: 310', 'thermalservice':'Thermal Status: 0'}
        def shell(_target, *args, **_kwargs):
            return values[args[1] if args[0]=='dumpsys' else args[-1].rsplit('/',1)[-1]]
        states=[{'running':True,'identity':'42:123'},
                {'running':True,'identity':'43:124' if changed else '42:123'}]
        with mock.patch.object(self.transport,'process_state',side_effect=states), \
             mock.patch.object(self.transport,'shell',side_effect=shell) as calls:
            result=self.transport.telemetry_snapshot('owned-test-alias','org.overte.test')
            calls.assert_any_call('owned-test-alias','dumpsys','meminfo','42',check=False)
            return result

    def test_memory_table_uses_kernel_rss_instead_of_private_dirty_column(self):
        value=self.telemetry('  TOTAL 45000 12000 9000 0\n', 'VmRSS: 60000 kB\n')
        self.assertEqual((value['memoryPssKb'],value['memoryRssKb']),(45000,60000))

    def test_memory_summary_and_owned_kernel_rollup_are_native_fallbacks(self):
        for memory,status,rollup,expected in (
                ('TOTAL PSS: 45000 TOTAL RSS: 60000','', '',(45000,60000)),
                ('TOTAL: 45000 TOTAL SWAP PSS: 0','VmRSS: 60000 kB','',(45000,60000)),
                ('No process found','', 'Pss: 45123 kB\nRss: 60234 kB\n',(45123,60234)),
                ('','', 'permission denied',(None,None))):
            with self.subTest(expected=expected):
                value=self.telemetry(memory,status,rollup)
                self.assertEqual((value['memoryPssKb'],value['memoryRssKb']),expected)

    def test_memory_from_a_replaced_process_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'process changed'):
            self.telemetry('TOTAL 45000 12000','VmRSS: 60000 kB',changed=True)

    def test_timeout_reports_a_closed_category_without_private_arguments(self):
        for arguments, category in ((["shell", "am", "start", "-n", "private-activity"], "activity launch"),
                                    (["shell", "am", "force-stop", "private-package"], "application stop"),
                                    (["shell", "run-as", "private-package", "cat", "private-file"], "controlled app file access"),
                                    (["private-command", "private-payload"], "command")):
            with self.subTest(category=category), mock.patch('adb_transport.subprocess.run',
                    side_effect=subprocess.TimeoutExpired('private-device-command', 20)):
                with self.assertRaises(RuntimeError) as caught:
                    self.transport.execute(arguments, target='private-device-selector')
                self.assertEqual(str(caught.exception), 'ADB operation timed out: ' + category)
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

    def test_native_epoch_is_read_from_android_and_malformed_clocks_fail(self):
        with mock.patch.object(self.transport, "shell", return_value="1791518932123\n") as shell:
            self.assertEqual(1791518932123, self.transport.epoch_milliseconds("secret"))
            shell.assert_called_once_with("secret", "date", "+%s%3N")
        for value in ("", "0", "true", "1791518932%3N", "1791518932123 extra"):
            with self.subTest(value=value), mock.patch.object(self.transport, "shell", return_value=value):
                with self.assertRaisesRegex(RuntimeError, "native clock"):
                    self.transport.epoch_milliseconds("secret")

    def test_process_identity_includes_start_time(self):
        state = self.transport.process_state("secret", "org.overte.test")
        self.assertTrue(state["running"])
        self.assertTrue(state["identity"].startswith("42:"))

    def test_property_snapshot_is_fresh_and_batched(self):
        with mock.patch.object(self.transport, "shell", side_effect=[
                "[ro.product.model]: [Phone]\n[ro.kernel.qemu]: [0]\n[private]: [secret]\n",
                "[ro.product.model]: [Emulator]\n[ro.kernel.qemu]: [1]\n"]) as shell:
            names = ("ro.product.model", "ro.kernel.qemu", "absent")
            self.assertEqual({"ro.product.model": "Phone", "ro.kernel.qemu": "0", "absent": ""},
                             self.transport.properties("secret", names))
            self.assertEqual("1", self.transport.properties("secret", names)["ro.kernel.qemu"])
            self.assertEqual([mock.call("secret", "getprop")]*2, shell.call_args_list)

    def test_duplicate_property_snapshot_fails_without_private_values(self):
        with mock.patch.object(self.transport, "shell", return_value=
                "[ro.kernel.qemu]: [private]\n[ro.kernel.qemu]: [secret]\n"):
            with self.assertRaisesRegex(RuntimeError, "duplicate entries") as error:
                self.transport.properties("secret", ("ro.kernel.qemu",))
            self.assertNotIn("private", str(error.exception))
            self.assertNotIn("secret", str(error.exception))

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
                    "adb_transport.time.sleep") as sleep:
            self.transport.require_connected(
                "secret", attempts=2, interval_seconds=0.25)
        self.assertEqual(2, execute.call_count)
        sleep.assert_called_once_with(0.25)

    def test_network_connection_retry_reconnects_only_the_exact_target(self):
        target = "127.0.0.1:5555"
        with mock.patch.object(
                self.transport, "execute",
                side_effect=["offline\n", "connected\n", "device\n"]) as execute, mock.patch(
                    "adb_transport.time.sleep") as sleep:
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
