#!/usr/bin/env python3
"""Contract tests for the canonical cross-platform adapter and smoke route."""

from __future__ import annotations

import json
from pathlib import Path
import unittest


DEVICE_ROOT = Path(__file__).resolve().parents[1]


class PortableSmokeContractTest(unittest.TestCase):
    def test_portable_smoke_is_the_exact_shared_behavior_sequence(self) -> None:
        catalog = json.loads(
            (DEVICE_ROOT / "catalog.json").read_text(encoding="utf-8"))
        modules = [
            module["id"] for module in catalog["modules"]
            if "portable-smoke" in module["suites"]
        ]
        self.assertEqual(
            ["launch-smoke", "scene", "look", "move", "tablet"], modules)

    def test_every_platform_routes_to_one_canonical_adapter(self) -> None:
        routing = json.loads(
            (DEVICE_ROOT / "platform-adapters.json").read_text(encoding="utf-8"))
        self.assertEqual(1, routing["schemaVersion"])
        self.assertEqual("cleanup", routing["cleanupAction"])
        self.assertEqual(
            {"android", "ios", "linux", "macos", "pico", "windows"},
            set(routing["platforms"]))
        for platform, relative in routing["platforms"].items():
            with self.subTest(platform=platform):
                manifest_path = (DEVICE_ROOT / relative).resolve()
                self.assertIn(DEVICE_ROOT.resolve(), manifest_path.parents)
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                self.assertEqual(1, manifest["schemaVersion"])
                self.assertTrue(manifest["command"])

    def test_baseline_covers_install_behavior_evidence_and_cleanup(self) -> None:
        routing = json.loads(
            (DEVICE_ROOT / "platform-adapters.json").read_text(encoding="utf-8"))
        capabilities = routing["requiredCapabilities"]
        self.assertEqual(sorted(set(capabilities)), capabilities)
        self.assertEqual({
            "app.install", "app.launch", "app.process", "artifact.screenshot",
            "artifact.video", "input.look", "input.move", "probe.snapshot",
            "scene.load", "tablet.close", "tablet.open",
        }, set(capabilities))

    def test_each_routed_adapter_implements_baseline_operations(self) -> None:
        routing = json.loads(
            (DEVICE_ROOT / "platform-adapters.json").read_text(encoding="utf-8"))
        registry = json.loads(
            (DEVICE_ROOT / "capabilities.json").read_text(encoding="utf-8"))[
                "capabilities"]
        operations = {
            registry[capability]["operation"]
            for capability in routing["requiredCapabilities"]
        }
        for platform, relative in routing["platforms"].items():
            with self.subTest(platform=platform):
                manifest_path = DEVICE_ROOT / relative
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                adapter_path = manifest_path.parent / manifest["command"][0]
                source = adapter_path.read_text(encoding="utf-8")
                for operation in operations:
                    self.assertIn(f'"{operation}"', source)
                self.assertIn("def cleanup(", source)


if __name__ == "__main__":
    unittest.main()
