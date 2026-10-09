"""Require real fresh probe contents, exact request ownership and process continuity."""
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
from adapters.ios import native_probe
from test_appium_adapter import snapshot


class RequestBoundProbe(unittest.TestCase):
    def setUp(self):
        self.target = {"appId": "org.example.client", "testBuild": {
            "fixtureOrigin": "http://fixture.invalid:49121", "resultsDirectory": "owned"}}
        self.pid = {"pid": 42, "foregroundRunning": True}
        self.observe = Mock(side_effect=[self.pid, self.pid.copy()])
        self.receipt = {"schemaVersion": 1, "commandId": "ios-" + "a" * 32,
                        "observation": snapshot()}
        self.client = Mock()
        self.client.execute.side_effect = lambda *args: base64.b64encode(
            json.dumps(self.receipt).encode()).decode()
        response = Mock(status=200)
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        def post(request, timeout):
            self.payload = json.loads(request.data)
            response.read.return_value = json.dumps(self.payload).encode()
            return context
        self.addCleanup(patch.stopall)
        patch.object(native_probe, "urlopen", side_effect=post).start()
        patch.object(native_probe.uuid, "uuid4", return_value=Mock(hex="a" * 32)).start()

    def capture(self):
        return native_probe.capture(self.client, "session", self.target, self.observe)

    def test_real_probe_contract_and_request_are_preserved(self):
        self.assertEqual(self.receipt["observation"], self.capture())
        self.assertEqual({"schemaVersion": 1, "commandId": self.receipt["commandId"],
                          "action": "native-probe-snapshot"}, self.payload)
        self.assertEqual(2, self.observe.call_count)
        self.client.execute.assert_called_once_with("session", "mobile: pullFile", {
            "remotePath": "@org.example.client:documents/owned/ios-probe-request-result.json"})

    def test_nonce_envelope_and_extra_host_fields_are_rejected(self):
        for change in ({"commandId": "old"}, {"schemaVersion": True}, {"result": "passed"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                native_probe.validate(self.receipt | change, self.receipt["commandId"])

    def test_actual_freshness_and_probe_schema_remain_required(self):
        for change in ({"sampleEpochMs": 1}, {"schemaVersion": 1}, {"application": {}},
                       {"scene": {}}, {"sampleSequence": 0}):
            receipt = copy.deepcopy(self.receipt)
            receipt["observation"].update(change)
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                native_probe.validate(receipt, receipt["commandId"])

    def test_only_absent_android_control_metadata_is_omitted(self):
        receipt = copy.deepcopy(self.receipt)
        receipt["observation"]["control"] = None
        self.assertEqual(self.receipt["observation"], native_probe.validate(
            receipt, receipt["commandId"]))
        receipt["observation"]["control"] = {"forged": True}
        with self.assertRaises(RuntimeError):
            native_probe.validate(receipt, receipt["commandId"])

    def test_process_change_and_lost_foreground_are_rejected(self):
        for after in ({"pid": 43, "foregroundRunning": True},
                      {"pid": 42, "foregroundRunning": False}, None):
            self.observe.side_effect = [self.pid, after]
            with self.subTest(after=after), self.assertRaises(RuntimeError):
                self.capture()

    def test_persistent_file_errors_are_never_an_observation(self):
        self.client.execute.side_effect = RuntimeError("persistent native read error")
        with self.assertRaisesRegex(RuntimeError, "persistent native read error"):
            self.capture()

    def test_previous_request_cannot_satisfy_current_capture(self):
        self.receipt["commandId"] = "ios-" + "b" * 32
        with patch.object(native_probe.time, "monotonic", side_effect=[0, 0, 6]), \
                patch.object(native_probe.time, "sleep"), self.assertRaises(RuntimeError):
            self.capture()
        self.assertEqual(1, self.observe.call_count)

    def test_first_launch_wait_is_bounded_without_accepting_a_previous_sample(self):
        self.client.execute.side_effect = [base64.b64encode(b'null').decode(),
            base64.b64encode(json.dumps(self.receipt).encode()).decode()]
        with patch.object(native_probe.time, "monotonic", side_effect=[0, 0, 6]), \
                patch.object(native_probe.time, "sleep"):
            self.assertEqual(self.receipt["observation"], native_probe.capture(
                self.client, "session", self.target, self.observe, timeout_seconds=20))
        for invalid in (True, 0, 21, 60):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                native_probe.capture(self.client, "session", self.target, self.observe,
                                     timeout_seconds=invalid)


if __name__ == "__main__":
    unittest.main()
