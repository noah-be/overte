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
import argparse, json, os, pathlib, sys
p = argparse.ArgumentParser()
p.add_argument("action", choices=("discover", "describe", "invoke", "cleanup"))
p.add_argument("--target")
p.add_argument("--operation")
p.add_argument("--arguments")
a = p.parse_args()
selector = os.environ.get("MOCK_SELECTOR", "private-device-123")
if a.action == "discover":
    if os.environ.get("MOCK_EMPTY_DISCOVERY") == "1":
        print("[]")
    else:
        print(json.dumps([{"selector": selector, "displayName": "Mock Phone",
                           "platform": "mock", "physical": os.environ.get("MOCK_VIRTUAL") != "1",
                           "capabilities": os.environ.get("MOCK_CAPABILITIES", "app.process").split(",")}]))
elif a.action == "describe":
    print(json.dumps({"platform": "mock", "model": "Contract Device"}))
elif a.action == "invoke":
    if os.environ.get("MOCK_INVOKE_FAILURE") == "1":
        print("private adapter failure for " + selector, file=sys.stderr)
        raise SystemExit(9)
    if os.environ.get("MOCK_ASSERTION_FAILURE") == "1" and a.operation == "app.process":
        print("ASSERTION: application process restarted on " + selector, file=sys.stderr)
        raise SystemExit(9)
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
        value = {"memoryPssKb": 100, "memoryRssKb": 120, "batteryLevel": 80,
                 "batteryTemperatureDeciC": 250, "thermalStatus": 0}
        if os.environ.get("MOCK_BAD_TELEMETRY") == "1":
            value["memoryPssKb"] = None
    elif a.operation == "artifact.screenshot":
        destination = pathlib.Path(os.environ["OVERTE_DEVICE_ARTIFACT_DIR"]) / "screenshot.png"
        destination.write_bytes(b"mock-png")
        value = {"artifact": destination.name}
    else:
        value = {"operation": a.operation, "arguments": json.loads(a.arguments)}
    print(json.dumps(value))
else:
    if os.environ.get("MOCK_CLEANUP_FAILURE") == "1":
        print("private cleanup transport failure for " + selector, file=sys.stderr)
        raise SystemExit(9)
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

    def test_infrastructure_failure_blocks_later_device_commands_and_cleans_up(self):
        catalog = json.loads(self.catalog.read_text(encoding="utf-8"))
        catalog["modules"].append({
            "id": "later", "description": "Must not run after transport loss",
            "command": ["module.py"], "suites": ["smoke"],
            "requires": ["app.process"], "timeoutSeconds": 10,
        })
        self.catalog.write_text(json.dumps(catalog), encoding="utf-8")

        result = self.run_harness(
            "--require-complete", environment={"MOCK_MODULE_EXIT": "75"})

        self.assertEqual(1, result.returncode, result.stdout)
        self.assertTrue(self.cleanup_marker.exists())
        self.assertFalse((self.output / "modules/later").exists())
        summary = json.loads((self.output / "summary.json").read_text())
        self.assertEqual(["error", "skipped"], [
            entry["status"] for entry in summary["results"]])
        junit = ET.parse(self.output / "junit.xml").getroot()
        self.assertEqual("1", junit.attrib["errors"])
        self.assertEqual("1", junit.attrib["skipped"])

    def test_missing_capability_is_reported_as_skip(self):
        result = self.run_harness(environment={"MOCK_CAPABILITIES": "telemetry.memory"})
        self.assertEqual(0, result.returncode, result.stdout)
        summary = json.loads((self.output / "summary.json").read_text())
        self.assertEqual("skipped", summary["results"][0]["status"])
        self.assertTrue(self.cleanup_marker.exists())

    def test_require_complete_turns_missing_capability_into_error(self):
        result = self.run_harness(
            "--require-complete", environment={"MOCK_CAPABILITIES": "telemetry.memory"})
        self.assertEqual(1, result.returncode, result.stdout)
        summary = json.loads((self.output / "summary.json").read_text())
        self.assertEqual("error", summary["results"][0]["status"])
        junit = ET.parse(self.output / "junit.xml").getroot()
        self.assertEqual("1", junit.attrib["errors"])

    def test_opt_in_failure_screenshot_is_captured_before_cleanup(self):
        result = self.run_harness(environment={
            "MOCK_MODULE_EXIT": "9",
            "MOCK_CAPABILITIES": "app.process,artifact.screenshot",
            "OVERTE_E2E_CAPTURE_ARTIFACTS": "1",
        })
        self.assertEqual(1, result.returncode, result.stdout)
        artifact = self.output / "modules/health/screenshot.png"
        self.assertEqual(b"mock-png", artifact.read_bytes())
        self.assertIn("Failure screenshot captured", (
            self.output / "modules/health/module.log").read_text())

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

    def test_adapter_protocol_verifier_can_require_a_discovered_target(self):
        env = os.environ.copy()
        env.update({"MOCK_CLEANUP_MARKER": str(self.cleanup_marker),
                    "MOCK_EMPTY_DISCOVERY": "1"})
        result = subprocess.run([
            sys.executable, str(VERIFIER), "--adapter-manifest", str(self.manifest),
            "--require-target",
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
           env=env, check=False)
        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn("returned no target", result.stdout)

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

    def test_invalid_module_configuration_is_an_infrastructure_error(self):
        env = os.environ.copy()
        env.update({
            "MOCK_CLEANUP_MARKER": str(self.cleanup_marker),
            "MOCK_STATE": str(self.root / "state"),
            "MOCK_CAPABILITIES": "app.foreground,app.launch,app.process",
            "OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS": "not-an-integer",
            "OVERTE_DEVICE_LOCK_ROOT": str(self.root / "locks"),
        })
        result = subprocess.run([
            sys.executable, str(HARNESS), "--adapter-manifest", str(self.manifest),
            "--catalog", str(HARNESS.parent / "catalog.json"), "--suite", "smoke",
            "--output-dir", str(self.output), "--require-complete",
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, check=False)
        self.assertEqual(1, result.returncode, result.stdout)
        summary = json.loads((self.output / "summary.json").read_text())
        self.assertEqual("error", summary["results"][0]["status"])
        junit = ET.parse(self.output / "junit.xml").getroot()
        self.assertEqual("1", junit.attrib["errors"])
        self.assertIn("INFRASTRUCTURE:", (
            self.output / "modules/launch-smoke/module.log").read_text())

    def test_portable_idle_soak_uses_process_evidence_without_telemetry(self):
        env = os.environ.copy()
        env.update({
            "MOCK_CLEANUP_MARKER": str(self.cleanup_marker),
            "MOCK_STATE": str(self.root / "state"),
            "MOCK_CAPABILITIES": "app.foreground,app.launch,app.process",
            "OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS": "0",
            "OVERTE_DEVICE_IDLE_SECONDS": "1",
            "OVERTE_DEVICE_SAMPLE_SECONDS": "1",
            "OVERTE_DEVICE_LOCK_ROOT": str(self.root / "locks"),
        })
        result = subprocess.run([
            sys.executable, str(HARNESS), "--adapter-manifest", str(self.manifest),
            "--catalog", str(HARNESS.parent / "catalog.json"), "--suite", "stability",
            "--output-dir", str(self.output), "--require-complete",
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, check=False)
        self.assertEqual(0, result.returncode, result.stdout)
        telemetry = (self.output / "modules/idle-soak/telemetry.jsonl").read_text()
        self.assertIn('"telemetryAvailable": false', telemetry)

    def test_advertised_telemetry_must_be_complete_and_non_null(self):
        env = os.environ.copy()
        env.update({
            "MOCK_CLEANUP_MARKER": str(self.cleanup_marker),
            "MOCK_STATE": str(self.root / "state"),
            "MOCK_CAPABILITIES": "app.foreground,app.launch,app.process,telemetry.snapshot",
            "MOCK_BAD_TELEMETRY": "1",
            "OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS": "0",
            "OVERTE_DEVICE_IDLE_SECONDS": "1",
            "OVERTE_DEVICE_SAMPLE_SECONDS": "1",
            "OVERTE_DEVICE_LOCK_ROOT": str(self.root / "locks"),
        })
        result = subprocess.run([
            sys.executable, str(HARNESS), "--adapter-manifest", str(self.manifest),
            "--catalog", str(HARNESS.parent / "catalog.json"), "--suite", "stability",
            "--output-dir", str(self.output), "--require-complete",
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, check=False)
        self.assertEqual(1, result.returncode, result.stdout)
        self.assertIn("memoryPssKb is missing or invalid", (
            self.output / "modules/idle-soak/module.log").read_text())

    def test_adapter_failure_is_junit_infrastructure_error_and_redacted(self):
        env = os.environ.copy()
        env.update({
            "MOCK_CLEANUP_MARKER": str(self.cleanup_marker),
            "MOCK_STATE": str(self.root / "state"),
            "MOCK_CAPABILITIES": "app.foreground,app.launch,app.process",
            "MOCK_INVOKE_FAILURE": "1",
            "OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS": "0",
            "OVERTE_DEVICE_LOCK_ROOT": str(self.root / "locks"),
        })
        result = subprocess.run([
            sys.executable, str(HARNESS), "--adapter-manifest", str(self.manifest),
            "--catalog", str(HARNESS.parent / "catalog.json"), "--suite", "smoke",
            "--output-dir", str(self.output),
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, check=False)
        self.assertEqual(1, result.returncode, result.stdout)
        summary = json.loads((self.output / "summary.json").read_text())
        self.assertEqual("error", summary["results"][0]["status"])
        junit = ET.parse(self.output / "junit.xml").getroot()
        self.assertEqual("1", junit.attrib["errors"])
        module_log = (self.output / "modules/launch-smoke/module.log").read_text()
        self.assertIn("INFRASTRUCTURE:", module_log)
        self.assertNotIn("private-device-123", module_log)

    def test_adapter_product_assertion_is_junit_failure_and_redacted(self):
        env = os.environ.copy()
        env.update({
            "MOCK_CLEANUP_MARKER": str(self.cleanup_marker),
            "MOCK_STATE": str(self.root / "state"),
            "MOCK_CAPABILITIES": "app.foreground,app.launch,app.process",
            "MOCK_ASSERTION_FAILURE": "1",
            "OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS": "0",
            "OVERTE_DEVICE_LOCK_ROOT": str(self.root / "locks"),
        })
        result = subprocess.run([
            sys.executable, str(HARNESS), "--adapter-manifest", str(self.manifest),
            "--catalog", str(HARNESS.parent / "catalog.json"), "--suite", "smoke",
            "--output-dir", str(self.output),
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, check=False)
        self.assertEqual(1, result.returncode, result.stdout)
        summary = json.loads((self.output / "summary.json").read_text())
        self.assertEqual("failed", summary["results"][0]["status"])
        junit = ET.parse(self.output / "junit.xml").getroot()
        self.assertEqual("1", junit.attrib["failures"])
        self.assertEqual("0", junit.attrib["errors"])
        module_log = (self.output / "modules/launch-smoke/module.log").read_text()
        self.assertIn("ASSERTION: application process restarted", module_log)
        self.assertNotIn("private-device-123", module_log)

    def test_cleanup_failure_is_junit_infrastructure_error_and_redacted(self):
        result = self.run_harness(environment={"MOCK_CLEANUP_FAILURE": "1"})
        self.assertEqual(1, result.returncode, result.stdout)
        summary = json.loads((self.output / "summary.json").read_text())
        cleanup = summary["results"][-1]
        self.assertEqual("target-cleanup", cleanup["id"])
        self.assertEqual("error", cleanup["status"])
        junit = ET.parse(self.output / "junit.xml").getroot()
        self.assertEqual("1", junit.attrib["errors"])
        self.assertNotIn("private-device-123", (self.output / "junit.xml").read_text())


if __name__ == "__main__":
    unittest.main()
