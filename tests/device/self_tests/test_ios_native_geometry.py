"""Exercise the actual geometry transport and reject unbound or stale evidence."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import base64
import copy
import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.ios import native_geometry


class NativeGeometryEvidence(unittest.TestCase):
    def setUp(self):
        self.target = {"appId": "org.example.client", "testBuild": {
            "fixtureOrigin": "http://fixture.invalid:49121", "resultsDirectory": "owned"}}
        self.process = {"pid": 42, "foregroundRunning": True}
        self.observe = Mock(side_effect=[self.process, self.process.copy()])
        self.document = {"schemaVersion": 1, "sampleEpochMs": time.time() * 1000,
            "sampleSequence": 7, "nativeUi": {"valid": True, "surfaceWidth": 1024,
                "surfaceHeight": 768, "safeInsetLeft": 0, "safeInsetTop": 20,
                "safeInsetRight": 0, "safeInsetBottom": 20},
            "window": {"width": 1024, "height": 728}}
        self.receipt = {"schemaVersion": 1, "commandId": "ios-" + "a" * 32,
                        "observation": self.document}
        self.client = Mock()
        self.client.execute.side_effect = lambda *args: base64.b64encode(
            json.dumps(self.receipt).encode()).decode()
        self.echo = Mock(status=200)
        self.open = Mock()
        self.open.return_value.__enter__ = Mock(return_value=self.echo)
        self.open.return_value.__exit__ = Mock(return_value=False)
        def post(request, timeout):
            self.payload = json.loads(request.data)
            self.assertEqual(timeout, 5)
            self.assertEqual(request.full_url, self.target["testBuild"]["fixtureOrigin"] +
                             "/e2e-client-command.json")
            self.echo.read.return_value = json.dumps(self.payload).encode()
            return self.open.return_value
        self.addCleanup(patch.stopall)
        patch.object(native_geometry, "urlopen", side_effect=post).start()
        patch.object(native_geometry.uuid, "uuid4", return_value=Mock(hex="a" * 32)).start()

    def capture(self):
        return native_geometry.capture(self.client, "owned-session", self.target, self.observe)

    def test_actual_capture_returns_observed_geometry_after_independent_process_checks(self):
        document, rect = self.capture()
        self.assertEqual(self.document, document)
        self.assertEqual({"x": 0, "y": 20, "width": 1024, "height": 728}, rect)
        self.assertEqual({"schemaVersion": 1, "commandId": "ios-" + "a" * 32,
                          "action": "native-geometry-snapshot"}, self.payload)
        self.assertEqual(self.observe.call_count, 2)
        self.client.execute.assert_called_once_with("owned-session", "mobile: pullFile",
            {"remotePath": "@org.example.client:documents/owned/ios-ui-request-result.json"})
        self.echo.read.assert_called_once_with(4097)

    def test_request_nonce_schema_and_extra_host_fields_are_rejected(self):
        for change in ({"commandId": "foreign"}, {"schemaVersion": True},
                       {"schemaVersion": 2}, {"window": {}}, {"observation": None}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                native_geometry.validate(self.receipt | change, self.receipt["commandId"])
        with self.assertRaises(ValueError):
            native_geometry.validate(None, self.receipt["commandId"])

    def test_existing_freshness_rotation_inset_and_dimensions_checks_remain_required(self):
        for path, value in (("sampleEpochMs", 1), ("sampleSequence", 0),
                            ("sampleSequence", True), ("window", {"width": 728, "height": 1024}),
                            ("nativeUi", self.document["nativeUi"] | {"valid": False}),
                            ("nativeUi", self.document["nativeUi"] | {"surfaceWidth": 0}),
                            ("nativeUi", self.document["nativeUi"] | {"safeInsetTop": -1})):
            receipt = copy.deepcopy(self.receipt)
            receipt["observation"][path] = value
            with self.subTest(path=path, value=value), self.assertRaises(ValueError):
                native_geometry.validate(receipt, receipt["commandId"])

    def test_missing_or_wrong_nonce_is_not_satisfied_by_a_fixture_delivery_echo(self):
        for receipt in (None, self.receipt | {"commandId": "foreign"}):
            self.receipt = receipt
            self.observe.reset_mock(side_effect=True)
            self.observe.side_effect = [self.process]
            with patch.object(native_geometry.time, "monotonic", side_effect=[0, 0, 6]), \
                    patch.object(native_geometry.time, "sleep"), \
                    self.assertRaisesRegex(RuntimeError, "not observed"):
                self.capture()
            self.assertEqual(self.observe.call_count, 1)

    def test_changed_pid_or_lost_foreground_rejects_fresh_native_dimensions(self):
        for after in ({"pid": 43, "foregroundRunning": True},
                      {"pid": 42, "foregroundRunning": False}, None):
            self.observe.side_effect = [self.process, after]
            with self.subTest(after=after), self.assertRaisesRegex(RuntimeError, "identities"):
                self.capture()

    def test_background_or_invalid_process_rejects_before_requesting_geometry(self):
        for before in ({"pid": 42, "foregroundRunning": False},
                       {"pid": True, "foregroundRunning": True}, None):
            self.observe.side_effect = [before]
            with self.subTest(before=before), self.assertRaisesRegex(RuntimeError, "foreground"):
                self.capture()
        self.client.execute.assert_not_called()

    def test_native_file_transport_failures_are_not_converted_to_geometry(self):
        self.client.execute.side_effect = OSError("native transport failed")
        with self.assertRaisesRegex(OSError, "native transport failed"):
            self.capture()

    def test_initial_absence_waits_for_the_exact_client_sample(self):
        self.client.execute.side_effect = [base64.b64encode(b"null").decode(),
            base64.b64encode(json.dumps(self.receipt).encode()).decode()]
        with patch.object(native_geometry.time, "sleep"):
            document, rect = self.capture()
        self.assertEqual(document, self.document)
        self.assertEqual(rect["height"], 728)
        self.assertEqual(self.client.execute.call_count, 2)

    def test_foreign_delivery_echo_rejects_before_consuming_device_evidence(self):
        response = Mock(status=200)
        response.read.return_value = json.dumps({"success": True}).encode()
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        with patch.object(native_geometry, "urlopen", return_value=context), \
                self.assertRaisesRegex(RuntimeError, "exact native geometry request"):
            self.capture()
        self.client.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
