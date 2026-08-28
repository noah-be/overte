#!/usr/bin/env python3
"""Static security contract for the portable in-client command channel."""

from __future__ import annotations

from pathlib import Path
import unittest


DEVICE_ROOT = Path(__file__).resolve().parents[1]
PROBE = DEVICE_ROOT / "probe/overte_e2e_probe.js"


class ProbeCommandChannelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = PROBE.read_text(encoding="utf-8")

    def test_private_channel_is_platform_neutral_and_fail_closed(self) -> None:
        self.assertIn('Script.resolvePath("e2e-client-command.json")', self.source)
        self.assertIn("clientCommandUnavailable = true", self.source)
        self.assertIn("objectKeysMatch(command", self.source)
        self.assertNotIn("desktop-command.json", self.source)

    def test_channel_exposes_only_bounded_behavior_commands(self) -> None:
        for action in ('"navigate"', '"asset-load"', '"sound-channel"'):
            self.assertIn(f"command.action === {action}", self.source)
        self.assertIn("Window.location = command.url", self.source)
        self.assertIn("controlledAssetEntity = Entities.addEntity({", self.source)
        self.assertIn("soundCommandUrl = String(command.url)", self.source)
        self.assertNotIn("Clipboard", self.source)
        self.assertNotIn("Desktop.openUrl", self.source)

    def test_adapter_owned_entity_is_removed_on_replacement_and_shutdown(self) -> None:
        self.assertGreaterEqual(
            self.source.count("Entities.deleteEntity(controlledAssetEntity)"), 2
        )
        self.assertIn("controlledAssetEntity = null", self.source)


if __name__ == "__main__":
    unittest.main()
