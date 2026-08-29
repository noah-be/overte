#!/usr/bin/env python3
"""Device-free proof of the versioned semantic tablet E2E contract."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


DEVICE_ROOT = Path(__file__).resolve().parents[1]
if str(DEVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(DEVICE_ROOT))

from contracts import (load_capability_registry, load_tablet_product_policy,
                       load_tablet_ui_contract, validate_operation_arguments,
                       validate_tablet_product_policy, validate_tablet_ui_snapshot)  # noqa: E402


class TabletContractValidationTest(unittest.TestCase):
    @staticmethod
    def snapshot() -> dict:
        return {
            "contractVersion": 1,
            "schemaVersion": 1,
            "screenId": "settings.home",
            "ready": True,
            "visibleControlIds": ["nav.home", "settings.general"],
            "selectedControlIds": [],
        }

    def test_snapshot_accepts_only_known_sorted_unique_semantics(self):
        value = self.snapshot()
        self.assertIs(value, validate_tablet_ui_snapshot(value))
        mutations = {
            "malformed": lambda item: item.pop("ready"),
            "duplicate": lambda item: item["visibleControlIds"].append("nav.home"),
            "unsorted": lambda item: item["visibleControlIds"].reverse(),
            "unknown-control": lambda item: item["visibleControlIds"].append(
                "settings.unknown"),
            "unknown-contract": lambda item: item.update(contractVersion=2),
            "unknown-schema": lambda item: item.update(schemaVersion=2),
            "selected-not-visible": lambda item: item["selectedControlIds"].append(
                "nav.close"),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                candidate = copy.deepcopy(value)
                mutate(candidate)
                with self.assertRaises(ValueError):
                    validate_tablet_ui_snapshot(candidate)

    def test_activate_request_is_versioned_and_closed(self):
        request = {"contractVersion": 1, "controlId": "app.settings"}
        self.assertIs(request, validate_operation_arguments("tablet.activate", request))
        for candidate in (
                {"contractVersion": 2, "controlId": "app.settings"},
                {"contractVersion": 1, "controlId": "settings.unknown"},
                {"contractVersion": 1, "controlId": "app.settings", "x": 1}):
            with self.assertRaises(ValueError):
                validate_operation_arguments("tablet.activate", candidate)
        with self.assertRaises(ValueError):
            validate_operation_arguments("tablet.snapshot", {"screen": "tablet.home"})

    def test_policy_is_external_versioned_and_fail_closed(self):
        path = DEVICE_ROOT / "policies/mock-flat-touch.json"
        value = load_tablet_product_policy(path)
        self.assertEqual("mock.flat-touch", value["profileId"])
        candidate = copy.deepcopy(value)
        candidate["expectations"]["settings.home"]["forbiddenControlIds"] = [
            "settings.controllers", "settings.controllers"]
        with self.assertRaisesRegex(ValueError, "sorted, unique"):
            validate_tablet_product_policy(candidate)
        candidate = copy.deepcopy(value)
        candidate["expectations"]["settings.general"]["entryControlId"] = "settings.controllers"
        with self.assertRaisesRegex(ValueError, "must be required on settings.home"):
            validate_tablet_product_policy(candidate)

    def test_schema_enums_match_the_taxonomy_and_public_names_are_neutral(self):
        contract = load_tablet_ui_contract()
        snapshot_schema = json.loads((DEVICE_ROOT / "schemas/tablet-ui-snapshot.schema.json")
                                     .read_text(encoding="utf-8"))
        policy_schema = json.loads((DEVICE_ROOT / "schemas/tablet-product-policy.schema.json")
                                   .read_text(encoding="utf-8"))
        for schema in (snapshot_schema, policy_schema):
            self.assertEqual(contract["controlIds"], schema["$defs"]["controlId"]["enum"])
            self.assertEqual(contract["screenIds"], schema["$defs"]["screenId"]["enum"])
        public_names = [*contract["controlIds"], *contract["screenIds"],
                        *load_capability_registry()]
        for value in public_names:
            for product_name in ("android", "iphone", "ipad", "pico", "quest"):
                self.assertNotIn(product_name, value.lower())


class TabletE2EFlowTest(unittest.TestCase):
    def run_tablet(self, profile: str, policy_name: str, *, mutation: str = "",
                   missing_capability: str = "", infrastructure_failure: bool = False):
        temporary = tempfile.TemporaryDirectory(prefix="overte-tablet-e2e-")
        root = Path(temporary.name)
        output = root / "results"
        environment = os.environ.copy()
        environment.update({
            "OVERTE_MOCK_E2E_STATE": str(root / "state.json"),
            "OVERTE_MOCK_TABLET_UI_PROFILE": profile,
            "OVERTE_DEVICE_LAUNCH_SETTLE_SECONDS": "0",
            "OVERTE_DEVICE_LOCK_ROOT": str(root / "locks"),
            "OVERTE_E2E_POLL_SECONDS": "0.05",
            "OVERTE_E2E_TIMEOUT_SECONDS": "1",
            "OVERTE_MOCK_PRIVATE_SECRET": "secret-target-selector-do-not-persist",
            "OVERTE_MOCK_ASSERT_POLICY_ISOLATED": "1",
        })
        if mutation:
            environment["OVERTE_MOCK_TABLET_MUTATION"] = mutation
        if missing_capability:
            environment["OVERTE_MOCK_MISSING_CAPABILITY"] = missing_capability
        if infrastructure_failure:
            environment["OVERTE_MOCK_TABLET_INFRASTRUCTURE_FAILURE"] = "1"
        result = subprocess.run([
            sys.executable, str(DEVICE_ROOT / "run.py"),
            "--adapter-manifest", str(DEVICE_ROOT / "adapters/mock/adapter.json"),
            "--catalog", str(DEVICE_ROOT / "catalog.json"),
            "--suite", "tablet-e2e",
            "--tablet-policy", str(DEVICE_ROOT / f"policies/{policy_name}"),
            "--allow-virtual", "--require-complete",
            "--output-dir", str(output),
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
           env=environment, check=False)
        summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
        return temporary, output, result, summary

    @staticmethod
    def tablet_result(summary: dict) -> dict:
        return next(item for item in summary["results"] if item["id"] == "tablet-e2e")

    def assert_flow(self, profile: str, policy: str, expected_status: str,
                    **options) -> tuple[Path, subprocess.CompletedProcess, dict, tempfile.TemporaryDirectory]:
        temporary, output, result, summary = self.run_tablet(
            profile, policy, **options)
        self.assertEqual(expected_status, self.tablet_result(summary)["status"], result.stdout)
        self.assertEqual(0 if expected_status == "passed" else 1, result.returncode, result.stdout)
        return output, result, summary, temporary

    def test_complete_flat_touch_flow_passes(self):
        output, _, _, temporary = self.assert_flow(
            "flat", "mock-flat-touch.json", "passed")
        try:
            evaluation = json.loads((output / "modules/tablet-e2e/tablet-policy-evaluation.json")
                                    .read_text(encoding="utf-8"))
            self.assertEqual("mock.flat-touch", evaluation["profileId"])
            self.assertTrue(evaluation["evaluations"])
            self.assertFalse((output / "modules/tablet-e2e/INVALID").exists())
        finally:
            temporary.cleanup()

    def test_complete_vr_render_resolution_flow_passes(self):
        _, _, _, temporary = self.assert_flow(
            "vr", "mock-vr-render-resolution.json", "passed")
        temporary.cleanup()

    def test_product_assertion_failures_remain_failures(self):
        cases = (
            ("flat", "mock-flat-touch.json", "missing-required", "missing required"),
            ("flat", "mock-flat-touch.json", "show-hmd", "forbidden"),
            ("flat", "mock-flat-touch.json", "show-controllers", "forbidden"),
            ("flat", "mock-flat-touch.json", "show-vr-render-resolution", "forbidden"),
            ("vr", "mock-vr-render-resolution.json", "missing-hmd", "missing required"),
            ("vr", "mock-vr-render-resolution.json", "missing-vr-render-resolution",
             "missing required"),
            ("flat", "mock-flat-touch.json", "not-ready", "ready stable"),
            ("flat", "mock-flat-touch.json", "wrong-screen", "ready stable"),
            ("flat", "mock-flat-touch.json", "action-no-transition", "ready stable"),
            ("flat", "mock-flat-touch.json", "process-restart", "restarted"),
        )
        for profile, policy, mutation, message in cases:
            with self.subTest(mutation=mutation):
                output, _, _, temporary = self.assert_flow(
                    profile, policy, "failed", mutation=mutation)
                try:
                    log = (output / "modules/tablet-e2e/module.log").read_text(
                        encoding="utf-8")
                    self.assertIn("ASSERTION:", log)
                    self.assertIn(message, log)
                finally:
                    temporary.cleanup()

    def test_malformed_adapter_snapshots_are_infrastructure_errors(self):
        for mutation in ("malformed", "duplicate-ids", "unsorted-ids", "unknown-id",
                         "unknown-version", "unknown-schema-version"):
            with self.subTest(mutation=mutation):
                output, _, _, temporary = self.assert_flow(
                    "flat", "mock-flat-touch.json", "error", mutation=mutation)
                try:
                    log = (output / "modules/tablet-e2e/module.log").read_text(
                        encoding="utf-8")
                    self.assertIn("INFRASTRUCTURE:", log)
                finally:
                    temporary.cleanup()

    def test_missing_required_operation_is_completeness_error(self):
        output, _, _, temporary = self.assert_flow(
            "flat", "mock-flat-touch.json", "error",
            missing_capability="tablet.activate")
        try:
            junit = (output / "junit.xml").read_text(encoding="utf-8")
            self.assertIn("Missing capabilities: tablet.activate", junit)
        finally:
            temporary.cleanup()

    def test_transport_failure_is_distinct_from_product_assertion(self):
        output, _, _, temporary = self.assert_flow(
            "flat", "mock-flat-touch.json", "error", infrastructure_failure=True)
        try:
            log = (output / "modules/tablet-e2e/module.log").read_text(encoding="utf-8")
            self.assertIn("INFRASTRUCTURE:", log)
            self.assertNotIn("ASSERTION:", log)
        finally:
            temporary.cleanup()

    def test_results_and_artifacts_do_not_persist_private_values(self):
        output, result, _, temporary = self.assert_flow(
            "flat", "mock-flat-touch.json", "passed")
        try:
            persisted = result.stdout
            for path in output.rglob("*"):
                if path.is_file():
                    persisted += path.read_text(encoding="utf-8", errors="replace")
            self.assertNotIn("mock-e2e-target", persisted)
            self.assertNotIn("secret-target-selector-do-not-persist", persisted)
        finally:
            temporary.cleanup()


if __name__ == "__main__":
    unittest.main()
