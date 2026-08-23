#!/usr/bin/env python3
"""Device-free contract tests for the universal device harness."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


HARNESS = Path(__file__).resolve().parents[1] / "run.py"
VERIFIER = Path(__file__).resolve().parents[1] / "verify_adapter.py"

ADAPTER = r'''#!/usr/bin/env python3
import argparse, json, os
p = argparse.ArgumentParser()
p.add_argument("action", choices=("discover", "describe", "invoke", "cleanup"))
p.add_argument("--target")
p.add_argument("--operation")
p.add_argument("--arguments")
a = p.parse_args()
selector = os.environ.get("MOCK_SELECTOR", "private-device-123")
if a.action == "discover":
    print(json.dumps([{"selector": selector, "displayName": "Mock Phone",
                       "platform": "mock", "physical": os.environ.get("MOCK_VIRTUAL") != "1",
                       "capabilities": os.environ.get("MOCK_CAPABILITIES", "app.process").split(",")}]))
elif a.action == "describe":
    print(json.dumps({"platform": "mock", "model": "Contract Device"}))
elif a.action == "invoke":
    state = os.environ.get("MOCK_STATE")
    if a.operation == "app.launch":
        if state:
            open(state, "w", encoding="utf-8").write("foreground")
        value = {"launched": True}
    elif a.operation == "app.process":
        value = {"running": True, "identity": "mock-process-42"}
    elif a.operation == "app.foreground":
        foreground = not state or not os.path.exists(state) or open(state, encoding="utf-8").read() == "foreground"
        value = {"foreground": foreground}
    elif a.operation == "lifecycle.background":
        if state:
            open(state, "w", encoding="utf-8").write("background")
        value = {"backgrounded": True}
    elif a.operation == "telemetry.snapshot":
        value = {"memoryPssKb": 100, "batteryLevel": 80, "thermalStatus": 0}
    else:
        value = {"operation": a.operation, "arguments": json.loads(a.arguments)}
    print(json.dumps(value))
else:
    with open(os.environ["MOCK_CLEANUP_MARKER"], "w", encoding="utf-8") as marker:
        marker.write("cleaned\n")
    print(json.dumps({"cleaned": True}))
'''

MODULE = r'''#!/usr/bin/env python3
import json, os, pathlib
artifact = pathlib.Path(os.environ["OVERTE_DEVICE_ARTIFACT_DIR"])
selector = os.environ["OVERTE_DEVICE_TARGET_SELECTOR"]
(artifact / "metric.json").write_text(json.dumps({"stable": True}) + "\n")
print("module target=" + selector)
raise SystemExit(int(os.environ.get("MOCK_MODULE_EXIT", "0")))
'''


class HarnessTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="device-harness-test-")
        self.root = Path(self.temporary.name)
        self.adapter = self.root / "adapter.py"
        self.module = self.root / "module.py"
        self.adapter.write_text(ADAPTER, encoding="utf-8")
        self.module.write_text(MODULE, encoding="utf-8")
        self.adapter.chmod(0o700)
        self.module.chmod(0o700)
        self.manifest = self.root / "adapter.json"
        self.manifest.write_text(json.dumps({
            "schemaVersion": 1, "id": "mock", "command": ["adapter.py"]}), encoding="utf-8")
        self.catalog = self.root / "catalog.json"
        self.catalog.write_text(json.dumps({"schemaVersion": 1, "modules": [{
            "id": "health", "description": "Mock health module", "command": ["module.py"],
            "suites": ["smoke", "stability"], "requires": ["app.process"],
            "timeoutSeconds": 10}]}), encoding="utf-8")
        self.output = self.root / "results"
        self.cleanup_marker = self.root / "cleanup"

    def tearDown(self):
        self.temporary.cleanup()

    def run_harness(self, *extra: str, environment: dict[str, str] | None = None):
        env = os.environ.copy()
        env["MOCK_CLEANUP_MARKER"] = str(self.cleanup_marker)
        env["MOCK_STATE"] = str(self.root / "state")
        env["OVERTE_DEVICE_LOCK_ROOT"] = str(self.root / "locks")
        if environment:
            env.update(environment)
        return subprocess.run([
            sys.executable, str(HARNESS), "--adapter-manifest", str(self.manifest),
            "--catalog", str(self.catalog), "--output-dir", str(self.output), *extra,
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, check=False)

    def test_success_writes_private_safe_json_junit_and_artifacts(self):
        result = self.run_harness("--suite", "smoke")
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertTrue(self.cleanup_marker.exists())
        self.assertFalse((self.output / "modules/health/INVALID").exists())
        self.assertTrue((self.output / "modules/health/metric.json").exists())
        self.assertNotIn("private-device-123", result.stdout)
        self.assertNotIn("private-device-123", (self.output / "device.json").read_text())
        self.assertNotIn("private-device-123", (self.output / "modules/health/module.log").read_text())
        summary = json.loads((self.output / "summary.json").read_text())
        self.assertEqual("passed", summary["status"])
        junit = ET.parse(self.output / "junit.xml").getroot()
        self.assertEqual("1", junit.attrib["tests"])
        self.assertEqual("0", junit.attrib["failures"])

    def test_failure_keeps_invalid_marker_and_still_cleans_up(self):
        result = self.run_harness(environment={"MOCK_MODULE_EXIT": "9"})
        self.assertEqual(1, result.returncode, result.stdout)
        self.assertTrue(self.cleanup_marker.exists())
        self.assertTrue((self.output / "modules/health/INVALID").exists())
        self.assertEqual("failed", json.loads((self.output / "summary.json").read_text())["status"])

    def test_missing_capability_is_reported_as_skip(self):
        result = self.run_harness(environment={"MOCK_CAPABILITIES": "telemetry.memory"})
        self.assertEqual(0, result.returncode, result.stdout)
        summary = json.loads((self.output / "summary.json").read_text())
        self.assertEqual("skipped", summary["results"][0]["status"])
        self.assertTrue(self.cleanup_marker.exists())

    def test_virtual_target_requires_explicit_opt_in(self):
        result = self.run_harness(environment={"MOCK_VIRTUAL": "1"})
        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn("physical-device policy", result.stdout)

    def test_virtual_target_can_be_explicitly_selected(self):
        result = self.run_harness("--allow-virtual", environment={"MOCK_VIRTUAL": "1"})
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertTrue(self.cleanup_marker.exists())

    def test_list_does_not_contact_adapter_or_create_results(self):
        result = self.run_harness("--list")
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn("health: Mock health module", result.stdout)
        self.assertFalse(self.cleanup_marker.exists())
        self.assertFalse(self.output.exists())

    def test_adapter_protocol_verifier_checks_cleanup_idempotency(self):
        env = os.environ.copy()
        env["MOCK_CLEANUP_MARKER"] = str(self.cleanup_marker)
        result = subprocess.run([
            sys.executable, str(VERIFIER), "--adapter-manifest", str(self.manifest),
            "--check-cleanup",
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, check=False)
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn("satisfies the protocol", result.stdout)
        self.assertTrue(self.cleanup_marker.exists())

    def test_portable_launch_module_runs_through_adapter_contract(self):
        env = os.environ.copy()
        env.update({
            "MOCK_CLEANUP_MARKER": str(self.cleanup_marker),
            "MOCK_STATE": str(self.root / "state"),
            "MOCK_CAPABILITIES": "app.foreground,app.launch,app.process",
            "OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS": "0",
            "OVERTE_DEVICE_LOCK_ROOT": str(self.root / "locks"),
        })
        result = subprocess.run([
            sys.executable, str(HARNESS), "--adapter-manifest", str(self.manifest),
            "--catalog", str(HARNESS.parent / "catalog.json"), "--suite", "smoke",
            "--output-dir", str(self.output),
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, check=False)
        self.assertEqual(0, result.returncode, result.stdout)
        metrics = json.loads((self.output / "modules/launch-smoke/metrics.json").read_text())
        self.assertEqual("mock-process-42", metrics["processIdentity"])


if __name__ == "__main__":
    unittest.main()
