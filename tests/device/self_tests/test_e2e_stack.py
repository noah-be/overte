#!/usr/bin/env python3
"""Shared, device-free Appium stack boundaries."""

from __future__ import annotations

import json
from pathlib import Path
import unittest


DEVICE_ROOT = Path(__file__).resolve().parents[1]
IOS_TARGET_ROOT = DEVICE_ROOT / "ios"


class E2EStackTest(unittest.TestCase):
    def test_examples_are_disabled_and_keep_physical_transport_target_owned(self):
        payload = json.loads(
            (DEVICE_ROOT / "adapters/appium/targets.example.json").read_text())
        self.assertEqual(1, payload["schemaVersion"])
        virtual_targets = [item for item in payload["targets"] if not item["physical"]]
        physical_targets = [item for item in payload["targets"] if item["physical"]]
        virtual_by_platform = {item["platform"]: item for item in virtual_targets}
        self.assertEqual(
            {"android", "ios"}, set(virtual_by_platform)
        )
        self.assertEqual(len(virtual_targets), len(virtual_by_platform))
        virtual_fields = {
            "appId", "capabilities", "controls", "displayName", "enabled", "physical",
            "platform", "selector", "serverUrl",
        }
        for item in virtual_targets:
            self.assertFalse(item["enabled"])
            self.assertEqual(virtual_fields, set(item))
            self.assertNotIn("appium:udid", item["capabilities"])

        physical_by_platform = {item["platform"]: item for item in physical_targets}
        expected_physical_platforms = {"ios"} if IOS_TARGET_ROOT.is_dir() else set()
        self.assertEqual(expected_physical_platforms, set(physical_by_platform))
        self.assertEqual(len(physical_targets), len(physical_by_platform))
        for item in physical_by_platform.values():
            self.assertFalse(item["enabled"])
            self.assertEqual("ios", item["platform"])
            self.assertEqual(
                {
                    "appId", "artifactMode", "artifactReceipt", "capabilities", "controls",
                    "displayName", "enabled", "physical", "platform", "probe", "scene",
                    "selector", "serverUrl", "soundControl", "testBuild",
                },
                set(item),
            )
            self.assertEqual("REPLACE_WITH_PRIVATE_UDID", item["capabilities"]["appium:udid"])
            self.assertEqual(
                "REPLACE_WITH_IOS_VERSION_18_OR_NEWER",
                item["capabilities"]["appium:platformVersion"],
            )
            self.assertEqual(
                {
                    "appium:autoLaunch", "appium:automationName", "appium:bundleId",
                    "appium:enforceAppInstall", "appium:noReset", "appium:platformVersion",
                    "appium:udid", "appium:updatedWDABundleId", "appium:usePreinstalledWDA",
                    "appium:waitForIdleTimeout", "platformName",
                },
                set(item["capabilities"]),
            )
            self.assertTrue(item["capabilities"]["appium:usePreinstalledWDA"])
            self.assertTrue(item["serverUrl"].startswith("http://127.0.0.1:"))
            self.assertTrue(item["artifactReceipt"].startswith("/private/"))
            self.assertEqual(
                {
                    "contract", "contractVersion", "fixtureOrigin", "launchArguments",
                    "launchEnvironment", "probeScriptPath", "resultsDirectory", "scenePath",
                },
                set(item["testBuild"]),
            )

    def test_docs_separate_device_free_and_physical_commands(self):
        overview = (DEVICE_ROOT / "adapters/appium/README.md").read_text(
            encoding="utf-8"
        )
        documentation = (DEVICE_ROOT / "adapters/appium/IOS_TABLET_E2E.md").read_text(
            encoding="utf-8"
        )
        for device_free_command in ("test_appium_adapter", "verify_adapter.py --help"):
            self.assertIn(device_free_command, overview)
            self.assertIn(device_free_command, documentation)
        self.assertNotIn("--target", overview)
        has_physical_section = "## Physical acceptance" in documentation
        self.assertEqual(IOS_TARGET_ROOT.is_dir(), has_physical_section)
        if not has_physical_section:
            self.assertNotIn("--target", documentation)
            return
        hardware_free = documentation.split("## Hardware-free validation", 1)[1].split(
            "## Physical acceptance", 1
        )[0]
        physical = documentation.split("## Physical acceptance", 1)[1]
        self.assertNotIn("--target", hardware_free)
        self.assertIn('--target "$OVERTE_DEVICE_TARGET_SELECTOR"', physical)
        self.assertIn("private receipt-bound target configuration", physical)


if __name__ == "__main__":
    unittest.main()
