"""Native iOS Documents PCM transport regression."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
class NativeVoiceTransport(unittest.TestCase):
    def test_ios_uses_documents_pcm_and_the_controlled_fixture(self):
        # apple-ios owns a richer Appium implementation; shared branches expose
        # the parent implementation through this same compatibility entrypoint.
        from ios.adapters.appium_adapter import AppiumAdapter
        adapter = object.__new__(AppiumAdapter)
        adapter.platform = "ios"
        target = {"platform": "ios", "appId": "org.example.overte.e2e", "testBuild": {
            "fixtureOrigin": "http://127.0.0.1:18080", "resultsDirectory": "results"},
            "probe": {"kind": "ios-documents"}}
        adapter.target = Mock(return_value=target)
        adapter.ensure_session = Mock(return_value=(Mock(), "session", {}))
        adapter.process_state = Mock(return_value={"running": True, "identity": "123"})
        adapter.assert_ios_process_identity = Mock(return_value="123")
        adapter.query_app_state = Mock(return_value=4)
        value = {"schemaVersion": 1, "commandId": "fresh", "action": "status"}
        response = {"schemaVersion": 1, "commandId": "fresh", "ok": True, "sampleEpochMs": 100000}
        with patch.dict(os.environ, {"OVERTE_E2E_VOICE_TESTS": "1"}), patch("adapters.voice_transport.time.time", return_value=100), patch("adapters.voice_transport.fixture_command") as deliver, patch("adapters.voice_transport.appium_read", return_value=json.dumps(response).encode()) as read:
            self.assertTrue(adapter.invoke("private-test-target", "voice.exchange", value)["ok"])
        self.assertEqual(deliver.call_args.args, ("http://127.0.0.1:18080/e2e-client-command.json", value))
        self.assertEqual(read.call_args.args[2], "@org.example.overte.e2e:documents/results/voice-result.json")
        with patch.dict(os.environ, {"OVERTE_E2E_VOICE_TESTS": "0"}):
            self.assertNotIn("voice.exchange", adapter.advertised_capabilities(target))
