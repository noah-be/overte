"""Validate real native UI evidence before audit or physical activation."""
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
from adapters.ios import native_ui
from adapters.ios.adapter import IOSAdapter


class NativeUiEvidence(unittest.TestCase):
    def setUp(self):
        self.document = {"schemaVersion": 1, "valid": True, "sampleEpochMs": 10000,
                         "processId": 42, "elements": [{"identifier": "OverteTabletOpen",
                          "visible": True, "enabled": True,
                          "frame": {"x": 16, "y": 16, "width": 128, "height": 64}}]}

    def test_audit_contains_only_observed_widgets(self):
        observed = native_ui.validate(self.document, 42, 10000)
        source = native_ui.source(observed)
        self.assertIn("UIKitAccessibility", source)
        self.assertIn("OverteTabletOpen", source)
        self.assertNotIn("OverteTabletClose", source)
        self.document["elements"] = []
        self.assertNotIn("OverteTabletOpen", native_ui.source(native_ui.validate(self.document, 42, 10000)))

    def test_stale_foreign_process_and_boolean_schema_are_rejected(self):
        for field, value in (("sampleEpochMs", 5000), ("processId", 43),
                             ("schemaVersion", True), ("valid", False)):
            document = copy.deepcopy(self.document)
            document[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                native_ui.validate(document, 42, 10000)

    def test_unknown_duplicate_and_malformed_widget_facts_are_rejected(self):
        for kind in ("unknown", "duplicate", "frame", "boolean", "foreign-field"):
            document = copy.deepcopy(self.document)
            widget = document["elements"][0]
            if kind == "unknown": widget["identifier"] = "OverteTabletUnexpectedPrivateValue"
            elif kind == "duplicate": document["elements"].append(copy.deepcopy(widget))
            elif kind == "frame": widget["frame"]["width"] = 0
            elif kind == "boolean": widget["enabled"] = 1
            else: widget["userText"] = "must not be exported"
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                native_ui.validate(document, 42, 10000)

    def adapter(self):
        target = {"appId": "org.example.client", "testBuild": {"resultsDirectory": "owned-results",
                  "fixtureOrigin": "http://fixture.invalid:49121"},
                  "nativeUiObservation": {"kind": "uikit-documents", "version": 1}}
        adapter = IOSAdapter.__new__(IOSAdapter)
        adapter.platform = "ios"
        adapter._native_ui_target = target
        client = Mock()
        return adapter, client, target

    def test_hidden_or_disabled_widget_never_receives_touch(self):
        for field in ("visible", "enabled"):
            document = copy.deepcopy(self.document)
            document["elements"][0][field] = False
            adapter, client, target = self.adapter()
            with patch.object(adapter, "native_ui_snapshot", return_value=document):
                with self.assertRaises(RuntimeError):
                    adapter.click_accessibility(client, "owned", "OverteTabletOpen")
            client.call.assert_not_called()

    def test_physical_touch_uses_observed_widget_frame(self):
        adapter, client, target = self.adapter()
        with patch.object(adapter, "native_ui_snapshot", return_value=self.document):
            adapter.click_accessibility(client, "owned", "OverteTabletOpen")
        method, path, body = client.call.call_args_list[0].args
        self.assertEqual((method, path), ("POST", "/session/owned/actions"))
        move = body["actions"][0]["actions"][0]
        self.assertEqual((move["x"], move["y"]), (80, 48))
        self.assertEqual(body["actions"][0]["actions"][-1]["type"], "pointerUp")
        client.call.assert_any_call("DELETE", "/session/owned/actions")

    def test_ui_receipt_cannot_cross_process_identity(self):
        adapter, client, target = self.adapter()
        document = copy.deepcopy(self.document)
        document["sampleEpochMs"] = time.time() * 1000
        command_id = "ios-" + "f" * 32
        receipt = {"schemaVersion": 1, "commandId": command_id, "observation": document}
        client.execute.return_value = base64.b64encode(json.dumps(receipt).encode()).decode()
        response = Mock(status=200)
        response.read.return_value = json.dumps({"schemaVersion": 1,
            "commandId": command_id, "action": "native-ui-snapshot"}).encode()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        before = {"bundleId": target["appId"], "pid": 42, "foreground": True}
        with patch.object(adapter, "native_process", side_effect=[before, {**before, "pid": 43}]), \
                patch("adapters.ios.adapter.uuid.uuid4", return_value=Mock(hex="f" * 32)), \
                patch("adapters.ios.adapter.urlopen", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "crossed process"):
                adapter.native_ui_snapshot(client, "owned", target)

    def test_snapshot_requires_exact_request_nonce_and_fresh_native_widgets(self):
        for violation in (None, "nonce", "stale", "extra", "boolean-schema"):
            with self.subTest(violation=violation):
                adapter, client, target = self.adapter()
                document = copy.deepcopy(self.document)
                document["sampleEpochMs"] = time.time() * 1000
                command_id = "ios-" + "f" * 32
                receipt = {"schemaVersion": 1, "commandId": command_id, "observation": document}
                if violation == "nonce": receipt["commandId"] = "ios-" + "e" * 32
                if violation == "stale": document["sampleEpochMs"] -= 10000
                if violation == "extra": receipt["inferredReady"] = True
                if violation == "boolean-schema": receipt["schemaVersion"] = True
                client.execute.return_value = base64.b64encode(json.dumps(receipt).encode()).decode()
                response = Mock(status=200)
                response.read.return_value = json.dumps({"schemaVersion": 1,
                    "commandId": command_id, "action": "native-ui-snapshot"}).encode()
                response.__enter__ = Mock(return_value=response)
                response.__exit__ = Mock(return_value=False)
                process = {"bundleId": target["appId"], "pid": 42, "foreground": True}
                with patch.object(adapter, "native_process", return_value=process), \
                        patch("adapters.ios.adapter.uuid.uuid4", return_value=Mock(hex="f" * 32)), \
                        patch("adapters.ios.adapter.urlopen", return_value=response), \
                        patch("adapters.ios.adapter.time.monotonic", side_effect=[0, 0.1, 6]), \
                        patch("adapters.ios.adapter.time.sleep"):
                    if violation is None:
                        self.assertEqual(document, adapter.native_ui_snapshot(client, "owned", target))
                        self.assertTrue(client.execute.call_args.args[2]["remotePath"].endswith(
                            "/ios-native-ui-request-result.json"))
                    else:
                        with self.assertRaisesRegex(RuntimeError, "not available") as rejected:
                            adapter.native_ui_snapshot(client, "owned", target)
                        self.assertIsInstance(rejected.exception.__cause__, ValueError)
                        if violation == "stale":
                            self.assertEqual("native UIKit observation is stale",
                                             str(rejected.exception.__cause__))

    def test_failed_physical_touch_still_releases_contact(self):
        adapter, client, target = self.adapter()
        client.call.side_effect = [RuntimeError("physical action failed"), None]
        with patch.object(adapter, "native_ui_snapshot", return_value=self.document):
            with self.assertRaisesRegex(RuntimeError, "physical action failed"):
                adapter.click_accessibility(client, "owned", "OverteTabletOpen")
        client.call.assert_any_call("DELETE", "/session/owned/actions")

    def test_native_ui_requires_exact_installed_feature_marker(self):
        adapter, client, target = self.adapter()
        self.assertTrue(adapter.native_ui_enabled(target))
        for marker in (None, True, {"kind": "uikit-documents", "version": True},
                       {"kind": "uikit-documents", "version": 2}):
            with self.subTest(marker=marker):
                self.assertFalse(adapter.native_ui_enabled({"nativeUiObservation": marker}))


if __name__ == "__main__":
    unittest.main()
