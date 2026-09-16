# SPDX-License-Identifier: Apache-2.0
"""Synthetic data only. Exercise the real Phone CLI and original Shared validator."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
CLI = ROOT / "android/phone/tools/performance/analyze.py"
spec = importlib.util.spec_from_file_location("phone_metrics", CLI)
phone = importlib.util.module_from_spec(spec)
spec.loader.exec_module(phone)
from metrics import fixture_digest


class PhoneMetricsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="phone-metrics-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.artifact = self.root / "synthetic-candidate.bin"
        self.artifact.write_bytes(b"synthetic bytes; not an APK or device result")
        self.artifact_sha = hashlib.sha256(self.artifact.read_bytes()).hexdigest()
        self.fixture = fixture_digest()
        self.trace = self.root / "synthetic-trace.json"
        self.document = dict(contract="overte-sh008-trace-v1", sourceRevision="a" * 40,
                             artifactSha256=self.artifact_sha, platform="android-phone",
                             fixtureSha256=self.fixture,
                             samples=[dict(elapsedMs=t, frameP95Ms=15,
                                           memory={"kind": "android-total-pss", "bytes": 100000000},
                                           thermal="nominal", batteryPercent=80,
                                           processEnergyJoules=None, queueDepth=1, blackFrames=0,
                                           degradation="normal", checkpoint=t == 1800000)
                                      for t in range(0, 3600001, 30000)])
        self.save()

    def save(self):
        self.trace.write_text(json.dumps(self.document))

    def arguments(self):
        return ["--trace", str(self.trace), "--artifact", str(self.artifact),
                "--expected-source-sha", "a" * 40, "--expected-artifact-sha256", self.artifact_sha,
                "--expected-fixture-sha256", self.fixture]

    def cli(self, extra=()):
        return subprocess.run([sys.executable, str(CLI), *self.arguments(), *extra],
                              text=True, capture_output=True, timeout=5)

    def check(self, budget=None, expected_budget=None):
        return phone.analyze_phone(self.trace, self.artifact, "a" * 40,
                                   self.artifact_sha, self.fixture, budget, expected_budget)

    def test_real_cli_binds_full_phone_duration_without_acceptance(self):
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        aggregate = json.loads(result.stdout)
        self.assertEqual(aggregate["status"], "METRICS_BOUND_BUDGETS_PENDING")
        self.assertEqual(aggregate["durationMs"], 3600000)
        self.assertEqual(aggregate["sampleCount"], 121)
        self.assertEqual(aggregate["memoryKind"], "android-total-pss")

    def test_foreign_identity_platform_short_gap_and_checkpoint_rejected(self):
        original = copy.deepcopy(self.document)
        mutations = [lambda d: d.update(platform="pico4"),
                     lambda d: d.update(sourceRevision="c" * 40),
                     lambda d: d.update(artifactSha256="c" * 64),
                     lambda d: d.update(fixtureSha256="c" * 64),
                     lambda d: d.update(samples=d["samples"][:-1]),
                     lambda d: d["samples"].pop(4),
                     lambda d: d["samples"][60].update(checkpoint=False)]
        for mutation in mutations:
            self.document = copy.deepcopy(original)
            mutation(self.document)
            self.save()
            with self.assertRaises(ValueError):
                self.check()

    def test_measurements_stop_and_unit_mapping(self):
        original = copy.deepcopy(self.document)
        for key, value in [("thermal", "critical"), ("thermal", "unavailable"),
                           ("thermal", "serious"), ("blackFrames", 1), ("blackFrames", None),
                           ("frameP95Ms", False), ("processEnergyJoules", 0),
                           ("memory", {"kind": "ios-physical-footprint", "bytes": 1000})]:
            with self.subTest(key=key, value=value):
                self.document = copy.deepcopy(original)
                self.document["samples"][2][key] = value
                self.save()
                with self.assertRaises(ValueError):
                    self.check()
        self.document = original
        self.document["samples"][2].update(thermal="serious", degradation="reduced")
        self.save()
        self.assertEqual(self.check()["status"], "METRICS_BOUND_BUDGETS_PENDING")

    def test_candidate_bytes_and_file_aliases(self):
        self.artifact.write_bytes(b"changed")
        with self.assertRaises(ValueError):
            self.check()
        alias = self.root / "alias.bin"
        os.link(self.trace, alias)
        with self.assertRaises(ValueError):
            phone.analyze_phone(self.trace, alias, "a" * 40, self.artifact_sha, self.fixture)
        link = self.root / "symlink.bin"
        link.symlink_to(self.artifact)
        with self.assertRaises(ValueError):
            phone.analyze_phone(self.trace, link, "a" * 40, self.artifact_sha, self.fixture)

    def test_synthetic_budget_requires_independent_expected_digest(self):
        budget = self.root / "synthetic-budget.json"
        budget.write_text(json.dumps(dict(contract="overte-sh008-budget-v1", platform="android-phone",
            fixtureSha256=self.fixture, memoryKind="android-total-pss", maxFrameP95Ms=15,
            maxMemoryGrowthBytes=0, maxQueueDepth=1, minBatteryEndPercent=80)))
        # Only synthetic tests manufacture approval; production requires a separately frozen digest.
        expected = hashlib.sha256(budget.read_bytes()).hexdigest()
        self.assertEqual(self.check(budget, expected)["status"], "BUDGETS_CHECKED_NOT_NODE_ACCEPTED")
        for path, digest in [(budget, None), (budget, "c" * 64), (None, expected)]:
            with self.assertRaises(ValueError):
                self.check(path, digest)
        self.document["samples"][2]["queueDepth"] = None
        self.save()
        self.assertEqual(self.check()["status"], "METRICS_BOUND_BUDGETS_PENDING")
        with self.assertRaises(ValueError):
            self.check(budget, expected)

    def test_cli_closed_diagnostics_and_duplicate_options(self):
        result = self.cli(["--expected-source-sha", "private.invalid/value"])
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, "PHONE_METRICS_ARGUMENTS_REJECTED\n")
        self.trace.write_text('{"private.invalid/value":')
        result = self.cli()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, "PHONE_METRICS_REJECTED\n")
        self.assertEqual(result.stdout, "")

    def test_each_budget_threshold_is_enforced(self):
        budget = self.root / "synthetic-budget.json"
        budget.write_text(json.dumps(dict(contract="overte-sh008-budget-v1", platform="android-phone",
            fixtureSha256=self.fixture, memoryKind="android-total-pss", maxFrameP95Ms=15,
            maxMemoryGrowthBytes=0, maxQueueDepth=1, minBatteryEndPercent=80)))
        expected = hashlib.sha256(budget.read_bytes()).hexdigest()
        original = copy.deepcopy(self.document)
        for key, value in [("frameP95Ms", 15.01), ("queueDepth", 2), ("batteryPercent", 79.99),
                           ("memory", {"kind": "android-total-pss", "bytes": 100000001})]:
            with self.subTest(key=key):
                self.document = copy.deepcopy(original)
                self.document["samples"][-1][key] = value
                self.save()
                with self.assertRaises(ValueError):
                    self.check(budget, expected)


if __name__ == "__main__":
    unittest.main()
