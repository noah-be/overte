"""Reject missing native provenance, stale commands and renderer evidence."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.ios.adapter import IOSAdapter
from contracts import validate_operation_result
from adapters.ios import native_integration as native


class NativeIntegration(unittest.TestCase):
    def setUp(self):
        self.text = {"schemaVersion": 1, "processId": 42, "sampleEpochMs": 10000,
                     "commandId": "owned-command", "ok": True,
                     "snapshot": {"schemaVersion": 1, "value": "äöü", "focused": True,
                                  "keyboardVisible": True, "submittedCount": 1}}
        self.render = {"schemaVersion": 1, "processId": 42, "sampleEpochMs": 10000,
                       "valid": True, "backend": "Vulkan/MoltenVK", "hardwareAccelerated": True,
                       "surfaceVisible": True, "generation": "2", "acceptedPresentCalls": "10", "frameSequence": 12}

    def test_installed_feature_must_be_explicit_and_exact(self):
        self.assertTrue(native.enabled({"nativeIntegration": {"kind": "ios-documents", "version": 2}}))
        for value in (None, True, {"kind": "ios-documents", "version": True},
                      {"kind": "ios-documents", "version": 1}):
            self.assertFalse(native.enabled({"nativeIntegration": value}))

    def test_text_returns_actual_unicode_observation(self):
        self.assertEqual(native.text(self.text, 42, "owned-command", 10000)["value"], "äöü")

    def test_transport_echo_cannot_substitute_for_gui_execution(self):
        for field, value in (("ok", False), ("commandId", "previous"), ("processId", 43),
                             ("schemaVersion", True), ("sampleEpochMs", 6000)):
            doc = copy.deepcopy(self.text); doc[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                native.text(doc, 42, "owned-command", 10000)

    def test_invalid_submit_count_and_unobserved_keyboard_are_rejected(self):
        for field, value in (("submittedCount", -1), ("focused", 1), ("keyboardVisible", "yes")):
            doc = copy.deepcopy(self.text); doc["snapshot"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                native.text(doc, 42, "owned-command", 10000)

    def test_presentation_requires_actual_current_generation_and_counter(self):
        self.assertEqual(native.render(self.render, 42, 10000)["frameSequence"], 12)
        for field, value in (("valid", False), ("frameSequence", 0), ("acceptedPresentCalls", "0"),
                             ("generation", "0"), ("acceptedPresentCalls", str(2**64)),
                             ("backend", "unknown"), ("hardwareAccelerated", 1),
                             ("processId", 43), ("sampleEpochMs", 6000)):
            doc = copy.deepcopy(self.render); doc[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                native.render(doc, 42, 10000)

    def test_native_unhealthy_surface_facts_are_never_replaced(self):
        self.render["hardwareAccelerated"] = False
        self.render["surfaceVisible"] = False
        observed = native.render(self.render, 42, 10000)
        self.assertIs(observed["hardwareAccelerated"], False)
        self.assertIs(observed["surfaceVisible"], False)

    def test_native_text_actions_satisfy_portable_contract_after_real_receipt(self):
        adapter = IOSAdapter.__new__(IOSAdapter)
        target = {"platform": "ios", "physical": True, "appId": "org.example.client",
                  "testBuild": {"resultsDirectory": "owned"}, "probe": {"kind": "ios-documents"},
                  "nativeIntegration": {"kind": "ios-documents", "version": 2}}
        adapter.target = Mock(return_value=target)
        adapter.ensure_session = Mock(return_value=(Mock(), "owned", {}))
        adapter.assert_ios_process_identity = Mock(return_value="42")
        adapter.native_text_command = Mock(return_value=self.text["snapshot"])
        for operation in ("text.focus", "text.dismiss"):
            observed = adapter.invoke("selected", operation, {})
            self.assertEqual(validate_operation_result(operation, observed), {"performed": True})
