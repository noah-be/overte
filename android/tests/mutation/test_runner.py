#!/usr/bin/env python3
"""Regression checks ensuring harness crashes never count as mutant kills."""

import importlib.util
import os
import sys
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).with_name("run_mutations.py")
SPEC = importlib.util.spec_from_file_location("overte_mutation_runner", MODULE_PATH)
runner = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)
SELF_TEST_TMP = runner.ROOT / "build/tmp/mutation-selftests"
SELF_TEST_TMP.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(SELF_TEST_TMP)


class MutationClassificationTest(unittest.TestCase):
    def test_jvm_exception_is_infrastructure_error(self):
        mutant = runner.Mutant(
            "intentional-jvm-crash", "java", runner.JAVA_PRODUCTION["deep"],
            'return "hifi" + value.substring(schemeSeparator);',
            'throw new RuntimeException("intentional harness crash");')
        with tempfile.TemporaryDirectory() as temporary:
            status, output = runner.execute(Path(temporary), mutant, "java")
        self.assertEqual("error", status)
        self.assertIn("harness crashed", output)

    def test_native_abnormal_exit_is_infrastructure_error(self):
        mutant = runner.Mutant(
            "intentional-native-crash", "handoff", runner.HANDOFF,
            "_pending = true;", "throw 7;")
        with tempfile.TemporaryDirectory() as temporary:
            status, output = runner.execute(Path(temporary), mutant, "handoff")
        self.assertEqual("error", status)
        self.assertIn("harness crashed", output)

    def test_javascript_runtime_error_is_infrastructure_error(self):
        source = runner.SCRIPTS / "quickGoto.js"
        mutant = runner.Mutant(
            "intentional-javascript-crash", "javascript", source,
            "if (home) {", 'throw new Error("intentional harness crash");\n        if (home) {')
        with tempfile.TemporaryDirectory() as temporary:
            status, output = runner.execute(Path(temporary), mutant, "javascript")
        self.assertEqual("error", status)
        self.assertIn("JavaScript harness crashed", output)

    def test_pattern_collision_is_infrastructure_error(self):
        mutant = runner.Mutant(
            "collision", "java", runner.JAVA_PRODUCTION["permission"],
            "this pattern does not exist", "replacement")
        with tempfile.TemporaryDirectory() as temporary:
            status, output = runner.execute(Path(temporary), mutant, "java")
        self.assertEqual("error", status)
        self.assertIn("matched 0 times", output)

    def test_behaviorally_equivalent_mutant_survives(self):
        mutant = runner.Mutant(
            "equivalent", "java", runner.JAVA_PRODUCTION["permission"],
            "return requestCode == RECORD_AUDIO_REQUEST;",
            "return RECORD_AUDIO_REQUEST == requestCode;")
        with tempfile.TemporaryDirectory() as temporary:
            status, _ = runner.execute(Path(temporary), mutant, "java")
        self.assertEqual("survived", status)

    def test_timeout_and_missing_tool_are_not_assertion_failures(self):
        with mock.patch.object(runner.subprocess, "run", side_effect=runner.subprocess.TimeoutExpired("x", 1)):
            timed_out = runner.command(["x"], Path("."), timeout=1)
        self.assertEqual(124, timed_out.returncode)
        self.assertIn("timed out", timed_out.stderr)
        with mock.patch.object(runner.subprocess, "run", side_effect=FileNotFoundError(2, "missing", "compiler")):
            missing = runner.command(["compiler"], Path("."))
        self.assertEqual(127, missing.returncode)
        self.assertIn("unavailable", missing.stderr)

    def test_atomic_reports_remain_valid_during_parallel_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "report.json"
            payloads = [{"sequence": list(range(100)), "writer": writer} for writer in range(8)]
            threads = [threading.Thread(target=runner.write_report, args=(report, payload)) for payload in payloads]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            import json
            actual = json.loads(report.read_text(encoding="utf-8"))
        self.assertIn(actual, payloads)

    def test_baseline_failure_stops_before_mutants_and_writes_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "baseline-error.json"
            environment = dict(os.environ)
            environment["PATH"] = ""
            result = subprocess.run(
                [sys.executable, str(MODULE_PATH), "--report", str(report)],
                text=True, capture_output=True, env=environment, check=False)
            import json
            payload = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(2, result.returncode)
        self.assertEqual([], payload["mutants"])
        self.assertEqual("error", payload["baseline"][0]["status"])

    def test_curated_mutant_order_is_stable(self):
        quick = [mutant.name for mutant in runner.MUTANTS if not mutant.extended]
        self.assertEqual([
            "legacy-url-skip-hifi-prefix", "legacy-asset-skip-base-prefix",
            "pico-audio-accept-unknown-source", "pico-audio-disable-callback-overflow",
            "pico-audio-deliver-stale-read",
            "pico-activity-null-extra-literal", "pico-activity-pre-s-exact-alarm",
            "pico-instance-ignore-registration", "pico-instance-retain-destroyed",
            "deep-link-length-boundary", "deep-link-allow-unsafe",
            "launch-skip-restored-validation", "permission-accept-unrelated",
            "pending-attempt-while-paused", "asset-disable-containment",
            "extractor-ignore-marker-validation", "extractor-disable-cache-hit",
            "extractor-disable-parent-creation", "extractor-disable-stale-replacement",
            "login-initially-pending", "login-accept-duplicate-submit",
            "login-submit-does-not-pend",
            "graphics-bool-never-true", "graphics-float-disable-lower-clamp",
            "graphics-unsigned-accept-suffix", "handoff-never-pending",
            "js-tablet-leak-menu-button", "js-actionbar-leak-goto-handler",
            "js-quick-goto-disable-home", "js-places-keep-message-subscription",
            "js-portal-allow-duplicate-entry",
        ], quick)


if __name__ == "__main__":
    unittest.main()
