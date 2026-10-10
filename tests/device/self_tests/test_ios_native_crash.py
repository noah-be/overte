"""Reject command delivery, arming and foreign process crash claims."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import base64
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.ios import native_crash
from adapters.ios.adapter import IOSAdapter


class NativeCrash(unittest.TestCase):
    def setUp(self):
        self.document = {"schemaVersion": 1, "processId": 42, "sampleEpochMs": 10000,
            "commandId": "ios-" + "c" * 32, "phase": "firing", "cause": "SIGABRT"}

    def test_firing_requires_the_exact_current_original_process_command_and_signal(self):
        def observe(value):
            return native_crash.observation(value, 42, "ios-" + "c" * 32, 10000)
        self.assertEqual(self.document, observe(self.document))
        for field, value in (("phase", "armed"), ("cause", "SIGKILL"),
                ("processId", 43), ("commandId", "previous"),
                ("sampleEpochMs", 6000), ("schemaVersion", True)):
            document = copy.deepcopy(self.document); document[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): observe(document)
        with self.assertRaises(ValueError): observe(self.document | {"crashed": True})

    def test_feature_needs_exact_installed_version(self):
        self.assertTrue(native_crash.enabled({"nativeCrash": {"kind": "ios-documents", "version": 1}}))
        for value in (None, True, {"kind": "ios-documents", "version": True},
                      {"kind": "ios-documents", "version": 2}):
            self.assertFalse(native_crash.enabled({"nativeCrash": value}))

    def test_adapter_requires_firing_receipt_and_observed_exit_without_signaling_another_process(self):
        target = {"appId": "org.example.owned", "testBuild": {
            "fixtureOrigin": "http://fixture.invalid:49121", "resultsDirectory": "owned"}}
        adapter = IOSAdapter.__new__(IOSAdapter)
        adapter.assert_ios_process_identity=Mock(return_value="42")
        adapter.reset_launch_state=Mock()
        adapter.native_process=Mock(return_value=None)
        client=Mock()
        client.execute.return_value=base64.b64encode(json.dumps(self.document).encode()).decode()
        response=Mock(status=200)
        response.read.return_value=json.dumps({"schemaVersion": 1,
            "commandId": "ios-" + "c" * 32, "action": "native-crash"}).encode()
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        def run():
            with patch("adapters.ios.adapter.uuid.uuid4",return_value=Mock(hex="c" * 32)), \
                    patch("adapters.ios.adapter.urlopen",return_value=response), \
                    patch("adapters.ios.native_integration.time.time",return_value=10):
                return adapter.crash_ios_client("owned", client, "session", {}, target)
        self.assertEqual({"crashed": True}, run())
        self.assertEqual("mobile: pullFile", client.execute.call_args.args[1])
        adapter.reset_launch_state.assert_called_once()
        adapter.reset_launch_state.reset_mock()
        adapter.native_process.return_value={"pid": 43, "foreground": True}
        with self.assertRaisesRegex(RuntimeError, "unexpectedly replaced"):run()
        adapter.reset_launch_state.assert_not_called()
        adapter.native_process.return_value=None
        client.execute.return_value=base64.b64encode(json.dumps({**self.document,"phase":"armed"}).encode()).decode()
        with self.assertRaises(ValueError):run()
        adapter.reset_launch_state.assert_not_called()


if __name__ == "__main__": unittest.main()
