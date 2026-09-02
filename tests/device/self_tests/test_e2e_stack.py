#!/usr/bin/env python3
"""Shared, device-free Appium stack boundaries."""

from __future__ import annotations

import json
from pathlib import Path
import unittest


DEVICE_ROOT = Path(__file__).resolve().parents[1]


class E2EStackTest(unittest.TestCase):
    def test_examples_are_disabled_and_contain_no_platform_transport(self):
        payload = json.loads(
            (DEVICE_ROOT / "adapters/appium/targets.example.json").read_text())
        self.assertEqual(1, payload["schemaVersion"])
        self.assertEqual({"android", "ios"}, {item["platform"] for item in payload["targets"]})
        allowed = {
            "appId", "capabilities", "controls", "displayName", "enabled", "physical",
            "platform", "selector", "serverUrl",
        }
        for item in payload["targets"]:
            self.assertFalse(item["enabled"])
            self.assertFalse(item["physical"])
            self.assertEqual(allowed, set(item))
            self.assertNotIn("appium:udid", item["capabilities"])

    def test_docs_publish_only_device_free_commands(self):
        documentation = "\n".join(
            (DEVICE_ROOT / relative).read_text(encoding="utf-8")
            for relative in ("adapters/appium/README.md", "adapters/appium/IOS_TABLET_E2E.md")
        )
        self.assertIn("test_appium_adapter", documentation)
        self.assertIn("verify_adapter.py --help", documentation)
        self.assertNotIn("--target", documentation)


if __name__ == "__main__":
    unittest.main()
