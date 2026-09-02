#!/usr/bin/env python3
"""Shared, device-free Appium stack boundaries."""

from __future__ import annotations

import json
from pathlib import Path
import unittest


DEVICE_ROOT = Path(__file__).resolve().parents[1]


class E2EStackTest(unittest.TestCase):
    def test_examples_are_disabled_and_physical_template_is_fail_closed(self):
        payload = json.loads(
            (DEVICE_ROOT / "adapters/appium/targets.example.json").read_text())
        self.assertEqual(1, payload["schemaVersion"])
        self.assertEqual({"android", "ios"}, {item["platform"] for item in payload["targets"]})
        virtual_allowed = {
            "appId", "capabilities", "controls", "displayName", "enabled", "physical",
            "platform", "selector", "serverUrl",
        }
        for item in payload["targets"]:
            self.assertFalse(item["enabled"])
            if not item["physical"]:
                self.assertEqual(virtual_allowed, set(item))
                self.assertNotIn("appium:udid", item["capabilities"])

        physical = [item for item in payload["targets"] if item["physical"]]
        self.assertEqual(1, len(physical))
        ios = physical[0]
        self.assertEqual("ios", ios["platform"])
        self.assertEqual(
            virtual_allowed | {"artifactMode", "artifactReceipt", "probe", "scene", "soundControl", "testBuild"},
            set(ios),
        )
        self.assertTrue(ios["serverUrl"].startswith("http://127.0.0.1:"))
        self.assertTrue(ios["artifactReceipt"].startswith("/private/"))
        self.assertEqual(
            {
                "appium:autoLaunch", "appium:automationName", "appium:bundleId",
                "appium:enforceAppInstall", "appium:noReset", "appium:platformVersion",
                "appium:udid", "appium:updatedWDABundleId", "appium:usePreinstalledWDA",
                "appium:waitForIdleTimeout", "platformName",
            },
            set(ios["capabilities"]),
        )
        self.assertIn("REPLACE", ios["capabilities"]["appium:udid"])
        self.assertIn("REPLACE", ios["capabilities"]["appium:platformVersion"])
        self.assertEqual(
            {
                "contract", "contractVersion", "fixtureOrigin", "launchArguments",
                "launchEnvironment", "probeScriptPath", "resultsDirectory", "scenePath",
            },
            set(ios["testBuild"]),
        )

    def test_docs_separate_device_free_and_physical_commands(self):
        documentation = (DEVICE_ROOT / "adapters/appium/IOS_TABLET_E2E.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("test_appium_adapter", documentation)
        self.assertIn("verify_adapter.py --help", documentation)
        hardware_free = documentation.split("## Hardware-free validation", 1)[1].split(
            "## Physical acceptance", 1
        )[0]
        physical = documentation.split("## Physical acceptance", 1)[1]
        self.assertNotIn("--target", hardware_free)
        self.assertIn('--target "$OVERTE_DEVICE_TARGET_SELECTOR"', physical)
        self.assertIn("private receipt-bound target configuration", physical)


if __name__ == "__main__":
    unittest.main()
