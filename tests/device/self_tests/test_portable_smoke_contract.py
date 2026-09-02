#!/usr/bin/env python3
"""Contract tests for the canonical platform-to-adapter routing table."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest


DEVICE_ROOT = Path(__file__).resolve().parents[1]


class PortableSmokeContractTest(unittest.TestCase):
    def test_routing_contains_only_integrated_platforms(self):
        routing = json.loads((DEVICE_ROOT / "platform-adapters.json").read_text())
        self.assertEqual({"schemaVersion", "contractVersion", "cleanupAction", "platforms"},
                         set(routing))
        self.assertEqual(1, routing["schemaVersion"])
        self.assertEqual(1, routing["contractVersion"])
        self.assertEqual("cleanup", routing["cleanupAction"])
        self.assertEqual({"android", "ios", "linux", "macos", "windows"},
                         set(routing["platforms"]))

    def test_each_route_resolves_to_a_canonical_manifest(self):
        routing = json.loads((DEVICE_ROOT / "platform-adapters.json").read_text())
        for platform, relative in routing["platforms"].items():
            with self.subTest(platform=platform):
                manifest_path = (DEVICE_ROOT / relative).resolve()
                self.assertIn(DEVICE_ROOT.resolve(), manifest_path.parents)
                manifest = json.loads(manifest_path.read_text())
                self.assertEqual(1, manifest["schemaVersion"])
                self.assertTrue(manifest["command"])
                adapter_path = manifest_path.parent / manifest["command"][0]
                self.assertTrue(adapter_path.is_file())
                command = ([sys.executable, str(adapter_path)]
                           if adapter_path.suffix == ".py" else [str(adapter_path)])
                result = subprocess.run(
                    [*command, *manifest["command"][1:], "--help"],
                    text=True, capture_output=True, timeout=10, check=False)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn("usage:", result.stdout)

    def test_mobile_routes_share_one_adapter(self):
        routing = json.loads((DEVICE_ROOT / "platform-adapters.json").read_text())
        commands = {}
        for platform in ("android", "ios"):
            manifest = json.loads((DEVICE_ROOT / routing["platforms"][platform]).read_text())
            commands[platform] = manifest["command"]
        self.assertEqual("adapter.py", commands["android"][0])
        self.assertEqual("adapter.py", commands["ios"][0])
        self.assertEqual(["--platform", "android"], commands["android"][1:])
        self.assertEqual(["--platform", "ios"], commands["ios"][1:])


if __name__ == "__main__":
    unittest.main()
