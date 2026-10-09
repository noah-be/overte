"""Reject foreign, stale and delivery-only consent evidence."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import copy
import base64
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.ios import native_consent
from adapters.ios.adapter import IOSAdapter
from contracts import validate_operation_arguments, validate_operation_result


class NativeConsent(unittest.TestCase):
    def setUp(self):
        self.source = "http://fixture.invalid:49121/scripted_interactable.js"
        self.scene = "http://fixture.invalid:49121/scene.json?location=controlled"
        self.document = {"schemaVersion": 1, "processId": 42, "sampleEpochMs": 10000,
            "commandId": "owned-command", "operation": "allow", "source": self.source,
            "origin": self.scene, "visible": True, "ok": True}

    def observe(self, document):
        return native_consent.observation(document, 42, "owned-command", "allow",
                                          self.source, self.scene, 10000)

    def test_receipt_requires_current_native_dialog_and_exact_world_source(self):
        self.assertEqual(self.observe(self.document), self.document)
        for field, value in (("processId", 43), ("sampleEpochMs", 6000),
                ("commandId", "previous"), ("visible", False), ("visible", 1),
                ("ok", False), ("operation", "review"), ("schemaVersion", True),
                ("source", self.source + "?foreign"),
                ("origin", "http://other.invalid:49121/scene.json"),
                ("origin", "http://fixture.invalid:49122/scene.json"),
                ("origin", "http://fixture.invalid:49121/other.json"),
                ("origin", "http://user@fixture.invalid:49121/scene.json")):
            document = copy.deepcopy(self.document); document[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.observe(document)
        with self.assertRaises(ValueError): self.observe(self.document | {"granted": True})

    def test_adapter_requires_both_ui_receipts_and_restores_tablet(self):
        target = {"appId": "org.example.client", "testBuild": {
            "fixtureOrigin": "http://fixture.invalid:49121",
            "scenePath": "/scene.json?location=controlled", "resultsDirectory": "owned"}}
        adapter = IOSAdapter.__new__(IOSAdapter)
        adapter.assert_ios_process_identity = Mock(return_value="42")
        adapter.probe_snapshot = Mock(return_value={"tablet": {"open": False}})
        adapter.invoke = Mock()
        adapter.command = Mock(side_effect=["review-command", "allow-command"])
        client = Mock()
        client.execute.side_effect = [base64.b64encode(json.dumps({**self.document,
            "commandId": key, "operation": operation}).encode()).decode()
            for key, operation in [("review-command", "review"), ("allow-command", "allow")]]
        with patch("adapters.ios.native_integration.time.time", return_value=10):
            self.assertEqual({"performed": True}, adapter.review_entity_script(
                "owned", client, "session", {}, target))
        self.assertEqual(["tablet.open", "tablet.close"],
                         [call.args[1] for call in adapter.invoke.call_args_list])
        self.assertEqual(["review", "allow"],
                         [call.kwargs['operation'] for call in adapter.command.call_args_list])
        adapter.invoke.reset_mock();adapter.command.reset_mock(side_effect=True)
        adapter.command.return_value="owned-command"
        client.execute.side_effect=None
        client.execute.return_value=base64.b64encode(json.dumps({**self.document,
            "operation": "review", "ok": False}).encode()).decode()
        with patch("adapters.ios.native_integration.time.time", return_value=10), self.assertRaises(ValueError):
            adapter.review_entity_script("owned", client, "session", {}, target)
        self.assertEqual(1, adapter.command.call_count)
        self.assertEqual(["tablet.open", "tablet.close"],
                         [call.args[1] for call in adapter.invoke.call_args_list])

    def test_installed_feature_is_explicit_and_never_truthy_or_inherited(self):
        target = {"platform": "ios", "physical": True, "testBuild": {"fixtureOrigin": "owned"},
                  "probe": {"kind": "ios-documents"}}
        self.assertNotIn("entity-script.review", IOSAdapter.advertised_capabilities(target))
        target["nativeEntityConsent"] = {"kind": "ios-documents", "version": 1}
        self.assertIn("entity-script.review", IOSAdapter.advertised_capabilities(target))
        target["nativeEntityConsent"]["version"] = True
        self.assertNotIn("entity-script.review", IOSAdapter.advertised_capabilities(target))
        with self.assertRaises(ValueError): validate_operation_arguments("entity-script.review", {"source": "foreign"})
        with self.assertRaises(ValueError): validate_operation_result("entity-script.review", {"performed": False})

    def test_slow_independent_process_query_does_not_age_a_fresh_receipt(self):
        target = {"appId": "org.example.client", "testBuild": {
            "fixtureOrigin": "http://fixture.invalid:49121",
            "scenePath": "/scene.json?location=controlled", "resultsDirectory": "owned"}}
        adapter = IOSAdapter.__new__(IOSAdapter)
        clock = [10.0]
        pending = {}

        def process(*args):
            clock[0] += 4.0
            return "42"

        def command(*args, operation, **kwargs):
            key = operation + "-command"
            pending.update(self.document, commandId=key, operation=operation,
                           sampleEpochMs=clock[0] * 1000)
            return key

        adapter.assert_ios_process_identity = Mock(side_effect=process)
        adapter.probe_snapshot = Mock(return_value={"tablet": {"open": False}})
        adapter.invoke = Mock()
        adapter.command = Mock(side_effect=command)
        client = Mock()
        client.execute.side_effect = lambda *args: base64.b64encode(
            json.dumps(pending).encode()).decode()
        with patch("adapters.ios.native_integration.time.time", side_effect=lambda: clock[0]):
            self.assertEqual({"performed": True}, adapter.review_entity_script(
                "owned", client, "session", {}, target))
        self.assertEqual(3, adapter.assert_ios_process_identity.call_count)
        self.assertEqual(["review", "allow"],
                         [call.kwargs["operation"] for call in adapter.command.call_args_list])

    def test_fresh_receipt_still_requires_an_independent_matching_process(self):
        target = {"appId": "org.example.client", "testBuild": {
            "fixtureOrigin": "http://fixture.invalid:49121",
            "scenePath": "/scene.json?location=controlled", "resultsDirectory": "owned"}}
        adapter = IOSAdapter.__new__(IOSAdapter)
        adapter.assert_ios_process_identity = Mock(side_effect=["42", "43"])
        adapter.probe_snapshot = Mock(return_value={"tablet": {"open": False}})
        adapter.invoke = Mock()
        adapter.command = Mock(return_value="owned-command")
        client = Mock()
        client.execute.return_value = base64.b64encode(json.dumps({**self.document,
            "operation": "review"}).encode()).decode()
        with patch("adapters.ios.native_integration.time.time", return_value=10), \
                self.assertRaisesRegex(RuntimeError, "entity consent crossed process identities"):
            adapter.review_entity_script("owned", client, "session", {}, target)
        self.assertEqual(1, adapter.command.call_count)
        self.assertEqual(["tablet.open", "tablet.close"],
                         [call.args[1] for call in adapter.invoke.call_args_list])


if __name__ == "__main__": unittest.main()
