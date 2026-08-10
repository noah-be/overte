import csv
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "analyze-phone-world-loading.py"
SPEC = importlib.util.spec_from_file_location("phone_world_analyzer", SCRIPT)
ANALYZER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(ANALYZER)


class AnalyzerTest(unittest.TestCase):
    def test_linear_slope_per_minute(self):
        rows = [
            {"elapsed_ms": "0", "pss_kb": "1000"},
            {"elapsed_ms": "60000", "pss_kb": "3048"},
            {"elapsed_ms": "120000", "pss_kb": "5096"},
        ]
        self.assertEqual(ANALYZER.linear_slope_per_minute(rows, "pss_kb"), 2048)
        self.assertEqual(len(ANALYZER.phase_rows(rows, 0, 60)), 2)

    def test_relative_spread(self):
        self.assertEqual(ANALYZER.relative_spread([10, 10]), 0)
        self.assertAlmostEqual(ANALYZER.relative_spread([8, 12]), 20)

    def test_first_sustained_idle(self):
        rows = [
            {"sample_epoch_ms": "1", "active_downloads": "0", "pending_downloads": "0"},
            {"sample_epoch_ms": "2", "active_downloads": "1", "pending_downloads": "0"},
            {"sample_epoch_ms": "3", "active_downloads": "0", "pending_downloads": "0"},
            {"sample_epoch_ms": "4", "active_downloads": "0", "pending_downloads": "0"},
        ]
        self.assertEqual(ANALYZER.first_sustained_idle(rows)["sample_epoch_ms"], "3")
        self.assertIsNone(ANALYZER.first_sustained_idle(rows[:2]))

    def test_summarizes_stable_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runs.csv"
            fields = ["run", "mean_cpu_percent", "max_cpu_percent", "max_pss_kb", "rx_delta_bytes", "tx_delta_bytes", "janky_percent", "max_thermal_status", "process_stable"]
            with path.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerow(dict(run=1, mean_cpu_percent=20, max_cpu_percent=50, max_pss_kb=204800, rx_delta_bytes=1048576, tx_delta_bytes=1024, janky_percent=5, max_thermal_status=2, process_stable=1))
            result = subprocess.run([sys.executable, SCRIPT, directory], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Overte Android Phone", result.stdout)
            self.assertIn("max PSS 200.0 MiB", result.stdout)
            self.assertIn("download: 1048576.00 bytes", result.stdout)

    def test_rejects_missing_report(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, SCRIPT, directory], text=True, capture_output=True)
            self.assertEqual(result.returncode, 2)

    def test_rejects_wrong_final_spawn_position(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory)
            fields = ["run", "mean_cpu_percent", "max_cpu_percent", "max_pss_kb", "rx_delta_bytes", "tx_delta_bytes", "janky_percent", "max_thermal_status", "process_stable"]
            with (report / "runs.csv").open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerow(dict(run=1, mean_cpu_percent=20, max_cpu_percent=50, max_pss_kb=204800, rx_delta_bytes=1, tx_delta_bytes=1, janky_percent=5, max_thermal_status=0, process_stable=1))
            with (report / "device.csv").open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["target"])
                writer.writeheader()
                writer.writerow({"target": "hifi://overte_hub/154.69,-98.296,-397.899"})
            run = report / "run-1"
            run.mkdir()
            with (run / "world-status.csv").open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["connected", "place", "domain_id", "x", "y", "z"])
                writer.writeheader()
                writer.writerow(dict(connected=1, place="overte_hub", domain_id="domain", x=0, y=0.566, z=0))
            result = subprocess.run([sys.executable, SCRIPT, directory], text=True, capture_output=True)
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("unexpected final client world", result.stdout)


if __name__ == "__main__":
    unittest.main()
