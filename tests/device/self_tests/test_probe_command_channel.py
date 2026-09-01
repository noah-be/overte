#!/usr/bin/env python3
"""Static security contract for the portable in-client command channel."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen


DEVICE_ROOT = Path(__file__).resolve().parents[1]
PROBE = DEVICE_ROOT / "probe/overte_e2e_probe.js"


class ProbeCommandChannelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = PROBE.read_text(encoding="utf-8")
        cls.temporary = tempfile.TemporaryDirectory(prefix="probe-command-fixture-")
        ready = Path(cls.temporary.name) / "ready.json"
        cls.server = subprocess.Popen([
            sys.executable, str(DEVICE_ROOT / "fixture/serve.py"),
            "--ready-file", str(ready),
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        if not ready.exists():
            cls.server.terminate()
            raise RuntimeError("client command fixture did not become ready")
        cls.command_url = json.loads(ready.read_text(encoding="utf-8"))["clientCommandUrl"]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.terminate()
        cls.server.communicate(timeout=5)
        cls.temporary.cleanup()

    @classmethod
    def post_command(cls, command: dict) -> dict:
        request = Request(cls.command_url, data=json.dumps(command).encode("utf-8"),
                          headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=2) as response:
            return json.load(response)

    def test_private_channel_is_platform_neutral_and_fail_closed(self) -> None:
        self.assertIn('Script.resolvePath("e2e-client-command.json")', self.source)
        self.assertIn("clientCommandEndpoint()", self.source)
        self.assertIn('request.open("GET", commandUrl)', self.source)
        self.assertIn("clientCommandUnavailable = true", self.source)
        self.assertIn("objectKeysMatch(command", self.source)
        self.assertNotIn("desktop-command.json", self.source)

    def test_channel_exposes_only_bounded_behavior_commands(self) -> None:
        for action in ('"scene-load"', '"navigate"', '"asset-load"', '"sound-channel"',
                       '"key-hold"'):
            self.assertIn(f"command.action === {action}", self.source)
        self.assertIn('command.action === "reload-scene"', self.source)
        self.assertIn("Window.location = baseAddress", self.source)
        self.assertIn('"overteE2EReloadCommandId="', self.source)
        self.assertIn(
            "lastAndroidControlCommandId = reloadCommandIdFromAddress(location.href)",
            self.source,
        )
        self.assertIn('&& String(location.protocol) !== "file"', self.source)
        self.assertIn("Window.location = command.url", self.source)
        self.assertIn("controlledSceneLocation(command.url)", self.source)
        self.assertIn("Window.location = scenePath", self.source)
        self.assertIn("applySceneLocation", self.source)
        self.assertIn("resetSceneObservation()", self.source)
        self.assertIn("controlledAssetEntity = Entities.addEntity({", self.source)
        self.assertIn("soundCommandUrl = String(command.url)", self.source)
        self.assertIn("Controller.newMapping(controlledInputMappingName)", self.source)
        for action in ("Backward", "Down", "Forward", "Up", "StrafeLeft",
                       "StrafeRight", "ContextMenu"):
            self.assertIn(f"Controller.Actions.{action}", self.source)
        self.assertIn("Controller.disableMapping(controlledInputMappingName)", self.source)
        self.assertIn("HMD.closeTablet()", self.source)
        self.assertIn('(name === "tablet" || !controlledTabletOpen())', self.source)
        self.assertNotIn("Keyboard.emitKeyEvent", self.source)
        self.assertNotIn("Clipboard", self.source)
        self.assertNotIn("Desktop.openUrl", self.source)
        self.assertNotIn("MyAvatar.position =", self.source)
        self.assertNotIn("MyAvatar.velocity =", self.source)

    def test_fixture_channel_round_trips_only_strict_commands(self) -> None:
        command = {
            "schemaVersion": 1,
            "commandId": "scene-exact",
            "action": "scene-load",
            "url": "http://127.0.0.1:18080/scene.json?location=%2F0%2C2%2C4",
        }
        self.assertEqual(command, self.post_command(command))
        with urlopen(self.command_url, timeout=2) as response:
            self.assertEqual(command, json.load(response))
        with self.assertRaises(HTTPError) as rejected:
            self.post_command(command | {"extra": True})
        self.assertEqual(400, rejected.exception.code)
        rejected.exception.close()

        key_command = {
            "schemaVersion": 1, "commandId": "key-exact", "action": "key-hold",
            "key": "forward", "durationMs": 1500,
        }
        self.assertEqual(key_command, self.post_command(key_command))
        with self.assertRaises(HTTPError) as rejected_key:
            self.post_command(key_command | {"key": "escape"})
        self.assertEqual(400, rejected_key.exception.code)
        rejected_key.exception.close()

    def test_adapter_owned_entity_is_removed_on_replacement_and_shutdown(self) -> None:
        self.assertGreaterEqual(
            self.source.count("Entities.deleteEntity(controlledAssetEntity)"), 2
        )
        self.assertIn("controlledAssetEntity = null", self.source)


if __name__ == "__main__":
    unittest.main()
