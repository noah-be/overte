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
    if os.environ.get("MOCK_DESCRIBE_FAILURE_MARKER") and pathlib.Path(os.environ["MOCK_DESCRIBE_FAILURE_MARKER"]).exists():
        raise SystemExit(9)
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
    elif a.operation == "app.stop":
        if state:
            open(state, "w", encoding="utf-8").write("stopped")
        value = {"stopped": True}
    elif a.operation == "app.process":
        running = not state or not os.path.exists(state) or open(state, encoding="utf-8").read() != "stopped"
        value = {"running": running, "identity": "mock-process-42" if running else None}
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

    def run_error_then_success(self, transport_loss=False):
        marker = self.root / "transport-lost"
        self.module.write_text(
            "from pathlib import Path\n"
            + (f"Path({str(marker)!r}).touch()\n" if transport_loss else "")
            + "raise SystemExit(75)\n")
        later = self.root / "later.py"
        later.write_text("raise SystemExit(0)\n")
        catalog = json.loads(self.catalog.read_text())
        catalog["modules"].append({
            "id": "later", "description": "Independent later module",
            "command": ["later.py"], "suites": ["smoke"],
            "requires": ["app.process"], "timeoutSeconds": 10,
        })
        self.catalog.write_text(json.dumps(catalog))
        result = self.run_harness("--require-complete", environment={
            "OVERTE_DEVICE_CONTINUE_AFTER_MODULE_ERROR": "1",
            "MOCK_DESCRIBE_FAILURE_MARKER": str(marker),
        })
        self.assertEqual(1, result.returncode, result.stdout)
        self.assertTrue(self.cleanup_marker.exists())
        return json.loads((self.output / "summary.json").read_text())

    def test_opt_in_continues_after_module_error_and_retains_failure(self):
        summary = self.run_error_then_success()
        self.assertEqual(["error", "passed"], [
            entry["status"] for entry in summary["results"]])
        self.assertTrue((self.output / "modules/later").exists())

    def test_opt_in_still_stops_if_target_reinspection_fails(self):
        summary = self.run_error_then_success(transport_loss=True)
        self.assertEqual(["error", "error"], [
            entry["status"] for entry in summary["results"]])
        self.assertEqual("target-execution", summary["results"][1]["id"])
        self.assertFalse((self.output / "modules/later").exists())

    def run_stopped_failure_recovery(self, *, scene_failure=False, live=False, domain_test=False):
        state = self.root / "state"
        scene_count = self.root / "scene-count"
        scene = self.root / "scene.py"
        scene.write_text(
            "from pathlib import Path\n"
            f"count = Path({str(scene_count)!r})\n"
            "n = int(count.read_text()) + 1 if count.exists() else 1\n"
            "count.write_text(str(n))\n"
            f"raise SystemExit(1 if {scene_failure!r} and n > 1 else 0)\n")
        fault = self.root / "fault.py"
        fault.write_text(
            "from pathlib import Path\n"
            + ("" if live else f"Path({str(state)!r}).write_text('stopped')\n")
            + "raise SystemExit(75)\n")
        later = self.root / "later.py"
        later.write_text(
            "from pathlib import Path\n"
            f"assert Path({str(state)!r}).read_text() == 'foreground'\n"
            f"assert int(Path({str(scene_count)!r}).read_text()) >= {1 if live else 2}\n")
        launch = HARNESS.parent / "modules/launch_smoke.py"
        commands = [("launch-smoke", launch), ("scene", scene)]
        if domain_test:
            commands.append(("domain-enter", self.module))
        commands += [("fault", fault), ("entity-sync" if domain_test else "later", later)]
        self.catalog.write_text(json.dumps({"schemaVersion": 1, "modules": [
            {"id": name, "description": name, "command": [str(command)],
             "suites": ["smoke"], "requires": ["app.launch", "app.process"],
             "timeoutSeconds": 10}
            for name, command in commands]}))
        result = self.run_harness("--require-complete", environment={
            "MOCK_CAPABILITIES": "app.launch,app.process",
            "OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS": "0",
            "OVERTE_DEVICE_CONTINUE_AFTER_MODULE_ERROR": "1",
            "OVERTE_DEVICE_RECOVER_STOPPED_APP_AFTER_FAILURE": "1"})
        self.assertEqual(1, result.returncode, result.stdout)
        return json.loads((self.output / "summary.json").read_text()), scene_count

    def test_stopped_failure_is_retained_and_later_module_gets_verified_world(self):
        summary, count = self.run_stopped_failure_recovery()
        self.assertEqual(["passed", "passed", "error", "passed"],
                         [r["status"] for r in summary["results"]])
        self.assertEqual(2, int(count.read_text()))
        recovery = json.loads((self.output / "preconditions/later/recovery.json").read_text())
        self.assertTrue(recovery["observedStopped"])
        self.assertTrue(recovery["verified"])
        self.assertEqual("fault", recovery["previousModule"])
        self.assertTrue((self.output / "modules/fault/INVALID").exists())

    def test_recovery_does_not_restart_a_live_app_after_a_module_error(self):
        summary, count = self.run_stopped_failure_recovery(live=True)
        self.assertEqual(["passed", "passed", "error", "passed"],
                         [r["status"] for r in summary["results"]])
        self.assertEqual(1, int(count.read_text()))
        self.assertFalse((self.output / "preconditions/later").exists())

    def test_stopped_process_recovery_restores_domain_before_dependent_test(self):
        summary, _count = self.run_stopped_failure_recovery(domain_test=True)
        self.assertEqual(["passed", "passed", "passed", "error", "passed"],
                         [r["status"] for r in summary["results"]])
        recovery = json.loads((self.output / "preconditions/entity-sync/recovery.json").read_text())
        self.assertTrue(recovery["verified"])
        self.assertEqual(["launch-smoke", "scene", "domain-enter"],
                         [r["id"] for r in recovery["prerequisites"]])

    def test_failed_recovery_world_prevents_later_module_execution(self):
        summary, _count = self.run_stopped_failure_recovery(scene_failure=True)
        self.assertEqual("target-execution", summary["results"][-1]["id"])
        self.assertEqual("error", summary["results"][-1]["status"])
        self.assertFalse((self.output / "modules/later").exists())
        recovery = json.loads((self.output / "preconditions/later/recovery.json").read_text())
        self.assertFalse(recovery["verified"])

    def run_domain_fault_isolation(self, *, fault_passes=False, domain_failure=False):
        scene_count = self.root / "scene-count"
        domain_count = self.root / "domain-count"
        scene = self.root / "scene.py"
        domain = self.root / "domain.py"
        for command, count, can_fail in [(scene, scene_count, False),
                                          (domain, domain_count, domain_failure)]:
            command.write_text(
                "from pathlib import Path\n"
                f"count=Path({str(count)!r})\n"
                "n=int(count.read_text())+1 if count.exists() else 1\n"
                "count.write_text(str(n))\n"
                f"raise SystemExit(1 if {can_fail!r} and n > 1 else 0)\n")
        fault = self.root / "fault.py"
        fault.write_text(f"raise SystemExit({0 if fault_passes else 1})\n")
        later = self.root / "later.py"
        later.write_text(
            "from pathlib import Path\n"
            f"assert Path({str(self.root / 'state')!r}).read_text() == 'foreground'\n"
            f"assert int(Path({str(scene_count)!r}).read_text()) == {1 if fault_passes else 2}\n"
            f"assert int(Path({str(domain_count)!r}).read_text()) == {1 if fault_passes else 2}\n")
        launch = HARNESS.parent / "modules/launch_smoke.py"
        self.catalog.write_text(json.dumps({"schemaVersion": 1, "modules": [
            {"id": name, "description": name, "command": [str(command)],
             "suites": ["smoke"], "requires": ["app.launch", "app.process"],
             "timeoutSeconds": 10}
            for name, command in [("launch-smoke", launch), ("scene", scene),
                ("domain-enter", domain), ("network-fault-recovery", fault), ("entity-sync", later)]]}))
        result = self.run_harness("--require-complete", environment={
            "MOCK_CAPABILITIES": "app.launch,app.process,app.stop",
            "OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS": "0",
            "OVERTE_DEVICE_RECOVER_DOMAIN_AFTER_FAULT": "1"})
        self.assertEqual(0 if fault_passes else 1, result.returncode, result.stdout)
        return json.loads((self.output / "summary.json").read_text())

    def test_failed_outage_retained_but_next_domain_test_has_fresh_prerequisites(self):
        summary = self.run_domain_fault_isolation()
        self.assertEqual(["passed", "passed", "passed", "failed", "passed"],
                         [r["status"] for r in summary["results"]])
        self.assertTrue((self.output / "modules/network-fault-recovery/INVALID").exists())
        receipt = json.loads((self.output / "preconditions/entity-sync/domain-isolation/recovery.json").read_text())
        self.assertTrue(receipt["stopped"])
        self.assertTrue(receipt["verified"])
        self.assertEqual(["launch-smoke", "scene", "domain-enter"],
                         [r["id"] for r in receipt["prerequisites"]])

    def test_passing_outage_does_not_restart_before_next_domain_test(self):
        summary = self.run_domain_fault_isolation(fault_passes=True)
        self.assertTrue(all(r["status"] == "passed" for r in summary["results"]))
        self.assertFalse((self.output / "preconditions/entity-sync").exists())

    def test_failed_domain_reentry_prevents_execution_of_dependent_test(self):
        summary = self.run_domain_fault_isolation(domain_failure=True)
        self.assertEqual("failed", summary["results"][-2]["status"])
        self.assertEqual("target-execution", summary["results"][-1]["id"])
        self.assertFalse((self.output / "modules/entity-sync").exists())
        receipt = json.loads((self.output / "preconditions/entity-sync/domain-isolation/recovery.json").read_text())
        self.assertFalse(receipt["verified"])

    def test_missing_capability_is_reported_as_skip(self):
        result = self.run_harness(environment={"MOCK_CAPABILITIES": "telemetry.memory"})
        self.assertEqual(0, result.returncode, result.stdout)
        summary = json.loads((self.output / "summary.json").read_text())
        self.assertEqual("skipped", summary["results"][0]["status"])
        self.assertTrue(self.cleanup_marker.exists())

    def test_failed_world_gate_blocks_later_tests_without_counting_them_as_passed(self):
        catalog = json.loads(self.catalog.read_text())
        catalog["modules"][0]["id"] = "scene"
        catalog["modules"].append({
            "id": "later", "description": "Must not execute in an unloaded world",
            "command": ["module.py"], "suites": ["smoke"],
            "requires": ["app.process"], "timeoutSeconds": 10,
        })
        self.catalog.write_text(json.dumps(catalog))
        result = self.run_harness("--require-complete", environment={
            "MOCK_MODULE_EXIT": "1", "OVERTE_E2E_REQUIRE_FIXTURE_SCREENSHOT": "1",
            "OVERTE_DEVICE_CONTINUE_AFTER_MODULE_ERROR": "1"})
        self.assertEqual(1, result.returncode, result.stdout)
        self.assertFalse((self.output / "modules/later").exists())
        self.assertTrue(self.cleanup_marker.exists())
        summary = json.loads((self.output / "summary.json").read_text())
        self.assertEqual(["failed", "skipped"], [item["status"] for item in summary["results"]])

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
