#!/usr/bin/env python3

import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "macos" / "ci" / "runner-telemetry.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("macos_runner_telemetry", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeCollector:
    def __init__(self, samples):
        self.samples = iter(samples)
        self.directory_requests = []

    def sample(self, include_directories=False):
        self.directory_requests.append(include_directories)
        metrics, directories = next(self.samples)
        return metrics, directories if include_directories else {}


class RunnerTelemetryTest(unittest.TestCase):
    def test_aggregates_five_second_samples_into_thirty_second_reports(self):
        module = load_tool()
        clock_values = iter([0, 0, 1, 5, 6, 10, 11, 15, 16, 20, 21, 25, 26, 30])
        collector = FakeCollector([
            ({"cpu_activity_pct": value, "ram_available_pct": 50,
              "disk_free_mib": 9000, "swap_used_pct": 0}, {})
            for value in (10, 20, 30, 40, 50, 60, 70)
        ])
        records = []
        module.run(collector, lambda event, **fields: records.append((event, fields)),
                   5, 30, 300, 4096, 10, 80, max_samples=7,
                   clock=lambda: next(clock_values), sleep=lambda _seconds: None)
        reports = [fields for event, fields in records if event == "report"]
        self.assertEqual(len(reports), 1)
        cpu = reports[0]["metrics"]["cpu_activity_pct"]
        self.assertEqual(cpu, {"current": 70.0, "min": 10.0, "max": 70.0, "avg": 40.0})
        self.assertEqual(reports[0]["samples"], 7)
        self.assertEqual(collector.directory_requests,
                         [True, False, False, False, False, False, False])

    def test_threshold_transitions_are_immediate_and_do_not_repeat(self):
        module = load_tool()
        samples = [
            ({"disk_free_mib": 3000, "ram_available_pct": 5, "swap_used_pct": 90}, {}),
            ({"disk_free_mib": 2000, "ram_available_pct": 4, "swap_used_pct": 91}, {}),
            ({"disk_free_mib": 8000, "ram_available_pct": 50, "swap_used_pct": 0}, {}),
        ]
        records = []
        ticks = iter(range(20))
        module.run(FakeCollector(samples), lambda event, **fields: records.append((event, fields)),
                   5, 30, 300, 4096, 10, 80, max_samples=3,
                   clock=lambda: next(ticks), sleep=lambda _seconds: None)
        thresholds = [fields for event, fields in records if event == "threshold"]
        self.assertEqual(len(thresholds), 6)
        self.assertEqual({row["state"] for row in thresholds}, {"active", "recovered"})

    def test_emitter_appends_flushes_and_contains_no_sensitive_context(self):
        module = load_tool()
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "telemetry.jsonl"
            log.write_text('{"existing":true}\n')
            log.chmod(0o666)
            stream = io.StringIO()
            emitter = module.Emitter(log, stream)
            os.environ["SIGNING_TOKEN"] = "do-not-leak"
            try:
                emitter("report", metrics={"cpu_activity_pct": {"current": 12}})
            finally:
                os.environ.pop("SIGNING_TOKEN", None)
            lines = log.read_text().splitlines()
            self.assertEqual(json.loads(lines[0]), {"existing": True})
            self.assertEqual(json.loads(lines[1])["macos_runner_telemetry"], "report")
            self.assertEqual(stream.getvalue(), lines[1] + "\n")
            self.assertNotIn("do-not-leak", log.read_text())
            self.assertNotIn(str(ROOT), log.read_text())
            self.assertEqual(log.stat().st_mode & 0o777, 0o600)

    def test_directory_labels_are_bounded_and_paths_are_never_reported(self):
        module = load_tool()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "payload").write_bytes(b"x" * 1024)
            collector = module.Collector(root, {"build-cache": root})
            with mock.patch.object(module, "_command", return_value=""):
                metrics, sizes = collector.sample(include_directories=True)
            self.assertIn("build-cache", sizes)
            serialized = json.dumps({"metrics": metrics, "directory_mib": sizes})
            self.assertNotIn(str(root), serialized)
            self.assertTrue(module.SAFE_LABEL.fullmatch("build-cache"))
            self.assertFalse(module.SAFE_LABEL.fullmatch("secret/path"))

    def test_memory_parsers_are_hermetic(self):
        module = load_tool()
        outputs = {
            ("sysctl", "-n", "hw.pagesize"): "4096\n",
            ("sysctl", "-n", "hw.memsize"): "1073741824\n",
            ("vm_stat",): "Pages free: 1000.\nPages inactive: 2000.\nPages speculative: 100.\n",
            ("sysctl", "-n", "vm.swapusage"): "total = 1024.00M used = 256.00M free = 768.00M\n",
            ("memory_pressure", "-Q"): "System-wide memory free percentage: 42%\n",
        }
        with mock.patch.object(module, "_command", side_effect=lambda command: outputs[tuple(command)]):
            result = module._mac_memory()
        self.assertEqual(result["swap_used_pct"], 25)
        self.assertEqual(result["memory_free_pct"], 42)
        self.assertGreater(result["ram_available_mib"], 0)

    def test_supervisor_preserves_child_exit_code_and_never_logs_command(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "runner.jsonl"
            secret = "never-print-this-command-secret"
            result = subprocess.run(
                [sys.executable, str(TOOL), "--log", str(log),
                 "--sample-interval", "0.01", "--publish-interval", "0.02",
                 "--directory-interval", "0.03", "--",
                 sys.executable, "-c", "import sys;sys.exit(37)", secret],
                capture_output=True, text=True, timeout=5, check=False,
            )
            self.assertEqual(result.returncode, 37, result.stdout + result.stderr)
            combined = result.stdout + result.stderr + log.read_text()
            self.assertNotIn(secret, combined)
            self.assertNotIn("sys.exit", combined)


if __name__ == "__main__":
    unittest.main()
