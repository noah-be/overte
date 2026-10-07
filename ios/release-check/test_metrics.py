"""Synthetic telemetry validates the gate, not physical-device performance."""
# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from device import analyze_metrics


class MetricsEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "synthetic-metrics.json"
        self.policy = dict(minimumSeconds=14400, maxRssMiB=2048, maxRssGrowthMiB=256,
                           maxMeanCpuPercent=200, maxBatteryDrainPerHour=30)
        self.errors = []
        def need(value, rule, message):
            if not value:
                self.errors.append(rule)
            return bool(value)
        self.ctx = SimpleNamespace(revision="a" * 40, need=need, inventories={},
                                   review=lambda name, *args, **kwargs: self.errors.append("review-" + name))
        self.sha = "b" * 64
        self.started = 1789776000000
        self.intervals = [(self.started, self.started + 14400000)]
        self.value = dict(sourceRevision=self.ctx.revision, artifactSha256=self.sha,
                          formFactor="ipad", startedEpochMs=self.started, charging=False,
                          samples=[dict(elapsedSeconds=i * 120, rssMiB=800, cpuPercent=50,
                                        processSession="synthetic-process", gpuPercent=20,
                                        batteryPercent=90 - i / 12, thermalState=0, freeDiskMiB=4096)
                                   for i in range(121)])

    def inspect(self):
        self.path.write_text(json.dumps(self.value))
        analyze_metrics(self.ctx, self.path, self.sha, "ipad", self.policy, self.intervals)

    def test_consistent_synthetic_campaign_has_no_failures(self):
        self.inspect()
        self.assertEqual(self.errors, [])

    def test_stale_artifact_is_rejected(self):
        self.value["artifactSha256"] = "c" * 64
        self.inspect()
        self.assertEqual(self.errors, ["metrics-binding"])

    def test_nonfinite_metrics_are_rejected(self):
        self.value["samples"][50]["rssMiB"] = float("nan")
        self.inspect()
        self.assertEqual(self.errors, ["metrics-values"])

    def test_sparse_measurements_cannot_cover_four_hours(self):
        self.value["samples"] = self.value["samples"][::4]
        self.inspect()
        self.assertIn("metrics-duration", self.errors)

    def test_unrelated_campaign_timestamps_are_rejected(self):
        self.value["startedEpochMs"] += 86400000
        self.inspect()
        self.assertIn("metrics-campaign-binding", self.errors)

    def test_process_restart_cannot_hide_memory_growth(self):
        self.value["samples"][-1]["processSession"] = "replacement-process"
        self.inspect()
        self.assertIn("continuous-process", self.errors)

    def test_charging_cannot_pass_battery_drain_gate(self):
        self.value["charging"] = True
        self.inspect()
        self.assertIn("battery-charging", self.errors)

    def test_peak_growth_cpu_and_thermal_budgets_block(self):
        for sample in self.value["samples"][-40:]:
            sample.update(rssMiB=2500, cpuPercent=1000, thermalState=3)
        self.inspect()
        self.assertTrue({"memory-budget", "memory-growth", "cpu-budget", "thermal-critical"} <= set(self.errors))


if __name__ == "__main__":
    unittest.main()
