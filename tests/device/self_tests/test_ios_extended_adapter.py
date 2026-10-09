#!/usr/bin/env python3
"""Negative boundaries and lifecycle evidence for physical iOS operations."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import base64
from contextlib import contextmanager
import json
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.ios.adapter import IOSAdapter
from fixture.serve import FixtureState


class ExtendedIOS(unittest.TestCase):
    def setUp(self):
        self.target = {"platform": "ios", "physical": True, "appId": "org.example.client",
                       "probe": {"kind": "ios-documents"},
                       "testBuild": {"fixtureOrigin": "http://lab.example:49121",
                                     "resultsDirectory": "overte-e2e"}}
        self.adapter = IOSAdapter.__new__(IOSAdapter)
        self.adapter.platform = "ios"
        self.adapter.target = Mock(return_value=self.target)
        self.client = Mock()
        self.state = {"processIdentity": "42", "iosE2ELaunchCompleted": True}
        self.adapter.ensure_session = Mock(return_value=(self.client, "owned", self.state))
        self.adapter.save_session = Mock()

    def test_foreign_process_is_rejected(self):
        self.client.execute.return_value = {"bundleId": "org.example.foreign", "pid": 42,
                                            "foreground": True}
        with self.assertRaises(RuntimeError):
            self.adapter.invoke("selected", "app.process", {})

    def test_atomic_native_guard_rejects_background_absent_foreign_and_restarted_process(self):
        live = {"bundleId": self.target["appId"], "pid": 42, "foreground": True}
        for observed in (None, {**live, "foreground": False}, {**live, "pid": 43},
                         {**live, "bundleId": "org.example.foreign"}):
            self.client.execute.return_value = observed
            with self.subTest(observed=observed), self.assertRaises(RuntimeError):
                self.adapter.assert_ios_process_identity("selected", self.client, "owned", self.state, self.target)

    def test_atomic_native_guard_observes_live_identity_again_on_every_call(self):
        live = {"bundleId": self.target["appId"], "pid": 42, "foreground": True}
        self.client.execute.side_effect = [live, {**live, "pid": 43}]
        self.assertEqual(self.adapter.assert_ios_process_identity(
            "selected", self.client, "owned", self.state, self.target), "42")
        with self.assertRaisesRegex(RuntimeError, "process restarted"):
            self.adapter.assert_ios_process_identity("selected", self.client, "owned", self.state, self.target)
        self.assertEqual(self.client.execute.call_count, 2)

    def test_background_process_remains_observable(self):
        self.client.execute.return_value = {"bundleId": self.target["appId"], "pid": 42,
                                            "foreground": False}
        self.assertEqual(self.adapter.invoke("selected", "app.process", {}),
                         {"running": True, "identity": "42"})

    def test_background_cannot_claim_success_after_a_process_change(self):
        before = {"bundleId": self.target["appId"], "pid": 42, "foreground": True}
        after = {**before, "pid": 43, "foreground": False}
        with patch.object(self.adapter, "native_process", side_effect=[before, after]):
            with self.assertRaisesRegex(RuntimeError, "lost the original process"):
                self.adapter.invoke("selected", "lifecycle.background", {})

    def test_stop_clears_launch_identity_only_after_observed_exit(self):
        self.client.execute.return_value = None
        self.assertEqual(self.adapter.invoke("selected", "app.stop", {}), {"stopped": True})
        self.assertNotIn("processIdentity", self.state)
        self.assertNotIn("iosE2ELaunchCompleted", self.state)

    def test_stop_does_not_clear_state_while_process_still_exists(self):
        self.client.execute.return_value = {"bundleId": self.target["appId"], "pid": 42,
                                            "foreground": True}
        with self.assertRaises(RuntimeError):
            self.adapter.invoke("selected", "app.stop", {})
        self.assertEqual(self.state["processIdentity"], "42")

    def test_foreign_asset_rejected_before_device_use(self):
        with self.assertRaises(RuntimeError):
            self.adapter.invoke("selected", "asset.load", {
                "assetId": "fixture-image", "url": "http://foreign.example/image.png",
                "entityName": "OVERTE_E2E_ASSET_LOAD_IMAGE"})
        self.adapter.ensure_session.assert_not_called()

    def test_http_echo_cannot_substitute_for_device_execution(self):
        self.adapter.assert_ios_process_identity = Mock(return_value="42")
        self.client.execute.return_value = base64.b64encode(json.dumps({
            "schemaVersion": 1, "commandId": "previous", "sampleEpochMs": time.time() * 1000
        }).encode()).decode()
        @contextmanager
        def response(request, **unused):
            value = Mock(status=200)
            value.read.return_value = request.data
            yield value
        with patch("adapters.ios.adapter.urlopen", response), \
                patch("adapters.ios.adapter.time.monotonic", side_effect=[0, 0, 16]), \
                patch("adapters.ios.adapter.time.sleep"):
            with self.assertRaisesRegex(RuntimeError, "execution receipt"):
                self.adapter.command("selected", self.client, "owned", self.state,
                                     self.target, "set-audio-mute", muted=True)

    def test_fixture_rejects_arbitrary_settings_and_non_boolean_mute(self):
        fixture = FixtureState()
        envelope = {"schemaVersion": 1, "commandId": "bounded-command"}
        for arguments in ({"action": "set-audio-mute", "muted": 1},
                          {"action": "set-safe-setting", "settingId": "arbitrary", "enabled": True}):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                fixture.set_client_command({**envelope, **arguments})
        self.assertEqual(fixture.set_client_command({**envelope,
                         "action": "set-audio-mute", "muted": True})["muted"], True)

    def test_execution_requires_exact_fresh_versioned_device_receipt(self):
        self.adapter.assert_ios_process_identity = Mock(return_value="42")
        @contextmanager
        def response(request, **unused):
            value = Mock(status=200)
            value.read.return_value = request.data
            yield value
        for version, age, accepted in ((1, 0, True), (True, 0, False), (1, 6000, False)):
            self.client.execute.return_value = base64.b64encode(json.dumps({
                "schemaVersion": version, "commandId": "ios-owned",
                "sampleEpochMs": 10000 - age
            }).encode()).decode()
            with self.subTest(version=version, age=age), \
                    patch("adapters.ios.adapter.urlopen", response), \
                    patch("adapters.ios.adapter.uuid.uuid4", return_value=Mock(hex="owned")), \
                    patch("adapters.ios.adapter.time.time", return_value=10), \
                    patch("adapters.ios.adapter.time.monotonic", side_effect=[0, 0, 16]), \
                    patch("adapters.ios.adapter.time.sleep"):
                if accepted:
                    self.assertEqual(self.adapter.command("selected", self.client, "owned", self.state,
                        self.target, "set-audio-mute", muted=True), "ios-owned")
                else:
                    with self.assertRaisesRegex(RuntimeError, "execution receipt"):
                        self.adapter.command("selected", self.client, "owned", self.state,
                            self.target, "set-audio-mute", muted=True)


if __name__ == "__main__":
    unittest.main()
